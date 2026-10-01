"""HTTP endpoint the iOS Shortcut calls on geofence arrive/leave.

POST /event  {"event": "arrive" | "leave"}   Authorization: Bearer <API_TOKEN>

An arrive schedules a clock-in after ARRIVE_DELAY_S; a leave inside that delay cancels it
(drive-by). A leave schedules a clock-out after LEAVE_DELAY_S; re-arriving cancels it.
"""
import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import guards, paycor
from .config import Config

log = logging.getLogger("autopunch")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

cfg = Config()
pending: dict[str, asyncio.Task] = {}
lock = asyncio.Lock()


def load_state() -> dict:
    try:
        return json.loads(cfg.state_file.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"clocked_in": False, "last": None}


def save_state(state: dict) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_file.write_text(json.dumps(state))


async def notify(title: str, body: str, priority: str = "default") -> None:
    log.info("%s: %s", title, body)
    if not cfg.ntfy_topic:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"https://ntfy.sh/{cfg.ntfy_topic}", content=body,
                         headers={"Title": title, "Priority": priority})
    except httpx.HTTPError:
        log.exception("notify failed")


async def do_punch(action: str, delay: int) -> None:
    await asyncio.sleep(delay)
    pending.pop(action, None)
    async with lock:
        state = load_state()
        now = datetime.now(cfg.tz)
        reason = guards.check(action, now, state["clocked_in"], cfg)
        if reason:
            log.info("skip clock-%s: %s", action, reason)
            return
        for attempt in (1, 2):
            try:
                text = await paycor.punch(action, cfg)
                break
            except Exception as e:
                log.exception("punch attempt %d failed", attempt)
                if attempt == 2:
                    await notify(f"Clock-{action} FAILED", f"{e}. Punch manually in Paycor.", "high")
                    return
                await asyncio.sleep(30)
        state = {"clocked_in": action == "in", "last": now.isoformat()}
        save_state(state)
        await notify(f"Clocked {action} {now:%-I:%M %p}", f"✓ {text}")


async def watchdog() -> None:
    """Alert once per day if still clocked in after the clock-out window closes."""
    alerted_on = None
    while True:
        await asyncio.sleep(300)
        now = datetime.now(cfg.tz)
        if load_state()["clocked_in"] and now.time() > cfg.out_end and alerted_on != now.date():
            alerted_on = now.date()
            await notify("Still clocked in", "No clock-out recorded. Punch out manually.", "high")


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(watchdog())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


class Event(BaseModel):
    event: str


def _auth(authorization: str | None) -> None:
    expected = f"Bearer {cfg.api_token}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(401, "bad token")


def _schedule(action: str, delay: int) -> None:
    if action not in pending:
        pending[action] = asyncio.create_task(do_punch(action, delay))


def _cancel(action: str) -> bool:
    task = pending.pop(action, None)
    if task:
        task.cancel()
    return task is not None


@app.post("/event")
async def event(ev: Event, authorization: str | None = Header(None)):
    _auth(authorization)
    if ev.event == "arrive":
        cancelled = _cancel("out")
        _schedule("in", cfg.arrive_delay_s)
        return {"ok": True, "scheduled": "in", "cancelled_out": cancelled}
    if ev.event == "leave":
        cancelled = _cancel("in")
        _schedule("out", cfg.leave_delay_s)
        return {"ok": True, "scheduled": "out", "cancelled_in": cancelled}
    raise HTTPException(400, "event must be 'arrive' or 'leave'")


@app.post("/punch/{action}")
async def manual(action: str, authorization: str | None = Header(None)):
    """Immediate punch, still subject to guards. Useful for testing setup."""
    _auth(authorization)
    if action not in ("in", "out"):
        raise HTTPException(400, "action must be 'in' or 'out'")
    await do_punch(action, 0)
    return {"ok": True, "state": load_state()}


@app.get("/status")
async def status(authorization: str | None = Header(None)):
    _auth(authorization)
    return {"state": load_state(), "pending": sorted(pending)}

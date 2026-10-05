import asyncio

import pytest

import os
os.environ.setdefault("API_TOKEN", "t")


@pytest.fixture
def srv(tmp_path, monkeypatch):
    from autopunch import server
    from autopunch.config import Config
    cfg = Config(api_token="t", data_dir=tmp_path, arrive_delay_s=0, leave_delay_s=0)
    monkeypatch.setattr(server, "cfg", cfg)
    calls = []

    async def fake_punch(action, _cfg):
        calls.append(action)
        return f"Clocked {action}"
    monkeypatch.setattr(server.paycor, "punch", fake_punch)
    monkeypatch.setattr(server.guards, "check", lambda *a: None)
    server.pending.clear()
    return server, calls


def test_arrive_then_leave_quickly_cancels_clock_in(srv):
    server, calls = srv

    async def run():
        server._schedule("in", 60)
        assert server._cancel("in")
        await asyncio.sleep(0)
    asyncio.run(run())
    assert calls == []


def test_full_day(srv):
    server, calls = srv

    async def run():
        await server.do_punch("in", 0)
        assert server.load_state()["clocked_in"]
        await server.do_punch("out", 0)
        assert not server.load_state()["clocked_in"]
    asyncio.run(run())
    assert calls == ["in", "out"]


def test_auth_rejects_bad_token(srv):
    from fastapi.testclient import TestClient
    server, _ = srv
    with TestClient(server.app) as c:
        assert c.post("/event", json={"event": "arrive"}, headers={"Authorization": "Bearer nope"}).status_code == 401
        assert c.get("/status", headers={"Authorization": "Bearer t"}).status_code == 200


def test_bootstrap_session_installs_once_per_secret(srv, monkeypatch):
    import base64
    server, _ = srv
    monkeypatch.setenv("PAYCOR_SESSION_B64", base64.b64encode(b'{"cookies":[]}').decode())
    server.bootstrap_session()
    assert server.cfg.session_file.read_bytes() == b'{"cookies":[]}'
    server.cfg.session_file.write_bytes(b'{"refreshed":1}')  # a punch refreshed it
    server.bootstrap_session()
    assert server.cfg.session_file.read_bytes() == b'{"refreshed":1}'
    monkeypatch.setenv("PAYCOR_SESSION_B64", base64.b64encode(b'{"new":1}').decode())
    server.bootstrap_session()
    assert server.cfg.session_file.read_bytes() == b'{"new":1}'

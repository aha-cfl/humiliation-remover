"""Pure decision logic: should this punch be allowed right now? Kept I/O-free for testing."""
from datetime import datetime

from .config import Config


def check(action: str, now: datetime, clocked_in: bool, cfg: Config) -> str | None:
    """Return None if the punch is allowed, else a human-readable reason it was skipped."""
    if action not in ("in", "out"):
        return f"unknown action {action!r}"
    if now.weekday() not in cfg.workdays:
        return "not a workday"
    t = now.time()
    if action == "in":
        if clocked_in:
            return "already clocked in"
        if not cfg.in_start <= t <= cfg.in_end:
            return f"outside clock-in window {cfg.in_start:%H:%M}-{cfg.in_end:%H:%M}"
    else:
        if not clocked_in:
            return "not clocked in"
        if not cfg.out_start <= t <= cfg.out_end:
            return f"outside clock-out window {cfg.out_start:%H:%M}-{cfg.out_end:%H:%M}"
    return None

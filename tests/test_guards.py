import os
os.environ.setdefault("API_TOKEN", "t")

from datetime import datetime

import pytest

from autopunch import guards
from autopunch.config import Config

cfg = Config(api_token="x")
WED = datetime(2026, 9, 30)  # Wednesday
SAT = datetime(2026, 10, 3)


def at(day, hh, mm):
    return day.replace(hour=hh, minute=mm)


@pytest.mark.parametrize("now,clocked_in,action,ok", [
    (at(WED, 8, 35), False, "in", True),
    (at(WED, 8, 35), True, "in", False),    # double punch
    (at(WED, 7, 0), False, "in", False),    # too early
    (at(WED, 12, 15), True, "out", False),  # lunch exit ignored
    (at(WED, 18, 2), True, "out", True),
    (at(WED, 18, 2), False, "out", False),  # never clocked in
    (at(WED, 20, 0), True, "out", False),   # too late; watchdog alerts instead
    (at(SAT, 8, 35), False, "in", False),   # weekend
])
def test_check(now, clocked_in, action, ok):
    assert (guards.check(action, now, clocked_in, cfg) is None) is ok

"""All settings come from environment variables so nothing secret lives in the repo."""
import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo


def _hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


@dataclass(frozen=True)
class Config:
    api_token: str = field(default_factory=lambda: os.environ["API_TOKEN"])
    paycor_url: str = field(default_factory=lambda: os.getenv("PAYCOR_URL", "https://secure.paycor.com/"))
    paycor_user: str = field(default_factory=lambda: os.getenv("PAYCOR_USER", ""))
    paycor_pass: str = field(default_factory=lambda: os.getenv("PAYCOR_PASS", ""))
    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo(os.getenv("TZ_NAME", "America/New_York")))

    # Punches outside these windows are ignored (e.g. leaving for lunch never clocks you out).
    in_start: time = field(default_factory=lambda: _hm(os.getenv("IN_WINDOW_START", "07:45")))
    in_end: time = field(default_factory=lambda: _hm(os.getenv("IN_WINDOW_END", "10:00")))
    out_start: time = field(default_factory=lambda: _hm(os.getenv("OUT_WINDOW_START", "16:30")))
    out_end: time = field(default_factory=lambda: _hm(os.getenv("OUT_WINDOW_END", "19:30")))
    workdays: frozenset = field(default_factory=lambda: frozenset(
        int(d) for d in os.getenv("WORKDAYS", "0,1,2,3,4").split(",")))  # Mon=0

    # Must stay inside/outside the geofence this long before the punch fires.
    arrive_delay_s: int = field(default_factory=lambda: int(os.getenv("ARRIVE_DELAY_S", "180")))
    leave_delay_s: int = field(default_factory=lambda: int(os.getenv("LEAVE_DELAY_S", "300")))

    ntfy_topic: str = field(default_factory=lambda: os.getenv("NTFY_TOPIC", ""))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "data")))
    headless: bool = field(default_factory=lambda: os.getenv("HEADLESS", "1") == "1")

    # Optional CSS/text selector overrides if Paycor's UI doesn't match the defaults.
    sel_clock_in: str = field(default_factory=lambda: os.getenv("SEL_CLOCK_IN", ""))
    sel_clock_out: str = field(default_factory=lambda: os.getenv("SEL_CLOCK_OUT", ""))

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def session_file(self) -> Path:
        return self.data_dir / "paycor_session.json"

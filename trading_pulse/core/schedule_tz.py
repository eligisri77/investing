"""UTC schedule times → local display (Israel + US Eastern)."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

TIME_RE = re.compile(r"^\d{2}:\d{2}$")

UTC = ZoneInfo("UTC")
ISRAEL = ZoneInfo("Asia/Jerusalem")
US_EASTERN = ZoneInfo("America/New_York")


def utc_hhmm_to_zone(hhmm: str, tz: ZoneInfo, *, on_day: date | None = None) -> str:
    if not hhmm or not TIME_RE.fullmatch(hhmm.strip()):
        return ""
    hour, minute = (int(x) for x in hhmm.strip().split(":"))
    base = on_day or date.today()
    dt_utc = datetime.combine(base, time(hour, minute), tzinfo=UTC)
    return dt_utc.astimezone(tz).strftime("%H:%M")


def format_dual_time(hhmm: str, *, on_day: date | None = None) -> str:
    """e.g. 13:35 UTC · 16:35 ישראל"""
    if not hhmm or not TIME_RE.fullmatch(str(hhmm).strip()):
        return ""
    utc = str(hhmm).strip()
    il = utc_hhmm_to_zone(utc, ISRAEL, on_day=on_day)
    return f"{utc} UTC · {il} ישראל"


def format_triple_time(hhmm: str, *, on_day: date | None = None) -> str:
    """UTC · Israel · US Eastern — for settings hints."""
    if not hhmm or not TIME_RE.fullmatch(str(hhmm).strip()):
        return ""
    utc = str(hhmm).strip()
    il = utc_hhmm_to_zone(utc, ISRAEL, on_day=on_day)
    et = utc_hhmm_to_zone(utc, US_EASTERN, on_day=on_day)
    return f"{utc} UTC · {il} ישראל · {et} ET"


def format_local_entry_moment(iso_ts: str | None) -> str:
    """Israel local date+time for when a simulated buy was recorded."""
    if not iso_ts:
        return "—"
    try:
        raw = str(iso_ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(ISRAEL).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return "—"


SCHEDULE_TIME_KEYS = (
    "planning_time",
    "entry_sim_time",
    "market_open_sim_time",
    "market_close_sim_time",
    "heartbeat_time",
    "plan_reminder_time",
)


def dual_times_from_config(cfg: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in SCHEDULE_TIME_KEYS:
        raw = cfg.get(key)
        if raw:
            out[key] = format_dual_time(str(raw))
    return out

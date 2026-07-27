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
    """e.g. ‎16:35‎ ישראל (‎13:35‎ UTC) — Israel first, LRM keeps times LTR."""
    if not hhmm or not TIME_RE.fullmatch(str(hhmm).strip()):
        return ""
    utc = str(hhmm).strip()
    il = utc_hhmm_to_zone(utc, ISRAEL, on_day=on_day)
    lrm = "\u200e"
    return f"{lrm}{il}{lrm} ישראל ({lrm}{utc}{lrm} UTC)"


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


SCHEDULE_TZ = "UTC"

SCHEDULE_TIME_KEYS = (
    "planning_time",
    "entry_sim_time",
    "market_open_sim_time",
    "market_close_sim_time",
    "heartbeat_time",
    "plan_reminder_time",
    "weekly_scan_time",
)


def us_trading_session_date(*, now: datetime | None = None) -> date:
    """US equity session calendar date (America/New_York), not the PC's local date."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(US_EASTERN).date()


def minutes_until_utc_hhmm(hhmm: str, *, now: datetime | None = None) -> int:
    """Minutes until HH:MM UTC today (0 if already past). Config times are UTC."""
    if not hhmm or not TIME_RE.fullmatch(str(hhmm).strip()):
        return 0
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    hour, minute = (int(x) for x in str(hhmm).strip().split(":", 1))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        return 0
    return max(0, int((target - now).total_seconds() // 60))


def schedule_daily_at(hhmm: str):
    """Register a daily job at HH:MM interpreted as UTC (config convention)."""
    import schedule

    return schedule.every().day.at(str(hhmm).strip(), SCHEDULE_TZ)


def schedule_weekday_at(day: str, hhmm: str):
    """Register a weekly job on a named weekday at HH:MM UTC."""
    import schedule

    day = str(day).strip().lower()
    job = getattr(schedule.every(), day, None)
    if job is None:
        return None
    return job.at(str(hhmm).strip(), SCHEDULE_TZ)


def dual_times_from_config(cfg: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in SCHEDULE_TIME_KEYS:
        raw = cfg.get(key)
        if raw:
            out[key] = format_dual_time(str(raw))
    return out

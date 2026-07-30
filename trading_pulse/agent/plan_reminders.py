"""Legacy pre-simulation reminders (disabled).

Historically reminded users to approve before EOD fills. Approvals now happen
the evening before, with fills at next open — so this reminder no longer runs.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Literal

ReminderKind = Literal["approval", "allocation"]


def minutes_until_local_time(hhmm: str, *, now: datetime | None = None) -> int:
    """Deprecated alias — config times are UTC; prefer minutes_until_utc_hhmm."""
    from trading_pulse.core.schedule_tz import minutes_until_utc_hhmm

    return minutes_until_utc_hhmm(hhmm, now=now)


def plan_reminder_kind(plan: dict[str, Any]) -> ReminderKind | None:
    """Legacy classifier — unused while send_pre_simulation_reminder is a no-op."""
    recs = plan.get("recommendations", [])
    if not recs:
        return None
    approved_n = sum(1 for r in recs if r.get("approved"))
    if approved_n == 0 or any(not r.get("approved") for r in recs):
        return "approval"
    alloc = plan.get("allocation") or {}
    if alloc.get("status") != "applied":
        return "allocation"
    return None


def send_pre_simulation_reminder(cfg: Any, trading_day: date) -> bool:
    """Disabled — leftover from old EOD-fill flow.

    Always returns False so old callers/config keys do not crash.
    """
    del cfg  # unused
    logging.debug(
        "Pre-simulation reminder disabled (skipped for %s)",
        trading_day.isoformat(),
    )
    return False

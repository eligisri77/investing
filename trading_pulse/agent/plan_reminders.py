"""Pre-simulation reminders when approval or allocation is still pending."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Literal

ReminderKind = Literal["approval", "allocation"]


def minutes_until_local_time(hhmm: str, *, now: datetime | None = None) -> int:
    """Deprecated alias — config times are UTC; prefer minutes_until_utc_hhmm."""
    from trading_pulse.core.schedule_tz import minutes_until_utc_hhmm

    return minutes_until_utc_hhmm(hhmm, now=now)


def plan_reminder_kind(plan: dict[str, Any]) -> ReminderKind | None:
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
    """Send one reminder per plan if approval/allocation still pending. Returns True if sent."""
    from trading_pulse.agent.dryrun_agent import plan_path, read_json, report_path, save_json, should_run_simulation_today
    from trading_pulse.core.schedule_tz import minutes_until_utc_hhmm
    from trading_pulse.telegram.telegram_format import format_pre_sim_reminder

    if not should_run_simulation_today(trading_day):
        return False
    if report_path(trading_day).exists():
        return False

    path = plan_path(trading_day)
    if not path.exists():
        return False

    plan = read_json(path)
    if plan.get("pre_sim_reminder_sent_at"):
        return False

    kind = plan_reminder_kind(plan)
    if kind is None:
        return False

    minutes = minutes_until_utc_hhmm(str(cfg.market_close_sim_time))
    text = format_pre_sim_reminder(minutes, kind)
    from trading_pulse.telegram.app_notify import notify_user
    from trading_pulse.agent.dryrun_agent import send_telegram_message

    sent = notify_user(
        cfg,
        text,
        "reminder:pre_sim",
        parse_mode="HTML",
        telegram_sender=send_telegram_message,
    )
    if not sent:
        return False

    plan["pre_sim_reminder_sent_at"] = datetime.now(timezone.utc).isoformat()
    save_json(path, plan)
    logging.info(
        "Pre-simulation reminder sent for %s (%s, %d min to sim)",
        trading_day.isoformat(),
        kind,
        minutes,
    )
    return True

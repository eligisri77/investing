"""Tests for pre-simulation reminders (UTC countdown)."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_pulse.agent.plan_reminders import minutes_until_local_time, plan_reminder_kind
from trading_pulse.core.schedule_tz import minutes_until_utc_hhmm


def test_minutes_until_utc_at_reminder_time():
    # plan_reminder_time 20:00 UTC → market_close 20:20 UTC = 20 minutes
    now = datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc)
    assert minutes_until_utc_hhmm("20:20", now=now) == 20
    # Deprecated alias must match (was buggy with local Israel clock)
    assert minutes_until_local_time("20:20", now=now) == 20


def test_plan_reminder_kind_approval():
    plan = {"recommendations": [{"approved": False}, {"approved": True}], "allocation": {}}
    assert plan_reminder_kind(plan) == "approval"


def test_plan_reminder_kind_ready():
    plan = {
        "recommendations": [{"approved": True}],
        "allocation": {"status": "applied"},
    }
    assert plan_reminder_kind(plan) is None


def test_parse_indices_all_skips_below_bar():
    from trading_pulse.agent.dryrun_agent import parse_indices

    recs = [
        {"symbol": "META", "below_bar": False},
        {"symbol": "NVDL", "below_bar": True},
    ]
    assert parse_indices("ALL", total=2, recs=recs) == [0]
    assert parse_indices("ALL", total=2, recs=recs, include_below_bar=True) == [0, 1]
    assert parse_indices("1,2", total=2, recs=recs) == [0, 1]


def test_format_below_bar_approve_hint():
    from trading_pulse.telegram.telegram_format import format_below_bar_approve_hint

    recs = [{"symbol": "NVDL", "score": 5.8, "below_bar": True}]
    text = format_below_bar_approve_hint(recs, plan_recs=recs)
    assert "הכל" in text
    assert "לא מאשר" in text
    assert "NVDL" in text
    assert "<code>1</code>" in text

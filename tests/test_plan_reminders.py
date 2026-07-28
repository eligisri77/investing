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


def test_format_nothing_to_approve_no_manual_actions():
    from trading_pulse.telegram.telegram_format import format_nothing_to_approve

    text = format_nothing_to_approve({"recommendations": [], "holding_actions": []})
    assert "אין קניות ממזומן לאשר" in text
    assert "<code>הכל</code>" in text
    assert "לא מכירות ולא החלפות" in text
    assert "אין גם פעולה ידנית" in text
    assert "תיק" in text
    assert "לא מצאתי מספרים תקינים" not in text


def test_format_nothing_to_approve_lists_manual_sell_and_swap():
    from trading_pulse.telegram.telegram_format import format_nothing_to_approve

    plan = {
        "recommendations": [],
        "holding_actions": [
            {"symbol": "LABD", "verdict": "hold"},
            {"symbol": "PATH", "verdict": "sell"},
            {"symbol": "RIVN", "verdict": "swap", "swap_to": "NVDA"},
            {"symbol": "BEAM", "verdict": "take_profit"},
        ],
    }
    text = format_nothing_to_approve(plan)
    assert "אין קניות ממזומן לאשר" in text
    assert "אם רוצה לפעול ידנית" in text
    assert "<code>מכור PATH</code>" in text
    assert "<code>החלף RIVN NVDA</code>" in text
    assert "<code>מכור BEAM</code>" in text
    assert "אין גם פעולה ידנית" not in text
    assert "LABD" not in text  # hold is not a manual tip


def test_format_nothing_to_approve_none_plan():
    from trading_pulse.telegram.telegram_format import format_nothing_to_approve

    text = format_nothing_to_approve(None)
    assert "אין קניות ממזומן לאשר" in text
    assert "אין גם פעולה ידנית" in text


def test_parse_indices_all_empty_or_only_below_bar():
    """«הכל» with nothing approveable → empty indices (formatter path, not invalid)."""
    from trading_pulse.agent.dryrun_agent import parse_indices

    assert parse_indices("ALL", total=0, recs=[]) == []
    only_weak = [
        {"symbol": "NVDL", "below_bar": True},
        {"symbol": "SOXL", "below_bar": True},
    ]
    assert parse_indices("ALL", total=2, recs=only_weak) == []


def test_approve_all_empty_indices_reply_branch():
    """Mirror dryrun approve branch: ALL + no indices → nothing_to_approve vs below_bar hint."""
    from trading_pulse.telegram.telegram_format import (
        format_below_bar_approve_hint,
        format_nothing_to_approve,
        user_guide_invalid_approve,
    )

    def reply_for(*, raw_idx: str, kind: str, recs: list, plan: dict) -> str:
        indices: list[int] = []  # empty after parse / filter
        if not indices:
            weak = [r for r in recs if r.get("below_bar")]
            if raw_idx.upper() == "ALL" and kind == "approve":
                if weak:
                    return format_below_bar_approve_hint(weak, plan_recs=recs)
                return format_nothing_to_approve(plan)
            return user_guide_invalid_approve()
        raise AssertionError("expected empty indices")

    empty_plan = {"recommendations": [], "holding_actions": [{"symbol": "PATH", "verdict": "sell"}]}
    text = reply_for(raw_idx="ALL", kind="approve", recs=[], plan=empty_plan)
    assert "אין קניות ממזומן לאשר" in text
    assert "<code>מכור PATH</code>" in text
    assert "לא מצאתי מספרים תקינים" not in text

    weak_recs = [{"symbol": "NVDL", "score": 5.8, "below_bar": True}]
    hint = reply_for(raw_idx="ALL", kind="approve", recs=weak_recs, plan={"recommendations": weak_recs})
    assert "לא מאשר" in hint
    assert "NVDL" in hint

    bad = reply_for(raw_idx="9", kind="approve", recs=[], plan=empty_plan)
    assert "לא מצאתי מספרים תקינים" in bad

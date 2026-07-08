"""Broker-style plan lifecycle tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from trading_pulse.agent.dryrun_agent import AgentConfig, save_json
from trading_pulse.agent.plan_engine import (
    STATUS_CONFIRMED,
    STATUS_DRAFT,
    apply_confirm,
    is_locked,
    normalize_status,
    pending_buy_symbols,
    plan_is_protected,
    supersede_other_plans,
)


def test_normalize_legacy_approved_to_confirmed():
    plan = {
        "status": "approved",
        "recommendations": [{"symbol": "LABU", "approved": True}],
        "allocation": {"status": "applied"},
    }
    assert normalize_status(plan) == STATUS_CONFIRMED


def test_not_locked_when_already_holding_all_picks():
    plan = {
        "for_trading_day": "2026-07-06",
        "status": STATUS_CONFIRMED,
        "recommendations": [
            {"symbol": "SOXL", "approved": True, "capital_usd": 333},
            {"symbol": "MSTR", "approved": True, "capital_usd": 333},
        ],
        "allocation": {"status": "applied"},
    }
    state = {
        "equity": 997,
        "open_positions": [
            {"symbol": "SOXL", "capital_usd": 333},
            {"symbol": "MSTR", "capital_usd": 333},
        ],
    }
    cfg = AgentConfig()
    assert pending_buy_symbols(plan, state) == []
    assert is_locked(plan, state, cfg, as_of=date(2026, 7, 5)) is False
    assert plan_is_protected(plan, state=state, as_of=date(2026, 7, 5)) is False


def test_locked_when_confirmed_and_pending_before_open():
    plan = {
        "for_trading_day": "2026-07-07",
        "status": STATUS_CONFIRMED,
        "recommendations": [{"symbol": "LABU", "approved": True, "capital_usd": 500}],
        "allocation": {"status": "applied"},
    }
    state = {"equity": 1000, "open_positions": []}
    cfg = AgentConfig(entry_sim_time="13:35")
    with patch("trading_pulse.agent.trading_flow.before_market_entry", return_value=True):
        assert is_locked(plan, state, cfg, as_of=date(2026, 7, 6)) is True


def test_apply_confirm_sets_status_and_allocation():
    plan = {
        "for_trading_day": "2026-07-07",
        "status": STATUS_DRAFT,
        "available_capital_usd": 1000,
        "recommendations": [
            {"symbol": "A", "capital_usd": 500},
            {"symbol": "B", "capital_usd": 500},
        ],
    }
    state = {"equity": 1000, "open_positions": []}
    cfg = AgentConfig()
    out = apply_confirm(plan, state, cfg)
    assert normalize_status(out) == STATUS_CONFIRMED
    assert out["allocation"]["status"] == "applied"
    assert all(r["approved"] for r in out["recommendations"])


def test_supersede_other_plans(tmp_path, monkeypatch):
    from trading_pulse.core.app_paths import PLANS_DIR

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.PLANS_DIR", plans_dir)

    save_json(
        plans_dir / "plan_2099-01-04.json",
        {"for_trading_day": "2099-01-04", "status": STATUS_CONFIRMED, "recommendations": []},
    )
    supersede_other_plans(date(2099, 1, 5))
    old = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plans_dir / "plan_2099-01-04.json"
    )
    assert old["status"] == "superseded"


def test_cancel_plan_marks_superseded(tmp_path, monkeypatch):
    from trading_pulse.agent.plan_engine import STATUS_SUPERSEDED, cancel_plan

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.PLANS_DIR", plans_dir)

    save_json(
        plans_dir / "plan_2099-01-05.json",
        {
            "for_trading_day": "2099-01-05",
            "status": STATUS_DRAFT,
            "recommendations": [{"symbol": "MSTX"}, {"symbol": "RIVN"}],
        },
    )
    result = cancel_plan(as_of=date(2099, 1, 4))
    assert result["ok"] is True
    assert result["day"] == "2099-01-05"
    assert set(result["symbols"]) == {"MSTX", "RIVN"}

    reread = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plans_dir / "plan_2099-01-05.json"
    )
    assert reread["status"] == STATUS_SUPERSEDED
    assert "cancelled_at" in reread


def test_cancel_plan_no_active_returns_reason(tmp_path, monkeypatch):
    from trading_pulse.agent.plan_engine import cancel_plan

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.PLANS_DIR", plans_dir)

    result = cancel_plan(as_of=date(2099, 1, 4))
    assert result["ok"] is False
    assert result["reason"] == "no_active_plan"

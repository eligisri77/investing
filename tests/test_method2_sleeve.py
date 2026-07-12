"""Tests for שיטה 2 sleeve allocation and confirm watch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from trading_pulse.agent.capital_allocation import _sleeve_aware_equal_amounts
from trading_pulse.agent.plan_engine import apply_confirm


def test_sleeve_aware_equal_keeps_method2_capital():
    recs = [
        {"symbol": "AAA", "strategy": "score", "capital_usd": 250},
        {"symbol": "BBB", "strategy": "score", "capital_usd": 250},
        {"symbol": "CCC", "strategy": "rising_three_methods", "capital_usd": 250},
        {"symbol": "DDD", "strategy": "method2", "capital_usd": 150, "sleeve": True},
    ]
    amounts = _sleeve_aware_equal_amounts(recs, 1000.0)
    assert amounts[3] == 150.0
    assert abs(sum(amounts[:3]) - 850.0) < 0.01
    assert abs(amounts[0] - amounts[1]) < 0.01


def test_apply_confirm_adds_method2_watch():
    cfg = SimpleNamespace(initial_capital=1000.0)
    state: dict = {"equity": 1000.0, "open_positions": []}
    plan = {
        "recommendations": [
            {"symbol": "AAA", "strategy": "score", "capital_usd": 400, "approved": False},
            {
                "symbol": "M2CO",
                "strategy": "method2",
                "capital_usd": 100,
                "sleeve": True,
                "trigger": "2-1-2",
                "approved": False,
            },
        ],
        "available_capital_usd": 1000.0,
        "equity_snapshot": 1000.0,
        "holdings": [],
    }
    with (
        patch("trading_pulse.agent.plan_engine.sync_plan_portfolio_snapshot"),
        patch("trading_pulse.agent.trading_flow.funding_gap", return_value=None),
        patch("trading_pulse.agent.trading_flow.auto_allocate_equal", return_value={"ok": True}),
        patch("trading_pulse.agent.dryrun_agent.save_json"),
    ):
        apply_confirm(plan, state, cfg)
    watches = state.get("price_watches") or {}
    assert "M2CO" in watches
    assert watches["M2CO"].get("label") == "שיטה 2"

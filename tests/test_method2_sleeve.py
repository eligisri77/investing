"""Tests for שיטה 2 sleeve allocation and confirm watch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

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


def test_sleeve_aware_equal_keeps_multiple_method2_offers():
    recs = [
        {"symbol": "AAA", "strategy": "score", "capital_usd": 400},
        {"symbol": "M2A", "strategy": "method2", "capital_usd": 120, "sleeve": True},
        {"symbol": "M2B", "strategy": "method2", "capital_usd": 80, "sleeve": True},
        {"symbol": "M2C", "strategy": "method2", "capital_usd": 100, "sleeve": True},
    ]
    amounts = _sleeve_aware_equal_amounts(recs, 1000.0)
    assert amounts[1:] == [120.0, 80.0, 100.0]
    assert abs(amounts[0] - 700.0) < 0.01


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
    assert watches["M2CO"].get("label") == "נרות סיניים 2"


def test_sync_plan_portfolio_preserves_method2_sleeve_capital():
    """Mains split remaining cash; Method2 capital is not flattened."""
    from trading_pulse.agent.plan_engine import sync_plan_portfolio_snapshot

    cfg = SimpleNamespace(initial_capital=1000.0)
    state = {"equity": 1000.0, "open_positions": []}
    plan = {
        "recommendations": [
            {"symbol": "AAA", "strategy": "score", "capital_usd": 333},
            {"symbol": "BBB", "strategy": "score", "capital_usd": 333},
            {
                "symbol": "M2CO",
                "strategy": "method2",
                "capital_usd": 150,
                "sleeve": True,
            },
        ],
        "available_capital_usd": 0,
        "holdings": [],
    }
    out = sync_plan_portfolio_snapshot(plan, state, cfg)
    by_sym = {r["symbol"]: float(r["capital_usd"]) for r in out["recommendations"]}
    assert by_sym["M2CO"] == 150.0
    assert abs(by_sym["AAA"] - by_sym["BBB"]) < 0.02
    assert abs(by_sym["AAA"] + by_sym["BBB"] - 850.0) < 0.05
    # Not a flat equal overwrite of all three (~333 each)
    assert by_sym["AAA"] != pytest.approx(333.0, abs=1)

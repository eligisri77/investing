"""Tests for floor price (hard sell threshold)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trading_pulse.agent.intraday_monitor import analyze_position
from trading_pulse.agent.positions import (
    close_position_at_price,
    floor_closed_today,
    holdings_snapshot,
    new_position_from_rec,
    partial_sell_position,
    position_floor_price,
    rec_floor_price,
    trade_from_close,
)


@dataclass
class FakeCfg:
    stop_loss_pct: float = 0.12
    take_profit_pct: float = 0.25
    commission_per_side_usd: float = 0.0


def test_rec_floor_price_from_entry():
    rec = {"symbol": "SOXL", "stop_loss_pct": 0.12}
    assert rec_floor_price(rec, 100.0) == 88.0


def test_new_position_stores_floor():
    rec = {"symbol": "LABU", "capital_usd": 250, "stop_loss_pct": 0.12, "floor_price": 44.0}
    pos = new_position_from_rec(rec, 50.0, "2026-06-30")
    assert pos["floor_price"] == 44.0


def test_new_position_preserves_strategy_attribution():
    rec = {
        "symbol": "NVDA",
        "capital_usd": 250,
        "stop_loss_pct": 0.08,
        "strategy": "rising_three_methods",
        "strategy_id": "rising_three",
        "strategy_version": "1.0",
        "schema_version": 2,
        "signal_id": "signal-123",
        "native_score": 8.25,
        "confidence": 0.82,
        "entry_policy": "market_open",
        "contributing_strategies": ["score_momentum", "rising_three"],
    }

    pos = new_position_from_rec(rec, 100.0, "2026-07-20")

    assert pos["strategy_id"] == "rising_three"
    assert pos["strategy_version"] == "1.0"
    assert pos["schema_version"] == 2
    assert pos["signal_id"] == "signal-123"
    assert pos["native_score"] == 8.25
    assert pos["confidence"] == 0.82
    assert pos["entry_policy"] == "market_open"
    assert pos["contributing_strategies"] == [
        "score_momentum",
        "rising_three",
    ]


def test_new_position_owns_contributor_list_copy():
    contributors = ["score_momentum"]
    rec = {
        "symbol": "AMD",
        "capital_usd": 100,
        "contributing_strategies": contributors,
    }
    pos = new_position_from_rec(rec, 50.0, "2026-07-20")

    contributors.append("method2")

    assert pos["contributing_strategies"] == ["score_momentum"]


def test_position_attribution_survives_snapshots_and_close():
    rec = {
        "symbol": "AMD",
        "capital_usd": 100,
        "stop_loss_pct": 0.08,
        "strategy": "rising_three_methods",
        "strategy_id": "rising_three",
        "strategy_version": "1.0",
        "contributing_strategies": ["score_momentum", "rising_three"],
    }
    pos = new_position_from_rec(rec, 50.0, "2026-07-20")

    snapshot = holdings_snapshot({"open_positions": [pos]})[0]
    trade = trade_from_close(pos, 55.0, "take_profit")

    assert snapshot["strategy_id"] == "rising_three"
    assert snapshot["contributing_strategies"] == [
        "score_momentum",
        "rising_three",
    ]
    assert trade["strategy_id"] == "rising_three"
    assert trade["strategy_version"] == "1.0"
    assert trade["contributing_strategies"] == [
        "score_momentum",
        "rising_three",
    ]


def test_analyze_floor_breach_triggers_sell_alert():
    cfg = FakeCfg()
    pos = {"symbol": "AMD", "entry_price": 100.0, "floor_price": 88.0, "stop_loss_pct": 0.12}
    quote = {"last": 87.5, "open": 90.0, "change_pct": -2.0}
    alerts = analyze_position(pos, quote, cfg)
    assert len(alerts) == 1
    assert alerts[0].kind == "floor_breach"


def test_close_position_at_floor_updates_state():
    cfg = FakeCfg()
    state = {"equity": 1000.0, "open_positions": [{"symbol": "IONQ", "entry_price": 40.0, "capital_usd": 200, "floor_price": 35.2, "days_held": 1}]}
    pos = state["open_positions"][0]
    trade = close_position_at_price(cfg, state, pos, 35.0, "floor_price", trading_day="2026-06-30")
    assert trade["symbol"] == "IONQ"
    assert state["open_positions"] == []
    assert state["equity"] < 1000.0
    assert floor_closed_today(state, "IONQ", "2026-06-30")


def test_partial_sells_persist_unique_booked_exits_without_reapplying_equity(
    monkeypatch,
):
    cfg = FakeCfg()
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "U",
                "entry_price": 100.0,
                "capital_usd": 200.0,
                "entry_day": "2026-07-15",
                "days_held": 2,
            }
        ],
    }
    monkeypatch.setattr(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        lambda *_args: {"close": 110.0},
    )

    first = partial_sell_position(
        cfg, state, "U", 0.25, trading_day=date(2026, 7, 17)
    )
    second = partial_sell_position(
        cfg, state, "U", 0.25, trading_day=date(2026, 7, 17)
    )

    assert first is not None and second is not None
    assert first["exit_id"].startswith("manual:")
    assert second["exit_id"].startswith("manual:")
    assert first["exit_id"] != second["exit_id"]
    assert first["trading_day"] == second["trading_day"] == "2026-07-17"
    assert first["closed_at"].endswith("+00:00")
    assert first["manual_exit"] is second["manual_exit"] is True
    assert state["intraday_floor_exits"] == [first, second]
    booked_pnl = sum(row["pnl_usd"] for row in state["intraday_floor_exits"])
    assert state["equity"] == 1000.0 + booked_pnl
    assert state["open_positions"][0]["capital_usd"] == 112.5

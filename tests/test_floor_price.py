"""Tests for floor price (hard sell threshold)."""

from __future__ import annotations

from dataclasses import dataclass

from trading_pulse.agent.intraday_monitor import analyze_position
from trading_pulse.agent.positions import (
    close_position_at_price,
    floor_closed_today,
    new_position_from_rec,
    position_floor_price,
    rec_floor_price,
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

"""Cash guardrails: never open buys that exceed free (unreserved) cash.

Swaps remain allowed — selling frees cash, then buying spends it.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from trading_pulse.agent.positions import (
    cash_free_among_positions,
    clamp_buy_capital,
    free_cash,
    simulate_swing_day,
    unreserved_free_cash,
)


def test_clamp_buy_capital_never_exceeds_cash():
    assert clamp_buy_capital(500, 120) == 120.0
    assert clamp_buy_capital(50, 120) == 50.0
    assert clamp_buy_capital(100, 0) == 0.0


def test_cash_free_among_positions_basic():
    assert cash_free_among_positions(1000.0, []) == 1000.0
    assert cash_free_among_positions(1000.0, [{"capital_usd": 400}]) == 600.0
    assert cash_free_among_positions(500.0, [{"capital_usd": 700}]) == 0.0


def test_unreserved_free_cash_subtracts_other_approvals():
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "META",
                "capital_usd": 400.0,
                "entry_price": 100.0,
                "entry_day": "2026-08-01",
                "lots": [
                    {
                        "id": "a",
                        "capital_usd": 400.0,
                        "entry_price": 100.0,
                        "entry_day": "2026-08-01",
                    }
                ],
            }
        ],
    }
    plan = {
        "recommendations": [
            {"symbol": "TSLL", "approved": True, "capital_usd": 300.0},
            {"symbol": "ANET", "approved": True, "capital_usd": 500.0},
        ]
    }
    # Free = 600; reserved by TSLL+ANET = 800 → unreserved 0
    assert free_cash(state) == 600.0
    assert unreserved_free_cash(state, plan) == 0.0
    # Approving ANET itself should ignore its own reservation
    assert unreserved_free_cash(state, plan, exclude_symbol="ANET") == 300.0


def test_unreserved_free_cash_ignores_held_and_terminal_method2():
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "META",
                "capital_usd": 200.0,
                "entry_price": 100.0,
                "entry_day": "2026-08-01",
                "lots": [
                    {
                        "id": "a",
                        "capital_usd": 200.0,
                        "entry_price": 100.0,
                        "entry_day": "2026-08-01",
                    }
                ],
            }
        ],
    }
    plan = {
        "recommendations": [
            # Already held — must not reserve again.
            {"symbol": "META", "approved": True, "capital_usd": 200.0},
            {"symbol": "TSLL", "approved": True, "capital_usd": 300.0, "method2_status": "filled"},
            {
                "symbol": "ANET",
                "approved": True,
                "capital_usd": 250.0,
                "method2_status": "invalidated",
            },
            {"symbol": "AMD", "approved": True, "capital_usd": 150.0, "method2_status": "expired"},
            # Still pending breakout — does reserve.
            {
                "symbol": "SOXL",
                "approved": True,
                "capital_usd": 100.0,
                "method2_status": "pending_breakout",
            },
        ]
    }
    # Free = 800; only SOXL reserves → unreserved 700
    assert free_cash(state) == 800.0
    assert unreserved_free_cash(state, plan) == 700.0
    assert unreserved_free_cash(state, None) == 800.0


def test_simulate_swing_day_skips_entry_without_free_cash(monkeypatch):
    cfg = SimpleNamespace(
        commission_per_side_usd=0.0,
        max_open_positions=4,
        max_daily_loss_pct=1.0,
        hold_mode="swing",
        stop_loss_pct=0.12,
        take_profit_pct=0.25,
    )
    state = {
        "equity": 950.0,
        "open_positions": [
            {
                "symbol": "TSLL",
                "capital_usd": 950.0,
                "entry_price": 8.0,
                "entry_day": "2026-08-05",
                "stop_loss_pct": 0.12,
                "take_profit_pct": 0.25,
                "floor_price": 7.0,
                "lots": [
                    {
                        "id": "t",
                        "capital_usd": 950.0,
                        "entry_price": 8.0,
                        "entry_day": "2026-08-05",
                    }
                ],
            }
        ],
    }
    approved = [
        {
            "symbol": "ANET",
            "approved": True,
            "capital_usd": 950.0,
            "entry_ref_price": 194.0,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
            "floor_price": 180.0,
        }
    ]

    monkeypatch.setattr(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        lambda _sym, _day: {"open": 194.0, "high": 200.0, "low": 190.0, "close": 198.0},
    )

    _executed, still_open, _pnl, _fees = simulate_swing_day(
        cfg, state, date(2026, 8, 5), approved, entries_only=True
    )
    syms = {p["symbol"] for p in still_open}
    assert syms == {"TSLL"}
    assert free_cash(state) == 0.0
    assert sum(float(p["capital_usd"]) for p in still_open) == 950.0


def test_simulate_swing_day_clamps_second_buy_to_remaining_cash(monkeypatch):
    cfg = SimpleNamespace(
        commission_per_side_usd=0.0,
        max_open_positions=4,
        max_daily_loss_pct=1.0,
        hold_mode="swing",
        stop_loss_pct=0.12,
        take_profit_pct=0.25,
    )
    state = {"equity": 1000.0, "open_positions": []}
    approved = [
        {
            "symbol": "AAA",
            "approved": True,
            "capital_usd": 700.0,
            "entry_ref_price": 10.0,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
            "floor_price": 5.0,
        },
        {
            "symbol": "BBB",
            "approved": True,
            "capital_usd": 700.0,
            "entry_ref_price": 20.0,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
            "floor_price": 10.0,
        },
    ]

    def _bar(sym, _day):
        if sym == "AAA":
            return {"open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5}
        return {"open": 20.0, "high": 21.0, "low": 19.5, "close": 20.5}

    monkeypatch.setattr("trading_pulse.agent.positions.fetch_day_ohlc", _bar)
    _executed, still_open, _pnl, _fees = simulate_swing_day(
        cfg, state, date(2026, 8, 5), approved, entries_only=True
    )
    by_sym = {p["symbol"]: float(p["capital_usd"]) for p in still_open}
    assert set(by_sym) == {"AAA", "BBB"}
    assert by_sym["AAA"] == 700.0
    assert by_sym["BBB"] == 300.0
    assert sum(by_sym.values()) == 1000.0
    assert free_cash(state) == 0.0


def test_method2_fill_skips_without_free_cash(monkeypatch):
    from trading_pulse.agent.method2_intraday import try_fill_pending_method2

    cfg = SimpleNamespace(
        method2_enabled=True,
        method2_intraday_enabled=True,
        method2_intraday_intervals=["5m"],
        max_open_positions=5,
        commission_per_side_usd=0.0,
        stop_loss_pct=0.12,
        take_profit_pct=0.25,
    )
    state = {
        "equity": 950.0,
        "open_positions": [
            {
                "symbol": "META",
                "capital_usd": 950.0,
                "entry_price": 100.0,
                "entry_day": "2026-08-05",
                "lots": [
                    {
                        "id": "m",
                        "capital_usd": 950.0,
                        "entry_price": 100.0,
                        "entry_day": "2026-08-05",
                    }
                ],
            }
        ],
    }
    plan = {
        "recommendations": [
            {
                "symbol": "AAA",
                "strategy": "method2",
                "sleeve": True,
                "approved": True,
                "side": "LONG",
                "capital_usd": 200.0,
                "method2_entry_ref": 50.0,
                "method2_stop_ref": 48.0,
                "floor_price": 48.0,
                "method2_status": "pending_breakout",
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.25,
            }
        ]
    }
    called = {"n": 0}

    def _eval(*_a, **_k):
        called["n"] += 1
        return {"fill_price": 50.0, "reason": "daily_level_break", "interval": "5m"}

    monkeypatch.setattr(
        "trading_pulse.agent.method2_intraday.evaluate_method2_intraday_entry",
        _eval,
    )
    filled = try_fill_pending_method2(cfg, state, plan, date(2026, 8, 5))
    assert filled == []
    assert called["n"] == 0  # cash check runs before candle eval
    assert plan["recommendations"][0]["method2_status"] == "pending_breakout"
    assert {p["symbol"] for p in state["open_positions"]} == {"META"}


def test_method2_fill_clamps_capital_to_free_cash(monkeypatch):
    from trading_pulse.agent.method2_intraday import try_fill_pending_method2

    cfg = SimpleNamespace(
        method2_enabled=True,
        method2_intraday_enabled=True,
        method2_intraday_intervals=["5m"],
        max_open_positions=5,
        commission_per_side_usd=0.0,
        stop_loss_pct=0.12,
        take_profit_pct=0.25,
    )
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "META",
                "capital_usd": 700.0,
                "entry_price": 100.0,
                "entry_day": "2026-08-05",
                "lots": [
                    {
                        "id": "m",
                        "capital_usd": 700.0,
                        "entry_price": 100.0,
                        "entry_day": "2026-08-05",
                    }
                ],
            }
        ],
    }
    plan = {
        "recommendations": [
            {
                "symbol": "AAA",
                "strategy": "method2",
                "sleeve": True,
                "approved": True,
                "side": "LONG",
                "capital_usd": 500.0,
                "method2_entry_ref": 50.0,
                "method2_stop_ref": 48.0,
                "floor_price": 48.0,
                "method2_status": "pending_breakout",
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.25,
            }
        ]
    }
    monkeypatch.setattr(
        "trading_pulse.agent.method2_intraday.evaluate_method2_intraday_entry",
        lambda *_a, **_k: {
            "fill_price": 50.0,
            "reason": "daily_level_break",
            "interval": "5m",
        },
    )
    filled = try_fill_pending_method2(cfg, state, plan, date(2026, 8, 5))
    assert len(filled) == 1
    assert filled[0]["capital_usd"] == 300.0
    assert plan["recommendations"][0]["capital_usd"] == 300.0
    assert plan["recommendations"][0]["method2_status"] == "filled"
    assert free_cash(state) == 0.0

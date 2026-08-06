"""Hard book invariants: invested capital must never exceed equity.

Regression for the 2026-08-05 bug where TSLL + ANET were both booked at ~$950
while equity was only ~$950 (phantom ~$1900 open value).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from trading_pulse.agent.positions import (
    BOOK_INVARIANT_EPS_USD,
    assert_book_invariant,
    book_invariant_ok,
    book_deployed_vs_equity,
    free_cash,
    log_book_invariant,
    simulate_swing_day,
)


def _cfg(**kw):
    base = dict(
        commission_per_side_usd=0.0,
        max_open_positions=4,
        max_daily_loss_pct=1.0,
        hold_mode="swing",
        stop_loss_pct=0.12,
        take_profit_pct=0.25,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _lot_pos(symbol: str, capital: float, entry: float, day: str = "2026-08-05") -> dict:
    return {
        "symbol": symbol,
        "capital_usd": capital,
        "entry_price": entry,
        "entry_day": day,
        "stop_loss_pct": 0.12,
        "take_profit_pct": 0.25,
        "floor_price": entry * 0.9,
        "lots": [
            {
                "id": "x",
                "capital_usd": capital,
                "entry_price": entry,
                "entry_day": day,
            }
        ],
    }


def test_book_invariant_detects_double_capital_bug():
    state = {
        "equity": 949.82,
        "open_positions": [
            _lot_pos("TSLL", 949.82, 8.07),
            _lot_pos("ANET", 949.82, 194.36),
        ],
    }
    assert book_invariant_ok(state) is False
    equity, deployed, over = book_deployed_vs_equity(state)
    assert equity == 949.82
    assert deployed == pytest.approx(1899.64)
    assert over > 900
    with pytest.raises(AssertionError, match="book invariant broken"):
        assert_book_invariant(state, context="regression")


def test_book_invariant_ok_when_fully_invested_once():
    state = {
        "equity": 949.82,
        "open_positions": [_lot_pos("TSLL", 949.82, 8.07)],
    }
    assert book_invariant_ok(state) is True
    assert_book_invariant(state)
    assert free_cash(state) == 0.0


def test_aug5_scenario_manual_full_buy_then_open_cannot_double_book(monkeypatch):
    """Exact failure mode: all cash in TSLL, approved ANET $950 must not open."""
    cfg = _cfg()
    state = {
        "equity": 949.82,
        "open_positions": [_lot_pos("TSLL", 949.82, 8.07)],
    }
    approved = [
        {
            "symbol": "TSLL",
            "approved": True,
            "capital_usd": 949.82,
            "entry_ref_price": 8.07,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
            "floor_price": 7.0,
        },
        {
            "symbol": "ANET",
            "approved": True,
            "capital_usd": 949.82,
            "entry_ref_price": 194.36,
            "stop_loss_pct": 0.034,
            "take_profit_pct": 0.25,
            "floor_price": 187.69,
            "strategy": "method2",
            "method2_entry_ref": 194.36,
            "method2_stop_ref": 187.69,
            "side": "LONG",
            "trigger": "3-2-2",
        },
    ]

    def _bar(sym, _day):
        if sym == "ANET":
            # Breakout-looking bar so Method2 would fill if cash allowed it.
            return {"open": 195.0, "high": 200.0, "low": 194.0, "close": 198.0}
        return {"open": 8.1, "high": 8.2, "low": 8.0, "close": 8.1}

    monkeypatch.setattr("trading_pulse.agent.positions.fetch_day_ohlc", _bar)
    monkeypatch.setattr(
        "trading_pulse.agent.candle_method2.resolve_method2_fill",
        lambda rec, bar: float(bar["open"]),
    )

    _ex, still_open, _pnl, _fees = simulate_swing_day(
        cfg, state, date(2026, 8, 5), approved, entries_only=True
    )
    syms = {p["symbol"] for p in still_open}
    assert "ANET" not in syms
    assert syms == {"TSLL"}
    assert_book_invariant(state, context="aug5_regression")
    assert sum(float(p["capital_usd"]) for p in still_open) == pytest.approx(949.82)


def test_simulate_swing_day_never_leaves_overdeployed_book(monkeypatch):
    cfg = _cfg()
    state = {"equity": 1000.0, "open_positions": []}
    approved = [
        {
            "symbol": "AAA",
            "approved": True,
            "capital_usd": 800.0,
            "entry_ref_price": 10.0,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
            "floor_price": 5.0,
        },
        {
            "symbol": "BBB",
            "approved": True,
            "capital_usd": 800.0,
            "entry_ref_price": 20.0,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
            "floor_price": 10.0,
        },
        {
            "symbol": "CCC",
            "approved": True,
            "capital_usd": 800.0,
            "entry_ref_price": 30.0,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
            "floor_price": 15.0,
        },
    ]

    def _bar(sym, _day):
        px = {"AAA": 10.0, "BBB": 20.0, "CCC": 30.0}[sym]
        return {"open": px, "high": px + 1, "low": px - 0.5, "close": px}

    monkeypatch.setattr("trading_pulse.agent.positions.fetch_day_ohlc", _bar)
    _ex, still_open, _pnl, _fees = simulate_swing_day(
        cfg, state, date(2026, 8, 5), approved, entries_only=True
    )
    assert_book_invariant(state)
    total = sum(float(p["capital_usd"]) for p in still_open)
    assert total == pytest.approx(1000.0)
    assert free_cash(state) == 0.0


def test_open_position_now_refuses_when_no_cash(monkeypatch):
    import trading_pulse.agent.dryrun_agent as agent

    cfg = _cfg(max_open_positions=4, commission_per_side_usd=0.0)
    state = {
        "equity": 950.0,
        "open_positions": [_lot_pos("TSLL", 950.0, 8.0)],
    }
    monkeypatch.setattr(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        lambda *_a, **_k: {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
    )
    monkeypatch.setattr(
        "trading_pulse.agent.intraday_monitor.fetch_intraday_quote",
        lambda *_a, **_k: {"last": 100.0},
    )
    pos = agent._open_position_now(
        cfg,
        state,
        {"symbol": "ANET", "capital_usd": 950.0, "stop_loss_pct": 0.12, "take_profit_pct": 0.25},
        date(2026, 8, 5),
    )
    assert pos is None
    assert [p["symbol"] for p in state["open_positions"]] == ["TSLL"]
    assert_book_invariant(state)


def test_book_invariant_allows_cent_eps():
    """Tiny float drift under BOOK_INVARIANT_EPS_USD is not a broken book."""
    equity = 1000.0
    state = {
        "equity": equity,
        "open_positions": [_lot_pos("AAA", equity + BOOK_INVARIANT_EPS_USD, 10.0)],
    }
    assert book_invariant_ok(state) is True
    assert log_book_invariant(state, context="eps") is True

    state_over = {
        "equity": equity,
        "open_positions": [
            _lot_pos("AAA", equity + BOOK_INVARIANT_EPS_USD + 0.01, 10.0)
        ],
    }
    assert book_invariant_ok(state_over) is False


def test_log_book_invariant_returns_false_and_logs(caplog):
    import logging

    state = {
        "equity": 949.82,
        "open_positions": [
            _lot_pos("TSLL", 949.82, 8.07),
            _lot_pos("ANET", 949.82, 194.36),
        ],
    }
    with caplog.at_level(logging.ERROR):
        assert log_book_invariant(state, context="aug5") is False
    assert any("BOOK INVARIANT BROKEN" in r.message for r in caplog.records)
    assert any("aug5" in r.message for r in caplog.records)


def test_simulate_swing_day_trims_preexisting_overdeploy(monkeypatch):
    """Repair path: already-broken book is trimmed (last-in dropped) before return."""
    cfg = _cfg()
    state = {
        "equity": 949.82,
        "open_positions": [
            _lot_pos("TSLL", 949.82, 8.07),
            _lot_pos("ANET", 949.82, 194.36),
        ],
    }
    monkeypatch.setattr(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        lambda *_a, **_k: None,
    )
    _ex, still_open, _pnl, _fees = simulate_swing_day(
        cfg, state, date(2026, 8, 5), [], entries_only=True
    )
    assert_book_invariant(state, context="trim_repair")
    assert {p["symbol"] for p in still_open} == {"TSLL"}
    assert sum(float(p["capital_usd"]) for p in still_open) == pytest.approx(949.82)


def test_open_position_now_clamps_to_free_cash(monkeypatch):
    import trading_pulse.agent.dryrun_agent as agent

    cfg = _cfg(max_open_positions=4, commission_per_side_usd=0.0)
    state = {
        "equity": 1000.0,
        "open_positions": [_lot_pos("TSLL", 700.0, 8.0)],
    }
    monkeypatch.setattr(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        lambda *_a, **_k: {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
    )
    pos = agent._open_position_now(
        cfg,
        state,
        {
            "symbol": "ANET",
            "capital_usd": 950.0,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.25,
        },
        date(2026, 8, 5),
    )
    assert pos is not None
    assert float(pos["capital_usd"]) == 300.0
    assert {p["symbol"] for p in state["open_positions"]} == {"TSLL", "ANET"}
    assert_book_invariant(state)
    assert free_cash(state) == 0.0


def test_method2_fill_rolls_back_if_invariant_would_break(monkeypatch):
    """If cash clamp is wrong / stale, fill append must roll back — not leave over-deploy."""
    from trading_pulse.agent.method2_intraday import try_fill_pending_method2

    cfg = _cfg(
        method2_enabled=True,
        method2_intraday_enabled=True,
        method2_intraday_intervals=["5m"],
        max_open_positions=5,
    )
    state = {
        "equity": 950.0,
        "open_positions": [_lot_pos("META", 950.0, 100.0)],
    }
    plan = {
        "recommendations": [
            {
                "symbol": "ANET",
                "strategy": "method2",
                "sleeve": True,
                "approved": True,
                "side": "LONG",
                "capital_usd": 200.0,
                "method2_entry_ref": 194.0,
                "method2_stop_ref": 187.0,
                "floor_price": 187.0,
                "method2_status": "pending_breakout",
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.25,
            }
        ]
    }
    # Lie about free cash so the pre-check passes, then invariant catches the fill.
    monkeypatch.setattr(
        "trading_pulse.agent.positions.free_cash",
        lambda *_a, **_k: 500.0,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.method2_intraday.evaluate_method2_intraday_entry",
        lambda *_a, **_k: {
            "fill_price": 194.0,
            "reason": "daily_level_break",
            "interval": "5m",
        },
    )
    filled = try_fill_pending_method2(cfg, state, plan, date(2026, 8, 5))
    assert filled == []
    assert plan["recommendations"][0]["method2_status"] == "pending_breakout"
    assert "method2_fill_price" not in plan["recommendations"][0]
    assert [p["symbol"] for p in state["open_positions"]] == ["META"]
    assert_book_invariant(state, context="method2_rollback")

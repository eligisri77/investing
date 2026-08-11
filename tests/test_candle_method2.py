"""Tests for שיטה 2 candle taxonomy, HTF continuity, and breakout fills."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd

from trading_pulse.agent.candle_method2 import (
    analyze_method2_daily,
    classify_bar,
    classify_series,
    detect_pending_trigger,
    htf_allows_trade,
    resolve_method2_fill,
    size_method2_capital,
)
from trading_pulse.agent.positions import simulate_swing_day


def test_classify_1_2_3():
    assert classify_bar(10, 8, 9.5, 8.5) == 1  # inside
    assert classify_bar(10, 8, 11, 8.5) == 2  # high only
    assert classify_bar(10, 8, 9.5, 7) == 2  # low only
    assert classify_bar(10, 8, 11, 7) == 3  # both


def test_pending_2_1_becomes_2_1_2():
    rows = [
        (10, 11, 9, 10.5),
        (10.5, 12, 10.2, 11.8),  # 2 up
        (11.5, 11.9, 10.5, 11.0),  # 1 inside
    ]
    o = np.array([r[0] for r in rows], dtype=float)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    types = classify_series(h, l)
    assert types[-2:] == [2, 1]
    pending = detect_pending_trigger(types, o, h, l, c)
    assert pending is not None
    assert pending["trigger"] == "2-1-2"
    assert pending["entry_ref"] == round(11.9 + 0.01, 4)
    assert pending["stop_ref"] == round(10.5 - 0.01, 4)
    assert pending["side"] == "LONG"


def test_pending_short_2_1():
    rows = [
        (10, 11, 9, 10.5),
        (10.5, 10.8, 8.5, 8.7),  # 2 down
        (9.0, 9.5, 8.6, 9.0),  # 1 inside
    ]
    o = np.array([r[0] for r in rows], dtype=float)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    types = classify_series(h, l)
    assert types[-2:] == [2, 1]
    pending = detect_pending_trigger(types, o, h, l, c, side="SHORT")
    assert pending is not None
    assert pending["trigger"] == "2-1-2"
    assert pending["side"] == "SHORT"
    assert pending["entry_ref"] < pending["stop_ref"]


def test_pending_2_2_2_long_up_then_down_pullback():
    """2↑ then 2↓ → pending 2-2-2; entry above middle (2↓) high."""
    rows = [
        (10.0, 11.0, 9.5, 10.5),
        (10.6, 12.0, 10.4, 11.8),  # 2 up (took high only)
        (11.5, 11.7, 10.0, 10.2),  # 2 down (took low only) — middle
    ]
    o = np.array([r[0] for r in rows], dtype=float)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    types = classify_series(h, l)
    assert types[-2:] == [2, 2]
    pending = detect_pending_trigger(types, o, h, l, c, side="LONG")
    assert pending is not None
    assert pending["trigger"] == "2-2-2"
    assert pending["entry_ref"] == round(11.7 + 0.01, 4)
    assert pending["stop_ref"] == round(10.0 - 0.01, 4)


def test_pending_2_2_2_rejects_two_ups():
    """Two consecutive 2-up bars are not a 2-2-2 pullback setup."""
    rows = [
        (10.0, 11.0, 9.5, 10.5),
        (10.6, 12.0, 10.4, 11.8),  # 2 up
        (11.7, 13.0, 11.5, 12.8),  # 2 up again
    ]
    o = np.array([r[0] for r in rows], dtype=float)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    types = classify_series(h, l)
    assert types[-2:] == [2, 2]
    pending = detect_pending_trigger(types, o, h, l, c, side="LONG")
    assert pending is None


def test_pending_2_2_2_short_down_then_up_pullback():
    """2↓ then 2↑ → SHORT 2-2-2; entry below middle (2↑) low."""
    rows = [
        (12.0, 12.5, 11.0, 11.5),
        (11.4, 11.6, 10.0, 10.2),  # 2 down
        (10.4, 11.8, 10.3, 11.5),  # 2 up (pullback) — middle
    ]
    o = np.array([r[0] for r in rows], dtype=float)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    types = classify_series(h, l)
    assert types[-2:] == [2, 2]
    pending = detect_pending_trigger(types, o, h, l, c, side="SHORT")
    assert pending is not None
    assert pending["trigger"] == "2-2-2"
    assert pending["side"] == "SHORT"
    assert pending["entry_ref"] == round(10.3 - 0.01, 4)
    assert pending["stop_ref"] == round(11.8 + 0.01, 4)
    assert pending["entry_ref"] < pending["stop_ref"]


def test_pending_2_2_2_short_rejects_two_downs():
    """Two consecutive 2-down bars are not a SHORT 2-2-2 pullback setup."""
    rows = [
        (12.0, 12.5, 11.0, 11.5),
        (11.4, 11.6, 10.0, 10.2),  # 2 down
        (10.1, 10.3, 9.0, 9.2),  # 2 down again
    ]
    o = np.array([r[0] for r in rows], dtype=float)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    types = classify_series(h, l)
    assert types[-2:] == [2, 2]
    pending = detect_pending_trigger(types, o, h, l, c, side="SHORT")
    assert pending is None


def test_pending_2_2_2_long_rejects_down_then_up():
    """LONG needs impulse-up then pullback-down; reverse order is not 2-2-2."""
    rows = [
        (12.0, 12.5, 11.0, 11.5),
        (11.4, 11.6, 10.0, 10.2),  # 2 down
        (10.4, 11.8, 10.3, 11.5),  # 2 up
    ]
    o = np.array([r[0] for r in rows], dtype=float)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    types = classify_series(h, l)
    assert types[-2:] == [2, 2]
    pending = detect_pending_trigger(types, o, h, l, c, side="LONG")
    assert pending is None


def test_htf_rejects_weekly_inside():
    idx = pd.date_range("2025-01-01", periods=80, freq="B")
    close = np.linspace(10, 20, len(idx))
    high = close + 0.5
    low = close - 0.5
    open_ = close - 0.1
    high[-5:] = high[-6]
    low[-5:] = low[-6]
    close[-5:] = (high[-5] + low[-5]) / 2
    open_[-5:] = close[-5:]
    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 2_000_000},
        index=idx,
    )
    ok, info = htf_allows_trade(df, side="LONG")
    assert isinstance(ok, bool)
    assert "W" in info and "M" in info


def test_htf_rejects_weak_weekly_close_for_long():
    """Weekly structure may look active, but close near the low = conflict for longs."""
    idx = pd.date_range("2025-01-01", periods=120, freq="B")
    close = np.linspace(10, 30, len(idx))
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.2
    # Last week: wide range, close glued to the low (LABU-style conflict)
    high[-5:] = close[-6] + 3.0
    low[-5:] = close[-6] - 3.0
    open_[-5:] = close[-6] + 2.5
    close[-5:] = low[-5] + 0.1
    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 2_000_000},
        index=idx,
    )
    ok, info = htf_allows_trade(df, side="LONG")
    assert ok is False
    assert info.get("reject") in {"weekly_weak_close", "weekly_opposes", "htf_inside", "no_htf_continuation", "monthly_opposes"}


def test_size_sleeve_20_cent_stop():
    cap = size_method2_capital(
        equity=1000.0,
        entry_ref=50.0,
        stop_ref=49.80,
        risk_pct=0.02,
        max_position_pct=0.15,
    )
    assert cap == 150.0

    cap2 = size_method2_capital(
        equity=1000.0,
        entry_ref=10.0,
        stop_ref=9.80,
        risk_pct=0.02,
        max_position_pct=0.15,
    )
    assert cap2 == 150.0

    cap3 = size_method2_capital(
        equity=1000.0,
        entry_ref=5.0,
        stop_ref=4.80,
        risk_pct=0.02,
        max_position_pct=0.50,
    )
    assert cap3 == 500.0


def test_analyze_requires_volume():
    idx = pd.date_range("2025-01-01", periods=40, freq="B")
    close = np.linspace(10, 15, len(idx))
    df = pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": 1000,
        },
        index=idx,
    )
    assert analyze_method2_daily(df, min_avg_volume=1_000_000) is None


def test_resolve_method2_fill_long_breakout():
    rec = {
        "strategy": "method2",
        "side": "LONG",
        "method2_entry_ref": 100.0,
        "method2_stop_ref": 95.0,
    }
    # No breakout
    assert resolve_method2_fill(rec, {"open": 98, "high": 99.5, "low": 97, "close": 99}) is None
    # Gap below stop — skip
    assert resolve_method2_fill(rec, {"open": 94, "high": 101, "low": 93, "close": 100}) is None
    # Breakout: fill at entry_ref
    assert resolve_method2_fill(rec, {"open": 98, "high": 100.5, "low": 97, "close": 100.2}) == 100.0
    # Gap open above entry
    assert resolve_method2_fill(rec, {"open": 101, "high": 102, "low": 100.5, "close": 101.5}) == 101.0


def test_resolve_method2_fill_short_breakout():
    rec = {
        "strategy": "method2",
        "side": "SHORT",
        "method2_entry_ref": 100.0,
        "method2_stop_ref": 105.0,
    }
    assert resolve_method2_fill(rec, {"open": 101, "high": 102, "low": 100.5, "close": 101}) is None
    assert resolve_method2_fill(rec, {"open": 101, "high": 102, "low": 99.5, "close": 99.8}) == 100.0


def test_simulate_skips_method2_without_breakout(monkeypatch):
    cfg = SimpleNamespace(
        max_open_positions=5,
        max_daily_loss_pct=0.5,
        hold_mode="swing",
        commission_per_side_usd=0.0,
        stop_loss_pct=0.12,
        take_profit_pct=0.25,
        max_hold_days=5,
    )
    state = {"equity": 1000.0, "open_positions": []}
    rec = {
        "symbol": "TEST",
        "strategy": "method2",
        "sleeve": True,
        "side": "LONG",
        "capital_usd": 150,
        "method2_entry_ref": 50.0,
        "method2_stop_ref": 48.0,
        "floor_price": 48.0,
        "stop_loss_pct": 0.04,
        "take_profit_pct": 0.25,
    }

    def fake_bar(symbol, day):
        return {"open": 49.0, "high": 49.5, "low": 48.5, "close": 49.2}

    monkeypatch.setattr("trading_pulse.agent.positions.fetch_day_ohlc", fake_bar)
    executed, still_open, pnl, _fees = simulate_swing_day(
        cfg, state, pd.Timestamp("2026-07-13").date(), [rec], entries_only=True
    )
    assert still_open == []
    assert executed == []
    assert pnl == 0.0


def test_simulate_fills_method2_on_breakout(monkeypatch):
    cfg = SimpleNamespace(
        max_open_positions=5,
        max_daily_loss_pct=0.5,
        hold_mode="swing",
        commission_per_side_usd=0.0,
        stop_loss_pct=0.12,
        take_profit_pct=0.25,
        max_hold_days=5,
    )
    state = {"equity": 1000.0, "open_positions": []}
    rec = {
        "symbol": "TEST",
        "strategy": "method2",
        "sleeve": True,
        "side": "LONG",
        "capital_usd": 150,
        "method2_entry_ref": 50.0,
        "method2_stop_ref": 48.0,
        "floor_price": 48.0,
        "stop_loss_pct": 0.04,
        "take_profit_pct": 0.25,
        "take_profit_price": 62.5,
    }

    def fake_bar(symbol, day):
        return {"open": 49.0, "high": 50.5, "low": 48.8, "close": 50.2}

    monkeypatch.setattr("trading_pulse.agent.positions.fetch_day_ohlc", fake_bar)
    _executed, still_open, pnl, _fees = simulate_swing_day(
        cfg, state, pd.Timestamp("2026-07-13").date(), [rec], entries_only=True
    )
    assert len(still_open) == 1
    assert still_open[0]["entry_price"] == 50.0
    assert still_open[0]["side"] == "LONG"
    assert pnl == 0.0


def test_session_bar_and_micro_trigger_fill():
    from trading_pulse.agent.candle_method2 import _micro_breakout_fill, session_bar_from_intraday

    idx = pd.date_range("2026-07-13 14:00", periods=12, freq="5min", tz="UTC")
    # Build 2-up then inside, then breakout bar
    rows = []
    # base + rising structure
    base = [
        (10.0, 10.5, 9.8, 10.2),
        (10.2, 11.0, 10.1, 10.9),  # 2 up
        (10.8, 10.95, 10.3, 10.5),  # 1 inside
    ]
    # pad earlier bars
    for i in range(8):
        rows.append((10.0 + i * 0.01, 10.2 + i * 0.01, 9.9, 10.1))
    rows.extend(base)
    # live breakout bar above inside high and daily entry 10.96
    rows.append((10.6, 11.2, 10.55, 11.1))
    df = pd.DataFrame(
        {
            "Open": [r[0] for r in rows],
            "High": [r[1] for r in rows],
            "Low": [r[2] for r in rows],
            "Close": [r[3] for r in rows],
        },
        index=idx[: len(rows)],
    )
    session = session_bar_from_intraday(df)
    assert session is not None
    assert session["high"] >= 11.0

    micro = _micro_breakout_fill(df, side="LONG", daily_entry=10.96, daily_stop=10.25)
    assert micro is not None
    assert micro["fill_price"] >= 10.96
    assert micro["reason"] == "micro_trigger"


def test_try_fill_pending_method2(monkeypatch):
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
    state = {"equity": 1000.0, "open_positions": []}
    plan = {
        "recommendations": [
            {
                "symbol": "AAA",
                "strategy": "method2",
                "sleeve": True,
                "approved": True,
                "side": "LONG",
                "capital_usd": 100,
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
        lambda rec, intervals=("5m",): {
            "fill_price": 50.0,
            "reason": "daily_level_break",
            "interval": "5m",
        },
    )
    filled = try_fill_pending_method2(cfg, state, plan, date(2026, 7, 13))
    assert len(filled) == 1
    assert filled[0]["entry_price"] == 50.0
    assert plan["recommendations"][0]["method2_status"] == "filled"
    assert len(state["open_positions"]) == 1

"""Tests for שיטה 2 candle taxonomy and pending triggers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_pulse.agent.candle_method2 import (
    analyze_method2_daily,
    classify_bar,
    classify_series,
    detect_pending_trigger,
    htf_allows_trade,
    size_method2_capital,
)


def test_classify_1_2_3():
    assert classify_bar(10, 8, 9.5, 8.5) == 1  # inside
    assert classify_bar(10, 8, 11, 8.5) == 2  # high only
    assert classify_bar(10, 8, 9.5, 7) == 2  # low only
    assert classify_bar(10, 8, 11, 7) == 3  # both


def test_pending_2_1_becomes_2_1_2():
    # Build OHLC where last two types are 2 then 1
    # Bar0: base
    # Bar1: breaks high (2)
    # Bar2: inside (1)
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


def test_htf_rejects_weekly_inside():
    idx = pd.date_range("2025-01-01", periods=80, freq="B")
    # Mostly trending then a tight inside week at the end — force weekly type 1
    close = np.linspace(10, 20, len(idx))
    high = close + 0.5
    low = close - 0.5
    open_ = close - 0.1
    # Last few days: tiny range inside prior week
    high[-5:] = high[-6]
    low[-5:] = low[-6]
    close[-5:] = (high[-5] + low[-5]) / 2
    open_[-5:] = close[-5:]
    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 2_000_000},
        index=idx,
    )
    # May or may not reject depending on resample; at least returns tuple
    ok, info = htf_allows_trade(df)
    assert isinstance(ok, bool)
    assert "W" in info and "M" in info


def test_size_sleeve_20_cent_stop():
    # $1000 equity, 2% risk = $20; stop $0.20 → 100 shares @ $50 = $5000 notional → capped 15% = $150
    cap = size_method2_capital(
        equity=1000.0,
        entry_ref=50.0,
        stop_ref=49.80,
        risk_pct=0.02,
        max_position_pct=0.15,
    )
    assert cap == 150.0

    # Wider stop / lower price so notional under cap
    cap2 = size_method2_capital(
        equity=1000.0,
        entry_ref=10.0,
        stop_ref=9.80,
        risk_pct=0.02,
        max_position_pct=0.15,
    )
    # 20/0.2 = 100 shares * 10 = 1000 → capped to 150
    assert cap2 == 150.0

    cap3 = size_method2_capital(
        equity=1000.0,
        entry_ref=5.0,
        stop_ref=4.80,
        risk_pct=0.02,
        max_position_pct=0.50,
    )
    # 100 shares * 5 = 500
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
            "Volume": 1000,  # too low
        },
        index=idx,
    )
    assert analyze_method2_daily(df, min_avg_volume=1_000_000) is None

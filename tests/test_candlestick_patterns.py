"""Tests for Rising Three Methods detector."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_pulse.agent.candlestick_patterns import (
    PATTERN_RISING_THREE,
    analyze_rising_three_methods,
)


def _ohlc_from_rows(rows: list[tuple[float, float, float, float]], *, pad: int = 25) -> pd.DataFrame:
    """Build OHLC with MA20 padding (flat history) then pattern rows."""
    base_close = rows[0][3] * 0.92
    hist = []
    for i in range(pad):
        c = base_close + i * 0.05
        hist.append((c - 0.2, c + 0.3, c - 0.4, c, 1_000_000))
    data = hist + [(o, h, l, c, 1_200_000) for o, h, l, c in rows]
    return pd.DataFrame(data, columns=["Open", "High", "Low", "Close", "Volume"])


def test_rising_three_full_match():
    # Long green, 3 small inside, long green new high close
    rows = [
        (10.0, 12.0, 9.8, 11.8),   # long bull
        (11.5, 11.7, 10.2, 10.5),  # small red inside
        (10.6, 11.4, 10.1, 10.3),
        (10.4, 11.3, 10.0, 10.2),
        (10.5, 12.4, 10.4, 12.2),  # long bull new high
    ]
    df = _ohlc_from_rows(rows)
    hit = analyze_rising_three_methods(df)
    assert hit is not None
    assert hit["pattern"] == PATTERN_RISING_THREE
    assert hit["full_match"] is True
    assert hit["pattern_weak"] is False
    assert hit["pattern_score"] >= 8.0


def test_rising_three_fails_when_middle_breaks_range():
    rows = [
        (10.0, 12.0, 9.8, 11.8),
        (11.5, 12.5, 10.2, 10.5),  # high above first candle
        (10.6, 11.4, 10.1, 10.3),
        (10.4, 11.3, 10.0, 10.2),
        (10.5, 12.4, 10.4, 12.2),
    ]
    df = _ohlc_from_rows(rows)
    hit = analyze_rising_three_methods(df)
    assert hit is not None
    assert hit["full_match"] is False
    assert hit["pattern_weak"] is True


def test_rising_three_fails_final_close_not_new_high():
    rows = [
        (10.0, 12.0, 9.8, 11.8),
        (11.5, 11.7, 10.2, 10.5),
        (10.6, 11.4, 10.1, 10.3),
        (10.4, 11.3, 10.0, 10.2),
        (10.5, 11.6, 10.4, 11.2),  # closes below first close high
    ]
    df = _ohlc_from_rows(rows)
    hit = analyze_rising_three_methods(df)
    assert hit is not None
    assert hit["full_match"] is False
    assert "שיא" in hit["reason_he"] or hit["pattern_weak"]


def test_rising_three_rejects_noise():
    # Random tiny bars — score too low
    rng = np.random.default_rng(0)
    rows = []
    for _ in range(5):
        o = 10.0 + float(rng.normal(0, 0.05))
        c = o + float(rng.normal(0, 0.05))
        h = max(o, c) + 0.05
        l = min(o, c) - 0.05
        rows.append((o, h, l, c))
    df = _ohlc_from_rows(rows)
    hit = analyze_rising_three_methods(df)
    assert hit is None

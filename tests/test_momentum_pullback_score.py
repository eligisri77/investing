"""Unit tests for trend + pullback momentum scoring."""

from __future__ import annotations

from trading_pulse.agent.signal_sources import (
    _ohlcv_df_from_series,
    _ohlcv_metrics,
    score_momentum,
    score_speculative,
)


def _base(**overrides) -> dict:
    m = {
        "momentum_ok": True,
        "above_ma20_pct": 3.0,
        "near_high_pct": -4.0,
        "ret_1d": -0.015,
        "ret_5d": 0.04,
        "down_days_last_3": 2,
        "up_days_last_5": 2,
        "down_days_last_5": 3,
        "range_5d_pct": 5.0,
        "zigzag_in_range": True,
        "vol_ratio": 1.2,
        "atr_pct": 3.0,
        "pullback_ok": True,
    }
    m.update(overrides)
    return m


def _metrics_from_closes(
    closes: list[float],
    *,
    high_off: float = 1.0,
    low_off: float = 1.0,
) -> dict:
    highs = [c + high_off for c in closes]
    lows = [c - low_off for c in closes]
    volumes = [1_000_000.0] * len(closes)
    out = _ohlcv_metrics(
        _ohlcv_df_from_series(closes=closes, highs=highs, lows=lows, volumes=volumes)
    )
    assert out is not None
    return out


def test_pullback_scores_higher_than_chase_at_high():
    pullback = _base()
    chase = _base(
        near_high_pct=-0.2,
        ret_1d=0.02,
        ret_5d=0.18,
        down_days_last_3=0,
        up_days_last_5=5,
        down_days_last_5=0,
        zigzag_in_range=False,
        pullback_ok=False,
    )
    assert score_momentum(pullback) > score_momentum(chase)
    assert score_speculative(pullback) > score_speculative(chase)


def test_below_ma20_scores_lower_than_above():
    above = _base()
    below = _base(momentum_ok=False, above_ma20_pct=-2.0, pullback_ok=False)
    assert score_momentum(below) < score_momentum(above)
    # Trend term alone is −5 vs +4; keep other terms equal so gap is large.
    assert score_momentum(above) - score_momentum(below) >= 8.0


def test_zigzag_bonus_over_same_setup_without_zigzag():
    common = dict(
        ret_1d=0.005,
        down_days_last_3=0,
        near_high_pct=-10.0,  # outside pullback band
        up_days_last_5=3,
        down_days_last_5=2,
    )
    zigzag = _base(zigzag_in_range=True, **common)
    no_zigzag = _base(zigzag_in_range=False, **common)
    assert score_momentum(zigzag) > score_momentum(no_zigzag)


def test_chase_near_high_and_hot_ret5d_penalized():
    clean = _base(near_high_pct=-4.0, ret_5d=0.05)
    chased = _base(near_high_pct=-0.5, ret_5d=0.20, pullback_ok=False)
    assert score_momentum(chased) < score_momentum(clean)


def test_pullback_band_near_high_adds_bonus():
    in_band = _base(near_high_pct=-4.0, zigzag_in_range=False)
    deep = _base(near_high_pct=-10.0, zigzag_in_range=False)
    assert score_momentum(in_band) > score_momentum(deep)


def test_score_speculative_adds_atr_over_momentum():
    m = _base(atr_pct=4.0)
    assert score_speculative(m) > score_momentum(m)


def test_ohlcv_metrics_short_series_returns_none():
    closes = [100.0 + i for i in range(20)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    vols = [1_000_000.0] * len(closes)
    assert (
        _ohlcv_metrics(
            _ohlcv_df_from_series(closes=closes, highs=highs, lows=lows, volumes=vols)
        )
        is None
    )


def test_ohlcv_metrics_pullback_ok_above_ma20_in_band():
    # Climb, then five down days: stay above MA20 and ~3–4% below 20d high.
    closes = [90 + i * 1.5 for i in range(25)]
    closes += [125.5, 124.5, 123.5, 122.5, 121.5]
    m = _metrics_from_closes(closes)
    assert m["momentum_ok"] is True
    assert m["zigzag_in_range"] is False
    assert -8.0 <= m["near_high_pct"] <= -2.0
    assert m["ret_1d"] < 0
    assert m["pullback_ok"] is True


def test_ohlcv_metrics_below_ma20_not_pullback_ok():
    closes = [150.0 - i for i in range(30)]
    m = _metrics_from_closes(closes)
    assert m["momentum_ok"] is False
    assert m["pullback_ok"] is False


def test_ohlcv_metrics_zigzag_in_tight_range_sets_pullback_ok():
    base = [100 + i * 0.3 for i in range(25)]
    tail = [107.0, 106.5, 107.2, 106.8, 107.1]
    m = _metrics_from_closes(base + tail)
    assert m["momentum_ok"] is True
    assert m["up_days_last_5"] >= 2
    assert m["down_days_last_5"] >= 2
    assert m["range_5d_pct"] <= 8.0
    assert m["zigzag_in_range"] is True
    assert m["pullback_ok"] is True


def test_ohlcv_metrics_wide_range_not_zigzag():
    closes = [100 + i * 0.3 for i in range(25)] + [107.0, 106.0, 107.0, 106.0, 107.0]
    highs = [c + 1 for c in closes[:-5]] + [120.0] * 5
    lows = [c - 1 for c in closes[:-5]] + [90.0] * 5
    volumes = [1_000_000.0] * len(closes)
    m = _ohlcv_metrics(
        _ohlcv_df_from_series(closes=closes, highs=highs, lows=lows, volumes=volumes)
    )
    assert m is not None
    assert m["range_5d_pct"] > 8.0
    assert m["zigzag_in_range"] is False


def test_ohlcv_metrics_chase_at_high_not_pullback_ok():
    closes = [100 + i * 0.8 for i in range(30)]
    m = _metrics_from_closes(closes)
    assert m["momentum_ok"] is True
    assert m["near_high_pct"] > -1.0
    assert m["zigzag_in_range"] is False
    assert m["pullback_ok"] is False

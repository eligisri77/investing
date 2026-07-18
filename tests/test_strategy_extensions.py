from __future__ import annotations

import numpy as np
import pandas as pd

from trading_pulse.agent.strategies.market_regime import analyze_market_regime
from trading_pulse.agent.strategies.trend_pullback import analyze_trend_pullback


def _ohlcv(close_values: list[float]) -> pd.DataFrame:
    close = np.array(close_values, dtype=float)
    return pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 0.8,
            "Low": close - 0.8,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000.0),
        },
        index=pd.date_range("2025-01-01", periods=len(close), freq="D"),
    )


def test_trend_pullback_detects_reversal_near_ema20():
    base = [100 + i * 0.16 + np.sin(i / 2) * 1.2 for i in range(75)]
    # Controlled pullback followed by a positive reversal.
    base[-5:] = [111.5, 110.5, 109.5, 109.8, 111.0]
    hit = analyze_trend_pullback(_ohlcv(base), symbol="AAA")
    assert hit is not None
    assert hit.strategy_id == "trend_pullback"
    assert "ניסיוני" in hit.reason
    assert "EMA20" in hit.reason
    assert hit.stop_loss_price < hit.entry_ref_price < hit.take_profit_price


def test_trend_pullback_rejects_falling_trend():
    values = [150 - i * 0.5 for i in range(80)]
    assert analyze_trend_pullback(_ohlcv(values), symbol="AAA") is None


def test_market_regime_risk_off_below_ma200():
    falling = _ohlcv([300 - i * 0.6 for i in range(220)])
    out = analyze_market_regime(falling, falling)
    assert out["status"] == "risk_off"
    assert out["exposure_multiplier"] == 0.0
    assert "ניסיוני" in out["reason_he"]
    assert "נעצרו" in out["reason_he"]


def test_market_regime_risk_on_above_ma50():
    rising = _ohlcv([100 + i * 0.5 for i in range(220)])
    out = analyze_market_regime(rising, rising)
    assert out["status"] == "risk_on"
    assert out["exposure_multiplier"] == 1.0
    assert "לא צומצמה" in out["reason_he"]

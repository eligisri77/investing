from __future__ import annotations

import numpy as np
import pandas as pd

from trading_pulse.agent.strategies.market_regime import analyze_market_regime
from trading_pulse.agent.strategies.relative_strength import (
    analyze_relative_strength,
    signal_to_recommendation as relative_strength_recommendation,
)
from trading_pulse.agent.strategies.trend_pullback import analyze_trend_pullback
from trading_pulse.agent.strategies.vcp_breakout import (
    analyze_vcp_breakout,
    signal_to_recommendation as vcp_recommendation,
)


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


def _vcp_frame() -> pd.DataFrame:
    close = np.linspace(80.0, 120.0, 130)
    high = close + 0.4
    low = close - 0.4
    high[-61:-31] += 5.0
    low[-61:-31] -= 5.0
    close[-1] = high[-21:-1].max() + 1.0
    high[-1] = close[-1] + 0.4
    low[-1] = close[-1] - 0.4
    volume = np.full(130, 1_000_000.0)
    volume[-11:-1] = 500_000.0
    volume[-1] = 1_500_000.0
    return pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=pd.date_range("2025-01-01", periods=130, freq="D"),
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


def test_vcp_breakout_detects_contraction_and_volume_breakout():
    hit = analyze_vcp_breakout(_vcp_frame(), symbol="vcp")

    assert hit is not None
    assert hit.strategy_id == "vcp_breakout"
    assert hit.symbol == "VCP"
    assert hit.evidence["contraction_ratio"] <= 0.75
    assert hit.evidence["dry_up_volume_ratio"] <= 0.90
    assert hit.evidence["breakout_volume_ratio"] >= 1.20
    assert hit.stop_loss_price < hit.entry_ref_price < hit.take_profit_price


def test_vcp_breakout_rejects_breakout_without_volume_confirmation():
    frame = _vcp_frame()
    frame.loc[frame.index[-1], "Volume"] = 500_000.0

    assert analyze_vcp_breakout(frame, symbol="VCP") is None


def test_relative_strength_detects_persistent_spy_outperformance():
    stock = _ohlcv([100 + i * 0.45 for i in range(130)])
    benchmark = _ohlcv([100 + i * 0.05 for i in range(130)])

    hit = analyze_relative_strength(stock, benchmark, symbol="rs")

    assert hit is not None
    assert hit.strategy_id == "relative_strength"
    assert hit.symbol == "RS"
    assert hit.evidence["relative_strength_63d_pct"] >= 10
    assert hit.evidence["relative_strength_21d_pct"] > 0
    assert hit.stop_loss_price < hit.entry_ref_price < hit.take_profit_price


def test_relative_strength_rejects_stock_that_does_not_outperform_spy():
    stock = _ohlcv([100 + i * 0.45 for i in range(130)])

    assert analyze_relative_strength(stock, stock.copy(), symbol="RS") is None


def test_experimental_signal_conversion_preserves_attribution():
    vcp_hit = analyze_vcp_breakout(_vcp_frame(), symbol="VCP")
    stock = _ohlcv([100 + i * 0.45 for i in range(130)])
    benchmark = _ohlcv([100 + i * 0.05 for i in range(130)])
    relative_hit = analyze_relative_strength(stock, benchmark, symbol="RS")

    assert vcp_hit is not None
    assert relative_hit is not None
    for signal, convert in (
        (vcp_hit, vcp_recommendation),
        (relative_hit, relative_strength_recommendation),
    ):
        rec = convert(signal)
        assert rec["strategy"] == signal.strategy_id
        assert rec["strategy_id"] == signal.strategy_id
        assert rec["strategy_version"] == "1.0"
        assert rec["entry_policy"] == "market_open"
        assert rec["contributing_strategies"] == [signal.strategy_id]
        assert rec["floor_price"] == rec["stop_loss_price"]
        assert rec["approved"] is False

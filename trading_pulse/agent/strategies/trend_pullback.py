"""Trend-pullback continuation strategy (experimental, disabled by default)."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import yfinance as yf

from trading_pulse.agent.strategies.models import StrategySignal
from trading_pulse.agent.strategies.registry import STRATEGY_SPECS


def _series(df: pd.DataFrame, name: str) -> pd.Series:
    col = df[name]
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    return col.astype(float)


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(period).mean()
    losses = (-delta.clip(upper=0)).rolling(period).mean()
    avg_gain = float(gains.iloc[-1])
    avg_loss = float(losses.iloc[-1])
    if avg_loss <= 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def analyze_trend_pullback(
    df: pd.DataFrame,
    *,
    symbol: str,
    stop_loss_pct: float = 0.06,
    take_profit_pct: float = 0.12,
) -> StrategySignal | None:
    """Detect a controlled pullback toward EMA20 inside a rising trend."""
    if df is None or len(df) < 60:
        return None
    close = _series(df, "Close").dropna()
    low = _series(df, "Low").reindex(close.index)
    volume = _series(df, "Volume").reindex(close.index)
    if len(close) < 60:
        return None
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    ema20_last = float(ema20.iloc[-1])
    ema50_last = float(ema50.iloc[-1])
    ema20_rising = ema20_last > float(ema20.iloc[-6])
    trend_ok = last > ema50_last and ema20_last > ema50_last and ema20_rising
    recent_low = float(low.iloc[-5:].min())
    pullback_distance = abs(recent_low / ema20_last - 1) if ema20_last > 0 else 99
    pullback_ok = pullback_distance <= 0.035
    reversal_ok = last > prev and last >= ema20_last * 0.99
    rsi = _rsi(close)
    rsi_ok = 40.0 <= rsi <= 68.0
    avg_volume = float(volume.iloc[-21:-1].mean())
    volume_ratio = float(volume.iloc[-1] / avg_volume) if avg_volume > 0 else 0.0
    if not (trend_ok and pullback_ok and reversal_ok and rsi_ok):
        return None
    score = (
        4.0
        + max(0.0, 2.0 - pullback_distance * 40)
        + min(2.0, max(0.0, volume_ratio - 0.7) * 2)
        + min(2.0, max(0.0, (last / ema50_last - 1) * 20))
    )
    spec = STRATEGY_SPECS["trend_pullback"]
    return StrategySignal(
        strategy_id=spec.id,
        strategy_version=spec.version,
        symbol=symbol.upper(),
        side="LONG",
        native_score=score,
        confidence=min(1.0, score / 10.0),
        reason=(
            f"אות ניסיוני: מגמה עולה, תיקון ל־EMA20 וחזרת מחיר "
            f"(RSI {rsi:.0f}, נפח {volume_ratio:.1f}x)"
        ),
        entry_policy=spec.entry_policy,
        entry_ref_price=last,
        stop_loss_price=last * (1 - stop_loss_pct),
        take_profit_price=last * (1 + take_profit_pct),
        evidence={
            "ema20": round(ema20_last, 4),
            "ema50": round(ema50_last, 4),
            "rsi14": round(rsi, 2),
            "volume_ratio": round(volume_ratio, 2),
            "pullback_distance_pct": round(pullback_distance * 100, 2),
        },
        contributing_strategies=[spec.id],
    )


def scan_trend_pullback(
    symbols: list[str],
    *,
    exclude: set[str] | frozenset[str] = frozenset(),
    stop_loss_pct: float = 0.06,
    take_profit_pct: float = 0.12,
) -> StrategySignal | None:
    hits: list[StrategySignal] = []
    excluded = {str(s).upper() for s in exclude}
    for symbol in symbols:
        sym = str(symbol).upper()
        if sym in excluded:
            continue
        try:
            df = yf.download(
                sym,
                period="6mo",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            hit = analyze_trend_pullback(
                df,
                symbol=sym,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
            )
            if hit:
                hits.append(hit)
        except Exception as ex:
            logging.debug("Trend pullback failed %s: %s", sym, ex)
    return max(hits, key=lambda hit: hit.confidence, default=None)


def signal_to_recommendation(signal: StrategySignal) -> dict[str, Any]:
    return {
        "symbol": signal.symbol,
        "side": signal.side,
        "capital_usd": round(signal.requested_capital_usd, 2),
        "entry_ref_price": round(signal.entry_ref_price, 4),
        "stop_loss_price": round(signal.stop_loss_price, 4),
        "floor_price": round(signal.stop_loss_price, 4),
        "take_profit_price": round(signal.take_profit_price, 4),
        "stop_loss_pct": round(
            abs(signal.entry_ref_price - signal.stop_loss_price)
            / signal.entry_ref_price,
            4,
        ),
        "take_profit_pct": round(
            abs(signal.take_profit_price - signal.entry_ref_price)
            / signal.entry_ref_price,
            4,
        ),
        "score": round(signal.native_score, 4),
        "native_score": round(signal.native_score, 4),
        "confidence": round(signal.confidence, 4),
        "strategy": "trend_pullback",
        "strategy_id": signal.strategy_id,
        "strategy_version": signal.strategy_version,
        "entry_policy": signal.entry_policy,
        "contributing_strategies": signal.contributing_strategies,
        "reason": signal.reason,
        "evidence": signal.evidence,
        "approved": False,
        "below_bar": False,
        "volume_ok": True,
        "sources_used": 1,
        "sources_list": ["daily_ohlcv"],
        "source_scores": {"trend_pullback": round(signal.native_score, 2)},
    }

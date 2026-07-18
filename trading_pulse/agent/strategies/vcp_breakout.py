"""Volatility Contraction Pattern breakout strategy (experimental)."""

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


def analyze_vcp_breakout(
    df: pd.DataFrame,
    *,
    symbol: str,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.14,
    min_price_usd: float = 5.0,
    min_avg_volume_20d: float = 500_000,
) -> StrategySignal | None:
    """Detect a confirmed breakout after price and volume contraction."""
    if df is None or len(df) < 120:
        return None
    close = _series(df, "Close").dropna()
    high = _series(df, "High").reindex(close.index)
    low = _series(df, "Low").reindex(close.index)
    volume = _series(df, "Volume").reindex(close.index)
    if len(close) < 120:
        return None

    sma50 = close.rolling(50).mean()
    sma100 = close.rolling(100).mean()
    last = float(close.iloc[-1])
    pivot = float(high.iloc[-21:-1].max())
    trend_ok = last > float(sma50.iloc[-1]) > float(sma100.iloc[-1])

    older_high = float(high.iloc[-61:-31].max())
    older_low = float(low.iloc[-61:-31].min())
    recent_high = float(high.iloc[-21:-1].max())
    recent_low = float(low.iloc[-21:-1].min())
    older_mid = (older_high + older_low) / 2
    recent_mid = (recent_high + recent_low) / 2
    older_range = (older_high - older_low) / older_mid if older_mid > 0 else 99.0
    recent_range = (recent_high - recent_low) / recent_mid if recent_mid > 0 else 99.0
    contraction_ratio = recent_range / older_range if older_range > 0 else 99.0

    prior_volume = float(volume.iloc[-41:-11].mean())
    dry_volume = float(volume.iloc[-11:-1].mean())
    normal_volume = float(volume.iloc[-21:-1].mean())
    dry_up_ratio = dry_volume / prior_volume if prior_volume > 0 else 99.0
    breakout_volume_ratio = float(volume.iloc[-1] / normal_volume) if normal_volume > 0 else 0.0
    breakout_ok = pivot > 0 and pivot < last <= pivot * 1.05

    if not (
        last >= min_price_usd
        and normal_volume >= min_avg_volume_20d
        and trend_ok
        and breakout_ok
        and contraction_ratio <= 0.75
        and dry_up_ratio <= 0.90
        and breakout_volume_ratio >= 1.20
    ):
        return None

    score = (
        4.0
        + min(2.0, max(0.0, (0.75 - contraction_ratio) * 5))
        + min(2.0, max(0.0, (1.0 - dry_up_ratio) * 5))
        + min(2.0, max(0.0, breakout_volume_ratio - 1.0))
    )
    stop = max(recent_low, last * (1 - stop_loss_pct))
    spec = STRATEGY_SPECS["vcp_breakout"]
    return StrategySignal(
        strategy_id=spec.id,
        strategy_version=spec.version,
        symbol=symbol.upper(),
        side="LONG",
        native_score=score,
        confidence=min(1.0, score / 10.0),
        reason=(
            "אות ניסיוני VCP: התנודתיות והנפח התכווצו ולאחר מכן התקבלה "
            f"פריצה בנפח {breakout_volume_ratio:.1f}x"
        ),
        entry_policy=spec.entry_policy,
        entry_ref_price=last,
        stop_loss_price=stop,
        take_profit_price=last * (1 + take_profit_pct),
        evidence={
            "pivot": round(pivot, 4),
            "contraction_ratio": round(contraction_ratio, 3),
            "dry_up_volume_ratio": round(dry_up_ratio, 3),
            "breakout_volume_ratio": round(breakout_volume_ratio, 2),
            "sma50": round(float(sma50.iloc[-1]), 4),
            "sma100": round(float(sma100.iloc[-1]), 4),
        },
        contributing_strategies=[spec.id],
    )


def scan_vcp_breakout(
    symbols: list[str],
    *,
    exclude: set[str] | frozenset[str] = frozenset(),
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.14,
    min_price_usd: float = 5.0,
    min_avg_volume_20d: float = 500_000,
) -> StrategySignal | None:
    hits: list[StrategySignal] = []
    excluded = {str(symbol).upper() for symbol in exclude}
    for symbol in symbols:
        sym = str(symbol).upper()
        if sym in excluded:
            continue
        try:
            df = yf.download(
                sym,
                period="1y",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            hit = analyze_vcp_breakout(
                df,
                symbol=sym,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                min_price_usd=min_price_usd,
                min_avg_volume_20d=min_avg_volume_20d,
            )
            if hit:
                hits.append(hit)
        except Exception as ex:
            logging.debug("VCP scan failed %s: %s", sym, ex)
    return max(hits, key=lambda hit: hit.confidence, default=None)


def signal_to_recommendation(signal: StrategySignal) -> dict[str, Any]:
    entry = signal.entry_ref_price
    return {
        "symbol": signal.symbol,
        "side": signal.side,
        "capital_usd": round(signal.requested_capital_usd, 2),
        "entry_ref_price": round(entry, 4),
        "stop_loss_price": round(signal.stop_loss_price, 4),
        "floor_price": round(signal.stop_loss_price, 4),
        "take_profit_price": round(signal.take_profit_price, 4),
        "stop_loss_pct": round(abs(entry - signal.stop_loss_price) / entry, 4),
        "take_profit_pct": round(abs(signal.take_profit_price - entry) / entry, 4),
        "score": round(signal.native_score, 4),
        "native_score": round(signal.native_score, 4),
        "confidence": round(signal.confidence, 4),
        "strategy": signal.strategy_id,
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
        "source_scores": {signal.strategy_id: round(signal.native_score, 2)},
    }

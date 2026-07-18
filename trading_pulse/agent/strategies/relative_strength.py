"""Relative-strength strategy versus SPY (experimental)."""

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


def analyze_relative_strength(
    stock_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    *,
    symbol: str,
    stop_loss_pct: float = 0.08,
    take_profit_pct: float = 0.16,
    min_price_usd: float = 5.0,
    min_avg_volume_20d: float = 500_000,
) -> StrategySignal | None:
    """Select an up-trending stock that has persistently outperformed SPY."""
    if stock_df is None or benchmark_df is None:
        return None
    stock_close = _series(stock_df, "Close").rename("stock")
    benchmark_close = _series(benchmark_df, "Close").rename("benchmark")
    prices = pd.concat([stock_close, benchmark_close], axis=1, join="inner").dropna()
    if len(prices) < 100:
        return None

    stock = prices["stock"]
    benchmark = prices["benchmark"]
    last = float(stock.iloc[-1])
    sma50 = float(stock.rolling(50).mean().iloc[-1])
    sma100 = float(stock.rolling(100).mean().iloc[-1])
    stock_ret_63 = float(last / stock.iloc[-64] - 1)
    benchmark_ret_63 = float(benchmark.iloc[-1] / benchmark.iloc[-64] - 1)
    stock_ret_21 = float(last / stock.iloc[-22] - 1)
    benchmark_ret_21 = float(benchmark.iloc[-1] / benchmark.iloc[-22] - 1)
    relative_63 = stock_ret_63 - benchmark_ret_63
    relative_21 = stock_ret_21 - benchmark_ret_21

    volume = _series(stock_df, "Volume").reindex(stock.index)
    average_volume = float(volume.iloc[-21:-1].mean())
    volume_ratio = float(volume.iloc[-1] / average_volume) if average_volume > 0 else 0.0
    if not (
        last >= min_price_usd
        and average_volume >= min_avg_volume_20d
        and last > sma50 > sma100
        and stock_ret_63 >= 0.08
        and relative_63 >= 0.10
        and relative_21 > 0
    ):
        return None

    score = (
        4.0
        + min(3.0, max(0.0, relative_63 * 10))
        + min(2.0, max(0.0, relative_21 * 10))
        + min(1.0, max(0.0, volume_ratio - 0.8))
    )
    recent_low = float(_series(stock_df, "Low").reindex(stock.index).iloc[-20:].min())
    stop = max(recent_low, last * (1 - stop_loss_pct))
    spec = STRATEGY_SPECS["relative_strength"]
    return StrategySignal(
        strategy_id=spec.id,
        strategy_version=spec.version,
        symbol=symbol.upper(),
        side="LONG",
        native_score=score,
        confidence=min(1.0, score / 10.0),
        reason=(
            "אות ניסיוני של חוזק יחסי: המניה הקדימה את SPY ב־"
            f"{relative_63 * 100:.1f}% בשלושה חודשים ושמרה על מגמה עולה"
        ),
        entry_policy=spec.entry_policy,
        entry_ref_price=last,
        stop_loss_price=stop,
        take_profit_price=last * (1 + take_profit_pct),
        evidence={
            "stock_return_63d_pct": round(stock_ret_63 * 100, 2),
            "spy_return_63d_pct": round(benchmark_ret_63 * 100, 2),
            "relative_strength_63d_pct": round(relative_63 * 100, 2),
            "relative_strength_21d_pct": round(relative_21 * 100, 2),
            "volume_ratio": round(volume_ratio, 2),
            "sma50": round(sma50, 4),
            "sma100": round(sma100, 4),
        },
        contributing_strategies=[spec.id],
    )


def scan_relative_strength(
    symbols: list[str],
    *,
    exclude: set[str] | frozenset[str] = frozenset(),
    benchmark_symbol: str = "SPY",
    stop_loss_pct: float = 0.08,
    take_profit_pct: float = 0.16,
    min_price_usd: float = 5.0,
    min_avg_volume_20d: float = 500_000,
) -> StrategySignal | None:
    try:
        benchmark = yf.download(
            benchmark_symbol,
            period="1y",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as ex:
        logging.debug("Relative-strength benchmark failed: %s", ex)
        return None
    if benchmark is None or benchmark.empty:
        return None

    hits: list[StrategySignal] = []
    excluded = {str(symbol).upper() for symbol in exclude}
    for symbol in symbols:
        sym = str(symbol).upper()
        if sym in excluded or sym == benchmark_symbol.upper():
            continue
        try:
            stock = yf.download(
                sym,
                period="1y",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            hit = analyze_relative_strength(
                stock,
                benchmark,
                symbol=sym,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                min_price_usd=min_price_usd,
                min_avg_volume_20d=min_avg_volume_20d,
            )
            if hit:
                hits.append(hit)
        except Exception as ex:
            logging.debug("Relative-strength scan failed %s: %s", sym, ex)
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
        "sources_used": 2,
        "sources_list": ["daily_ohlcv", "SPY"],
        "source_scores": {signal.strategy_id: round(signal.native_score, 2)},
    }

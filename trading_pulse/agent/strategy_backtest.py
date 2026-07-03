"""Historical backtest for the rule-based speculative/momentum strategy."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import yfinance as yf

from trading_pulse.agent.signal_sources import _extract_series, _ohlcv_metrics, score_momentum, score_speculative


def _simulate_long_day(
    o: float,
    h: float,
    l: float,
    c: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> tuple[float, str, float]:
    stop_price = o * (1 - stop_loss_pct)
    take_price = o * (1 + take_profit_pct)
    if l <= stop_price:
        exit_price, exit_reason = stop_price, "stop_loss"
    elif h >= take_price:
        exit_price, exit_reason = take_price, "take_profit"
    else:
        exit_price, exit_reason = c, "close"
    pnl_pct = (exit_price / o) - 1 if o > 0 else 0.0
    return exit_price, exit_reason, pnl_pct


def _qualifies_speculative(metrics: dict[str, Any], min_volume_ratio: float) -> bool:
    volume_ok = bool(metrics.get("volume_ok"))
    breakout_ok = bool(metrics.get("breakout_ok"))
    volatile_ok = float(metrics.get("atr_pct") or 0.0) >= 3.0
    return volume_ok or breakout_ok or volatile_ok


def _qualifies_momentum(metrics: dict[str, Any], min_volume_ratio: float) -> bool:
    vol_ratio = float(metrics.get("vol_ratio") or 0.0)
    momentum_ok = bool(metrics.get("momentum_ok"))
    volume_ok = vol_ratio >= min_volume_ratio
    return momentum_ok or volume_ok


def backtest_symbol(
    symbol: str,
    *,
    stop_loss_pct: float,
    take_profit_pct: float,
    lookback_days: int = 90,
    speculative: bool = True,
    min_volume_ratio: float = 1.0,
    min_price_usd: float = 5.0,
    min_avg_volume_20d: float = 500_000,
    max_trades_per_day: int = 2,
) -> dict[str, Any]:
    period = f"{max(lookback_days + 40, 120)}d"
    df = yf.download(
        symbol,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df.empty or len(df) < 30:
        return _empty_backtest(lookback_days, note="insufficient_data")

    df = df.dropna()
    if len(df) < 30:
        return _empty_backtest(lookback_days, note="insufficient_data")

    cutoff = max(25, len(df) - lookback_days - 1)
    trades: list[dict[str, Any]] = []

    for idx in range(cutoff, len(df) - 1):
        history = df.iloc[: idx + 1]
        metrics = _ohlcv_metrics(history)
        if metrics is None:
            continue

        close = float(metrics["close"])
        avg_vol20 = float(metrics.get("avg_vol20") or 0.0)
        if close < min_price_usd or avg_vol20 < min_avg_volume_20d:
            continue

        if speculative:
            if not _qualifies_speculative(metrics, min_volume_ratio):
                continue
            signal_score = score_speculative(metrics)
        else:
            if not _qualifies_momentum(metrics, min_volume_ratio):
                continue
            signal_score = score_momentum(metrics)

        # Approximate plan selection: only count days the signal score is strong enough
        # to land in the top picks bucket (same max_trades_per_day as live plans).
        min_pick_score = 6.0 if speculative else 3.0
        if signal_score < min_pick_score:
            continue

        next_slice = df.iloc[idx + 1 : idx + 2]
        o = float(_extract_series(next_slice, "Open").iloc[0])
        h = float(_extract_series(next_slice, "High").iloc[0])
        l = float(_extract_series(next_slice, "Low").iloc[0])
        c = float(_extract_series(next_slice, "Close").iloc[0])
        _, exit_reason, pnl_pct = _simulate_long_day(o, h, l, c, stop_loss_pct, take_profit_pct)

        day_str = df.index[idx + 1]
        day_label = day_str.date().isoformat() if hasattr(day_str, "date") else str(day_str)[:10]
        trades.append(
            {
                "day": day_label,
                "pnl_pct": round(pnl_pct * 100, 3),
                "exit_reason": exit_reason,
                "signal_score": round(signal_score, 2),
                "win": pnl_pct > 0,
            }
        )

    if not trades:
        return _empty_backtest(lookback_days, note="no_signals")

    wins = sum(1 for t in trades if t["win"])
    losses = len(trades) - wins
    avg_pnl = sum(t["pnl_pct"] for t in trades) / len(trades)
    total_pnl = sum(t["pnl_pct"] for t in trades)
    win_rate = (wins / len(trades)) * 100

    summary = (
        f"{lookback_days} יום: {len(trades)} עסקאות, "
        f"{win_rate:.0f}% win, ממוצע {avg_pnl:+.1f}%"
    )
    logging.info("Backtest %s: %s", symbol, summary)

    return {
        "lookback_days": lookback_days,
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 1),
        "avg_pnl_pct": round(avg_pnl, 2),
        "total_pnl_pct": round(total_pnl, 2),
        "summary": summary,
        "note": None,
    }


def _empty_backtest(lookback_days: int, note: str) -> dict[str, Any]:
    return {
        "lookback_days": lookback_days,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": 0.0,
        "avg_pnl_pct": 0.0,
        "total_pnl_pct": 0.0,
        "summary": f"{lookback_days} יום: אין מספיק נתונים",
        "note": note,
    }

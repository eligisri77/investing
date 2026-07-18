"""Historical backtest for the rule-based speculative/momentum strategy."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Callable
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


SignalFunction = Callable[[str, pd.DataFrame], dict[str, Any] | None]


def score_signal_from_history(
    symbol: str,
    history: pd.DataFrame,
    *,
    speculative: bool = True,
    min_score: float | None = None,
) -> dict[str, Any] | None:
    """Default no-lookahead score signal for portfolio walk-forward tests."""
    metrics = _ohlcv_metrics(history)
    if metrics is None:
        return None
    score = score_speculative(metrics) if speculative else score_momentum(metrics)
    threshold = min_score if min_score is not None else (6.0 if speculative else 3.0)
    if score < threshold:
        return None
    if speculative and not _qualifies_speculative(metrics, 1.0):
        return None
    if not speculative and not _qualifies_momentum(metrics, 1.0):
        return None
    return {
        "symbol": symbol,
        "score": float(score),
        "strategy_id": "score_momentum",
    }


def walk_forward_portfolio(
    frames: dict[str, pd.DataFrame],
    signal_fn: SignalFunction,
    *,
    initial_capital: float = 10_000.0,
    max_open_positions: int = 4,
    max_trades_per_day: int = 2,
    stop_loss_pct: float = 0.08,
    take_profit_pct: float = 0.16,
    max_hold_days: int = 5,
    commission_per_side_usd: float = 1.0,
) -> dict[str, Any]:
    """Portfolio walk-forward simulation using only data known at each close.

    Signals are computed at day D close and filled at day D+1 open. Existing
    positions are evaluated before new entries. If stop and target both touch
    in one daily bar, stop wins (pessimistic and deterministic).
    """
    prepared: dict[str, pd.DataFrame] = {}
    for symbol, raw in frames.items():
        if raw is None or raw.empty:
            continue
        df = raw.copy().sort_index()
        if {"Open", "High", "Low", "Close"}.issubset(df.columns):
            prepared[str(symbol).upper()] = df
    all_days = sorted({day for df in prepared.values() for day in df.index})
    if len(all_days) < 2:
        return _empty_portfolio_backtest(initial_capital, "insufficient_data")

    cash = float(initial_capital)
    positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    exposure_days = 0
    strategy_pnl: dict[str, float] = defaultdict(float)

    def close_position(symbol: str, exit_price: float, reason: str, day: Any) -> None:
        nonlocal cash
        pos = positions.pop(symbol)
        shares = float(pos["shares"])
        proceeds = shares * exit_price
        gross = proceeds - float(pos["capital_usd"])
        fees = float(commission_per_side_usd)
        pnl = gross - fees
        cash += proceeds - fees
        trade = {
            "symbol": symbol,
            "strategy_id": pos["strategy_id"],
            "entry_day": str(pos["entry_day"])[:10],
            "exit_day": str(day)[:10],
            "entry_price": round(float(pos["entry_price"]), 4),
            "exit_price": round(float(exit_price), 4),
            "capital_usd": round(float(pos["capital_usd"]), 2),
            "pnl_usd": round(pnl, 2),
            "pnl_pct": round((pnl / float(pos["capital_usd"])) * 100, 3),
            "exit_reason": reason,
            "days_held": int(pos["days_held"]),
        }
        trades.append(trade)
        strategy_pnl[pos["strategy_id"]] += pnl

    for day_idx, day in enumerate(all_days):
        # 1) Manage positions using today's complete bar.
        for symbol in list(positions):
            df = prepared[symbol]
            if day not in df.index:
                continue
            row = df.loc[day]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            pos = positions[symbol]
            pos["days_held"] += 1
            stop = float(pos["stop_price"])
            target = float(pos["target_price"])
            low, high = float(row["Low"]), float(row["High"])
            if low <= stop:
                close_position(symbol, stop, "stop_loss", day)
            elif high >= target:
                close_position(symbol, target, "take_profit", day)
            elif int(pos["days_held"]) >= max_hold_days:
                close_position(symbol, float(row["Close"]), "max_hold_days", day)

        # 2) Fill signals created yesterday at today's open.
        todays = pending
        pending = []
        free_slots = max(0, int(max_open_positions) - len(positions))
        todays = [
            sig
            for sig in todays
            if sig["symbol"] not in positions
            and sig["symbol"] in prepared
            and day in prepared[sig["symbol"]].index
        ][: min(free_slots, int(max_trades_per_day))]
        if todays:
            budget_each = cash / len(todays)
            for sig in todays:
                symbol = sig["symbol"]
                row = prepared[symbol].loc[day]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[-1]
                entry = float(row["Open"])
                fee = float(commission_per_side_usd)
                capital = max(0.0, min(budget_each, cash) - fee)
                if entry <= 0 or capital <= 0:
                    continue
                shares = capital / entry
                cash -= capital + fee
                positions[symbol] = {
                    "symbol": symbol,
                    "strategy_id": str(sig.get("strategy_id") or "unknown"),
                    "entry_day": day,
                    "entry_price": entry,
                    "capital_usd": capital,
                    "shares": shares,
                    "stop_price": entry * (1 - stop_loss_pct),
                    "target_price": entry * (1 + take_profit_pct),
                    "days_held": 0,
                }
                # Entry-day intraday range is known only after that day closes.
                # Apply the same pessimistic stop-before-target convention.
                low, high = float(row["Low"]), float(row["High"])
                if low <= float(positions[symbol]["stop_price"]):
                    close_position(
                        symbol,
                        float(positions[symbol]["stop_price"]),
                        "stop_loss",
                        day,
                    )
                elif high >= float(positions[symbol]["target_price"]):
                    close_position(
                        symbol,
                        float(positions[symbol]["target_price"]),
                        "take_profit",
                        day,
                    )

        # 3) Produce signals using history through today's close.
        if day_idx < len(all_days) - 1:
            candidates: list[dict[str, Any]] = []
            for symbol, df in prepared.items():
                if symbol in positions or day not in df.index:
                    continue
                history = df.loc[:day]
                signal = signal_fn(symbol, history)
                if signal:
                    candidates.append({"symbol": symbol, **signal})
            candidates.sort(key=lambda s: float(s.get("score") or 0), reverse=True)
            pending = candidates[: int(max_trades_per_day)]

        marked = cash
        if positions:
            exposure_days += 1
        for symbol, pos in positions.items():
            df = prepared[symbol]
            if day in df.index:
                row = df.loc[day]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[-1]
                marked += float(pos["shares"]) * float(row["Close"])
            else:
                marked += float(pos["capital_usd"])
        equity_curve.append({"day": str(day)[:10], "equity": round(marked, 2)})

    # Liquidate remaining positions on their last known close.
    final_day = all_days[-1]
    for symbol in list(positions):
        df = prepared[symbol]
        row = df.iloc[-1]
        close_position(symbol, float(row["Close"]), "end_of_backtest", final_day)
    final_equity = cash
    if equity_curve:
        equity_curve[-1]["equity"] = round(final_equity, 2)
    return _portfolio_metrics(
        initial_capital=float(initial_capital),
        final_equity=final_equity,
        trades=trades,
        equity_curve=equity_curve,
        exposure_days=exposure_days,
        total_days=len(all_days),
        strategy_pnl=dict(strategy_pnl),
    )


def _portfolio_metrics(
    *,
    initial_capital: float,
    final_equity: float,
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    exposure_days: int,
    total_days: int,
    strategy_pnl: dict[str, float],
) -> dict[str, Any]:
    wins = [t for t in trades if float(t["pnl_usd"]) > 0]
    losses = [t for t in trades if float(t["pnl_usd"]) <= 0]
    gross_profit = sum(float(t["pnl_usd"]) for t in wins)
    gross_loss = abs(sum(float(t["pnl_usd"]) for t in losses))
    peak = float(initial_capital)
    max_drawdown = 0.0
    monthly: dict[str, list[float]] = defaultdict(list)
    for point in equity_curve:
        eq = float(point["equity"])
        peak = max(peak, eq)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - eq) / peak * 100)
        monthly[str(point["day"])[:7]].append(eq)
    positive_months = 0
    evaluated_months = 0
    for values in monthly.values():
        if len(values) >= 2:
            evaluated_months += 1
            positive_months += int(values[-1] > values[0])
    stability = (
        positive_months / evaluated_months * 100 if evaluated_months else 0.0
    )
    return {
        "initial_capital": round(initial_capital, 2),
        "final_equity": round(final_equity, 2),
        "return_pct": round(
            ((final_equity / initial_capital) - 1) * 100
            if initial_capital > 0
            else 0.0,
            2,
        ),
        "max_drawdown_pct": round(max_drawdown, 2),
        "trades": trades,
        "trade_count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1)
        if trades
        else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 2)
        if gross_loss > 0
        else (math.inf if gross_profit > 0 else 0.0),
        "exposure_pct": round(exposure_days / max(total_days, 1) * 100, 1),
        "monthly_stability_pct": round(stability, 1),
        "strategy_pnl_usd": {
            key: round(value, 2) for key, value in strategy_pnl.items()
        },
        "equity_curve": equity_curve,
        "note": None,
    }


def _empty_portfolio_backtest(initial_capital: float, note: str) -> dict[str, Any]:
    return {
        "initial_capital": float(initial_capital),
        "final_equity": float(initial_capital),
        "return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "trades": [],
        "trade_count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": 0.0,
        "profit_factor": 0.0,
        "exposure_pct": 0.0,
        "monthly_stability_pct": 0.0,
        "strategy_pnl_usd": {},
        "equity_curve": [],
        "note": note,
    }

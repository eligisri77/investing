"""Multi-day position tracking and swing-trading simulation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf


def ensure_open_positions(state: dict[str, Any]) -> None:
    if "open_positions" not in state:
        state["open_positions"] = []


def deployed_capital(state: dict[str, Any]) -> float:
    ensure_open_positions(state)
    return round(sum(float(p.get("capital_usd", 0)) for p in state["open_positions"]), 2)


def held_symbols(state: dict[str, Any]) -> set[str]:
    ensure_open_positions(state)
    return {str(p["symbol"]) for p in state["open_positions"]}


def available_capital(cfg: Any, state: dict[str, Any]) -> float:
    return max(0.0, round(float(state.get("equity", 0)) - deployed_capital(state), 2))


def fetch_day_ohlc(symbol: str, trading_day: date) -> dict[str, float] | None:
    day_df = yf.download(
        symbol,
        start=trading_day.isoformat(),
        end=(trading_day + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    ).dropna()
    if day_df.empty:
        return None

    def col(name: str) -> pd.Series:
        series = day_df[name]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        return series

    return {
        "open": float(col("Open").iloc[0]),
        "high": float(col("High").iloc[0]),
        "low": float(col("Low").iloc[0]),
        "close": float(col("Close").iloc[0]),
    }


def _stop_take(entry: float, pos: dict[str, Any], cfg: Any) -> tuple[float, float]:
    sl_pct = float(pos.get("stop_loss_pct", getattr(cfg, "stop_loss_pct", 0.12)))
    tp_pct = float(pos.get("take_profit_pct", getattr(cfg, "take_profit_pct", 0.25)))
    floor = position_floor_price(pos, cfg, entry=entry)
    return floor, entry * (1 + tp_pct)


def rec_floor_price(rec: dict[str, Any], entry_price: float | None = None, cfg: Any = None) -> float:
    """Hard floor — sell automatically if price drops below."""
    if rec.get("floor_price") is not None:
        return round(float(rec["floor_price"]), 4)
    if rec.get("stop_loss_price") is not None:
        return round(float(rec["stop_loss_price"]), 4)
    entry = float(entry_price or rec.get("entry_ref_price") or rec.get("entry_price") or 0)
    sl_pct = float(rec.get("stop_loss_pct", getattr(cfg, "stop_loss_pct", 0.12) if cfg else 0.12))
    return round(entry * (1 - sl_pct), 4)


def position_floor_price(pos: dict[str, Any], cfg: Any, *, entry: float | None = None) -> float:
    if pos.get("floor_price") is not None:
        return round(float(pos["floor_price"]), 4)
    entry_px = float(entry if entry is not None else pos.get("entry_price") or pos.get("entry_ref_price") or 0)
    return rec_floor_price(pos, entry_px, cfg)


def evaluate_intraday_exit(
    pos: dict[str, Any],
    bar: dict[str, float],
    cfg: Any,
) -> tuple[float, str] | None:
    entry = float(pos["entry_price"])
    stop_price, take_price = _stop_take(entry, pos, cfg)
    low = bar["low"]
    high = bar["high"]
    close = bar["close"]

    if low <= stop_price:
        return stop_price, "floor_price"
    if high >= take_price:
        return take_price, "take_profit"

    days_held = int(pos.get("days_held", 0))
    max_days = int(getattr(cfg, "max_hold_days", 5))
    if days_held >= max_days:
        return close, "max_hold_days"

    if getattr(cfg, "hold_mode", "swing") == "day":
        return close, "close"

    return None


def trade_from_close(pos: dict[str, Any], exit_price: float, exit_reason: str) -> dict[str, Any]:
    entry = float(pos["entry_price"])
    capital = float(pos["capital_usd"])
    pnl_pct = (exit_price / entry) - 1
    return {
        "symbol": pos["symbol"],
        "entry_price": round(entry, 4),
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "capital_usd": round(capital, 2),
        "pnl_pct": round(pnl_pct * 100, 3),
        "pnl_usd": round(capital * pnl_pct, 2),
        "days_held": int(pos.get("days_held", 0)),
        "entry_day": pos.get("entry_day"),
    }


def new_position_from_rec(rec: dict[str, Any], entry_price: float, trading_day: str) -> dict[str, Any]:
    floor = rec_floor_price(rec, entry_price)
    return {
        "symbol": rec["symbol"],
        "entry_day": trading_day,
        "entry_price": round(entry_price, 4),
        "capital_usd": round(float(rec["capital_usd"]), 2),
        "stop_loss_pct": float(rec.get("stop_loss_pct", 0.12)),
        "take_profit_pct": float(rec.get("take_profit_pct", 0.25)),
        "floor_price": floor,
        "stop_loss_price": floor,
        "days_held": 0,
    }


def backfill_position_floors(state: dict[str, Any], cfg: Any) -> None:
    """Ensure legacy open positions have an explicit floor price."""
    ensure_open_positions(state)
    for pos in state.get("open_positions", []):
        if pos.get("floor_price") is None:
            entry = float(pos.get("entry_price", 0))
            floor = position_floor_price(pos, cfg, entry=entry)
            pos["floor_price"] = floor
            pos["stop_loss_price"] = floor


def close_position_at_price(
    cfg: Any,
    state: dict[str, Any],
    pos: dict[str, Any],
    exit_price: float,
    reason: str,
    *,
    trading_day: str | None = None,
) -> dict[str, Any]:
    """Close one open position, update equity, record intraday exit."""
    from datetime import date, datetime, timezone

    ensure_open_positions(state)
    symbol = str(pos["symbol"])
    state["open_positions"] = [p for p in state["open_positions"] if str(p["symbol"]) != symbol]

    trade = trade_from_close(pos, exit_price, reason)
    commission = float(getattr(cfg, "commission_per_side_usd", 0.0))
    if commission > 0:
        trade["fees_usd"] = round(commission, 2)
        trade["pnl_usd"] = round(trade["pnl_usd"] - commission, 2)
    else:
        trade["fees_usd"] = 0.0

    state["equity"] = round(float(state.get("equity", 0)) + float(trade["pnl_usd"]), 2)
    day_str = trading_day or date.today().isoformat()
    record = {
        **trade,
        "trading_day": day_str,
        "floor_price": position_floor_price(pos, cfg),
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }
    state.setdefault("intraday_floor_exits", []).append(record)
    try:
        from trading_pulse.agent.symbol_cooldown import maybe_record_loss_cooldown

        maybe_record_loss_cooldown(state, trade, cfg, as_of=date.fromisoformat(day_str))
    except ImportError:
        pass
    return record


def floor_closed_today(state: dict[str, Any], symbol: str, trading_day: str) -> bool:
    for row in state.get("intraday_floor_exits") or []:
        if row.get("symbol") == symbol and row.get("trading_day") == trading_day:
            return True
    return False


def _record_loss_cooldown_if_needed(
    state: dict[str, Any],
    trade: dict[str, Any],
    cfg: Any,
    trading_day: date,
) -> None:
    try:
        from trading_pulse.agent.symbol_cooldown import maybe_record_loss_cooldown

        maybe_record_loss_cooldown(state, trade, cfg, as_of=trading_day)
    except ImportError:
        pass


def simulate_swing_day(
    cfg: Any,
    state: dict[str, Any],
    trading_day: date,
    approved: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float, float]:
    """Process one trading day. Returns (executed_trades, held_eod, pnl_total, fees_total)."""
    ensure_open_positions(state)
    commission = float(getattr(cfg, "commission_per_side_usd", 0.0))
    day_str = trading_day.isoformat()

    executed: list[dict[str, Any]] = []
    still_open: list[dict[str, Any]] = []
    pnl_total = 0.0
    fees_total = 0.0

    for pos in list(state.get("open_positions", [])):
        pos = dict(pos)
        pos["days_held"] = int(pos.get("days_held", 0)) + 1
        bar = fetch_day_ohlc(str(pos["symbol"]), trading_day)
        if bar is None:
            still_open.append(pos)
            continue

        exit_info = evaluate_intraday_exit(pos, bar, cfg)
        if exit_info:
            exit_price, reason = exit_info
            trade = trade_from_close(pos, exit_price, reason)
            trade["fees_usd"] = round(commission, 2)
            trade["pnl_usd"] = round(trade["pnl_usd"] - commission, 2)
            pnl_total += trade["pnl_usd"]
            fees_total += commission
            executed.append(trade)
            _record_loss_cooldown_if_needed(state, trade, cfg, trading_day)
        else:
            still_open.append(pos)

    held_symbols_today = {p["symbol"] for p in still_open}
    equity_before = float(state["equity"])
    daily_loss_limit = equity_before * float(cfg.max_daily_loss_pct)

    for rec in approved:
        symbol = str(rec["symbol"])
        if symbol in held_symbols_today:
            continue
        if len(still_open) >= int(getattr(cfg, "max_open_positions", 4)):
            break
        if pnl_total <= -daily_loss_limit:
            break

        bar = fetch_day_ohlc(symbol, trading_day)
        if bar is None:
            continue

        pos = new_position_from_rec(rec, bar["open"], day_str)
        exit_info = evaluate_intraday_exit(pos, bar, cfg)

        if exit_info and getattr(cfg, "hold_mode", "swing") == "day":
            exit_price, reason = exit_info
            trade = trade_from_close(pos, exit_price, reason)
            entry_fee = commission
            exit_fee = commission
            trade["fees_usd"] = round(entry_fee + exit_fee, 2)
            trade["pnl_usd"] = round(trade["pnl_usd"] - entry_fee - exit_fee, 2)
            pnl_total += trade["pnl_usd"]
            fees_total += entry_fee + exit_fee
            executed.append(trade)
            _record_loss_cooldown_if_needed(state, trade, cfg, trading_day)
            continue

        if exit_info and exit_info[1] in {"stop_loss", "take_profit", "floor_price"}:
            exit_price, reason = exit_info
            trade = trade_from_close(pos, exit_price, reason)
            trade["fees_usd"] = round(commission * 2, 2)
            trade["pnl_usd"] = round(trade["pnl_usd"] - commission * 2, 2)
            pnl_total += trade["pnl_usd"]
            fees_total += commission * 2
            executed.append(trade)
            _record_loss_cooldown_if_needed(state, trade, cfg, trading_day)
            continue

        pos["days_held"] = 0
        still_open.append(pos)
        held_symbols_today.add(symbol)
        if commission > 0:
            pnl_total -= commission
            fees_total += commission

    state["open_positions"] = still_open
    return executed, still_open, round(pnl_total, 2), round(fees_total, 2)


def holdings_snapshot(state: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_open_positions(state)
    rows: list[dict[str, Any]] = []
    for pos in state.get("open_positions", []):
        rows.append(
            {
                "symbol": pos["symbol"],
                "capital_usd": float(pos.get("capital_usd", 0)),
                "entry_day": pos.get("entry_day"),
                "entry_price": float(pos.get("entry_price", 0)),
                "floor_price": float(pos.get("floor_price", 0)) or None,
                "days_held": int(pos.get("days_held", 0)),
                "status": "holding",
            }
        )
    return rows


def format_holdings_lines(holdings: list[dict[str, Any]], *, html: bool = False) -> list[str]:
    if not holdings:
        return []
    lines = ["", "📂 מחזיקים כרגע (לא נמכרים אוטומטית):"]
    for h in holdings:
        text = (
            f"  {h['symbol']} · ${h['capital_usd']:.0f} · מ-{h['entry_day']} · "
            f"{h['days_held']} ימים"
        )
        lines.append(text)
    return lines

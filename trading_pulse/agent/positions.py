"""Multi-day position tracking and swing-trading simulation."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pandas as pd
import yfinance as yf


def ensure_open_positions(state: dict[str, Any]) -> None:
    if "open_positions" not in state:
        state["open_positions"] = []
    for pos in state["open_positions"]:
        ensure_position_lots(pos)


def deployed_capital(state: dict[str, Any]) -> float:
    ensure_open_positions(state)
    return round(sum(float(p.get("capital_usd", 0)) for p in state["open_positions"]), 2)


def held_symbols(state: dict[str, Any]) -> set[str]:
    ensure_open_positions(state)
    return {str(p["symbol"]) for p in state["open_positions"]}


def available_capital(cfg: Any, state: dict[str, Any]) -> float:
    return max(0.0, round(float(state.get("equity", 0)) - deployed_capital(state), 2))


def free_cash(state: dict[str, Any], cfg: Any | None = None) -> float:
    """Undeployed cash (alias used by sell/swap replies)."""
    if cfg is not None:
        return available_capital(cfg, state)
    return max(0.0, round(float(state.get("equity", 0)) - deployed_capital(state), 2))


def cash_free_among_positions(equity: float, positions: list[dict[str, Any]]) -> float:
    """Free cash given equity and a candidate open-positions list."""
    deployed = round(sum(float(p.get("capital_usd") or 0) for p in positions), 2)
    return max(0.0, round(float(equity) - deployed, 2))


def unreserved_free_cash(
    state: dict[str, Any],
    plan: dict[str, Any] | None,
    cfg: Any | None = None,
    *,
    exclude_symbol: str | None = None,
) -> float:
    """Live free cash minus capital already approved but not yet filled.

    Prevents a second approve/swap from claiming the same dollars twice before open.
    """
    cash = free_cash(state, cfg)
    if not plan:
        return cash
    held = held_symbols(state)
    exclude = str(exclude_symbol or "").upper()
    reserved = 0.0
    for rec in plan.get("recommendations") or []:
        if not rec.get("approved"):
            continue
        sym = str(rec.get("symbol") or "").upper()
        if not sym or sym == exclude or sym in held:
            continue
        # Method2 already filled / invalidated / expired should not reserve.
        status = str(rec.get("method2_status") or "")
        if status in {"filled", "invalidated", "expired"}:
            continue
        reserved += float(rec.get("capital_usd") or 0)
    return max(0.0, round(cash - reserved, 2))


def clamp_buy_capital(wanted_usd: float, cash_left: float) -> float:
    """Capital we can actually deploy right now (swap/sell funding still OK via cash)."""
    return round(max(0.0, min(float(wanted_usd or 0), float(cash_left or 0))), 2)


# Allow tiny float/cent drift; anything larger is a real book bug (e.g. double buy).
BOOK_INVARIANT_EPS_USD = 0.05


def book_deployed_vs_equity(state: dict[str, Any]) -> tuple[float, float, float]:
    """Return (equity, deployed, overdeploy_usd). overdeploy > 0 means broken book."""
    ensure_open_positions(state)
    equity = round(float(state.get("equity") or 0), 2)
    deployed = deployed_capital(state)
    over = round(max(0.0, deployed - equity - BOOK_INVARIANT_EPS_USD), 2)
    return equity, deployed, over


def book_invariant_ok(state: dict[str, Any]) -> bool:
    """True when invested capital does not exceed book equity (within cents)."""
    _eq, _dep, over = book_deployed_vs_equity(state)
    return over <= 0


def assert_book_invariant(state: dict[str, Any], *, context: str = "") -> None:
    """Raise if open capital exceeds equity — used by tests and hard guards."""
    equity, deployed, over = book_deployed_vs_equity(state)
    if over > 0:
        where = f" ({context})" if context else ""
        raise AssertionError(
            f"book invariant broken{where}: equity=${equity:.2f} "
            f"deployed=${deployed:.2f} over=${over:.2f}"
        )


def log_book_invariant(state: dict[str, Any], *, context: str = "") -> bool:
    """Log a critical error if the book is over-deployed. Returns True if OK."""
    equity, deployed, over = book_deployed_vs_equity(state)
    if over <= 0:
        return True
    where = f" ({context})" if context else ""
    logging.error(
        "BOOK INVARIANT BROKEN%s: equity=$%.2f deployed=$%.2f over=$%.2f positions=%s",
        where,
        equity,
        deployed,
        over,
        [(p.get("symbol"), p.get("capital_usd")) for p in state.get("open_positions") or []],
    )
    return False


def _new_lot(
    capital_usd: float,
    entry_price: float,
    entry_day: str,
    *,
    entry_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid4().hex[:12],
        "capital_usd": round(float(capital_usd), 2),
        "entry_price": round(float(entry_price), 4),
        "entry_day": str(entry_day),
        "entry_at": entry_at or datetime.now(timezone.utc).isoformat(),
    }


def ensure_position_lots(pos: dict[str, Any]) -> list[dict[str, Any]]:
    """Migrate legacy single-entry positions to lot list; keep aggregates in sync."""
    lots = pos.get("lots")
    if isinstance(lots, list) and lots:
        sync_position_from_lots(pos)
        return list(pos["lots"])
    capital = round(float(pos.get("capital_usd") or 0), 2)
    entry = float(pos.get("entry_price") or pos.get("entry_ref_price") or 0)
    day = str(pos.get("entry_day") or date.today().isoformat())
    entry_at = pos.get("entry_at")
    if capital > 0 and entry > 0:
        pos["lots"] = [
            _new_lot(capital, entry, day, entry_at=str(entry_at) if entry_at else None)
        ]
    else:
        pos["lots"] = []
    sync_position_from_lots(pos)
    return list(pos["lots"])


def sync_position_from_lots(pos: dict[str, Any]) -> None:
    """Refresh capital_usd / entry_price (weighted avg) / entry_day from lots."""
    lots = [dict(x) for x in (pos.get("lots") or []) if float(x.get("capital_usd") or 0) > 0]
    pos["lots"] = lots
    if not lots:
        pos["capital_usd"] = 0.0
        return
    total_cap = round(sum(float(x["capital_usd"]) for x in lots), 2)
    weighted = sum(float(x["capital_usd"]) * float(x["entry_price"]) for x in lots)
    pos["capital_usd"] = total_cap
    pos["entry_price"] = round(weighted / total_cap, 4) if total_cap > 0 else float(lots[0]["entry_price"])
    # Oldest lot defines position age / days_held baseline.
    oldest = min(lots, key=lambda x: (str(x.get("entry_day") or ""), str(x.get("entry_at") or "")))
    pos["entry_day"] = oldest.get("entry_day") or pos.get("entry_day")
    if oldest.get("entry_at"):
        pos["entry_at"] = oldest["entry_at"]


def add_lot_to_position(
    pos: dict[str, Any],
    capital_usd: float,
    entry_price: float,
    entry_day: str,
    *,
    entry_at: str | None = None,
) -> dict[str, Any]:
    """Append a purchase tranche (separate cost basis for PnL)."""
    ensure_position_lots(pos)
    capital_usd = round(float(capital_usd), 2)
    entry_price = float(entry_price)
    if capital_usd < 1 or entry_price <= 0:
        return pos
    pos.setdefault("lots", []).append(
        _new_lot(capital_usd, entry_price, entry_day, entry_at=entry_at)
    )
    sync_position_from_lots(pos)
    return pos


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
    tp_pct = float(pos.get("take_profit_pct", getattr(cfg, "take_profit_pct", 0.25)))
    floor = position_floor_price(pos, cfg, entry=entry)
    side = str(pos.get("side") or "LONG").upper()
    if side == "SHORT":
        take = float(pos.get("take_profit_price") or entry * (1 - tp_pct))
        return floor, take
    take = float(pos.get("take_profit_price") or entry * (1 + tp_pct))
    return floor, take


def rec_floor_price(rec: dict[str, Any], entry_price: float | None = None, cfg: Any = None) -> float:
    """Hard floor — sell automatically if price drops below (long) / rises above (short)."""
    if rec.get("floor_price") is not None:
        return round(float(rec["floor_price"]), 4)
    if rec.get("stop_loss_price") is not None:
        return round(float(rec["stop_loss_price"]), 4)
    entry = float(entry_price or rec.get("entry_ref_price") or rec.get("entry_price") or 0)
    sl_pct = float(rec.get("stop_loss_pct", getattr(cfg, "stop_loss_pct", 0.12) if cfg else 0.12))
    side = str(rec.get("side") or "LONG").upper()
    if side == "SHORT":
        return round(entry * (1 + sl_pct), 4)
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
    side = str(pos.get("side") or "LONG").upper()

    if side == "SHORT":
        if high >= stop_price:
            return stop_price, "floor_price"
        if low <= take_price:
            return take_price, "take_profit"
    else:
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


def _pnl_pct(entry: float, exit_price: float, side: str = "LONG") -> float:
    if entry <= 0:
        return 0.0
    if str(side).upper() == "SHORT":
        return (entry - exit_price) / entry
    return (exit_price / entry) - 1


def unrealized_pnl_for_position(
    pos: dict[str, Any],
    *,
    mark_price: float | None = None,
    trading_day: date | None = None,
) -> dict[str, Any]:
    """Mark open position; PnL is summed per purchase lot (separate cost bases)."""
    enriched = dict(pos)
    ensure_position_lots(enriched)
    side = str(enriched.get("side") or "LONG")
    mark = mark_price
    if mark is None and trading_day is not None:
        bar = fetch_day_ohlc(str(enriched["symbol"]), trading_day)
        mark = float(bar["close"]) if bar else None

    lots = list(enriched.get("lots") or [])
    capital = float(enriched.get("capital_usd") or 0)
    if mark is None or mark <= 0 or not lots:
        # Fallback: single-entry math if lots empty but capital exists.
        entry = float(enriched.get("entry_price") or enriched.get("entry_ref_price") or 0)
        enriched["mark_price"] = None if mark is None else round(float(mark), 4)
        if mark is not None and entry > 0 and capital > 0:
            frac = _pnl_pct(entry, float(mark), side)
            enriched["unrealized_pnl_usd"] = round(capital * frac, 2)
            enriched["unrealized_pnl_pct"] = round(frac * 100, 2)
        else:
            enriched["unrealized_pnl_usd"] = 0.0
            enriched["unrealized_pnl_pct"] = 0.0
        return enriched

    pnl_total = 0.0
    marked_lots: list[dict[str, Any]] = []
    for lot in lots:
        cap = float(lot.get("capital_usd") or 0)
        entry = float(lot.get("entry_price") or 0)
        if cap <= 0 or entry <= 0:
            continue
        frac = _pnl_pct(entry, float(mark), side)
        lot_pnl = round(cap * frac, 2)
        pnl_total += lot_pnl
        marked_lots.append(
            {
                **lot,
                "mark_price": round(float(mark), 4),
                "unrealized_pnl_usd": lot_pnl,
                "unrealized_pnl_pct": round(frac * 100, 2),
            }
        )

    enriched["lots"] = marked_lots
    enriched["mark_price"] = round(float(mark), 4)
    enriched["unrealized_pnl_usd"] = round(pnl_total, 2)
    enriched["unrealized_pnl_pct"] = (
        round((pnl_total / capital) * 100, 2) if capital > 0 else 0.0
    )
    return enriched


def enrich_held_unrealized(
    positions: list[dict[str, Any]],
    trading_day: date,
) -> tuple[list[dict[str, Any]], float]:
    """Add unrealized P/L per held position; returns (enriched, total_usd)."""
    enriched: list[dict[str, Any]] = []
    total = 0.0
    for pos in positions:
        row = unrealized_pnl_for_position(pos, trading_day=trading_day)
        enriched.append(row)
        total += float(row.get("unrealized_pnl_usd", 0))
    return enriched, round(total, 2)


def trade_from_close(pos: dict[str, Any], exit_price: float, exit_reason: str) -> dict[str, Any]:
    """Realize PnL across lots (each tranche vs its own entry)."""
    ensure_position_lots(pos)
    side = str(pos.get("side") or "LONG")
    lots = list(pos.get("lots") or [])
    if not lots:
        entry = float(pos["entry_price"])
        capital = float(pos["capital_usd"])
        pnl_pct = _pnl_pct(entry, exit_price, side)
        pnl_usd = round(capital * pnl_pct, 2)
    else:
        capital = round(sum(float(x.get("capital_usd") or 0) for x in lots), 2)
        pnl_usd = 0.0
        weighted_entry = 0.0
        for lot in lots:
            cap = float(lot.get("capital_usd") or 0)
            entry = float(lot.get("entry_price") or 0)
            if cap <= 0 or entry <= 0:
                continue
            pnl_usd += cap * _pnl_pct(entry, exit_price, side)
            weighted_entry += cap * entry
        pnl_usd = round(pnl_usd, 2)
        entry = round(weighted_entry / capital, 4) if capital > 0 else float(pos.get("entry_price") or 0)
        pnl_pct = (pnl_usd / capital) if capital > 0 else 0.0

    return {
        "symbol": pos["symbol"],
        "side": side,
        "entry_price": round(entry, 4),
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "capital_usd": round(capital, 2),
        "pnl_pct": round(pnl_pct * 100, 3),
        "pnl_usd": pnl_usd,
        "days_held": int(pos.get("days_held", 0)),
        "entry_day": pos.get("entry_day"),
        "lots_closed": len(lots) if lots else 1,
        "strategy": pos.get("strategy"),
        "strategy_id": pos.get("strategy_id"),
        "strategy_version": pos.get("strategy_version"),
        "schema_version": pos.get("schema_version"),
        "signal_id": pos.get("signal_id"),
        "native_score": pos.get("native_score"),
        "confidence": pos.get("confidence"),
        "entry_policy": pos.get("entry_policy"),
        "contributing_strategies": list(
            pos.get("contributing_strategies") or []
        ),
        "trigger": pos.get("trigger"),
        "pattern_weak": pos.get("pattern_weak"),
    }


def new_position_from_rec(rec: dict[str, Any], entry_price: float, trading_day: str) -> dict[str, Any]:
    from datetime import datetime, timezone

    floor = rec_floor_price(rec, entry_price)
    side = str(rec.get("side") or "LONG").upper()
    tp = rec.get("take_profit_price")
    if tp is None:
        tp_pct = float(rec.get("take_profit_pct", 0.25))
        tp = entry_price * (1 - tp_pct) if side == "SHORT" else entry_price * (1 + tp_pct)
    capital = round(float(rec["capital_usd"]), 2)
    entry_at = datetime.now(timezone.utc).isoformat()
    pos = {
        "symbol": rec["symbol"],
        "side": side,
        "entry_day": trading_day,
        "entry_at": entry_at,
        "entry_price": round(entry_price, 4),
        "capital_usd": capital,
        "lots": [_new_lot(capital, entry_price, trading_day, entry_at=entry_at)],
        "stop_loss_pct": float(rec.get("stop_loss_pct", 0.12)),
        "take_profit_pct": float(rec.get("take_profit_pct", 0.25)),
        "take_profit_price": round(float(tp), 4),
        "floor_price": floor,
        "stop_loss_price": floor,
        "days_held": 0,
        "strategy": rec.get("strategy"),
        "strategy_id": rec.get("strategy_id"),
        "strategy_version": rec.get("strategy_version"),
        "schema_version": rec.get("schema_version"),
        "signal_id": rec.get("signal_id"),
        "native_score": rec.get("native_score"),
        "confidence": rec.get("confidence"),
        "entry_policy": rec.get("entry_policy"),
        "contributing_strategies": list(rec.get("contributing_strategies") or []),
        "trigger": rec.get("trigger"),
        "pattern_weak": rec.get("pattern_weak"),
        "sleeve": rec.get("sleeve"),
    }
    sync_position_from_lots(pos)
    return pos


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
    *,
    entries_only: bool = False,
    eod_only: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float, float]:
    """Process one trading day. Returns (executed_trades, held_eod, pnl_total, fees_total)."""
    ensure_open_positions(state)
    commission = float(getattr(cfg, "commission_per_side_usd", 0.0))
    day_str = trading_day.isoformat()

    executed: list[dict[str, Any]] = []
    still_open: list[dict[str, Any]] = []
    pnl_total = 0.0
    fees_total = 0.0

    if not entries_only:
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
    else:
        still_open = [dict(p) for p in state.get("open_positions", [])]

    if eod_only:
        state["open_positions"] = still_open
        return executed, still_open, round(pnl_total, 2), round(fees_total, 2)

    held_symbols_today = {p["symbol"] for p in still_open}
    equity_before = float(state["equity"])
    daily_loss_limit = equity_before * float(cfg.max_daily_loss_pct)
    cash_left = cash_free_among_positions(equity_before, still_open)

    for rec in approved:
        symbol = str(rec["symbol"])
        if symbol in held_symbols_today:
            continue
        if len(still_open) >= int(getattr(cfg, "max_open_positions", 4)):
            break
        if pnl_total <= -daily_loss_limit:
            break

        wanted = float(rec.get("capital_usd") or 0)
        capital = clamp_buy_capital(wanted, cash_left)
        if capital < 1:
            logging.info(
                "Skip entry %s: no free cash (wanted $%.2f, free $%.2f)",
                symbol,
                wanted,
                cash_left,
            )
            continue

        bar = fetch_day_ohlc(symbol, trading_day)
        if bar is None:
            # Method2 needs a real session bar to confirm breakout — never invent one.
            if str(rec.get("strategy") or "") == "method2" or bool(rec.get("sleeve")):
                logging.info(
                    "Method2 skip %s: no OHLC yet for %s (waiting for breakout bar)",
                    symbol,
                    day_str,
                )
                continue
            ref = rec.get("entry_ref_price")
            if ref is None:
                continue
            price = float(ref)
            bar = {"open": price, "high": price, "low": price, "close": price}

        entry_px = float(bar["open"])
        if str(rec.get("strategy") or "") == "method2" or bool(rec.get("sleeve")):
            from trading_pulse.agent.candle_method2 import resolve_method2_fill

            fill = resolve_method2_fill(rec, bar)
            if fill is None:
                logging.info(
                    "Method2 skip %s: breakout not triggered (entry=%s stop=%s O=%.2f H=%.2f L=%.2f)",
                    symbol,
                    rec.get("method2_entry_ref") or rec.get("entry_ref_price"),
                    rec.get("method2_stop_ref") or rec.get("floor_price"),
                    bar["open"],
                    bar["high"],
                    bar["low"],
                )
                continue
            entry_px = float(fill)

        rec_for_pos = dict(rec)
        rec_for_pos["capital_usd"] = capital
        pos = new_position_from_rec(rec_for_pos, entry_px, day_str)
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
            cash_left = round(cash_left - capital, 2)
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
            cash_left = round(cash_left - capital, 2)
            continue

        pos["days_held"] = 0
        still_open.append(pos)
        held_symbols_today.add(symbol)
        cash_left = round(cash_left - capital, 2)
        if commission > 0:
            pnl_total -= commission
            fees_total += commission

    state["open_positions"] = still_open
    # Hard stop for regressions like the Aug-2026 double-capital bug.
    if not log_book_invariant(state, context="simulate_swing_day"):
        equity = float(state.get("equity") or 0)
        repaired = list(still_open)
        while repaired:
            dep = round(sum(float(p.get("capital_usd") or 0) for p in repaired), 2)
            if dep <= equity + BOOK_INVARIANT_EPS_USD:
                break
            dropped = repaired.pop()
            logging.error(
                "Trimmed over-deploy entry %s $%.2f to restore book",
                dropped.get("symbol"),
                float(dropped.get("capital_usd") or 0),
            )
        state["open_positions"] = repaired
        still_open = repaired
        assert_book_invariant(state, context="simulate_swing_day.repaired")
    return executed, still_open, round(pnl_total, 2), round(fees_total, 2)


def partial_sell_position(
    cfg: Any,
    state: dict[str, Any],
    symbol: str,
    fraction: float,
    *,
    trading_day: date | None = None,
    reason: str = "user_sell",
) -> dict[str, Any] | None:
    """Sell fraction of an open position at latest close (dry-run).

    Realizes PnL FIFO across purchase lots (oldest tranche first).
    """
    ensure_open_positions(state)
    symbol = symbol.upper()
    fraction = max(0.01, min(1.0, float(fraction)))
    day = trading_day or date.today()
    commission = float(getattr(cfg, "commission_per_side_usd", 0.0))

    for i, pos in enumerate(state.get("open_positions", [])):
        if str(pos.get("symbol")) != symbol:
            continue
        pos = dict(pos)
        ensure_position_lots(pos)
        bar = fetch_day_ohlc(symbol, day)
        if bar is None:
            return None
        exit_price = float(bar["close"])
        total_cap = float(pos.get("capital_usd") or 0)
        if total_cap <= 0:
            return None
        sell_capital = round(total_cap * fraction, 2)
        if sell_capital < 1:
            return None

        side = str(pos.get("side") or "LONG")
        remaining_to_sell = sell_capital
        pnl_usd = 0.0
        weighted_entry = 0.0
        sold_cap = 0.0
        new_lots: list[dict[str, Any]] = []
        for lot in list(pos.get("lots") or []):
            lot_cap = float(lot.get("capital_usd") or 0)
            lot_entry = float(lot.get("entry_price") or 0)
            if lot_cap <= 0:
                continue
            if remaining_to_sell <= 0:
                new_lots.append(dict(lot))
                continue
            take = min(lot_cap, remaining_to_sell)
            take = round(take, 2)
            if take > 0 and lot_entry > 0:
                pnl_usd += take * _pnl_pct(lot_entry, exit_price, side)
                weighted_entry += take * lot_entry
                sold_cap += take
                remaining_to_sell = round(remaining_to_sell - take, 2)
            left = round(lot_cap - take, 2)
            if left >= 1:
                kept = dict(lot)
                kept["capital_usd"] = left
                new_lots.append(kept)

        sold_cap = round(sold_cap, 2)
        if sold_cap < 1:
            return None
        avg_entry = round(weighted_entry / sold_cap, 4) if sold_cap else float(pos.get("entry_price") or 0)
        pnl_usd = round(pnl_usd, 2)
        pnl_pct = (pnl_usd / sold_cap) if sold_cap else 0.0
        trade = {
            "symbol": symbol,
            "side": side,
            "entry_price": avg_entry,
            "exit_price": round(exit_price, 4),
            "exit_reason": reason,
            "capital_usd": sold_cap,
            "pnl_pct": round(pnl_pct * 100, 3),
            "pnl_usd": pnl_usd,
            "days_held": int(pos.get("days_held", 0)),
            "entry_day": pos.get("entry_day"),
            "strategy": pos.get("strategy"),
            "strategy_id": pos.get("strategy_id"),
            "strategy_version": pos.get("strategy_version"),
            "schema_version": pos.get("schema_version"),
            "signal_id": pos.get("signal_id"),
            "native_score": pos.get("native_score"),
            "confidence": pos.get("confidence"),
            "entry_policy": pos.get("entry_policy"),
            "contributing_strategies": list(pos.get("contributing_strategies") or []),
            "trigger": pos.get("trigger"),
            "pattern_weak": pos.get("pattern_weak"),
        }
        trade["fees_usd"] = round(commission, 2)
        trade["pnl_usd"] = round(trade["pnl_usd"] - commission, 2)
        state["equity"] = round(float(state.get("equity", 0)) + float(trade["pnl_usd"]), 2)

        remaining = round(sum(float(x.get("capital_usd") or 0) for x in new_lots), 2)
        if remaining < 1 or fraction >= 0.999:
            state["open_positions"].pop(i)
        else:
            pos["lots"] = new_lots
            sync_position_from_lots(pos)
            state["open_positions"][i] = pos
        record = {
            **trade,
            "exit_id": f"manual:{uuid4().hex[:12]}",
            "trading_day": day.isoformat(),
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "manual_exit": True,
        }
        state.setdefault("intraday_floor_exits", []).append(record)
        _record_loss_cooldown_if_needed(state, record, cfg, day)
        return record
    return None


def partial_sell_usd(
    cfg: Any,
    state: dict[str, Any],
    symbol: str,
    amount_usd: float,
    *,
    trading_day: date | None = None,
    reason: str = "user_sell",
) -> dict[str, Any] | None:
    """Sell a fixed USD amount from an open position."""
    ensure_open_positions(state)
    symbol = symbol.upper()
    amount_usd = max(1.0, float(amount_usd))
    for pos in state.get("open_positions", []):
        if str(pos.get("symbol")) != symbol:
            continue
        cap = float(pos.get("capital_usd", 0))
        if cap <= 0:
            return None
        fraction = min(1.0, amount_usd / cap)
        return partial_sell_position(
            cfg, state, symbol, fraction, trading_day=trading_day, reason=reason
        )
    return None


def holdings_snapshot(state: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_open_positions(state)
    entry_at_fallback = _plan_entry_executed_at()
    rows: list[dict[str, Any]] = []
    for pos in state.get("open_positions", []):
        rows.append(
            {
                "symbol": pos["symbol"],
                "capital_usd": float(pos.get("capital_usd", 0)),
                "entry_day": pos.get("entry_day"),
                "entry_at": pos.get("entry_at") or entry_at_fallback,
                "entry_price": float(pos.get("entry_price", 0)),
                "floor_price": float(pos.get("floor_price", 0)) or None,
                "days_held": int(pos.get("days_held", 0)),
                "status": "holding",
                "mark_price": float(pos["mark_price"]) if pos.get("mark_price") is not None else None,
                "strategy": pos.get("strategy"),
                "strategy_id": pos.get("strategy_id"),
                "strategy_version": pos.get("strategy_version"),
                "contributing_strategies": list(
                    pos.get("contributing_strategies") or []
                ),
                "trigger": pos.get("trigger"),
                "side": pos.get("side"),
                "pattern_weak": pos.get("pattern_weak"),
            }
        )
    return rows


def _plan_entry_executed_at() -> str | None:
    from trading_pulse.agent.dryrun_agent import PLANS_DIR, read_json

    for path in sorted(PLANS_DIR.glob("plan_*.json"), reverse=True):
        plan = read_json(path)
        ts = plan.get("entry_executed_at")
        if ts:
            return str(ts)
    return None


def format_holdings_lines(holdings: list[dict[str, Any]], *, html: bool = False) -> list[str]:
    if not holdings:
        return []
    lines = ["", "📂 מחזיקים כרגע (לא נמכרים אוטומטית):"]
    for h in holdings:
        days = int(h.get("days_held", 0))
        days_text = "יום אחד" if days == 1 else f"{days} ימים"
        text = (
            f"  {h['symbol']} · ${h['capital_usd']:.0f} · מ-{h['entry_day']} · "
            f"{days_text}"
        )
        lines.append(text)
    return lines

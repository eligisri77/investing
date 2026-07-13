"""Fill pending שיטה 2 breakouts during the US session (daily level + 5m/1m)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from trading_pulse.agent.candle_method2 import (
    evaluate_method2_intraday_entry,
    is_method2_rec,
    pending_method2_recs,
)


def stamp_method2_after_morning(
    plan: dict[str, Any],
    state: dict[str, Any],
    trading_day: date,
) -> list[str]:
    """Mark method2 recs as filled / pending_breakout / invalidated after the open job."""
    from trading_pulse.agent.positions import fetch_day_ohlc, held_symbols

    held = held_symbols(state)
    pending_syms: list[str] = []
    for rec in plan.get("recommendations") or []:
        if not rec.get("approved") or not is_method2_rec(rec):
            continue
        sym = str(rec.get("symbol") or "").upper()
        if not sym:
            continue
        if sym in held:
            rec["method2_status"] = "filled"
            rec["method2_fill_source"] = rec.get("method2_fill_source") or "morning"
            continue

        stop = float(rec.get("method2_stop_ref") or rec.get("floor_price") or 0)
        side = str(rec.get("side") or "LONG").upper()
        bar = fetch_day_ohlc(sym, trading_day)
        if bar is not None and stop > 0:
            if side == "LONG" and float(bar["open"]) < stop:
                rec["method2_status"] = "invalidated"
                rec["method2_note"] = "open below stop"
                logging.info("Method2 invalidated %s: open %.2f < stop %.2f", sym, bar["open"], stop)
                continue
            if side == "SHORT" and float(bar["open"]) > stop:
                rec["method2_status"] = "invalidated"
                rec["method2_note"] = "open above stop"
                logging.info("Method2 invalidated %s: open %.2f > stop %.2f", sym, bar["open"], stop)
                continue

        rec["method2_status"] = "pending_breakout"
        pending_syms.append(sym)
        logging.info("Method2 pending breakout: %s (watch intraday)", sym)
    return pending_syms


def try_fill_pending_method2(
    cfg: Any,
    state: dict[str, Any],
    plan: dict[str, Any],
    trading_day: date,
) -> list[dict[str, Any]]:
    """Attempt intraday fills for pending method2 breakouts. Returns new positions."""
    if not bool(getattr(cfg, "method2_enabled", True)):
        return []
    if not bool(getattr(cfg, "method2_intraday_enabled", True)):
        return []

    from trading_pulse.agent.positions import held_symbols, new_position_from_rec

    pending = pending_method2_recs(plan, state)
    if not pending:
        return []

    intervals_raw = getattr(cfg, "method2_intraday_intervals", None) or ["5m", "1m"]
    intervals = tuple(str(x) for x in intervals_raw)
    filled: list[dict[str, Any]] = []
    max_open = int(getattr(cfg, "max_open_positions", 5))

    for rec in pending:
        if len(state.get("open_positions", [])) >= max_open:
            break
        sym = str(rec["symbol"]).upper()
        if sym in held_symbols(state):
            rec["method2_status"] = "filled"
            continue

        result = evaluate_method2_intraday_entry(rec, intervals=intervals)
        if result is None:
            continue
        reason = str(result.get("reason") or "")
        if reason == "invalidated":
            rec["method2_status"] = "invalidated"
            rec["method2_note"] = "session open through stop"
            logging.info("Method2 invalidated intraday: %s", sym)
            continue
        fill_px = result.get("fill_price")
        if fill_px is None:
            continue

        pos = new_position_from_rec(rec, float(fill_px), trading_day.isoformat())
        pos["entry_at"] = datetime.now(timezone.utc).isoformat()
        pos["method2_fill_reason"] = reason
        pos["method2_fill_interval"] = result.get("interval")
        if result.get("micro_trigger"):
            pos["method2_micro_trigger"] = result["micro_trigger"]
        state.setdefault("open_positions", []).append(pos)
        commission = float(getattr(cfg, "commission_per_side_usd", 0.0))
        if commission > 0:
            state["equity"] = round(float(state["equity"]) - commission, 2)

        rec["method2_status"] = "filled"
        rec["method2_fill_source"] = reason
        rec["method2_filled_at"] = pos["entry_at"]
        rec["method2_fill_price"] = float(fill_px)
        filled.append(pos)
        logging.info(
            "Method2 intraday fill %s @ $%.2f (%s %s)",
            sym,
            float(fill_px),
            reason,
            result.get("interval"),
        )
    return filled


def expire_method2_pending(plan: dict[str, Any]) -> int:
    """At EOD, expire breakouts that never printed."""
    n = 0
    for rec in plan.get("recommendations") or []:
        if not is_method2_rec(rec):
            continue
        if str(rec.get("method2_status") or "") == "pending_breakout":
            rec["method2_status"] = "expired"
            n += 1
    return n

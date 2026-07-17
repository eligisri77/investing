"""Portfolio aggregation and Telegram formatting."""

from __future__ import annotations

from datetime import date
from typing import Any

from trading_pulse.agent.dryrun_agent import PLANS_DIR, REPORTS_DIR, load_config, load_state, read_json


def load_report(trading_day: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / f"report_{trading_day}.json"
    if not path.exists():
        return None
    return read_json(path)


def _append_pending_approved_rows(
    cfg: Any, open_positions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    from trading_pulse.agent.trading_flow import (
        before_market_entry,
        entries_already_run,
        scheduled_entry_moment,
    )

    held_symbols = {p["symbol"] for p in open_positions}
    rows = list(open_positions)
    for path in sorted(PLANS_DIR.glob("plan_*.json")):
        plan = read_json(path)
        trading_day = plan.get("for_trading_day", path.stem.replace("plan_", ""))
        if load_report(trading_day):
            continue
        alloc = plan.get("allocation") or {}
        if alloc.get("status") != "applied":
            continue
        td = date.fromisoformat(trading_day)
        if entries_already_run(plan, td) or not before_market_entry(cfg, td):
            continue
        entry_when = scheduled_entry_moment(cfg, td)
        for rec in plan.get("recommendations", []):
            if not rec.get("approved"):
                continue
            sym = str(rec["symbol"])
            if sym in held_symbols:
                continue
            rows.append(
                {
                    "symbol": sym,
                    "capital_usd": round(float(rec.get("capital_usd", 0)), 2),
                    "entry_ref_price": rec.get("entry_ref_price") or rec.get("last_price"),
                    "status": "pending_market_entry",
                    "entry_day": trading_day,
                    "approved_at": plan.get("approved_at"),
                    "scheduled_entry": entry_when,
                    "strategy": rec.get("strategy"),
                    "trigger": rec.get("trigger"),
                    "side": rec.get("side"),
                    "pattern_weak": rec.get("pattern_weak"),
                }
            )
            held_symbols.add(sym)
    return rows


def load_open_positions() -> list[dict[str, Any]]:
    """Positions currently held in the portfolio (with mark-to-market)."""
    from trading_pulse.agent.positions import enrich_held_unrealized

    cfg = load_config()
    state = load_state(cfg)
    from trading_pulse.agent.positions import ensure_open_positions, holdings_snapshot
    from trading_pulse.agent.trading_flow import (
        entries_already_run,
        revert_premarket_fills,
    )

    ensure_open_positions(state)

    for path in sorted(PLANS_DIR.glob("plan_*.json")):
        plan = read_json(path)
        trading_day = plan.get("for_trading_day", path.stem.replace("plan_", ""))
        if load_report(trading_day):
            continue
        alloc = plan.get("allocation") or {}
        if alloc.get("status") != "applied":
            continue
        td = date.fromisoformat(trading_day)
        if revert_premarket_fills(cfg, state, plan, td):
            state = load_state(cfg)
            ensure_open_positions(state)

    open_positions = _append_pending_approved_rows(cfg, list(holdings_snapshot(state)))

    from trading_pulse.agent.positions import _plan_entry_executed_at
    from trading_pulse.agent.dryrun_agent import STATE_FILE, save_json

    ts = _plan_entry_executed_at()
    changed = False
    for pos in state.get("open_positions", []):
        if not pos.get("entry_at") and ts:
            pos["entry_at"] = ts
            changed = True
    if changed:
        save_json(STATE_FILE, state)
        open_positions = _append_pending_approved_rows(cfg, list(holdings_snapshot(state)))

    holding = [p for p in open_positions if p.get("status") == "holding"]
    if holding:
        enriched, _total_ur = enrich_held_unrealized(holding, date.today())
        by_sym = {r["symbol"]: r for r in enriched}
        merged: list[dict[str, Any]] = []
        for p in open_positions:
            if p.get("status") == "holding" and p["symbol"] in by_sym:
                row = dict(by_sym[p["symbol"]])
                cap = float(row.get("capital_usd", 0))
                ur = float(row.get("unrealized_pnl_usd", 0))
                row["marked_value_usd"] = round(cap + ur, 2)
                merged.append(row)
            else:
                merged.append(p)
        open_positions = merged

    open_positions.sort(key=lambda x: (x.get("entry_day", x.get("trading_day", "")), x["symbol"]))
    return open_positions


def aggregate_symbol_pnl(state: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    all_trades: list[dict[str, Any]] = []

    for day_report in state.get("history", []):
        trading_day = day_report.get("trading_day", "")
        for trade in day_report.get("executed", []):
            symbol = trade["symbol"]
            pnl = float(trade.get("pnl_usd", 0))
            capital = float(trade.get("capital_usd", 0))
            record = {
                "symbol": symbol,
                "trading_day": trading_day,
                "capital_usd": round(capital, 2),
                "pnl_usd": round(pnl, 2),
                "pnl_pct": float(trade.get("pnl_pct", 0)),
                "exit_reason": trade.get("exit_reason", ""),
                "entry_price": trade.get("entry_price"),
                "exit_price": trade.get("exit_price"),
            }
            all_trades.append(record)

            if symbol not in by_symbol:
                by_symbol[symbol] = {
                    "symbol": symbol,
                    "trade_count": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_capital_usd": 0.0,
                    "total_pnl_usd": 0.0,
                    "last_trading_day": None,
                }
            agg = by_symbol[symbol]
            agg["trade_count"] += 1
            agg["total_pnl_usd"] += pnl
            agg["total_capital_usd"] += capital
            if pnl > 0:
                agg["wins"] += 1
            elif pnl < 0:
                agg["losses"] += 1
            if not agg["last_trading_day"] or trading_day > agg["last_trading_day"]:
                agg["last_trading_day"] = trading_day

    symbols = []
    for agg in by_symbol.values():
        cap = agg["total_capital_usd"]
        agg["total_pnl_usd"] = round(agg["total_pnl_usd"], 2)
        agg["total_capital_usd"] = round(cap, 2)
        agg["avg_pnl_pct"] = round((agg["total_pnl_usd"] / cap * 100) if cap else 0.0, 2)
        agg["win_rate_pct"] = round(
            (agg["wins"] / agg["trade_count"] * 100) if agg["trade_count"] else 0.0, 1
        )
        symbols.append(agg)

    symbols.sort(key=lambda x: (-x["total_pnl_usd"], x["symbol"]))
    all_trades.sort(key=lambda x: (x["trading_day"], x["symbol"]), reverse=True)
    return symbols, all_trades


def build_portfolio() -> dict[str, Any]:
    cfg = load_config()
    state = load_state(cfg)
    open_positions = load_open_positions()
    by_symbol, trades = aggregate_symbol_pnl(state)
    open_total = round(sum(p["capital_usd"] for p in open_positions), 2)
    realized_pnl = round(sum(s["total_pnl_usd"] for s in by_symbol), 2)
    unrealized_pnl = round(
        sum(float(p.get("unrealized_pnl_usd", 0)) for p in open_positions if p.get("status") == "holding"),
        2,
    )
    marked_total = round(
        sum(float(p.get("marked_value_usd", p.get("capital_usd", 0))) for p in open_positions),
        2,
    )
    equity = round(float(state.get("equity", cfg.initial_capital)), 2)
    holding_cap = round(
        sum(float(p.get("capital_usd", 0)) for p in open_positions if p.get("status") == "holding"),
        2,
    )
    cash_usd = max(0.0, round(equity - holding_cap, 2))

    return {
        "equity": equity,
        "cash_usd": cash_usd,
        "initial_capital": float(cfg.initial_capital),
        "open_positions": open_positions,
        "open_capital_usd": open_total,
        "open_marked_usd": marked_total,
        "open_count": len(open_positions),
        "unrealized_pnl_usd": unrealized_pnl,
        "by_symbol": by_symbol,
        "trades": trades,
        "total_realized_pnl": realized_pnl,
        "symbol_count": len(by_symbol),
        "trade_count": len(trades),
    }

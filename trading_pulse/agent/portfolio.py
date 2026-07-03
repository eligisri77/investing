"""Portfolio aggregation and Telegram formatting."""

from __future__ import annotations

from typing import Any

from trading_pulse.agent.dryrun_agent import PLANS_DIR, REPORTS_DIR, load_config, load_state, read_json


def load_report(trading_day: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / f"report_{trading_day}.json"
    if not path.exists():
        return None
    return read_json(path)


def load_open_positions() -> list[dict[str, Any]]:
    """Positions held in market + approved trades waiting for first trading day."""
    cfg = load_config()
    state = load_state(cfg)
    from trading_pulse.agent.positions import ensure_open_positions, holdings_snapshot

    ensure_open_positions(state)
    open_positions = list(holdings_snapshot(state))

    for path in sorted(PLANS_DIR.glob("plan_*.json")):
        plan = read_json(path)
        trading_day = plan.get("for_trading_day", path.stem.replace("plan_", ""))
        if load_report(trading_day):
            continue
        held_symbols = {p["symbol"] for p in open_positions}
        for rec in plan.get("recommendations", []):
            if not rec.get("approved"):
                continue
            symbol = rec["symbol"]
            if symbol in held_symbols:
                continue
            open_positions.append(
                {
                    "symbol": symbol,
                    "trading_day": trading_day,
                    "capital_usd": round(float(rec.get("capital_usd", 0)), 2),
                    "entry_ref_price": round(float(rec.get("entry_ref_price", 0)), 4),
                    "stop_loss_pct": float(rec.get("stop_loss_pct", 0)),
                    "take_profit_pct": float(rec.get("take_profit_pct", 0)),
                    "score": float(rec.get("score", 0)),
                    "status": "pending_execution",
                }
            )
            held_symbols.add(symbol)
    open_positions.sort(key=lambda x: (x.get("trading_day", x.get("entry_day", "")), x["symbol"]))
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

    return {
        "equity": round(float(state.get("equity", cfg.initial_capital)), 2),
        "initial_capital": float(cfg.initial_capital),
        "open_positions": open_positions,
        "open_capital_usd": open_total,
        "open_count": len(open_positions),
        "by_symbol": by_symbol,
        "trades": trades,
        "total_realized_pnl": realized_pnl,
        "symbol_count": len(by_symbol),
        "trade_count": len(trades),
    }


def format_portfolio_message(data: dict[str, Any]) -> str:
    pnl = float(data["total_realized_pnl"])
    pnl_sign = "+" if pnl >= 0 else ""

    lines = [
        "💼 תיק השקעות",
        "",
        f"הון נוכחי: ${data['equity']:.2f}",
        f"מושקע (ממתין): ${data['open_capital_usd']:.0f} · {data['open_count']} עסקאות",
        f"רווח/הפסד מצטבר: {pnl_sign}${pnl:.2f} · {data['trade_count']} עסקאות · {data['symbol_count']} מניות",
    ]

    open_positions = data.get("open_positions") or []
    if open_positions:
        lines.extend(["", "📌 מושקע / ממתין:"])
        for p in open_positions:
            if p.get("status") == "holding":
                lines.append(
                    f"  {p['symbol']} · ${p['capital_usd']:.0f} · מ-{p.get('entry_day')} · "
                    f"{p.get('days_held', 0)} ימים · מחזיק"
                )
            else:
                sl = int(float(p.get("stop_loss_pct", 0)) * 100)
                tp = int(float(p.get("take_profit_pct", 0)) * 100)
                lines.append(
                    f"  {p['symbol']} · ${p['capital_usd']:.0f} · {p.get('trading_day')} · "
                    f"ממתין לכניסה · SL -{sl}% / TP +{tp}%"
                )
    else:
        lines.extend(["", "📌 מושקע עכשיו: אין"])

    by_symbol = data.get("by_symbol") or []
    if by_symbol:
        lines.extend(["", "📊 סיכום לפי מניה:"])
        for s in by_symbol:
            sign = "+" if s["total_pnl_usd"] >= 0 else ""
            lines.append(
                f"  {s['symbol']} · {s['trade_count']} עסק · ${s['total_capital_usd']:.0f} הושקע"
                f" · {sign}${s['total_pnl_usd']:.2f} ({sign}{s['avg_pnl_pct']:.2f}%)"
                f" · win {s['win_rate_pct']:.0f}%"
            )
    else:
        lines.extend(["", "📊 עדיין לא בוצעו עסקאות"])

    return "\n".join(lines)

"""Persistent shadow ledger and per-strategy performance summary."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_pulse.agent.strategies.registry import STRATEGY_SPECS
from trading_pulse.core.app_paths import DATA_DIR

SHADOW_FILE = DATA_DIR / "strategy_shadow.json"


def _load(path: Path = SHADOW_FILE) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "signals": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("signals", [])
            return data
    except (OSError, ValueError):
        pass
    return {"schema_version": 1, "signals": []}


def _save(data: dict[str, Any], path: Path = SHADOW_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def record_shadow_plan(
    plan: dict[str, Any],
    *,
    path: Path = SHADOW_FILE,
) -> int:
    """Record one row per contributing strategy without duplicating live orders."""
    data = _load(path)
    rows: list[dict[str, Any]] = data["signals"]
    existing = {str(row.get("signal_key")) for row in rows}
    day = str(plan.get("for_trading_day") or "")
    added = 0
    for rec in plan.get("recommendations") or []:
        symbol = str(rec.get("symbol") or "").upper()
        contributors = list(
            rec.get("contributing_strategies")
            or [rec.get("strategy_id") or rec.get("strategy") or "unknown"]
        )
        for strategy_id in contributors:
            strategy_id = str(strategy_id)
            key = f"{day}|{symbol}|{strategy_id}"
            if not day or not symbol or key in existing:
                continue
            rows.append(
                {
                    "signal_key": key,
                    "trading_day": day,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "strategy_version": rec.get("strategy_version"),
                    "selected_live": True,
                    "status": "open",
                    "side": rec.get("side", "LONG"),
                    "entry_ref_price": rec.get("entry_ref_price"),
                    "stop_loss_price": rec.get("stop_loss_price"),
                    "take_profit_price": rec.get("take_profit_price"),
                    "native_score": rec.get("native_score", rec.get("score")),
                    "confidence": rec.get("confidence"),
                    "confluence_count": rec.get("confluence_count", 1),
                }
            )
            existing.add(key)
            added += 1
    if added:
        _save(data, path)
    return added


def reconcile_shadow_with_state(
    state: dict[str, Any],
    *,
    path: Path = SHADOW_FILE,
) -> int:
    """Attach realized live outcomes to matching shadow signals."""
    data = _load(path)
    rows: list[dict[str, Any]] = data["signals"]
    closed: list[dict[str, Any]] = []
    for day in state.get("history") or []:
        for trade in day.get("executed") or []:
            if trade.get("pnl_usd") is not None:
                closed.append({**trade, "_history_day": day.get("trading_day")})
    for trade in state.get("intraday_floor_exits") or []:
        if trade.get("pnl_usd") is not None:
            closed.append(trade)

    changed = 0
    for row in rows:
        if row.get("status") == "closed":
            continue
        for trade in closed:
            if str(trade.get("symbol") or "").upper() != row.get("symbol"):
                continue
            entry_day = str(
                trade.get("entry_day")
                or trade.get("trading_day")
                or trade.get("_history_day")
                or ""
            )
            if entry_day and entry_day < str(row.get("trading_day") or ""):
                continue
            row.update(
                {
                    "status": "closed",
                    "exit_day": trade.get("trading_day")
                    or trade.get("_history_day"),
                    "exit_reason": trade.get("exit_reason"),
                    "pnl_usd": round(float(trade.get("pnl_usd") or 0), 2),
                    "pnl_pct": round(float(trade.get("pnl_pct") or 0), 3),
                }
            )
            changed += 1
            break
    if changed:
        _save(data, path)
    return changed


def strategy_performance(
    state: dict[str, Any] | None = None,
    *,
    path: Path = SHADOW_FILE,
) -> dict[str, Any]:
    if state is not None:
        reconcile_shadow_with_state(state, path=path)
    rows = _load(path).get("signals") or []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("strategy_id") or "unknown")].append(row)
    summaries: list[dict[str, Any]] = []
    for strategy_id, signals in grouped.items():
        closed = [r for r in signals if r.get("status") == "closed"]
        wins = [r for r in closed if float(r.get("pnl_usd") or 0) > 0]
        pnl = sum(float(r.get("pnl_usd") or 0) for r in closed)
        summaries.append(
            {
                "strategy_id": strategy_id,
                "label_he": STRATEGY_SPECS.get(strategy_id).label_he
                if strategy_id in STRATEGY_SPECS
                else strategy_id,
                "signals": len(signals),
                "closed_trades": len(closed),
                "open_signals": len(signals) - len(closed),
                "wins": len(wins),
                "win_rate_pct": round(len(wins) / len(closed) * 100, 1)
                if closed
                else 0.0,
                "pnl_usd": round(pnl, 2),
                "ready_for_comparison": len(closed) >= 20,
            }
        )
    summaries.sort(key=lambda row: row["strategy_id"])
    return {
        "strategies": summaries,
        "minimum_closed_trades": 20,
        "recommended_weeks": "4–6",
        "total_signals": len(rows),
    }

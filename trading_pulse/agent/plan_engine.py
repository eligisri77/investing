"""
Evening brief → user confirm → market-open fill → EOD close.

Modelled after retail brokers (eToro confirm recurring order, Robinhood order lifecycle):
one active draft/confirmed plan per target trading day; regeneration each evening
unless a confirmed plan still has pending buys before the open.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

STATUS_DRAFT = "draft"
STATUS_CONFIRMED = "confirmed"
STATUS_EXECUTED = "executed"
STATUS_CLOSED = "closed"
STATUS_SUPERSEDED = "superseded"

# Legacy statuses mapped on read
_LEGACY_TO_STATUS = {
    "pending_approval": STATUS_DRAFT,
    "approved": STATUS_CONFIRMED,
    "hold_only": STATUS_DRAFT,
    "no_picks": STATUS_DRAFT,
}


def plan_trading_day(plan: dict[str, Any]) -> date:
    td = plan.get("for_trading_day")
    if not td:
        raise ValueError("plan missing for_trading_day")
    return date.fromisoformat(str(td))


def normalize_status(plan: dict[str, Any]) -> str:
    raw = str(plan.get("status", STATUS_DRAFT))
    if raw in _LEGACY_TO_STATUS:
        mapped = _LEGACY_TO_STATUS[raw]
        alloc = plan.get("allocation") or {}
        if alloc.get("status") == "applied" or any(
            r.get("approved") for r in plan.get("recommendations") or []
        ):
            return STATUS_CONFIRMED
        return mapped
    if raw in {STATUS_DRAFT, STATUS_CONFIRMED, STATUS_EXECUTED, STATUS_CLOSED, STATUS_SUPERSEDED}:
        return raw
    return STATUS_DRAFT


def _report_exists(trading_day: date) -> bool:
    from trading_pulse.agent.dryrun_agent import report_path

    return report_path(trading_day).exists()


def pending_buy_symbols(plan: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Approved picks that are not yet held — still need a fill at the open."""
    from trading_pulse.agent.positions import held_symbols
    from trading_pulse.agent.trading_flow import entries_already_run

    td = plan_trading_day(plan)
    if entries_already_run(plan, td):
        return []
    held = held_symbols(state)
    out: list[str] = []
    for rec in plan.get("recommendations") or []:
        if not rec.get("approved"):
            continue
        sym = str(rec["symbol"])
        if sym not in held:
            out.append(sym)
    return out


def is_locked(plan: dict[str, Any], state: dict[str, Any], cfg: Any, *, as_of: date | None = None) -> bool:
    """
    True when the plan is a live confirmed order waiting for market open.
    Draft plans are never locked — evening job may refresh research.
    """
    if not plan.get("for_trading_day"):
        return False
    as_of = as_of or date.today()
    status = normalize_status(plan)
    td = plan_trading_day(plan)

    if status in {STATUS_EXECUTED, STATUS_CLOSED, STATUS_SUPERSEDED}:
        return False
    if _report_exists(td):
        return False
    if td < as_of:
        return False
    if status != STATUS_CONFIRMED:
        return False

    pending = pending_buy_symbols(plan, state)
    if not pending:
        return False

    from trading_pulse.agent.trading_flow import before_market_entry

    return before_market_entry(cfg, td)


def supersede_other_plans(target_day: date) -> None:
    """Keep a single active plan file per target session."""
    from trading_pulse.agent.dryrun_agent import PLANS_DIR, read_json, save_json

    for path in PLANS_DIR.glob("plan_*.json"):
        plan = read_json(path)
        td_str = plan.get("for_trading_day", path.stem.replace("plan_", ""))
        try:
            td = date.fromisoformat(td_str)
        except ValueError:
            continue
        if td == target_day:
            continue
        st = normalize_status(plan)
        if st in {STATUS_CLOSED, STATUS_SUPERSEDED}:
            continue
        if _report_exists(td):
            plan["status"] = STATUS_CLOSED
        else:
            plan["status"] = STATUS_SUPERSEDED
        save_json(path, plan)
        logging.info("Plan %s marked %s", td_str, plan["status"])


def apply_confirm(plan: dict[str, Any], state: dict[str, Any], cfg: Any) -> dict[str, Any]:
    """
    One-step confirm (like tapping Confirm on a broker order preview):
    approve all picks + equal cash split + status confirmed.
    """
    from trading_pulse.agent.trading_flow import auto_allocate_equal, funding_gap

    recs = plan.get("recommendations") or []
    if not recs:
        return plan

    gap = funding_gap(plan, state, cfg)
    if gap:
        plan["funding"] = gap
        return plan

    for rec in recs:
        rec["approved"] = True
    plan["status"] = STATUS_CONFIRMED
    plan["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    plan["pre_entry_equity"] = round(float(state.get("equity", cfg.initial_capital)), 2)
    plan["allocation"] = {"status": "pending"}
    chosen = auto_allocate_equal(cfg, plan, state)
    if chosen is None:
        n = len(recs)
        cash = float(plan.get("available_capital_usd", state.get("equity", 0)))
        each = round(cash / max(n, 1), 2)
        diff = round(cash - each * n, 2)
        for i, rec in enumerate(recs):
            rec["capital_usd"] = each + (diff if i == 0 else 0)
        plan["allocation"] = {
            "status": "applied",
            "auto": True,
            "title": "שווה — השקעה מלאה",
            "applied_at": plan["confirmed_at"],
            "amounts": {str(r["symbol"]): float(r["capital_usd"]) for r in recs},
        }
    else:
        plan.setdefault("allocation", {})["status"] = "applied"
        plan["allocation"]["auto"] = True
    return plan


def cancel_plan(*, as_of: date | None = None) -> dict[str, Any]:
    """Cancel the active (draft/confirmed) plan for the next open session.

    Marks it superseded so the evening job (or a manual regenerate) can build a
    fresh one. Does not touch executed/closed plans or already-filled positions.
    """
    from trading_pulse.agent.dryrun_agent import PLANS_DIR, read_json, save_json

    day_str = active_trading_day(as_of=as_of)
    if not day_str:
        return {"ok": False, "reason": "no_active_plan"}

    td = date.fromisoformat(day_str)
    path = PLANS_DIR / f"plan_{day_str}.json"
    if not path.exists():
        return {"ok": False, "reason": "no_active_plan"}

    plan = read_json(path)
    status = normalize_status(plan)
    if status in {STATUS_EXECUTED, STATUS_CLOSED}:
        return {"ok": False, "reason": "already_executed", "day": day_str, "status": status}

    symbols = [str(r["symbol"]) for r in plan.get("recommendations") or []]
    plan["status"] = STATUS_SUPERSEDED
    plan["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    save_json(path, plan)
    logging.info("Plan %s cancelled by user (was %s)", day_str, status)
    return {"ok": True, "day": day_str, "prev_status": status, "symbols": symbols}


def mark_executed(plan: dict[str, Any], trading_day: date, *, cfg: Any | None = None) -> None:
    from trading_pulse.agent.trading_flow import mark_entries_executed

    plan["status"] = STATUS_EXECUTED
    mark_entries_executed(plan, trading_day, cfg=cfg)


def mark_closed(plan: dict[str, Any]) -> None:
    plan["status"] = STATUS_CLOSED


def active_trading_day(*, as_of: date | None = None) -> str | None:
    """Next open session with a plan and no EOD report."""
    from trading_pulse.agent.dryrun_agent import PLANS_DIR, read_json

    as_of = as_of or date.today()
    candidates: list[tuple[date, str]] = []
    for path in PLANS_DIR.glob("plan_*.json"):
        plan = read_json(path)
        td_str = plan.get("for_trading_day")
        if not td_str:
            continue
        td = date.fromisoformat(str(td_str))
        if _report_exists(td) or td < as_of:
            continue
        if normalize_status(plan) == STATUS_SUPERSEDED:
            continue
        candidates.append((td, str(td_str)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def evening_summary_kind(plan: dict[str, Any], state: dict[str, Any], cfg: Any) -> str:
    """draft | hold | no_picks | locked"""
    if is_locked(plan, state, cfg):
        return "locked"
    st = normalize_status(plan)
    recs = plan.get("recommendations") or []
    if not recs:
        if plan.get("holdings"):
            return "hold"
        return "no_picks"
    if st == STATUS_DRAFT:
        return "draft"
    return "locked"


def plan_is_protected(
    plan: dict[str, Any], *, state: dict[str, Any] | None = None, as_of: date | None = None
) -> bool:
    """Backward-compatible name used by generate_plan and tests."""
    from trading_pulse.agent.dryrun_agent import load_config

    cfg = load_config()
    st = state if state is not None else {}
    return is_locked(plan, st, cfg, as_of=as_of)

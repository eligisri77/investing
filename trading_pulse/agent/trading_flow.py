"""User-facing trading flow: wallet, first-day deploy, funding gaps, auto-allocation."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

PlanIntent = Literal["first_investment", "add_with_cash", "add_needs_sell", "hold_only", "no_picks"]


def wallet_summary(state: dict[str, Any], cfg: Any) -> dict[str, float]:
    from trading_pulse.agent.positions import available_capital, deployed_capital

    equity = float(state.get("equity", getattr(cfg, "initial_capital", 1000.0)))
    invested = deployed_capital(state)
    cash = available_capital(cfg, state)
    return {
        "equity_usd": round(equity, 2),
        "invested_usd": round(invested, 2),
        "cash_free_usd": round(cash, 2),
    }


def is_empty_portfolio(state: dict[str, Any]) -> bool:
    from trading_pulse.agent.positions import ensure_open_positions

    ensure_open_positions(state)
    return len(state.get("open_positions", [])) == 0


def plan_intent(plan: dict[str, Any], state: dict[str, Any], cfg: Any) -> PlanIntent:
    recs = plan.get("recommendations") or []
    if not recs:
        if plan.get("holdings"):
            return "hold_only"
        return "no_picks"
    wallet = wallet_summary(state, cfg)
    if is_empty_portfolio(state):
        return "first_investment"
    if wallet["cash_free_usd"] >= 50:
        return "add_with_cash"
    return "add_needs_sell"


def initial_deploy_slots(cfg: Any, state: dict[str, Any]) -> int:
    """How many stocks to suggest on day 1 (split $1000)."""
    if not is_empty_portfolio(state):
        return min(int(cfg.max_trades_per_day), int(cfg.max_open_positions))
    target = int(getattr(cfg, "initial_deploy_stocks", 3))
    return max(1, min(target, int(cfg.max_open_positions), int(cfg.max_trades_per_day)))


def per_trade_cap_for_plan(cfg: Any, state: dict[str, Any], n_picks: int) -> float:
    wallet = wallet_summary(state, cfg)
    equity = wallet["equity_usd"]
    cash = wallet["cash_free_usd"] if not is_empty_portfolio(state) else equity
    deployable = max(cash, 0.0)
    n = max(n_picks, 1)
    if is_empty_portfolio(state):
        return round(deployable / n, 2)
    cap = equity * float(cfg.max_position_pct)
    return round(min(cap, deployable / n), 2)


def funding_gap(plan: dict[str, Any], state: dict[str, Any], cfg: Any) -> dict[str, Any] | None:
    """When cash is too low for approved new picks — suggest partial sells."""
    from trading_pulse.agent.positions import held_symbols, holdings_snapshot

    intent = plan_intent(plan, state, cfg)
    if intent != "add_needs_sell":
        return None
    approved = [r for r in plan.get("recommendations", []) if r.get("approved")]
    held = held_symbols(state)
    new_recs = [r for r in approved if str(r["symbol"]) not in held]
    if not new_recs:
        new_recs = [r for r in plan.get("recommendations", []) if str(r["symbol"]) not in held]
    if not new_recs:
        return None

    wallet = wallet_summary(state, cfg)
    needed = sum(float(r.get("capital_usd", 0)) for r in new_recs)
    gap = round(max(0.0, needed - wallet["cash_free_usd"]), 2)
    if gap < 1:
        return None

    holdings = holdings_snapshot(state)
    suggestions: list[dict[str, Any]] = []
    remaining = gap
    for h in sorted(holdings, key=lambda x: -float(x.get("capital_usd", 0))):
        sym = str(h["symbol"])
        cap = float(h.get("capital_usd", 0))
        if cap <= 0:
            continue
        sell_usd = round(min(cap, max(remaining, cap * 0.25)), 2)
        suggestions.append(
            {
                "symbol": sym,
                "sell_usd": sell_usd,
                "sell_pct": round(sell_usd / cap * 100, 1),
                "keeps_usd": round(cap - sell_usd, 2),
            }
        )
        remaining = round(remaining - sell_usd, 2)
        if remaining <= 0:
            break

    target_sym = str(new_recs[0]["symbol"])
    return {
        "gap_usd": gap,
        "cash_free_usd": wallet["cash_free_usd"],
        "needed_usd": round(needed, 2),
        "target_symbol": target_sym,
        "sell_suggestions": suggestions,
    }


def should_auto_allocate(cfg: Any, plan: dict[str, Any], state: dict[str, Any]) -> bool:
    intent = plan_intent(plan, state, cfg)
    if intent == "first_investment":
        return True
    if intent == "add_with_cash":
        approved = [r for r in plan.get("recommendations", []) if r.get("approved")]
        return len(approved) > 0
    return False


def auto_allocate_equal(cfg: Any, plan: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    """Apply equal split of free cash — no manual ח1…ח5."""
    from trading_pulse.agent.capital_allocation import apply_allocation_option, ensure_allocation_options

    options = ensure_allocation_options(cfg, plan, state)
    if not options:
        return None
    chosen = apply_allocation_option(plan, 1, options)
    if chosen is None:
        return None
    plan.setdefault("allocation", {})["status"] = "applied"
    plan["allocation"]["auto"] = True
    return chosen


def entries_already_run(plan: dict[str, Any], trading_day: date) -> bool:
    return plan.get("entries_executed_for") == trading_day.isoformat()


def before_market_entry(cfg: Any, trading_day: date) -> bool:
    """True until scheduled US market-open entry for this trading day."""
    from datetime import datetime, time

    from trading_pulse.core.schedule_tz import UTC

    now = datetime.now(UTC)
    if now.date() < trading_day:
        return True
    if now.date() > trading_day:
        return False
    hour, minute = (int(x) for x in str(getattr(cfg, "entry_sim_time", "13:35")).split(":"))
    open_at = datetime.combine(trading_day, time(hour, minute), tzinfo=UTC)
    return now < open_at


def scheduled_entry_moment(cfg: Any, trading_day: date) -> str:
    from trading_pulse.core.schedule_tz import format_dual_time

    return format_dual_time(str(getattr(cfg, "entry_sim_time", "13:35")), on_day=trading_day)


def revert_premarket_fills(cfg: Any, state: dict[str, Any], plan: dict[str, Any], trading_day: date) -> bool:
    """Remove fills that ran before market open — user approves first, buys at open."""
    from trading_pulse.agent.dryrun_agent import STATE_FILE, plan_path, save_json
    from trading_pulse.agent.positions import ensure_open_positions

    if not before_market_entry(cfg, trading_day):
        return False

    ensure_open_positions(state)
    approved_syms = {str(r["symbol"]) for r in plan.get("recommendations", []) if r.get("approved")}
    day_str = trading_day.isoformat()
    removed = [
        p
        for p in state.get("open_positions", [])
        if str(p.get("symbol")) in approved_syms and str(p.get("entry_day")) == day_str
    ]
    had_executed = entries_already_run(plan, trading_day)
    alloc_applied = (plan.get("allocation") or {}).get("status") == "applied"
    if not removed and not had_executed:
        snap = plan.get("pre_entry_equity") or plan.get("equity_snapshot")
        if alloc_applied and snap and not state.get("open_positions"):
            if float(state.get("equity", 0)) > float(snap) + 1:
                state["equity"] = round(float(snap), 2)
                save_json(STATE_FILE, state)
                return True
        return False

    kept = [p for p in state.get("open_positions", []) if p not in removed]
    pre = plan.get("pre_entry_equity") or plan.get("equity_snapshot")
    if pre is not None and (removed or had_executed):
        state["equity"] = round(float(pre), 2)
    # Equity already includes deployed capital — do not add capital_usd back when removing positions.
    state["open_positions"] = kept
    plan.pop("entries_executed_for", None)
    plan.pop("entry_executed_at", None)
    save_json(plan_path(trading_day), plan)
    save_json(STATE_FILE, state)
    return True


def mark_entries_executed(plan: dict[str, Any], trading_day: date, *, cfg: Any | None = None) -> None:
    from datetime import datetime, time, timezone

    from trading_pulse.core.schedule_tz import UTC

    plan["entries_executed_for"] = trading_day.isoformat()
    if cfg is not None:
        hour, minute = (int(x) for x in str(getattr(cfg, "entry_sim_time", "13:35")).split(":"))
        plan["entry_executed_at"] = datetime.combine(
            trading_day, time(hour, minute), tzinfo=UTC
        ).isoformat()
    else:
        plan["entry_executed_at"] = datetime.now(timezone.utc).isoformat()

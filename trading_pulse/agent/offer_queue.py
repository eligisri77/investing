"""Sequential, one-stock-at-a-time buy offers.

Instead of dumping the whole plan for a mass `הכל` approve, the pre-market
review offers new-buy candidates one at a time: score + explanation + chart +
free cash + a suggested amount. The bot waits for a reply (`כן` / an amount /
`דלג`) before moving to the next one, nudging after ~10 minutes of silence.
Direct commands (`מכור`, `קנה SYMBOL`, `תיק`, ...) keep working at any time —
only a bare yes/no/amount reply is consumed here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

NUDGE_AFTER_MINUTES = 10
OFFER_TTL_HOURS = 6  # covers the pre-market window through mid-morning

_YES_WORDS = frozenset({"כן", "yes", "ok", "אוקי", "אישור", "יאללה", "מאשר", "אשר", "קנה", "buy"})
_SKIP_WORDS = frozenset({"דלג", "skip", "לא", "no", "לא תודה", "דחה"})


def _rec_by_symbol(plan: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    for rec in plan.get("recommendations") or []:
        if str(rec.get("symbol")) == str(symbol):
            return rec
    return None


def eligible_offer_symbols(plan: dict[str, Any]) -> list[str]:
    """New-buy candidates: not below-bar, not already held, not yet decided."""
    held = {str(h.get("symbol")) for h in (plan.get("holdings") or [])}
    out: list[str] = []
    for rec in plan.get("recommendations") or []:
        sym = str(rec.get("symbol"))
        if sym in held or rec.get("below_bar"):
            continue
        if rec.get("approved") or rec.get("offer_skipped"):
            continue
        out.append(sym)
    return out


def start_offer_queue(state: dict[str, Any], plan: dict[str, Any]) -> bool:
    """Seed `state['pending_offer']` with today's queue. False = nothing to offer."""
    queue = eligible_offer_symbols(plan)
    if not queue:
        state.pop("pending_offer", None)
        return False
    state["pending_offer"] = {
        "trading_day": str(plan.get("for_trading_day")),
        "queue": queue,
        "index": 0,
        "decided": {},
        "offered_at": None,
        "nudged_at": None,
    }
    return True


def pending_offer(state: dict[str, Any]) -> dict[str, Any] | None:
    po = state.get("pending_offer")
    if not isinstance(po, dict) or not po.get("queue"):
        return None
    if int(po.get("index", 0)) >= len(po["queue"]):
        return None
    return po


def current_offer_symbol(state: dict[str, Any]) -> str | None:
    po = pending_offer(state)
    return str(po["queue"][po["index"]]) if po else None


def suggested_amount(plan: dict[str, Any], po: dict[str, Any]) -> float:
    """Equal split of remaining deployable cash across remaining un-decided offers."""
    remaining_n = max(1, len(po["queue"]) - int(po.get("index", 0)))
    total = float(plan.get("available_capital_usd") or 0)
    spent = sum(float(v) for v in (po.get("decided") or {}).values())
    deployable = max(0.0, total - spent)
    return round(deployable / remaining_n, 2)


def cash_remaining(plan: dict[str, Any], po: dict[str, Any]) -> float:
    total = float(plan.get("available_capital_usd") or 0)
    spent = sum(float(v) for v in (po.get("decided") or {}).values())
    return max(0.0, round(total - spent, 2))


def _advance(state: dict[str, Any]) -> None:
    po = state.get("pending_offer")
    if not po:
        return
    po["index"] = int(po.get("index", 0)) + 1
    po["offered_at"] = None
    po["nudged_at"] = None


def format_offer_prompt(
    rec: dict[str, Any],
    *,
    cash_free: float,
    suggested_usd: float,
    position_no: int,
    total: int,
) -> str:
    from trading_pulse.telegram.telegram_format import escape_html

    sym = escape_html(str(rec.get("symbol")))
    score = float(rec.get("score") or rec.get("score_technical") or 0)
    explanation = str(rec.get("explanation") or rec.get("reason") or "").strip()
    lines = [f"💡 <b>הצעה {position_no}/{total}: {sym}</b>", f"ציון: <b>{score:.1f}</b>"]
    if explanation:
        lines.append(escape_html(explanation))
    lines += [
        "",
        f"מזומן פנוי: <b>${cash_free:.0f}</b>",
        f"מומלץ: <b>${suggested_usd:.0f}</b>",
        "",
        "שלח <code>כן</code> לקנות בסכום המוצע, סכום (למשל <code>150</code>), או <code>דלג</code>",
    ]
    return "\n".join(lines)


def send_offer(cfg: Any, state: dict[str, Any], plan: dict[str, Any]) -> bool:
    """Send the current offer's chart + prompt. False = queue is empty."""
    from trading_pulse.agent.dryrun_agent import (
        format_rec_signal_block,
        send_telegram_photo,
        send_user_notification,
    )

    po = pending_offer(state)
    if not po:
        return False
    symbol = current_offer_symbol(state)
    rec = _rec_by_symbol(plan, symbol or "")
    if rec is None:
        # Stale queue entry (rec vanished) — skip forward.
        _advance(state)
        return send_offer(cfg, state, plan)

    total = len(po["queue"])
    position_no = int(po["index"]) + 1
    try:
        speculative = plan.get("risk_profile") == "speculative"
        signal_lines = format_rec_signal_block(rec, speculative).splitlines()
        from trading_pulse.telegram.reply_cards import chart_with_recommendation_details

        img = chart_with_recommendation_details(
            rec,
            position_no,
            str(plan.get("for_trading_day", "")),
            signal_lines=signal_lines,
            held=False,
        )
        if img:
            send_telegram_photo(
                cfg, img, f"#{position_no} {symbol}", context=f"offer:{symbol}", parse_mode="HTML"
            )
    except Exception as ex:
        logging.warning("Offer chart for %s failed: %s", symbol, ex)

    text = format_offer_prompt(
        rec,
        cash_free=cash_remaining(plan, po),
        suggested_usd=suggested_amount(plan, po),
        position_no=position_no,
        total=total,
    )
    send_user_notification(cfg, text, context="offer", parse_mode="HTML")
    po["offered_at"] = datetime.now(timezone.utc).isoformat()
    po["nudged_at"] = None
    return True


def finish_offers(cfg: Any, plan: dict[str, Any]) -> None:
    from trading_pulse.agent.dryrun_agent import send_user_notification

    approved = [r for r in plan.get("recommendations") or [] if r.get("approved")]
    if approved:
        names = ", ".join(str(r["symbol"]) for r in approved)
        text = (
            "✅ <b>עברנו על כל ההמלצות של היום</b>\n"
            f"קניות שאושרו: <b>{names}</b> — נכנסות בפתיחה."
        )
    else:
        text = "✅ <b>עברנו על כל ההמלצות של היום</b> — לא נקנה כלום היום."
    send_user_notification(cfg, text, context="offer:done", parse_mode="HTML")


def start_and_send_first_offer(cfg: Any, state: dict[str, Any], plan: dict[str, Any]) -> bool:
    """Seed the queue from `plan` and send the first offer. False = nothing to offer."""
    if not start_offer_queue(state, plan):
        return False
    return send_offer(cfg, state, plan)


def maybe_nudge_offer(cfg: Any, state: dict[str, Any]) -> bool:
    """Send a gentle reminder if the current offer has been waiting ~10 minutes."""
    po = pending_offer(state)
    if not po or not po.get("offered_at") or po.get("nudged_at"):
        return False
    try:
        offered = datetime.fromisoformat(str(po["offered_at"]).replace("Z", "+00:00"))
        if offered.tzinfo is None:
            offered = offered.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    if (now - offered).total_seconds() < NUDGE_AFTER_MINUTES * 60:
        return False
    symbol = current_offer_symbol(state)
    if not symbol:
        return False
    from trading_pulse.agent.dryrun_agent import send_user_notification

    send_user_notification(
        cfg,
        f"⏳ עדיין מחכה לתשובה על <b>{symbol}</b> — <code>כן</code> / סכום / <code>דלג</code>",
        context="offer:nudge",
        parse_mode="HTML",
    )
    po["nudged_at"] = now.isoformat()
    return True


def expire_stale_offer(state: dict[str, Any]) -> bool:
    """Drop a pending offer that has sat unanswered past the TTL (e.g. missed the whole morning)."""
    po = state.get("pending_offer")
    if not isinstance(po, dict):
        return False
    offered_raw = po.get("offered_at")
    if not offered_raw:
        return False
    try:
        offered = datetime.fromisoformat(str(offered_raw).replace("Z", "+00:00"))
        if offered.tzinfo is None:
            offered = offered.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    if (datetime.now(timezone.utc) - offered).total_seconds() > OFFER_TTL_HOURS * 3600:
        state.pop("pending_offer", None)
        return True
    return False


def cutoff_pending_offer(cfg: Any, state: dict[str, Any]) -> bool:
    """Market open reached with the offer queue still unanswered.

    Auto-finalizes whatever was decided so far and drops the rest — still
    buyable later via a direct `קנה SYMBOL`, or re-offered on the next review
    if still a valid candidate. Returns True if a pending offer was cleared.
    """
    po = state.get("pending_offer")
    if not isinstance(po, dict) or not po.get("queue"):
        return False
    from datetime import date as _date

    from trading_pulse.agent.dryrun_agent import (
        plan_path,
        read_json,
        save_json,
        send_user_notification,
    )
    from trading_pulse.agent.plan_engine import finalize_manual_confirm, mark_offer_skipped

    trading_day = str(po.get("trading_day") or "")
    try:
        path = plan_path(_date.fromisoformat(trading_day))
    except ValueError:
        state.pop("pending_offer", None)
        return True
    if not path.exists():
        state.pop("pending_offer", None)
        return True

    plan = read_json(path)
    remaining = list(po["queue"][int(po.get("index", 0)) :])
    for sym in remaining:
        mark_offer_skipped(plan, sym)
    finalize_manual_confirm(plan, state, cfg)
    save_json(path, plan)
    state.pop("pending_offer", None)
    if remaining:
        names = ", ".join(remaining)
        send_user_notification(
            cfg,
            f"⏰ <b>השוק נפתח</b> — סגרנו את סבב ההצעות של היום.\n"
            f"לא נענו והושמטו: <b>{names}</b> (אפשר תמיד <code>קנה SYMBOL</code> בנפרד).",
            context="offer:cutoff",
            parse_mode="HTML",
        )
    return True


def try_resolve_pending_offer(cfg: Any, state: dict[str, Any], text: str) -> bool:
    """Handle a reply to the current offer. True = consumed (caller should stop parsing)."""
    from trading_pulse.agent.dryrun_agent import (
        STATE_FILE,
        plan_path,
        read_json,
        save_json,
        send_user_notification,
    )
    from trading_pulse.agent.plan_engine import (
        apply_partial_confirm_manual,
        finalize_manual_confirm,
        mark_offer_skipped,
    )

    po = pending_offer(state)
    if not po:
        return False
    symbol = current_offer_symbol(state)
    if not symbol:
        return False

    trading_day = str(po.get("trading_day") or "")
    from datetime import date as _date

    try:
        path = plan_path(_date.fromisoformat(trading_day))
    except ValueError:
        state.pop("pending_offer", None)
        return False
    if not path.exists():
        state.pop("pending_offer", None)
        return False
    plan = read_json(path)

    raw = str(text).strip()
    low = raw.lower()
    decision: str
    amount: float = 0.0
    if low in _YES_WORDS:
        decision = "buy"
        amount = suggested_amount(plan, po)
    elif low in _SKIP_WORDS:
        decision = "skip"
    else:
        cleaned = raw.replace("$", "").replace(",", "").strip()
        try:
            amount = float(cleaned)
            if amount <= 0:
                return False
            decision = "buy"
        except ValueError:
            return False  # not an offer reply — let normal command parsing try

    if decision == "buy":
        amount = max(0.0, min(float(amount), cash_remaining(plan, po)))
        apply_partial_confirm_manual(plan, symbol, amount)
        po.setdefault("decided", {})[symbol] = amount
        reply = f"✅ נקנה <b>{symbol}</b> ב-${amount:.0f} (נכנס בפתיחה)"
    else:
        mark_offer_skipped(plan, symbol)
        reply = f"⏭️ דילגנו על <b>{symbol}</b>"

    _advance(state)
    save_json(path, plan)
    send_user_notification(cfg, reply, context="offer:decision", parse_mode="HTML")

    if pending_offer(state) is not None:
        save_json(STATE_FILE, state)
        send_offer(cfg, state, plan)
    else:
        finalize_manual_confirm(plan, state, cfg)
        save_json(path, plan)
        state.pop("pending_offer", None)
        save_json(STATE_FILE, state)
        finish_offers(cfg, plan)
    return True

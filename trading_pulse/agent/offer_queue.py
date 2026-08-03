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
import re
from datetime import datetime, timezone
from typing import Any

NUDGE_AFTER_MINUTES = 10
OFFER_TTL_HOURS = 6  # covers the pre-market window through mid-morning

_YES_WORDS = frozenset({"כן", "yes", "ok", "אוקי", "אישור", "יאללה", "מאשר", "אשר", "קנה", "buy"})
_SKIP_WORDS = frozenset({"דלג", "skip", "לא", "no", "לא תודה", "דחה"})
# Natural replies while an offer is open: "קנה 200", "buy $150", "קנה RBLX 200"
_BUY_AMOUNT_RE = re.compile(
    r"^(?:קנה|תקנה|buy)\s+(?:([A-Za-z][A-Za-z0-9.\-]*)\s+)?\$?\s*([\d]+(?:[.,]\d+)?)\s*$",
    re.IGNORECASE,
)


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


def build_offer_metric_cubes(rec: dict[str, Any], *, rank: int | None = None) -> list[dict[str, str]]:
    """Structured metric cubes for the offer PNG card (title / blurb / value)."""
    from trading_pulse.agent.signal_sources import SOURCE_LABELS
    from trading_pulse.agent.strategy_labels import strategy_label

    score = float(rec.get("score") or rec.get("score_technical") or 0)
    ret5 = float(rec.get("ret_5d_pct") or 0)
    vol_ratio = float(rec.get("vol_ratio") or 0)
    volume_ok = bool(rec.get("volume_ok", False))
    rank_n = int(rank) if rank is not None else 0
    strategy = str(rec.get("strategy") or "")
    cubes: list[dict[str, str]] = []

    method = strategy_label(rec) or str(rec.get("strategy_id") or strategy or "").strip()
    entry_policy = str(rec.get("entry_policy") or "")
    if entry_policy == "stop_breakout":
        timing = "כניסה רק בפריצה — לא אוטומטית בפתיחה"
        timing_short = "בפריצה"
    elif entry_policy == "market_open":
        timing = "כניסה במחיר פתיחה אם אישרת"
        timing_short = "בפתיחה"
    else:
        timing = "איך המערכת בחרה את המניה הזו"
        timing_short = ""
    method_value = " · ".join(p for p in (method or "—", timing_short) if p)
    cubes.append(
        {
            "title": "שיטת כניסה",
            "blurb": timing,
            "value": method_value,
            "wide": "1",
        }
    )

    if strategy == "method2":
        side = str(rec.get("side") or "LONG").upper()
        side_he = "שורט" if side == "SHORT" else "לונג"
        trig = str(rec.get("trigger") or "—")
        entry = float(rec.get("method2_entry_ref") or rec.get("entry_ref_price") or 0)
        stop = float(rec.get("method2_stop_ref") or rec.get("stop_loss_price") or 0)
        cubes.append(
            {
                "title": "נרות סיניים 2",
                "blurb": "רמות הפריצה והסטופ לשיטה הזו.",
                "value": f"{side_he} · טריגר {trig} · פריצה ${entry:.2f} · סטופ ${stop:.2f}",
                "wide": "1",
            }
        )
    elif strategy == "rising_three_methods":
        weak = " (חלש)" if rec.get("pattern_weak") else ""
        cubes.append(
            {
                "title": "תבנית Rising Three",
                "blurb": "זיהוי תבנית נרות — ציון התבנית מול דירוג היום.",
                "value": f"דירוג #{rank_n or '—'}{weak} · ציון תבנית {float(rec.get('pattern_score', score)):.1f}",
                "wide": "1",
            }
        )
    else:
        atr = float(rec.get("atr_pct") or 0)
        score_bits = [f"דירוג #{rank_n}" if rank_n else "דירוג —", f"ציון {score:.1f}"]
        if atr:
            score_bits.append(f"ATR {atr:.1f}%")
        cubes.append(
            {
                "title": "ציון ותנודתיות",
                "blurb": "דירוג מול הרשימה וכמה המניה זזה ביום.",
                "value": " · ".join(score_bits),
            }
        )

        if rec.get("breakout_ok") is not None or rec.get("near_high_pct") is not None:
            near = float(rec.get("near_high_pct") or 0)
            if rec.get("breakout_ok"):
                mom = f"פריצה · {near:.1f}% משיא 20 יום"
            else:
                mom = f"לא בפריצה · {near:.1f}% מתחת לשיא 20 יום"
        elif rec.get("momentum_ok") is not None:
            above = float(rec.get("above_ma20_pct") or 0)
            mom = f"מעל MA20 ב-{above:+.1f}%" if rec.get("momentum_ok") else "מתחת ל-MA20"
        else:
            mom = "—"
        ret_txt = f"{ret5:+.1f}% ב-5 ימים" if ret5 else "ללא שינוי משמעותי ב-5 ימים"
        cubes.append(
            {
                "title": "מומנטום ומחיר",
                "blurb": "האם המחיר חזק ביחס לממוצע / לשיא האחרון.",
                "value": f"{mom} · {ret_txt}",
            }
        )

    vol_label = "גבוה" if volume_ok else ("רגיל" if vol_ratio >= 0.8 else "נמוך")
    cubes.append(
        {
            "title": "נפח",
            "blurb": "האם יש עניין בשוק מעבר לתנועת מחיר בלבד.",
            "value": f"{vol_ratio:.2f}× מהממוצע · {vol_label}",
        }
    )

    source_scores = rec.get("source_scores") or {}
    news_parts: list[str] = []
    if source_scores:
        breakdown = ", ".join(
            f"{SOURCE_LABELS.get(k, k)} {v:.1f}"
            for k, v in sorted(source_scores.items(), key=lambda x: -x[1])[:4]
        )
        news_parts.append(f"{int(rec.get('sources_used', len(source_scores)))} אתרים: {breakdown}")
    adj = float(rec.get("sentiment_adjustment") or 0)
    if adj:
        news_parts.append(f"חדשות ({rec.get('sentiment_tone', 'neutral')}): {adj:+.1f}")
    if rec.get("source_disagreement"):
        news_parts.append("⚠️ מקורות לא מסכימים")
    cubes.append(
        {
            "title": "חדשות ומקורות",
            "blurb": "איך ציון חיצוני וסנטימנט משנים את התמונה.",
            "value": " · ".join(news_parts) if news_parts else "אין פירוט מקורות להצעה הזו",
        }
    )

    backtest = rec.get("backtest") or {}
    bt_summary = str(backtest.get("summary") or "").strip()
    cubes.append(
        {
            "title": "בדיקה לאחור",
            "blurb": "איך הכלל הזה התנהג בעבר — לא הבטחה.",
            "value": bt_summary if bt_summary else "אין מספיק עסקאות לבדיקה",
            "wide": "1",
        }
    )
    return cubes


def build_offer_action_cubes(
    rec: dict[str, Any],
    *,
    cash_free: float,
    suggested_usd: float,
    swap: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Cash / swap / how-to cubes — merged into the metrics PNG (no second message)."""
    sym = str(rec.get("symbol") or "")
    score = float(rec.get("score") or rec.get("score_technical") or 0)
    cubes: list[dict[str, str]] = []

    if cash_free >= 1 and suggested_usd >= 1:
        cubes.append(
            {
                "title": "מזומן וקנייה",
                "blurb": "אפשר לקנות ממזומן בלי למכור מניה קיימת.",
                "value": (
                    f"${cash_free:.0f} פנוי · מומלץ ${suggested_usd:.0f} · "
                    "כן / קנה / או סכום אחר"
                ),
                "wide": "1",
            }
        )
    else:
        cubes.append(
            {
                "title": "מזומן וקנייה",
                "blurb": "בלי מזומן אי אפשר לאשר קנייה ישירה מההצעה.",
                "value": "$0 פנוי — לא מומלץ כן/קנה ממזומן",
                "wide": "1",
            }
        )

    if swap:
        from_sym = str(swap.get("from_symbol") or "")
        from_score = float(swap.get("from_score") or 0)
        cubes.append(
            {
                "title": "החלפה מומלצת",
                "blurb": "ההצעה חזקה יותר בציונים ממניה שכבר בתיק.",
                "value": (
                    f"החלף {from_sym} {sym} · "
                    f"ציון {from_score:.1f} → {score:.1f}"
                ),
                "wide": "1",
            }
        )

    steps: list[str] = []
    if cash_free >= 1 and suggested_usd >= 1:
        steps.append(f"כן / קנה — ממזומן (${suggested_usd:.0f})")
        steps.append("סכום אחר (150 או קנה 150)")
    if swap:
        steps.append(f"החלף {swap['from_symbol']} {sym}")
    if cash_free < 1 and not swap:
        steps.append("מכור SYMBOL ואז קנה")
    steps.append("דלג — להצעה הבאה")
    cubes.append(
        {
            "title": "איך לבצע",
            "blurb": "שלח בטלגרם אחת מהאפשרויות למטה.",
            "value": " · ".join(steps),
            "wide": "1",
        }
    )
    return cubes


def format_offer_prompt(
    rec: dict[str, Any],
    *,
    cash_free: float,
    suggested_usd: float,
    position_no: int,
    total: int,
    swap: dict[str, Any] | None = None,
) -> str:
    """Text fallback when the cubes PNG cannot be sent."""
    from trading_pulse.agent.strategy_labels import strategy_label
    from trading_pulse.telegram.telegram_format import escape_html

    sym_raw = str(rec.get("symbol") or "")
    sym = escape_html(sym_raw)
    score = float(rec.get("score") or rec.get("score_technical") or 0)
    method = strategy_label(rec) or str(rec.get("strategy_id") or rec.get("strategy") or "").strip()
    lines = [
        f"💡 <b>הצעה {position_no}/{total}: {sym}</b> · ציון <b>{score:.1f}</b>",
    ]
    if method:
        lines.append(f"שיטת כניסה: <b>{escape_html(method)}</b>")

    if cash_free >= 1:
        lines.append(
            f"מזומן פנוי: <b>${cash_free:.0f}</b> · מומלץ ממזומן: <b>${suggested_usd:.0f}</b>"
        )
    else:
        lines.append("מזומן פנוי: <b>$0</b> — אי אפשר לקנות בלי למכור/להחליף")

    if swap:
        from_sym = escape_html(str(swap["from_symbol"]))
        from_score = float(swap.get("from_score") or 0)
        lines.append(
            f"🔁 מומלץ להחליף: <b>{from_sym}</b> (ציון {from_score:.1f}) → "
            f"<b>{sym}</b> ({score:.1f})"
        )

    lines.append("")
    lines.append("✅ איך לבצע:")
    if cash_free >= 1 and suggested_usd >= 1:
        lines.append(
            f"<code>כן</code> / <code>קנה</code> — ממזומן (${suggested_usd:.0f})"
        )
        lines.append("סכום (למשל <code>150</code> או <code>קנה 150</code>) — סכום אחר")
    if swap:
        from_raw = str(swap["from_symbol"])
        lines.append(
            f"<code>החלף {escape_html(from_raw)} {sym}</code> — "
            f"מוכר {escape_html(from_raw)} וקונה {sym}"
        )
    if cash_free < 1 and not swap:
        lines.append("אין מימון מתאים מהתיק — <code>מכור SYMBOL</code> ואז קנה, או דלג")
    lines.append("<code>דלג</code> — להצעה הבאה")
    return "\n".join(lines)


def send_offer(cfg: Any, state: dict[str, Any], plan: dict[str, Any]) -> bool:
    """Send chart + one cubes card (metrics + actions). Text only if cubes fail."""
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
    cash = cash_remaining(plan, po)
    suggested = suggested_amount(plan, po)
    from trading_pulse.agent.holdings_review import swap_funding_for_offer

    swap = swap_funding_for_offer(plan, str(symbol))
    from trading_pulse.telegram.reply_cards import (
        chart_with_recommendation_details,
        offer_cubes_card,
    )

    try:
        speculative = plan.get("risk_profile") == "speculative"
        signal_lines = format_rec_signal_block(rec, speculative).splitlines()
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

    cubes_sent = False
    try:
        cubes_img = offer_cubes_card(
            rec,
            position_no=position_no,
            total=total,
            cash_free=cash,
            suggested_usd=suggested,
            rank=position_no,
            swap=swap,
        )
        if cubes_img:
            # Caption stays tiny — actions live inside the PNG cubes.
            send_telegram_photo(
                cfg,
                cubes_img,
                f"הצעה {position_no}/{total} {symbol}",
                context=f"offer:cubes:{symbol}",
                parse_mode="HTML",
            )
            cubes_sent = True
    except Exception as ex:
        logging.warning("Offer cubes for %s failed: %s", symbol, ex)

    if not cubes_sent:
        text = format_offer_prompt(
            rec,
            cash_free=cash,
            suggested_usd=suggested,
            position_no=position_no,
            total=total,
            swap=swap,
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
        m = _BUY_AMOUNT_RE.match(raw)
        if m:
            named_sym = (m.group(1) or "").upper()
            if named_sym and named_sym != str(symbol).upper():
                # Explicit different ticker — leave for normal `קנה SYMBOL` handling.
                return False
            try:
                amount = float(m.group(2).replace(",", "."))
            except ValueError:
                return False
            if amount <= 0:
                return False
            decision = "buy"
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
        if amount < 1:
            from trading_pulse.agent.holdings_review import swap_funding_for_offer
            from trading_pulse.telegram.telegram_format import escape_html

            sym_e = escape_html(str(symbol))
            swap = swap_funding_for_offer(plan, str(symbol))
            if swap:
                from_raw = str(swap["from_symbol"])
                send_user_notification(
                    cfg,
                    f"אין מזומן פנוי לקניית <b>{sym_e}</b>.\n"
                    f"מומלץ: <code>החלף {escape_html(from_raw)} {sym_e}</code>\n"
                    "או שלח <code>דלג</code> להצעה הבאה.",
                    context="offer:needs_swap",
                    parse_mode="HTML",
                )
            else:
                send_user_notification(
                    cfg,
                    f"אין מזומן פנוי לקניית <b>{sym_e}</b>.\n"
                    "מכור מניה קודם (<code>מכור SYMBOL</code>) או שלח <code>דלג</code>.",
                    context="offer:no_cash",
                    parse_mode="HTML",
                )
            return True
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

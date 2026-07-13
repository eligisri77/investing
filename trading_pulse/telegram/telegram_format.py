"""Clean Telegram message formatting (HTML)."""

from __future__ import annotations

import re
from typing import Any

SEP = "--------------------"

TELEGRAM_MAX_HEADLINES = 1
TELEGRAM_HTML_MAX_LEN = 3800


def chunk_telegram_html(parts: list[str]) -> list[str]:
    """Join HTML sections and split into Telegram-safe message chunks."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for raw in parts:
        part = raw.strip()
        if not part:
            continue
        add_len = len(part) + (2 if current else 0)
        if current and current_len + add_len > TELEGRAM_HTML_MAX_LEN:
            chunks.append("\n\n".join(current))
            current = [part]
            current_len = len(part)
        else:
            current.append(part)
            current_len += add_len
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def user_guide_step1() -> str:
    """Buy picks — allocation is automatic when cash is available."""
    return "\n".join(
        [
            "<b>📝 פקודה אחת:</b>",
            "✅ <code>התחל</code> — קונה את התיק המומלץ",
            "✅ <code>מכור SYMBOL</code> — כשצריך מזומן לקנייה חדשה",
            "✅ <code>החלף X Y</code> — מכירה + קנייה בפעולה אחת",
        ]
    )


def user_guide_step2() -> str:
    """Legacy manual allocation — only when advanced split is needed."""
    return "\n".join(
        [
            "<b>📝 חלוקה ידנית (רק אם נשלחה):</b>",
            "✅ <code>ח1</code> — שווה בין המאושרות",
            "✅ <code>ח4</code> — לפי תוכנית + מזומן למחר",
            "✅ <code>חלוקה</code> — להציג שוב",
        ]
    )


def user_guide_done() -> str:
    return "\n".join(
        [
            "<b>✅ הקנייה בוצעה.</b>",
            "התיק שלך מעודכן — אין צורך לעשות כלום עד דוח הערב.",
            "לבדיקה: <code>תיק</code> · <code>סטטוס</code>",
        ]
    )


def format_pre_sim_reminder(minutes: int, kind: str) -> str:
    mins = max(0, int(minutes))
    if kind == "allocation":
        action = "שלח <code>הכל</code> לאישור (או בחר חלוקה ידנית אם נשלחה)"
    else:
        action = "שלח <code>הכל</code> לאישור · אם אין מזומן — <code>מכור SYMBOL</code> קודם"
    return "\n".join(
        [
            f"⏰ <b>תזכורת</b> — נשארו <b>{mins}</b> דקות עד סגירת השוק",
            action,
            "",
            "<i>אפשר גם בדשבורד: תוכנית פעילה (#/plan)</i>",
        ]
    )


def user_guide_full() -> str:
    return "\n".join(
        [
            "<b>📖 איך זה עובד — פשוט</b>",
            "",
            "1. <code>התחל</code> / <code>הכל</code> — עד 4 מניות עיקריות + שרוול שיטה 2",
            "2. בערב — ציון + Rising Three + שיטה 2 (1/2/3) עם מעקב שעתי",
            "3. בערב אחרי סגירה — דוח יומי על הרווח/הפסד",
            "",
            "אין מזומן? <code>מכור 1 $100</code> (רק חלק) · <code>מכור 1</code> (הכל)",
            "קנייה ממזומן: <code>תקנה 1 $20</code> · <code>קנה BEAM $50</code>",
            "החלפה חלקית: <code>מכור 1 תקנה 2 $100</code>",
            "שני סכומים: <code>מכור 1 200$ קנה 2 100$</code>",
            "ניתוח מניה: <code>מניה NVDA</code> · <code>ציון AAPL</code>",
            "מעקב שעתי: <code>ציון שעתי AAPL</code> · <code>הפסק מעקב AAPL</code>",
            "",
            "<code>תיק</code> · <code>סטטוס</code> · <code>מדריך</code>",
        ]
    )


def format_start_investing_reply(result: dict[str, Any]) -> str:
    status = result.get("status", "")
    if status in {"bought", "already_bought"}:
        title = "<b>✅ קנית — בתיק</b>"
    elif status in {"confirmed_pending_entry", "already_ready"}:
        title = "<b>✅ מאושר — ממתין לפתיחת השוק</b>"
    else:
        title = "<b>📋 תיק</b>"
    msg = escape_html(str(result.get("message", "")))
    lines = [title, "", msg]
    entry_when = result.get("entry_when")
    if entry_when and status in {"confirmed_pending_entry", "already_ready", "approved_pending_entry"}:
        lines.append(f"⏰ כניסה לשוק: <b>{escape_html(entry_when)}</b>")
    syms = result.get("symbols") or []
    entries = result.get("entries") or []
    if entries:
        lines.append("")
        for e in entries:
            lines.append(
                f"• <b>{escape_html(e['symbol'])}</b> "
                f"${float(e['capital_usd']):.0f} @ ${float(e['entry_price']):.2f}"
            )
    elif syms and status not in {"approved_pending_entry", "already_ready"}:
        lines.append("")
        lines.append(" · ".join(f"<b>{escape_html(s)}</b>" for s in syms))
    if status in {"bought", "already_bought"}:
        lines.extend(["", user_guide_done()])
    return finalize("\n".join(lines))


def user_guide_invalid_allocation() -> str:
    return "\n".join(
        [
            "⚠️ <b>אופציה לא תקינה</b>",
            "שלח בדיוק אחת מהאפשרויות:",
            "<code>ח1</code> <code>ח2</code> <code>ח3</code> <code>ח4</code> <code>ח5</code>",
            "",
            user_guide_step2(),
        ]
    )


def user_guide_bare_digit_allocation(option_id: int) -> str:
    """User sent 1–5 during step 2 instead of ח1–ח5."""
    return (
        f"ℹ️ <b>קיבלתי כ־<code>ח{option_id}</code></b> — "
        f"בפעם הבאה שלח <code>ח{option_id}</code> עם אות <b>ח'</b>, לא רק המספר."
    )


def user_guide_invalid_approve() -> str:
    return "\n".join(
        [
            "⚠️ <b>לא מצאתי מספרים תקינים</b>",
            "",
            user_guide_step1(),
        ]
    )


def escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def truncate(text: str, max_len: int = 70) -> str:
    cleaned = re.sub(r"\s+", " ", str(text).strip())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def finalize(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return truncate(text, limit - 1)


def format_scan_summary(plan: dict[str, Any], *, html: bool = True) -> str:
    """Human-readable scan funnel: tickers → signal pass → quality pass → picks."""
    stats = plan.get("scan_stats") or {}
    tickers = int(stats.get("tickers_scanned", 0))
    before = int(stats.get("before_quality", 0))
    after = int(stats.get("after_quality", 0))
    recs = len(plan.get("recommendations") or [])
    min_score = stats.get("min_entry_score")
    min_vol = stats.get("min_volume_ratio")

    if tickers <= 0 and before <= 0:
        return ""

    def _fmt(label: str, value: str) -> str:
        if html:
            return f"• {escape_html(label)}: <b>{escape_html(value)}</b>"
        return f"• {label}: {value}"

    lines: list[str] = []
    if tickers > 0:
        lines.append(_fmt("נסרקו מניות", str(tickers)))
    if tickers > 0 or before > 0:
        lines.append(_fmt("עברו סינון אותות", str(before)))
    if min_vol:
        vol_label = f"נפח לפחות {float(min_vol):.1f}× או פריצה"
        lines.append(_fmt("תנאי כניסה", vol_label))
    if min_score:
        lines.append(_fmt("סף ציון", f"מינימום {float(min_score):.0f}"))
    lines.append(_fmt("עברו סינון איכות", str(after)))
    lines.append(_fmt("המלצות", str(recs)))

    if recs == 0 and before == 0 and tickers > 0:
        lines.append(
            "<i>אף מניה לא עברה נפח/פריצה, מקורות או נזילות.</i>"
            if html
            else "אף מניה לא עברה נפח/פריצה, מקורות או נזילות."
        )
    elif recs == 0 and after == 0 and before > 0:
        top = stats.get("top_skipped_scores") or []
        if top:
            names = ", ".join(f"{r['symbol']} ({r['score']:.1f})" for r in top[:3])
            detail = f"הציונים הגבוהים: {names}"
            lines.append(f"<i>{escape_html(detail)}</i>" if html else detail)

    return "\n".join(lines)


def format_weekly_watchlist(result: dict[str, Any]) -> str:
    """Summary of the weekly watchlist selection for Telegram."""
    week = escape_html(str(result.get("week", "")))
    selected = int(result.get("selected", 0))
    scanned = int(result.get("scanned", 0))
    universe = int(result.get("universe_size", 0))
    symbols = result.get("symbols") or []
    lines = [
        f"<b>🗓️ רשימת המסחר לשבוע {week}</b>",
        SEP,
        f"נסרקו <b>{scanned}</b> מתוך {universe} · נבחרו <b>{selected}</b>",
        "",
        escape_html(", ".join(symbols)),
        "",
        "<i>התוכנית היומית תיסרק רק על הרשימה הזו. אפשר לערוך עם</i> "
        "<code>הוסף SYMBOL</code> / <code>הסר SYMBOL</code>.",
    ]
    return finalize("\n".join(lines))


_VERDICT_META = {
    "hold": ("🟢", "החזק"),
    "sell": ("🔴", "מכור"),
    "swap": ("🔄", "החלף"),
    "take_profit": ("💰", "ממש רווח"),
}


def _held_symbol_set(holdings: list[dict[str, Any]]) -> set[str]:
    return {str(h["symbol"]) for h in holdings}


def format_current_holdings(holdings: list[dict[str, Any]]) -> list[str]:
    """What the user owns right now — invested $ per symbol."""
    if not holdings:
        return []
    lines = ["<b>💼 התיק שלך עכשיו</b>"]
    total = 0.0
    for h in holdings:
        sym = escape_html(str(h["symbol"]))
        cap = float(h.get("capital_usd", 0))
        total += cap
        entry = h.get("entry_price")
        days = int(h.get("days_held", 0))
        entry_txt = f" @ ${float(entry):.2f}" if entry else ""
        lines.append(f"• <b>{sym}</b> — <b>${cap:.0f}</b> מושקע{entry_txt} · {days} ימים")
    lines.append(f"סה\"כ מושקע: <b>${total:.0f}</b>")
    return lines


def format_holding_actions(
    actions: list[dict[str, Any]],
    holdings: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Evening decision: hold / sell / swap per open position, with $ amounts."""
    if not actions:
        return []
    cap_by_sym = {str(h["symbol"]): float(h.get("capital_usd", 0)) for h in (holdings or [])}
    lines = ["<b>📊 מה לעשות עם מה שיש לך</b>"]
    for a in actions:
        sym = escape_html(str(a.get("symbol", "")))
        verdict = str(a.get("verdict", "hold"))
        icon, label = _VERDICT_META.get(verdict, ("🟢", "החזק"))
        pnl = float(a.get("pnl_pct", 0))
        cap = float(a.get("capital_usd") or cap_by_sym.get(str(a.get("symbol", "")), 0))
        cap_txt = f" · <b>${cap:.0f}</b> מושקע" if cap > 0 else ""
        head = f"{icon} <b>{sym}</b>{cap_txt} · {pnl:+.1f}% · <b>{label}</b>"
        reason = escape_html(str(a.get("reason", "")))
        lines.append(f"{head} — {reason}")
        if verdict == "swap" and a.get("swap_to"):
            to_sym = escape_html(str(a["swap_to"]))
            lines.append(
                f"   ↳ מוכר <b>${cap:.0f}</b> מ-{sym} → קונה <b>{to_sym}</b> · "
                f"<code>החלף {sym} {to_sym}</code>"
            )
        elif verdict in {"sell", "take_profit"}:
            lines.append(f"   ↳ מוכר <b>${cap:.0f}</b> מ-{sym} · <code>מכור {sym}</code>")
    return lines


def format_new_picks_block(recs: list[dict[str, Any]], holdings: list[dict[str, Any]]) -> list[str]:
    """Separate truly new buys from symbols already in the portfolio."""
    held = _held_symbol_set(holdings)
    new_recs = [r for r in recs if str(r["symbol"]) not in held]
    dup_recs = [r for r in recs if str(r["symbol"]) in held]

    lines: list[str] = []
    if dup_recs:
        lines.extend(["", "<b>ℹ️ כבר בתיק שלך — לא צריך לקנות שוב</b>"])
        for r in dup_recs:
            sym = escape_html(str(r["symbol"]))
            h = next((x for x in holdings if str(x["symbol"]) == r["symbol"]), {})
            cap = float(h.get("capital_usd", r.get("capital_usd", 0)))
            lines.append(f"• <b>{sym}</b> — ${cap:.0f} מושקע · ממשיך להחזיק")

    if new_recs:
        lines.extend(["", f"<b>🆕 קניות חדשות למחר ({len(new_recs)})</b>"])
        for idx, r in enumerate(new_recs, 1):
            sym = escape_html(str(r["symbol"]))
            strat = str(r.get("strategy") or "")
            tag = ""
            if strat == "method2":
                trig = escape_html(str(r.get("trigger") or ""))
                tag = f" · <i>שיטה 2 · {trig}</i>"
            elif strat == "rising_three_methods":
                weak = " · חלש" if r.get("pattern_weak") else ""
                tag = f" · <i>נרות{weak}</i>"
            lines.append(
                f"#{idx} <b>{sym}</b> — <b>${float(r['capital_usd']):.0f}</b> "
                f"@ ~${float(r.get('entry_ref_price', 0)):.2f}{tag}"
            )
        if held:
            lines.append("<i>לא מחליף מניות קיימות — רק מוסיף מזומן פנוי</i>")
    elif recs and not dup_recs:
        symbols = " · ".join(
            f"<b>#{idx} {escape_html(rec['symbol'])}</b> (${float(rec['capital_usd']):.0f})"
            for idx, rec in enumerate(recs, start=1)
        )
        lines.extend(["", f"<b>🆕 {len(recs)} המלצות</b>", symbols])
    return lines


def format_what_all_does(
    intent: str,
    recs: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    free: float,
) -> list[str]:
    """Plain-language explanation of what «הכל» will do."""
    held = _held_symbol_set(holdings)
    new_recs = [r for r in recs if str(r["symbol"]) not in held]
    lines = ["", "<b>📌 מה קורה בלחיצת «הכל»?</b>"]

    if intent == "first_investment":
        total = sum(float(r.get("capital_usd", 0)) for r in recs)
        lines.append(
            f"קונה {len(recs)} מניות חדשות · סה\"כ <b>${total:.0f}</b> · בפתיחת וול סטריט"
        )
    elif intent == "add_needs_sell":
        lines.append("אין מספיק מזומן — קודם <code>מכור SYMBOL</code>, אחר כך «הכל»")
    elif new_recs:
        buys = " · ".join(
            f"{escape_html(str(r['symbol']))} ${float(r['capital_usd']):.0f}" for r in new_recs
        )
        lines.append(f"קונה: <b>{buys}</b> ממזומן פנוי (${free:.0f})")
        if held:
            lines.append(f"נשאר ללא שינוי: <b>{escape_html(', '.join(sorted(held)))}</b>")
        lines.append("בפתיחת וול סטריט למחר")
    elif held:
        lines.append("אין קניות חדשות — המשך להחזיק את התיק")
    else:
        lines.append("מאשר כניסה בפתיחת השוק למחר")

    lines.append("החלפה ידנית: <code>החלף X Y</code> או <code>למכור X ולקנות Y</code>")
    return lines


def format_buy_reply(
    symbol: str,
    *,
    bought_usd: float,
    entry_price: float,
    cash: float,
    added_to_existing: bool = False,
) -> str:
    action = "הוספת ל" if added_to_existing else "קנית"
    return finalize(
        "\n".join(
            [
                f"✅ <b>{action} {escape_html(symbol)}</b> — <b>${bought_usd:.0f}</b> @ ${entry_price:.2f}",
                f"מזומן פנוי: <b>${cash:.0f}</b>",
                "",
                "<code>תיק</code> לראות את המספרים המעודכנים",
            ]
        )
    )


def format_sell_reply(
    symbol: str,
    *,
    fraction: float,
    pnl_usd: float,
    cash: float,
    target_symbol: str | None = None,
    target_usd: float | None = None,
) -> str:
    sign = "+" if pnl_usd >= 0 else ""
    pct = int(round(fraction * 100))
    lines = [
        f"✅ <b>מכרת {escape_html(symbol)}</b> ({pct}%)",
        f"רווח/הפסד ממומש: <b>{sign}${abs(pnl_usd):.2f}</b>",
        f"מזומן פנוי: <b>${cash:.0f}</b>",
    ]
    if target_symbol and target_usd:
        lines.append(
            f"לקניית <b>{escape_html(target_symbol)}</b>: שלח "
            f"<code>החלף {escape_html(symbol)} {escape_html(target_symbol)}</code> "
            f"(~${target_usd:.0f})"
        )
    else:
        lines.append("לקנייה חדשה: <code>החלף X Y</code> או אשר תוכנית עם «הכל»")
    return finalize("\n".join(lines))


def format_swap_completed(
    *,
    from_symbol: str,
    to_symbol: str,
    sold_usd: float,
    entry_price: float,
    bought_usd: float,
    cash: float,
) -> str:
    return finalize(
        "\n".join(
            [
                "🔄 <b>החלפה הושלמה</b>",
                f"מכרת <b>{escape_html(from_symbol)}</b> — <b>${sold_usd:.0f}</b>",
                f"קנית <b>{escape_html(to_symbol)}</b> — <b>${bought_usd:.0f}</b> "
                f"@ ${entry_price:.2f}",
                f"מזומן פנוי: <b>${cash:.0f}</b>",
            ]
        )
    )


def format_plan(plan: dict[str, Any], *, rec_formatter) -> str:
    """Format daily plan overview for Telegram (details sent per stock)."""
    day = escape_html(plan.get("for_trading_day", ""))
    recs = plan.get("recommendations", [])
    equity = float(plan.get("equity_snapshot", 0))
    free = float(plan.get("available_capital_usd", 0))
    invested = float(plan.get("deployed_capital_usd", 0))
    holdings = plan.get("holdings") or []
    actions = plan.get("holding_actions") or []
    intent = plan.get("flow_intent", "")

    lines = [
        "<b>📋 תוכנית למחר</b>",
        f"<b>יום מסחר:</b> {day}",
        "",
        f"💼 מזומן <b>${free:.0f}</b> · מושקע <b>${invested:.0f}</b> · סה\"כ <b>${equity:.0f}</b>",
    ]
    if plan.get("monthly_target_summary"):
        lines.append(escape_html(truncate(plan["monthly_target_summary"], 100)))

    if not recs:
        if holdings:
            lines.append("")
            if actions:
                lines.extend(format_holding_actions(actions, holdings))
            else:
                lines.append("<b>📂 מחזיקים — אין כניסות חדשות</b>")
                for h in holdings:
                    lines.append(
                        f"• <b>{escape_html(h['symbol'])}</b> "
                        f"${float(h['capital_usd']):.0f} · {h['days_held']} ימים"
                    )
        else:
            lines.extend(["", "🔍 <b>אין המלצות היום</b>"])
            summary = format_scan_summary(plan, html=True)
            if summary:
                lines.extend(["", "<b>📊 סיכום סריקה</b>", summary])
            reason = plan.get("no_picks_reason")
            if reason and not (plan.get("scan_stats") or {}).get("top_skipped_scores"):
                lines.append(escape_html(str(reason)))
        return finalize("\n".join(lines))

    if intent == "first_investment":
        each = round(free / max(len(recs), 1))
        lines.extend(
            [
                "",
                f"<b>🌟 יום ראשון — חלק ${equity:.0f} על {len(recs)} מניות</b>",
                f"בערך <b>${each:.0f}</b> לכל מניה",
            ]
        )
    elif intent == "add_needs_sell":
        gap = plan.get("funding") or {}
        target = escape_html(str(gap.get("target_symbol", recs[0]["symbol"])))
        target_usd = float(next((r["capital_usd"] for r in recs if r["symbol"] == gap.get("target_symbol")), recs[0]["capital_usd"]))
        lines.extend(
            [
                "",
                f"<b>💡 רוצה לקנות {target}</b> — חסר מזומן (${free:.0f} פנוי, צריך ${target_usd:.0f})",
                f"חסר עוד <b>${float(gap.get('gap_usd', 0)):.0f}</b>",
                "",
                "<b>מה למכור כדי לפנות מקום?</b>",
            ]
        )
        for s in (gap.get("sell_suggestions") or [])[:3]:
            lines.append(
                f"• מכור <b>${float(s['sell_usd']):.0f}</b> מ-{escape_html(s['symbol'])} "
                f"({float(s['sell_pct']):.0f}% מהפוזיציה) · "
                f"<code>מכור {escape_html(s['symbol'])}</code>"
            )
        lines.append(
            f"• או החלף בפעולה אחת: "
            f"<code>החלף {escape_html((gap.get('sell_suggestions') or [{}])[0].get('symbol', ''))} {target}</code>"
        )

    if holdings:
        lines.append("")
        lines.extend(format_current_holdings(holdings))
        if actions:
            lines.append("")
            lines.extend(format_holding_actions(actions, holdings))

    if plan.get("fallback_pick"):
        lines.extend(
            [
                "",
                "<b>⚠️ אין מניה שעברה את סף האיכות</b>",
                "<i>הטובה ביותר היום (מתחת לסף) — לשיקולך בלבד</i>",
            ]
        )

    lines.extend(format_new_picks_block(recs, holdings))
    lines.extend(format_what_all_does(intent, recs, holdings, free))
    lines.extend(
        [
            "",
            "<i>פרטים + גרף לכל מניה ↓</i>",
            "",
            SEP,
            "<b>⏰ מחר בפתיחת וול סטריט</b> — כניסה במחיר פתיחה",
            "<b>בערב</b> — דוח יומי",
            "",
            "לאישור: <code>הכל</code>",
        ]
    )
    return finalize("\n".join(lines))


def format_funding_prompt(plan: dict[str, Any], gap: dict[str, Any], *, trading_day: str) -> str:
    target = escape_html(str(gap.get("target_symbol", "")))
    lines = [
        "<b>💰 אין מספיק מזומן לקנייה</b>",
        f"<b>יום מסחר:</b> {escape_html(trading_day)}",
        "",
        f"רוצה <b>{target}</b> · חסר <b>${float(gap.get('gap_usd', 0)):.0f}</b>",
        f"מזומן פנוי: <b>${float(gap.get('cash_free_usd', 0)):.0f}</b>",
        "",
        "<b>מכור חלק ממה שמחזיקים:</b>",
    ]
    for s in gap.get("sell_suggestions") or []:
        lines.append(
            f"• <code>מכור {escape_html(s['symbol'])}</code> "
            f"(${float(s['sell_usd']):.0f})"
            f" או <code>מכור {float(s['sell_pct']):.0f}% {escape_html(s['symbol'])}</code>"
        )
    lines.extend(
        [
            "",
            f"או: <code>החלף SYMBOL {target}</code>",
            "",
            "אחרי מכירה — שלח <code>התחל</code> לקנייה",
        ]
    )
    return finalize("\n".join(lines))


def format_entry_notification(
    entries: list[dict[str, Any]],
    *,
    trading_day: str,
    subtitle: str | None = None,
) -> str:
    if not entries:
        return ""
    title = subtitle or "קנית"
    lines = [
        f"<b>✅ {escape_html(title)} · {escape_html(trading_day)}</b>",
        "",
    ]
    for e in entries:
        extra = ""
        reason = e.get("method2_fill_reason")
        if reason == "daily_level_break":
            extra = " · פריצה יומית"
        elif reason == "micro_trigger":
            iv = escape_html(str(e.get("method2_fill_interval") or "5m"))
            trig = escape_html(str(e.get("method2_micro_trigger") or ""))
            extra = f" · טריגר {iv}" + (f" {trig}" if trig else "")
        side = str(e.get("side") or "LONG").upper()
        side_tag = " שורט" if side == "SHORT" else ""
        lines.append(
            f"• <b>{escape_html(e['symbol'])}</b>{side_tag} "
            f"${float(e['capital_usd']):.0f} @ <b>${float(e['entry_price']):.2f}</b>{extra}"
        )
    lines.extend(["", "דוח סוף יום יישלח אחרי סגירת וול סטריט"])
    return finalize("\n".join(lines))


def format_plan_table_caption(plan: dict[str, Any]) -> str:
    """Caption for the plan summary table image."""
    day = escape_html(plan.get("for_trading_day", ""))
    recs = plan.get("recommendations") or []
    holdings = plan.get("holdings") or []
    held = _held_symbol_set(holdings)
    new_recs = [r for r in recs if str(r["symbol"]) not in held]
    if new_recs:
        picks = " · ".join(
            f"{escape_html(r['symbol'])} ${float(r.get('capital_usd', 0)):.0f}" for r in new_recs
        )
        return (
            f"<b>📋 המלצות {day}</b>\n"
            f"קניות חדשות: {picks}\n"
            "שלח <code>הכל</code> לאישור"
        )
    if recs:
        return f"<b>📋 תוכנית {day}</b>\nשלח <code>הכל</code> לאישור"
    summary = format_scan_summary(plan, html=True)
    if summary:
        return f"<b>📋 תוכנית {day}</b>\n🔍 אין המלצות\n{summary}"
    return f"<b>📋 תוכנית {day}</b>\nאין המלצות היום — אין צורך באישור."


def format_recommendation(
    rec: dict[str, Any],
    idx: int,
    plan: dict[str, Any],
    *,
    signal_lines: list[str],
) -> str:
    """HTML caption for a single recommendation chart image."""
    sym = escape_html(rec["symbol"])
    day = escape_html(plan.get("for_trading_day", ""))
    held = _held_symbol_set(plan.get("holdings") or [])
    draft = float(rec.get("capital_usd", 0))
    price = float(rec.get("entry_ref_price", 0))
    sl = int(float(rec.get("stop_loss_pct", 0)) * 100)
    tp = int(float(rec.get("take_profit_pct", 0)) * 100)
    sl_price = float(rec.get("floor_price") or rec.get("stop_loss_price", 0))
    tp_price = float(rec.get("take_profit_price", 0))

    lines = [
        f"<b>#{idx} {sym}</b> · יום מסחר {day}",
    ]
    if str(rec.get("strategy") or "") == "method2":
        trig = escape_html(str(rec.get("trigger") or ""))
        side = str(rec.get("side") or "LONG").upper()
        side_he = "שורט" if side == "SHORT" else "לונג"
        lines.append(f"<b>שיטה 2 · {side_he} · טריגר {trig}</b>")
        entry = float(rec.get("method2_entry_ref") or rec.get("entry_ref_price") or 0)
        stop = float(rec.get("method2_stop_ref") or rec.get("stop_loss_price") or 0)
        lines.append(f"פריצה ~${entry:.2f} · סטופ ~${stop:.2f} · כניסה רק אם נפרץ")
    elif str(rec.get("strategy") or "") == "rising_three_methods":
        weak = " (חלש)" if rec.get("pattern_weak") else ""
        lines.append(f"<b>נרות · Rising Three Methods{weak}</b>")
    if str(rec["symbol"]) in held:
        lines.append("<b>כבר בתיק — לא נקנה שוב</b>")
    lines.extend(
        [
        f"הצעה <b>${draft:.0f}</b> · מחיר ייחוס <b>${price:.2f}</b>",
        f"מחיר תחתון <b>${sl_price:.2f}</b> (-{sl}%) · מכירה אוטומטית מתחת",
        f"יעד רווח <b>+{tp}%</b> (${tp_price:.2f})",
        "",
        ]
    )
    for line in signal_lines:
        if line.strip():
            lines.append(f"<i>{escape_html(line)}</i>")
    headlines = rec.get("news_headlines", [])[:TELEGRAM_MAX_HEADLINES]
    if headlines:
        title = truncate(headlines[0].get("title", ""), 80)
        if title:
            lines.extend(["", f"📰 {escape_html(title)}"])
    if rec.get("news_summary"):
        lines.append(escape_html(truncate(rec["news_summary"], 120)))
    return finalize("\n".join(lines))


def _approval_buys_and_held(plan: dict[str, Any]) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """New buys vs existing holdings for approval confirmation text."""
    alloc = plan.get("allocation") or {}
    amounts = alloc.get("amounts") or {}
    holdings_raw = alloc.get("holdings") or plan.get("holdings") or []
    held_syms = {str(h["symbol"]) for h in holdings_raw}

    if amounts:
        new_buys = [(str(sym), float(amt)) for sym, amt in amounts.items()]
    else:
        new_buys = [
            (str(r["symbol"]), float(r.get("capital_usd", 0)))
            for r in plan.get("recommendations", []) or []
            if r.get("approved") and str(r["symbol"]) not in held_syms
        ]

    held = [(str(h["symbol"]), float(h.get("capital_usd", 0))) for h in holdings_raw]
    return new_buys, held


def format_approval_reply(
    *,
    trading_day: str,
    picked_symbols: list[str],
    all_approved_symbols: list[str],
    rejected: bool = False,
    allocation_sent: bool = False,
    auto_allocated: bool = False,
    funding_sent: bool = False,
    cfg: Any | None = None,
    trading_day_date: Any | None = None,
    plan: dict[str, Any] | None = None,
) -> str:
    if rejected:
        return (
            f"🚫 <b>בוטל:</b> {escape_html(', '.join(picked_symbols))}\n"
            f"<b>יום:</b> {escape_html(trading_day)}"
        )

    full_confirm = auto_allocated and plan and len(all_approved_symbols) == len(
        plan.get("recommendations") or []
    )
    if full_confirm:
        lines = [
            "<b>✅ תוכנית מאושרת</b>",
            f"<b>יום מסחר:</b> {escape_html(trading_day)}",
        ]
        new_buys, held = _approval_buys_and_held(plan)
        if new_buys:
            lines.extend(["", "<b>🛒 קניות מחר בפתיחה:</b>"])
            for sym, amt in new_buys:
                lines.append(f"• <b>{escape_html(sym)}</b> — <b>${amt:.0f}</b>")
        if held:
            lines.extend(["", "<b>📂 נשאר בתיק (ללא שינוי):</b>"])
            for sym, amt in held:
                lines.append(f"• <b>{escape_html(sym)}</b> — ${amt:.0f} מושקע")
        if not new_buys and held:
            lines.extend(["", "<i>אין קניות חדשות — רק המשך החזקה</i>"])
        elif new_buys and held:
            dup = [s for s, _ in held if s in {b[0] for b in new_buys}]
            if not dup:
                in_rec_not_buy = [
                    str(r["symbol"])
                    for r in plan.get("recommendations", []) or []
                    if r.get("approved") and str(r["symbol"]) in {h[0] for h in held}
                ]
                if in_rec_not_buy:
                    names = ", ".join(in_rec_not_buy)
                    lines.append(
                        f"<i>{escape_html(names)} מופיע בהמלצות אבל כבר בתיק — לא נקנה שוב</i>"
                    )
    else:
        lines = [
            f"<b>✅ מאושר — {escape_html(', '.join(picked_symbols))}</b>",
            f"<b>יום:</b> {escape_html(trading_day)}",
        ]
    if auto_allocated and cfg is not None and trading_day_date is not None:
        from trading_pulse.agent.trading_flow import scheduled_entry_moment

        when = scheduled_entry_moment(cfg, trading_day_date)
        new_buys, _held = _approval_buys_and_held(plan) if plan else ([], [])
        timing = [
            "",
            f"⏰ כניסה לשוק: <b>{escape_html(when)}</b>",
        ]
        if new_buys:
            timing.insert(1, "💰 הקנייה תתבצע בפתיחת השוק")
        elif full_confirm:
            timing.insert(1, "📂 אין קניות חדשות — התיק נשאר כמו שהוא")
        else:
            timing.insert(1, "💰 חולקים את הכסף — הקנייה תתבצע בפתיחת השוק")
        lines.extend(timing)
    elif funding_sent:
        lines.extend(
            [
                "",
                "💰 <b>אין מספיק מזומן</b> — שלח <code>מכור SYMBOL</code> או <code>החלף X Y</code>",
            ]
        )
    elif allocation_sent:
        lines.extend(["", user_guide_step2()])
    else:
        lines.extend(["", user_guide_step1()])
    return "\n".join(lines)


def format_report(report: dict[str, Any]) -> str:
    day = escape_html(report.get("trading_day", ""))
    pnl = float(report.get("pnl_usd", 0))
    pnl_sign = "+" if pnl >= 0 else ""
    lines = [
        f"<b>📊 דוח יומי · {day}</b>",
        SEP,
        f"הון: <code>${report['equity_before']}</code> → <code>${report['equity_after']}</code>",
        f"רווח/הפסד: <b>{pnl_sign}${pnl:.2f}</b>",
    ]
    if report.get("fees_usd"):
        lines.append(f"עמלות: ${float(report['fees_usd']):.2f}")
    unrealized = float(report.get("unrealized_pnl_usd", 0))
    if unrealized or report.get("held_eod"):
        ur_sign = "+" if unrealized >= 0 else ""
        lines.append(f"רווח עתידי (לא ממומש): <b>{ur_sign}${unrealized:.2f}</b>")
        if report.get("equity_marked_usd") is not None:
            lines.append(f"שווי משוער כולל: <code>${float(report['equity_marked_usd']):.2f}</code>")
    if report.get("monthly_target_summary"):
        lines.append(escape_html(truncate(report["monthly_target_summary"], 120)))

    held = report.get("held_eod") or []
    if held:
        lines.extend(["", "<b>📂 עדיין מחזיקים</b>"])
        for pos in held:
            ur = float(pos.get("unrealized_pnl_usd", 0))
            ur_sign = "+" if ur >= 0 else ""
            ur_txt = f" · {ur_sign}${ur:.2f} ({float(pos.get('unrealized_pnl_pct', 0)):+.1f}%)" if pos.get("unrealized_pnl_usd") is not None else ""
            lines.append(
                f"• <b>{escape_html(pos['symbol'])}</b> "
                f"${float(pos['capital_usd']):.0f} · {pos.get('days_held', 0)} ימים{ur_txt}"
            )

    executed = report.get("executed", [])
    if executed:
        lines.extend(["", "<b>✅ נסגרו היום</b>"])
        for t in executed:
            p = float(t.get("pnl_usd", 0))
            sign = "+" if p >= 0 else ""
            reason = {
                "stop_loss": "סטופ",
                "floor_price": "מחיר תחתון",
                "take_profit": "יעד",
                "close": "סגירה",
                "max_hold_days": "מקס ימים",
            }.get(t.get("exit_reason", ""), t.get("exit_reason", ""))
            days = f" · {t['days_held']}י" if t.get("days_held") is not None else ""
            lines.append(
                f"• <b>{escape_html(t['symbol'])}</b> {reason}{days}"
                f" · <b>{sign}${p:.2f}</b> ({float(t.get('pnl_pct', 0)):+.1f}%)"
            )
    elif not held:
        lines.append("\nאין עסקאות היום.")

    return finalize("\n".join(lines))


def format_portfolio(data: dict[str, Any]) -> str:
    from trading_pulse.agent.portfolio_index import attach_slots_to_portfolio
    from trading_pulse.core.schedule_tz import format_local_entry_moment

    data = attach_slots_to_portfolio(data)
    pnl = float(data["total_realized_pnl"])
    unrealized = float(data.get("unrealized_pnl_usd", 0))
    marked = float(data.get("open_marked_usd", data.get("open_capital_usd", 0)))
    sign = "+" if pnl >= 0 else ""
    ur_sign = "+" if unrealized >= 0 else ""
    lines = [
        "<b>💼 תיק השקעות</b>",
        SEP,
        f"הון: <b>${data['equity']:.2f}</b>",
        f"מזומן פנוי: <b>${float(data.get('cash_usd', 0)):.0f}</b>",
        f"שווי פתוח: <b>${marked:.0f}</b> · רווח פתוח: <b>{ur_sign}${unrealized:.2f}</b>",
        f"רווח ממומש: <b>{sign}${pnl:.2f}</b>",
    ]

    open_positions = data.get("open_positions") or []
    pending = [p for p in open_positions if p.get("status") == "pending_market_entry"]
    holding = [p for p in open_positions if p.get("status") == "holding"]
    if pending:
        lines.extend(["", "<b>⏳ מאושר — ממתין לפתיחת השוק</b>"])
        for p in pending:
            sym = escape_html(p["symbol"])
            when = escape_html(str(p.get("scheduled_entry", "פתיחת השוק")))
            approved = format_local_entry_moment(p.get("approved_at"))
            lines.append(
                f"• <b>{sym}</b> ${p['capital_usd']:.0f} · אושר {escape_html(approved)} · כניסה {when}"
            )
    if holding:
        lines.extend(["", "<b>📌 בתיק עכשיו</b>"])
        for i, p in enumerate(holding):
            if i:
                lines.append("")  # blank line between stocks
            sym = escape_html(p["symbol"])
            slot = p.get("slot")
            prefix = f"<b>#{slot}</b> " if slot else ""
            entry = p.get("entry_price")
            when = format_local_entry_moment(p.get("entry_at"))
            price_bit = f" @ <b>${float(entry):.2f}</b>" if entry else ""
            marked_val = float(p.get("marked_value_usd", p.get("capital_usd", 0)))
            ur = float(p.get("unrealized_pnl_usd", 0))
            ur_s = "+" if ur >= 0 else ""
            lines.append(f"{prefix}<b>{sym}</b> ${p['capital_usd']:.0f}{price_bit}")
            lines.append(
                f"→ שווי <b>${marked_val:.0f}</b> ({ur_s}${ur:.0f}) · {escape_html(when)}"
            )
    elif not pending:
        lines.append("\n📌 אין פוזיציות פתוחות")

    by_symbol = data.get("by_symbol") or []
    if by_symbol:
        lines.extend(["", "<b>📊 לפי מניה</b>"])
        for s in by_symbol[:8]:
            ps = "+" if s["total_pnl_usd"] >= 0 else ""
            lines.append(
                f"• <b>{escape_html(s['symbol'])}</b> "
                f"{s['trade_count']} עסק · {ps}${s['total_pnl_usd']:.2f}"
                f" · win {s['win_rate_pct']:.0f}%"
            )

    if holding:
        lines.extend(
            ["", "<i>דוגמאות: מכור 1 $100 · מכור 1 200$ קנה 2 100$ · תקנה 1 $20</i>"]
        )

    return finalize("\n".join(lines))


def format_intraday_monitor(report: Any) -> str:
    """Hourly intraday watch message (alerts + buy/swap suggestions)."""
    lines = [
        "<b>🔍 מעקב שעתי — מסחר פעיל</b>",
        SEP,
    ]

    holdings = report.holdings or []
    if holdings:
        lines.append("<b>📌 מושקע עכשיו</b>")
        for h in holdings[:6]:
            pnl = float(h.get("pnl_pct", 0))
            day = float(h.get("day_change_pct", 0))
            sign = "+" if pnl >= 0 else ""
            cap = float(h.get("capital_usd", 0))
            cap_txt = f"<b>${cap:.0f}</b> מושקע · " if cap > 0 else ""
            floor = h.get("floor_price")
            floor_txt = f" · רף ${float(floor):.2f}" if floor else ""
            lines.append(
                f"• <b>{escape_html(h['symbol'])}</b> — {cap_txt}"
                f"${h.get('last', 0):.2f}{floor_txt} · {sign}{pnl:.1f}% · היום {day:+.1f}%"
            )

    floor_sells = getattr(report, "floor_sells", None) or []
    if floor_sells:
        lines.extend(["", "<b>🔻 נמכר — מחיר תחתון</b>"])
        for trade in floor_sells[:6]:
            pnl = float(trade.get("pnl_usd", 0))
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"• <b>{escape_html(trade['symbol'])}</b> "
                f"${float(trade.get('exit_price', 0)):.2f} · רף ${float(trade.get('floor_price', 0)):.2f} · "
                f"{sign}${abs(pnl):.2f}"
            )

    alerts = report.alerts or []
    if alerts:
        lines.extend(["", "<b>⚠️ חריגות</b>"])
        for alert in sorted(alerts, key=lambda a: -a.severity)[:6]:
            icon = "🔴" if alert.severity >= 3 else "🟠" if alert.severity >= 2 else "🟡"
            lines.append(
                f"{icon} <b>{escape_html(alert.symbol)}</b> — {escape_html(alert.message)}"
            )

    suggestions = report.suggestions or []
    if suggestions:
        lines.extend(["", "<b>💡 הצעות</b>"])
        for sug in suggestions[:3]:
            if sug.kind == "buy":
                lines.append(
                    f"🟢 <b>רכישה</b> · {escape_html(sug.symbol)} — {escape_html(sug.message)}"
                )
            elif sug.kind == "swap":
                lines.append(
                    f"🔄 <b>החלפה</b> · {escape_html(sug.message)}"
                )
            elif sug.kind == "sell":
                lines.append(
                    f"🔻 <b>מכירה</b> · {escape_html(sug.symbol)} — {escape_html(sug.message)}"
                )
            else:
                lines.append(
                    f"👀 <b>לעקוב</b> · {escape_html(sug.symbol)} — {escape_html(sug.message)}"
                )

    lines.extend(
        [
            "",
            "<i>הצעה בלבד — לא ביצוע אוטומטי. להחלפה: שלח את הפקודה המוצעת.</i>",
        ]
    )
    return finalize("\n".join(lines))


def format_heartbeat(cfg: Any, state: dict[str, Any], *, summary_fn, monthly_fn, speculative_fn) -> str:
    from trading_pulse.core.schedule_tz import format_dual_time

    equity = float(state.get("equity", cfg.initial_capital))
    lines = [
        "<b>💚 הסוכן חי</b>",
        SEP,
        f"הון: <b>${equity:.2f}</b>",
        escape_html(truncate(summary_fn(cfg, equity), 100)),
    ]
    if speculative_fn(cfg):
        lines.append(escape_html(truncate(monthly_fn(cfg, state), 120)))
    plan_t = format_dual_time(str(cfg.planning_time)) or str(cfg.planning_time)
    report_t = format_dual_time(str(cfg.market_close_sim_time)) or str(cfg.market_close_sim_time)
    lines.append(f"תוכנית {escape_html(plan_t)}")
    lines.append(f"דוח {escape_html(report_t)}")
    return finalize("\n".join(lines))


def format_reply_plain(text: str) -> str:
    """User-facing command replies (approve/status) — simple plain text."""
    return text

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


def user_guide_full() -> str:
    return "\n".join(
        [
            "<b>📖 איך זה עובד — פשוט</b>",
            "",
            "1. לפני הפתיחה — סקירת תיק בקוביות (או סריקה מלאה בתיק ריק), ואז הצעות אחת-אחת "
            "(גרף → כרטיס קוביות אחד עם מדדים + איך לבצע) · ממזומן: <code>כן</code> / סכום · "
            "או <code>החלף X Y</code> אם הציון חזק יותר · <code>דלג</code>",
            "2. בפתיחה — תמונת כניסה; נרות סיניים 2 ממתינה לפריצה ולא נקנית אוטומטית",
            "3. אין מקום לפוזיציה חדשה אבל יש מזומן פנוי? מעקב שעתי יציע לחזק החזקה קיימת — <code>תקנה SYMBOL</code>",
            "4. בערב אחרי סגירה — כרטיס PNG «דוח יומי» על הרווח/הפסד",
            "",
            "לא ענית להצעה? תזכורת עדינה אחרי ~10 דק׳; בפתיחת השוק — רק «לא נענו» יורדים "
            "(מה שכבר אושר, גם ב־<code>החלף</code>, נשאר) · עדיין אפשר <code>קנה SYMBOL</code> בנפרד",
            "<code>החלף FROM TO</code> כש־TO היא ההצעה הנוכחית = אישור ועוברים הלאה "
            "(מוכר עכשיו · מאשר קנייה בפתיחה — בלי «שלב 2 — חלוקת הון»)",
            "אין מזומן? אם יש מניה חלשה יותר בציונים — <code>החלף PBF SOXL</code> · "
            "אחרת <code>מכור 1 $100</code> / <code>מכור 1</code>",
            "יש מזומן פנוי? אפשר לקנות ממנו או להחליף מניה חלשה · חיזוק: <code>תקנה 1</code> · <code>קנה BEAM $50</code>",
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


def format_nothing_to_approve(plan: dict[str, Any] | None = None) -> str:
    """«הכל» when there are no cash buys left to confirm."""
    plan = plan or {}
    actions = list(plan.get("holding_actions") or [])
    manual = [
        a
        for a in actions
        if str(a.get("verdict")) in {"sell", "swap", "take_profit"}
    ]
    lines = [
        "ℹ️ <b>אין קניות ממזומן לאשר</b>",
        "",
        "<code>הכל</code> מאשר רק קניות חדשות ממזומן — לא מכירות ולא החלפות.",
    ]
    if manual:
        lines.append("")
        lines.append("<b>אם רוצה לפעול ידנית:</b>")
        for a in manual[:4]:
            sym = str(a.get("symbol") or "")
            verdict = str(a.get("verdict") or "")
            if verdict == "swap":
                to_sym = str(a.get("swap_to") or "")
                lines.append(f"· <code>החלף {sym} {to_sym}</code>")
            else:
                lines.append(f"· <code>מכור {sym}</code>")
    else:
        lines.extend(
            [
                "",
                "אין גם פעולה ידנית בתוכנית — אפשר לחכות לדוח/תוכנית הבאה, או לשלוח <code>תיק</code>.",
            ]
        )
    return finalize("\n".join(lines))


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


def format_days_he(value: Any) -> str:
    days = int(value or 0)
    if days == 1:
        return "יום אחד"
    return f"{days} ימים"


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
    """Summary of the weekly watchlist selection for Telegram (HTML fallback)."""
    from trading_pulse.telegram.html_tables import strategy_ids_he

    week = escape_html(str(result.get("week", "")))
    selected = int(result.get("selected", 0))
    scanned = int(result.get("scanned", 0))
    universe = int(result.get("universe_size", 0))
    symbols = result.get("symbols") or []
    sym_names: list[str] = []
    for item in symbols:
        if isinstance(item, dict):
            sym_names.append(str(item.get("symbol") or ""))
        else:
            sym_names.append(str(item))
    sym_names = [s for s in sym_names if s]
    strategies = result.get("strategies_used") or []
    strategy_hits = int(result.get("strategy_hit_symbols", 0) or 0)
    rank = "מומנטום · תנודתיות · נפח"
    if strategies:
        rank += " · אותות אסטרטגיה"
    lines = [
        f"<b>רשימת מסחר לשבוע {week}</b>",
        SEP,
        f"<b>נסרקו בהצלחה:</b> {scanned} מתוך {universe}",
        f"<b>נבחרו לרשימה:</b> {selected}",
        f"<b>דירוג לפי:</b> {rank}",
    ]
    if strategies:
        he = " · ".join(strategy_ids_he(list(strategies)))
        lines.append(f"<b>עם אות אסטרטגיה:</b> {strategy_hits} מתוך {selected}")
        lines.append(f"<b>שיטות שזוהו:</b> {escape_html(he)}")
    preview = sym_names[:10]
    more = max(0, len(sym_names) - len(preview))
    lines.extend(
        [
            "",
            "<b>Top 10 ברשימה</b>",
        ]
    )
    for i, sym in enumerate(preview, start=1):
        lines.append(f"{i}. <code>{escape_html(sym)}</code>")
    if more:
        lines.append(f"<i>ועוד {more} ברשימה המלאה — דשבורד או פקודת מניות</i>")
    lines.extend(
        [
            "",
            "<b>דוגמאות לעריכת הרשימה</b>",
            "<code>הוסף SYMBOL</code> · <code>הסר SYMBOL</code> · <code>מניות</code>",
            "",
            "<i>התוכנית היומית סורקת רק את הרשימה הזו · סריקה אוטומטית: יום ראשון ~09:00 ישראל</i>",
        ]
    )
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
    from trading_pulse.agent.strategy_labels import strategy_suffix_html

    lines = ["<b>💼 התיק שלך עכשיו</b>"]
    total = 0.0
    for h in holdings:
        sym = escape_html(str(h["symbol"]))
        tag = strategy_suffix_html(h)
        cap = float(h.get("capital_usd", 0))
        total += cap
        entry = h.get("entry_price")
        days = int(h.get("days_held", 0))
        entry_txt = f" @ ${float(entry):.2f}" if entry else ""
        lines.append(
            f"• <b>{sym}</b>{tag} — <b>${cap:.0f}</b> מושקע{entry_txt} · "
            f"{format_days_he(days)}"
        )
    lines.append(f"סה\"כ מושקע: <b>${total:.0f}</b>")
    return lines


def format_holding_actions(
    actions: list[dict[str, Any]],
    holdings: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Evening decision: hold / sell / swap per open position, with how-to commands."""
    if not actions:
        return []
    from trading_pulse.agent.strategy_labels import strategy_suffix_html

    cap_by_sym = {str(h["symbol"]): float(h.get("capital_usd", 0)) for h in (holdings or [])}
    strat_by_sym = {str(h["symbol"]): h for h in (holdings or [])}
    lines = [
        "<b>📊 המלצות על התיק הקיים</b>",
        "<i>«הכל» לא מבצע החלפות/מכירות — רק קניות ממזומן. החלפה ידנית למטה.</i>",
    ]
    has_manual = False
    for a in actions:
        sym = escape_html(str(a.get("symbol", "")))
        raw_sym = str(a.get("symbol", ""))
        tag = strategy_suffix_html(strat_by_sym.get(raw_sym) or a)
        verdict = str(a.get("verdict", "hold"))
        icon, label = _VERDICT_META.get(verdict, ("🟢", "החזק"))
        pnl = float(a.get("pnl_pct", 0))
        cap = float(a.get("capital_usd") or cap_by_sym.get(raw_sym, 0))
        cap_txt = f" · <b>${cap:.0f}</b> מושקע" if cap > 0 else ""
        reason = escape_html(str(a.get("reason", "")))
        lines.append(f"{icon} <b>{sym}</b>{tag}{cap_txt} · {pnl:+.1f}% · <b>{label}</b>")
        if reason:
            lines.append(f"   {reason}")
        if verdict == "swap" and a.get("swap_to"):
            to_sym = escape_html(str(a["swap_to"]))
            to_raw = str(a["swap_to"])
            has_manual = True
            lines.append(
                f"   ✅ <b>איך לבצע:</b> שלח "
                f"<code>החלף {raw_sym} {to_raw}</code>"
            )
            lines.append(
                f"   → מוכר ~${cap:.0f} מ-{sym} וקונה <b>{to_sym}</b> במכה אחת"
            )
        elif verdict in {"sell", "take_profit"}:
            has_manual = True
            lines.append(f"   ✅ <b>איך לבצע:</b> שלח <code>מכור {raw_sym}</code>")
            lines.append(f"   → מוכר ~${cap:.0f} מ-{sym} למזומן")
        elif verdict == "hold":
            lines.append("   ✅ אין פעולה — ממשיכים להחזיק")
    if has_manual:
        lines.append(
            "<i>טיפ: אפשר גם <code>מכור SYMBOL $100</code> למכירה חלקית</i>"
        )
    return lines


def _rec_entry_hint(rec: dict[str, Any]) -> str:
    strat = str(rec.get("strategy") or "")
    side = str(rec.get("side") or "LONG").upper()
    if strat == "method2":
        trig = escape_html(str(rec.get("trigger") or ""))
        entry = float(rec.get("method2_entry_ref") or rec.get("entry_ref_price") or 0)
        stop = float(rec.get("method2_stop_ref") or rec.get("floor_price") or 0)
        side_he = "שורט" if side == "SHORT" else "לונג"
        return (
            f"נרות סיניים 2 · {side_he} · טריגר {trig} · "
            f"כניסה רק בפריצה ~${entry:.2f} (סטופ ~${stop:.2f})"
        )
    if strat == "rising_three_methods":
        weak = " · דפוס חלש" if rec.get("pattern_weak") else ""
        return f"נרות Rising Three{weak} · כניסה בפתיחה"
    score = float(rec.get("score") or 0)
    return f"ציון {score:.1f} · כניסה במחיר פתיחה"


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
        lines.extend(["", f"<b>🆕 המלצות קנייה חדשות ({len(new_recs)})</b>"])
        has_method2 = False
        for idx, r in enumerate(new_recs, 1):
            sym = escape_html(str(r["symbol"]))
            raw = str(r["symbol"])
            cap = float(r.get("capital_usd", 0))
            ref = float(r.get("entry_ref_price") or r.get("method2_entry_ref") or 0)
            strat = str(r.get("strategy") or "")
            lines.append(f"#{idx} <b>{sym}</b> — <b>${cap:.0f}</b> @ ~${ref:.2f}")
            lines.append(f"   {_rec_entry_hint(r)}")
            if strat == "method2":
                has_method2 = True
                lines.append(
                    f"   ✅ <b>איך לבצע:</b> שלח <code>הכל</code> "
                    f"(או רק <code>{raw}</code> אם תרצה לאשר בודדת)"
                )
                lines.append(
                    "   → אחרי אישור: כניסה <b>רק אם נפרצת הרמה</b> "
                    "(בוקר או תוך־יום). בלי פריצה — אין כניסה."
                )
            elif r.get("below_bar"):
                lines.append(
                    f"   ⚠️ <b>מתחת לסף האיכות</b> — <code>הכל</code> <b>לא</b> מאשר אוטומטית"
                )
                lines.append(
                    f"   ✅ <b>איך לבצע:</b> שלח <code>{idx}</code> לאישור מפורש "
                    f"(או <code>דחה</code> לדלג)"
                )
                lines.append("   → רק אם אתה מקבל מניה חלשה כיום — לא אות חזק")
            else:
                lines.append(
                    f"   ✅ <b>איך לבצע:</b> שלח <code>הכל</code> "
                    f"(או <code>{raw}</code> לאישור בודד)"
                )
                lines.append("   → מחר בפתיחת וול סטריט ייכנס אוטומטית במחיר פתיחה")
        if any(r.get("below_bar") for r in new_recs):
            lines.append(
                "<i>«הכל» מאשר רק מניות שעברו את הסף — חלשות דורשות מספר מפורש</i>"
            )
        if held:
            lines.append("<i>לא מחליף מניות קיימות אוטומטית — רק מוסיף ממזומן פנוי</i>")
        strong = [r for r in new_recs if not r.get("below_bar")]
        if strong:
            lines.append(
                "<b>סיכום ביצוע:</b> שלח <code>הכל</code> לאישור הקניות שעברו סף"
                + (" · נרות סיניים 2 מחכה לפריצה" if has_method2 else "")
            )
        else:
            lines.append(
                "<b>סיכום ביצוע:</b> אין קניות חזקות ל«הכל» — אשר במספר או דחה"
            )
    elif not dup_recs and not recs:
        pass
    elif recs and not dup_recs and not new_recs:
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
    *,
    actions: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Plain-language explanation of what «הכל» will do vs manual steps."""
    held = _held_symbol_set(holdings)
    new_recs = [r for r in recs if str(r["symbol"]) not in held]
    actions = actions or []
    manual = [
        a
        for a in actions
        if str(a.get("verdict")) in {"swap", "sell", "take_profit"}
    ]
    lines = ["", "<b>📌 איך לבצע — שני מסלולים</b>"]

    lines.append("<b>א. אוטומטי עם «הכל»</b>")
    if intent == "first_investment":
        total = sum(float(r.get("capital_usd", 0)) for r in recs)
        lines.append(
            f"• שלח <code>הכל</code> → קונה {len(recs)} מניות · סה\"כ <b>${total:.0f}</b> בפתיחה"
        )
    elif intent == "add_needs_sell":
        lines.append("• אין מספיק מזומן — קודם מכירה/החלפה, ואז <code>הכל</code>")
    elif new_recs:
        strong = [r for r in new_recs if not r.get("below_bar")]
        weak = [r for r in new_recs if r.get("below_bar")]
        if strong:
            buys = " · ".join(
                f"{escape_html(str(r['symbol']))} ${float(r['capital_usd']):.0f}" for r in strong
            )
            lines.append(f"• שלח <code>הכל</code> → קונה: <b>{buys}</b> ממזומן (${free:.0f})")
        if weak:
            wnames = ", ".join(escape_html(str(r["symbol"])) for r in weak)
            lines.append(
                f"• מתחת לסף ({wnames}): <code>הכל</code> מדלג — אשר במספר מהתוכנית"
            )
        method2 = [r for r in new_recs if str(r.get("strategy")) == "method2"]
        if method2:
            names = ", ".join(escape_html(str(r["symbol"])) for r in method2)
            shorts = [r for r in method2 if str(r.get("side") or "").upper() == "SHORT"]
            side_note = " (כולל שורט — רווח כשהמחיר יורד)" if shorts else ""
            lines.append(
                f"• נרות סיניים 2 ({names}){side_note}: אחרי אישור — כניסה <b>רק אם נפרצת הרמה</b> "
                "(בוקר או תוך־יום), לא חובה בפתיחה"
            )
        if held:
            lines.append(
                f"• התיק הקיים נשאר: <b>{escape_html(', '.join(sorted(held)))}</b>"
            )
        if not strong and not weak:
            lines.append("• אין קניות חדשות ממזומן — <code>הכל</code> לא ישנה את התיק")
    else:
        lines.append("• אין קניות חדשות ממזומן — <code>הכל</code> לא ישנה את התיק")

    lines.append("<b>ב. ידני (החלפה / מכירה)</b>")
    if manual:
        for a in manual[:4]:
            sym = str(a.get("symbol", ""))
            if str(a.get("verdict")) == "swap" and a.get("swap_to"):
                lines.append(
                    f"• <code>החלף {escape_html(sym)} {escape_html(str(a['swap_to']))}</code>"
                )
            else:
                lines.append(f"• <code>מכור {escape_html(sym)}</code>")
        lines.append("<i>אחרי החלפה ידנית אין צורך ב«הכל» לאותה מניה</i>")
    else:
        lines.append(
            "• אין המלצת החלפה היום · בכל זאת אפשר: "
            "<code>החלף X Y</code> / <code>מכור X</code>"
        )
    return lines


def _best_topup_holding(
    holdings: list[dict[str, Any]],
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Pick a held name to suggest topping up with idle cash."""
    if not holdings:
        return None
    actions = actions or []
    by_sym = {str(a.get("symbol")): a for a in actions}
    ranked: list[tuple[float, float, dict[str, Any]]] = []
    for h in holdings:
        sym = str(h.get("symbol") or "")
        if not sym:
            continue
        a = by_sym.get(sym) or {}
        # Prefer holds that aren't sell/swap candidates.
        verdict = str(a.get("verdict") or "hold")
        if verdict in {"sell", "swap"}:
            continue
        score = float(a.get("score") or 0)
        pnl = float(a.get("pnl_pct") if a.get("pnl_pct") is not None else h.get("unrealized_pnl_pct") or 0)
        ranked.append((score, pnl, h))
    if not ranked:
        # All marked sell/swap — still allow top-up of strongest PnL
        for h in holdings:
            pnl = float(h.get("unrealized_pnl_pct") or 0)
            ranked.append((0.0, pnl, h))
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return ranked[0][2]


def format_cash_deploy_advice(
    cash: float,
    holdings: list[dict[str, Any]],
    *,
    actions: list[dict[str, Any]] | None = None,
    new_buy_symbols: set[str] | frozenset[str] | None = None,
    min_cash: float = 20.0,
) -> list[str]:
    """What to do with idle cash — including topping up an existing holding."""
    cash = float(cash or 0)
    if cash < min_cash:
        return []
    holdings = holdings or []
    new_buy_symbols = set(new_buy_symbols or ())
    suggest_usd = int(round(cash)) if cash < 100 else int(round(cash / 5.0) * 5)
    suggest_usd = max(int(min_cash), min(int(cash), suggest_usd))

    lines = [
        "",
        f"<b>💰 יש מזומן פנוי · ${cash:.0f}</b>",
        "<b>מה אפשר לעשות איתו:</b>",
    ]
    if new_buy_symbols:
        lines.append(
            "• אם אישרת קניות חדשות — המזומן ילך אליהן עם <code>הכל</code>"
        )
    top = _best_topup_holding(holdings, actions)
    if top:
        sym = str(top["symbol"])
        slot = top.get("slot")
        if slot:
            cmd = f"תקנה {int(slot)} ${suggest_usd}"
            alt = f"תקנה {sym} ${suggest_usd}"
            lines.append(
                f"• להוסיף ל־<b>{escape_html(sym)}</b> (כבר בתיק): "
                f"שלח <code>{escape_html(cmd)}</code>"
            )
            lines.append(f"  או: <code>{escape_html(alt)}</code>")
        else:
            lines.append(
                f"• להוסיף ל־<b>{escape_html(sym)}</b> (כבר בתיק): "
                f"שלח <code>תקנה {escape_html(sym)} ${suggest_usd}</code>"
            )
        # Second option if another holding exists
        others = [h for h in holdings if str(h.get("symbol")) != sym][:1]
        for h in others:
            o = str(h["symbol"])
            lines.append(
                f"• או למניה אחרת: <code>תקנה {escape_html(o)} ${suggest_usd}</code>"
            )
    elif not new_buy_symbols:
        lines.append(
            f"• לקנות מניה מהרשימה: <code>קנה SYMBOL</code> "
            f"(כל המזומן, ≈${suggest_usd}) או <code>קנה SYMBOL ${suggest_usd}</code>"
        )
    lines.append("• להשאיר במזומן — אין חובה לקנות היום")
    lines.append(
        "<i>טיפ: <code>תקנה 1 $50</code> מוסיף למניה #1 בתיק בלי למכור אחרת</i>"
    )
    return lines


def format_portfolio_review_digest(plan: dict[str, Any]) -> str:
    """Day 2+ pre-market digest: buy-more/sell/swap on holdings + idle-cash advice.

    New-buy candidates are not listed here — they go out one at a time via the
    sequential offer queue right after this digest. Prefer the cubes PNG card;
    this HTML is the short companion / text fallback.
    """
    holdings = plan.get("holdings") or []
    actions = plan.get("holding_actions") or []
    cash = float(plan.get("available_capital_usd", 0) or 0)
    lines = ["<b>📋 סקירת תיק לפני הפתיחה</b>"]
    if not holdings:
        lines.append("אין החזקות פתוחות כרגע.")
    else:
        lines.append(f"מזומן פנוי: <b>${cash:.0f}</b>")
        manual = [
            a for a in actions if str(a.get("verdict")) in {"swap", "sell", "take_profit"}
        ]
        if manual:
            lines.append("")
            lines.append("<b>פעולות מומלצות על התיק:</b>")
            for a in manual:
                sym = str(a.get("symbol") or "")
                my_score = float(a.get("score") or 0)
                if str(a.get("verdict")) == "swap" and a.get("swap_to"):
                    to_raw = str(a["swap_to"])
                    to_score = a.get("swap_to_score")
                    score_bit = f"ציון <b>{my_score:.1f}</b>"
                    if to_score is not None:
                        score_bit += f" → <b>{float(to_score):.1f}</b>"
                    lines.append(
                        f"🔄 <b>{escape_html(sym)}</b> → <b>{escape_html(to_raw)}</b> · {score_bit}"
                    )
                    lines.append(
                        f"   <code>החלף {escape_html(sym)} {escape_html(to_raw)}</code>"
                    )
                elif str(a.get("verdict")) in {"sell", "take_profit"}:
                    lines.append(
                        f"🔴 <b>{escape_html(sym)}</b> · ציון <b>{my_score:.1f}</b>: "
                        f"<code>מכור {escape_html(sym)}</code>"
                    )
        else:
            # Still show scored holdings so the review is visibly about the book.
            scored = [a for a in actions if str(a.get("symbol") or "")]
            if scored:
                lines.append("")
                lines.append("<b>ציוני ההחזקות:</b>")
                for a in scored:
                    sym = escape_html(str(a.get("symbol") or ""))
                    my_score = float(a.get("score") or 0)
                    pnl = float(a.get("pnl_pct") or 0)
                    lines.append(
                        f"🟢 <b>{sym}</b> · ציון <b>{my_score:.1f}</b> · {pnl:+.1f}% — ממשיכים להחזיק"
                    )
            else:
                lines.append("<i>כל ההחזקות במגמה תקינה — ממשיכים להחזיק</i>")

    held_syms = {str(h.get("symbol")) for h in holdings}
    new_recs = [
        r
        for r in (plan.get("recommendations") or [])
        if not r.get("below_bar")
        and not r.get("approved")
        and not r.get("offer_skipped")
        and str(r.get("symbol")) not in held_syms
    ]
    if new_recs:
        n = len(new_recs)
        word = "הצעת קנייה חדשה אחת" if n == 1 else f"{n} הצעות קנייה חדשות"
        lines.append("")
        lines.append(f"<i>יש {word} — נשלח אחת-אחת (עם בדיקת החלפה מול התיק)</i>")
    elif cash >= 20:
        lines.extend(
            format_cash_deploy_advice(cash, holdings, actions=actions, new_buy_symbols=set())
        )
    return "\n".join(lines)


def format_no_new_buys_banner(
    plan: dict[str, Any],
    *,
    holdings: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[str]:
    """Emphasize empty / weak recommendation days."""
    stats = plan.get("scan_stats") or {}
    quality_passed = int(stats.get("after_quality", 0) or 0)
    free = float(plan.get("available_capital_usd", 0))
    slots = int(plan.get("max_trades", 0) or 0)
    capacity = plan.get("capacity") or {}
    blocked_reason = str(capacity.get("blocked_reason") or "")
    quality_text = (
        "מניה אחת עברה את סף האיכות"
        if quality_passed == 1
        else f"{quality_passed} מניות עברו את סף האיכות"
    )
    if quality_passed > 0 and blocked_reason == "no_cash_and_slots":
        explanation = (
            f"⏸️ <b>{quality_text}, אבל אין מזומן ואין מקום בתיק</b>\n"
            f"מזומן פנוי: <b>${free:.0f}</b> · פוזיציות: "
            f"<b>{int(capacity.get('positions_open', 0))}/"
            f"{int(capacity.get('max_positions', 0))}</b>."
        )
    elif quality_passed > 0 and blocked_reason == "no_open_slots":
        explanation = (
            f"⏸️ <b>{quality_text}, אבל התיק מלא</b>\n"
            f"פוזיציות: <b>{int(capacity.get('positions_open', 0))}/"
            f"{int(capacity.get('max_positions', 0))}</b>."
        )
    elif quality_passed > 0 and blocked_reason == "no_cash":
        explanation = (
            f"⏸️ <b>{quality_text}, אבל אין מזומן פנוי</b>\n"
            f"מזומן פנוי: <b>${free:.0f}</b>."
        )
    elif quality_passed > 0 and blocked_reason == "market_regime":
        explanation = (
            f"⏸️ <b>{quality_text}, אבל מסנן מצב השוק עצר כניסות חדשות</b>"
        )
    elif quality_passed > 0 and (slots <= 0 or free < 1):
        explanation = f"⏸️ <b>{quality_text}, אבל לא ניתן לפתוח עסקה חדשה כרגע</b>"
    elif quality_passed > 0:
        explanation = (
            f"<b>{quality_text}</b>, "
            "אך האסטרטגיות הפעילות לא נתנו אות כניסה מתאים."
        )
    else:
        explanation = "<b>אין מניות שעברו את סף האיכות</b>"
    lines = [
        "",
        "🚫 <b>אין המלצות היום לקנייה חדשה</b>",
        explanation,
    ]
    summary = format_scan_summary(plan, html=True)
    if summary:
        lines.extend(["", "<b>📊 למה?</b>", summary])
    reason = plan.get("no_picks_reason")
    if reason and not (plan.get("scan_stats") or {}).get("top_skipped_scores"):
        lines.append(escape_html(str(reason)))

    manual = [a for a in actions if str(a.get("verdict")) in {"swap", "sell", "take_profit"}]
    if manual:
        lines.extend(
            [
                "",
                "<b>✅ יש המלצות על מה שכבר מחזיקים</b> — ראה למעלה איך לבצע "
                "(<code>החלף</code> / <code>מכור</code>).",
                "<i>אין צורך לשלוח «הכל» — אין מה לאשר לקנייה ממזומן.</i>",
            ]
        )
    elif holdings:
        lines.extend(
            [
                "",
                "<b>✅ המלצה:</b> להמשיך להחזיק את התיק עד הזדמנות מחר.",
                "<i>אין צורך באישור אוטומטי — אין קנייה חדשה מהתוכנית.</i>",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "<b>✅ המלצה:</b> לחכות לערב הבא — התיק ריק ואין כניסות.",
                "<i>אין צורך לשלוח «הכל».</i>",
            ]
        )
    lines.extend(
        format_cash_deploy_advice(free, holdings, actions=actions, new_buy_symbols=set())
    )
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
    equity: float | None = None,
    target_symbol: str | None = None,
    target_usd: float | None = None,
    holdings: list[dict[str, Any]] | None = None,
) -> str:
    outcome = "רווח ממומש" if pnl_usd >= 0 else "הפסד ממומש"
    amount = f"+${abs(pnl_usd):.2f}" if pnl_usd >= 0 else f"-${abs(pnl_usd):.2f}"
    pct = int(round(fraction * 100))
    lines = [
        f"✅ <b>מכרת {escape_html(symbol)}</b> ({pct}%)",
        f"{outcome}: <code>{amount}</code>",
        f"מזומן פנוי: <b>${cash:.0f}</b>",
    ]
    if equity is not None:
        lines.append(f"הון לאחר המכירה: <b>${equity:.2f}</b>")
    if target_symbol and target_usd:
        lines.append(
            f"לקניית <b>{escape_html(target_symbol)}</b>: שלח "
            f"<code>החלף {escape_html(symbol)} {escape_html(target_symbol)}</code> "
            f"(~${target_usd:.0f})"
        )
    lines.extend(
        format_cash_deploy_advice(cash, holdings or [], new_buy_symbols=set())
    )
    if not (target_symbol and target_usd) and cash < 20:
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
    holdings: list[dict[str, Any]] | None = None,
    sell_price: float | None = None,
    sell_pnl_usd: float | None = None,
) -> str:
    """Text/inbox fallback — prefer cubes PNG via execute_swap_command."""
    from_s = escape_html(from_symbol)
    to_s = escape_html(to_symbol)
    sell_bits = [f"ערך <b>${sold_usd:.2f}</b>"]
    if sell_price and sell_price > 0:
        sell_bits.append(f"מחיר <b>${sell_price:.2f}</b>")
    if sell_pnl_usd is not None:
        if sell_pnl_usd > 0:
            sell_bits.append(f"רווח <b>+${sell_pnl_usd:.2f}</b>")
        elif sell_pnl_usd < 0:
            sell_bits.append(f"הפסד <b>-${abs(sell_pnl_usd):.2f}</b>")
    buy_bits = [f"ערך <b>${bought_usd:.2f}</b>", f"מחיר <b>${entry_price:.2f}</b>"]
    if entry_price > 0 and bought_usd > 0:
        buy_bits.append(f"≈ <b>{bought_usd / entry_price:.4g}</b> מניות")
    lines = [
        "🔄 <b>החלפה הושלמה</b>",
        f"<b>מכרת {from_s}</b> — {' · '.join(sell_bits)}",
        f"<b>קנית {to_s}</b> — {' · '.join(buy_bits)}",
        f"מזומן פנוי: <b>${cash:.2f}</b>",
    ]
    lines.extend(format_cash_deploy_advice(cash, holdings or [], new_buy_symbols=set()))
    return finalize("\n".join(lines))


def format_plan(plan: dict[str, Any], *, rec_formatter) -> str:
    """Format daily plan overview for Telegram (details sent per stock)."""
    from trading_pulse.core.schedule_tz import format_local_entry_moment

    day = escape_html(plan.get("for_trading_day", ""))
    recs = plan.get("recommendations", [])
    equity = float(plan.get("equity_snapshot", 0))
    free = float(plan.get("available_capital_usd", 0))
    invested = float(plan.get("deployed_capital_usd", 0))
    holdings = plan.get("holdings") or []
    actions = plan.get("holding_actions") or []
    intent = plan.get("flow_intent", "")
    held = _held_symbol_set(holdings)
    new_recs = [r for r in recs if str(r["symbol"]) not in held]

    lines = [
        "<b>📋 תוכנית למחר</b>",
        f"<b>יום מסחר:</b> {day}",
        "",
        f"💼 מזומן <b>${free:.0f}</b> · מושקע <b>${invested:.0f}</b> · סה\"כ <b>${equity:.0f}</b>",
    ]
    generated_at = format_local_entry_moment(plan.get("generated_at"))
    if generated_at != "—":
        lines.append(f"נכון ל־{escape_html(generated_at)} (שעון ישראל)")
    if plan.get("last_manual_action"):
        action = escape_html(str(plan["last_manual_action"]))
        if plan.get("portfolio_snapshot_stale"):
            lines.append(
                f"⚠️ התיק השתנה לאחר {action}. "
                "ההזמנה שכבר אושרה לא שונתה."
            )
        else:
            lines.append(f"🔄 התוכנית עודכנה לאחר {action}.")
    if plan.get("monthly_target_summary"):
        lines.append(escape_html(truncate(plan["monthly_target_summary"], 100)))

    if not recs:
        if holdings:
            lines.append("")
            lines.extend(format_current_holdings(holdings))
            if actions:
                lines.append("")
                lines.extend(format_holding_actions(actions, holdings))
            lines.extend(format_no_new_buys_banner(plan, holdings=holdings, actions=actions))
        else:
            lines.extend(format_no_new_buys_banner(plan, holdings=[], actions=[]))
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
                "<i>מוצגת הטובה ביותר כיום (מתחת לסף) — לשיקולך בלבד, לא אות חזק</i>",
            ]
        )

    lines.extend(format_new_picks_block(recs, holdings))

    if not new_recs:
        # Recommendations exist but all already held, or empty new set
        lines.extend(format_no_new_buys_banner(plan, holdings=holdings, actions=actions))

    lines.extend(format_what_all_does(intent, recs, holdings, free, actions=actions))

    if new_recs:
        lines.extend(
            format_cash_deploy_advice(
                free,
                holdings,
                actions=actions,
                new_buy_symbols={str(r["symbol"]) for r in new_recs},
            )
        )

    footer: list[str] = [
        "",
        "<i>גרף לכל מניה ↓ (פרטים בעברית מתחת לגרף בתמונה · כיתוב קצר)</i>",
        "",
        SEP,
    ]
    if new_recs:
        has_m2 = any(str(r.get("strategy")) == "method2" for r in new_recs)
        footer.append("<b>⏰ מחר</b> — כניסת ציון/נרות בפתיחה")
        if has_m2:
            footer.append("<b>נרות סיניים 2</b> — כניסה רק אם נפרצת הרמה (בוקר או תוך־יום)")
        footer.append("<b>בערב</b> — דוח יומי")
        footer.extend(["", "לאישור קניות ממזומן: <code>הכל</code>"])
    else:
        footer.append("<b>אין קניות ממזומן לאשר</b> — אם יש החלפה למעלה, שלח את הפקודה הידנית")
        footer.append("<b>בערב</b> — דוח יומי")

    lines.extend(footer)
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
        from trading_pulse.agent.strategy_labels import strategy_suffix_html

        tag = strategy_suffix_html(e)
        entry_px = float(e.get("entry_price") or 0)
        lines.append(
            f"• <b>{escape_html(e['symbol'])}</b>{tag}{side_tag} "
            f"${float(e['capital_usd']):.0f} @ <b>${entry_px:.2f}</b>{extra}"
        )
        ref = float(e.get("entry_ref_price") or e.get("evening_ref_price") or 0)
        if ref > 0 and entry_px > 0:
            gap_pct = (entry_px / ref - 1.0) * 100.0
            if abs(gap_pct) >= 3.0:
                lines.append(
                    f"   <i>נפתח בפער מול ייחוס הערב (~${ref:.2f}): "
                    f"{gap_pct:+.1f}%</i>"
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
    actions = plan.get("holding_actions") or []
    has_manual = any(str(a.get("verdict")) in {"swap", "sell", "take_profit"} for a in actions)
    if new_recs:
        picks = " · ".join(
            f"{escape_html(r['symbol'])} ${float(r.get('capital_usd', 0)):.0f}" for r in new_recs
        )
        how = "שלח <code>הכל</code> לאישור קניות"
        if has_manual:
            how += " · החלפות ידניות בטקסט"
        return (
            f"<b>📋 המלצות {day}</b>\n"
            f"קניות חדשות: {picks}\n"
            f"{how}"
        )
    if recs:
        return f"<b>📋 תוכנית {day}</b>\nאין קניות חדשות (כבר בתיק) · פרטים בטקסט"
    summary = format_scan_summary(plan, html=True)
    if summary:
        return (
            f"<b>📋 תוכנית {day}</b>\n"
            f"🚫 <b>אין המלצות קנייה</b>\n{summary}"
        )
    return (
        f"<b>📋 תוכנית {day}</b>\n"
        "🚫 <b>אין המלצות היום</b> — אין צורך באישור."
    )


def format_recommendation(
    rec: dict[str, Any],
    idx: int,
    plan: dict[str, Any],
    *,
    signal_lines: list[str],
) -> str:
    """HTML fallback when chart+details PNG cannot be built (prefer short photo caption)."""
    sym = escape_html(rec["symbol"])
    day = escape_html(plan.get("for_trading_day", ""))
    held = _held_symbol_set(plan.get("holdings") or [])
    draft = float(rec.get("capital_usd", 0))
    price = float(rec.get("entry_ref_price", 0))
    sl_frac = float(rec.get("stop_loss_pct", 0))
    tp_frac = float(rec.get("take_profit_pct", 0))
    sl_price = float(rec.get("floor_price") or rec.get("stop_loss_price", 0))
    tp_price = float(rec.get("take_profit_price", 0))

    lines = [
        f"<b>#{idx} {sym}</b> · יום מסחר {day}",
    ]
    if str(rec.get("strategy") or "") == "method2":
        trig = escape_html(str(rec.get("trigger") or ""))
        side = str(rec.get("side") or "LONG").upper()
        side_he = "שורט" if side == "SHORT" else "לונג"
        lines.append(f"<b>נרות סיניים 2 · {side_he} · טריגר {trig}</b>")
        entry = float(rec.get("method2_entry_ref") or rec.get("entry_ref_price") or 0)
        stop = float(rec.get("method2_stop_ref") or rec.get("stop_loss_price") or 0)
        lines.append(
            f"פריצה ~{_fmt_usd(entry)} · סטופ ~{_fmt_usd(stop)} · כניסה רק אם נפרץ"
        )
    elif str(rec.get("strategy") or "") == "rising_three_methods":
        weak = " (חלש)" if rec.get("pattern_weak") else ""
        lines.append(f"<b>נרות · Rising Three Methods{weak}</b>")
    if str(rec["symbol"]) in held:
        lines.append("<b>כבר בתיק — לא נקנה שוב</b>")
    lines.extend(
        [
            f"הצעה {_fmt_usd(draft, decimals=0)} · מחיר ייחוס {_fmt_usd(price)}",
            (
                f"מחיר תחתון {_fmt_usd(sl_price)} "
                f"({_fmt_signed_pct(-abs(sl_frac * 100))}) · מכירה אוטומטית מתחת"
            ),
            f"יעד רווח {_fmt_signed_pct(abs(tp_frac * 100))} ({_fmt_usd(tp_price)})",
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
        new_buys = [
            (str(sym), float(amt))
            for sym, amt in amounts.items()
            if float(amt) >= 1 and str(sym) not in held_syms
        ]
    else:
        new_buys = [
            (str(r["symbol"]), float(r.get("capital_usd", 0)))
            for r in plan.get("recommendations", []) or []
            if r.get("approved")
            and str(r["symbol"]) not in held_syms
            and float(r.get("capital_usd", 0)) >= 1
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
            "<b>תוכנית מאושרת</b>",
            f"<b>יום מסחר:</b> {escape_html(trading_day)}",
        ]
        new_buys, held = _approval_buys_and_held(plan)
        buy_syms = {s for s, _ in new_buys}
        if new_buys:
            lines.extend(["", "<b>קניות ממזומן — מחר בפתיחה:</b>"])
            for sym, amt in new_buys:
                rec = next(
                    (
                        r
                        for r in (plan.get("recommendations") or [])
                        if str(r.get("symbol")) == sym
                    ),
                    {},
                )
                extra = ""
                strat = str(rec.get("strategy") or rec.get("strategy_id") or "")
                if strat == "method2":
                    trig = escape_html(str(rec.get("trigger") or ""))
                    side = str(rec.get("side") or "LONG").upper()
                    side_he = "שורט" if side == "SHORT" else "לונג"
                    extra = f" · נרות סיניים 2 · {side_he}"
                    if trig:
                        extra += f" · טריגר {trig}"
                    extra += " — כניסה בפריצה בלבד"
                    if side == "SHORT":
                        extra += " · רווח כשהמחיר יורד"
                elif strat in {"rising_three", "rising_three_methods"}:
                    extra = " · Rising Three — כניסה בפתיחה"
                lines.append(f"• <b>{escape_html(sym)}</b> — ${amt:.0f}{extra}")
            if any(
                str(r.get("strategy") or r.get("strategy_id") or "") == "method2"
                for r in (plan.get("recommendations") or [])
                if str(r.get("symbol")) in buy_syms
            ):
                lines.append(
                    "<i>נרות סיניים 2: בלי פריצה בבוקר — נשאר במעקב; אין כניסה אוטומטית</i>"
                )
            lines.append("<i>«הכל» קונה ממזומן בלבד — לא מוכר ולא מחליף</i>")
        if held:
            lines.extend(["", "<b>נשאר בתיק (בלי שינוי אוטומטי):</b>"])
            for sym, amt in held:
                lines.append(f"• <b>{escape_html(sym)}</b> — מושקע ${amt:.0f}")
        live_held = {s for s, _ in held}
        if cfg is not None:
            try:
                live_held |= {
                    str(h.get("symbol"))
                    for h in (plan.get("holdings") or [])
                    if str(h.get("symbol") or "").strip()
                }
            except Exception:
                pass
        pending_actions = [
            a
            for a in (plan.get("holding_actions") or [])
            if str(a.get("verdict")) in {"swap", "sell", "take_profit"}
            and str(a.get("symbol") or "") in live_held
        ]
        if pending_actions and full_confirm:
            lines.extend(
                [
                    "",
                    "<b>מומלץ ידנית (לא בוצע ב«הכל»):</b>",
                    "<i>דוגמאות לפקודות — העתק ושלח אם רלוונטי:</i>",
                ]
            )
            for a in pending_actions[:6]:
                verdict = str(a.get("verdict"))
                raw_sym = str(a.get("symbol") or "")
                sym = escape_html(raw_sym)
                if verdict == "swap":
                    to_raw = str(a.get("swap_to") or "")
                    to_sym = escape_html(to_raw)
                    if to_raw in buy_syms:
                        # Target already bought with cash — don't suggest swap-into it.
                        lines.append(
                            f"• לפנות מקום מ־<b>{sym}</b> — שלח <code>מכור {raw_sym}</code>"
                            f" <i>(לא «החלף ל־{to_sym}» — {to_sym} כבר מאושרת ממזומן)</i>"
                        )
                    else:
                        lines.append(
                            f"• להחליף <b>{sym}</b> → <b>{to_sym}</b> — שלח "
                            f"<code>החלף {raw_sym} {to_raw}</code>"
                        )
                else:
                    lines.append(
                        f"• למכור <b>{sym}</b> — שלח <code>מכור {raw_sym}</code>"
                    )
        if not new_buys and held:
            lines.extend(["", "<i>אין קניות חדשות — רק המשך החזקה</i>"])
        elif new_buys and held:
            dup = [s for s, _ in held if s in buy_syms]
            if not dup:
                in_rec_not_buy = [
                    str(r["symbol"])
                    for r in plan.get("recommendations", []) or []
                    if r.get("approved") and str(r["symbol"]) in {h[0] for h in held}
                ]
                if in_rec_not_buy:
                    names = ", ".join(in_rec_not_buy)
                    lines.append(
                        f"<i>{escape_html(names)} בהמלצות אבל כבר בתיק — לא נקנה שוב</i>"
                    )
    else:
        lines = [
            f"<b>מאושר — {escape_html(', '.join(picked_symbols))}</b>",
            f"<b>יום:</b> {escape_html(trading_day)}",
        ]
    if auto_allocated and cfg is not None and trading_day_date is not None:
        from trading_pulse.agent.trading_flow import scheduled_entry_moment

        when = scheduled_entry_moment(cfg, trading_day_date)
        new_buys, _held = _approval_buys_and_held(plan) if plan else ([], [])
        timing = [""]
        if new_buys:
            timing.append("הקנייה תתבצע בפתיחת השוק")
        elif full_confirm:
            timing.append("אין קניות חדשות — התיק נשאר כמו שהוא")
        else:
            timing.append("חולקים את הכסף — הקנייה תתבצע בפתיחת השוק")
        timing.append(f"<b>כניסה לשוק:</b> {escape_html(when)}")
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
    pnl_outcome = "רווח" if pnl > 0 else ("הפסד" if pnl < 0 else "ללא שינוי")
    pnl_amount = f"+${abs(pnl):.2f}" if pnl > 0 else (f"-${abs(pnl):.2f}" if pnl < 0 else "$0.00")
    lines = [
        f"<b>📊 דוח יומי · {day}</b>",
        SEP,
        f"הון בתחילת היום: <code>${report['equity_before']}</code>",
        f"סה״כ שינוי ממומש היום: <b>{pnl_outcome} {pnl_amount}</b>",
        f"הון בסוף היום: <code>${report['equity_after']}</code>",
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
        from trading_pulse.agent.strategy_labels import strategy_suffix_html

        lines.extend(["", "<b>📂 עדיין מחזיקים</b>"])
        for pos in held:
            ur = float(pos.get("unrealized_pnl_usd", 0))
            ur_sign = "+" if ur >= 0 else ""
            ur_txt = f" · {ur_sign}${ur:.2f} ({float(pos.get('unrealized_pnl_pct', 0)):+.1f}%)" if pos.get("unrealized_pnl_usd") is not None else ""
            tag = strategy_suffix_html(pos)
            lines.append(
                f"• <b>{escape_html(pos['symbol'])}</b>{tag} "
                f"${float(pos['capital_usd']):.0f} · "
                f"{format_days_he(pos.get('days_held', 0))}{ur_txt}"
            )

    executed = report.get("executed", [])
    if executed:
        from trading_pulse.agent.strategy_labels import strategy_suffix_html

        def _append_trade_group(title: str, trades: list[dict[str, Any]]) -> None:
            if not trades:
                return
            lines.extend(["", f"<b>{title}</b>"])
            for trade in trades:
                trade_pnl = float(trade.get("pnl_usd", 0))
                trade_amount = (
                    f"+${abs(trade_pnl):.2f}"
                    if trade_pnl >= 0
                    else f"-${abs(trade_pnl):.2f}"
                )
                reason = {
                    "stop_loss": "סטופ",
                    "floor_price": "מחיר תחתון",
                    "take_profit": "יעד",
                    "close": "סגירה",
                    "max_hold_days": "מקס ימים",
                    "user_sell": "מכירה ידנית",
                }.get(
                    trade.get("exit_reason", ""),
                    trade.get("exit_reason", ""),
                )
                days = (
                    f" · {format_days_he(trade['days_held'])}"
                    if trade.get("days_held") is not None
                    else ""
                )
                tag = strategy_suffix_html(trade)
                lines.append(
                    f"• <b>{escape_html(trade['symbol'])}</b>{tag} {reason}{days}"
                    f" · <code>{trade_amount}</code> "
                    f"({float(trade.get('pnl_pct', 0)):+.1f}%)"
                )

        manual = [
            trade
            for trade in executed
            if trade.get("manual_exit") or trade.get("exit_reason") == "user_sell"
        ]
        automatic = [trade for trade in executed if trade not in manual]
        _append_trade_group("🧾 מכירות ידניות", manual)
        _append_trade_group("✅ נסגרו אוטומטית היום", automatic)
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
    cash = float(data.get("cash_usd", 0))
    lines.extend(
        format_cash_deploy_advice(cash, holding, actions=None, new_buy_symbols=set())
    )
    if pending:
        lines.extend(["", "<b>⏳ מאושר — ממתין לפתיחת השוק</b>"])
        from trading_pulse.agent.strategy_labels import strategy_suffix_html

        for p in pending:
            sym = escape_html(p["symbol"])
            tag = strategy_suffix_html(p)
            when = escape_html(str(p.get("scheduled_entry", "פתיחת השוק")))
            approved = format_local_entry_moment(p.get("approved_at"))
            lines.append(
                f"• <b>{sym}</b>{tag} ${p['capital_usd']:.0f} · אושר {escape_html(approved)} · כניסה {when}"
            )
    if holding:
        lines.extend(["", "<b>📌 בתיק עכשיו</b>"])
        from trading_pulse.agent.strategy_labels import strategy_suffix_html

        for i, p in enumerate(holding):
            if i:
                lines.append("")  # blank line between stocks
            sym = escape_html(p["symbol"])
            tag = strategy_suffix_html(p)
            slot = p.get("slot")
            prefix = f"<b>#{slot}</b> " if slot else ""
            entry = p.get("entry_price")
            when = format_local_entry_moment(p.get("entry_at"))
            price_bit = f" @ <b>${float(entry):.2f}</b>" if entry else ""
            marked_val = float(p.get("marked_value_usd", p.get("capital_usd", 0)))
            ur = float(p.get("unrealized_pnl_usd", 0))
            ur_s = "+" if ur >= 0 else ""
            lines.append(f"{prefix}<b>{sym}</b>{tag} ${p['capital_usd']:.0f}{price_bit}")
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


def _intraday_howto_command(sug: Any) -> str | None:
    """Copy-paste Telegram command for an intraday suggestion."""
    kind = getattr(sug, "kind", "")
    sym = str(getattr(sug, "symbol", "") or "")
    swap_from = getattr(sug, "swap_from", None)
    if kind == "swap" and swap_from and sym:
        return f"החלף {swap_from} {sym}"
    if kind == "buy" and sym:
        return f"תקנה {sym}"
    if kind == "sell" and sym:
        return f"מכור {sym}"
    return None


# Unicode minus — ASCII "-" flips next to Hebrew in Telegram RTL.
_MINUS = "\u2212"
_LRM = "\u200e"


def _ltr_code(text: str) -> str:
    """LTR island via <code> so numbers/tickers stay readable in RTL HTML."""
    return f"<code>{_LRM}{escape_html(text)}{_LRM}</code>"


def _fmt_signed_pct(value: float) -> str:
    x = float(value)
    if x > 0:
        body = f"+{x:.1f}%"
    elif x < 0:
        body = f"{_MINUS}{abs(x):.1f}%"
    else:
        body = "0.0%"
    return _ltr_code(body)


def _fmt_usd(value: float, *, decimals: int = 2, signed: bool = False) -> str:
    x = float(value)
    if signed:
        if x > 0:
            body = f"+${x:.{decimals}f}"
        elif x < 0:
            body = f"{_MINUS}${abs(x):.{decimals}f}"
        else:
            body = f"${0:.{decimals}f}"
    else:
        body = f"${x:.{decimals}f}"
    return _ltr_code(body)


def _fmt_ticker(symbol: str) -> str:
    return f"<b>{_ltr_code(str(symbol).strip().upper())}</b>"


def format_intraday_monitor(report: Any) -> str:
    """Hourly intraday watch message (alerts + buy/swap suggestions).

    Layout rules for Telegram RTL:
    - Ticker alone on the first line of each block (never mid-number line).
    - Hebrew label, then a <code> LTR island for every number/%/$.
    - Unicode minus (U+2212) instead of ASCII hyphen for negatives.
    """
    lines = [
        "<b>🔍 מעקב שעתי — מסחר פעיל</b>",
        SEP,
    ]
    has_howto = False

    holdings = report.holdings or []
    if holdings:
        from trading_pulse.agent.strategy_labels import strategy_method_line

        lines.append("<b>📌 מושקע עכשיו</b>")
        for i, h in enumerate(holdings[:6], start=1):
            pnl = float(h.get("pnl_pct", 0))
            day = float(h.get("day_change_pct", 0))
            cap = float(h.get("capital_usd", 0))
            floor = h.get("floor_price")
            method = strategy_method_line(h)
            # Slot on the right of ticker in RTL: «ISRG 1#»
            lines.append(f"• {_fmt_ticker(str(h['symbol']))} {_ltr_code(f'{i}#')}")
            if method:
                lines.append(f"  <i>{escape_html(method)}</i>")
            if cap > 0:
                lines.append(f"  מושקע: {_fmt_usd(cap, decimals=0)}")
            lines.append(f"  מחיר עכשיו: {_fmt_usd(float(h.get('last', 0)))}")
            if floor:
                lines.append(f"  רף יציאה: {_fmt_usd(float(floor))}")
            marked = cap * (1.0 + pnl / 100.0) if cap else 0.0
            if cap > 0:
                lines.append(f"  שווי נוכחי: {_fmt_usd(marked, decimals=0)}")
            lines.append(f"  מהכניסה: {_fmt_signed_pct(pnl)}")
            lines.append(f"  היום: {_fmt_signed_pct(day)}")

    floor_sells = getattr(report, "floor_sells", None) or []
    if floor_sells:
        lines.extend(["", "<b>🔻 נמכר — מחיר תחתון</b>"])
        for trade in floor_sells[:6]:
            pnl = float(trade.get("pnl_usd", 0))
            lines.append(f"• {_fmt_ticker(str(trade['symbol']))}")
            lines.append(
                f"  יציאה {_fmt_usd(float(trade.get('exit_price', 0)))} · "
                f"רף {_fmt_usd(float(trade.get('floor_price', 0)))}"
            )
            result_word = "רווח" if pnl >= 0 else "הפסד"
            lines.append(f"  {result_word} {_fmt_usd(pnl, signed=True)}")

    alerts = report.alerts or []
    if alerts:
        lines.extend(["", "<b>⚠️ חריגות</b>"])
        for alert in sorted(alerts, key=lambda a: -a.severity)[:6]:
            icon = "🔴" if alert.severity >= 3 else "🟠" if alert.severity >= 2 else "🟡"
            lines.append(
                f"{icon} {_fmt_ticker(alert.symbol)} — {escape_html(alert.message)}"
            )

    suggestions = report.suggestions or []
    if suggestions:
        lines.extend(["", "<b>💡 הצעות</b>"])
        for sug in suggestions[:3]:
            if sug.kind == "buy":
                lines.append(
                    f"🟢 <b>רכישה</b> · {_fmt_ticker(sug.symbol)} — {escape_html(sug.message)}"
                )
            elif sug.kind == "swap":
                lines.append(f"🔄 <b>החלפה</b> · {escape_html(sug.message)}")
            elif sug.kind == "sell":
                lines.append(
                    f"🔻 <b>מכירה</b> · {_fmt_ticker(sug.symbol)} — {escape_html(sug.message)}"
                )
            else:
                lines.append(
                    f"👀 <b>לעקוב</b> · {_fmt_ticker(sug.symbol)} — {escape_html(sug.message)}"
                )
            cmd = _intraday_howto_command(sug)
            if cmd:
                has_howto = True
                lines.append(f"  ✅ <b>איך לבצע:</b> שלח <code>{escape_html(cmd)}</code>")

    lines.append("")
    if has_howto:
        lines.append(
            "<i>הצעה בלבד — לא ביצוע אוטומטי. העתק את הפקודה מ«איך לבצע».</i>"
        )
    elif floor_sells and not suggestions:
        lines.append("<i>יציאה אוטומטית בוצעה — אין פעולה נוספת נדרשת.</i>")
    else:
        lines.append("<i>למעקב בלבד — אין פעולה נדרשת כרגע.</i>")
    return finalize("\n".join(lines))


def format_no_entries_morning(*, trading_day: str) -> str:
    """Short morning ping when the book has nothing new to open."""
    return finalize(
        "\n".join(
            [
                f"<b>📂 אין קניות היום · {escape_html(trading_day)}</b>",
                "ממשיכים עם התיק הקיים — אין כניסות חדשות בפתיחה",
            ]
        )
    )


def format_heartbeat(
    cfg: Any,
    state: dict[str, Any],
    *,
    summary_fn,
    monthly_fn,
    speculative_fn,
    market_day: bool = True,
    next_trading_day: str | None = None,
) -> str:
    """Clear multi-line heartbeat — numbers in <code> so minus/$ don't flip in RTL."""
    from trading_pulse.core.schedule_tz import utc_hhmm_to_zone, ISRAEL

    equity = float(state.get("equity", cfg.initial_capital))
    lines = [
        "<b>💚 הסוכן חי</b>",
        SEP,
        f"הון בספרים: {_ltr_code(f'${equity:.2f}')}",
    ]
    marked = _heartbeat_marked_parts(state, equity)
    if marked:
        marked_s = f"${marked['marked']:.2f}"
        lines.append(f"שווי משוער: {_ltr_code(marked_s)}")
        ur = marked["unrealized"]
        ur_word = "רווח עתידי" if ur > 0 else ("הפסד עתידי" if ur < 0 else "עתידי")
        lines.append(f"{ur_word}: {_fmt_usd(ur, signed=True)}")

    # Prefer structured profile when available
    try:
        from trading_pulse.agent.dryrun_agent import risk_profile_parts

        p = risk_profile_parts(cfg, equity)
        deploy_s = f"${p['max_deploy_usd']:.0f}"
        per_s = f"${p['per_trade_usd']:.0f}"
        lines.extend(
            [
                "",
                f"פרופיל: <b>{escape_html(p['label'])}</b>",
                f"השקעה: עד {p['max_deploy_pct']}% ({_ltr_code(deploy_s)})",
                f"עסקאות: עד {p['max_trades']} · כ־{_ltr_code(per_s)} לעסקה",
            ]
        )
    except Exception:
        lines.append(escape_html(truncate(summary_fn(cfg, equity), 120)))

    if speculative_fn(cfg):
        try:
            from trading_pulse.agent.dryrun_agent import monthly_target_parts

            m = monthly_target_parts(cfg, state)
            pnl_word = "רווח החודש" if m["month_pnl"] > 0 else (
                "הפסד החודש" if m["month_pnl"] < 0 else "חודש"
            )
            gap_word = "מעל היעד" if m["gap_usd"] <= 0 else "נותר ליעד"
            gap_amt = abs(m["gap_usd"])
            target_s = f"${m['target_usd']:.0f}"
            equity_s = f"${m['equity']:.2f}"
            gap_s = f"${gap_amt:.0f}"
            lines.extend(
                [
                    "",
                    f"יעד חודשי: {_ltr_code(target_s)}",
                    f"נוכחי: {_ltr_code(equity_s)}",
                    f"{pnl_word}: {_fmt_usd(m['month_pnl'], signed=True)} "
                    f"({_fmt_signed_pct(m['month_pnl_pct'])})",
                    f"{gap_word}: {_ltr_code(gap_s)}",
                    f"ימי מסחר שנותרו: {int(m['trading_days_left'])}",
                ]
            )
        except Exception:
            lines.append(escape_html(truncate(monthly_fn(cfg, state), 140)))

    if market_day:
        plan_il = str(getattr(cfg, "portfolio_review_time", "15:00"))
        report_utc = str(cfg.market_close_sim_time)
        report_il = utc_hhmm_to_zone(report_utc, ISRAEL) or report_utc
        lines.extend(
            [
                "",
                f"סקירה: {_ltr_code(plan_il)} ישראל",
                f"דוח: {_ltr_code(report_il)} ישראל "
                f"({_ltr_code(report_utc)} UTC)",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "💤 <b>וול סטריט סגורה היום</b>",
                "אין כניסות או דוח מסחר.",
                (
                    f"התוכנית הבאה לקראת המסחר ב־{escape_html(next_trading_day)}."
                    if next_trading_day
                    else "התוכנית הבאה לקראת יום המסחר הבא."
                ),
            ]
        )
    return finalize("\n".join(lines))


def _heartbeat_marked_parts(state: dict[str, Any], equity: float) -> dict[str, float] | None:
    positions = [dict(p) for p in (state.get("open_positions") or [])]
    if not positions:
        return None
    try:
        from trading_pulse.agent.positions import enrich_held_unrealized
        from trading_pulse.core.schedule_tz import us_trading_session_date

        day = us_trading_session_date()
        _, ur = enrich_held_unrealized(positions, day)
        ur_f = float(ur)
        return {"marked": round(equity + ur_f, 2), "unrealized": ur_f}
    except Exception:
        return None


def _heartbeat_marked_line(state: dict[str, Any], equity: float) -> str | None:
    """Optional marked equity line (HTML fallback helper)."""
    marked = _heartbeat_marked_parts(state, equity)
    if not marked:
        return None
    ur = marked["unrealized"]
    ur_word = "רווח עתידי" if ur > 0 else ("הפסד עתידי" if ur < 0 else "עתידי")
    marked_s = f"${marked['marked']:.2f}"
    return (
        f"שווי משוער: {_ltr_code(marked_s)} · "
        f"{ur_word} {_fmt_usd(ur, signed=True)}"
    )


def format_below_bar_approve_hint(weak_recs: list[dict[str, Any]], *, plan_recs: list[dict[str, Any]] | None = None) -> str:
    """Reply when «הכל» would only cover below-threshold fallback picks."""
    plan_recs = plan_recs or weak_recs
    lines = [
        "<b>⚠️ המלצות מתחת לסף — «הכל» לא מאשר אותן</b>",
        "זה fallback חלש (לא אות איכות מלא). לאישור מפורש שלח את המספר:",
    ]
    for i, r in enumerate(plan_recs, start=1):
        if not r.get("below_bar"):
            continue
        sym = escape_html(str(r.get("symbol", "")))
        score = float(r.get("score") or 0)
        lines.append(f"• שלח <code>{i}</code> — <b>{sym}</b> (ציון {score:.1f})")
    lines.append("<i>או דחה: <code>דחה</code> / חכה לערב הבא</i>")
    return finalize("\n".join(lines))


def format_below_bar_skipped_note(symbols: list[str]) -> str:
    names = ", ".join(escape_html(s) for s in symbols)
    return (
        f"⚠️ לא אושר אוטומטית (מתחת לסף): <b>{names}</b>\n"
        "לאישור מפורש שלח את המספר מהתוכנית (למשל <code>1</code>)."
    )


def format_reply_plain(text: str) -> str:
    """User-facing command replies (approve/status) — simple plain text."""
    return text

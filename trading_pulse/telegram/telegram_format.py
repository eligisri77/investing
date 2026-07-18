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
            "1. <code>התחל</code> / <code>הכל</code> — המלצות לפי מצב האסטרטגיה בהגדרות",
            "2. בפתיחה — קניות שאושרו; שיטה 2 ממתינה לפריצה ולא נקנית אוטומטית",
            "3. בערב אחרי סגירה — דוח יומי על הרווח/הפסד",
            "",
            "אין מזומן? <code>מכור 1 $100</code> (רק חלק) · <code>מכור 1</code> (הכל)",
            "יש מזומן פנוי? הבוט מציע מה לעשות · חיזוק: <code>תקנה 1 $20</code> · <code>קנה BEAM $50</code>",
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
        lines.append(f"• <b>{sym}</b>{tag} — <b>${cap:.0f}</b> מושקע{entry_txt} · {days} ימים")
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
            f"שיטה 2 · נרות סיניים · {side_he} · טריגר {trig} · "
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
                    "(בוקר או תוך־יום). בלי פריצה — אין קנייה."
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
                + (" · שיטה 2 מחכה לפריצה" if has_method2 else "")
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
            lines.append(
                f"• שיטה 2 ({names}): אחרי אישור — כניסה <b>רק אם נפרצת הרמה</b> "
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
            f"• לקנות מניה מהרשימה: <code>קנה SYMBOL ${suggest_usd}</code>"
        )
    lines.append("• להשאיר במזומן — אין חובה לקנות היום")
    lines.append(
        "<i>טיפ: <code>תקנה 1 $50</code> מוסיף למניה #1 בתיק בלי למכור אחרת</i>"
    )
    return lines


def format_no_new_buys_banner(
    plan: dict[str, Any],
    *,
    holdings: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[str]:
    """Emphasize empty / weak recommendation days."""
    lines = [
        "",
        "🚫 <b>אין המלצות היום לקנייה חדשה</b>",
        "<b>אין מניות שעברו את סף האיכות</b>",
    ]
    summary = format_scan_summary(plan, html=True)
    if summary:
        lines.extend(["", "<b>📊 למה?</b>", summary])
    reason = plan.get("no_picks_reason")
    if reason and not (plan.get("scan_stats") or {}).get("top_skipped_scores"):
        lines.append(escape_html(str(reason)))

    free = float(plan.get("available_capital_usd", 0))
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
    target_symbol: str | None = None,
    target_usd: float | None = None,
    holdings: list[dict[str, Any]] | None = None,
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
) -> str:
    lines = [
        "🔄 <b>החלפה הושלמה</b>",
        f"מכרת <b>{escape_html(from_symbol)}</b> — <b>${sold_usd:.0f}</b>",
        f"קנית <b>{escape_html(to_symbol)}</b> — <b>${bought_usd:.0f}</b> "
        f"@ ${entry_price:.2f}",
        f"מזומן פנוי: <b>${cash:.0f}</b>",
    ]
    lines.extend(format_cash_deploy_advice(cash, holdings or [], new_buy_symbols=set()))
    return finalize("\n".join(lines))


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
    held = _held_symbol_set(holdings)
    new_recs = [r for r in recs if str(r["symbol"]) not in held]

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

    footer: list[str] = ["", "<i>פרטים + גרף לכל מניה ↓</i>", "", SEP]
    if new_recs:
        has_m2 = any(str(r.get("strategy")) == "method2" for r in new_recs)
        footer.append("<b>⏰ מחר</b> — כניסת ציון/נרות בפתיחה")
        if has_m2:
            footer.append("<b>שיטה 2</b> — כניסה רק אם נפרצת הרמה (בוקר או תוך־יום)")
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
        lines.append(
            f"• <b>{escape_html(e['symbol'])}</b>{tag}{side_tag} "
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
        lines.append(f"<b>שיטה 2 · נרות סיניים · {side_he} · טריגר {trig}</b>")
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
                rec = next(
                    (
                        r
                        for r in (plan.get("recommendations") or [])
                        if str(r.get("symbol")) == sym
                    ),
                    {},
                )
                extra = ""
                if str(rec.get("strategy") or "") == "method2":
                    trig = escape_html(str(rec.get("trigger") or ""))
                    extra = f" · שיטה 2 · נרות סיניים ({trig}) — כניסה בפריצה בלבד"
                elif str(rec.get("strategy") or "") == "rising_three_methods":
                    extra = " · נרות Rising Three — כניסה בפתיחה"
                lines.append(f"• <b>{escape_html(sym)}</b> — <b>${amt:.0f}</b>{extra}")
            if any(
                str(r.get("strategy") or "") == "method2"
                for r in (plan.get("recommendations") or [])
                if str(r.get("symbol")) in {s for s, _ in new_buys}
            ):
                lines.append(
                    "<i>שיטה 2: אם לא נפרץ בבוקר — נשאר במעקב תוך־יומי; בלי פריצה אין כניסה</i>"
                )
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
        from trading_pulse.agent.strategy_labels import strategy_suffix_html

        lines.extend(["", "<b>📂 עדיין מחזיקים</b>"])
        for pos in held:
            ur = float(pos.get("unrealized_pnl_usd", 0))
            ur_sign = "+" if ur >= 0 else ""
            ur_txt = f" · {ur_sign}${ur:.2f} ({float(pos.get('unrealized_pnl_pct', 0)):+.1f}%)" if pos.get("unrealized_pnl_usd") is not None else ""
            tag = strategy_suffix_html(pos)
            lines.append(
                f"• <b>{escape_html(pos['symbol'])}</b>{tag} "
                f"${float(pos['capital_usd']):.0f} · {pos.get('days_held', 0)} ימים{ur_txt}"
            )

    executed = report.get("executed", [])
    if executed:
        from trading_pulse.agent.strategy_labels import strategy_suffix_html

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
            tag = strategy_suffix_html(t)
            lines.append(
                f"• <b>{escape_html(t['symbol'])}</b>{tag} {reason}{days}"
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


def format_intraday_monitor(report: Any) -> str:
    """Hourly intraday watch message (alerts + buy/swap suggestions)."""
    lines = [
        "<b>🔍 מעקב שעתי — מסחר פעיל</b>",
        SEP,
    ]

    holdings = report.holdings or []
    if holdings:
        from trading_pulse.agent.strategy_labels import strategy_suffix_html

        lines.append("<b>📌 מושקע עכשיו</b>")
        for h in holdings[:6]:
            pnl = float(h.get("pnl_pct", 0))
            day = float(h.get("day_change_pct", 0))
            sign = "+" if pnl >= 0 else ""
            cap = float(h.get("capital_usd", 0))
            cap_txt = f"<b>${cap:.0f}</b> מושקע · " if cap > 0 else ""
            floor = h.get("floor_price")
            floor_txt = f" · רף ${float(floor):.2f}" if floor else ""
            tag = strategy_suffix_html(h)
            lines.append(
                f"• <b>{escape_html(h['symbol'])}</b>{tag} — {cap_txt}"
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
            cmd = _intraday_howto_command(sug)
            if cmd:
                lines.append(f"   ✅ <b>איך לבצע:</b> שלח <code>{escape_html(cmd)}</code>")

    lines.extend(
        [
            "",
            "<i>הצעה בלבד — לא ביצוע אוטומטי. העתק את הפקודה מ«איך לבצע».</i>",
        ]
    )
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


def format_heartbeat(cfg: Any, state: dict[str, Any], *, summary_fn, monthly_fn, speculative_fn) -> str:
    from trading_pulse.core.schedule_tz import format_dual_time

    equity = float(state.get("equity", cfg.initial_capital))
    lines = [
        "<b>💚 הסוכן חי</b>",
        SEP,
        f"הון בספרים: <b>${equity:.2f}</b>",
    ]
    marked_txt = _heartbeat_marked_line(state, equity)
    if marked_txt:
        lines.append(marked_txt)
    lines.append(escape_html(truncate(summary_fn(cfg, equity), 100)))
    if speculative_fn(cfg):
        lines.append(escape_html(truncate(monthly_fn(cfg, state), 120)))
    plan_t = format_dual_time(str(cfg.planning_time)) or str(cfg.planning_time)
    report_t = format_dual_time(str(cfg.market_close_sim_time)) or str(cfg.market_close_sim_time)
    lines.append(f"תוכנית {escape_html(plan_t)}")
    lines.append(f"דוח {escape_html(report_t)}")
    return finalize("\n".join(lines))


def _heartbeat_marked_line(state: dict[str, Any], equity: float) -> str | None:
    """Optional marked equity (book + unrealized) when quotes are available."""
    positions = [dict(p) for p in (state.get("open_positions") or [])]
    if not positions:
        return None
    try:
        from trading_pulse.agent.positions import enrich_held_unrealized
        from trading_pulse.core.schedule_tz import us_trading_session_date

        day = us_trading_session_date()
        _, ur = enrich_held_unrealized(positions, day)
        marked = round(equity + float(ur), 2)
        ur_f = float(ur)
        ur_sign = "+" if ur_f >= 0 else ""
        return (
            f"שווי משוער: <b>${marked:.2f}</b> "
            f"(עתידי {ur_sign}${ur_f:.2f})"
        )
    except Exception:
        return None


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

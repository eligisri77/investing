"""Clean Telegram message formatting (HTML)."""

from __future__ import annotations

import re
from typing import Any

SEP = "────────────────"

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
            "1️⃣ <code>התחל</code> — קונה 3 מניות ומחלק את $1,000",
            "2️⃣ בערב — דוח יומי על הרווח/הפסד",
            "",
            "אין מזומן? <code>מכור SYMBOL</code> · <code>החלף X Y</code> · <code>למכור X ולקנות Y</code>",
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


def format_holding_actions(actions: list[dict[str, Any]]) -> list[str]:
    """Evening decision lines: hold / sell / swap / take-profit per holding."""
    if not actions:
        return []
    lines = ["<b>📊 מה לעשות עם התיק שלך</b>"]
    for a in actions:
        sym = escape_html(str(a.get("symbol", "")))
        verdict = str(a.get("verdict", "hold"))
        icon, label = _VERDICT_META.get(verdict, ("🟢", "החזק"))
        pnl = float(a.get("pnl_pct", 0))
        head = f"{icon} <b>{sym}</b> · {pnl:+.1f}% · <b>{label}</b>"
        reason = escape_html(str(a.get("reason", "")))
        lines.append(f"{head} — {reason}")
        if verdict == "swap" and a.get("swap_to"):
            to_sym = escape_html(str(a["swap_to"]))
            lines.append(f"   ↳ <code>החלף {sym} {to_sym}</code>")
        elif verdict in {"sell", "take_profit"}:
            lines.append(f"   ↳ <code>מכור {sym}</code>")
    return lines


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
                lines.extend(format_holding_actions(actions))
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
                f"בערך <b>${each:.0f}</b> לכל מניה — לחץ <code>הכל</code> לאישור",
                "",
                user_guide_step1(),
            ]
        )
    elif intent == "add_needs_sell":
        gap = plan.get("funding") or {}
        target = escape_html(str(gap.get("target_symbol", recs[0]["symbol"])))
        lines.extend(
            [
                "",
                f"<b>💡 מומלץ לקנות {target}</b> — אין מספיק מזומן (${free:.0f} פנוי)",
                f"צריך עוד <b>${float(gap.get('gap_usd', 0)):.0f}</b>",
                "",
                "<b>אפשרויות:</b>",
            ]
        )
        for s in (gap.get("sell_suggestions") or [])[:3]:
            lines.append(
                f"• <code>מכור {escape_html(s['symbol'])}</code> "
                f"(${float(s['sell_usd']):.0f} · {float(s['sell_pct']):.0f}% מהפוזיציה)"
            )
        lines.append(f"• <code>החלף {escape_html((gap.get('sell_suggestions') or [{}])[0].get('symbol', ''))} {target}</code>")
        lines.extend(["", "אחרי מכירה — שלח <code>הכל</code> לאישור"])
    else:
        lines.extend(["", "<b>כניסות חדשות</b>", user_guide_step1()])

    if holdings:
        lines.append("")
        if actions:
            lines.extend(format_holding_actions(actions))
        else:
            lines.append("<b>📂 כבר מחזיקים</b>")
            for h in holdings:
                lines.append(
                    f"• <b>{escape_html(h['symbol'])}</b> "
                    f"${float(h['capital_usd']):.0f} · {h['days_held']} ימים"
                )

    symbols = " · ".join(f"<b>#{idx} {escape_html(rec['symbol'])}</b>" for idx, rec in enumerate(recs, start=1))
    header = f"<b>🆕 {len(recs)} המלצות</b>"
    if plan.get("fallback_pick"):
        header = "<b>⚠️ אין מניה שעברה את סף האיכות</b>"
        symbols = (
            f"הטובה ביותר היום (מתחת לסף): {symbols}\n"
            "<i>לשיקולך בלבד — איכות נמוכה מהרגיל. אפשר גם לוותר היום.</i>"
        )
    lines.extend(
        [
            "",
            header,
            symbols,
            "<i>פרטים + גרף לכל מניה ↓</i>",
            "",
            SEP,
            "<b>⏰ מחר בפתיחת וול סטריט</b> — כניסה במחיר פתיחה",
            "<b>בערב</b> — דוח יומי",
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


def format_entry_notification(entries: list[dict[str, Any]], *, trading_day: str) -> str:
    if not entries:
        return ""
    lines = [
        f"<b>✅ קנית · {escape_html(trading_day)}</b>",
        "",
    ]
    for e in entries:
        lines.append(
            f"• <b>{escape_html(e['symbol'])}</b> "
            f"${float(e['capital_usd']):.0f} @ <b>${float(e['entry_price']):.2f}</b>"
        )
    lines.extend(["", "דוח סוף יום יישלח אחרי סגירת וול סטריט"])
    return finalize("\n".join(lines))


def format_plan_table_caption(plan: dict[str, Any]) -> str:
    """Caption for the plan summary table image."""
    day = escape_html(plan.get("for_trading_day", ""))
    recs = plan.get("recommendations") or []
    if recs:
        return (
            f"<b>📋 המלצות {day}</b>\n"
            "שלח <code>הכל</code> לאישור"
        )
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
    draft = float(rec.get("capital_usd", 0))
    price = float(rec.get("entry_ref_price", 0))
    sl = int(float(rec.get("stop_loss_pct", 0)) * 100)
    tp = int(float(rec.get("take_profit_pct", 0)) * 100)
    sl_price = float(rec.get("floor_price") or rec.get("stop_loss_price", 0))
    tp_price = float(rec.get("take_profit_price", 0))

    lines = [
        f"<b>#{idx} {sym}</b> · יום מסחר {day}",
        f"הצעה <b>${draft:.0f}</b> · מחיר ייחוס <b>${price:.2f}</b>",
        f"מחיר תחתון <b>${sl_price:.2f}</b> (-{sl}%) · מכירה אוטומטית מתחת",
        f"יעד רווח <b>+{tp}%</b> (${tp_price:.2f})",
        "",
    ]
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
) -> str:
    if rejected:
        return (
            f"🚫 <b>בוטל:</b> {escape_html(', '.join(picked_symbols))}\n"
            f"<b>יום:</b> {escape_html(trading_day)}"
        )

    lines = [
        f"<b>✅ מאושר — {escape_html(', '.join(all_approved_symbols))}</b>",
        f"<b>יום:</b> {escape_html(trading_day)}",
    ]
    if auto_allocated and cfg is not None and trading_day_date is not None:
        from trading_pulse.agent.trading_flow import scheduled_entry_moment

        when = scheduled_entry_moment(cfg, trading_day_date)
        lines.extend(
            [
                "",
                "💰 חולקים את הכסף — הקנייה תתבצע בפתיחת השוק",
                f"⏰ כניסה לשוק: <b>{escape_html(when)}</b>",
            ]
        )
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
    from trading_pulse.core.schedule_tz import format_local_entry_moment

    pnl = float(data["total_realized_pnl"])
    unrealized = float(data.get("unrealized_pnl_usd", 0))
    marked = float(data.get("open_marked_usd", data.get("open_capital_usd", 0)))
    sign = "+" if pnl >= 0 else ""
    ur_sign = "+" if unrealized >= 0 else ""
    lines = [
        "<b>💼 תיק השקעות</b>",
        SEP,
        f"הון: <b>${data['equity']:.2f}</b>",
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
        for p in holding:
            sym = escape_html(p["symbol"])
            entry = p.get("entry_price")
            when = format_local_entry_moment(p.get("entry_at"))
            price_bit = f" @ <b>${float(entry):.2f}</b>" if entry else ""
            marked_val = float(p.get("marked_value_usd", p.get("capital_usd", 0)))
            ur = float(p.get("unrealized_pnl_usd", 0))
            ur_s = "+" if ur >= 0 else ""
            lines.append(
                f"• <b>{sym}</b> ${p['capital_usd']:.0f}{price_bit} → שווי <b>${marked_val:.0f}</b> "
                f"({ur_s}${ur:.0f}) · {escape_html(when)}"
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
            floor = h.get("floor_price")
            floor_txt = f" · רף ${float(floor):.2f}" if floor else ""
            lines.append(
                f"• <b>{escape_html(h['symbol'])}</b> "
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
            "<i>הצעה בלבד — לא ביצוע אוטומטי. בדוק בדשבורד או שלח פקודה ידנית.</i>",
        ]
    )
    return finalize("\n".join(lines))


def format_heartbeat(cfg: Any, state: dict[str, Any], *, summary_fn, monthly_fn, speculative_fn) -> str:
    equity = float(state.get("equity", cfg.initial_capital))
    lines = [
        "<b>💚 הסוכן חי</b>",
        SEP,
        f"הון: <b>${equity:.2f}</b>",
        escape_html(truncate(summary_fn(cfg, equity), 100)),
    ]
    if speculative_fn(cfg):
        lines.append(escape_html(truncate(monthly_fn(cfg, state), 120)))
    lines.append(
        f"תוכנית {cfg.planning_time} · דוח {cfg.market_close_sim_time}"
    )
    return finalize("\n".join(lines))


def format_reply_plain(text: str) -> str:
    """User-facing command replies (approve/status) — simple plain text."""
    return text

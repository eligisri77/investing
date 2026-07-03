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
    """What the user should send during recommendation approval."""
    return "\n".join(
        [
            "<b>📝 מה לשלוח עכשיו (שלב 1):</b>",
            "✅ <code>הכל</code> — לאשר את כל ההמלצות",
            "✅ <code>1,2,3</code> — לאשר רק את המספרים האלה",
            "✅ <code>דחה 4</code> — לדחות המלצה מס' 4",
            "❌ לא עכשיו: <code>ח1</code>…<code>ח5</code> (זה שלב 2, אחרי אישור)",
        ]
    )


def user_guide_step2() -> str:
    """What the user should send during capital allocation."""
    return "\n".join(
        [
            "<b>📝 מה לשלוח עכשיו (שלב 2):</b>",
            "✅ <code>ח1</code> — שווה, כל הפנוי",
            "✅ <code>ח2</code> — לפי דירוג",
            "✅ <code>ח3</code> — מקסימום לראשונה",
            "✅ <code>ח4</code> — לפי תוכנית + מזומן למחר",
            "✅ <code>ח5</code> — שמרני, חצי פנוי",
            "✅ <code>חלוקה</code> — להציג את האפשרויות שוב",
            "❌ לא: <code>1</code> או <code>2</code> (מאשרים המלצה, לא חלוקה)",
        ]
    )


def user_guide_done() -> str:
    return "\n".join(
        [
            "<b>📝 הכל מוכן.</b>",
            "אין צורך לשלוח עוד כלום עד דוח המסחר.",
            "לבדיקה: <code>סטטוס</code> · <code>תיק</code> · <code>תוכנית</code>",
        ]
    )


def format_pre_sim_reminder(minutes: int, kind: str) -> str:
    mins = max(0, int(minutes))
    if kind == "allocation":
        action = "שלח <code>ח4</code> לחלוקה (או <code>ח1</code>…<code>ח5</code>)"
    else:
        action = "שלח <code>הכל</code> או <code>1,2</code> לאישור"
    return "\n".join(
        [
            f"⏰ <b>תזכורת</b> — נשארו <b>{mins}</b> דקות עד סימולציה",
            action,
            "",
            "<i>אפשר גם בדשבורד: תוכנית פעילה (#/plan)</i>",
        ]
    )


def user_guide_full() -> str:
    return "\n".join(
        [
            "<b>📖 שני שלבים — אל תערבב ביניהם</b>",
            "",
            "<b>שלב 1 — אישור</b> (מספרים בלי ח')",
            "<code>הכל</code> · <code>1,2</code> · <code>דחה 3</code>",
            "",
            "<b>שלב 2 — חלוקה</b> (עם אות ח')",
            "<code>ח1</code>…<code>ח5</code> · <code>חלוקה</code>",
            "",
            "<b>דוגמה נכונה:</b>",
            "1) <code>1,2,3</code>  →  2) <code>ח4</code>",
            "",
            "<b>כללי</b>",
            "<code>סטטוס</code> · <code>תיק</code> · <code>תוכנית</code> · <code>עזרה</code>",
            "<code>מדריך</code> — מדריך מלא · <code>איך בוחרים מניות</code> — תהליך הבחירה",
            "<code>חיבור בוט</code> — יצירת בוט והגדרות",
            "",
            "<b>רשימת מניות:</b>",
            "<code>מניות</code> · <code>הוסף SMCI</code> · <code>הסר IONQ</code> · <code>חפש מניות</code>",
            "",
            "<code>תוכנית עכשיו</code> — ליצור תוכנית חדשה",
            "<code>תוכנית</code> — לשלוח שוב את התוכנית האחרונה",
            "",
            "<b>מעקב מסחר (במהלך היום):</b>",
            "התראות על מניות מושקעות + הצעות רכישה/החלפה",
            "ניתן לכבות או לשנות תדירות ב-<code>#/settings</code>",
            "(intraday_check_enabled · intraday_check_interval_minutes)",
            "",
            "<b>דשבורד:</b> אישור + חלוקה ב-<code>#/plan</code>",
            "",
            "<b>טעות נפוצה:</b>",
            "שליחת <code>1</code> אחרי האישור — לא בוחרת חלוקה!",
        ]
    )


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


def format_plan(plan: dict[str, Any], *, rec_formatter) -> str:
    """Format daily plan overview for Telegram (details sent per stock)."""
    day = escape_html(plan.get("for_trading_day", ""))
    recs = plan.get("recommendations", [])
    equity = float(plan.get("equity_snapshot", 0))
    free = float(plan.get("available_capital_usd", plan.get("equity_snapshot", 0)))
    holdings = plan.get("holdings") or []

    lines = [
        "<b>📋 תוכנית יומית</b>",
        f"<b>יום מסחר:</b> {day}",
        "",
        f"💰 הון <b>${equity:.0f}</b> · פנוי <b>${free:.0f}</b>",
    ]
    if plan.get("monthly_target_summary"):
        lines.append(escape_html(truncate(plan["monthly_target_summary"], 100)))

    if not recs:
        if holdings:
            lines.extend(["", "<b>📂 כבר מחזיקים</b>"])
            for h in holdings:
                lines.append(
                    f"• <b>{escape_html(h['symbol'])}</b> "
                    f"${float(h['capital_usd']):.0f} · {h['days_held']} ימים"
                )
            lines.extend(["", "אין כניסות חדשות היום — רק החזקה."])
        else:
            lines.extend(["", "🔍 <b>אין המלצות היום</b>"])
            summary = format_scan_summary(plan, html=True)
            if summary:
                lines.extend(["", "<b>📊 סיכום סריקה</b>", summary])
            reason = plan.get("no_picks_reason")
            if reason and not (plan.get("scan_stats") or {}).get("top_skipped_scores"):
                lines.append(escape_html(str(reason)))
        return finalize("\n".join(lines))

    lines.extend(
        [
            "",
            "<b>שלב 1 — אישור המלצות</b>",
            user_guide_step1(),
        ]
    )

    if holdings:
        lines.extend(["", "<b>📂 כבר מחזיקים</b> (לא נכללים באישור)"])
        for h in holdings:
            lines.append(
                f"• <b>{escape_html(h['symbol'])}</b> "
                f"${float(h['capital_usd']):.0f} · {h['days_held']} ימים"
            )

    symbols = " · ".join(f"<b>#{idx} {escape_html(rec['symbol'])}</b>" for idx, rec in enumerate(recs, start=1))
    lines.extend(
        [
            "",
            f"<b>🆕 {len(recs)} המלצות חדשות</b>",
            symbols,
            "<i>לכל מניה תישלח הודעה נפרדת עם גרף ופירוט ↓</i>",
            "",
            SEP,
            "<b>אחרי שתאשר</b> — תקבל הודעת שלב 2",
            "שם תשלח <code>ח1</code>…<code>ח5</code> (עם אות <b>ח'</b>)",
            "טבלת סיכום בתמונה למטה ↑",
        ]
    )
    return finalize("\n".join(lines))


def format_plan_table_caption(plan: dict[str, Any]) -> str:
    """Caption for the plan summary table image."""
    day = escape_html(plan.get("for_trading_day", ""))
    recs = plan.get("recommendations") or []
    if recs:
        return (
            f"<b>📋 תוכנית {day}</b>\n"
            "שלב 1: אשר עם <code>הכל</code> / <code>1,2</code>"
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
) -> str:
    if rejected:
        return (
            f"🚫 <b>נדחו:</b> {escape_html(', '.join(picked_symbols))}\n"
            f"<b>יום מסחר:</b> {escape_html(trading_day)}\n\n"
            f"סטטוס: <code>סטטוס</code>"
        )

    lines = [
        "<b>✅ שלב 1 הושלם — אישור המלצות</b>",
        f"<b>יום מסחר:</b> {escape_html(trading_day)}",
        "",
        f"<b>בחרת עכשיו:</b> {escape_html(', '.join(picked_symbols))}",
        (
            f"<b>סה\"כ מאושרות:</b> {escape_html(', '.join(all_approved_symbols))}"
            f" ({len(all_approved_symbols)} מניות)"
        ),
    ]
    if allocation_sent:
        lines.extend(
            [
                "",
                SEP,
                "<b>▶️ עכשיו שלב 2 — חלוקת הון</b>",
                "נשלחה הודעה נפרדת עם האפשרויות.",
                "",
                user_guide_step2(),
            ]
        )
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
    if report.get("monthly_target_summary"):
        lines.append(escape_html(truncate(report["monthly_target_summary"], 120)))

    held = report.get("held_eod") or []
    if held:
        lines.extend(["", "<b>📂 עדיין מחזיקים</b>"])
        for pos in held:
            lines.append(
                f"• <b>{escape_html(pos['symbol'])}</b> "
                f"${float(pos['capital_usd']):.0f} · {pos.get('days_held', 0)} ימים"
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
    pnl = float(data["total_realized_pnl"])
    sign = "+" if pnl >= 0 else ""
    lines = [
        "<b>💼 תיק השקעות</b>",
        SEP,
        f"הון: <b>${data['equity']:.2f}</b>",
        f"מושקע: <b>${data['open_capital_usd']:.0f}</b> ({data['open_count']} פוזיציות)",
        f"רווח מצטבר: <b>{sign}${pnl:.2f}</b>",
    ]

    open_positions = data.get("open_positions") or []
    if open_positions:
        lines.extend(["", "<b>📌 פתוח / ממתין</b>"])
        for p in open_positions:
            sym = escape_html(p["symbol"])
            if p.get("status") == "holding":
                lines.append(
                    f"• <b>{sym}</b> ${p['capital_usd']:.0f} · מחזיק {p.get('days_held', 0)} ימים"
                )
            else:
                lines.append(f"• <b>{sym}</b> ${p['capital_usd']:.0f} · ממתין לכניסה")
    else:
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

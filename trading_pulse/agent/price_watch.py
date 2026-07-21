"""User-requested intraday price watches (Telegram: ציון שעתי / מעקב)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from trading_pulse.agent.intraday_monitor import fetch_intraday_quote, is_within_market_hours
from trading_pulse.agent.ticker_manager import normalize_symbol


def list_price_watches(state: dict[str, Any]) -> list[str]:
    raw = state.get("price_watches") or []
    if isinstance(raw, dict):
        return sorted({str(s).upper() for s in raw.keys()})
    return sorted({str(s).upper() for s in raw if str(s).strip()})


def clear_all_price_watches(state: dict[str, Any]) -> list[str]:
    """Remove all hourly watches (end of trading day). Returns cleared symbols."""
    cleared = list_price_watches(state)
    state["price_watches"] = {}
    return cleared


def format_watches_cleared(cleared: list[str]) -> str:
    """EOD notice for cleared hourly watches — not the daily P/L report."""
    from trading_pulse.telegram.telegram_format import escape_html

    if not cleared:
        return ""

    lines = [
        "🌙 <b>סיום מעקב שעתי</b>",
        "סוף יום מסחר — המעקבים של היום נוקו.",
        "",
    ]
    for symbol in cleared:
        sym = escape_html(symbol)
        quote = None
        try:
            quote = fetch_intraday_quote(symbol)
        except Exception as ex:
            logging.debug("EOD watch quote skip %s: %s", symbol, ex)
        if quote:
            last = float(quote["last"])
            day_chg = float(quote.get("day_change_pct", quote.get("change_pct", 0)) or 0)
            sign = "+" if day_chg >= 0 else ""
            high = float(quote.get("high", last))
            low = float(quote.get("low", last))
            lines.append(
                f"• <b>{sym}</b>  ${last:.2f}  ·  היום {sign}{day_chg:.2f}%"
            )
            lines.append(f"  טווח היום ${low:.2f}–${high:.2f}")
        else:
            lines.append(f"• <b>{sym}</b>  (אין מחיר סגירה)")
    lines.extend(
        [
            "",
            f"נוקו <b>{len(cleared)}</b> מעקב(ים).",
            "להפעלה מחר: <code>ציון שעתי SYMBOL</code>",
        ]
    )
    return "\n".join(lines)


def _ensure_watches_dict(state: dict[str, Any]) -> dict[str, Any]:
    watches = state.get("price_watches")
    if isinstance(watches, list):
        watches = {str(s).upper(): {"added_at": datetime.now(timezone.utc).isoformat()} for s in watches}
        state["price_watches"] = watches
    elif not isinstance(watches, dict):
        watches = {}
        state["price_watches"] = watches
    return watches


def add_price_watch(state: dict[str, Any], symbol: str) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    watches = _ensure_watches_dict(state)
    if symbol in watches:
        return {"symbol": symbol, "added": False, "watches": list_price_watches(state)}
    watches[symbol] = {"added_at": datetime.now(timezone.utc).isoformat()}
    return {"symbol": symbol, "added": True, "watches": list_price_watches(state)}


def mark_price_watch_sent(state: dict[str, Any], symbol: str) -> None:
    """Record last update time so the next tick waits a full interval."""
    symbol = normalize_symbol(symbol)
    watches = _ensure_watches_dict(state)
    entry = watches.get(symbol)
    if not isinstance(entry, dict):
        entry = {}
        watches[symbol] = entry
    entry["last_sent_at"] = datetime.now(timezone.utc).isoformat()


def due_for_price_tick(state: dict[str, Any], symbol: str, interval_minutes: int) -> bool:
    """True when enough time has passed since the last snapshot/tick."""
    symbol = normalize_symbol(symbol)
    watches = state.get("price_watches") or {}
    if not isinstance(watches, dict):
        return True
    entry = watches.get(symbol)
    if not isinstance(entry, dict):
        return True
    raw = entry.get("last_sent_at")
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    return elapsed >= max(1, int(interval_minutes)) * 60


def remove_price_watch(state: dict[str, Any], symbol: str) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    watches = state.get("price_watches")
    removed = False
    if isinstance(watches, dict):
        removed = watches.pop(symbol, None) is not None
    elif isinstance(watches, list):
        before = len(watches)
        state["price_watches"] = [s for s in watches if str(s).upper() != symbol]
        removed = len(state["price_watches"]) < before
    return {"symbol": symbol, "removed": removed, "watches": list_price_watches(state)}


def _quick_score_line(cfg: Any, symbol: str) -> str:
    """Best-effort score snippet; never fail the price update."""
    try:
        from trading_pulse.agent.dryrun_agent import fetch_signal_universe, is_speculative

        df = fetch_signal_universe([symbol], cfg)
        if df is None or df.empty:
            return ""
        row = df.iloc[0]
        score = float(row.get("score", 0))
        ret5 = float(row.get("ret_5d_pct", 0))
        vol = float(row.get("vol_ratio", 0))
        extra = ""
        if is_speculative(cfg):
            atr = float(row.get("atr_pct", 0))
            extra = f" · ATR {atr:.1f}%"
        return f"ציון <b>{score:.1f}</b> · 5י {ret5:+.1f}% · נפח {vol:.2f}x{extra}"
    except Exception as ex:
        logging.debug("Price watch score skip %s: %s", symbol, ex)
        return ""


def format_price_watch_update(
    cfg: Any,
    symbol: str,
    *,
    include_score: bool = True,
    watch_meta: dict[str, Any] | None = None,
) -> str | None:
    quote = fetch_intraday_quote(symbol)
    if not quote:
        return None
    last = float(quote["last"])
    day_chg = float(quote.get("day_change_pct", quote.get("change_pct", 0)) or 0)
    sign = "+" if day_chg >= 0 else ""
    high = float(quote.get("high", last))
    low = float(quote.get("low", last))
    lines = [
        f"<b>⏱ מעקב · {symbol}</b>",
        f"מחיר <b>${last:.2f}</b> · היום <b>{sign}{day_chg:.2f}%</b>",
        f"טווח היום ${low:.2f}–${high:.2f}",
    ]
    m2_line = _method2_distance_line(watch_meta, last)
    if m2_line:
        lines.append(m2_line)
    if include_score:
        score_line = _quick_score_line(cfg, symbol)
        if score_line:
            lines.append(score_line)
    interval = int(getattr(cfg, "intraday_check_interval_minutes", 60))
    lines.append(f"<i>עדכון כל {interval} דק׳ בזמן מסחר · הפסק מעקב {symbol}</i>")
    return "\n".join(lines)


def _method2_distance_line(watch_meta: dict[str, Any] | None, last: float) -> str:
    if not watch_meta:
        return ""
    entry_ref = float(watch_meta.get("entry_ref") or 0)
    if entry_ref <= 0:
        return ""
    side = str(watch_meta.get("side") or "LONG").upper()
    stop = float(watch_meta.get("stop_ref") or 0)
    if side == "SHORT":
        to_break = (last / entry_ref - 1.0) * 100.0
        status = "מעל הפריצה" if last > entry_ref else "מתחת לפריצה"
        line = (
            f"שיטה 2 שורט · פריצה ~${entry_ref:.2f} · "
            f"רחוק <b>{to_break:+.2f}%</b> ({status})"
        )
    else:
        if last >= entry_ref:
            line = (
                f"שיטה 2 · פריצה ~${entry_ref:.2f} · "
                f"<b>נפרץ</b> (+{(last / entry_ref - 1) * 100:.2f}%)"
            )
        else:
            to_break = (entry_ref / last - 1.0) * 100.0 if last > 0 else 0.0
            line = f"שיטה 2 · פריצה ~${entry_ref:.2f} · חסר <b>{to_break:.2f}%</b>"
    if stop > 0:
        line += f" · סטופ ~${stop:.2f}"
    return line


def should_send_method2_price_tick(
    watch_meta: dict[str, Any] | None,
    quote: dict[str, Any],
) -> bool:
    """Skip noisy flat ticks; always send when near breakout or price moved."""
    last = float(quote.get("last") or 0)
    day_chg = abs(
        float(quote.get("day_change_pct", quote.get("change_pct", 0)) or 0)
    )
    if last <= 0:
        return False
    meta = watch_meta or {}
    entry_ref = float(meta.get("entry_ref") or 0)
    near_breakout = False
    if entry_ref > 0:
        near_breakout = abs(last / entry_ref - 1.0) <= 0.015  # within 1.5%
    prev = meta.get("last_price")
    moved = True
    if prev is not None:
        try:
            moved = abs(last / float(prev) - 1.0) >= 0.004  # ≥0.4%
        except (TypeError, ValueError, ZeroDivisionError):
            moved = True
    if near_breakout:
        return True
    if day_chg < 0.05 and not moved:
        return False
    return moved or day_chg >= 0.15


def format_watch_added(cfg: Any, result: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import escape_html

    sym = escape_html(result["symbol"])
    interval = int(getattr(cfg, "intraday_check_interval_minutes", 60))
    watches = ", ".join(escape_html(s) for s in result.get("watches") or []) or "—"
    if result.get("added"):
        head = f"✅ <b>מעקב שעתי ל-{sym}</b>"
    else:
        head = f"ℹ️ <b>{sym} כבר במעקב</b>"
    return "\n".join(
        [
            head,
            "בהתחלה: כרטיס נתונים מלא + גרף.",
            f"אחר כך בזמן מסחר: עדכון מחיר כל <b>{interval}</b> דקות.",
            "בסוף יום המסחר המעקב נמחק אוטומטית.",
            f"רשימה: {watches}",
            f"להפסקה ידנית: <code>הפסק מעקב {sym}</code>",
        ]
    )


def format_watch_removed(result: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import escape_html

    sym = escape_html(result["symbol"])
    watches = ", ".join(escape_html(s) for s in result.get("watches") or []) or "אין"
    if result.get("removed"):
        return f"🛑 <b>הופסק מעקב ל-{sym}</b>\nנותרו: {watches}"
    return f"ℹ️ <b>{sym} לא היה במעקב</b>\nרשימה: {watches}"


def format_watches_list(cfg: Any, state: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import escape_html

    watches = list_price_watches(state)
    interval = int(getattr(cfg, "intraday_check_interval_minutes", 60))
    if not watches:
        return (
            "<b>⏱ אין מניות במעקב שעתי</b>\n"
            f"הוסף: <code>ציון שעתי AAPL</code> · עדכון כל {interval} דק׳ בזמן מסחר"
        )
    lines = [
        f"<b>⏱ מעקב שעתי</b> · כל {interval} דק׳ בזמן מסחר",
        "",
        ", ".join(f"<code>{escape_html(s)}</code>" for s in watches),
        "",
        "הפסקה: <code>הפסק מעקב SYMBOL</code>",
    ]
    return "\n".join(lines)


def send_price_watch_snapshot(cfg: Any, symbol: str) -> bool:
    """Start-of-watch: full metrics card + price chart (once)."""
    from trading_pulse.agent.dryrun_agent import send_telegram_message, send_telegram_photo
    from trading_pulse.agent.stock_detail import analyze_symbol
    from trading_pulse.telegram.reply_cards import card_stock_detail
    from trading_pulse.telegram.telegram_images import render_recommendation_chart

    symbol = normalize_symbol(symbol)
    interval = int(getattr(cfg, "intraday_check_interval_minutes", 60))
    try:
        detail = analyze_symbol(cfg, symbol)
    except Exception as ex:
        logging.warning("Price watch analyze failed for %s: %s", symbol, ex)
        text = format_price_watch_update(cfg, symbol, include_score=False)
        if text:
            from trading_pulse.agent.dryrun_agent import send_user_notification

            return bool(send_user_notification(cfg, text, context=f"price_watch:{symbol}", parse_mode="HTML"))
        return False

    if not detail.get("ok"):
        send_telegram_message(
            cfg,
            f"❌ <b>מעקב {symbol}</b> — {detail.get('error', 'אין נתונים')}",
            context=f"price_watch:{symbol}",
            parse_mode="HTML",
        )
        return False

    quote = fetch_intraday_quote(symbol)
    if quote:
        detail["live_quote"] = quote
    detail["watch_mode"] = True
    detail["watch_interval_min"] = interval

    rec = detail.get("rec") or {}
    day = str(detail.get("trading_day") or datetime.now(timezone.utc).date().isoformat())
    ok = False
    try:
        card = card_stock_detail(detail)
        send_telegram_photo(
            cfg,
            card,
            f"מעקב {symbol}",
            context=f"price_watch:{symbol}",
            inbox_text=f"מעקב {symbol}",
        )
        ok = True
    except Exception as ex:
        logging.warning("Price watch card failed for %s: %s", symbol, ex)

    try:
        chart = render_recommendation_chart(rec, 1, day)
        if chart:
            send_telegram_photo(
                cfg,
                chart,
                f"{symbol} · גרף",
                context=f"price_watch_chart:{symbol}",
                inbox_text=f"גרף {symbol}",
            )
            ok = True
    except Exception as ex:
        logging.warning("Price watch chart failed for %s: %s", symbol, ex)

    return ok


def send_price_only_tick(cfg: Any, symbol: str, state: dict[str, Any] | None = None) -> bool:
    """Hourly tick: price only (no full analysis / no chart)."""
    from trading_pulse.agent.dryrun_agent import send_telegram_photo, send_user_notification
    from trading_pulse.telegram.reply_cards import render_reply_card

    symbol = normalize_symbol(symbol)
    quote = fetch_intraday_quote(symbol)
    if not quote:
        logging.info("Price tick %s: no quote", symbol)
        return False

    watches = (state or {}).get("price_watches") or {}
    meta = watches.get(symbol) if isinstance(watches, dict) else None
    if not isinstance(meta, dict):
        meta = {}

    if meta.get("label") == "שיטה 2" or meta.get("entry_ref"):
        if not should_send_method2_price_tick(meta, quote):
            logging.info("Price tick %s: skipped (flat / far from breakout)", symbol)
            # Still remember last price so we don't spam after tiny noise
            meta["last_price"] = float(quote["last"])
            return False

    last = float(quote["last"])
    day_chg = float(quote.get("day_change_pct", quote.get("change_pct", 0)) or 0)
    sign = "+" if day_chg > 0 else ("-" if day_chg < 0 else "")
    high = float(quote.get("high", last))
    low = float(quote.get("low", last))
    interval = int(getattr(cfg, "intraday_check_interval_minutes", 60))
    m2_line = _method2_distance_line(meta, last)
    day_label = f"{sign}{abs(day_chg):.2f}%" if abs(day_chg) >= 0.005 else "0.00%"

    rows = [
        ("מחיר", f"${last:.2f}"),
        ("שינוי היום", day_label),
        ("טווח היום", f"${low:.2f} – ${high:.2f}"),
    ]
    if m2_line:
        # Strip HTML for card row
        plain_m2 = (
            m2_line.replace("<b>", "")
            .replace("</b>", "")
            .replace("&lt;", "<")
        )
        rows.append(("שיטה 2", plain_m2.replace("שיטה 2 · ", "").replace("שיטה 2 שורט · ", "")))

    try:
        png = render_reply_card(
            f"מחיר {symbol}",
            accent="cyan",
            rows=rows,
            footer=f"עדכון כל {interval} דק׳ · הפסק מעקב {symbol}",
        )
        inbox = f"{symbol} ${last:.2f} ({day_label})"
        if m2_line:
            inbox += " · " + m2_line.replace("<b>", "").replace("</b>", "")
        send_telegram_photo(
            cfg,
            png,
            f"{symbol} ${last:.2f}",
            context=f"price_tick:{symbol}",
            inbox_text=inbox,
        )
        meta["last_price"] = last
        return True
    except Exception as ex:
        logging.warning("Price tick card failed for %s: %s", symbol, ex)
        text = format_price_watch_update(cfg, symbol, include_score=False, watch_meta=meta)
        if text:
            ok = bool(send_user_notification(cfg, text, context=f"price_tick:{symbol}", parse_mode="HTML"))
            if ok:
                meta["last_price"] = last
            return ok
        return False


def send_price_watch_updates(cfg: Any, state: dict[str, Any]) -> int:
    """Periodic updates: price-only ticks during market hours (at most once per interval)."""
    from trading_pulse.agent.dryrun_agent import is_us_trading_day, save_json
    from trading_pulse.core.app_paths import STATE_FILE
    from trading_pulse.core.schedule_tz import us_trading_session_date

    today = us_trading_session_date()
    if not is_us_trading_day(today):
        return 0
    if not bool(getattr(cfg, "intraday_check_enabled", True)):
        return 0
    if not is_within_market_hours(cfg):
        return 0

    interval = int(getattr(cfg, "intraday_check_interval_minutes", 60))
    sent = 0
    for symbol in list_price_watches(state):
        try:
            if not due_for_price_tick(state, symbol, interval):
                logging.debug("Price watch %s: skipped (within %s min)", symbol, interval)
                continue
            if send_price_only_tick(cfg, symbol, state):
                mark_price_watch_sent(state, symbol)
                sent += 1
            else:
                # Method2 noise-skip still advances the interval (last_price stored in meta).
                watches = state.get("price_watches")
                meta = watches.get(symbol) if isinstance(watches, dict) else None
                if isinstance(meta, dict) and (
                    meta.get("label") == "שיטה 2" or meta.get("entry_ref")
                ):
                    mark_price_watch_sent(state, symbol)
        except Exception as ex:
            logging.warning("Price watch update failed for %s: %s", symbol, ex)
    save_json(STATE_FILE, state)
    return sent

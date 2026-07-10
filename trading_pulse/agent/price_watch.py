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
    from trading_pulse.telegram.telegram_format import escape_html

    if not cleared:
        return ""
    syms = ", ".join(escape_html(s) for s in cleared)
    return (
        f"🌙 <b>סוף יום מסחר</b> — נוקו מעקבים שעתיים:\n{syms}\n"
        f"להפעלה מחדש מחר: <code>ציון שעתי SYMBOL</code>"
    )


def add_price_watch(state: dict[str, Any], symbol: str) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    watches = state.setdefault("price_watches", {})
    if isinstance(watches, list):
        watches = {s.upper(): {"added_at": datetime.now(timezone.utc).isoformat()} for s in watches}
        state["price_watches"] = watches
    if symbol in watches:
        return {"symbol": symbol, "added": False, "watches": list_price_watches(state)}
    watches[symbol] = {"added_at": datetime.now(timezone.utc).isoformat()}
    return {"symbol": symbol, "added": True, "watches": list_price_watches(state)}


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


def format_price_watch_update(cfg: Any, symbol: str, *, include_score: bool = True) -> str | None:
    quote = fetch_intraday_quote(symbol)
    if not quote:
        return None
    last = float(quote["last"])
    day_chg = float(quote.get("day_change_pct", 0))
    sign = "+" if day_chg >= 0 else ""
    high = float(quote.get("high", last))
    low = float(quote.get("low", last))
    lines = [
        f"<b>⏱ מעקב · {symbol}</b>",
        f"מחיר <b>${last:.2f}</b> · היום <b>{sign}{day_chg:.2f}%</b>",
        f"טווח היום ${low:.2f}–${high:.2f}",
    ]
    if include_score:
        score_line = _quick_score_line(cfg, symbol)
        if score_line:
            lines.append(score_line)
    interval = int(getattr(cfg, "intraday_check_interval_minutes", 60))
    lines.append(f"<i>עדכון כל {interval} דק׳ בזמן מסחר · הפסק מעקב {symbol}</i>")
    return "\n".join(lines)


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


def send_price_only_tick(cfg: Any, symbol: str) -> bool:
    """Hourly tick: price only (no full analysis / no chart)."""
    from trading_pulse.agent.dryrun_agent import send_telegram_photo, send_user_notification
    from trading_pulse.telegram.reply_cards import render_reply_card

    symbol = normalize_symbol(symbol)
    quote = fetch_intraday_quote(symbol)
    if not quote:
        logging.info("Price tick %s: no quote", symbol)
        return False

    last = float(quote["last"])
    day_chg = float(quote.get("day_change_pct", 0))
    sign = "+" if day_chg >= 0 else ("-" if day_chg < 0 else "")
    high = float(quote.get("high", last))
    low = float(quote.get("low", last))
    interval = int(getattr(cfg, "intraday_check_interval_minutes", 60))

    try:
        png = render_reply_card(
            f"מחיר {symbol}",
            accent="cyan",
            rows=[
                ("מחיר", f"${last:.2f}"),
                ("שינוי היום", f"{sign}{abs(day_chg):.2f}%"),
                ("טווח היום", f"${low:.2f} – ${high:.2f}"),
            ],
            footer=f"עדכון כל {interval} דק׳ · הפסק מעקב {symbol}",
        )
        send_telegram_photo(
            cfg,
            png,
            f"{symbol} ${last:.2f}",
            context=f"price_tick:{symbol}",
            inbox_text=f"{symbol} ${last:.2f} ({sign}{abs(day_chg):.2f}%)",
        )
        return True
    except Exception as ex:
        logging.warning("Price tick card failed for %s: %s", symbol, ex)
        text = format_price_watch_update(cfg, symbol, include_score=False)
        if text:
            return bool(send_user_notification(cfg, text, context=f"price_tick:{symbol}", parse_mode="HTML"))
        return False


def send_price_watch_updates(cfg: Any, state: dict[str, Any]) -> int:
    """Periodic updates: price-only ticks during market hours."""
    from trading_pulse.agent.dryrun_agent import is_us_trading_day

    today = __import__("datetime").date.today()
    if not is_us_trading_day(today):
        return 0
    if not bool(getattr(cfg, "intraday_check_enabled", True)):
        return 0
    if not is_within_market_hours(cfg):
        return 0

    sent = 0
    for symbol in list_price_watches(state):
        try:
            if send_price_only_tick(cfg, symbol):
                sent += 1
        except Exception as ex:
            logging.warning("Price watch update failed for %s: %s", symbol, ex)
    return sent

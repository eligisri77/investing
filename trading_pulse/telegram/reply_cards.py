"""PIL reply cards for Telegram — dashboard look, narrow portrait."""

from __future__ import annotations

import io
import re
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont

from trading_pulse.telegram.telegram_images import (
    BG,
    BORDER,
    CYAN,
    GREEN,
    MUTED,
    PINK,
    RED,
    SURFACE,
    TEXT,
    _load_font,
    _pil_hebrew,
    _text_width,
)

CARD_W = 440
PAD = 18
INNER = 14
ROW_BG = (12, 12, 26)
CHIP_BG = (40, 12, 28)
CHIP_BORDER = (90, 25, 55)

Accent = Literal["cyan", "pink", "green", "red", "purple"]
_ACCENTS = {
    "cyan": CYAN,
    "pink": PINK,
    "green": GREEN,
    "red": RED,
    "purple": (168, 85, 247),
}


def _strip_html(text: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    t = re.sub(r"</p>|</div>|</li>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    t = t.replace("&quot;", '"').replace("&#39;", "'")
    # PIL fonts can't draw most emoji / box-drawing — replace with plain text.
    t = t.replace("─", "-").replace("━", "-").replace("—", "-").replace("–", "-")
    t = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]", "", t)
    t = re.sub(r"[✅❌⏳📌📋💼📊🌟💰🔄🚀⭐❗❓]", "", t)
    t = re.sub(r"-{4,}", "---", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_w: int,
) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if _text_width(draw, _pil_hebrew(trial), font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def _rtl(
    draw: ImageDraw.ImageDraw,
    x_right: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    shown = _pil_hebrew(text)
    w = _text_width(draw, shown, font)
    draw.text((x_right - w, y), shown, fill=fill, font=font)


def render_reply_card(
    title: str,
    *,
    accent: Accent = "cyan",
    subtitle: str = "",
    rows: list[tuple[str, str]] | None = None,
    bullets: list[str] | None = None,
    chips: list[str] | None = None,
    body: str = "",
    footer: str = "",
) -> bytes:
    """Generic narrow RTL card used for most Telegram replies."""
    font_title = _load_font(22, bold=True)
    font_sub = _load_font(13)
    font_label = _load_font(13)
    font_value = _load_font(15, bold=True)
    font_body = _load_font(14)
    font_chip = _load_font(13, bold=True)
    font_foot = _load_font(12)

    tmp = Image.new("RGB", (CARD_W, 80), BG)
    draw = ImageDraw.Draw(tmp)
    content_w = CARD_W - PAD * 2 - INNER * 2

    h = PAD + 48
    if subtitle:
        h += len(_wrap(draw, subtitle, font_sub, content_w)) * 18 + 6
    if body:
        for para in body.split("\n"):
            h += max(1, len(_wrap(draw, para, font_body, content_w))) * 20
        h += 8
    for _label, value in rows or []:
        h += 8
        h += 18  # label
        h += len(_wrap(draw, value, font_value, content_w - 8)) * 22 + 10
    for bullet in bullets or []:
        h += len(_wrap(draw, f"• {bullet}", font_body, content_w)) * 20 + 4
    # Chips last (above footer) so command hints aren't stuck mid-card.
    for chip in chips or []:
        h += 34
    if footer:
        h += 10 + len(_wrap(draw, footer, font_foot, content_w)) * 17
    h += PAD + 8

    img = Image.new("RGB", (CARD_W, h), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (8, 8, CARD_W - 8, h - 8),
        radius=18,
        fill=SURFACE,
        outline=BORDER,
        width=2,
    )

    color = _ACCENTS.get(accent, CYAN)
    x_right = CARD_W - PAD - INNER
    y = PAD + 14
    draw.rounded_rectangle((x_right - 3, y, x_right + 1, y + 26), radius=3, fill=color)
    _rtl(draw, x_right - 12, y, title, font_title, TEXT)
    y += 36

    if subtitle:
        for line in _wrap(draw, subtitle, font_sub, content_w):
            _rtl(draw, x_right, y, line, font_sub, MUTED)
            y += 18
        y += 6

    if body:
        for para in body.split("\n"):
            lines = _wrap(draw, para, font_body, content_w) or [""]
            for line in lines:
                if line:
                    _rtl(draw, x_right, y, line, font_body, TEXT)
                y += 20
        y += 6

    for label, value in rows or []:
        draw.rounded_rectangle(
            (PAD + 4, y, CARD_W - PAD - 4, y + 18 + len(_wrap(draw, value, font_value, content_w - 8)) * 22 + 10),
            radius=12,
            fill=ROW_BG,
            outline=BORDER,
        )
        cy = y + 8
        _rtl(draw, x_right - 8, cy, label, font_label, MUTED)
        cy += 18
        for line in _wrap(draw, value, font_value, content_w - 8):
            _rtl(draw, x_right - 8, cy, line, font_value, TEXT)
            cy += 22
        y = cy + 10

    for bullet in bullets or []:
        for line in _wrap(draw, f"• {bullet}", font_body, content_w):
            _rtl(draw, x_right, y, line, font_body, TEXT)
            y += 20
        y += 4

    for chip in chips or []:
        chip_w = min(content_w, _text_width(draw, _pil_hebrew(chip), font_chip) + 18)
        draw.rounded_rectangle(
            (x_right - chip_w, y, x_right, y + 28),
            radius=8,
            fill=CHIP_BG,
            outline=CHIP_BORDER,
        )
        _rtl(draw, x_right - 8, y + 6, chip, font_chip, PINK)
        y += 34

    if footer:
        y += 6
        for line in _wrap(draw, footer, font_foot, content_w):
            _rtl(draw, x_right, y, line, font_foot, MUTED)
            y += 17

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_html_message_card(html: str, *, title: str = "", accent: Accent = "cyan") -> bytes:
    """Best-effort: turn an HTML Telegram reply into a card image."""
    plain = _strip_html(html)
    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    if not lines:
        lines = [plain or "—"]
    head = title or lines[0]
    body_lines = lines[1:] if not title else lines
    # First line often repeats title
    if body_lines and body_lines[0] == head:
        body_lines = body_lines[1:]
    return render_reply_card(
        head[:60],
        accent=accent,
        body="\n".join(body_lines),
    )


def card_sell(
    symbol: str,
    *,
    fraction: float,
    pnl_usd: float,
    cash: float,
    sold_usd: float | None = None,
) -> bytes:
    pct = int(round(fraction * 100))
    sign = "+" if pnl_usd >= 0 else ""
    rows = [
        ("מניה", symbol),
        ("נמכר", f"{pct}%" + (f" · ${sold_usd:.0f}" if sold_usd else "")),
        ("רווח/הפסד ממומש", f"{sign}${abs(pnl_usd):.2f}"),
        ("מזומן פנוי", f"${cash:.0f}"),
    ]
    return render_reply_card(
        f"מכרת {symbol}",
        accent="green" if pnl_usd >= 0 else "red",
        rows=rows,
        footer="לקנייה: תקנה 1 $20 · או החלף X Y",
    )


def card_buy(
    symbol: str,
    *,
    bought_usd: float,
    entry_price: float,
    cash: float,
    added_to_existing: bool = False,
) -> bytes:
    action = "הוספת ל" if added_to_existing else "קנית"
    return render_reply_card(
        f"{action} {symbol}",
        accent="green",
        rows=[
            ("סכום", f"${bought_usd:.0f}"),
            ("מחיר", f"${entry_price:.2f}"),
            ("מזומן פנוי", f"${cash:.0f}"),
        ],
        footer="שלח תיק לראות מספרים מעודכנים",
    )


def card_swap(
    *,
    from_symbol: str,
    to_symbol: str,
    sold_usd: float,
    bought_usd: float,
    entry_price: float,
    cash: float,
) -> bytes:
    return render_reply_card(
        "החלפה הושלמה",
        accent="pink",
        rows=[
            ("מכרת", f"{from_symbol} · ${sold_usd:.0f}"),
            ("קנית", f"{to_symbol} · ${bought_usd:.0f} @ ${entry_price:.2f}"),
            ("מזומן פנוי", f"${cash:.0f}"),
        ],
    )


def card_approval(
    *,
    trading_day: str,
    new_buys: list[tuple[str, float]],
    held: list[tuple[str, float]],
    when: str = "",
    rejected: bool = False,
    symbols: list[str] | None = None,
) -> bytes:
    if rejected:
        return render_reply_card(
            "בוטל",
            accent="red",
            subtitle=f"יום מסחר {trading_day}",
            bullets=symbols or [],
        )
    rows: list[tuple[str, str]] = [("יום מסחר", trading_day)]
    bullets: list[str] = []
    for sym, amt in new_buys:
        bullets.append(f"קנייה: {sym} ${amt:.0f}")
    for sym, amt in held:
        bullets.append(f"ללא שינוי: {sym} ${amt:.0f}")
    footer = f"כניסה לשוק: {when}" if when else "הקנייה בפתיחת השוק"
    return render_reply_card(
        "תוכנית מאושרת",
        accent="green",
        rows=rows,
        bullets=bullets or ["אין קניות חדשות"],
        footer=footer,
    )


def card_error(title: str, body: str, *, chips: list[str] | None = None) -> bytes:
    return render_reply_card(title, accent="red", body=body, chips=chips or [])


def card_help() -> bytes:
    return render_reply_card(
        "איך זה עובד",
        accent="cyan",
        bullets=[
            "התחל — קונה 3 מניות ומחלק את $1,000",
            "בערב — תוכנית למחר · שלח הכל לאישור",
            "בבוקר — כניסה במחיר פתיחה",
            "בערב — דוח יומי",
        ],
        chips=["מכור 1 $100", "מניה NVDA", "תקנה 1 $20", "תיק"],
        footer="מכור 1 = הכל · מכור 1 $100 = רק חלק · מניה X = ניתוח+גרף",
    )


def card_funding(gap: dict[str, Any], *, trading_day: str) -> bytes:
    target = str(gap.get("target_symbol", ""))
    bullets = [
        f"רוצה {target} · חסר ${float(gap.get('gap_usd', 0)):.0f}",
        f"מזומן פנוי: ${float(gap.get('cash_free_usd', 0)):.0f}",
    ]
    chips = []
    for s in (gap.get("sell_suggestions") or [])[:3]:
        chips.append(f"מכור {s['symbol']}")
    if chips and target:
        chips.append(f"החלף {chips[0].replace('מכור ', '')} {target}")
    return render_reply_card(
        "אין מספיק מזומן",
        accent="pink",
        subtitle=f"יום מסחר {trading_day}",
        bullets=bullets,
        chips=chips,
        footer="אחרי מכירה — שלח הכל או תקנה",
    )


def card_entry(entries: list[dict[str, Any]], *, trading_day: str) -> bytes:
    bullets = [
        f"{e['symbol']} ${float(e['capital_usd']):.0f} @ ${float(e['entry_price']):.2f}"
        for e in entries
    ]
    return render_reply_card(
        f"קנית · {trading_day}",
        accent="green",
        bullets=bullets,
        footer="דוח סוף יום יישלח אחרי סגירת וול סטריט",
    )


def card_portfolio(data: dict[str, Any]) -> bytes:
    """Portfolio card: clear per-stock blocks, chips at bottom, no caption needed."""
    from trading_pulse.agent.portfolio_index import attach_slots_to_portfolio
    from trading_pulse.core.schedule_tz import format_local_entry_moment
    from trading_pulse.telegram.telegram_images import _pnl_color

    data = attach_slots_to_portfolio(data)
    equity = float(data.get("equity", 0))
    marked = float(data.get("open_marked_usd", data.get("open_capital_usd", 0)))
    unrealized = float(data.get("unrealized_pnl_usd", 0))
    realized = float(data.get("total_realized_pnl", 0))
    positions = data.get("open_positions") or []
    holding = [p for p in positions if p.get("status") == "holding"]
    pending = [p for p in positions if p.get("status") == "pending_market_entry"]
    holding_cap = sum(float(p.get("capital_usd", 0)) for p in holding)
    cash = float(data.get("cash_usd", max(0.0, equity - holding_cap)))

    font_title = _load_font(24, bold=True)
    font_section = _load_font(16, bold=True)
    font_label = _load_font(14)
    font_value = _load_font(18, bold=True)
    font_sym = _load_font(19, bold=True)
    font_line = _load_font(16)
    font_line_b = _load_font(16, bold=True)
    font_chip = _load_font(14, bold=True)
    font_foot = _load_font(13)

    chips = ["מכור 1 $100", "מכור 1 200$ קנה 2 100$", "תקנה 1 $20"]
    content_w = CARD_W - PAD * 2 - INNER * 2
    x0 = PAD + 4
    x1 = CARD_W - PAD - 4
    x_right = CARD_W - PAD - INNER

    h = PAD + 50
    h += 5 * 52  # summary stats (incl. cash)
    h += 14
    if pending:
        h += 28 + len(pending) * 58 + 8
    if holding:
        h += 28 + len(holding) * 108 + 8
    elif not pending:
        h += 36
    h += 36 + len(chips) * 36 + 28 + PAD

    img = Image.new("RGB", (CARD_W, h), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (8, 8, CARD_W - 8, h - 8),
        radius=18,
        fill=SURFACE,
        outline=BORDER,
        width=2,
    )

    y = PAD + 14
    draw.rounded_rectangle((x_right - 3, y, x_right + 1, y + 28), radius=3, fill=CYAN)
    _rtl(draw, x_right - 12, y, "תיק השקעות", font_title, TEXT)
    y += 40

    def _stat(label: str, value: str, value_color: tuple[int, int, int] = TEXT) -> None:
        nonlocal y
        draw.rounded_rectangle((x0, y, x1, y + 46), radius=12, fill=ROW_BG, outline=BORDER)
        _rtl(draw, x_right - 8, y + 6, label, font_label, MUTED)
        _rtl(draw, x_right - 8, y + 22, value, font_value, value_color)
        y += 52

    ur_sign = "+" if unrealized > 0 else ("-" if unrealized < 0 else "")
    rz_sign = "+" if realized > 0 else ("-" if realized < 0 else "")
    _stat("הון", f"${equity:.2f}")
    _stat("מזומן פנוי", f"${cash:.0f}", CYAN if cash >= 1 else MUTED)
    _stat("שווי פתוח", f"${marked:.0f}")
    _stat("רווח פתוח", f"{ur_sign}${abs(unrealized):.0f}", _pnl_color(unrealized))
    _stat("רווח ממומש", f"{rz_sign}${abs(realized):.2f}", _pnl_color(realized))
    y += 6

    def _section(title: str) -> None:
        nonlocal y
        _rtl(draw, x_right, y, title, font_section, CYAN)
        y += 26

    if pending:
        _section("מאושר — ממתין לפתיחה")
        for p in pending:
            sym = str(p["symbol"])
            cap = float(p.get("capital_usd", 0))
            when = str(p.get("scheduled_entry", "פתיחת השוק"))
            box_h = 50
            draw.rounded_rectangle((x0, y, x1, y + box_h), radius=12, fill=ROW_BG, outline=CHIP_BORDER)
            _rtl(draw, x_right - 10, y + 8, f"{sym}  ${cap:.0f}", font_sym, PINK)
            _rtl(draw, x_right - 10, y + 30, f"כניסה {when}", font_line, MUTED)
            y += box_h + 8
        y += 4

    if holding:
        _section("בתיק עכשיו")
        for i, p in enumerate(holding):
            slot = p.get("slot", "—")
            sym = str(p["symbol"])
            cap = float(p.get("capital_usd", 0))
            ep = float(p.get("entry_price") or 0)
            mv = float(p.get("marked_value_usd", cap))
            ur = float(p.get("unrealized_pnl_usd", 0))
            ur_s = "+" if ur > 0 else ("-" if ur < 0 else "")
            when = format_local_entry_moment(p.get("entry_at"))
            box_h = 92
            draw.rounded_rectangle((x0, y, x1, y + box_h), radius=12, fill=ROW_BG, outline=BORDER)
            _rtl(draw, x_right - 10, y + 10, f"#{slot}  {sym}", font_sym, CYAN)
            _rtl(draw, x_right - 10, y + 36, f"${cap:.0f}  @  ${ep:.2f}", font_line_b, TEXT)
            _rtl(draw, x_right - 10, y + 56, f"שווי ${mv:.0f}", font_line_b, TEXT)
            pnl_txt = f"{ur_s}${abs(ur):.0f}"
            draw.text((x0 + 14, y + 56), pnl_txt, fill=_pnl_color(ur), font=font_line_b)
            _rtl(draw, x_right - 10, y + 74, when, font_foot, MUTED)
            y += box_h + 14
            if i < len(holding) - 1:
                draw.line((x0 + 28, y - 7, x1 - 28, y - 7), fill=(60, 60, 95), width=2)
    elif not pending:
        _rtl(draw, x_right, y, "אין פוזיציות פתוחות", font_line, MUTED)
        y += 28

    y += 16
    _rtl(draw, x_right, y, "דוגמאות", font_section, MUTED)
    y += 24
    for chip in chips:
        chip_w = min(content_w, _text_width(draw, _pil_hebrew(chip), font_chip) + 20)
        draw.rounded_rectangle(
            (x_right - chip_w, y, x_right, y + 30),
            radius=8,
            fill=CHIP_BG,
            outline=CHIP_BORDER,
        )
        _rtl(draw, x_right - 10, y + 6, chip, font_chip, PINK)
        y += 36

    y += 4
    _rtl(draw, x_right, y, "מספרים (#1 #2…) לפי סדר בתיק", font_foot, MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def card_from_plan_summary(plan: dict[str, Any]) -> bytes:
    """Compact plan overview card (details still in table/charts)."""
    day = str(plan.get("for_trading_day", ""))
    free = float(plan.get("available_capital_usd", 0))
    invested = float(plan.get("deployed_capital_usd", 0))
    equity = float(plan.get("equity_snapshot", 0))
    recs = plan.get("recommendations") or []
    holdings = plan.get("holdings") or []
    held = {str(h["symbol"]) for h in holdings}
    new_recs = [r for r in recs if str(r["symbol"]) not in held]
    bullets = [f"מזומן ${free:.0f} · מושקע ${invested:.0f} · סה\"כ ${equity:.0f}"]
    for h in holdings[:4]:
        bullets.append(f"בתיק: {h['symbol']} ${float(h.get('capital_usd', 0)):.0f}")
    for r in new_recs[:4]:
        bullets.append(f"חדש: {r['symbol']} ${float(r.get('capital_usd', 0)):.0f}")
    if not recs and not holdings:
        bullets.append("אין המלצות היום")
    return render_reply_card(
        f"תוכנית · {day}",
        accent="cyan",
        bullets=bullets,
        chips=["הכל"] if recs else ["תיק"],
        footer="פרטים בטבלה ובגרפים למטה" if recs else "אין צורך באישור",
    )


def card_stock_detail(detail: dict[str, Any]) -> bytes:
    """Decision metrics card for one symbol (watchlist or not)."""
    from trading_pulse.agent.signal_sources import SOURCE_LABELS

    rec = detail.get("rec") or {}
    sym = str(detail.get("symbol") or rec.get("symbol") or "?")
    score = float(rec.get("score", 0))
    on_list = bool(detail.get("on_watchlist"))
    would = bool(detail.get("would_pick"))
    speculative = bool(detail.get("speculative"))

    rows: list[tuple[str, str]] = [
        ("ציון סופי", f"{score:.1f}"),
        ("ציון טכני", f"{float(rec.get('score_technical', score)):.1f}"),
        ("מחיר", f"${float(rec.get('entry_ref_price', 0)):.2f}"),
        ("5 ימים", f"{float(rec.get('ret_5d_pct', 0)):+.1f}%"),
        ("נפח", f"{float(rec.get('vol_ratio', 0)):.2f}x"),
        ("ATR", f"{float(rec.get('atr_pct', 0)):.1f}%"),
    ]
    live = detail.get("live_quote") or {}
    if live:
        last = float(live.get("last", 0))
        day_chg = float(live.get("day_change_pct", 0))
        sign = "+" if day_chg >= 0 else ""
        high = float(live.get("high", last))
        low = float(live.get("low", last))
        rows.insert(0, ("מחיר עכשיו", f"${last:.2f}"))
        rows.insert(1, ("שינוי היום", f"{sign}{day_chg:.2f}%"))
        rows.insert(2, ("טווח היום", f"${low:.2f} – ${high:.2f}"))
    if speculative:
        rows.append(
            (
                "פריצה 20י",
                "כן" if rec.get("breakout_ok") else f"{float(rec.get('near_high_pct', 0)):+.1f}%",
            )
        )
    else:
        rows.append(
            (
                "מול MA20",
                "מעל" if rec.get("momentum_ok") else f"{float(rec.get('above_ma20_pct', 0)):+.1f}%",
            )
        )
    rows.append(
        (
            "SL / TP",
            f"${float(rec.get('stop_loss_price', 0)):.2f} / ${float(rec.get('take_profit_price', 0)):.2f}",
        )
    )

    source_scores = rec.get("source_scores") or {}
    if source_scores:
        parts = [
            f"{SOURCE_LABELS.get(k, k)} {float(v):.1f}"
            for k, v in sorted(source_scores.items(), key=lambda x: -float(x[1]))
        ]
        rows.append(("מקורות", " · ".join(parts[:6])))

    if rec.get("source_disagreement"):
        rows.append(
            (
                "אי-הסכמה",
                f"std {float(rec.get('source_score_std', 0)):.1f} · פער {float(rec.get('source_score_spread', 0)):.1f}",
            )
        )

    sent = float(rec.get("sentiment_adjustment", 0) or 0)
    if sent:
        rows.append(("חדשות", f"{rec.get('sentiment_tone', '')} {sent:+.1f}"))

    bt = rec.get("backtest") or {}
    if bt.get("summary"):
        rows.append(("Backtest", str(bt.get("summary"))))

    bullets: list[str] = [
        "ברשימה" if on_list else "לא ברשימת הסריקה",
        "עובר סינון כניסה" if would else "לא עובר סינון כניסה כרגע",
    ]
    for name, ok, detail_txt in detail.get("gates") or []:
        mark = "OK" if ok else "לא"
        bullets.append(f"{mark} · {name}: {detail_txt}")

    expl = str(rec.get("explanation") or "").strip()
    if expl:
        bullets.append(expl[:180] + ("…" if len(expl) > 180 else ""))

    title = f"מעקב {sym}" if detail.get("watch_mode") else f"ניתוח {sym}"
    interval = int(detail.get("watch_interval_min") or 0)
    if detail.get("watch_mode") and interval:
        footer = f"עדכון כל {interval} דק׳ בזמן מסחר · הפסק מעקב {sym}"
    else:
        footer = "גרף מחיר נשלח בהודעה הבאה"

    return render_reply_card(
        title,
        accent="green" if would else "pink",
        subtitle=f"ציון {score:.1f} · {'ברשימה' if on_list else 'מחוץ לרשימה'}",
        rows=rows,
        bullets=bullets,
        chips=[f"הפסק מעקב {sym}"] if detail.get("watch_mode") else (
            [f"הוסף {sym}"] if not on_list else [f"הסר {sym}", "תיק"]
        ),
        footer=footer,
    )


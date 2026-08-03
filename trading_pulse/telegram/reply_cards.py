"""PIL reply cards for Telegram — dashboard look, narrow portrait."""

from __future__ import annotations

import io
import logging
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
    # Clock / media pictographs (⏰ ⏸️ …) and variation selectors also draw as boxes.
    t = re.sub(r"[\U000023E9-\U000023FA\U0000FE0F]", "", t)
    # BiDi marks help Telegram text but draw as bars here — the card does its own RTL.
    t = t.replace("\u200e", "").replace("\u200f", "")
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
    # Leave room for the accent bar on the right of the title.
    title_w = CARD_W - PAD * 2 - INNER * 2 - 16
    content_w = CARD_W - PAD * 2 - INNER * 2
    title_lines = _wrap(draw, title, font_title, title_w) or [title or "—"]

    h = PAD + 14 + len(title_lines) * 28 + 10
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
    bar_h = max(26, len(title_lines) * 26 - 4)
    draw.rounded_rectangle((x_right - 3, y, x_right + 1, y + bar_h), radius=3, fill=color)
    for line in title_lines:
        _rtl(draw, x_right - 12, y, line, font_title, TEXT)
        y += 28
    y += 8

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
        head,
        accent=accent,
        body="\n".join(body_lines),
    )


def card_sell(
    symbol: str,
    *,
    fraction: float,
    pnl_usd: float,
    cash: float,
    equity: float | None = None,
    sold_usd: float | None = None,
) -> bytes:
    pct = int(round(fraction * 100))
    outcome = "רווח ממומש" if pnl_usd >= 0 else "הפסד ממומש"
    amount = f"+${abs(pnl_usd):.2f}" if pnl_usd > 0 else (f"-${abs(pnl_usd):.2f}" if pnl_usd < 0 else "$0.00")
    rows = [
        ("מניה", symbol),
        ("נמכר", f"{pct}%" + (f" · ${sold_usd:.0f}" if sold_usd else "")),
        (outcome, amount),
        ("מזומן פנוי", f"${cash:.0f}"),
    ]
    if equity is not None:
        rows.append(("הון לאחר המכירה", f"${equity:.2f}"))
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
            "בערב — כרטיס PNG «תוכנית למחר» + גרפים (פרטים בתמונה · כיתוב #1 CLF)",
            "בבוקר — תמונת כניסה במחיר פתיחה",
            "בערב — כרטיס PNG «דוח יומי»",
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


def card_heartbeat(
    cfg: Any,
    state: dict[str, Any],
    *,
    market_day: bool = True,
    next_trading_day: str | None = None,
) -> bytes:
    """Daily alive ping — HTML key/value table → PNG (trailing-sign numbers)."""
    from trading_pulse.telegram.html_tables import card_png_from_html, html_heartbeat
    from trading_pulse.telegram.telegram_images import _pil_hebrew, _render_table

    doc = html_heartbeat(
        cfg, state, market_day=market_day, next_trading_day=next_trading_day
    )

    def _pil() -> bytes:
        return _render_table(
            title=_pil_hebrew("הסוכן חי"),
            subtitle=_pil_hebrew("סיכום יומי"),
            headers=[_pil_hebrew("שדה"), _pil_hebrew("ערך")],
            rows=[[_pil_hebrew("הון"), f"${float(state.get('equity', 0)):.2f}"]],
        )

    return card_png_from_html(doc, width=560, height=1400, pil_fallback_fn=_pil)


def card_allocation_prompt(
    plan: dict[str, Any],
    options: list[dict[str, Any]],
    *,
    trading_day: str,
    state: dict[str, Any] | None = None,
) -> bytes:
    """שלב 2 — HTML comparison table → PNG."""
    del state  # kept for call-site compatibility
    from trading_pulse.telegram.html_tables import card_png_from_html, html_allocation
    from trading_pulse.telegram.telegram_images import _pil_hebrew, _render_table

    doc = html_allocation(plan, options, trading_day=trading_day)

    def _pil() -> bytes:
        return _render_table(
            title=_pil_hebrew("חלוקת הון"),
            subtitle=trading_day,
            headers=[_pil_hebrew("אופציה"), _pil_hebrew("שם")],
            rows=[
                [f"ח{o.get('id')}", _pil_hebrew(str(o.get("title") or ""))]
                for o in (options or [])[:5]
            ]
            or [["—", "—"]],
        )

    return card_png_from_html(doc, width=780, height=2000, pil_fallback_fn=_pil)


def card_entry(entries: list[dict[str, Any]], *, trading_day: str, subtitle: str | None = None) -> bytes:
    """Morning fills — HTML table → PNG."""
    from trading_pulse.telegram.html_tables import card_png_from_html, html_entry
    from trading_pulse.telegram.telegram_images import _pil_hebrew, _render_table

    doc = html_entry(entries, trading_day=trading_day, subtitle=subtitle)

    def _pil() -> bytes:
        rows = []
        for e in (entries or [])[:8]:
            rows.append(
                [
                    str(e.get("symbol") or "?"),
                    f"${float(e.get('capital_usd') or 0):.0f}",
                    f"${float(e.get('entry_price') or 0):.2f}",
                ]
            )
        return _render_table(
            title=_pil_hebrew(subtitle or "קנית"),
            subtitle=trading_day,
            headers=[_pil_hebrew("סימול"), _pil_hebrew("סכום"), _pil_hebrew("מחיר")],
            rows=rows or [["—", "—", "—"]],
        )

    return card_png_from_html(doc, width=700, height=1400, pil_fallback_fn=_pil)


def card_portfolio(data: dict[str, Any]) -> bytes:
    """Portfolio — HTML table → PNG."""
    from trading_pulse.telegram.html_tables import card_png_from_html, html_portfolio
    from trading_pulse.telegram.telegram_images import _pil_hebrew, _render_table

    doc = html_portfolio(data)

    def _pil() -> bytes:
        return _render_table(
            title=_pil_hebrew("תיק השקעות"),
            subtitle=f"equity ${float(data.get('equity', 0)):.2f}",
            headers=[_pil_hebrew("סימול"), _pil_hebrew("סכום")],
            rows=[
                [str(p.get("symbol")), f"${float(p.get('capital_usd') or 0):.0f}"]
                for p in (data.get("open_positions") or [])[:8]
            ]
            or [["—", "—"]],
        )

    return card_png_from_html(doc, width=900, height=2000, pil_fallback_fn=_pil)


def card_intraday_monitor(report: Any) -> bytes:
    """Hourly monitor — HTML table with labeled columns → PNG."""
    from trading_pulse.telegram.html_tables import card_png_from_html, html_intraday
    from trading_pulse.telegram.telegram_images import _pil_hebrew, _render_table

    doc = html_intraday(report)

    def _pil() -> bytes:
        holdings = list(getattr(report, "holdings", None) or [])[:6]
        rows = []
        for h in holdings:
            rows.append(
                [
                    str(h.get("symbol") or "?"),
                    f"${float(h.get('capital_usd') or 0):.0f}",
                    f"{float(h.get('pnl_pct') or 0):.1f}%-"
                    if float(h.get("pnl_pct") or 0) < 0
                    else f"{float(h.get('pnl_pct') or 0):.1f}%",
                ]
            )
        return _render_table(
            title=_pil_hebrew("מעקב שעתי"),
            subtitle="",
            headers=[_pil_hebrew("סימול"), _pil_hebrew("מושקע"), _pil_hebrew("מהכניסה")],
            rows=rows or [["—", "—", "—"]],
            width=700,
        )

    return card_png_from_html(doc, width=980, height=2200, pil_fallback_fn=_pil)


def card_daily_report(report: dict[str, Any]) -> bytes:
    """EOD report — HTML Hebrew tables → PNG."""
    from trading_pulse.telegram.html_tables import card_png_from_html, html_daily_report
    from trading_pulse.telegram.telegram_images import _pil_hebrew, _render_table

    doc = html_daily_report(report)

    def _pil() -> bytes:
        day = str(report.get("trading_day") or "")
        return _render_table(
            title=_pil_hebrew(f"דוח יומי {day}"),
            subtitle=f"P/L {float(report.get('pnl_usd') or 0):.2f}",
            headers=[_pil_hebrew("סימול"), _pil_hebrew("רווח")],
            rows=[
                [str(p.get("symbol")), f"${float(p.get('unrealized_pnl_usd') or 0):.2f}"]
                for p in (report.get("held_eod") or [])[:8]
            ]
            or [["—", "—"]],
        )

    return card_png_from_html(doc, width=900, height=2200, pil_fallback_fn=_pil)


def card_weekly_watchlist(result: dict[str, Any]) -> bytes:
    """Weekly scan summary — HTML labeled card → PNG."""
    from trading_pulse.telegram.html_tables import card_png_from_html, html_weekly_watchlist
    from trading_pulse.telegram.telegram_images import _pil_hebrew, _render_table

    doc = html_weekly_watchlist(result)

    def _pil() -> bytes:
        week = str(result.get("week") or "")
        syms = []
        for item in (result.get("symbols") or [])[:10]:
            syms.append(str(item.get("symbol") if isinstance(item, dict) else item))
        rows = [[str(i + 1), s] for i, s in enumerate(syms)] or [["—", "—"]]
        return _render_table(
            title=_pil_hebrew(f"רשימת מסחר {week}"),
            subtitle=f"{int(result.get('scanned') or 0)}/{int(result.get('universe_size') or 0)}",
            headers=["#", _pil_hebrew("סימול")],
            rows=rows,
        )

    return card_png_from_html(doc, width=720, height=2000, pil_fallback_fn=_pil)


def card_from_plan_summary(plan: dict[str, Any]) -> bytes:
    """Evening plan — full labeled HTML tables → PNG (not a text wall)."""
    from trading_pulse.telegram.html_tables import card_png_from_html, html_plan
    from trading_pulse.telegram.telegram_images import _pil_hebrew, _render_table

    doc = html_plan(plan)

    def _pil() -> bytes:
        day = str(plan.get("for_trading_day") or "")
        free = float(plan.get("available_capital_usd") or 0)
        recs = plan.get("recommendations") or []
        holdings = plan.get("holdings") or []
        held = {str(h["symbol"]) for h in holdings}
        new_recs = [r for r in recs if str(r["symbol"]) not in held]
        rows = [
            [str(r.get("symbol")), f"${float(r.get('capital_usd') or 0):.0f}"]
            for r in new_recs[:8]
        ] or [["—", "—"]]
        return _render_table(
            title=_pil_hebrew(f"תוכנית {day}"),
            subtitle=f"cash ${free:.0f}",
            headers=[_pil_hebrew("סימול"), _pil_hebrew("סכום")],
            rows=rows,
        )

    return card_png_from_html(doc, width=920, height=3200, pil_fallback_fn=_pil)


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

    watch_reason = str(detail.get("watch_reason") or "").strip()
    if detail.get("watch_mode") and watch_reason:
        rows = [("סיבת המעקב", watch_reason), *rows]

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


def stack_png_vertical(top: bytes, bottom: bytes, *, gap: int = 8, bg=None) -> bytes:
    """Stack two PNGs into one image (same width; bottom scaled if needed)."""
    fill = bg if bg is not None else BG
    top_im = Image.open(io.BytesIO(top)).convert("RGB")
    bot_im = Image.open(io.BytesIO(bottom)).convert("RGB")
    if bot_im.width != top_im.width:
        new_h = max(1, int(bot_im.height * (top_im.width / bot_im.width)))
        bot_im = bot_im.resize((top_im.width, new_h), Image.Resampling.LANCZOS)
    out = Image.new("RGB", (top_im.width, top_im.height + gap + bot_im.height), fill)
    out.paste(top_im, (0, 0))
    out.paste(bot_im, (0, top_im.height + gap))
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def chart_with_recommendation_details(
    rec: dict[str, Any],
    idx: int,
    trading_day: str,
    *,
    signal_lines: list[str] | None = None,
    held: bool = False,
) -> bytes | None:
    """Price chart + Hebrew labeled details strip (details not in Telegram caption)."""
    from trading_pulse.telegram.html_tables import card_png_from_html, html_recommendation
    from trading_pulse.telegram.telegram_images import render_recommendation_chart

    chart = render_recommendation_chart(rec, idx, trading_day)
    if not chart:
        return None
    try:
        doc = html_recommendation(
            rec,
            idx,
            trading_day,
            signal_lines=signal_lines,
            held=held,
        )
        details = card_png_from_html(doc, width=920, height=2200)
        return stack_png_vertical(chart, details)
    except Exception:
        return chart


def offer_cubes_card(
    rec: dict[str, Any],
    *,
    position_no: int,
    total: int,
    cash_free: float,
    suggested_usd: float,
    rank: int | None = None,
    swap: dict[str, Any] | None = None,
    swap_from: str | None = None,
    swap_from_score: float | None = None,
) -> bytes | None:
    """PNG card: metric cubes + cash/swap/how-to (single message, no action strip)."""
    from trading_pulse.agent.offer_queue import (
        build_offer_action_cubes,
        build_offer_metric_cubes,
    )
    from trading_pulse.telegram.html_tables import card_png_from_html, html_offer_cubes

    try:
        if swap is None and swap_from:
            swap = {
                "from_symbol": swap_from,
                "from_score": swap_from_score if swap_from_score is not None else 0.0,
            }
        cubes = build_offer_metric_cubes(rec, rank=rank if rank is not None else position_no)
        cubes.extend(
            build_offer_action_cubes(
                rec,
                cash_free=cash_free,
                suggested_usd=suggested_usd,
                swap=swap,
            )
        )
        doc = html_offer_cubes(
            rec,
            position_no=position_no,
            total=total,
            cash_free=cash_free,
            suggested_usd=suggested_usd,
            cubes=cubes,
            swap_from=str(swap["from_symbol"]) if swap else None,
            swap_from_score=float(swap["from_score"]) if swap and swap.get("from_score") is not None else None,
            include_action_footer=False,
        )
        return card_png_from_html(doc, width=920, height=2200)
    except Exception:
        logging.exception("offer_cubes_card failed for %s", rec.get("symbol"))
        return None


def portfolio_review_cubes_card(plan: dict[str, Any]) -> bytes | None:
    """PNG card: pre-market holdings review as labeled cubes."""
    from trading_pulse.agent.holdings_review import build_portfolio_review_cubes
    from trading_pulse.telegram.html_tables import card_png_from_html, html_portfolio_review_cubes

    try:
        holdings = plan.get("holdings") or []
        held = {str(h.get("symbol")) for h in holdings}
        offers_n = sum(
            1
            for r in (plan.get("recommendations") or [])
            if not r.get("below_bar")
            and not r.get("approved")
            and not r.get("offer_skipped")
            and str(r.get("symbol")) not in held
        )
        cubes = build_portfolio_review_cubes(plan)
        doc = html_portfolio_review_cubes(
            cubes=cubes,
            cash_free=float(plan.get("available_capital_usd") or 0),
            offers_n=offers_n,
        )
        return card_png_from_html(doc, width=920, height=2000)
    except Exception:
        logging.exception("portfolio_review_cubes_card failed")
        return None


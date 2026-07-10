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
    for chip in chips or []:
        h += 34
    for bullet in bullets or []:
        h += len(_wrap(draw, f"• {bullet}", font_body, content_w)) * 20 + 4
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

    for bullet in bullets or []:
        for line in _wrap(draw, f"• {bullet}", font_body, content_w):
            _rtl(draw, x_right, y, line, font_body, TEXT)
            y += 20
        y += 4

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
        chips=["תיק", "מכור 2 20$", "תקנה 1 $20", "מדריך"],
        footer="אין מזומן? מכור חלק ואז קנה / החלף",
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
    """Narrow portfolio card — all details in the image (mobile-friendly)."""
    from trading_pulse.agent.portfolio_index import attach_slots_to_portfolio
    from trading_pulse.core.schedule_tz import format_local_entry_moment

    data = attach_slots_to_portfolio(data)
    equity = float(data.get("equity", 0))
    marked = float(data.get("open_marked_usd", data.get("open_capital_usd", 0)))
    unrealized = float(data.get("unrealized_pnl_usd", 0))
    ur_sign = "+" if unrealized >= 0 else ""
    positions = data.get("open_positions") or []
    holding = [p for p in positions if p.get("status") == "holding"]
    pending = [p for p in positions if p.get("status") == "pending_market_entry"]

    rows: list[tuple[str, str]] = [
        ("הון", f"${equity:.2f}"),
        ("שווי פתוח", f"${marked:.0f}"),
        ("רווח פתוח", f"{ur_sign}${unrealized:.0f}"),
    ]
    bullets: list[str] = []
    for p in holding:
        slot = p.get("slot", "—")
        sym = str(p["symbol"])
        cap = float(p.get("capital_usd", 0))
        ep = float(p.get("entry_price") or 0)
        mv = float(p.get("marked_value_usd", cap))
        ur = float(p.get("unrealized_pnl_usd", 0))
        ur_s = "+" if ur >= 0 else ""
        when = format_local_entry_moment(p.get("entry_at"))
        bullets.append(f"#{slot} {sym}  ${cap:.0f} @ ${ep:.2f}")
        bullets.append(f"    → שווי ${mv:.0f}  ({ur_s}${ur:.0f})  · {when}")
    for p in pending:
        sym = str(p["symbol"])
        cap = float(p.get("capital_usd", 0))
        when = str(p.get("scheduled_entry", "פתיחה"))
        bullets.append(f"⏳ {sym}  ${cap:.0f}  · כניסה {when}")
    if not bullets:
        bullets.append("אין פוזיציות פתוחות")

    return render_reply_card(
        "תיק השקעות",
        accent="cyan",
        rows=rows,
        bullets=bullets,
        chips=["מכור 1", "מכור 2 20$", "תקנה 1 $20"],
        footer="מספרים (#1 #2…) לפי סדר בתיק",
    )


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

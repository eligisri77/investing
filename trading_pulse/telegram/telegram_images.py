"""Render trading summary tables as images for Telegram."""

from __future__ import annotations

import io
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Dark neon theme (matches web dashboard)
BG = (10, 10, 24)
SURFACE = (18, 18, 36)
HEADER_BG = (24, 24, 48)
BORDER = (40, 40, 70)
TEXT = (230, 235, 245)
MUTED = (140, 145, 165)
CYAN = (0, 240, 255)
PINK = (255, 45, 149)
GREEN = (0, 255, 136)
RED = (255, 51, 102)
ROW_ALT = (14, 14, 30)

FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/david.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    bold_candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    paths = (bold_candidates if bold else []) + FONT_CANDIDATES
    for path in paths:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_height(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), "Ag", font=font)
    return box[3] - box[1]


def _pnl_color(value: float) -> tuple[int, int, int]:
    if value > 0:
        return GREEN
    if value < 0:
        return RED
    return TEXT


def _render_table(
    *,
    title: str,
    subtitle: str,
    headers: list[str],
    rows: list[list[str]],
    row_colors: list[tuple[int, int, int]] | None = None,
    width: int = 900,
) -> bytes:
    font_title = _load_font(26, bold=True)
    font_sub = _load_font(16)
    font_head = _load_font(15, bold=True)
    font_cell = _load_font(15)

    pad_x = 28
    pad_y = 24
    row_h = 38
    header_h = 42

    tmp = Image.new("RGB", (width, 200), BG)
    draw = ImageDraw.Draw(tmp)
    col_count = len(headers)
    usable = width - pad_x * 2
    col_w = usable // col_count

    content_h = pad_y + 70 + header_h + row_h * max(len(rows), 1) + pad_y
    img = Image.new("RGB", (width, content_h), BG)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((12, 12, width - 12, content_h - 12), radius=16, fill=SURFACE, outline=BORDER, width=2)
    y = 28
    draw.text((pad_x, y), title, fill=CYAN, font=font_title)
    y += 36
    draw.text((pad_x, y), subtitle, fill=MUTED, font=font_sub)
    y += 40

    # Header
    draw.rectangle((pad_x, y, width - pad_x, y + header_h), fill=HEADER_BG)
    for i, head in enumerate(headers):
        x = pad_x + i * col_w + 10
        draw.text((x, y + 10), head, fill=PINK, font=font_head)
    y += header_h

    for r_idx, row in enumerate(rows):
        bg = ROW_ALT if r_idx % 2 else SURFACE
        draw.rectangle((pad_x, y, width - pad_x, y + row_h), fill=bg)
        for c_idx, cell in enumerate(row):
            x = pad_x + c_idx * col_w + 10
            color = row_colors[r_idx][c_idx] if row_colors and r_idx < len(row_colors) else TEXT
            draw.text((x, y + 10), cell, fill=color, font=font_cell)
        y += row_h

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _pil_hebrew(text: str) -> str:
    """Render Hebrew correctly on PIL's LTR canvas."""
    try:
        from bidi.algorithm import get_display

        return get_display(text)
    except Exception:
        return text


def _shares_count(capital_usd: float, entry_price: float | None) -> str:
    if not entry_price or entry_price <= 0:
        return "—"
    qty = capital_usd / entry_price
    if qty >= 10:
        return f"{qty:.1f}"
    if qty >= 1:
        return f"{qty:.2f}"
    return f"{qty:.3f}"


def render_portfolio_image(data: dict[str, Any]) -> bytes:
    from trading_pulse.agent.portfolio_index import attach_slots_to_portfolio
    from trading_pulse.core.schedule_tz import format_local_entry_moment

    data = attach_slots_to_portfolio(data)
    equity = float(data.get("equity", 0))
    invested = float(data.get("open_capital_usd", 0))
    marked = float(data.get("open_marked_usd", invested))
    pnl = float(data.get("total_realized_pnl", 0))
    unrealized = float(data.get("unrealized_pnl_usd", 0))
    sign = "+" if pnl >= 0 else ""
    ur_sign = "+" if unrealized >= 0 else ""
    open_positions = data.get("open_positions") or []
    pending = [p for p in open_positions if p.get("status") == "pending_market_entry"]
    holding = [p for p in open_positions if p.get("status") == "holding"]

    if pending and not holding:
        title = _pil_hebrew("תיק — מאושר, ממתין לפתיחה")
    else:
        title = _pil_hebrew("תיק השקעות — מה קנית")

    if pending:
        subtitle = _pil_hebrew(
            f"הון ${equity:.2f}  |  ממומש {sign}${pnl:.2f}  |  "
            f"{len(pending)} מניות ממתינות לפתיחת השוק"
        )
    else:
        subtitle = _pil_hebrew(
            f"הון ${equity:.2f}  |  שווי ${marked:.0f}  |  "
            f"רווח פתוח {ur_sign}${unrealized:.2f}  |  ממומש {sign}${pnl:.2f}"
        )

    headers = [
        _pil_hebrew("#"),
        _pil_hebrew("מניה"),
        _pil_hebrew("סכום"),
        _pil_hebrew("@מחיר"),
        _pil_hebrew("שווי"),
        _pil_hebrew("רווח פתוח"),
        _pil_hebrew("אושר / כניסה"),
    ]
    rows: list[list[str]] = []
    colors: list[list[tuple[int, int, int]]] = []

    for p in sorted(open_positions, key=lambda x: (x.get("entry_at") or x.get("approved_at") or "", x["symbol"])):
        symbol = str(p["symbol"])
        capital = float(p.get("capital_usd", 0))
        entry = p.get("entry_price") or p.get("entry_ref_price")
        entry_f = float(entry) if entry else 0.0
        if p.get("status") == "pending_market_entry":
            approved = format_local_entry_moment(p.get("approved_at"))
            entry_when = str(p.get("scheduled_entry", "פתיחה"))
            rows.append(
                [
                    "—",
                    f"{symbol} *",
                    f"${capital:.0f}",
                    f"~${entry_f:.2f}" if entry_f > 0 else "—",
                    "—",
                    "—",
                    _pil_hebrew(f"{approved} → {entry_when}"),
                ]
            )
            colors.append([MUTED, PINK, TEXT, MUTED, MUTED, MUTED, MUTED])
            continue
        when = format_local_entry_moment(p.get("entry_at"))
        if p.get("status") == "holding":
            marked_val = float(p.get("marked_value_usd", capital))
            ur = float(p.get("unrealized_pnl_usd", 0))
            ur_pct = float(p.get("unrealized_pnl_pct", 0))
            ur_sign_row = "+" if ur >= 0 else ""
            slot = str(p.get("slot", "—"))
            rows.append(
                [
                    slot,
                    symbol,
                    f"${capital:.0f}",
                    f"${entry_f:.2f}" if entry_f > 0 else "—",
                    f"${marked_val:.0f}",
                    f"{ur_sign_row}${ur:.0f} ({ur_sign_row}{ur_pct:.1f}%)",
                    when,
                ]
            )
            colors.append([CYAN, CYAN, TEXT, GREEN, TEXT, _pnl_color(ur), MUTED])
        else:
            ref = float(p.get("entry_ref_price", 0) or 0)
            rows.append(
                [
                    "—",
                    f"{symbol} *",
                    f"${capital:.0f}",
                    f"~${ref:.2f}" if ref > 0 else "—",
                    "—",
                    "—",
                    _pil_hebrew("ממתין"),
                ]
            )
            colors.append([MUTED, PINK, TEXT, MUTED, MUTED, MUTED, MUTED])

    if not rows:
        rows = [[_pil_hebrew("—"), _pil_hebrew("אין מניות"), "—", "—", "—", "—", "—"]]
        colors = [[MUTED] * 7]

    footnote = _pil_hebrew(
        "מכור 1 · מכור 2 $200 · מכור 1 תקנה SYMBOL $200 · סימולציה dry-run"
    )

    return _render_portfolio_holdings(
        title=title,
        subtitle=subtitle,
        footnote=footnote,
        headers=headers,
        rows=rows,
        row_colors=colors,
        width=1040,
    )


def _portfolio_column_widths(col_count: int, usable: int) -> list[int]:
    """Wider columns for P/L and time."""
    if col_count == 7:
        ratios = [0.05, 0.10, 0.11, 0.12, 0.12, 0.26, 0.24]
    elif col_count == 6:
        ratios = [0.11, 0.12, 0.13, 0.12, 0.28, 0.24]
        widths = [max(56, int(usable * r)) for r in ratios]
        widths[-1] += usable - sum(widths)
        return widths
    base = usable // max(col_count, 1)
    return [base] * col_count


def _render_portfolio_holdings(
    *,
    title: str,
    subtitle: str,
    footnote: str,
    headers: list[str],
    rows: list[list[str]],
    row_colors: list[list[tuple[int, int, int]]] | None = None,
    width: int = 920,
) -> bytes:
    font_title = _load_font(26, bold=True)
    font_sub = _load_font(16)
    font_head = _load_font(14, bold=True)
    font_cell = _load_font(14)
    font_note = _load_font(13)

    pad_x = 28
    row_h = 40
    header_h = 44
    col_count = len(headers)
    usable = width - pad_x * 2
    col_widths = _portfolio_column_widths(col_count, usable)

    content_h = 28 + 36 + 36 + header_h + row_h * max(len(rows), 1) + (28 if footnote else 16) + 20
    img = Image.new("RGB", (width, content_h), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((12, 12, width - 12, content_h - 12), radius=16, fill=SURFACE, outline=BORDER, width=2)

    y = 28
    draw.text((pad_x, y), title, fill=CYAN, font=font_title)
    y += 36
    draw.text((pad_x, y), subtitle, fill=MUTED, font=font_sub)
    y += 36

    draw.rectangle((pad_x, y, width - pad_x, y + header_h), fill=HEADER_BG)
    x = pad_x
    for i, head in enumerate(headers):
        draw.text((x + 8, y + 12), head, fill=PINK, font=font_head)
        x += col_widths[i]
    y += header_h

    for r_idx, row in enumerate(rows):
        bg = ROW_ALT if r_idx % 2 else SURFACE
        draw.rectangle((pad_x, y, width - pad_x, y + row_h), fill=bg)
        x = pad_x
        for c_idx, cell in enumerate(row):
            color = row_colors[r_idx][c_idx] if row_colors and r_idx < len(row_colors) else TEXT
            draw.text((x + 8, y + 11), cell, fill=color, font=font_cell)
            x += col_widths[c_idx]
        y += row_h

    if footnote:
        draw.text((pad_x, y + 4), footnote, fill=MUTED, font=font_note)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_plan_image(plan: dict[str, Any]) -> bytes:
    day = plan.get("for_trading_day", "")
    equity = float(plan.get("equity_snapshot", 0))
    free = float(plan.get("available_capital_usd", equity))
    subtitle = f"Day {day}  |  Equity ${equity:.0f}  |  Free ${free:.0f}"

    headers = ["#", "Symbol", "Amount", "SL", "TP"]
    rows: list[list[str]] = []
    colors: list[list[tuple[int, int, int]]] = []

    for h in plan.get("holdings") or []:
        rows.append(
            [
                "H",
                str(h["symbol"]),
                f"${float(h['capital_usd']):.0f}",
                f"{h.get('days_held', 0)}d",
                "hold",
            ]
        )
        colors.append([CYAN, CYAN, TEXT, MUTED, MUTED])

    for idx, rec in enumerate(plan.get("recommendations") or [], start=1):
        sl = int(float(rec.get("stop_loss_pct", 0)) * 100)
        tp = int(float(rec.get("take_profit_pct", 0)) * 100)
        rows.append(
            [
                str(idx),
                str(rec["symbol"]),
                f"${float(rec['capital_usd']):.0f}",
                f"-{sl}%",
                f"+{tp}%",
            ]
        )
        colors.append([TEXT, PINK, TEXT, RED, GREEN])

    if not rows:
        rows = [["—", "—", "—", "—", "No picks"]]
        colors = [[MUTED] * 5]

    return _render_table(title=f"Plan / תוכנית {day}", subtitle=subtitle, headers=headers, rows=rows, row_colors=colors)


def render_report_image(report: dict[str, Any]) -> bytes:
    day = report.get("trading_day", "")
    pnl = float(report.get("pnl_usd", 0))
    sign = "+" if pnl >= 0 else ""
    subtitle = (
        f"Day {day}  |  ${report['equity_before']} -> ${report['equity_after']}  |  "
        f"P/L {sign}${pnl:.2f}"
    )
    headers = ["Symbol", "Action", "Days", "P/L", "%"]
    rows: list[list[str]] = []
    colors: list[list[tuple[int, int, int]]] = []

    reason_map = {
        "stop_loss": "Stop",
        "take_profit": "Target",
        "close": "Close",
        "max_hold_days": "Max days",
    }

    for t in report.get("executed") or []:
        p = float(t.get("pnl_usd", 0))
        ps = "+" if p >= 0 else ""
        rows.append(
            [
                str(t["symbol"]),
                reason_map.get(t.get("exit_reason", ""), str(t.get("exit_reason", ""))),
                str(t.get("days_held", "—")),
                f"{ps}${p:.2f}",
                f"{float(t.get('pnl_pct', 0)):+.1f}%",
            ]
        )
        colors.append([TEXT, TEXT, TEXT, _pnl_color(p), _pnl_color(p)])

    for pos in report.get("held_eod") or []:
        ur = float(pos.get("unrealized_pnl_usd", 0))
        ps = "+" if ur >= 0 else ""
        rows.append(
            [
                str(pos["symbol"]),
                "Holding",
                str(pos.get("days_held", 0)),
                f"{ps}${ur:.2f}" if pos.get("unrealized_pnl_usd") is not None else "—",
                f"{float(pos.get('unrealized_pnl_pct', 0)):+.1f}%" if pos.get("unrealized_pnl_pct") is not None else "—",
            ]
        )
        colors.append([CYAN, CYAN, MUTED, _pnl_color(ur), _pnl_color(ur)])

    if not rows:
        rows = [["—", "—", "—", "—", "No activity"]]
        colors = [[MUTED] * 5]

    return _render_table(title=f"Report / דוח {day}", subtitle=subtitle, headers=headers, rows=rows, row_colors=colors)


def _series_values(df: Any, col: str) -> list[float]:
    series = df[col]
    if hasattr(series, "columns"):
        series = series.iloc[:, 0]
    return [float(v) for v in series.dropna().tolist()]


def _fetch_recent_closes(symbol: str, days: int = 35) -> tuple[list[str], list[float]]:
    import yfinance as yf

    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days + 10)
    df = yf.download(
        symbol,
        start=start.isoformat(),
        end=end.isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    ).dropna()
    if df.empty:
        return [], []
    closes = _series_values(df, "Close")
    labels: list[str] = []
    for idx in df.index[-len(closes) :]:
        labels.append(idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10])
    if len(labels) > days:
        labels = labels[-days:]
        closes = closes[-days:]
    return labels, closes


def _fetch_recent_ohlc(symbol: str, days: int = 40) -> list[dict[str, Any]]:
    """Daily OHLC bars newest-last for candlestick charts."""
    import yfinance as yf

    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days + 15)
    df = yf.download(
        symbol,
        start=start.isoformat(),
        end=end.isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    ).dropna()
    if df is None or df.empty:
        return []
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df = df.copy()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    bars: list[dict[str, Any]] = []
    for idx in df.index:
        try:
            o = float(df.loc[idx, "Open"])
            h = float(df.loc[idx, "High"])
            l = float(df.loc[idx, "Low"])
            c = float(df.loc[idx, "Close"])
        except (TypeError, ValueError, KeyError):
            continue
        label = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        bars.append({"date": label, "open": o, "high": h, "low": l, "close": c})
    if len(bars) > days:
        bars = bars[-days:]
    return bars


def render_japanese_candlestick_chart(rec: dict[str, Any], idx: int, trading_day: str) -> bytes | None:
    """Japanese candlestick chart for Rising Three / שיטה 2 picks."""
    symbol = str(rec.get("symbol", "")).upper()
    bars = _fetch_recent_ohlc(symbol, days=40)
    if len(bars) < 5:
        logging.warning("Candlestick skip %s: not enough OHLC", symbol)
        return None

    width, height = 960, 560
    pad_l, pad_r, pad_t, pad_b = 58, 30, 86, 56
    chart_l, chart_r = pad_l, width - pad_r
    chart_t, chart_b = pad_t, height - pad_b

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (10, 10, width - 10, height - 10),
        radius=16,
        fill=SURFACE,
        outline=BORDER,
        width=2,
    )

    font_title = _load_font(24, bold=True)
    font_sub = _load_font(14)
    font_axis = _load_font(12)
    font_lbl = _load_font(13, bold=True)

    strategy = str(rec.get("strategy") or "")
    price = float(rec.get("entry_ref_price", bars[-1]["close"]))
    sl_price = float(rec.get("method2_stop_ref") or rec.get("stop_loss_price") or price * 0.88)
    tp_price = float(rec.get("take_profit_price") or price * 1.12)
    entry_ref = float(rec.get("method2_entry_ref") or price)

    if strategy == "method2":
        strat_label = f"שיטה 2 · {rec.get('trigger') or ''}"
        highlight_n = 3
    elif strategy == "rising_three_methods":
        weak = " · חלש" if rec.get("pattern_weak") else ""
        strat_label = f"Rising Three Methods{weak}"
        highlight_n = 5
    else:
        strat_label = "נרות יפניים"
        highlight_n = 0

    title = f"#{idx} {symbol} · נרות יפניים"
    subtitle = (
        f"{strat_label} · Ref ${price:.2f} · Day {trading_day} · "
        f"SL ${sl_price:.2f} · TP ${tp_price:.2f}"
    )
    draw.text((pad_l, 22), title, fill=CYAN, font=font_title)
    draw.text((pad_l, 52), subtitle, fill=MUTED, font=font_sub)

    lows = [b["low"] for b in bars] + [sl_price]
    highs = [b["high"] for b in bars] + [tp_price, entry_ref]
    y_min = min(lows) * 0.985
    y_max = max(highs) * 1.015
    if y_max <= y_min:
        y_max = y_min + 1.0

    def y_map(val: float) -> int:
        ratio = (val - y_min) / (y_max - y_min)
        return int(chart_b - ratio * (chart_b - chart_t))

    for i in range(5):
        y = chart_t + int((chart_b - chart_t) * i / 4)
        draw.line((chart_l, y, chart_r, y), fill=BORDER, width=1)
        val = y_max - (y_max - y_min) * i / 4
        draw.text((8, y - 7), f"${val:.1f}", fill=MUTED, font=font_axis)

    # Guides
    for val, color, label in (
        (sl_price, RED, "Stop"),
        (tp_price, GREEN, "Target"),
    ):
        y = y_map(val)
        draw.line((chart_l, y, chart_r, y), fill=color, width=2)
        draw.text((chart_r - 72, y - 16), label, fill=color, font=font_lbl)
    if strategy == "method2":
        ey = y_map(entry_ref)
        draw.line((chart_l, ey, chart_r, ey), fill=PINK, width=2)
        draw.text((chart_r - 78, ey - 16), "Entry", fill=PINK, font=font_lbl)

    n = len(bars)
    slot = max(4, (chart_r - chart_l) // max(n, 1))
    body_w = max(3, min(14, slot - 2))

    for i, bar in enumerate(bars):
        x_center = chart_l + int((chart_r - chart_l) * (i + 0.5) / n)
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        y_o, y_c = y_map(o), y_map(c)
        y_h, y_l = y_map(h), y_map(l)
        bull = c >= o
        color = GREEN if bull else RED
        # Wick
        draw.line((x_center, y_h, x_center, y_l), fill=color, width=2)
        # Body
        top, bot = min(y_o, y_c), max(y_o, y_c)
        if bot - top < 2:
            bot = top + 2
        left, right = x_center - body_w // 2, x_center + body_w // 2
        draw.rectangle((left, top, right, bot), fill=color, outline=color)

        # Highlight pattern window (last N bars)
        if highlight_n and i >= n - highlight_n:
            draw.rectangle(
                (left - 2, min(y_h, top) - 2, right + 2, max(y_l, bot) + 2),
                outline=CYAN,
                width=2,
            )

    footer = f"Last ${bars[-1]['close']:.2f} · {bars[0]['date']} → {bars[-1]['date']}"
    if strategy == "rising_three_methods":
        footer += " · מסומנים 5 הנרות של התבנית"
    elif strategy == "method2":
        footer += " · מסומנים נרות הטריגר"
    draw.text((pad_l, height - 36), footer, fill=TEXT, font=font_sub)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_recommendation_chart(rec: dict[str, Any], idx: int, trading_day: str) -> bytes | None:
    """Mini price chart with stop/target lines for one recommendation."""
    strategy = str(rec.get("strategy") or "")
    if strategy in {"rising_three_methods", "method2"}:
        candle = render_japanese_candlestick_chart(rec, idx, trading_day)
        if candle:
            return candle
        # Fall through to line chart if OHLC missing.

    symbol = str(rec.get("symbol", "")).upper()
    labels, closes = _fetch_recent_closes(symbol)
    if len(closes) < 3:
        logging.warning("Chart skip %s: not enough price data", symbol)
        return None

    width, height = 920, 520
    pad_l, pad_r, pad_t, pad_b = 56, 28, 78, 52
    chart_l = pad_l
    chart_r = width - pad_r
    chart_t = pad_t
    chart_b = height - pad_b

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((10, 10, width - 10, height - 10), radius=16, fill=SURFACE, outline=BORDER, width=2)

    font_title = _load_font(24, bold=True)
    font_sub = _load_font(15)
    font_axis = _load_font(12)
    font_lbl = _load_font(13, bold=True)

    price = float(rec.get("entry_ref_price", closes[-1]))
    sl_price = float(rec.get("stop_loss_price", price * 0.88))
    tp_price = float(rec.get("take_profit_price", price * 1.12))
    score = float(rec.get("score", 0))

    title = f"#{idx} {symbol}"
    subtitle = (
        f"Score {score:.1f} · Ref ${price:.2f} · Day {trading_day} · "
        f"SL ${sl_price:.2f} · TP ${tp_price:.2f}"
    )
    draw.text((pad_l, 24), title, fill=CYAN, font=font_title)
    draw.text((pad_l, 52), subtitle, fill=MUTED, font=font_sub)

    y_min = min(min(closes), sl_price) * 0.985
    y_max = max(max(closes), tp_price) * 1.015
    if y_max <= y_min:
        y_max = y_min + 1

    def y_map(val: float) -> int:
        ratio = (val - y_min) / (y_max - y_min)
        return int(chart_b - ratio * (chart_b - chart_t))

    # Grid + Y labels
    for i in range(5):
        y = chart_t + int((chart_b - chart_t) * i / 4)
        draw.line((chart_l, y, chart_r, y), fill=BORDER, width=1)
        val = y_max - (y_max - y_min) * i / 4
        draw.text((8, y - 7), f"${val:.1f}", fill=MUTED, font=font_axis)

    # Stop / target guides
    sl_y = y_map(sl_price)
    tp_y = y_map(tp_price)
    draw.line((chart_l, sl_y, chart_r, sl_y), fill=RED, width=2)
    draw.line((chart_l, tp_y, chart_r, tp_y), fill=GREEN, width=2)
    draw.text((chart_r - 72, sl_y - 16), "Stop", fill=RED, font=font_lbl)
    draw.text((chart_r - 62, tp_y - 16), "Target", fill=GREEN, font=font_lbl)

    n = len(closes)
    points: list[tuple[int, int]] = []
    for i, close in enumerate(closes):
        x = chart_l + int((chart_r - chart_l) * i / max(n - 1, 1))
        y = y_map(close)
        points.append((x, y))

    if len(points) >= 2:
        draw.line(points, fill=CYAN, width=3)
    for i, (x, y) in enumerate(points):
        color = PINK if i == len(points) - 1 else CYAN
        radius = 5 if i == len(points) - 1 else 3
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    ret_5d = rec.get("ret_5d_pct")
    atr = rec.get("atr_pct")
    footer_parts = [f"Last ${closes[-1]:.2f}"]
    if ret_5d is not None:
        footer_parts.append(f"5d {float(ret_5d):+.1f}%")
    if atr is not None:
        footer_parts.append(f"ATR {float(atr):.1f}%")
    draw.text((pad_l, height - 34), " · ".join(footer_parts), fill=TEXT, font=font_sub)

    if len(labels) >= 2:
        draw.text((chart_l, height - 34), labels[0], fill=MUTED, font=font_axis)
        draw.text((chart_r - 78, height - 34), labels[-1], fill=MUTED, font=font_axis)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

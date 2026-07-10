"""Draw Telegram guide cards with PIL (same approach as portfolio/plan tables)."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from trading_pulse.telegram.telegram_images import (
    BG,
    BORDER,
    CYAN,
    MUTED,
    PINK,
    SURFACE,
    TEXT,
    _load_font,
    _pil_hebrew,
    _text_height,
    _text_width,
)

CARD_W = 440
PAD = 18
INNER = 14
ACCENT = (168, 85, 247)
CHIP_BG = (40, 12, 28)
CHIP_BORDER = (90, 25, 55)
ROW_BG = (12, 12, 26)
MARKER_BG = (8, 36, 42)
MARKER_BORDER = (20, 90, 100)


def _wrap_lines(
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


def _draw_rtl(
    draw: ImageDraw.ImageDraw,
    x_right: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> int:
    """Draw RTL text right-aligned; return width used."""
    shown = _pil_hebrew(text)
    w = _text_width(draw, shown, font)
    draw.text((x_right - w, y), shown, fill=fill, font=font)
    return w


def _rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill, outline=None, radius=14, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _measure_commands(title: str, items: list[dict[str, Any]], warning: str = "") -> int:
    tmp = Image.new("RGB", (CARD_W, 80), BG)
    draw = ImageDraw.Draw(tmp)
    font_title = _load_font(22, bold=True)
    font_chip = _load_font(14, bold=True)
    font_desc = _load_font(14)
    font_warn = _load_font(13)
    content_w = CARD_W - PAD * 2 - INNER * 2
    h = PAD + 8 + 36
    if warning:
        h += 28
    h += 8
    for item in items:
        chip_lines = _wrap_lines(draw, str(item.get("cmd", "")), font_chip, content_w - 20)
        desc_lines = _wrap_lines(draw, str(item.get("desc", "")), font_desc, content_w - 20)
        row_h = 12 + len(chip_lines) * 20 + 6 + len(desc_lines) * 20 + 12
        h += row_h + 8
    return h + PAD


def render_guide_commands_image(
    title: str,
    items: list[dict[str, Any]],
    *,
    warning: str = "",
) -> bytes:
    font_title = _load_font(22, bold=True)
    font_chip = _load_font(14, bold=True)
    font_desc = _load_font(14)
    font_warn = _load_font(13)
    height = _measure_commands(title, items, warning)
    img = Image.new("RGB", (CARD_W, height), BG)
    draw = ImageDraw.Draw(img)
    _rounded(draw, (8, 8, CARD_W - 8, height - 8), fill=SURFACE, outline=BORDER, radius=18, width=2)

    x_right = CARD_W - PAD - INNER
    y = PAD + 14
    # accent bar
    draw.rounded_rectangle((x_right - 3, y, x_right + 1, y + 26), radius=3, fill=PINK)
    _draw_rtl(draw, x_right - 12, y, title, font_title, TEXT)
    y += 40

    content_w = CARD_W - PAD * 2 - INNER * 2
    if warning:
        for line in _wrap_lines(draw, f"⚠ {warning}", font_warn, content_w):
            _draw_rtl(draw, x_right, y, line, font_warn, (255, 230, 0))
            y += 20
        y += 6

    for item in items:
        chip_lines = _wrap_lines(draw, str(item.get("cmd", "")), font_chip, content_w - 20)
        desc_lines = _wrap_lines(draw, str(item.get("desc", "")), font_desc, content_w - 20)
        row_h = 12 + len(chip_lines) * 20 + 6 + len(desc_lines) * 20 + 12
        _rounded(
            draw,
            (PAD + 4, y, CARD_W - PAD - 4, y + row_h),
            fill=ROW_BG,
            outline=BORDER,
            radius=12,
        )
        cy = y + 12
        # chip box
        chip_text = " ".join(chip_lines) if len(chip_lines) == 1 else chip_lines[0]
        chip_w = min(content_w - 8, _text_width(draw, _pil_hebrew(chip_text), font_chip) + 18)
        chip_h = 8 + len(chip_lines) * 18
        chip_left = x_right - chip_w
        _rounded(
            draw,
            (chip_left, cy, x_right, cy + chip_h),
            fill=CHIP_BG,
            outline=CHIP_BORDER,
            radius=8,
        )
        ty = cy + 5
        for line in chip_lines:
            _draw_rtl(draw, x_right - 8, ty, line, font_chip, PINK)
            ty += 18
        cy = cy + chip_h + 6
        for line in desc_lines:
            _draw_rtl(draw, x_right, cy, line, font_desc, TEXT)
            cy += 20
        y += row_h + 8

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _measure_flow(title: str, flow: list[dict[str, Any]], subtitle: str) -> int:
    tmp = Image.new("RGB", (CARD_W, 80), BG)
    draw = ImageDraw.Draw(tmp)
    font_title = _load_font(22, bold=True)
    font_sub = _load_font(12)
    font_label = _load_font(15, bold=True)
    font_detail = _load_font(13)
    font_time = _load_font(11, bold=True)
    marker_w = 96
    text_w = CARD_W - PAD * 2 - INNER * 2 - marker_w - 12
    h = PAD + 50
    if subtitle:
        h += len(_wrap_lines(draw, subtitle, font_sub, CARD_W - PAD * 2 - 40)) * 18 + 8
    for item in flow:
        time_lines = str(item.get("time", "")).replace(" | ", "\n").split("\n")
        label_lines = _wrap_lines(draw, str(item.get("label", "")), font_label, text_w)
        detail_lines = _wrap_lines(draw, str(item.get("detail", "")), font_detail, text_w)
        block = max(len(time_lines) * 16 + 16, len(label_lines) * 20 + len(detail_lines) * 18 + 8)
        h += block + 14
    return h + PAD


def render_guide_flow_image(
    title: str,
    flow: list[dict[str, Any]],
    *,
    subtitle: str = "",
) -> bytes:
    font_title = _load_font(22, bold=True)
    font_sub = _load_font(12)
    font_label = _load_font(15, bold=True)
    font_detail = _load_font(13)
    font_time = _load_font(11, bold=True)
    height = _measure_flow(title, flow, subtitle)
    img = Image.new("RGB", (CARD_W, height), BG)
    draw = ImageDraw.Draw(img)
    _rounded(draw, (8, 8, CARD_W - 8, height - 8), fill=SURFACE, outline=BORDER, radius=18, width=2)

    x_right = CARD_W - PAD - INNER
    y = PAD + 14
    draw.rounded_rectangle((x_right - 3, y, x_right + 1, y + 26), radius=3, fill=CYAN)
    _draw_rtl(draw, x_right - 12, y, title, font_title, TEXT)
    y += 36
    if subtitle:
        for line in _wrap_lines(draw, subtitle, font_sub, CARD_W - PAD * 2 - 40):
            _draw_rtl(draw, x_right, y, line, font_sub, MUTED)
            y += 18
        y += 6

    marker_w = 96
    text_w = CARD_W - PAD * 2 - INNER * 2 - marker_w - 12
    for idx, item in enumerate(flow):
        time_lines = [ln for ln in str(item.get("time", "")).replace(" | ", "\n").split("\n") if ln]
        label_lines = _wrap_lines(draw, str(item.get("label", "")), font_label, text_w)
        detail_lines = _wrap_lines(draw, str(item.get("detail", "")), font_detail, text_w)
        block_h = max(len(time_lines) * 16 + 16, len(label_lines) * 20 + len(detail_lines) * 18 + 10)

        marker_left = x_right - marker_w
        _rounded(
            draw,
            (marker_left, y, x_right, y + max(44, len(time_lines) * 16 + 14)),
            fill=MARKER_BG,
            outline=MARKER_BORDER,
            radius=10,
        )
        ty = y + 8
        for ln in time_lines:
            _draw_rtl(draw, x_right - 6, ty, ln, font_time, CYAN)
            ty += 16

        tx_right = marker_left - 12
        ty = y + 2
        for ln in label_lines:
            _draw_rtl(draw, tx_right, ty, ln, font_label, TEXT)
            ty += 20
        for ln in detail_lines:
            _draw_rtl(draw, tx_right, ty, ln, font_detail, MUTED)
            ty += 18

        if idx < len(flow) - 1:
            mid_x = marker_left + marker_w // 2
            draw.line((mid_x, y + block_h - 4, mid_x, y + block_h + 10), fill=MARKER_BORDER, width=2)
        y += block_h + 14

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_guide_start_image(
    title: str,
    items: list[dict[str, Any]],
    *,
    subtitle: str = "",
) -> bytes:
    font_title = _load_font(22, bold=True)
    font_sub = _load_font(12)
    font_item = _load_font(15, bold=True)
    font_detail = _load_font(13)
    font_chip = _load_font(13, bold=True)
    tmp = Image.new("RGB", (CARD_W, 80), BG)
    draw = ImageDraw.Draw(tmp)
    content_w = CARD_W - PAD * 2 - INNER * 2 - 36
    h = PAD + 50
    if subtitle:
        h += len(_wrap_lines(draw, subtitle, font_sub, content_w)) * 18 + 8
    for item in items:
        h += 14
        h += 22
        h += len(_wrap_lines(draw, str(item.get("detail", "")), font_detail, content_w)) * 18
        if item.get("cmd"):
            h += 28
        h += 14 + 8
    h += PAD

    img = Image.new("RGB", (CARD_W, h), BG)
    draw = ImageDraw.Draw(img)
    _rounded(draw, (8, 8, CARD_W - 8, h - 8), fill=SURFACE, outline=BORDER, radius=18, width=2)
    x_right = CARD_W - PAD - INNER
    y = PAD + 14
    draw.rounded_rectangle((x_right - 3, y, x_right + 1, y + 26), radius=3, fill=PINK)
    _draw_rtl(draw, x_right - 12, y, title, font_title, TEXT)
    y += 36
    if subtitle:
        for line in _wrap_lines(draw, subtitle, font_sub, content_w):
            _draw_rtl(draw, x_right, y, line, font_sub, MUTED)
            y += 18
        y += 6

    for item in items:
        detail_lines = _wrap_lines(draw, str(item.get("detail", "")), font_detail, content_w)
        row_h = 14 + 22 + len(detail_lines) * 18 + (28 if item.get("cmd") else 0) + 10
        _rounded(draw, (PAD + 4, y, CARD_W - PAD - 4, y + row_h), fill=ROW_BG, outline=BORDER, radius=12)
        cy = y + 12
        icon = str(item.get("icon", "📌"))
        draw.text((x_right - 28, cy), icon, font=_load_font(18), fill=TEXT)
        _draw_rtl(draw, x_right - 36, cy + 2, str(item.get("title", "")), font_item, TEXT)
        cy += 24
        for ln in detail_lines:
            _draw_rtl(draw, x_right - 8, cy, ln, font_detail, MUTED)
            cy += 18
        if item.get("cmd"):
            cmd = str(item["cmd"])
            chip_w = _text_width(draw, _pil_hebrew(cmd), font_chip) + 16
            _rounded(
                draw,
                (x_right - chip_w, cy + 4, x_right, cy + 26),
                fill=CHIP_BG,
                outline=CHIP_BORDER,
                radius=8,
            )
            _draw_rtl(draw, x_right - 8, cy + 8, cmd, font_chip, PINK)
        y += row_h + 8

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_guide_tips_image(title: str, tips: list[str]) -> bytes:
    font_title = _load_font(22, bold=True)
    font_tip = _load_font(13)
    tmp = Image.new("RGB", (CARD_W, 80), BG)
    draw = ImageDraw.Draw(tmp)
    content_w = CARD_W - PAD * 2 - INNER * 2 - 16
    h = PAD + 50
    for tip in tips:
        lines = _wrap_lines(draw, f"💡 {tip}", font_tip, content_w)
        h += 12 + len(lines) * 18 + 12 + 8
    h += PAD

    img = Image.new("RGB", (CARD_W, h), BG)
    draw = ImageDraw.Draw(img)
    _rounded(draw, (8, 8, CARD_W - 8, h - 8), fill=SURFACE, outline=BORDER, radius=18, width=2)
    x_right = CARD_W - PAD - INNER
    y = PAD + 14
    draw.rounded_rectangle((x_right - 3, y, x_right + 1, y + 26), radius=3, fill=CYAN)
    _draw_rtl(draw, x_right - 12, y, title, font_title, TEXT)
    y += 40
    for tip in tips:
        lines = _wrap_lines(draw, f"💡 {tip}", font_tip, content_w)
        row_h = 12 + len(lines) * 18 + 12
        _rounded(draw, (PAD + 4, y, CARD_W - PAD - 4, y + row_h), fill=ROW_BG, outline=BORDER, radius=12)
        cy = y + 12
        for ln in lines:
            _draw_rtl(draw, x_right - 8, cy, ln, font_tip, MUTED)
            cy += 18
        y += row_h + 8

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

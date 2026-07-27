"""Tests for PIL-drawn Telegram guide cards."""

from __future__ import annotations

from trading_pulse.telegram import guide_images
from trading_pulse.telegram.telegram_guide import get_telegram_guide, render_telegram_guide_images


def test_guide_commands_image_is_png():
    png = guide_images.render_guide_commands_image(
        "כשאין מזומן לקנייה חדשה",
        [
            {"cmd": "מכור 1", "desc": "למכור את כל מניה מספר 1"},
            {"cmd": "תקנה 1 $20", "desc": "לקנות $20 ממניה #1"},
            {"cmd": "מכור 4 תקנה BEAM $200", "desc": "החלפת $200 ממניה #4 ל-BEAM"},
        ],
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1500


def test_guide_flow_image_is_png():
    png = guide_images.render_guide_flow_image(
        "זרימת יום מסחר",
        [
            {
                "time": "UTC 20:15 | 23:15 ישראל",
                "label": "תוכנית ליום המסחר הבא",
                "detail": "תמונת PNG «תוכנית למחר» + תיק + גרף",
            },
            {
                "time": "UTC 13:35 | 16:35 ישראל",
                "label": "כניסה בפתיחה",
                "detail": "סימולציית קנייה במחיר פתיחה",
            },
        ],
    )
    assert png.startswith(b"\x89PNG")


def test_render_telegram_guide_images_full():
    g = get_telegram_guide({})
    assert g["flow"]
    images = render_telegram_guide_images({})
    assert len(images) >= 3
    assert all(png.startswith(b"\x89PNG") for png, _cap in images)
    # narrow cards — width encoded in PNG IHDR should be CARD_W
    from io import BytesIO

    from PIL import Image

    w, _h = Image.open(BytesIO(images[0][0])).size
    assert w == guide_images.CARD_W

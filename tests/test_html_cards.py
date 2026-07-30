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


def test_guide_omits_pre_close_plan_reminder():
    guide = get_telegram_guide({"plan_reminder_time": "19:59"})
    guide_text = str(guide)

    assert all(item["label"] != "תזכורת" for item in guide["flow"])
    assert all(item["title"] != "תזכורת לפני סגירה" for item in guide["outgoing"])
    assert "תזכורת לפני סגירה" not in guide_text
    assert "plan_reminder" not in guide_text
    assert "19:59" not in guide_text


def test_guide_includes_portfolio_review_israel_time():
    guide = get_telegram_guide(
        {
            "portfolio_review_time": "15:00",
            "intraday_check_enabled": True,
            "intraday_cash_topup_min_usd": 20,
        }
    )
    flow_labels = [item["label"] for item in guide["flow"]]
    assert "סקירת תיק לפני הפתיחה" in flow_labels
    assert flow_labels.index("סקירת תיק לפני הפתיחה") < flow_labels.index("כניסה בפתיחה")
    assert flow_labels.index("כניסה בפתיחה") < flow_labels.index("דוח יומי")

    review_flow = next(item for item in guide["flow"] if item["label"] == "סקירת תיק לפני הפתיחה")
    assert "15:00" in review_flow["time"]
    assert "ישראל" in review_flow["time"]
    # Must NOT treat 15:00 as UTC (that would show ~18:00 ישראל in summer)
    assert "18:00" not in review_flow["time"]

    out_titles = [item["title"] for item in guide["outgoing"]]
    assert "סריקת שוק מלאה (תיק ריק)" in out_titles
    assert "סקירת תיק לפני הפתיחה" in out_titles
    assert "הצעת קנייה (אחת-אחת)" in out_titles
    assert out_titles.index("כניסה בפתיחה") > out_titles.index("סקירת תיק לפני הפתיחה")
    assert "מעקב מסחר (שעתי)" in out_titles
    assert "סקירה" in guide["schedule_note"]


def test_guide_portfolio_review_has_no_disable_toggle():
    """Unlike the removed cash reminder, portfolio review always runs on trading days."""
    guide = get_telegram_guide({"intraday_check_enabled": False})
    flow_labels = [item["label"] for item in guide["flow"]]
    assert "סקירת תיק לפני הפתיחה" in flow_labels

    out_titles = [item["title"] for item in guide["outgoing"]]
    assert "סריקת שוק מלאה (תיק ריק)" in out_titles
    assert "סקירת תיק לפני הפתיחה" in out_titles
    assert "מעקב מסחר (שעתי)" not in out_titles

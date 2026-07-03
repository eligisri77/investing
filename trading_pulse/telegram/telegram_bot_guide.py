"""Guide: create a Telegram bot and connect it to Trading Pulse."""

from __future__ import annotations

from typing import Any


def get_telegram_bot_guide() -> dict[str, Any]:
    return {
        "title": "איך יוצרים בוט טלגרם?",
        "subtitle": "מדריך שלב-אחר-שלב — יצירת בוט, Chat ID, וחיבור לאפליקציה",
        "where": {
            "title": "איפה מעדכנים את הבוט?",
            "items": [
                {
                    "icon": "⚙️",
                    "label": "דשבורד — הגדרות (מומלץ)",
                    "detail": "פתח האפליקציה → תפריט «הגדרות» או כתובת #/settings → מקטע «בוט טלגרם».",
                    "action_label": "פתח הגדרות",
                    "action_route": "#/settings",
                },
                {
                    "icon": "📁",
                    "label": "קובץ .env (ידני)",
                    "detail": (
                        "פיתוח: בתיקיית הפרויקט. "
                        "לאחר התקנה: %LOCALAPPDATA%\\TradingPulse\\.env "
                        "(TELEGRAM_BOT_TOKEN ו-TELEGRAM_CHAT_ID). "
                        "אפשר להעתיק מ-instance/.env.example."
                    ),
                    "action_label": None,
                    "action_route": None,
                },
            ],
            "note": (
                "הסודות נשמרים ב-.env ולא ב-git. "
                "ב«התראות» ודא ש-notification_mode הוא telegram או both."
            ),
        },
        "sections": [
            {
                "step": 1,
                "icon": "🤖",
                "title": "יצירת בוט ב-BotFather",
                "steps": [
                    "פתח טלגרם וחפש @BotFather (רשמי, עם V כחול).",
                    "שלח /newbot",
                    "בחר שם תצוגה (למשל Trading Pulse שלי)",
                    "בחר username שמסתיים ב-bot (למשל my_trading_pulse_bot)",
                    "BotFather ישלח Token — מחרוזת כמו 123456789:AAH… — שמור אותה.",
                ],
                "tip": "אל תשתף את ה-Token עם אף אחד — מי שיש לו אותו שולט בבוט.",
            },
            {
                "step": 2,
                "icon": "👋",
                "title": "הפעלת הבוט",
                "steps": [
                    "חפש בטלגרם את הבוט שיצרת (לפי ה-username).",
                    "לחץ Start או שלח /start — חובה לפני שהאפליקציה תוכל לשלוח אליך הודעות.",
                ],
                "tip": None,
            },
            {
                "step": 3,
                "icon": "🆔",
                "title": "מציאת Chat ID",
                "steps": [
                    "שלח הודעה כלשהי לבוט שלך (למשל «שלום»).",
                    "דרך קלה: חפש @userinfobot → /start → העתק את המספר (Id).",
                    "דרך מתקדמת: בדפדפן פתח https://api.telegram.org/bot<TOKEN>/getUpdates "
                    "(החלף <TOKEN> ב-Token האמיתי) → חפש \"chat\":{\"id\":123456789}.",
                ],
                "tip": "Chat ID הוא מספר (לפעמים שלילי בקבוצות — לשימוש אישי בדרך כלל חיובי).",
            },
            {
                "step": 4,
                "icon": "🔗",
                "title": "חיבור לאפליקציה",
                "steps": [
                    "פתח דשבורד → הגדרות (#/settings).",
                    "הדבק Bot Token בשדה Token.",
                    "הדבק Chat ID בשדה המתאים.",
                    "לחץ «בדיקת חיבור» — אמורה להגיע הודעה בטלגרם.",
                    "לחץ «שמור בוט» — נשמר ב-.env.",
                ],
                "tip": "אחרי שמירה השינוי נכנס לתוקף תוך ~דקה, או הפעל מחדש את האפליקציה.",
            },
        ],
        "new_install": {
            "title": "התקנה אצל משתמש חדש",
            "steps": [
                "הורד והתקן TradingPulse-Setup.exe (אין צורך ב-git).",
                "בהרצה ראשונה נוצרים config.json ו-.env אוטומטית.",
                "פתח 🤖 חיבור בוט (#/bot-guide) או הגדרות (#/settings).",
                "צור בוט ב-@BotFather (שלבים 1–3 למעלה).",
                "הדבק Token + Chat ID → בדיקת חיבור → שמור בוט.",
            ],
        },
        "faq": [
            {
                "q": "שלחתי «סטטוס» ולא קיבלתי תשובה",
                "a": "בדוק ש-notification_mode הוא telegram או both, שהבוט שמור, וששלחת /start לבוט. המתן עד דקה לבדיקת הודעות.",
            },
            {
                "q": "בדיקת חיבור נכשלת",
                "a": "ודא Token מלא מ-BotFather, Chat ID נכון, ו-/start לבוט. בדוק חיבור אינטרנט.",
            },
            {
                "q": "איך מחליפים בוט?",
                "a": "הגדרות → הזן Token ו-Chat ID חדשים → שמור בוט. הישן מוחלף ב-.env.",
            },
        ],
        "tips": [
            "כל משתמש יכול בוט משלו — אין צורך לשתף Token.",
            "אחרי שינוי בוט אין צורך לשנות קוד — רק .env או הגדרות.",
            "מדריך פקודות (הכל, ח1, תוכנית…): #/guide או שלח מדריך בטלגרם.",
            "נתונים אישיים (config, .env, תוכניות): %LOCALAPPDATA%\\TradingPulse\\",
        ],
    }


def setup_steps_short() -> list[str]:
    """Compact list for the settings page."""
    return [
        "צור בוט: @BotFather → /newbot → שמור Token",
        "שלח /start לבוט שלך",
        "Chat ID: @userinfobot או getUpdates",
        "עדכן בהגדרות למטה → בדיקת חיבור → שמור",
    ]


def format_telegram_bot_guide_messages() -> list[str]:
    """Short bot-setup guide for Telegram."""
    from trading_pulse.telegram.telegram_format import chunk_telegram_html, escape_html

    g = get_telegram_bot_guide()
    parts: list[str] = []

    parts.append(
        "\n".join(
            [
                f"<b>🤖 {escape_html(g['title'])}</b>",
                f"<i>{escape_html(g['subtitle'])}</i>",
            ]
        )
    )

    where_lines = [f"<b>{escape_html(g['where']['title'])}</b>"]
    for item in g["where"]["items"]:
        where_lines.append(f"• <b>{escape_html(item['label'])}</b> — {escape_html(item['detail'])}")
    where_lines.append(f"<i>{escape_html(g['where']['note'])}</i>")
    parts.append("\n".join(where_lines))

    for sec in g["sections"]:
        lines = [f"<b>{sec['step']}. {escape_html(sec['title'])}</b>"]
        for step in sec["steps"]:
            lines.append(f"• {escape_html(step)}")
        if sec.get("tip"):
            lines.append(f"<i>💡 {escape_html(sec['tip'])}</i>")
        parts.append("\n".join(lines))

    parts.append(
        "<b>📖 מדריך מלא בדשבורד:</b> #/bot-guide · <b>עדכון:</b> #/settings"
    )
    return chunk_telegram_html(parts)

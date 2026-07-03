"""Structured Telegram help for the dashboard (mirrors bot behavior)."""

from __future__ import annotations

from typing import Any


def _format_interval_hebrew(minutes: int) -> str:
    minutes = max(15, int(minutes))
    if minutes % 60 == 0:
        hours = minutes // 60
        if hours == 1:
            return "כל שעה"
        return f"כל {hours} שעות"
    return f"כל {minutes} דקות"


def _intraday_settings_help(cfg: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(cfg.get("intraday_check_enabled", True))
    interval = int(cfg.get("intraday_check_interval_minutes", 60))
    cooldown = int(cfg.get("intraday_alert_cooldown_minutes", 120))
    open_t = str(cfg.get("market_open_sim_time", "16:40"))
    close_t = str(cfg.get("market_close_sim_time", "23:10"))
    status = "פעיל" if enabled else "כבוי"
    return {
        "title": "מעקב שעתי במהלך מסחר",
        "status": status,
        "dashboard_path": "#/settings",
        "fields": [
            {
                "key": "intraday_check_enabled",
                "label": "הפעלה",
                "value": "כן" if enabled else "לא",
                "hint": "כבוי = לא יישלחו התראות מעקב במהלך היום",
            },
            {
                "key": "intraday_check_interval_minutes",
                "label": "תדירות בדיקה",
                "value": _format_interval_hebrew(interval) if enabled else "—",
                "hint": "דקות בין בדיקות (60=שעה, 120=שעתיים). נכנס לתוקף תוך ~דקה",
            },
            {
                "key": "market_open_sim_time",
                "label": "תחילת חלון",
                "value": open_t,
                "hint": "שעון מקומי (Windows) — מתי מתחיל המעקב",
            },
            {
                "key": "market_close_sim_time",
                "label": "סוף חלון",
                "value": close_t,
                "hint": "עד מתי רצות בדיקות (לפני דוח הסימולציה)",
            },
            {
                "key": "intraday_alert_cooldown_minutes",
                "label": "השהייה בין אותה התראה",
                "value": f"{cooldown} דקות",
                "hint": "מונע ספאם — אותה התראה על אותה מניה לא תחזור לפני שעבר הזמן",
            },
        ],
        "examples": [
            "לכבות לגמרי: intraday_check_enabled = false",
            "כל שעתיים: intraday_check_interval_minutes = 120",
            "חלון קצר יותר: שנה market_open_sim_time / market_close_sim_time",
        ],
    }


def get_telegram_guide(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or {}
    intraday = _intraday_settings_help(cfg)
    enabled = bool(cfg.get("intraday_check_enabled", True))
    interval = int(cfg.get("intraday_check_interval_minutes", 60))
    open_t = str(cfg.get("market_open_sim_time", "16:40"))
    close_t = str(cfg.get("market_close_sim_time", "23:10"))
    plan_t = str(cfg.get("planning_time", "21:00"))
    reminder_t = str(cfg.get("plan_reminder_time", "22:00"))
    sim_t = str(cfg.get("market_close_sim_time", "23:10"))
    heartbeat_t = str(cfg.get("heartbeat_time", "09:00"))

    flow = [
        {
            "time": plan_t,
            "label": "תוכנית יומית",
            "detail": "סיכום + טבלה + הודעה נפרדת לכל מניה עם גרף",
        },
        {
            "time": "שלב 1",
            "label": "אישור המלצות",
            "detail": "שלח הכל / 1,2 / דחה 4",
        },
        {
            "time": "שלב 2",
            "label": "חלוקת הון",
            "detail": "שלח ח1…ח5 (עם אות ח') — או בדשבורד #/plan",
        },
        {
            "time": f"~{reminder_t}",
            "label": "תזכורת",
            "detail": "אם חסר אישור או חלוקה — הודעה לפני הסימולציה",
        },
        {
            "time": sim_t,
            "label": "דוח יומי",
            "detail": "סימולציה + סיכום P/L",
        },
        {
            "time": heartbeat_t,
            "label": "Heartbeat",
            "detail": "אישור שהסוכן חי",
        },
    ]
    if enabled:
        flow.insert(
            5,
            {
                "time": f"{open_t}–{close_t}",
                "label": "מעקב מסחר",
                "detail": (
                    f"{_format_interval_hebrew(interval)} — בדיקת מניות מושקעות, "
                    "חריגות והצעות רכישה/החלפה (רק כשיש מה לדווח)"
                ),
            },
        )

    outgoing = [
        {
            "icon": "📋",
            "title": "תוכנית יומית",
            "when": f"כל יום מסחר ~{plan_t}, או אחרי תוכנית עכשיו",
                "parts": [
                    "הודעת סיכום — הון, הוראות שלב 1, רשימת מניות",
                    "תמונת טבלה — כל ההמלצות במבט אחד",
                    "לכל מניה — גרף + מחיר תחתון (רף מכירה) + יעד רווח",
                ],
        },
        {
            "icon": "✅",
            "title": "אישור המלצות",
            "when": "אחרי שלב 1 (הכל / 1,2 / דחה)",
            "parts": [
                "אילו מניות אושרו",
                "הודעת חלוקת הון (שלב 2) אם יש מאושרות",
            ],
        },
        {
            "icon": "💵",
            "title": "חלוקת הון",
            "when": "אחרי אישור, או כששולחים חלוקה",
            "parts": [
                "5 אפשרויות: ח1…ח5 עם פירוט סכומים",
                "אישור שמירה אחרי בחירת חלוקה",
            ],
        },
        {
            "icon": "📊",
            "title": "דוח יומי",
            "when": f"~{sim_t} בסוף יום מסחר",
            "parts": [
                "הון לפני/אחרי, רווח/הפסד",
                "עסקאות שנסגרו ופוזיציות שמוחזקות",
                "תמונת טבלת דוח",
            ],
        },
        {
            "icon": "💚",
            "title": "Heartbeat",
            "when": f"{heartbeat_t} (ובהפעלת אפליקציה אם מוגדר)",
            "parts": ["הון נוכחי וסיכום מצב"],
        },
        {
            "icon": "💼",
            "title": "תיק",
            "when": "כששולחים תיק",
            "parts": ["תמונת טבלה עם פוזיציות ורווח לפי מניה"],
        },
        {
            "icon": "📋",
            "title": "סטטוס",
            "when": "כששולחים סטטוס",
            "parts": [
                "מצב אישור וחלוקה לתוכנית הפעילה",
                "מה לשלוח עכשיו לפי השלב",
            ],
        },
        {
            "icon": "⏰",
            "title": "תזכורת לפני סימולציה",
            "when": f"~{reminder_t} אם חסר אישור או חלוקה",
            "parts": [
                "כמה דקות נותרו עד הסימולציה",
                "מה לשלוח: הכל / 1,2 או ח4",
                "אפשר גם לפתוח תוכנית פעילה בדשבורד",
            ],
        },
    ]
    if enabled:
        outgoing.insert(
            5,
            {
                "icon": "🔍",
                "title": "מעקב מסחר (שעתי)",
                "when": (
                    f"{open_t}–{close_t} · {_format_interval_hebrew(interval)} · "
                    f"סטטוס: {intraday['status']}"
                ),
                "parts": [
                    "מצב מניות מושקעות — מחיר, רווח/הפסד, ירידות חדות",
                    "חריגות: מתחת למחיר תחתון, קרוב לרף, ירידה חדה",
                    "מכירה אוטומטית כשהמחיר יורד מתחת לרף",
                    "הצעות: רכישה אם יש מקום בתיק, החלפה אם התיק מלא",
                    "נשלח רק כשיש משהו לדווח — לא ספאם כל שעה",
                    "הגדרות: #/settings (או config.json)",
                ],
            },
        )

    tips = [
        "כל ההודעות בטלגרם בפורמט HTML — עברית אמורה להופיע תקין.",
        "אם לא ענית לחלוקה עד הסימולציה — נבחרת אוטומטית ח4 (לפי תוכנית).",
        "אישור וחלוקה אפשריים גם בדשבורד: תוכנית פעילה (#/plan).",
        "דפי עזרה: מדריך (#/guide) · בחירת מניות (#/selection) · חיבור בוט (#/bot-guide).",
        "בלי תאריך — כל הפקודות על התוכנית האחרונה.",
        "שינוי מרווח בדיקת טלגרם בהגדרות נכנס לתוקף תוך ~דקה.",
        "מעקב מסחר: intraday_check_enabled / intraday_check_interval_minutes — נכנס לתוקף תוך ~דקה.",
        f"מעקב מסחר כרגע: {intraday['status']}"
        + (
            f" · {_format_interval_hebrew(interval)} בין {open_t} ל-{close_t}"
            if enabled
            else " — להפעלה: הגדרות → מעקב שעתי"
        ),
    ]

    return {
        "title": "מדריך טלגרם",
        "subtitle": "מה הבוט שולח אליך ומה לענות בכל שלב",
        "flow": flow,
        "outgoing": outgoing,
        "config_help": [intraday],
        "commands": [
            {
                "id": "step1",
                "title": "שלב 1 — אישור (מספרים בלי ח')",
                "warning": "לא לשלוח ח1 כאן — זה שלב 2",
                "items": [
                    {"cmd": "הכל", "desc": "לאשר את כל ההמלצות"},
                    {"cmd": "1,2,3", "desc": "לאשר רק את המספרים האלה"},
                    {"cmd": "דחה 4", "desc": "לדחות המלצה מס' 4"},
                ],
            },
            {
                "id": "step2",
                "title": "שלב 2 — חלוקה (עם אות ח')",
                "warning": "לא לשלוח 1 או 2 לבד — זה מאשר המלצה, לא חלוקה",
                "items": [
                    {"cmd": "ח1", "desc": "שווה — כל ההון הפנוי"},
                    {"cmd": "ח2", "desc": "לפי דירוג ההמלצות"},
                    {"cmd": "ח3", "desc": "מקסימום למניה הראשונה"},
                    {"cmd": "ח4", "desc": "לפי תוכנית + מזומן למחר"},
                    {"cmd": "ח5", "desc": "שמרני — חצי מהפנוי"},
                    {"cmd": "חלוקה", "desc": "להציג שוב את האפשרויות"},
                ],
            },
            {
                "id": "watchlist",
                "title": "רשימת מניות לסריקה",
                "items": [
                    {"cmd": "מניות", "desc": "הצג את הרשימה הנוכחית"},
                    {"cmd": "הוסף SMCI", "desc": "הוסף מניה לרשימה (add SMCI)"},
                    {"cmd": "הסר IONQ", "desc": "הסר מניה מהרשימה"},
                    {"cmd": "חפש מניות", "desc": "סריקה אוטומטית והוספת עד 3 מניות חזקות"},
                ],
            },
            {
                "id": "general",
                "title": "כללי — בכל שלב",
                "items": [
                    {"cmd": "סטטוס", "desc": "מצב התוכנית והחלוקה"},
                    {"cmd": "תיק", "desc": "סיכום השקעות (תמונה)"},
                    {"cmd": "תוכנית", "desc": "לשלוח שוב את התוכנית האחרונה"},
                    {"cmd": "תוכנית עכשיו", "desc": "ליצור תוכנית חדשה מיד"},
                    {"cmd": "עזרה", "desc": "מדריך קצר בטלגרם"},
                    {"cmd": "מדריך", "desc": "מדריך מלא (זרימה, הודעות, פקודות)"},
                    {"cmd": "איך בוחרים מניות", "desc": "איך האפליקציה בוחרת מניות לתוכנית"},
                    {"cmd": "חיבור בוט", "desc": "איך ליצור בוט ולחבר לאפליקציה"},
                ],
            },
        ],
        "examples": [
            {
                "title": "זרימה נכונה",
                "steps": ["1,2,3", "ח4"],
                "note": "קודם אישור במספרים, אחר כך חלוקה עם ח'",
            },
            {
                "title": "טעות נפוצה",
                "steps": ["1"],
                "note": "אחרי אישור — 1 לבד מאשר רק המלצה #1, לא בוחר חלוקה ח1",
            },
        ],
        "tips": tips,
    }


def format_telegram_guide_messages(cfg: dict[str, Any] | None = None) -> list[str]:
    """Full Telegram guide as one or more HTML messages."""
    from trading_pulse.telegram.telegram_format import chunk_telegram_html, escape_html

    if cfg is None:
        try:
            from trading_pulse.agent.dryrun_agent import load_config

            cfg = load_config().__dict__
        except ImportError:
            cfg = {}

    g = get_telegram_guide(cfg)
    parts: list[str] = []

    header = "\n".join(
        [
            f"<b>📖 {escape_html(g['title'])}</b>",
            f"<i>{escape_html(g['subtitle'])}</i>",
        ]
    )
    parts.append(header)

    flow_lines = ["<b>⏱ זרימה יומית</b>"]
    for item in g["flow"]:
        flow_lines.append(
            f"• <b>{escape_html(item['time'])}</b> — {escape_html(item['label'])}: "
            f"{escape_html(item['detail'])}"
        )
    parts.append("\n".join(flow_lines))

    out_lines = ["<b>📤 מה הבוט שולח</b>"]
    for item in g["outgoing"]:
        out_lines.append(f"{item['icon']} <b>{escape_html(item['title'])}</b> — {escape_html(item['when'])}")
        for p in item["parts"]:
            out_lines.append(f"  · {escape_html(p)}")
    parts.append("\n".join(out_lines))

    cmd_lines = ["<b>⌨️ פקודות</b>"]
    for section in g["commands"]:
        cmd_lines.append(f"\n<b>{escape_html(section['title'])}</b>")
        if section.get("warning"):
            cmd_lines.append(f"⚠️ <i>{escape_html(section['warning'])}</i>")
        for row in section["items"]:
            cmd_lines.append(f"<code>{escape_html(row['cmd'])}</code> — {escape_html(row['desc'])}")
    parts.append("\n".join(cmd_lines))

    ex_lines = ["<b>💡 דוגמאות וטיפים</b>"]
    for ex in g["examples"]:
        steps = " → ".join(f"<code>{escape_html(s)}</code>" for s in ex["steps"])
        ex_lines.append(f"<b>{escape_html(ex['title'])}:</b> {steps}")
        ex_lines.append(f"<i>{escape_html(ex['note'])}</i>")
    for tip in g["tips"]:
        ex_lines.append(f"• {escape_html(tip)}")
    parts.append("\n".join(ex_lines))

    cfg_help = g.get("config_help") or []
    if cfg_help:
        cfg_lines = ["<b>⚙️ הגדרות (config.json / #/settings)</b>"]
        for block in cfg_help:
            cfg_lines.append(f"\n<b>{escape_html(block['title'])}</b> — {escape_html(block.get('status', ''))}")
            for row in block.get("fields", []):
                cfg_lines.append(
                    f"• <code>{escape_html(row['key'])}</code>: {escape_html(row['label'])} "
                    f"= <b>{escape_html(str(row['value']))}</b>"
                )
                if row.get("hint"):
                    cfg_lines.append(f"  <i>{escape_html(row['hint'])}</i>")
            for ex in block.get("examples", []):
                cfg_lines.append(f"  💡 {escape_html(ex)}")
        parts.append("\n".join(cfg_lines))

    return chunk_telegram_html(parts)

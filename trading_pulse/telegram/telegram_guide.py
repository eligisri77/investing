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


def _schedule_note(cfg: dict[str, Any]) -> str:
    from trading_pulse.core.schedule_tz import format_dual_time

    plan_t = str(cfg.get("planning_time", "20:15"))
    entry_t = str(cfg.get("entry_sim_time", "13:35"))
    close_t = str(cfg.get("market_close_sim_time", "20:20"))
    return (
        f"תוכנית {format_dual_time(plan_t)} · "
        f"כניסה {format_dual_time(entry_t)} · "
        f"דוח {format_dual_time(close_t)}"
    )


def _intraday_settings_help(cfg: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(cfg.get("intraday_check_enabled", True))
    interval = int(cfg.get("intraday_check_interval_minutes", 60))
    cooldown = int(cfg.get("intraday_alert_cooldown_minutes", 120))
    open_t = str(cfg.get("market_open_sim_time", "13:30"))
    close_t = str(cfg.get("market_close_sim_time", "20:20"))
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
                "hint": "UTC — פתיחת וול סטריט (~16:30 ישראל בקיץ)",
            },
            {
                "key": "market_close_sim_time",
                "label": "סוף חלון",
                "value": close_t,
                "hint": "UTC — לפני דוח סוף יום (~23:20 ישראל בקיץ)",
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
    open_t = str(cfg.get("market_open_sim_time", "13:30"))
    close_t = str(cfg.get("market_close_sim_time", "20:20"))
    plan_t = str(cfg.get("planning_time", "20:15"))
    entry_t = str(cfg.get("entry_sim_time", "13:35"))
    reminder_t = str(cfg.get("plan_reminder_time", "20:00"))
    sim_t = str(cfg.get("market_close_sim_time", "20:20"))
    heartbeat_t = str(cfg.get("heartbeat_time", "13:00"))
    from trading_pulse.core.schedule_tz import format_dual_time

    def _dual(t: str) -> str:
        clean = str(t).lstrip("~")
        dual = format_dual_time(clean)
        return dual if dual else str(t)

    flow = [
        {
            "time": _dual(plan_t),
            "label": "תוכנית ליום המסחר הבא",
            "detail": "סיכום + טבלה + גרף לכל מניה · שלח הכל לאישור (חלוקה אוטומטית)",
        },
        {
            "time": _dual(entry_t),
            "label": "כניסה בפתיחה",
            "detail": "סימולציית קנייה במחיר פתיחה + הודעה בטלגרם",
        },
        {
            "time": _dual(reminder_t),
            "label": "תזכורת",
            "detail": "אם לא אושרה תוכנית — תזכורת לפני סגירת השוק",
        },
        {
            "time": _dual(sim_t),
            "label": "דוח יומי",
            "detail": "סגירת יום · רווח ממומש + רווח עתידי על מניות פתוחות",
        },
        {
            "time": _dual(heartbeat_t),
            "label": "Heartbeat",
            "detail": "אישור שהסוכן חי",
        },
    ]
    if enabled:
        flow.insert(
            5,
            {
                "time": f"{_dual(open_t)} – {_dual(close_t)}",
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
                "מזומן / מושקע / סה\"כ — והמלצות למחר",
                "יום ראשון: חלוקה על כמה מניות · אחר כך: מניה חדשה או מכירה לפני קנייה",
                "תמונת טבלה + גרף לכל מניה",
            ],
        },
        {
            "icon": "✅",
            "title": "אישור (הכל)",
            "when": "אחרי שליחת הכל / 1,2",
            "parts": [
                "חלוקה אוטומטית כשיש מזומן",
                "אם אין מזומן — הודעה עם מכור / החלף",
            ],
        },
        {
            "icon": "🌅",
            "title": "כניסה בפתיחה",
            "when": f"~{entry_t} (פתיחת וול סטריט)",
            "parts": [
                "קנייה במחיר פתיחה (dry-run)",
                "סיכום: אילו מניות נכנסו ובאיזה מחיר",
            ],
        },
        {
            "icon": "📊",
            "title": "דוח יומי",
            "when": f"~{sim_t} בסוף יום מסחר",
            "parts": [
                "הון לפני/אחרי, רווח ממומש",
                "רווח עתידי על מניות שעדיין מוחזקות",
                "עסקאות שנסגרו ופוזיציות פתוחות",
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
            "title": "תזכורת לפני סגירה",
            "when": f"~{reminder_t} אם לא אושרה תוכנית",
            "parts": [
                "כמה דקות נותרו עד סגירת השוק",
                "מה לשלוח: הכל או מכור + הכל",
                "אפשר גם בדשבורד: תוכנית פעילה (#/plan)",
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
        "יום ראשון: שלח הכל — ההון מתחלק אוטומטית על כמה מניות.",
        "מניה חדשה בלי מזומן: מכור SYMBOL או החלף X Y, ואז הכל.",
        "אישור אפשרי גם בדשבורד: תוכנית פעילה (#/plan).",
        "דפי עזרה: מדריך (#/guide) · בחירת מניות (#/selection) · חיבור בוט (#/bot-guide).",
        "שעות נשמרות ב-UTC — בכל מקום מוצג גם שעון ישראל (Asia/Jerusalem).",
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

    deploy_n = int(cfg.get("initial_deploy_stocks", 3))

    return {
        "title": "מדריך טלגרם",
        "subtitle": "תוכנית בערב · כניסה בבוקר · דוח בערב — פשוט וברור",
        "schedule_note": _schedule_note(cfg),
        "getting_started": [
            {
                "icon": "🚀",
                "title": "פקודה אחת — התחל",
                "detail": "יוצר תוכנית, מאשר, ומחלק את ההון. בלי שלבים נפרדים.",
                "cmd": "התחל",
            },
            {
                "icon": "📈",
                "title": "ימים רגילים — מניה חדשה",
                "detail": "יש מזומן? שלח הכל. אין מזומן? קודם מכור חלק ממה שמחזיקים.",
                "cmd": "מכור SYMBOL → הכל",
            },
            {
                "icon": "🔄",
                "title": "החלפה מהירה",
                "detail": "מכירה וקנייה במכה אחת — בלי שלבים נפרדים.",
                "cmd": "החלף LABU HOOD",
            },
        ],
        "flow": flow,
        "outgoing": outgoing,
        "config_help": [intraday],
        "commands": [
            {
                "id": "approve",
                "title": "אישור תוכנית",
                "items": [
                    {"cmd": "הכל", "desc": "לאשר הכל — חלוקה אוטומטית (יום ראשון: כמה מניות)"},
                    {"cmd": "1,2,3", "desc": "לאשר רק את המספרים האלה"},
                    {"cmd": "דחה 4", "desc": "לדחות המלצה מס' 4"},
                ],
            },
            {
                "id": "funding",
                "title": "כשאין מזומן לקנייה חדשה",
                "items": [
                    {"cmd": "תיק", "desc": "תמונת תיק עם מספרים לכל מניה (#1, #2…)"},
                    {"cmd": "מכור 1", "desc": "למכור את כל מניה מספר 1"},
                    {"cmd": "מכור 2 $200", "desc": "למכור $200 ממניה מספר 2"},
                    {"cmd": "מכור 50% 3", "desc": "למכור חצי ממניה מספר 3"},
                    {"cmd": "תקנה 1 $20", "desc": "לקנות $20 ממניה #1 (ממזומן פנוי)"},
                    {"cmd": "קנה BEAM $50", "desc": "לקנות $50 מ-BEAM ממזומן"},
                    {"cmd": "מכור 4 תקנה BEAM $200", "desc": "החלפת $200 ממניה #4 ל-BEAM"},
                    {"cmd": "מכור LABU", "desc": "למכור את כל הפוזיציה ולפנות מזומן"},
                    {"cmd": "מכור 50% LABU", "desc": "למכור חלק מהפוזיציה"},
                    {"cmd": "החלף LABU HOOD", "desc": "מכירה מלאה + קניית מניה אחרת"},
                ],
            },
            {
                "id": "advanced",
                "title": "חלוקה ידנית (מתקדם)",
                "warning": "רק אם נשלחה הודעת חלוקה ידנית",
                "items": [
                    {"cmd": "ח1", "desc": "שווה — כל ההון הפנוי"},
                    {"cmd": "ח4", "desc": "לפי תוכנית + מזומן למחר"},
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
                    {"cmd": "סטטוס", "desc": "מצב התוכנית — מה לשלוח עכשיו"},
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
                "title": "יום ראשון — $1,000",
                "steps": ["הכל"],
                "note": "ההון מתחלק אוטומטית על ~3 מניות. למחר בפתיחה — כניסה לשוק.",
            },
            {
                "title": "מניה חדשה בלי מזומן",
                "steps": ["מכור LABU", "הכל"],
                "note": "קודם מוכרים חלק ממה שמחזיקים, אחר כך מאשרים את הקנייה.",
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

    gs = g.get("getting_started") or []
    if gs:
        gs_lines = ["<b>🚀 התחלה מהירה</b>"]
        if g.get("schedule_note"):
            gs_lines.append(f"<i>{escape_html(g['schedule_note'])}</i>")
        for item in gs:
            gs_lines.append(
                f"{item['icon']} <b>{escape_html(item['title'])}</b> — {escape_html(item['detail'])}"
            )
            if item.get("cmd"):
                gs_lines.append(f"  → <code>{escape_html(item['cmd'])}</code>")
        parts.append("\n".join(gs_lines))

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


def render_telegram_guide_images(
    cfg: dict[str, Any] | None = None,
) -> list[tuple[bytes, str]]:
    """Guide as drawn PNG cards (PIL) — same style as portfolio/plan images."""
    from trading_pulse.telegram import guide_images

    if cfg is None:
        try:
            from trading_pulse.agent.dryrun_agent import load_config

            cfg = load_config().__dict__
        except ImportError:
            cfg = {}

    g = get_telegram_guide(cfg)
    out: list[tuple[bytes, str]] = []

    gs = g.get("getting_started") or []
    if gs:
        out.append(
            (
                guide_images.render_guide_start_image(
                    "התחלה מהירה",
                    gs,
                    subtitle=str(g.get("subtitle") or ""),
                ),
                "🚀 התחלה מהירה",
            )
        )

    flow = g.get("flow") or []
    if flow:
        out.append(
            (
                guide_images.render_guide_flow_image(
                    "זרימת יום מסחר",
                    flow,
                    subtitle=str(g.get("schedule_note") or ""),
                ),
                "⏱ זרימת יום מסחר",
            )
        )

    for section in g.get("commands") or []:
        items = section.get("items") or []
        if not items:
            continue
        out.append(
            (
                guide_images.render_guide_commands_image(
                    str(section.get("title") or "פקודות"),
                    items,
                    warning=str(section.get("warning") or ""),
                ),
                f"⌨️ {section.get('title', 'פקודות')}",
            )
        )

    tips = (g.get("tips") or [])[:6]
    if tips:
        out.append((guide_images.render_guide_tips_image("טיפים", tips), "💡 טיפים"))

    return out


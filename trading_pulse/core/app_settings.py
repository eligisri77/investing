"""Editable application settings (config.json) for the dashboard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from trading_pulse.core.app_paths import CONFIG_FILE, USER_DATA_DIR

TIME_RE = re.compile(r"^\d{2}:\d{2}$")

SETTINGS_SECTIONS: list[dict[str, Any]] = [
    {
        "id": "notifications",
        "title": "התראות",
        "fields": [
            {
                "key": "notification_mode",
                "label": "ערוץ התראות",
                "type": "select",
                "options": [
                    {"value": "app", "label": "אפליקציה בלבד"},
                    {"value": "telegram", "label": "טלגרם בלבד"},
                    {"value": "both", "label": "אפליקציה + טלגרם"},
                ],
            },
            {
                "key": "telegram_poll_interval_sec",
                "label": "מרווח בדיקת פקודות טלגרם (שניות)",
                "type": "number",
                "min": 15,
                "max": 3600,
                "step": 15,
                "restart_required": True,
                "hint": "כמה זמן לחכות בין בדיקות הודעות נכנסות בטלגרם",
            },
            {
                "key": "send_heartbeat_on_startup",
                "label": "שלח heartbeat בהפעלה",
                "type": "boolean",
            },
        ],
    },
    {
        "id": "schedule",
        "title": "לוח זמנים",
        "fields": [
            {
                "key": "planning_time",
                "label": "שעת תוכנית יומית",
                "type": "time",
                "hint": "שעון מקומי (Windows)",
            },
            {
                "key": "market_close_sim_time",
                "label": "שעת סימולציה ודוח",
                "type": "time",
            },
            {
                "key": "market_open_sim_time",
                "label": "תחילת חלון מסחר (מעקב שעתי)",
                "type": "time",
                "hint": "שעון מקומי — מתחיל בדיקות שעתיות על מניות מושקעות",
            },
            {
                "key": "intraday_check_enabled",
                "label": "מעקב שעתי במהלך מסחר",
                "type": "boolean",
                "default": True,
                "hint": "כבוי = בלי התראות מעקב ביום. נכנס לתוקף תוך ~דקה",
            },
            {
                "key": "intraday_check_interval_minutes",
                "label": "מרווח מעקב (דקות)",
                "type": "number",
                "min": 15,
                "max": 240,
                "step": 15,
                "default": 60,
                "hint": "60 = כל שעה · 120 = כל שעתיים · נכנס לתוקף תוך ~דקה",
            },
            {
                "key": "intraday_alert_cooldown_minutes",
                "label": "השהייה בין אותה התראה (דקות)",
                "type": "number",
                "min": 30,
                "max": 480,
                "step": 30,
                "default": 120,
                "hint": "מונע שליחה חוזרת של אותה התראה על אותה מניה",
            },
            {
                "key": "heartbeat_time",
                "label": "שעת heartbeat יומי",
                "type": "time",
            },
            {
                "key": "plan_reminder_time",
                "label": "תזכורת לפני סימולציה",
                "type": "time",
                "restart_required": True,
                "hint": "הודעה אם חסר אישור או חלוקה (ברירת מחדל 22:00)",
            },
        ],
    },
    {
        "id": "trading",
        "title": "מסחר וסיכון",
        "fields": [
            {
                "key": "risk_profile",
                "label": "פרופיל סיכון",
                "type": "select",
                "options": [
                    {"value": "conservative", "label": "שמרני"},
                    {"value": "balanced", "label": "מאוזן"},
                    {"value": "aggressive", "label": "אגרסיבי"},
                    {"value": "speculative", "label": "ספקולטיבי"},
                ],
                "hint": "משפיע על גודל פוזיציה, מספר עסקאות וסטופים",
            },
            {
                "key": "monthly_target_usd",
                "label": "יעד חודשי ($)",
                "type": "number",
                "min": 0,
                "max": 1_000_000,
                "step": 100,
            },
            {
                "key": "hold_mode",
                "label": "מצב החזקה",
                "type": "select",
                "options": [
                    {"value": "intraday", "label": "יומי — סגירה באותו יום"},
                    {"value": "swing", "label": "סווינג — החזקה מספר ימים"},
                ],
            },
            {
                "key": "max_hold_days",
                "label": "מקסימום ימי החזקה",
                "type": "number",
                "min": 1,
                "max": 30,
                "step": 1,
            },
            {
                "key": "max_open_positions",
                "label": "מקסימום פוזיציות פתוחות",
                "type": "number",
                "min": 1,
                "max": 20,
                "step": 1,
            },
            {
                "key": "commission_per_side_usd",
                "label": "עמלה לצד ($)",
                "type": "number",
                "min": 0,
                "max": 50,
                "step": 0.5,
            },
        ],
    },
]

_EDITABLE_KEYS = {
    field["key"]
    for section in SETTINGS_SECTIONS
    for field in section["fields"]
}


def _read_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_config(cfg: dict[str, Any]) -> None:
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _field_by_key(key: str) -> dict[str, Any] | None:
    for section in SETTINGS_SECTIONS:
        for field in section["fields"]:
            if field["key"] == key:
                return field
    return None


def _field_default(field: dict[str, Any]) -> Any:
    return field.get("default")


def _coalesce_field_value(field: dict[str, Any], raw: Any) -> Any:
    if raw is None:
        return _field_default(field)
    if isinstance(raw, str) and not raw.strip():
        return _field_default(field)
    return raw


def _validate_field(field: dict[str, Any], raw: Any) -> Any:
    ftype = field["type"]
    key = field["key"]
    raw = _coalesce_field_value(field, raw)

    if ftype == "boolean":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in {"1", "true", "yes", "on"}
        return bool(raw)

    if ftype == "number":
        if raw is None:
            raise HTTPException(status_code=400, detail=f"ערך לא תקין: {key}")
        try:
            value = float(raw)
        except (TypeError, ValueError) as ex:
            raise HTTPException(status_code=400, detail=f"ערך לא תקין: {key}") from ex
        if value != int(value) and field.get("step", 1) == 1:
            value = int(value)
        else:
            value = float(value) if field.get("step", 1) != 1 else int(value)
        min_v = field.get("min")
        max_v = field.get("max")
        if min_v is not None and value < min_v:
            raise HTTPException(status_code=400, detail=f"{field['label']}: מינימום {min_v}")
        if max_v is not None and value > max_v:
            raise HTTPException(status_code=400, detail=f"{field['label']}: מקסימום {max_v}")
        return value

    if ftype == "time":
        text = str(raw).strip()
        if not TIME_RE.fullmatch(text):
            raise HTTPException(status_code=400, detail=f"{field['label']}: פורמט שעה HH:MM")
        hh, mm = text.split(":")
        if int(hh) > 23 or int(mm) > 59:
            raise HTTPException(status_code=400, detail=f"{field['label']}: שעה לא תקינה")
        return text

    if ftype == "select":
        text = str(raw).strip()
        allowed = {opt["value"] for opt in field.get("options", [])}
        if text not in allowed:
            raise HTTPException(status_code=400, detail=f"{field['label']}: ערך לא חוקי")
        return text

    raise HTTPException(status_code=500, detail=f"Unknown field type: {ftype}")


def get_settings_payload() -> dict[str, Any]:
    cfg = _read_config()
    values: dict[str, Any] = {}
    for section in SETTINGS_SECTIONS:
        for field in section["fields"]:
            key = field["key"]
            if key in cfg:
                values[key] = cfg[key]
            elif "default" in field:
                values[key] = field["default"]
            else:
                values[key] = cfg.get(key)
    restart_keys = [
        field["key"]
        for section in SETTINGS_SECTIONS
        for field in section["fields"]
        if field.get("restart_required")
    ]
    try:
        from trading_pulse.core.env_config import secrets_source

        secrets = secrets_source()
    except Exception:
        secrets = "config"
    return {
        "sections": SETTINGS_SECTIONS,
        "values": values,
        "restart_required_keys": restart_keys,
        "secrets_source": secrets,
        "config_path": str(CONFIG_FILE),
        "user_data_dir": str(USER_DATA_DIR),
    }


def update_settings(updates: dict[str, Any]) -> dict[str, Any]:
    unknown = set(updates) - _EDITABLE_KEYS
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"שדות לא ניתנים לעריכה: {', '.join(sorted(unknown))}",
        )
    if not updates:
        raise HTTPException(status_code=400, detail="אין שדות לעדכון")

    cfg = _read_config()
    changed: list[str] = []
    for key, raw in updates.items():
        field = _field_by_key(key)
        if field is None:
            continue
        cfg[key] = _validate_field(field, raw)
        changed.append(key)

    _write_config(cfg)
    restart_needed = any(
        field.get("restart_required")
        for key in changed
        for section in SETTINGS_SECTIONS
        for field in section["fields"]
        if field["key"] == key
    )
    out_values: dict[str, Any] = {}
    for section in SETTINGS_SECTIONS:
        for field in section["fields"]:
            key = field["key"]
            if key in cfg:
                out_values[key] = cfg[key]
            elif "default" in field:
                out_values[key] = field["default"]
            else:
                out_values[key] = cfg.get(key)
    return {
        "ok": True,
        "changed": changed,
        "restart_recommended": restart_needed,
        "values": {key: out_values.get(key) for key in _EDITABLE_KEYS},
    }

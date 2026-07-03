"""Telegram bot connection settings for the dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from trading_pulse.core.env_config import (
    clear_telegram_from_config_json,
    mask_secret,
    read_telegram_credentials,
    secrets_source,
    validate_bot_token,
    validate_chat_id,
    write_telegram_env,
)
from trading_pulse.telegram.telegram_bot_guide import setup_steps_short

SETUP_STEPS = setup_steps_short()


def get_telegram_settings_payload() -> dict[str, Any]:
    token, chat_id = read_telegram_credentials()
    configured = bool(token and chat_id)
    return {
        "configured": configured,
        "source": secrets_source(),
        "bot_token_masked": mask_secret(token) if token else "",
        "chat_id_masked": mask_secret(chat_id, visible=3) if chat_id else "",
        "chat_id": chat_id if configured else "",
        "setup_steps": SETUP_STEPS,
        "env_path": str(__import__("env_config").ENV_FILE),
    }


def update_telegram_settings(
    *,
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    current_token, current_chat = read_telegram_credentials()
    new_token = (bot_token or "").strip() or current_token
    new_chat = (chat_id or "").strip() or current_chat

    if not new_token and not new_chat:
        raise HTTPException(status_code=400, detail="נדרשים Token ו-Chat ID")
    if not new_token:
        raise HTTPException(status_code=400, detail="חסר Bot Token")
    if not new_chat:
        raise HTTPException(status_code=400, detail="חסר Chat ID")

    try:
        new_token = validate_bot_token(new_token)
        new_chat = validate_chat_id(new_chat)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    write_telegram_env(new_token, new_chat)
    clear_telegram_from_config_json()
    return get_telegram_settings_payload()


def test_telegram_connection(
    *,
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    current_token, current_chat = read_telegram_credentials()
    token = (bot_token or "").strip() or current_token
    chat = (chat_id or "").strip() or current_chat

    if not token or not chat:
        raise HTTPException(status_code=400, detail="הזן Token ו-Chat ID לפני בדיקה")

    try:
        token = validate_bot_token(token)
        chat = validate_chat_id(chat)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    from trading_pulse.agent.dryrun_agent import telegram_api_call

    text = (
        "✅ <b>Trading Pulse</b> — החיבור עובד!\n"
        "הבוט מחובר לאפליקציה. שלח <code>עזרה</code> לרשימת פקודות."
    )
    try:
        telegram_api_call(
            token,
            "sendMessage",
            {"chat_id": chat, "text": text, "parse_mode": "HTML"},
        )
    except Exception as ex:
        raise HTTPException(status_code=502, detail=f"שליחה נכשלה: {ex}") from ex

    return {"ok": True, "message": "הודעת בדיקה נשלחה לטלגרם שלך."}

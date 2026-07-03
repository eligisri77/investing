"""In-app notifications (replaces Telegram when notification_mode=app)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trading_pulse.telegram.telegram_store import append_message as log_inbox_message

from trading_pulse.core.app_paths import INBOX_STATE_FILE


def _ensure_data_dir() -> None:
    INBOX_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_inbox_state() -> dict[str, Any]:
    _ensure_data_dir()
    if not INBOX_STATE_FILE.exists():
        return {"unread": 0, "pending_plan_day": None, "last_notification_at": None}
    with INBOX_STATE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_inbox_state(state: dict[str, Any]) -> None:
    _ensure_data_dir()
    with INBOX_STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def uses_app_notifications(cfg: Any) -> bool:
    mode = str(getattr(cfg, "notification_mode", "app")).lower()
    return mode in {"app", "both"}


def uses_telegram_notifications(cfg: Any) -> bool:
    mode = str(getattr(cfg, "notification_mode", "app")).lower()
    return mode in {"telegram", "both"}


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def bump_inbox(
    *,
    requires_action: bool = False,
    trading_day: str | None = None,
) -> dict[str, Any]:
    state = load_inbox_state()
    state["unread"] = int(state.get("unread", 0)) + 1
    state["last_notification_at"] = datetime.now(timezone.utc).isoformat()
    if requires_action and trading_day:
        state["pending_plan_day"] = trading_day
    save_inbox_state(state)
    return state


def clear_pending_plan(trading_day: str | None = None) -> None:
    state = load_inbox_state()
    if trading_day is None or state.get("pending_plan_day") == trading_day:
        state["pending_plan_day"] = None
    save_inbox_state(state)


def mark_inbox_read() -> None:
    state = load_inbox_state()
    state["unread"] = 0
    save_inbox_state(state)


def inbox_summary() -> dict[str, Any]:
    state = load_inbox_state()
    return {
        "unread": int(state.get("unread", 0)),
        "pending_plan_day": state.get("pending_plan_day"),
        "last_notification_at": state.get("last_notification_at"),
    }


def notify_user(
    cfg: Any,
    text: str,
    context: str,
    *,
    parse_mode: str | None = None,
    plan: dict[str, Any] | None = None,
    telegram_sender: Callable[..., bool] | None = None,
) -> bool:
    """Deliver notification to app inbox and/or Telegram based on config."""
    sent = False
    metadata: dict[str, Any] = {}
    requires_action = False
    trading_day = None
    if plan:
        trading_day = plan.get("for_trading_day")
        requires_action = plan.get("status") == "pending_approval"
        metadata = {
            "trading_day": trading_day,
            "requires_action": requires_action,
        }

    if uses_app_notifications(cfg):
        plain = strip_html(text) if parse_mode == "HTML" else text
        log_inbox_message("out", context, plain, parse_mode=None, metadata=metadata)
        bump_inbox(requires_action=requires_action, trading_day=trading_day)
        sent = True

    if uses_telegram_notifications(cfg) and telegram_sender is not False:
        if telegram_sender is not None and telegram_sender(cfg, text, context, parse_mode=parse_mode):
            sent = True

    return sent

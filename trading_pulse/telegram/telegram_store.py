"""Persist Telegram messages for the web dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from trading_pulse.core.app_paths import MESSAGES_FILE, TELEGRAM_DIR


def _ensure_dir() -> None:
    TELEGRAM_DIR.mkdir(parents=True, exist_ok=True)


def load_messages() -> list[dict[str, Any]]:
    if not MESSAGES_FILE.exists():
        return []
    with MESSAGES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return []


def save_messages(messages: list[dict[str, Any]]) -> None:
    _ensure_dir()
    with MESSAGES_FILE.open("w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def append_message(
    direction: str,
    context: str,
    text: str,
    *,
    parse_mode: str | None = None,
    message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: str | None = None,
    backfilled: bool = False,
) -> dict[str, Any]:
    entry = {
        "id": message_id or f"{direction}:{uuid4().hex[:12]}",
        "direction": direction,
        "context": context,
        "text": text,
        "parse_mode": parse_mode,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "backfilled": backfilled,
        "metadata": metadata or {},
    }
    messages = load_messages()
    if any(m.get("id") == entry["id"] for m in messages):
        return entry
    messages.append(entry)
    messages.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    save_messages(messages)
    return entry


def merge_backfill(entries: list[dict[str, Any]]) -> int:
    messages = load_messages()
    existing = {m.get("id") for m in messages}
    added = 0
    for entry in entries:
        if entry.get("id") in existing:
            continue
        messages.append(entry)
        existing.add(entry["id"])
        added += 1
    if added:
        messages.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
        save_messages(messages)
    return added

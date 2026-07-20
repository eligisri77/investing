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


def get_message(message_id: str) -> dict[str, Any] | None:
    return next(
        (message for message in load_messages() if message.get("id") == message_id),
        None,
    )


def update_message_metadata(
    message_id: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    messages = load_messages()
    for message in messages:
        if message.get("id") != message_id:
            continue
        current = dict(message.get("metadata") or {})
        current.update(metadata)
        message["metadata"] = current
        save_messages(messages)
        return message
    return None


def merge_backfill(entries: list[dict[str, Any]]) -> int:
    messages = load_messages()
    existing = {m.get("id") for m in messages}
    # Skip archive rows when a live (non-backfilled) message already covers
    # the same context + trading day — avoids duplicate plan/report/heartbeat.
    live_keys: set[tuple[str, str]] = set()
    for message in messages:
        if message.get("backfilled"):
            continue
        ctx = str(message.get("context") or "")
        if ctx not in {"plan", "report", "heartbeat"}:
            continue
        meta = message.get("metadata") or {}
        day = str(meta.get("trading_day") or "")
        if not day:
            day = str(message.get("timestamp") or "")[:10]
        if day:
            live_keys.add((ctx, day))

    added = 0
    for entry in entries:
        if entry.get("id") in existing:
            continue
        ctx = str(entry.get("context") or "")
        meta = entry.get("metadata") or {}
        day = str(meta.get("trading_day") or "")
        if not day:
            day = str(entry.get("timestamp") or "")[:10]
        if ctx in {"plan", "report", "heartbeat"} and day and (ctx, day) in live_keys:
            continue
        messages.append(entry)
        existing.add(entry.get("id"))
        added += 1
    if added:
        messages.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
        save_messages(messages)
    return added

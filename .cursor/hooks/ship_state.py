#!/usr/bin/env python3
"""Shared pending ship-check state for Trading Pulse hooks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_FILE = STATE_DIR / "pending_ship.json"

# Product code that should get tests after edits.
PRODUCT_PREFIXES = (
    "trading_pulse/",
    "web/static/",
)

# Editing these satisfies the test-writer requirement.
TEST_PREFIXES = ("tests/",)

# User-facing surfaces that should keep guides in sync.
GUIDE_TRIGGER_PREFIXES = (
    "trading_pulse/telegram/",
    "trading_pulse/guides/",
    "trading_pulse/agent/dryrun_agent.py",
    "trading_pulse/agent/capital_allocation.py",
    "trading_pulse/agent/ticker_manager.py",
    "trading_pulse/agent/trading_flow.py",
    "trading_pulse/agent/plan_engine.py",
    "trading_pulse/agent/intraday_monitor.py",
    "web/static/",
)

# Editing these satisfies the guide-updater requirement.
GUIDE_SATISFY_SUFFIXES = (
    "telegram_guide.py",
    "telegram_bot_guide.py",
    "selection_guide.py",
)

GUIDE_SATISFY_PATH_PARTS = (
    "trading_pulse/guides/",
    "trading_pulse/telegram/telegram_guide.py",
    "trading_pulse/telegram/telegram_bot_guide.py",
)

# Never treat tooling / hooks / agent defs as product ship triggers.
IGNORE_PREFIXES = (
    ".cursor/",
    "instance/",
)


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    # Strip drive / absolute workspace prefix if present
    lower = p.lower()
    for marker in ("/trading_pulse/", "/web/static/", "/tests/", "/.cursor/"):
        idx = lower.find(marker)
        if idx >= 0:
            return p[idx + 1 :]  # drop leading slash → trading_pulse/...
    # Already relative
    if p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def load_state() -> dict[str, Any]:
    try:
        if STATE_FILE.is_file():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"need_tests": False, "need_guides": False, "paths": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def clear_state() -> None:
    state = {"need_tests": False, "need_guides": False, "paths": []}
    save_state(state)


def is_ignored(rel: str) -> bool:
    return any(rel.startswith(p) or f"/{p}" in f"/{rel}" for p in IGNORE_PREFIXES)


def is_product(rel: str) -> bool:
    if is_ignored(rel):
        return False
    if any(rel.startswith(p) for p in TEST_PREFIXES):
        return False
    if rel.endswith(GUIDE_SATISFY_SUFFIXES):
        return False
    if any(rel.startswith(p) or p in rel for p in GUIDE_SATISFY_PATH_PARTS):
        # Guide-only edits don't re-trigger product ship
        if "telegram_format.py" not in rel and "reply_cards.py" not in rel:
            return False
    return any(rel.startswith(p) for p in PRODUCT_PREFIXES)


def triggers_guides(rel: str) -> bool:
    if is_ignored(rel):
        return False
    if any(rel.endswith(s) for s in GUIDE_SATISFY_SUFFIXES):
        return False
    for p in GUIDE_TRIGGER_PREFIXES:
        if rel == p.rstrip("/") or rel.startswith(p):
            return True
    return False


def satisfies_tests(rel: str) -> bool:
    return any(rel.startswith(p) for p in TEST_PREFIXES)


def satisfies_guides(rel: str) -> bool:
    if any(rel.endswith(s) for s in GUIDE_SATISFY_SUFFIXES):
        return True
    if "selection_guide.py" in rel:
        return True
    # In-chat guides live in telegram_format user_guide_* — count format edits
    # only when the agent also ran guide-updater; file edit alone of format
    # is product. So do NOT clear guides on telegram_format.py alone.
    return False


def note_edit(file_path: str) -> dict[str, Any]:
    rel = _norm(file_path)
    state = load_state()
    paths: list[str] = list(state.get("paths") or [])
    if rel and rel not in paths:
        paths.append(rel)
        # Cap history
        paths = paths[-40:]
    state["paths"] = paths

    if satisfies_tests(rel):
        state["need_tests"] = False
    elif is_product(rel):
        state["need_tests"] = True

    if satisfies_guides(rel):
        state["need_guides"] = False
    elif triggers_guides(rel):
        state["need_guides"] = True

    save_state(state)
    return state


def note_subagent(subagent_type: str, status: str) -> dict[str, Any]:
    state = load_state()
    if status != "completed":
        return state
    st = (subagent_type or "").strip().lower()
    if st in {"trading-pulse-test-writer", "trading_pulse_test_writer"}:
        state["need_tests"] = False
    if st in {"trading-pulse-guide-updater", "trading_pulse_guide_updater"}:
        state["need_guides"] = False
    # Verifier does not clear pending — it checks them
    save_state(state)
    return state


def pending_summary(state: dict[str, Any] | None = None) -> list[str]:
    state = state or load_state()
    missing: list[str] = []
    if state.get("need_tests"):
        missing.append("tests (@trading-pulse-test-writer)")
    if state.get("need_guides"):
        missing.append("guides (@trading-pulse-guide-updater)")
    return missing

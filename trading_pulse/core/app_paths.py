"""Install directory vs writable user-data (dev tree + PyInstaller build)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "TradingPulse"
APP_VERSION = "0.1.32"
INSTANCE_DIR_NAME = "instance"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def install_dir() -> Path:
    """Application files (code, web UI, examples)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        internal = Path(sys.executable).resolve().parent / "_internal"
        if internal.is_dir():
            return internal
        return Path(sys.executable).resolve().parent
    # Repo root (parent of trading_pulse package).
    return Path(__file__).resolve().parent.parent.parent


def user_data_dir() -> Path:
    """Writable config, secrets, plans, and runtime data."""
    if is_frozen():
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
        root.mkdir(parents=True, exist_ok=True)
        return root
    return install_dir() / INSTANCE_DIR_NAME


def config_examples_dir() -> Path:
    """Tracked templates (instance/ in dev, bundle root when frozen)."""
    if is_frozen():
        return install_dir()
    return install_dir() / INSTANCE_DIR_NAME


INSTALL_DIR = install_dir()
USER_DATA_DIR = user_data_dir()

# Bundled / read-only assets live under INSTALL_DIR; user files under USER_DATA_DIR.
BASE_DIR = USER_DATA_DIR
DATA_DIR = USER_DATA_DIR / "data"
PLANS_DIR = DATA_DIR / "plans"
REPORTS_DIR = DATA_DIR / "reports"
STATE_FILE = DATA_DIR / "state.json"
CONFIG_FILE = USER_DATA_DIR / "config.json"
ENV_FILE = USER_DATA_DIR / ".env"
CONFIG_EXAMPLE = config_examples_dir() / "config.example.json"
ENV_EXAMPLE = config_examples_dir() / ".env.example"
WEB_STATIC_DIR = INSTALL_DIR / "web" / "static"
LOCK_FILE = DATA_DIR / "trading_pulse.lock"
HEALTH_FILE = DATA_DIR / "health.json"
SCHEDULER_LOG_FILE = DATA_DIR / "logs" / "scheduler.log"
INBOX_STATE_FILE = DATA_DIR / "inbox_state.json"
TELEGRAM_DIR = DATA_DIR / "telegram"
MESSAGES_FILE = TELEGRAM_DIR / "messages.json"
WATCHLIST_DIR = DATA_DIR / "watchlist"

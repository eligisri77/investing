"""First-run setup: user config, .env, and data folders."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from trading_pulse.core.app_paths import (
    CONFIG_EXAMPLE,
    CONFIG_FILE,
    DATA_DIR,
    ENV_EXAMPLE,
    ENV_FILE,
    INSTANCE_DIR_NAME,
    PLANS_DIR,
    REPORTS_DIR,
    TELEGRAM_DIR,
    USER_DATA_DIR,
    install_dir,
    is_frozen,
)


def _copy_if_missing(src: Path, dest: Path) -> bool:
    if dest.exists() or not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def _write_default_env() -> bool:
    if ENV_FILE.exists():
        return False
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text(
        "# Telegram bot credentials (see dashboard: Settings / Bot guide)\n"
        "TELEGRAM_BOT_TOKEN=\n"
        "TELEGRAM_CHAT_ID=\n",
        encoding="utf-8",
    )
    return True


def _migrate_legacy_root_layout() -> None:
    """Move pre-instance/ dev files from repo root (one-time)."""
    if is_frozen():
        return
    root = install_dir()
    instance = USER_DATA_DIR
    instance.mkdir(parents=True, exist_ok=True)
    for src, dest in (
        (root / "config.json", instance / "config.json"),
        (root / "config.example.json", instance / "config.example.json"),
        (root / ".env", instance / ".env"),
        (root / ".env.example", instance / ".env.example"),
        (root / "data", instance / "data"),
    ):
        if not src.exists() or dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))


def ensure_first_run() -> list[str]:
    """Create missing user files. Returns names of created resources."""
    _migrate_legacy_root_layout()
    created: list[str] = []

    for directory in (DATA_DIR, PLANS_DIR, REPORTS_DIR, DATA_DIR / "logs", TELEGRAM_DIR):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            if directory == DATA_DIR:
                created.append(f"{INSTANCE_DIR_NAME}/data/")

    if _copy_if_missing(CONFIG_EXAMPLE, CONFIG_FILE):
        created.append("config.json")
    if _copy_if_missing(ENV_EXAMPLE, ENV_FILE):
        created.append(".env")
    elif _write_default_env():
        created.append(".env")

    if created:
        mode = "installed" if is_frozen() else "development"
        logging.info("First-run bootstrap (%s): created %s", mode, ", ".join(created))
    return created

"""Load and persist Telegram credentials (.env overrides config.json)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from trading_pulse.core.app_paths import CONFIG_FILE, ENV_FILE

TOKEN_KEY = "TELEGRAM_BOT_TOKEN"
CHAT_KEY = "TELEGRAM_CHAT_ID"
ALPHA_VANTAGE_KEY = "ALPHA_VANTAGE_API_KEY"
FINNHUB_KEY = "FINNHUB_API_KEY"
ALPACA_KEY_ID = "ALPACA_API_KEY_ID"
ALPACA_SECRET_KEY = "ALPACA_API_SECRET_KEY"

MARKET_DATA_ENV_KEYS = (
    ALPHA_VANTAGE_KEY,
    FINNHUB_KEY,
    ALPACA_KEY_ID,
    ALPACA_SECRET_KEY,
)
TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]+$")
CHAT_RE = re.compile(r"^-?\d+$")


def _parse_env_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def read_env_file() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    try:
        return _parse_env_lines(ENV_FILE.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _load_dotenv(override: bool = False) -> None:
    if not ENV_FILE.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_FILE, override=override)
        return
    except ImportError:
        pass
    for key, value in read_env_file().items():
        if override:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def mask_secret(value: str, *, visible: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= visible:
        return "•" * len(text)
    return "•" * (len(text) - visible) + text[-visible:]


def read_telegram_credentials() -> tuple[str, str]:
    """Effective token and chat id (env file → os.environ → config.json)."""
    _load_dotenv(override=True)
    token = os.environ.get(TOKEN_KEY, "").strip()
    chat_id = os.environ.get(CHAT_KEY, "").strip()
    if token and chat_id:
        return token, chat_id

    env_vals = read_env_file()
    token = env_vals.get(TOKEN_KEY, "").strip() or token
    chat_id = env_vals.get(CHAT_KEY, "").strip() or chat_id
    if token and chat_id:
        return token, chat_id

    if CONFIG_FILE.exists():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            token = token or str(raw.get("telegram_bot_token", "")).strip()
            chat_id = chat_id or str(raw.get("telegram_chat_id", "")).strip()
        except (OSError, json.JSONDecodeError):
            pass
    return token, chat_id


def secrets_source() -> str:
    env_vals = read_env_file()
    if env_vals.get(TOKEN_KEY) or env_vals.get(CHAT_KEY):
        return "env"
    if os.environ.get(TOKEN_KEY) or os.environ.get(CHAT_KEY):
        return "env"
    if CONFIG_FILE.exists():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if str(raw.get("telegram_bot_token", "")).strip() or str(raw.get("telegram_chat_id", "")).strip():
                return "config"
        except (OSError, json.JSONDecodeError):
            pass
    return "none"


def apply_secrets_to_config(raw: dict) -> dict:
    """Overlay telegram secrets from .env / environment onto config dict."""
    _load_dotenv(override=True)
    env_vals = read_env_file()
    token = env_vals.get(TOKEN_KEY, "").strip() or os.environ.get(TOKEN_KEY, "").strip()
    chat_id = env_vals.get(CHAT_KEY, "").strip() or os.environ.get(CHAT_KEY, "").strip()
    if token:
        raw["telegram_bot_token"] = token
    if chat_id:
        raw["telegram_chat_id"] = chat_id
    for key in MARKET_DATA_ENV_KEYS:
        value = env_vals.get(key, "").strip() or os.environ.get(key, "").strip()
        if value:
            os.environ[key] = value
    return raw


def market_data_keys_status() -> dict[str, bool]:
    """Which paid market-data API keys are configured (values never returned)."""
    _load_dotenv(override=True)
    env_vals = read_env_file()

    def _has(key: str) -> bool:
        return bool(env_vals.get(key, "").strip() or os.environ.get(key, "").strip())

    return {
        "alpha_vantage": _has(ALPHA_VANTAGE_KEY),
        "finnhub": _has(FINNHUB_KEY),
        "alpaca": _has(ALPACA_KEY_ID) and _has(ALPACA_SECRET_KEY),
    }


def write_telegram_env(token: str, chat_id: str) -> None:
    """Persist Telegram credentials to .env (keeps other keys and comments)."""
    token = token.strip()
    chat_id = chat_id.strip()
    lines: list[str] = []
    found_token = found_chat = False

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{TOKEN_KEY}="):
                lines.append(f"{TOKEN_KEY}={token}")
                found_token = True
            elif stripped.startswith(f"{CHAT_KEY}="):
                lines.append(f"{CHAT_KEY}={chat_id}")
                found_chat = True
            else:
                lines.append(line)
    else:
        lines.append("# Telegram bot (never commit real tokens to git)")

    if not found_token:
        lines.append(f"{TOKEN_KEY}={token}")
    if not found_chat:
        lines.append(f"{CHAT_KEY}={chat_id}")

    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    os.environ[TOKEN_KEY] = token
    os.environ[CHAT_KEY] = chat_id


def clear_telegram_from_config_json() -> None:
    if not CONFIG_FILE.exists():
        return
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    changed = False
    if raw.get("telegram_bot_token"):
        raw["telegram_bot_token"] = ""
        changed = True
    if raw.get("telegram_chat_id"):
        raw["telegram_chat_id"] = ""
        changed = True
    if changed:
        CONFIG_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_bot_token(token: str) -> str:
    text = token.strip()
    if not TOKEN_RE.fullmatch(text):
        raise ValueError("פורמט Token לא תקין (מקבלים מ-@BotFather)")
    return text


def validate_chat_id(chat_id: str) -> str:
    text = chat_id.strip()
    if not CHAT_RE.fullmatch(text):
        raise ValueError("Chat ID חייב להיות מספר (למשל 123456789)")
    return text

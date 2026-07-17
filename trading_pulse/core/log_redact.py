"""Redact secrets from log strings (Telegram bot tokens in URLs, etc.)."""

from __future__ import annotations

import logging
import re

_BOT_IN_URL = re.compile(r"(https://api\.telegram\.org/bot)([^/\s\"']+)", re.IGNORECASE)
_BOT_TOKEN_SHAPE = re.compile(r"\b(\d{8,}:[A-Za-z0-9_-]{25,})\b")


def redact_secrets(text: object) -> str:
    """Replace Telegram bot tokens so they never land in logs."""
    s = str(text) if text is not None else ""
    if not s:
        return s
    out = _BOT_IN_URL.sub(r"\1***", s)
    out = _BOT_TOKEN_SHAPE.sub("***", out)
    return out


def _scrub_arg(arg: object) -> object:
    if isinstance(arg, str):
        return redact_secrets(arg)
    if isinstance(arg, BaseException):
        return redact_secrets(arg)
    return arg


class RedactSecretsFilter(logging.Filter):
    """Logging filter: scrub secrets from the formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_secrets(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: _scrub_arg(v) for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(_scrub_arg(a) for a in record.args)
            if record.exc_text:
                record.exc_text = redact_secrets(record.exc_text)
        except Exception:
            pass
        return True

"""Tests for Telegram token redaction in logs."""

from __future__ import annotations

from trading_pulse.core.log_redact import redact_secrets


def test_redact_bot_token_in_telegram_url():
    raw = (
        "502 Server Error: Bad Gateway for url: "
        "https://api.telegram.org/bot123456789:AAExampleTokenValueHereXXXX/getUpdates"
    )
    out = redact_secrets(raw)
    assert "AAExampleTokenValueHereXXXX" not in out
    assert "api.telegram.org/bot***" in out


def test_redact_bare_bot_token_shape():
    raw = "token=1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    out = redact_secrets(raw)
    assert "AAH" not in out
    assert "***" in out

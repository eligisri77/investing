"""Tests for Telegram token redaction in logs."""

from __future__ import annotations

import io
import logging
import sys

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


def test_safe_console_filter_sanitizes_emoji_for_cp1252(monkeypatch):
    """Filter rewrites the record so a cp1252 console can encode the message."""
    from trading_pulse.agent.dryrun_agent import _SafeConsoleFilter

    class _FakeStdout:
        encoding = "cp1252"

    monkeypatch.setattr(sys, "stdout", _FakeStdout())
    filt = _SafeConsoleFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="תוכנית ✅ emoji 🚀",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    # After sanitizing, cp1252 encode must succeed (Hebrew/emoji → '?').
    record.getMessage().encode("cp1252")
    assert "emoji" in record.getMessage()


def test_replace_stderr_handler_emit_with_emoji_does_not_raise(monkeypatch):
    """Handler + filter must never propagate UnicodeEncodeError to the loop."""
    from trading_pulse.agent.dryrun_agent import (
        _ReplaceStderrHandler,
        _SafeConsoleFilter,
    )

    class _Cp1252Stream(io.TextIOBase):
        encoding = "cp1252"

        def write(self, s: str) -> int:
            s.encode("cp1252")
            return len(s)

        def flush(self) -> None:
            return None

    class _FakeStdout:
        encoding = "cp1252"

    monkeypatch.setattr(sys, "stdout", _FakeStdout())
    stream = _Cp1252Stream()
    handler = _ReplaceStderrHandler.__new__(_ReplaceStderrHandler)
    logging.StreamHandler.__init__(handler, stream=stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(_SafeConsoleFilter())

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="תוכנית ✅ emoji 🚀",
        args=(),
        exc_info=None,
    )
    handler.emit(record)  # must not raise


def test_setup_logger_console_handler_is_replace_stderr(tmp_path):
    from trading_pulse.agent.dryrun_agent import (
        _ReplaceStderrHandler,
        setup_logger,
    )

    log_file = tmp_path / "agent.log"
    setup_logger(log_file)
    assert any(isinstance(h, _ReplaceStderrHandler) for h in logging.root.handlers)
    logging.info("מדריך 📊")  # smoke: root logger emit must not raise

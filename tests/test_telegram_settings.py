"""Telegram settings API payload."""

from trading_pulse.telegram.telegram_settings import get_telegram_settings_payload


def test_telegram_settings_payload_has_env_path():
    payload = get_telegram_settings_payload()
    assert "env_path" in payload
    assert payload["env_path"].endswith(".env")
    assert "setup_steps" in payload

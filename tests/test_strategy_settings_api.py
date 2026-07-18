from __future__ import annotations

import pytest
from fastapi import HTTPException

from trading_pulse.api import web_app
from trading_pulse.core import app_settings


def test_settings_payload_exposes_strategy_defaults_and_metadata(monkeypatch):
    monkeypatch.setattr(app_settings, "_read_config", lambda: {})

    payload = app_settings.get_settings_payload()

    assert payload["values"]["strategy_mode"] == "balanced_mix"
    assert payload["values"]["candle_fourth_enabled"] is True
    assert payload["values"]["trend_pullback_enabled"] is False
    assert payload["values"]["vcp_breakout_enabled"] is False
    assert payload["values"]["relative_strength_enabled"] is False
    assert payload["values"]["market_regime_filter_enabled"] is False
    metadata = {row["id"]: row for row in payload["strategy_metadata"]}
    assert metadata["method2"]["entry_policy"] == "stop_breakout"
    assert metadata["trend_pullback"]["default_enabled"] is False
    assert metadata["vcp_breakout"]["default_enabled"] is False
    assert metadata["relative_strength"]["default_enabled"] is False


def test_update_settings_validates_and_persists_strategy_fields(monkeypatch):
    stored = {"risk_profile": "balanced"}

    monkeypatch.setattr(app_settings, "_read_config", lambda: dict(stored))
    monkeypatch.setattr(
        app_settings,
        "_write_config",
        lambda value: stored.update(value),
    )

    out = app_settings.update_settings(
        {
            "strategy_mode": "method2_only",
            "candle_fourth_enabled": False,
            "trend_pullback_enabled": "true",
            "vcp_breakout_enabled": "on",
            "relative_strength_enabled": False,
            "market_regime_filter_enabled": "off",
        }
    )

    assert out["ok"] is True
    assert out["restart_recommended"] is False
    assert stored["strategy_mode"] == "method2_only"
    assert stored["candle_fourth_enabled"] is False
    assert stored["trend_pullback_enabled"] is True
    assert stored["vcp_breakout_enabled"] is True
    assert stored["relative_strength_enabled"] is False
    assert stored["market_regime_filter_enabled"] is False
    assert out["values"]["vcp_breakout_enabled"] is True
    assert out["values"]["relative_strength_enabled"] is False


def test_update_settings_rejects_unknown_strategy_mode(monkeypatch):
    monkeypatch.setattr(app_settings, "_read_config", lambda: {})

    with pytest.raises(HTTPException) as exc:
        app_settings.update_settings({"strategy_mode": "anything"})

    assert exc.value.status_code == 400
    assert "ערך לא חוקי" in str(exc.value.detail)


def test_strategy_performance_api_uses_current_state(monkeypatch):
    state = {"history": [{"trading_day": "2026-07-18"}]}
    expected = {"strategies": [], "total_signals": 0}
    seen = {}

    monkeypatch.setattr(web_app, "load_state", lambda: state)

    def fake_performance(value):
        seen["state"] = value
        return expected

    monkeypatch.setattr(web_app, "strategy_performance", fake_performance)

    assert web_app.api_strategy_performance() == expected
    assert seen["state"] is state

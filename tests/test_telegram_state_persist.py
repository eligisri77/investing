"""Regression: telegram poll must not wipe sells when saving update offset."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import trading_pulse.agent.dryrun_agent as agent


def test_telegram_poll_preserves_sell_when_saving_offset(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state = {
        "equity": 1000.0,
        "open_positions": [
            {"symbol": "RIVN", "capital_usd": 333.0, "entry_price": 15.0, "entry_day": "2026-07-08"},
        ],
        "telegram_last_update_id": 10,
        "history": [],
        "month_key": "2026-07",
        "month_start_equity": 1000.0,
        "month_start_date": "2026-07-01",
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(agent, "STATE_FILE", state_path)

    def _fake_api(_token, method, _payload=None):
        if method == "getUpdates":
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 11,
                        "message": {"chat": {"id": "1"}, "text": "מכור 1 $20"},
                    }
                ],
            }
        return {"ok": True, "result": {}}

    monkeypatch.setattr(agent, "telegram_api_call", _fake_api)
    monkeypatch.setattr(agent, "uses_telegram_notifications", lambda _cfg: True)
    monkeypatch.setattr(agent, "log_telegram_message", lambda *a, **k: None)
    monkeypatch.setattr(agent, "send_telegram_message", lambda *a, **k: True)
    monkeypatch.setattr(agent, "send_telegram_photo", lambda *a, **k: True)
    monkeypatch.setattr(agent, "resolve_sell_target", lambda ref: "RIVN")

    def _sell(cfg, symbol, fraction=1.0, *, sell_usd=None):
        st = json.loads(state_path.read_text(encoding="utf-8"))
        for p in st["open_positions"]:
            if p["symbol"] == "RIVN":
                p["capital_usd"] = 313.0
        st["equity"] = 1003.0
        state_path.write_text(json.dumps(st), encoding="utf-8")
        return "✅ sold"

    monkeypatch.setattr(agent, "execute_sell_command", _sell)

    class Cfg:
        telegram_bot_token = "t"
        telegram_chat_id = "1"
        initial_capital = 1000.0
        notification_mode = "telegram"

    agent.process_telegram_commands(Cfg())
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["telegram_last_update_id"] == 11
    assert saved["open_positions"][0]["capital_usd"] == 313.0
    assert saved["equity"] == 1003.0

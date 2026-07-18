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


def test_app_and_telegram_failure_persists_delivery_and_warning(
    tmp_path, monkeypatch
):
    from trading_pulse.telegram import app_notify, telegram_store

    messages_file = tmp_path / "messages.json"
    monkeypatch.setattr(telegram_store, "MESSAGES_FILE", messages_file)
    monkeypatch.setattr(telegram_store, "TELEGRAM_DIR", tmp_path)
    monkeypatch.setattr(app_notify, "bump_inbox", lambda **_kwargs: {})

    class Cfg:
        notification_mode = "both"

    assert app_notify.notify_user(
        Cfg(),
        "<b>תוכנית</b>",
        "plan",
        parse_mode="HTML",
        telegram_sender=lambda *_args, **_kwargs: False,
    )

    messages = telegram_store.load_messages()
    original = next(row for row in messages if row["context"] == "plan")
    warning = next(
        row
        for row in messages
        if row["context"] == "delivery:telegram_failed"
    )
    assert original["text"] == "תוכנית"
    assert original["metadata"]["delivery"]["app"]["status"] == "delivered"
    assert original["metadata"]["delivery"]["telegram"]["status"] == "failed"
    assert original["metadata"]["delivery"]["telegram"]["at"]
    assert "לא נמסרה לטלגרם" in warning["text"]
    assert warning["metadata"]["original_context"] == "plan"


def test_message_metadata_update_merges_and_persists(tmp_path, monkeypatch):
    from trading_pulse.telegram import telegram_store

    monkeypatch.setattr(
        telegram_store, "MESSAGES_FILE", tmp_path / "messages.json"
    )
    monkeypatch.setattr(telegram_store, "TELEGRAM_DIR", tmp_path)
    row = telegram_store.append_message(
        "out",
        "plan",
        "hello",
        message_id="out:fixed",
        metadata={"keep": "value"},
    )

    updated = telegram_store.update_message_metadata(
        row["id"],
        {"delivery": {"telegram": {"status": "failed"}}},
    )

    assert updated is not None
    persisted = telegram_store.get_message("out:fixed")
    assert persisted["metadata"]["keep"] == "value"
    assert persisted["metadata"]["delivery"]["telegram"]["status"] == "failed"


def test_retry_api_updates_delivery_metadata(monkeypatch):
    import trading_pulse.api.web_app as web_app

    updates = []
    message = {
        "id": "out:fixed",
        "direction": "out",
        "context": "plan",
        "text": "תוכנית",
        "metadata": {
            "delivery": {
                "app": {"status": "delivered", "at": "before"},
                "telegram": {"status": "failed", "at": "before"},
            }
        },
    }
    monkeypatch.setattr(web_app, "get_message", lambda _message_id: message)
    monkeypatch.setattr(web_app, "load_agent_config", lambda: object())
    monkeypatch.setattr(
        web_app,
        "update_message_metadata",
        lambda message_id, metadata: updates.append((message_id, metadata)),
    )
    monkeypatch.setattr(
        agent,
        "_send_telegram_as_card",
        lambda *_args, **_kwargs: True,
    )

    result = web_app.api_retry_telegram_message("out:fixed")

    assert result["ok"] is True
    assert result["delivery"]["app"]["status"] == "delivered"
    assert result["delivery"]["telegram"]["status"] == "delivered"
    assert result["delivery"]["telegram"]["at"] != "before"
    assert updates == [("out:fixed", {"delivery": result["delivery"]})]

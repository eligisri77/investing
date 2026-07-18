"""Regression: telegram poll must not wipe sells when saving update offset."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

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


def _photo_cfg(mode: str, *, token: str = "token"):
    class Cfg:
        notification_mode = mode
        telegram_bot_token = token
        telegram_chat_id = "chat"

    return Cfg()


def _isolated_message_store(tmp_path, monkeypatch):
    from trading_pulse.telegram import telegram_store

    monkeypatch.setattr(
        telegram_store, "MESSAGES_FILE", tmp_path / "messages.json"
    )
    monkeypatch.setattr(telegram_store, "TELEGRAM_DIR", tmp_path)
    monkeypatch.setattr(agent, "_save_telegram_image", lambda _png: "image123")
    return telegram_store


@pytest.mark.parametrize(
    ("send_ok", "expected_result", "expected_status"),
    [
        (True, True, "delivered"),
        (False, False, "failed"),
    ],
)
def test_photo_updates_existing_app_row_delivery(
    tmp_path, monkeypatch, send_ok, expected_result, expected_status
):
    from trading_pulse.telegram import app_notify

    store = _isolated_message_store(tmp_path, monkeypatch)
    cfg = _photo_cfg("both")
    app_notify.notify_user(
        cfg,
        "כרטיס",
        "reply:card",
        telegram_sender=False,
    )

    class Response:
        def raise_for_status(self):
            if not send_ok:
                raise RuntimeError("offline")

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(agent.requests, "post", lambda *_args, **_kwargs: Response())

    result = agent.send_telegram_photo(
        cfg,
        b"png",
        "כרטיס",
        context="reply:card",
        log_inbox=False,
    )

    assert result is expected_result
    messages = store.load_messages()
    assert len(messages) == 1
    delivery = messages[0]["metadata"]["delivery"]
    assert delivery["app"]["status"] == "delivered"
    assert delivery["telegram"]["status"] == expected_status
    assert delivery["telegram"]["at"]


@pytest.mark.parametrize(
    ("mode", "expected_result", "expected_status"),
    [
        ("both", False, "failed"),
        ("app", True, "not_requested"),
    ],
)
def test_photo_missing_token_fails_both_but_app_only_succeeds(
    tmp_path, monkeypatch, mode, expected_result, expected_status
):
    from trading_pulse.telegram import app_notify

    store = _isolated_message_store(tmp_path, monkeypatch)
    cfg = _photo_cfg(mode, token="")
    app_notify.notify_user(
        cfg,
        "תמונה",
        "photo",
        telegram_sender=False,
    )

    result = agent.send_telegram_photo(
        cfg,
        b"png",
        "תמונה",
        context="photo",
        log_inbox=False,
    )

    assert result is expected_result
    message = store.load_messages()[0]
    assert message["metadata"]["delivery"]["app"]["status"] == "delivered"
    assert (
        message["metadata"]["delivery"]["telegram"]["status"]
        == expected_status
    )


def test_card_path_updates_same_app_inbox_row(tmp_path, monkeypatch):
    from trading_pulse.telegram import reply_cards

    store = _isolated_message_store(tmp_path, monkeypatch)
    cfg = _photo_cfg("both")
    monkeypatch.setattr(
        reply_cards,
        "render_html_message_card",
        lambda *_args, **_kwargs: b"png",
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(agent.requests, "post", lambda *_args, **_kwargs: Response())

    assert agent.send_telegram_message(
        cfg,
        "<b>בוצע</b>",
        context="reply:buy",
        parse_mode="HTML",
    )
    messages = store.load_messages()
    assert len(messages) == 1
    assert messages[0]["text"] == "בוצע"
    assert messages[0]["metadata"]["image_id"] == "image123"
    assert (
        messages[0]["metadata"]["delivery"]["telegram"]["status"]
        == "delivered"
    )


def test_plan_card_updates_prelogged_plan_row_without_duplicate(
    tmp_path, monkeypatch
):
    from trading_pulse.telegram import reply_cards

    store = _isolated_message_store(tmp_path, monkeypatch)
    cfg = _photo_cfg("both")
    monkeypatch.setattr(
        agent, "format_plan_message_for_app", lambda _plan: "תוכנית"
    )
    monkeypatch.setattr(
        reply_cards, "card_from_plan_summary", lambda _plan: b"png"
    )
    monkeypatch.setattr(agent, "send_plan_portfolio_image", lambda _cfg: None)
    monkeypatch.setattr(
        agent, "send_plan_table_image", lambda _cfg, _plan: None
    )
    monkeypatch.setattr(
        agent, "send_plan_stock_charts", lambda _cfg, _plan: None
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(agent.requests, "post", lambda *_args, **_kwargs: Response())

    agent.send_plan_notifications(
        cfg,
        {"for_trading_day": "2026-07-20", "status": "draft"},
    )

    messages = [
        row for row in store.load_messages() if row["context"] == "plan"
    ]
    assert len(messages) == 1
    assert messages[0]["metadata"]["image_id"] == "image123"
    assert (
        messages[0]["metadata"]["delivery"]["telegram"]["status"]
        == "delivered"
    )

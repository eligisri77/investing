"""Tests for Telegram command parsing."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from trading_pulse.agent.dryrun_agent import (
    clear_pending_sell_confirm,
    parse_telegram_user_command,
    pending_sell_confirm_symbol,
    set_pending_sell_confirm,
    try_confirm_pending_sell,
)


@pytest.mark.parametrize(
    ("text", "expected_kind", "extra"),
    [
        ("תוכנית עכשיו", "plan_now", {}),
        ("תוכנית", "plan_show", {}),
        ("מדריך", "guide_telegram", {}),
        ("איך בוחרים מניות", "guide_selection", {}),
        ("חיבור בוט", "guide_bot_setup", {}),
        ("עזרה", "help", {}),
        ("סטטוס", "status", {}),
        ("הכל", "approve", {"indices_raw": "ALL"}),
        ("אישור", "approve", {"indices_raw": "ALL"}),
        ("אשור", "approve", {"indices_raw": "ALL"}),
        ("בטל תוכנית", "plan_cancel", {}),
        ("ביטול תוכנית", "plan_cancel", {}),
        ("החלף LABU HOOD", "swap", {"from_symbol": "LABU", "to_symbol": "HOOD"}),
        (
            "החלף ELF U 190",
            "swap",
            {"from_symbol": "ELF", "to_symbol": "U", "buy_usd": 190.0, "sell_usd": 190.0},
        ),
        ("מכור ELF 100", "sell", {"symbol": "ELF", "sell_usd": 100.0}),
        ("מכירה ELF 100", "sell", {"symbol": "ELF", "sell_usd": 100.0}),
        ("למכור SOXL ולקנות HOOD", "swap", {"from_ref": "SOXL", "to_ref": "HOOD"}),
        ("תוכל לשלוח לי פקודה מלאה?", "help", {}),
        ("1,2,3", "approve", {"indices_raw": "1,2,3"}),
        ("ח1", "allocation_pick", {"option_id": 1}),
        ("ח5", "allocation_pick", {"option_id": 5}),
        ("חלוקה 3", "allocation_pick", {"option_id": 3}),
        ("1", "approve", {"indices_raw": "1"}),
        ("מניות", "tickers_list", {}),
        ("הוסף SMCI", "ticker_add", {"symbol": "SMCI"}),
        ("הסר IONQ", "ticker_remove", {"symbol": "IONQ"}),
        ("חפש מניות", "tickers_discover", {}),
        ("מכירה U", "sell_confirmation", {"ref": "U"}),
        ("מכיר U", "sell_confirmation", {"ref": "U"}),
        ("תמכור SOXL", "sell_confirmation", {"ref": "SOXL"}),
        ("למכור NVDA", "sell_confirmation", {"ref": "NVDA"}),
    ],
)
def test_parse_known_commands(text: str, expected_kind: str, extra: dict) -> None:
    parsed = parse_telegram_user_command(text)
    assert parsed["kind"] == expected_kind
    for key, value in extra.items():
        assert parsed.get(key) == value


@pytest.mark.parametrize(
    ("text", "to_ref"),
    [
        ("תקנה ARWR", "ARWR"),
        ("קנה NVDA", "NVDA"),
        ("לקנות BEAM", "BEAM"),
        ("buy HOOD", "HOOD"),
        ("תקנה 1", "1"),
        ("קנה 3", "3"),
    ],
)
def test_bare_buy_parses_as_all_cash(text: str, to_ref: str) -> None:
    """Buy without $ amount → spend all free cash."""
    parsed = parse_telegram_user_command(text)
    assert parsed == {
        "kind": "buy",
        "to_ref": to_ref,
        "buy_usd": None,
        "all_cash": True,
    }


def test_buy_with_explicit_amount() -> None:
    parsed = parse_telegram_user_command("תקנה ARWR $145")
    assert parsed == {
        "kind": "buy",
        "to_ref": "ARWR",
        "buy_usd": 145.0,
    }
    assert "all_cash" not in parsed
    assert parse_telegram_user_command("קנה BEAM 50$")["buy_usd"] == 50.0
    assert parse_telegram_user_command("buy 2 $100") == {
        "kind": "buy",
        "to_ref": "2",
        "buy_usd": 100.0,
    }


def test_free_text_not_approve() -> None:
    assert parse_telegram_user_command("שלום")["kind"] == "unknown"
    assert parse_telegram_user_command("מה קורה")["kind"] == "unknown"


def test_ch1_not_same_as_1() -> None:
    one = parse_telegram_user_command("1")
    ch_one = parse_telegram_user_command("ח1")
    assert one["kind"] == "approve"
    assert ch_one["kind"] == "allocation_pick"
    assert ch_one["option_id"] == 1


@pytest.mark.parametrize("text", ["מכירה U", "מכיר U", "תמכור U", "למכור U"])
def test_natural_sell_wording_is_confirmation_not_execution(text: str) -> None:
    parsed = parse_telegram_user_command(text)
    assert parsed == {"kind": "sell_confirmation", "ref": "U"}
    assert parsed["kind"] != "sell"


@pytest.mark.parametrize(
    "text",
    [
        "מכירה ELF 100",
        "מכירה ELF $100",
        "מכירה 100 ELF",
        "מכיר ELF 100",
        "למכור ELF 100",
        "תמכור ELF $100",
        "למכור 100 ELF",
    ],
)
def test_natural_sell_with_amount_is_execute_not_confirmation(text: str) -> None:
    """Amount turns natural sell wording into immediate sell (sell_usd), not confirm."""
    parsed = parse_telegram_user_command(text)
    assert parsed == {"kind": "sell", "symbol": "ELF", "sell_usd": 100.0}


def test_set_pending_sell_confirm_stores_symbol() -> None:
    state: dict = {}
    set_pending_sell_confirm(state, "u")
    assert state["pending_sell_confirm"]["symbol"] == "U"
    assert pending_sell_confirm_symbol(state) == "U"


@pytest.mark.parametrize("word", ["כן", "אישור", "yes", "מאשר"])
def test_try_confirm_pending_sell_accepts_confirm_words(word: str) -> None:
    state: dict = {}
    set_pending_sell_confirm(state, "SOXL")
    assert try_confirm_pending_sell(state, word) == "SOXL"
    assert "pending_sell_confirm" not in state


def test_try_confirm_pending_sell_rejects_other_text() -> None:
    state: dict = {}
    set_pending_sell_confirm(state, "SOXL")
    assert try_confirm_pending_sell(state, "לא") is None
    assert pending_sell_confirm_symbol(state) == "SOXL"


def test_pending_sell_confirm_expires() -> None:
    state: dict = {
        "pending_sell_confirm": {
            "symbol": "NVDA",
            "at": (datetime.now(timezone.utc) - timedelta(seconds=2000)).isoformat(),
        }
    }
    assert pending_sell_confirm_symbol(state, max_age_sec=1800) is None
    assert "pending_sell_confirm" not in state
    assert try_confirm_pending_sell(state, "כן") is None


def test_clear_pending_sell_confirm() -> None:
    state: dict = {}
    set_pending_sell_confirm(state, "AAPL")
    clear_pending_sell_confirm(state)
    assert pending_sell_confirm_symbol(state) is None


def _routing_setup(tmp_path, monkeypatch, *, text: str):
    """Shared scaffolding for pending-offer routing tests in process_telegram_commands."""
    import trading_pulse.agent.dryrun_agent as agent

    state_path = tmp_path / "state.json"
    state = {
        "equity": 1000.0,
        "open_positions": [],
        "telegram_last_update_id": 10,
        "history": [],
        "pending_offer": {
            "trading_day": "2026-07-20",
            "queue": ["NVDA"],
            "index": 0,
            "decided": {},
            "offered_at": None,
            "nudged_at": None,
        },
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(agent, "STATE_FILE", state_path)

    plan_file = tmp_path / "plan_2026-07-20.json"
    agent.save_json(
        plan_file,
        {
            "for_trading_day": "2026-07-20",
            "available_capital_usd": 100.0,
            "holdings": [],
            "recommendations": [{"symbol": "NVDA", "score": 12.0}],
        },
    )
    monkeypatch.setattr(agent, "plan_path", lambda _day: plan_file)

    def _fake_api(_token, method, _payload=None):
        if method == "getUpdates":
            return {
                "ok": True,
                "result": [{"update_id": 11, "message": {"chat": {"id": "1"}, "text": text}}],
            }
        return {"ok": True, "result": {}}

    monkeypatch.setattr(agent, "telegram_api_call", _fake_api)
    monkeypatch.setattr(agent, "uses_telegram_notifications", lambda _cfg: True)
    monkeypatch.setattr(agent, "log_telegram_message", lambda *a, **k: None)
    return agent, state_path, plan_file


class _RoutingCfg:
    telegram_bot_token = "t"
    telegram_chat_id = "1"
    initial_capital = 1000.0
    notification_mode = "telegram"


def test_pending_offer_does_not_intercept_direct_help_command(tmp_path, monkeypatch):
    """A direct command (עזרה) must still work normally while an offer is pending."""
    agent, state_path, _plan_file = _routing_setup(tmp_path, monkeypatch, text="עזרה")

    send_calls: list[tuple] = []
    monkeypatch.setattr(
        agent, "send_telegram_message", lambda *a, **k: send_calls.append((a, k)) or True
    )

    handled = agent.process_telegram_commands(_RoutingCfg())

    assert handled == 1
    assert len(send_calls) == 1
    assert send_calls[0][1].get("context") == "reply:help"
    # Pending offer must be untouched — the reply was not consumed as an offer decision.
    saved_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved_state["pending_offer"]["index"] == 0


def test_pending_offer_does_not_intercept_sell_command(tmp_path, monkeypatch):
    """A direct «מכור» must not be swallowed by the pending-offer reply parser."""
    agent, state_path, _plan_file = _routing_setup(tmp_path, monkeypatch, text="מכור AAPL")

    monkeypatch.setattr(agent, "resolve_sell_target", lambda ref: None)  # nothing held
    send_calls: list[tuple] = []
    monkeypatch.setattr(
        agent, "send_telegram_message", lambda *a, **k: send_calls.append((a, k)) or True
    )

    handled = agent.process_telegram_commands(_RoutingCfg())

    assert handled == 1
    # Reached the "sell" branch (not swallowed as an unrecognized offer reply).
    saved_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved_state["pending_offer"]["index"] == 0


def test_pending_offer_intercepts_bare_yes_reply(tmp_path, monkeypatch):
    """A bare «כן» while an offer is pending buys it — it must not reach normal parsing."""
    agent, state_path, plan_file = _routing_setup(tmp_path, monkeypatch, text="כן")

    send_calls: list[tuple] = []
    monkeypatch.setattr(
        agent, "send_telegram_message", lambda *a, **k: send_calls.append((a, k)) or True
    )
    notify_calls: list[dict] = []
    monkeypatch.setattr(
        agent,
        "send_user_notification",
        lambda cfg, text, **kw: notify_calls.append({"text": text, **kw}) or True,
    )

    handled = agent.process_telegram_commands(_RoutingCfg())

    assert handled == 1
    assert send_calls == []  # never fell through to normal command parsing
    assert notify_calls  # offer decision (+ finish-offers) notifications sent instead
    saved_plan = agent.read_json(plan_file)
    nvda = saved_plan["recommendations"][0]
    assert nvda["approved"] is True
    assert saved_plan["status"] == "confirmed"
    saved_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "pending_offer" not in saved_state  # queue exhausted after the only offer


def test_sell_confirmation_reply_has_no_leading_question_emoji(tmp_path, monkeypatch):
    """«תמכור BE» asks for confirm — reply must not start with ❓ (looked like an error)."""
    import trading_pulse.agent.dryrun_agent as agent

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "equity": 1000.0,
                "open_positions": [
                    {
                        "symbol": "BE",
                        "capital_usd": 200.0,
                        "entry_price": 10.0,
                        "entry_day": "2026-07-08",
                    }
                ],
                "telegram_last_update_id": 10,
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agent, "STATE_FILE", state_path)

    def _fake_api(_token, method, _payload=None):
        if method == "getUpdates":
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 11,
                        "message": {"chat": {"id": "1"}, "text": "תמכור BE"},
                    }
                ],
            }
        return {"ok": True, "result": {}}

    monkeypatch.setattr(agent, "telegram_api_call", _fake_api)
    monkeypatch.setattr(agent, "uses_telegram_notifications", lambda _cfg: True)
    monkeypatch.setattr(agent, "log_telegram_message", lambda *a, **k: None)
    monkeypatch.setattr(agent, "resolve_sell_target", lambda ref: "BE")

    send_calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "send_telegram_message",
        lambda *a, **k: send_calls.append((a, k)) or True,
    )

    handled = agent.process_telegram_commands(_RoutingCfg())
    assert handled == 1
    assert len(send_calls) == 1
    reply = send_calls[0][0][1]
    assert send_calls[0][1].get("context") == "reply:sell_confirmation"
    assert not reply.startswith("❓")
    assert reply.startswith("<b>למכור את BE?</b>")
    assert "כן" in reply
    assert "מכור BE" in reply
    assert "לא בוצעה פעולה עדיין" in reply
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["pending_sell_confirm"]["symbol"] == "BE"
    assert saved["telegram_last_update_id"] == 11


def test_telegram_command_error_reply_truncates_exception(tmp_path, monkeypatch):
    """Handler failures send a short error card — not a wall of exception text."""
    import trading_pulse.agent.dryrun_agent as agent

    agent, state_path, _plan = _routing_setup(tmp_path, monkeypatch, text="עזרה")
    monkeypatch.setattr(
        agent,
        "telegram_help_text",
        lambda: (_ for _ in ()).throw(RuntimeError("x" * 500)),
    )
    send_calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "send_telegram_message",
        lambda *a, **k: send_calls.append((a, k)) or True,
    )

    handled = agent.process_telegram_commands(_RoutingCfg())
    assert handled == 1
    assert len(send_calls) == 1
    reply = send_calls[0][0][1]
    assert send_calls[0][1].get("context") == "reply:error"
    assert reply.startswith("❌ <b>שגיאה:</b> ")
    # Truncated to 200 chars of exception text + surrounding HTML/hint.
    assert "x" * 200 in reply
    assert "x" * 201 not in reply
    assert "עזרה" in reply


def test_inbound_log_failure_still_acks_and_handles(tmp_path, monkeypatch):
    """Inbound inbox log must not stall the poll — offset is acked and command runs."""
    import trading_pulse.agent.dryrun_agent as agent

    agent, state_path, _plan = _routing_setup(tmp_path, monkeypatch, text="עזרה")

    def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(agent, "log_telegram_message", _boom)
    send_calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "send_telegram_message",
        lambda *a, **k: send_calls.append((a, k)) or True,
    )

    handled = agent.process_telegram_commands(_RoutingCfg())
    assert handled == 1
    assert len(send_calls) == 1
    assert send_calls[0][1].get("context") == "reply:help"
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["telegram_last_update_id"] == 11

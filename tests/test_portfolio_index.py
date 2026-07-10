"""Tests for numbered portfolio slots and trade command parsing."""

from __future__ import annotations

from unittest.mock import patch

from trading_pulse.agent.dryrun_agent import parse_telegram_user_command
from trading_pulse.agent.portfolio_index import attach_slots_to_portfolio, slot_to_symbol


def _holdings_state():
    return {
        "open_positions": [
            {"symbol": "LABD", "capital_usd": 333, "status": "holding", "entry_day": "2026-07-08"},
            {"symbol": "RIVN", "capital_usd": 333, "status": "holding", "entry_day": "2026-07-08"},
            {"symbol": "BEAM", "capital_usd": 320, "status": "holding", "entry_day": "2026-07-09"},
        ]
    }


def test_attach_slots_to_portfolio():
    data = attach_slots_to_portfolio(_holdings_state())
    slots = [p.get("slot") for p in data["open_positions"]]
    assert slots == [1, 2, 3]


@patch("trading_pulse.agent.portfolio.build_portfolio")
def test_slot_to_symbol(mock_build):
    mock_build.return_value = _holdings_state()
    assert slot_to_symbol(1) == "LABD"
    assert slot_to_symbol(3) == "BEAM"
    assert slot_to_symbol(9) is None


def test_parse_sell_by_slot():
    assert parse_telegram_user_command("מכור 2") == {
        "kind": "sell",
        "slot": 2,
        "fraction": 1.0,
    }
    assert parse_telegram_user_command("מכור 2 $200") == {
        "kind": "sell",
        "slot": 2,
        "sell_usd": 200.0,
    }
    assert parse_telegram_user_command("מכור 2 20$") == {
        "kind": "sell",
        "slot": 2,
        "sell_usd": 20.0,
    }
    assert parse_telegram_user_command("מכור 50% 3") == {
        "kind": "sell",
        "slot": 3,
        "fraction": 0.5,
    }


def test_parse_swap_with_amount():
    parsed = parse_telegram_user_command("מכור 4 תקנה BEAM $200")
    assert parsed["kind"] == "swap"
    assert parsed["from_ref"] == "4"
    assert parsed["to_ref"] == "BEAM"
    assert parsed["buy_usd"] == 200.0
    assert parsed["sell_usd"] == 200.0

    slot_swap = parse_telegram_user_command("מכור 1 תקנה 2 $100")
    assert slot_swap["kind"] == "swap"
    assert slot_swap["from_ref"] == "1"
    assert slot_swap["to_ref"] == "2"
    assert slot_swap["sell_usd"] == 100.0
    assert slot_swap["buy_usd"] == 100.0

    two_amt = parse_telegram_user_command("מכור 1 200$ קנה 2 100$")
    assert two_amt == {
        "kind": "swap",
        "from_ref": "1",
        "to_ref": "2",
        "sell_usd": 200.0,
        "buy_usd": 100.0,
    }
    assert parse_telegram_user_command("מכור 1 $200 תקנה 2 $100")["sell_usd"] == 200.0

    sell_then = parse_telegram_user_command("מכור 1 $100 תקנה 2")
    assert sell_then["kind"] == "swap"
    assert sell_then["from_ref"] == "1"
    assert sell_then["to_ref"] == "2"
    assert sell_then["sell_usd"] == 100.0

    nl = parse_telegram_user_command("למכור SOXL ולקנות HOOD $150")
    assert nl["kind"] == "swap"
    assert nl["from_ref"] == "SOXL"
    assert nl["to_ref"] == "HOOD"
    assert nl["buy_usd"] == 150.0
    assert nl["sell_usd"] == 150.0


def test_parse_buy_by_slot_and_symbol():
    assert parse_telegram_user_command("תקנה 1 $20") == {
        "kind": "buy",
        "to_ref": "1",
        "buy_usd": 20.0,
    }
    assert parse_telegram_user_command("קנה BEAM 50$") == {
        "kind": "buy",
        "to_ref": "BEAM",
        "buy_usd": 50.0,
    }
    assert parse_telegram_user_command("buy 2 $100")["kind"] == "buy"

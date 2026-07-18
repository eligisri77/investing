"""Tests for Telegram command parsing."""

from __future__ import annotations

import pytest

from trading_pulse.agent.dryrun_agent import parse_telegram_user_command


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
    ],
)
def test_parse_known_commands(text: str, expected_kind: str, extra: dict) -> None:
    parsed = parse_telegram_user_command(text)
    assert parsed["kind"] == expected_kind
    for key, value in extra.items():
        assert parsed.get(key) == value


def test_free_text_not_approve() -> None:
    assert parse_telegram_user_command("שלום")["kind"] == "unknown"
    assert parse_telegram_user_command("מה קורה")["kind"] == "unknown"


def test_ch1_not_same_as_1() -> None:
    one = parse_telegram_user_command("1")
    ch_one = parse_telegram_user_command("ח1")
    assert one["kind"] == "approve"
    assert ch_one["kind"] == "allocation_pick"
    assert ch_one["option_id"] == 1


@pytest.mark.parametrize("text", ["מכירה U", "מכיר U"])
def test_natural_sell_wording_is_confirmation_not_execution(text: str) -> None:
    parsed = parse_telegram_user_command(text)
    assert parsed == {"kind": "sell_confirmation", "ref": "U"}
    assert parsed["kind"] != "sell"

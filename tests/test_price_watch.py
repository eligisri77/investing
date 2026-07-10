"""Tests for hourly price-watch commands."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from trading_pulse.agent.dryrun_agent import parse_telegram_user_command
from trading_pulse.agent.price_watch import (
    add_price_watch,
    format_watch_added,
    list_price_watches,
    remove_price_watch,
)


def test_parse_price_watch_commands():
    assert parse_telegram_user_command("ציון שעתי AAPL") == {
        "kind": "price_watch_add",
        "symbol": "AAPL",
    }
    assert parse_telegram_user_command("AAPL ציון שעתי")["symbol"] == "AAPL"
    assert parse_telegram_user_command("מעקב NVDA")["kind"] == "price_watch_add"
    assert parse_telegram_user_command("הפסק מעקב AAPL") == {
        "kind": "price_watch_remove",
        "symbol": "AAPL",
    }
    assert parse_telegram_user_command("מעקבים")["kind"] == "price_watch_list"
    # one-shot score still works
    assert parse_telegram_user_command("ציון AAPL")["kind"] == "stock_detail"


def test_add_remove_price_watch():
    state: dict = {}
    added = add_price_watch(state, "aapl")
    assert added["added"] is True
    assert list_price_watches(state) == ["AAPL"]
    again = add_price_watch(state, "AAPL")
    assert again["added"] is False
    removed = remove_price_watch(state, "AAPL")
    assert removed["removed"] is True
    assert list_price_watches(state) == []


def test_clear_all_price_watches():
    from trading_pulse.agent.price_watch import clear_all_price_watches, format_watches_cleared

    state: dict = {}
    add_price_watch(state, "AAPL")
    add_price_watch(state, "NVDA")
    cleared = clear_all_price_watches(state)
    assert set(cleared) == {"AAPL", "NVDA"}
    assert list_price_watches(state) == []
    msg = format_watches_cleared(cleared)
    assert "AAPL" in msg and "NVDA" in msg


def test_format_watch_added_uses_interval():
    cfg = SimpleNamespace(intraday_check_interval_minutes=60)
    text = format_watch_added(cfg, {"symbol": "AAPL", "added": True, "watches": ["AAPL"]})
    assert "60" in text
    assert "AAPL" in text
    assert "נמחק" in text or "סוף" in text

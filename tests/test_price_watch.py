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
    with patch(
        "trading_pulse.agent.price_watch.fetch_intraday_quote",
        side_effect=lambda s: {
            "last": 100.0 if s == "AAPL" else 200.0,
            "day_change_pct": 1.5 if s == "AAPL" else -0.5,
            "high": 101.0,
            "low": 99.0,
        },
    ):
        msg = format_watches_cleared(cleared)
    assert "AAPL" in msg and "NVDA" in msg
    assert "$100.00" in msg and "$200.00" in msg
    assert "סיום מעקב" in msg


def test_format_watch_added_uses_interval():
    cfg = SimpleNamespace(intraday_check_interval_minutes=60)
    text = format_watch_added(cfg, {"symbol": "AAPL", "added": True, "watches": ["AAPL"]})
    assert "60" in text
    assert "AAPL" in text
    assert "נמחק" in text or "סוף" in text


def test_due_for_price_tick_respects_interval():
    from datetime import datetime, timedelta, timezone

    from trading_pulse.agent.price_watch import due_for_price_tick, mark_price_watch_sent

    state: dict = {}
    add_price_watch(state, "AAPL")
    assert due_for_price_tick(state, "AAPL", 60) is True
    mark_price_watch_sent(state, "AAPL")
    assert due_for_price_tick(state, "AAPL", 60) is False
    # Simulate last send just over an hour ago
    state["price_watches"]["AAPL"]["last_sent_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=61)
    ).isoformat()
    assert due_for_price_tick(state, "AAPL", 60) is True

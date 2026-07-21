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


def test_should_send_method2_price_tick_skips_flat_far_from_breakout():
    from trading_pulse.agent.price_watch import should_send_method2_price_tick

    meta = {"entry_ref": 100.0, "side": "LONG", "last_price": 90.0}
    flat_far = {"last": 90.05, "day_change_pct": 0.02}
    assert should_send_method2_price_tick(meta, flat_far) is False

    near = {"last": 99.0, "day_change_pct": 0.0}
    assert should_send_method2_price_tick(meta, near) is True

    moved = {"last": 91.0, "day_change_pct": 0.02}  # ~1% vs last_price
    assert should_send_method2_price_tick(meta, moved) is True


def test_should_send_method2_price_tick_falls_back_to_change_pct():
    from trading_pulse.agent.price_watch import should_send_method2_price_tick

    meta = {"entry_ref": 100.0, "side": "LONG", "last_price": 90.0}
    # Quote shaped like fetch_intraday_quote before day_change_pct existed.
    flat_far = {"last": 90.05, "change_pct": 0.02}
    assert should_send_method2_price_tick(meta, flat_far) is False
    moved = {"last": 91.0, "change_pct": 0.02}
    assert should_send_method2_price_tick(meta, moved) is True


def test_method2_distance_line_shows_distance():
    from trading_pulse.agent.price_watch import _method2_distance_line

    long_line = _method2_distance_line(
        {"entry_ref": 100.0, "side": "LONG", "stop_ref": 95.0},
        last=97.0,
    )
    assert "שיטה 2" in long_line
    assert "חסר" in long_line
    assert "100.00" in long_line
    assert "סטופ" in long_line

    short_line = _method2_distance_line(
        {"entry_ref": 50.0, "side": "SHORT"},
        last=52.0,
    )
    assert "שורט" in short_line
    assert "רחוק" in short_line


def test_format_price_watch_handles_zero_day_change():
    from trading_pulse.agent.price_watch import format_price_watch_update

    cfg = SimpleNamespace(intraday_check_interval_minutes=60)
    with patch(
        "trading_pulse.agent.price_watch.fetch_intraday_quote",
        return_value={"last": 42.0, "day_change_pct": 0.0, "high": 43.0, "low": 41.0},
    ), patch(
        "trading_pulse.agent.price_watch._quick_score_line",
        return_value="",
    ):
        text = format_price_watch_update(cfg, "FLAT", include_score=False)
    assert text is not None
    assert "+0.00%" in text
    assert "$42.00" in text


def test_format_price_watch_handles_none_day_change():
    from trading_pulse.agent.price_watch import format_price_watch_update

    cfg = SimpleNamespace(intraday_check_interval_minutes=60)
    with patch(
        "trading_pulse.agent.price_watch.fetch_intraday_quote",
        return_value={"last": 10.0, "day_change_pct": None, "high": 10.0, "low": 10.0},
    ), patch(
        "trading_pulse.agent.price_watch._quick_score_line",
        return_value="",
    ):
        text = format_price_watch_update(
            cfg,
            "M2",
            include_score=False,
            watch_meta={"entry_ref": 11.0, "side": "LONG"},
        )
    assert text is not None
    assert "+0.00%" in text
    assert "חסר" in text


def test_format_price_watch_falls_back_to_change_pct():
    from trading_pulse.agent.price_watch import format_price_watch_update

    cfg = SimpleNamespace(intraday_check_interval_minutes=60)
    with patch(
        "trading_pulse.agent.price_watch.fetch_intraday_quote",
        return_value={"last": 50.0, "change_pct": -1.25, "high": 51.0, "low": 49.0},
    ), patch(
        "trading_pulse.agent.price_watch._quick_score_line",
        return_value="",
    ):
        text = format_price_watch_update(cfg, "FALLBACK", include_score=False)
    assert text is not None
    assert "-1.25%" in text
    assert "$50.00" in text

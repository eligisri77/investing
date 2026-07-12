"""Tests for Japanese candlestick plan charts."""

from __future__ import annotations

from unittest.mock import patch

from trading_pulse.telegram.telegram_images import render_japanese_candlestick_chart, render_recommendation_chart


def _fake_bars(n: int = 30):
    bars = []
    price = 100.0
    for i in range(n):
        o = price
        c = price + (1.2 if i % 2 == 0 else -0.8)
        h = max(o, c) + 0.5
        l = min(o, c) - 0.5
        bars.append(
            {
                "date": f"2026-06-{i+1:02d}" if i < 28 else f"2026-07-{i-27:02d}",
                "open": o,
                "high": h,
                "low": l,
                "close": c,
            }
        )
        price = c
    return bars


def test_render_rising_three_candlestick():
    rec = {
        "symbol": "TEST",
        "strategy": "rising_three_methods",
        "entry_ref_price": 110.0,
        "stop_loss_price": 100.0,
        "take_profit_price": 130.0,
        "pattern_weak": False,
    }
    with patch(
        "trading_pulse.telegram.telegram_images._fetch_recent_ohlc",
        return_value=_fake_bars(),
    ):
        png = render_japanese_candlestick_chart(rec, 4, "2026-07-14")
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_method2_candlestick_dispatches():
    rec = {
        "symbol": "M2",
        "strategy": "method2",
        "trigger": "2-1-2",
        "entry_ref_price": 50.0,
        "method2_entry_ref": 50.1,
        "method2_stop_ref": 49.5,
        "stop_loss_price": 49.5,
        "take_profit_price": 55.0,
    }
    with patch(
        "trading_pulse.telegram.telegram_images._fetch_recent_ohlc",
        return_value=_fake_bars(),
    ):
        png = render_recommendation_chart(rec, 5, "2026-07-14")
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

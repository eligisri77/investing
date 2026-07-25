"""Tests for strategy labels on portfolio / holdings displays."""

from __future__ import annotations

from trading_pulse.agent.strategy_labels import (
    is_candle_strategy,
    strategy_label,
    strategy_method_line,
    strategy_suffix_html,
    strategy_suffix_plain,
)
from trading_pulse.telegram.telegram_format import format_current_holdings, format_portfolio


def test_method2_label_is_chinese_candles_2():
    obj = {"strategy": "method2", "trigger": "3-2-2", "side": "LONG"}
    label = strategy_label(obj)
    assert label.startswith("נרות סיניים 2")
    assert "3-2-2" in label
    assert "שיטה 2" not in label
    assert strategy_method_line(obj) == "שיטת כניסה · " + label


def test_rising_three_label():
    assert "Rising Three" in strategy_label({"strategy": "rising_three_methods"})
    assert is_candle_strategy({"strategy": "method2"})
    assert not is_candle_strategy({"strategy": "score"})


def test_experimental_strategy_label_is_explicit():
    label = strategy_label({"strategy_id": "trend_pullback"})
    assert "תיקון במגמה" in label
    assert "ניסיוני" in label


def test_relative_strength_label_avoids_spy_inside_rtl():
    label = strategy_label({"strategy_id": "relative_strength"})
    assert "חוזק יחסי" in label
    assert "ניסיוני" in label
    assert "SPY" not in label


def test_strategy_method_line_prefixes_entry_method():
    assert strategy_method_line({"strategy": "score_momentum"}) == "שיטת כניסה · מומנטום וציון"
    assert strategy_method_line({"strategy_id": "relative_strength"}).startswith("שיטת כניסה ·")
    assert strategy_method_line({"strategy": "rising_three"}) == "שיטת כניסה · נרות Rising Three"
    assert strategy_method_line({"strategy_id": "vcp_breakout"}).startswith("שיטת כניסה ·")
    assert strategy_method_line({"strategy_id": "trend_pullback"}).startswith("שיטת כניסה ·")


def test_strategy_method_line_empty_when_unknown():
    assert strategy_method_line(None) == ""
    assert strategy_method_line({}) == ""
    assert strategy_method_line({"strategy": "unknown_xyz"}) == ""


def test_strategy_suffix_has_no_ascii_parentheses():
    html = strategy_suffix_html({"strategy": "score_momentum"})
    assert "(" not in html and ")" not in html
    assert "מומנטום וציון" in html
    assert "שיטת כניסה" in html
    assert "·" in html


def test_strategy_suffix_plain_uses_method_line():
    assert strategy_suffix_plain({"strategy": "score"}) == " · שיטת כניסה · מומנטום וציון"
    assert strategy_suffix_plain(None) == ""
    m2 = strategy_suffix_plain({"strategy": "method2", "trigger": "3-2-2"})
    assert m2.startswith(" · שיטת כניסה · נרות סיניים 2")
    assert "שיטה 2" not in m2


def test_rising_three_weak_uses_middot_not_parens():
    label = strategy_label({"strategy": "rising_three_methods", "pattern_weak": True})
    assert "חלש" in label
    assert "(" not in label


def test_holdings_and_portfolio_show_strategy_tag():
    holdings = [
        {
            "symbol": "MPC",
            "capital_usd": 120,
            "entry_price": 300,
            "days_held": 1,
            "strategy": "method2",
            "trigger": "3-2-2",
        }
    ]
    text = "\n".join(format_current_holdings(holdings))
    assert "MPC" in text
    assert "נרות סיניים 2" in text
    assert "שיטת כניסה" in text
    assert "שיטה 2" not in text

    data = {
        "equity": 1000,
        "cash_usd": 0,
        "open_marked_usd": 120,
        "unrealized_pnl_usd": 0,
        "total_realized_pnl": 0,
        "open_positions": [
            {
                "symbol": "MPC",
                "status": "holding",
                "capital_usd": 120,
                "entry_price": 300,
                "marked_value_usd": 120,
                "unrealized_pnl_usd": 0,
                "entry_at": "2026-07-14T13:35:00+00:00",
                "strategy": "method2",
                "trigger": "3-2-2",
                "slot": 1,
            }
        ],
        "by_symbol": [],
    }
    port = format_portfolio(data)
    assert "נרות סיניים 2" in port
    assert "שיטת כניסה" in strategy_suffix_html({"strategy": "method2"})
    assert "(" not in strategy_suffix_html({"strategy": "method2"})

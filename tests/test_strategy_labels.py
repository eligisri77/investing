"""Tests for strategy labels on portfolio / holdings displays."""

from __future__ import annotations

from trading_pulse.agent.strategy_labels import (
    is_candle_strategy,
    strategy_label,
    strategy_suffix_html,
)
from trading_pulse.telegram.telegram_format import format_current_holdings, format_portfolio


def test_method2_label_includes_chinese_candles():
    label = strategy_label({"strategy": "method2", "trigger": "3-2-2", "side": "LONG"})
    assert "שיטה 2" in label
    assert "נרות סיניים" in label
    assert "3-2-2" in label


def test_rising_three_label():
    assert "Rising Three" in strategy_label({"strategy": "rising_three_methods"})
    assert is_candle_strategy({"strategy": "method2"})
    assert not is_candle_strategy({"strategy": "score"})


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
    assert "שיטה 2" in text
    assert "נרות סיניים" in text

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
    assert "נרות סיניים" in port
    assert strategy_suffix_html({"strategy": "method2"}) 

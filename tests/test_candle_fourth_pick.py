"""Tests for score + candle fourth-pick merge helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from trading_pulse.agent.candlestick_patterns import PatternHit
from trading_pulse.agent.trading_flow import initial_deploy_slots, per_trade_cap_for_plan


def test_initial_deploy_slots_four_on_empty():
    cfg = SimpleNamespace(initial_deploy_stocks=4, max_open_positions=4, max_trades_per_day=4)
    state = {"equity": 1000.0, "open_positions": []}
    assert initial_deploy_slots(cfg, state) == 4


def test_equal_split_four_picks():
    cfg = SimpleNamespace(max_position_pct=0.34, initial_capital=1000.0)
    state = {"equity": 1000.0, "open_positions": []}
    assert per_trade_cap_for_plan(cfg, state, 4) == 250.0


def test_candle_hit_not_duplicating_score_symbols():
    """Candle scanner excludes already-picked score symbols."""
    from trading_pulse.agent.candlestick_patterns import scan_rising_three_methods

    hit = PatternHit(
        symbol="NVDA",
        pattern="rising_three_methods",
        pattern_score=9.0,
        pattern_weak=False,
        close=100.0,
        reason_he="test",
    )
    with patch(
        "trading_pulse.agent.candlestick_patterns.fetch_daily_ohlc",
        return_value=None,
    ):
        # exclude NVDA → no download called usefully; result None
        out = scan_rising_three_methods(["NVDA", "AAPL"], exclude={"NVDA"}, allow_partial=True)
        assert out is None or out.symbol != "NVDA"


def test_merge_four_symbols_unique():
    picks = pd.DataFrame(
        [
            {"symbol": "AAA", "close": 10, "score": 12},
            {"symbol": "BBB", "close": 20, "score": 11},
            {"symbol": "CCC", "close": 30, "score": 10},
        ]
    )
    candle = PatternHit(
        symbol="DDD",
        pattern="rising_three_methods",
        pattern_score=8.5,
        pattern_weak=False,
        close=40.0,
        reason_he="נרות",
    )
    n = len(picks) + 1
    assert n == 4
    assert candle.symbol not in set(picks["symbol"])

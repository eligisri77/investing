"""Purchase lots: separate cost bases for add-on buys and FIFO sells."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import trading_pulse.agent.dryrun_agent as agent
from trading_pulse.agent.dryrun_agent import AgentConfig
from trading_pulse.agent.positions import (
    add_lot_to_position,
    ensure_position_lots,
    new_position_from_rec,
    partial_sell_position,
    sync_position_from_lots,
    trade_from_close,
    unrealized_pnl_for_position,
)


def test_legacy_position_migrates_to_one_lot():
    pos = {"symbol": "ILMN", "entry_price": 192.04, "capital_usd": 87.0, "entry_day": "2026-07-27"}
    lots = ensure_position_lots(pos)
    assert len(lots) == 1
    assert lots[0]["capital_usd"] == 87.0
    assert lots[0]["entry_price"] == 192.04
    assert pos["capital_usd"] == 87.0


def test_add_lot_keeps_separate_entries_and_weighted_display():
    pos = new_position_from_rec(
        {"symbol": "X", "capital_usd": 100},
        100.0,
        "2026-07-27",
    )
    add_lot_to_position(pos, 200.0, 105.0, "2026-07-28")
    assert len(pos["lots"]) == 2
    assert pos["capital_usd"] == 300.0
    # Display entry = weighted average
    assert pos["entry_price"] == round((100 * 100 + 200 * 105) / 300, 4)


def test_unrealized_pnl_sums_lots_like_user_example():
    """$100 @100 then +5%, buy $200 @105, then +10% → $115.5 + $220."""
    pos = {
        "symbol": "DEMO",
        "side": "LONG",
        "lots": [
            {"id": "a", "capital_usd": 100.0, "entry_price": 100.0, "entry_day": "2026-07-01"},
            {"id": "b", "capital_usd": 200.0, "entry_price": 105.0, "entry_day": "2026-07-02"},
        ],
    }
    sync_position_from_lots(pos)
    # After +5% then +10% from original: mark = 100 * 1.05 * 1.10 = 115.5
    row = unrealized_pnl_for_position(pos, mark_price=115.5)
    assert row["unrealized_pnl_usd"] == 35.5  # 15.5 + 20
    assert row["lots"][0]["unrealized_pnl_usd"] == 15.5
    assert row["lots"][1]["unrealized_pnl_usd"] == 20.0


def test_trade_from_close_sums_lot_pnl():
    pos = {
        "symbol": "DEMO",
        "side": "LONG",
        "days_held": 2,
        "lots": [
            {"capital_usd": 100.0, "entry_price": 100.0, "entry_day": "2026-07-01"},
            {"capital_usd": 200.0, "entry_price": 105.0, "entry_day": "2026-07-02"},
        ],
    }
    sync_position_from_lots(pos)
    trade = trade_from_close(pos, 115.5, "user_sell")
    assert trade["pnl_usd"] == 35.5
    assert trade["capital_usd"] == 300.0
    assert trade["lots_closed"] == 2


def test_partial_sell_fifo_consumes_oldest_lot_first():
    class Cfg:
        commission_per_side_usd = 0.0

    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "FIFO",
                "side": "LONG",
                "capital_usd": 300.0,
                "entry_price": 100.0,
                "entry_day": "2026-07-01",
                "lots": [
                    {
                        "id": "old",
                        "capital_usd": 100.0,
                        "entry_price": 100.0,
                        "entry_day": "2026-07-01",
                    },
                    {
                        "id": "new",
                        "capital_usd": 200.0,
                        "entry_price": 110.0,
                        "entry_day": "2026-07-02",
                    },
                ],
            }
        ],
    }
    with patch(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        return_value={"open": 120, "high": 120, "low": 120, "close": 120},
    ):
        # Sell $100 → only oldest lot (entry 100) → pnl = 20
        trade = partial_sell_position(Cfg(), state, "FIFO", 100 / 300, trading_day=date(2026, 7, 3))
    assert trade is not None
    assert trade["pnl_usd"] == 20.0
    assert trade["capital_usd"] == 100.0
    pos = state["open_positions"][0]
    assert pos["capital_usd"] == 200.0
    assert len(pos["lots"]) == 1
    assert pos["lots"][0]["entry_price"] == 110.0


def test_partial_sell_fifo_splits_oldest_lot_midway():
    """Sell more than the oldest lot but less than all — trim first lot, keep rest."""

    class Cfg:
        commission_per_side_usd = 0.0

    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "SPLIT",
                "side": "LONG",
                "capital_usd": 300.0,
                "entry_price": 100.0,
                "entry_day": "2026-07-01",
                "lots": [
                    {
                        "id": "old",
                        "capital_usd": 100.0,
                        "entry_price": 100.0,
                        "entry_day": "2026-07-01",
                    },
                    {
                        "id": "new",
                        "capital_usd": 200.0,
                        "entry_price": 110.0,
                        "entry_day": "2026-07-02",
                    },
                ],
            }
        ],
    }
    with patch(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        return_value={"open": 120, "high": 120, "low": 120, "close": 120},
    ):
        # Sell $150 → all of old ($100 @100 → +20) + $50 of new (@110 → +~4.55)
        trade = partial_sell_position(Cfg(), state, "SPLIT", 150 / 300, trading_day=date(2026, 7, 3))
    assert trade is not None
    assert trade["capital_usd"] == 150.0
    assert trade["pnl_usd"] == round(100 * 0.20 + 50 * (120 / 110 - 1), 2)
    pos = state["open_positions"][0]
    assert pos["capital_usd"] == 150.0
    assert len(pos["lots"]) == 1
    assert pos["lots"][0]["id"] == "new"
    assert pos["lots"][0]["capital_usd"] == 150.0
    assert pos["lots"][0]["entry_price"] == 110.0


def test_buy_symbol_usd_adds_lot_at_ohlc_fill_price():
    """Adding to an existing symbol appends a lot at live day close (not prior entry)."""
    cfg = AgentConfig(commission_per_side_usd=0.0)
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "ADD",
                "side": "LONG",
                "capital_usd": 100.0,
                "entry_price": 50.0,
                "entry_day": "2026-07-20",
                "lots": [
                    {
                        "id": "first",
                        "capital_usd": 100.0,
                        "entry_price": 50.0,
                        "entry_day": "2026-07-20",
                    }
                ],
            }
        ],
    }
    with patch(
        "trading_pulse.agent.positions.fetch_day_ohlc",
        return_value={"open": 55, "high": 56, "low": 54, "close": 55.25},
    ):
        pos = agent._buy_symbol_usd(cfg, state, "ADD", 200.0, date(2026, 7, 28))
    assert pos is not None
    assert len(pos["lots"]) == 2
    assert pos["lots"][0]["entry_price"] == 50.0
    assert pos["lots"][1]["capital_usd"] == 200.0
    assert pos["lots"][1]["entry_price"] == 55.25
    assert pos["lots"][1]["entry_day"] == "2026-07-28"
    assert pos["capital_usd"] == 300.0
    # Weighted display entry: (100*50 + 200*55.25) / 300
    assert pos["entry_price"] == round((100 * 50 + 200 * 55.25) / 300, 4)
    assert pos["entry_day"] == "2026-07-20"  # oldest lot still defines age


def test_buy_symbol_usd_falls_back_to_intraday_quote():
    cfg = AgentConfig(commission_per_side_usd=0.0)
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "Q",
                "side": "LONG",
                "capital_usd": 100.0,
                "entry_price": 10.0,
                "entry_day": "2026-07-20",
            }
        ],
    }
    with (
        patch("trading_pulse.agent.positions.fetch_day_ohlc", return_value=None),
        patch(
            "trading_pulse.agent.intraday_monitor.fetch_intraday_quote",
            return_value={"last": 12.5},
        ),
    ):
        pos = agent._buy_symbol_usd(cfg, state, "Q", 50.0, date(2026, 7, 28))
    assert pos is not None
    assert len(pos["lots"]) == 2
    assert pos["lots"][1]["entry_price"] == 12.5
    assert pos["capital_usd"] == 150.0


def test_buy_symbol_usd_returns_none_when_no_fill_price():
    cfg = AgentConfig(commission_per_side_usd=0.0)
    state = {
        "equity": 1000.0,
        "open_positions": [
            {
                "symbol": "NOPRICE",
                "side": "LONG",
                "capital_usd": 100.0,
                "entry_price": 10.0,
                "entry_day": "2026-07-20",
            }
        ],
    }
    with (
        patch("trading_pulse.agent.positions.fetch_day_ohlc", return_value=None),
        patch(
            "trading_pulse.agent.intraday_monitor.fetch_intraday_quote",
            return_value=None,
        ),
    ):
        pos = agent._buy_symbol_usd(cfg, state, "NOPRICE", 50.0, date(2026, 7, 28))
    assert pos is None
    assert len(state["open_positions"][0].get("lots") or []) <= 1
    assert float(state["open_positions"][0]["capital_usd"]) == 100.0


def test_add_lot_rejects_tiny_or_zero_price():
    pos = new_position_from_rec(
        {"symbol": "X", "capital_usd": 100},
        100.0,
        "2026-07-27",
    )
    add_lot_to_position(pos, 0.5, 105.0, "2026-07-28")
    add_lot_to_position(pos, 50.0, 0.0, "2026-07-28")
    assert len(pos["lots"]) == 1
    assert pos["capital_usd"] == 100.0

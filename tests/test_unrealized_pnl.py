"""Tests for unrealized (future) P/L on open positions."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from trading_pulse.agent.positions import enrich_held_unrealized, unrealized_pnl_for_position


def test_unrealized_pnl_for_position_with_mark():
    pos = {"symbol": "LABU", "entry_price": 287.59, "capital_usd": 1000.0, "days_held": 0}
    row = unrealized_pnl_for_position(pos, mark_price=303.45)
    assert row["unrealized_pnl_usd"] == 55.15
    assert row["unrealized_pnl_pct"] == 5.51
    assert row["mark_price"] == 303.45


def test_enrich_held_unrealized_total():
    held = [{"symbol": "LABU", "entry_price": 100.0, "capital_usd": 500.0, "days_held": 1}]
    with patch("trading_pulse.agent.positions.fetch_day_ohlc", return_value={"close": 110.0}):
        enriched, total = enrich_held_unrealized(held, date(2026, 7, 2))
    assert len(enriched) == 1
    assert enriched[0]["unrealized_pnl_usd"] == 50.0
    assert total == 50.0

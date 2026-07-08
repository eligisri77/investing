"""Tests for the evening holdings decision report."""

from __future__ import annotations

from dataclasses import dataclass

from trading_pulse.agent.holdings_review import review_holding, review_holdings


@dataclass
class FakeCfg:
    max_hold_days: int = 5
    stop_loss_pct: float = 0.12
    take_profit_pct: float = 0.25


def _holding(symbol, entry, floor, days=1):
    return {"symbol": symbol, "entry_price": entry, "floor_price": floor, "days_held": days}


def test_hold_when_healthy():
    cfg = FakeCfg()
    h = _holding("HOOD", 100.0, 88.0, days=1)
    scores = {"HOOD": {"score": 7.5, "close": 105.0}}
    r = review_holding(h, cfg, scores, [])
    assert r.verdict == "hold"
    assert round(r.pnl_pct) == 5


def test_sell_when_near_floor():
    cfg = FakeCfg()
    h = _holding("SOXL", 197.0, 159.0, days=1)
    scores = {"SOXL": {"score": 4.0, "close": 162.0}}  # ~1.9% above floor
    r = review_holding(h, cfg, scores, [])
    assert r.verdict == "sell"


def test_take_profit_when_up_big():
    cfg = FakeCfg()
    h = _holding("MSTR", 100.0, 88.0, days=2)
    scores = {"MSTR": {"score": 8.0, "close": 125.0}}  # +25%
    r = review_holding(h, cfg, scores, [])
    assert r.verdict == "take_profit"


def test_sell_when_max_hold_days_reached():
    cfg = FakeCfg(max_hold_days=5)
    h = _holding("AMD", 100.0, 88.0, days=4)
    scores = {"AMD": {"score": 7.0, "close": 103.0}}
    r = review_holding(h, cfg, scores, [])
    assert r.verdict == "sell"


def test_swap_when_better_pick_tomorrow():
    cfg = FakeCfg()
    h = _holding("AMD", 100.0, 88.0, days=1)
    scores = {"AMD": {"score": 6.0, "close": 102.0}}
    recs = [{"symbol": "NVDA", "score": 9.0}]
    r = review_holding(h, cfg, scores, recs)
    assert r.verdict == "swap"
    assert r.swap_to == "NVDA"


def test_no_swap_out_of_strong_winner():
    cfg = FakeCfg()
    h = _holding("AMD", 100.0, 88.0, days=1)
    scores = {"AMD": {"score": 6.0, "close": 115.0}}  # +15% winner
    recs = [{"symbol": "NVDA", "score": 9.0}]
    r = review_holding(h, cfg, scores, recs)
    assert r.verdict == "hold"


def test_hold_when_no_price_data():
    cfg = FakeCfg()
    h = _holding("XYZ", 50.0, 44.0, days=1)
    r = review_holding(h, cfg, {}, [])
    assert r.verdict == "hold"


def test_review_holdings_batch_and_serialize():
    cfg = FakeCfg()
    holdings = [_holding("HOOD", 100.0, 88.0), _holding("SOXL", 197.0, 159.0)]
    scores = {"HOOD": {"score": 7.5, "close": 105.0}, "SOXL": {"score": 4.0, "close": 161.0}}
    reviews = review_holdings(holdings, cfg, scores, [])
    assert len(reviews) == 2
    d = reviews[0].to_dict()
    assert set(d) >= {"symbol", "verdict", "pnl_pct", "reason"}

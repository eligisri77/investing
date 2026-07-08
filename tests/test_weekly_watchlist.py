"""Tests for the weekly watchlist funnel selection logic."""

from __future__ import annotations

from datetime import date

from trading_pulse.agent.weekly_watchlist import rank_candidates, week_key


def test_week_key_format():
    assert week_key(date(2026, 7, 7)) == "2026-W28"


def test_rank_prefers_high_score():
    rows = [
        {"symbol": "AAA", "score": 9.0, "atr_pct": 5.0, "vol_ratio": 1.5},
        {"symbol": "BBB", "score": 3.0, "atr_pct": 5.0, "vol_ratio": 1.5},
    ]
    ranked = rank_candidates(rows, target_size=2)
    assert ranked[0]["symbol"] == "AAA"


def test_rank_limits_to_target_size():
    rows = [
        {"symbol": f"S{i}", "score": float(i), "atr_pct": 4.0, "vol_ratio": 1.0}
        for i in range(10)
    ]
    ranked = rank_candidates(rows, target_size=3)
    assert len(ranked) == 3
    # highest scores kept
    assert {r["symbol"] for r in ranked} == {"S9", "S8", "S7"}


def test_rank_blends_volatility_and_volume():
    # Same score; higher ATR + volume should win.
    rows = [
        {"symbol": "CALM", "score": 7.0, "atr_pct": 2.0, "vol_ratio": 0.5},
        {"symbol": "WILD", "score": 7.0, "atr_pct": 12.0, "vol_ratio": 2.5},
    ]
    ranked = rank_candidates(rows, target_size=2)
    assert ranked[0]["symbol"] == "WILD"


def test_rank_handles_empty():
    assert rank_candidates([], target_size=5) == []


def test_rank_serializes_expected_keys():
    rows = [{"symbol": "AAA", "score": 8.0, "atr_pct": 6.0, "vol_ratio": 1.2}]
    ranked = rank_candidates(rows, target_size=1)
    assert set(ranked[0]) == {"symbol", "score", "atr_pct", "vol_ratio", "composite"}


def test_source_universe_is_deduped_and_nonempty():
    from trading_pulse.agent.universe import SOURCE_UNIVERSE

    assert len(SOURCE_UNIVERSE) > 100
    assert len(SOURCE_UNIVERSE) == len(set(SOURCE_UNIVERSE))

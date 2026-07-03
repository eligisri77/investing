"""Tests for symbol cooldown and quality filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from trading_pulse.agent.symbol_cooldown import (
    filter_candidates_dataframe,
    is_symbol_in_cooldown,
    maybe_record_loss_cooldown,
    record_symbol_cooldown,
)


@dataclass
class FakeCfg:
    min_entry_score: float = 10.0
    symbol_cooldown_days_after_loss: int = 5
    max_leveraged_etf_positions: int = 1


def test_loss_trade_sets_cooldown():
    state: dict = {}
    cfg = FakeCfg()
    maybe_record_loss_cooldown(
        state,
        {"symbol": "SOXL", "pnl_usd": -40.0, "exit_reason": "floor_price"},
        cfg,
        as_of=date(2026, 7, 1),
    )
    assert is_symbol_in_cooldown(state, "SOXL", as_of=date(2026, 7, 3))
    assert not is_symbol_in_cooldown(state, "SOXL", as_of=date(2026, 7, 7))


def test_filter_removes_cooldown_symbol():
    state = {}
    record_symbol_cooldown(state, "SOXL", days=5, as_of=date(2026, 7, 1))
    df = pd.DataFrame(
        [
            {"symbol": "SOXL", "score": 15.0},
            {"symbol": "NVDA", "score": 12.0},
        ]
    )
    out = filter_candidates_dataframe(df, state, FakeCfg(), as_of=date(2026, 7, 2))
    assert list(out["symbol"]) == ["NVDA"]


def test_filter_min_entry_score():
    state = {}
    df = pd.DataFrame([{"symbol": "AMD", "score": 8.0}, {"symbol": "NVDA", "score": 11.0}])
    out = filter_candidates_dataframe(df, state, FakeCfg(), as_of=date(2026, 7, 1))
    assert list(out["symbol"]) == ["NVDA"]


def test_leveraged_etf_cap_one_per_plan():
    state = {}
    cfg = FakeCfg()
    df = pd.DataFrame(
        [
            {"symbol": "SOXL", "score": 14.0},
            {"symbol": "LABU", "score": 13.0},
            {"symbol": "NVDA", "score": 12.0},
        ]
    )
    out = filter_candidates_dataframe(df, state, cfg, held_symbols=set(), as_of=date(2026, 7, 1))
    lev = [s for s in out["symbol"] if s in {"SOXL", "LABU", "TQQQ"}]
    assert len(lev) == 1
    assert lev[0] == "SOXL"

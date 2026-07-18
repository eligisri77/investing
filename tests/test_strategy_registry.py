from __future__ import annotations

from types import SimpleNamespace

import pytest

from trading_pulse.agent.strategies.combiner import (
    allocate_combined_capital,
    combine_recommendations,
)
from trading_pulse.agent.strategies.registry import (
    annotate_recommendation,
    enabled_strategy_ids,
)


def test_balanced_mode_enables_existing_three_strategies():
    cfg = SimpleNamespace(
        strategy_mode="balanced_mix",
        trend_pullback_enabled=False,
        vcp_breakout_enabled=False,
        relative_strength_enabled=False,
    )
    assert enabled_strategy_ids(cfg) == (
        "score_momentum",
        "rising_three",
        "method2",
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("score_only", ("score_momentum",)),
        ("rising_three_only", ("rising_three",)),
        ("method2_only", ("method2",)),
        ("not-a-mode", ("score_momentum", "rising_three", "method2")),
    ],
)
def test_strategy_mode_presets_and_unknown_fallback(mode, expected):
    cfg = SimpleNamespace(strategy_mode=mode, trend_pullback_enabled=False)
    assert enabled_strategy_ids(cfg) == expected


def test_experimental_strategy_is_only_appended_when_enabled():
    cfg = SimpleNamespace(strategy_mode="score_only", trend_pullback_enabled=True)
    assert enabled_strategy_ids(cfg) == ("score_momentum", "trend_pullback")


@pytest.mark.parametrize(
    ("flag", "strategy_id"),
    [
        ("vcp_breakout_enabled", "vcp_breakout"),
        ("relative_strength_enabled", "relative_strength"),
    ],
)
def test_new_experimental_strategies_are_default_off_and_individually_enabled(
    flag,
    strategy_id,
):
    cfg = SimpleNamespace(strategy_mode="score_only")
    assert enabled_strategy_ids(cfg) == ("score_momentum",)

    setattr(cfg, flag, True)
    assert enabled_strategy_ids(cfg) == ("score_momentum", strategy_id)


def test_legacy_recommendation_gets_versioned_attribution():
    rec = annotate_recommendation(
        {"symbol": "NVDA", "strategy": "score", "score": 8.4}
    )
    assert rec["strategy_id"] == "score_momentum"
    assert rec["strategy_version"] == "1.0"
    assert rec["schema_version"] == 2
    assert rec["contributing_strategies"] == ["score_momentum"]
    assert 0 < rec["confidence"] <= 1


def test_combiner_merges_duplicate_symbol_and_rewards_confluence():
    rows = [
        {"symbol": "NVDA", "strategy": "score", "score": 8.0},
        {
            "symbol": "NVDA",
            "strategy": "rising_three_methods",
            "score": 7.5,
            "reason": "pattern",
        },
    ]
    out = combine_recommendations(rows, max_picks=4)
    assert len(out) == 1
    assert out[0]["confluence_count"] == 2
    assert set(out[0]["contributing_strategies"]) == {
        "score_momentum",
        "rising_three",
    }
    assert "הסכמה בין 2 אסטרטגיות" in out[0]["reason"]


def test_combiner_normalizes_symbols_and_prefers_strategy_priority():
    rows = [
        {
            "symbol": "nvda",
            "strategy": "score",
            "score": 12,
            "reason": "score",
        },
        {
            "symbol": "NVDA",
            "strategy": "method2",
            "score": 4,
            "reason": "breakout",
        },
        {"symbol": "", "strategy": "score", "score": 99},
    ]
    out = combine_recommendations(rows, max_picks=1)
    assert len(out) == 1
    assert out[0]["symbol"] == "NVDA"
    assert out[0]["strategy_id"] == "method2"
    assert out[0]["confluence_count"] == 2


def test_combiner_does_not_reward_duplicate_same_strategy():
    rows = [
        {"symbol": "AMD", "strategy": "score", "score": 6},
        {"symbol": "AMD", "strategy": "score", "score": 9},
    ]
    out = combine_recommendations(rows, max_picks=2)
    assert out[0]["contributing_strategies"] == ["score_momentum"]
    assert out[0]["confluence_count"] == 1
    assert "הסכמה בין" not in str(out[0].get("reason") or "")


def test_combiner_non_positive_cap_returns_no_picks():
    assert combine_recommendations(
        [{"symbol": "AMD", "strategy": "score", "score": 9}],
        max_picks=0,
    ) == []


def test_combined_allocation_preserves_method2_risk_sleeve():
    rows = [
        {"symbol": "A", "strategy_id": "score_momentum", "capital_usd": 0},
        {"symbol": "B", "strategy_id": "score_momentum", "capital_usd": 0},
        {
            "symbol": "M2",
            "strategy_id": "method2",
            "capital_usd": 100,
            "sleeve": True,
        },
    ]
    allocate_combined_capital(rows, deployable=1000)
    assert rows[2]["capital_usd"] == 100
    assert rows[0]["capital_usd"] == rows[1]["capital_usd"] == 450


def test_combined_allocation_handles_only_sleeves_and_zero_cash():
    sleeves = [
        {
            "symbol": "M2",
            "strategy_id": "method2",
            "capital_usd": 75,
            "sleeve": True,
        }
    ]
    allocate_combined_capital(sleeves, deployable=500)
    assert sleeves[0]["capital_usd"] == 75

    mains = [{"symbol": "A", "strategy_id": "score_momentum", "capital_usd": 10}]
    allocate_combined_capital(mains, deployable=0)
    assert mains[0]["capital_usd"] == 0


def test_combined_allocation_caps_sleeve_at_deployable_cash():
    rows = [
        {
            "symbol": "M2",
            "strategy_id": "method2",
            "capital_usd": 600,
            "sleeve": True,
        },
        {"symbol": "A", "strategy_id": "score_momentum", "capital_usd": 0},
    ]

    allocate_combined_capital(rows, deployable=250)

    assert rows[0]["capital_usd"] == 250
    assert rows[1]["capital_usd"] == 0
    assert sum(float(row["capital_usd"]) for row in rows) == 250

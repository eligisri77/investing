from __future__ import annotations

from trading_pulse.agent.strategies.shadow import (
    reconcile_shadow_with_state,
    record_shadow_plan,
    strategy_performance,
)


def test_shadow_records_each_contributing_strategy_once(tmp_path):
    path = tmp_path / "shadow.json"
    plan = {
        "for_trading_day": "2026-07-20",
        "recommendations": [
            {
                "symbol": "NVDA",
                "strategy_id": "rising_three",
                "strategy_version": "1.0",
                "contributing_strategies": ["score_momentum", "rising_three"],
                "entry_ref_price": 100,
                "stop_loss_price": 90,
                "take_profit_price": 120,
                "score": 8,
            }
        ],
    }
    assert record_shadow_plan(plan, path=path) == 2
    assert record_shadow_plan(plan, path=path) == 0
    out = strategy_performance(path=path)
    assert out["total_signals"] == 2
    assert {row["strategy_id"] for row in out["strategies"]} == {
        "score_momentum",
        "rising_three",
    }


def test_shadow_reconciles_closed_trade_and_summarizes(tmp_path):
    path = tmp_path / "shadow.json"
    record_shadow_plan(
        {
            "for_trading_day": "2026-07-20",
            "recommendations": [
                {
                    "symbol": "NVDA",
                    "strategy_id": "score_momentum",
                    "entry_ref_price": 100,
                }
            ],
        },
        path=path,
    )
    state = {
        "history": [
            {
                "trading_day": "2026-07-22",
                "executed": [
                    {
                        "symbol": "NVDA",
                        "entry_day": "2026-07-20",
                        "pnl_usd": 25,
                        "pnl_pct": 2.5,
                        "exit_reason": "take_profit",
                    }
                ],
            }
        ]
    }
    out = strategy_performance(state, path=path)
    row = out["strategies"][0]
    assert row["closed_trades"] == 1
    assert row["wins"] == 1
    assert row["pnl_usd"] == 25


def test_shadow_skips_records_without_day_or_symbol(tmp_path):
    path = tmp_path / "shadow.json"
    assert record_shadow_plan(
        {
            "recommendations": [
                {"symbol": "AMD", "strategy_id": "score_momentum"},
                {"symbol": "", "strategy_id": "method2"},
            ]
        },
        path=path,
    ) == 0
    assert strategy_performance(path=path)["total_signals"] == 0


def test_shadow_recovers_from_malformed_ledger(tmp_path):
    path = tmp_path / "shadow.json"
    path.write_text("{not-json", encoding="utf-8")

    added = record_shadow_plan(
        {
            "for_trading_day": "2026-07-20",
            "recommendations": [
                {"symbol": "amd", "strategy_id": "score_momentum"}
            ],
        },
        path=path,
    )

    assert added == 1
    out = strategy_performance(path=path)
    assert out["total_signals"] == 1
    assert out["strategies"][0]["open_signals"] == 1


def test_shadow_does_not_match_trade_entered_before_signal(tmp_path):
    path = tmp_path / "shadow.json"
    record_shadow_plan(
        {
            "for_trading_day": "2026-07-20",
            "recommendations": [
                {"symbol": "NVDA", "strategy_id": "score_momentum"}
            ],
        },
        path=path,
    )
    state = {
        "history": [
            {
                "trading_day": "2026-07-19",
                "executed": [
                    {
                        "symbol": "NVDA",
                        "entry_day": "2026-07-18",
                        "pnl_usd": -10,
                        "pnl_pct": -1,
                    }
                ],
            }
        ]
    }

    assert reconcile_shadow_with_state(state, path=path) == 0
    row = strategy_performance(path=path)["strategies"][0]
    assert row["closed_trades"] == 0
    assert row["open_signals"] == 1


def test_shadow_does_not_match_later_unrelated_entry(tmp_path):
    path = tmp_path / "shadow.json"
    record_shadow_plan(
        {
            "for_trading_day": "2026-07-20",
            "recommendations": [
                {"symbol": "NVDA", "strategy_id": "score_momentum"}
            ],
        },
        path=path,
    )
    state = {
        "history": [
            {
                "trading_day": "2026-07-25",
                "executed": [
                    {
                        "symbol": "NVDA",
                        "entry_day": "2026-07-24",
                        "strategy_id": "trend_pullback",
                        "contributing_strategies": ["trend_pullback"],
                        "pnl_usd": 12,
                        "pnl_pct": 1.2,
                    }
                ],
            }
        ]
    }

    assert reconcile_shadow_with_state(state, path=path) == 0
    row = strategy_performance(path=path)["strategies"][0]
    assert row["closed_trades"] == 0

from __future__ import annotations

import pandas as pd

from trading_pulse.agent.strategy_backtest import walk_forward_portfolio


def _frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["Open", "High", "Low", "Close"],
        index=pd.date_range("2026-01-01", periods=len(rows), freq="D"),
    )


def test_walk_forward_enters_next_day_without_lookahead():
    frame = _frame(
        [
            (100, 101, 99, 100),
            (110, 112, 109, 111),
            (111, 113, 110, 112),
        ]
    )
    seen_lengths: list[int] = []

    def signal(symbol, history):
        seen_lengths.append(len(history))
        return {"score": 9, "strategy_id": "score_momentum"} if len(history) == 1 else None

    out = walk_forward_portfolio(
        {"AAA": frame},
        signal,
        initial_capital=1000,
        max_hold_days=1,
        commission_per_side_usd=0,
    )
    assert seen_lengths[0] == 1
    assert out["trades"][0]["entry_price"] == 110
    assert out["trades"][0]["entry_day"] == "2026-01-02"


def test_walk_forward_stop_wins_if_stop_and_target_touch_same_bar():
    frame = _frame(
        [
            (100, 101, 99, 100),
            (100, 120, 80, 100),
            (100, 101, 99, 100),
        ]
    )

    def signal(symbol, history):
        return {"score": 9, "strategy_id": "score_momentum"} if len(history) == 1 else None

    out = walk_forward_portfolio(
        {"AAA": frame},
        signal,
        initial_capital=1000,
        stop_loss_pct=0.10,
        take_profit_pct=0.10,
        commission_per_side_usd=0,
    )
    assert out["trades"][0]["exit_reason"] == "stop_loss"
    assert out["trades"][0]["exit_price"] == 90
    assert out["return_pct"] < 0


def test_walk_forward_reports_portfolio_risk_metrics():
    frame = _frame(
        [
            (100, 101, 99, 100),
            (100, 110, 99, 108),
            (108, 120, 107, 118),
            (118, 119, 117, 118),
        ]
    )

    def signal(symbol, history):
        return {"score": 9, "strategy_id": "trend_pullback"} if len(history) == 1 else None

    out = walk_forward_portfolio(
        {"AAA": frame},
        signal,
        initial_capital=1000,
        take_profit_pct=0.15,
        commission_per_side_usd=1,
    )
    assert set(
        [
            "return_pct",
            "max_drawdown_pct",
            "profit_factor",
            "exposure_pct",
            "monthly_stability_pct",
        ]
    ).issubset(out)
    assert out["trade_count"] == 1
    assert "trend_pullback" in out["strategy_pnl_usd"]


def test_walk_forward_returns_empty_result_without_usable_frames():
    calls = []

    def signal(symbol, history):
        calls.append((symbol, len(history)))
        return {"score": 9}

    out = walk_forward_portfolio(
        {"EMPTY": pd.DataFrame(), "MISSING_COLUMNS": pd.DataFrame({"Close": [1]})},
        signal,
        initial_capital=2500,
    )

    assert out["note"] == "insufficient_data"
    assert out["final_equity"] == 2500
    assert out["trade_count"] == 0
    assert calls == []


def test_walk_forward_ranks_candidates_and_enforces_daily_cap():
    frame = _frame(
        [
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),
        ]
    )

    def signal(symbol, history):
        if len(history) != 1:
            return None
        return {
            "score": 9 if symbol == "HIGH" else 5,
            "strategy_id": f"strategy_{symbol.lower()}",
        }

    out = walk_forward_portfolio(
        {"low": frame, "high": frame},
        signal,
        initial_capital=1000,
        max_open_positions=2,
        max_trades_per_day=1,
        max_hold_days=1,
        commission_per_side_usd=0,
    )

    assert out["trade_count"] == 1
    assert out["trades"][0]["symbol"] == "HIGH"
    assert out["trades"][0]["strategy_id"] == "strategy_high"

"""Tests for idle-cash deploy advice (top up existing holdings)."""

from __future__ import annotations

import pytest

from trading_pulse.telegram.telegram_format import (
    format_cash_deploy_advice,
    format_no_new_buys_banner,
    format_plan,
    format_portfolio,
    format_sell_reply,
    format_swap_completed,
)


def test_cash_deploy_advice_suggests_top_up_existing():
    holdings = [
        {"symbol": "META", "capital_usd": 250, "entry_price": 660, "days_held": 2, "slot": 1},
        {"symbol": "PYPL", "capital_usd": 290, "entry_price": 55, "days_held": 1, "slot": 2},
    ]
    actions = [
        {"symbol": "META", "verdict": "hold", "score": 4.0, "pnl_pct": 1.0},
        {"symbol": "PYPL", "verdict": "hold", "score": 11.0, "pnl_pct": 2.0},
    ]
    lines = format_cash_deploy_advice(123, holdings, actions=actions)
    text = "\n".join(lines)
    assert "יש מזומן פנוי" in text
    assert "PYPL" in text  # higher score preferred
    assert "תקנה PYPL" in text or "תקנה 2" in text
    assert "להשאיר במזומן" in text


def test_cash_deploy_skips_sell_swap_prefers_hold():
    """Highest-score sell/swap is skipped; primary top-up goes to best hold."""
    holdings = [
        {"symbol": "META", "capital_usd": 250, "slot": 1, "unrealized_pnl_pct": 8.0},
        {"symbol": "PYPL", "capital_usd": 290, "slot": 2, "unrealized_pnl_pct": 1.0},
    ]
    actions = [
        {"symbol": "META", "verdict": "sell", "score": 20.0, "pnl_pct": 8.0},
        {"symbol": "PYPL", "verdict": "hold", "score": 5.0, "pnl_pct": 1.0},
    ]
    text = "\n".join(format_cash_deploy_advice(80, holdings, actions=actions))
    # Primary suggestion targets PYPL (hold), not META (sell)
    assert "להוסיף ל־<b>PYPL</b>" in text
    assert "להוסיף ל־<b>META</b>" not in text
    assert "תקנה 2" in text or "תקנה PYPL" in text


def test_cash_deploy_all_sell_swap_falls_back_to_pnl():
    """When every holding is sell/swap, still suggest strongest PnL."""
    holdings = [
        {"symbol": "META", "capital_usd": 250, "slot": 1, "unrealized_pnl_pct": 2.0},
        {"symbol": "PYPL", "capital_usd": 290, "slot": 2, "unrealized_pnl_pct": 9.0},
    ]
    actions = [
        {"symbol": "META", "verdict": "sell", "score": 10.0, "pnl_pct": 2.0},
        {"symbol": "PYPL", "verdict": "swap", "score": 8.0, "pnl_pct": 9.0},
    ]
    text = "\n".join(format_cash_deploy_advice(50, holdings, actions=actions))
    assert "תקנה PYPL" in text or "תקנה 2" in text


def test_cash_deploy_with_new_buys_mentions_hakol():
    holdings = [{"symbol": "META", "capital_usd": 250, "slot": 1}]
    actions = [{"symbol": "META", "verdict": "hold", "score": 8.0}]
    text = "\n".join(
        format_cash_deploy_advice(
            100,
            holdings,
            actions=actions,
            new_buy_symbols={"NVDA"},
        )
    )
    assert "הכל" in text
    assert "יש מזומן פנוי" in text
    assert "תקנה" in text  # still offers top-up


def test_cash_deploy_no_holdings_suggests_kana():
    text = "\n".join(format_cash_deploy_advice(75, []))
    assert "יש מזומן פנוי" in text
    assert "קנה SYMBOL" in text
    assert "תקנה" not in text or "תקנה 1 $50" in text  # tip only
    assert "להשאיר במזומן" in text


def test_cash_advice_hidden_when_too_small():
    assert format_cash_deploy_advice(10, [{"symbol": "META"}]) == []


def test_cash_advice_hidden_just_below_min_cash():
    assert format_cash_deploy_advice(19.99, [{"symbol": "META"}]) == []


def test_cash_advice_shown_at_exact_min_cash():
    text = "\n".join(format_cash_deploy_advice(20, [{"symbol": "META", "slot": 1}]))
    assert "יש מזומן פנוי" in text
    assert "$20" in text


def test_plan_no_picks_includes_cash_advice():
    holdings = [
        {"symbol": "META", "capital_usd": 250, "entry_price": 660, "days_held": 2},
        {"symbol": "PYPL", "capital_usd": 290, "entry_price": 55, "days_held": 1},
    ]
    plan = {
        "for_trading_day": "2026-07-18",
        "equity_snapshot": 1040,
        "available_capital_usd": 123,
        "deployed_capital_usd": 917,
        "recommendations": [],
        "holdings": holdings,
        "holding_actions": [
            {"symbol": "META", "verdict": "hold", "score": 4.0, "pnl_pct": 1.0},
            {"symbol": "PYPL", "verdict": "hold", "score": 11.0, "pnl_pct": 2.0},
        ],
        "status": "no_picks",
        "scan_stats": {"tickers_scanned": 10, "after_quality": 0, "min_entry_score": 7},
    }
    plan_text = format_plan(plan, rec_formatter=lambda *a, **k: "")
    assert "יש מזומן פנוי" in plan_text
    assert "תקנה" in plan_text


def test_no_new_buys_banner_includes_cash_block():
    plan = {"available_capital_usd": 85, "scan_stats": {}}
    holdings = [{"symbol": "AAPL", "capital_usd": 200, "slot": 1}]
    actions = [{"symbol": "AAPL", "verdict": "hold", "score": 7.0}]
    text = "\n".join(
        format_no_new_buys_banner(plan, holdings=holdings, actions=actions)
    )
    assert "אין המלצות היום" in text
    assert "יש מזומן פנוי" in text
    assert "תקנה" in text


def test_portfolio_includes_cash_deploy_when_cash_ge_20():
    data = {
        "equity": 1100,
        "cash_usd": 55,
        "total_realized_pnl": 10,
        "unrealized_pnl_usd": 5,
        "open_marked_usd": 1045,
        "open_positions": [
            {
                "symbol": "NVDA",
                "status": "holding",
                "capital_usd": 500,
                "entry_price": 100,
                "marked_value_usd": 520,
                "unrealized_pnl_usd": 20,
                "entry_at": "2026-07-14T13:35:00+00:00",
            }
        ],
        "by_symbol": [],
    }
    text = format_portfolio(data)
    assert "יש מזומן פנוי" in text
    assert "תקנה" in text
    assert "NVDA" in text


def test_sell_reply_includes_cash_deploy_when_cash_ge_20():
    holdings = [{"symbol": "PYPL", "capital_usd": 300, "slot": 1}]
    text = format_sell_reply(
        "META",
        fraction=1.0,
        pnl_usd=12.5,
        cash=90,
        holdings=holdings,
    )
    assert "מכרת META" in text
    assert "יש מזומן פנוי" in text
    assert "תקנה PYPL" in text or "תקנה 1" in text


@pytest.mark.parametrize(
    ("pnl_usd", "outcome", "amount"),
    [
        (-12.5, "הפסד ממומש", "-$12.50"),
        (12.5, "רווח ממומש", "+$12.50"),
        (0.0, "רווח ממומש", "+$0.00"),
    ],
)
def test_sell_reply_preserves_sign_and_names_outcome(pnl_usd, outcome, amount):
    text = format_sell_reply(
        "META",
        fraction=1.0,
        pnl_usd=pnl_usd,
        cash=10,
        equity=987.5,
    )
    assert outcome in text
    assert f"<code>{amount}</code>" in text
    assert "הון לאחר המכירה: <b>$987.50</b>" in text


def test_no_buy_banner_uses_capacity_reason_without_quality_contradiction():
    plan = {
        "available_capital_usd": 0,
        "max_trades": 0,
        "scan_stats": {
            "tickers_scanned": 20,
            "before_quality": 4,
            "after_quality": 1,
        },
        "capacity": {
            "blocked_reason": "no_cash_and_slots",
            "positions_open": 5,
            "max_positions": 5,
        },
    }
    text = "\n".join(
        format_no_new_buys_banner(plan, holdings=[], actions=[])
    )
    assert "מניה אחת עברה את סף האיכות" in text
    assert "אין מזומן ואין מקום בתיק" in text
    assert "אין מניות שעברו את סף האיכות" not in text


def test_swap_completed_includes_cash_deploy_when_cash_ge_20():
    holdings = [{"symbol": "BEAM", "capital_usd": 400, "slot": 1}]
    text = format_swap_completed(
        from_symbol="RIVN",
        to_symbol="BEAM",
        sold_usd=300,
        entry_price=40.0,
        bought_usd=280,
        cash=45,
        holdings=holdings,
    )
    assert "החלפה הושלמה" in text
    assert "יש מזומן פנוי" in text
    assert "תקנה" in text

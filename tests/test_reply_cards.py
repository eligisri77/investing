"""Tests for Telegram reply cards."""

from __future__ import annotations

import pytest

from trading_pulse.telegram.reply_cards import (
    card_buy,
    card_entry,
    card_from_plan_summary,
    card_help,
    card_sell,
    card_swap,
    render_html_message_card,
    render_reply_card,
)


def test_render_reply_card_png():
    png = render_reply_card(
        "בדיקה",
        accent="cyan",
        rows=[("מזומן", "$20"), ("מניה", "RIVN")],
        bullets=["שורה אחת"],
        chips=["תיק"],
        footer="הערה",
    )
    assert png.startswith(b"\x89PNG")


def test_html_message_card_strips_tags():
    png = render_html_message_card(
        "✅ <b>מכרת RIVN</b> (6%)\nמזומן פנוי: <b>$23</b>",
        accent="green",
    )
    assert png.startswith(b"\x89PNG")


def test_trade_cards():
    assert card_sell("RIVN", fraction=0.06, pnl_usd=3.13, cash=23, sold_usd=20).startswith(b"\x89PNG")
    assert card_buy("LABD", bought_usd=20, entry_price=7.1, cash=3).startswith(b"\x89PNG")
    assert card_swap(
        from_symbol="RIVN",
        to_symbol="BEAM",
        sold_usd=200,
        bought_usd=200,
        entry_price=36.0,
        cash=0,
    ).startswith(b"\x89PNG")
    assert card_help().startswith(b"\x89PNG")
    assert card_entry(
        [{"symbol": "BEAM", "capital_usd": 320, "entry_price": 36.6}],
        trading_day="2026-07-09",
    ).startswith(b"\x89PNG")


@pytest.mark.parametrize(
    ("pnl_usd", "outcome", "amount", "accent"),
    [
        (-3.25, "הפסד ממומש", "-$3.25", "red"),
        (3.25, "רווח ממומש", "+$3.25", "green"),
        (0.0, "רווח ממומש", "+$0.00", "green"),
    ],
)
def test_sell_card_preserves_sign_and_names_outcome(
    monkeypatch, pnl_usd, outcome, amount, accent
):
    captured = {}

    def fake_render(title, **kwargs):
        captured.update(title=title, **kwargs)
        return b"png"

    monkeypatch.setattr(
        "trading_pulse.telegram.reply_cards.render_reply_card",
        fake_render,
    )

    assert (
        card_sell(
            "RIVN",
            fraction=0.5,
            pnl_usd=pnl_usd,
            cash=120,
            equity=996.75,
        )
        == b"png"
    )
    assert (outcome, amount) in captured["rows"]
    assert ("הון לאחר המכירה", "$996.75") in captured["rows"]
    assert captured["accent"] == accent


def test_portfolio_card():
    from trading_pulse.telegram.reply_cards import card_portfolio

    png = card_portfolio(
        {
            "equity": 986.68,
            "cash_usd": 20,
            "open_marked_usd": 1021,
            "unrealized_pnl_usd": 34,
            "total_realized_pnl": -13.32,
            "open_positions": [
                {
                    "symbol": "LABD",
                    "status": "holding",
                    "capital_usd": 333,
                    "entry_price": 7.1,
                    "marked_value_usd": 322,
                    "unrealized_pnl_usd": -11,
                    "entry_at": "2026-07-08T17:20:00+00:00",
                },
                {
                    "symbol": "RIVN",
                    "status": "holding",
                    "capital_usd": 333,
                    "entry_price": 15.66,
                    "marked_value_usd": 386,
                    "unrealized_pnl_usd": 52,
                    "entry_at": "2026-07-08T17:20:00+00:00",
                },
            ],
        }
    )
    assert png.startswith(b"\x89PNG")


def test_plan_summary_card():
    plan = {
        "for_trading_day": "2026-07-10",
        "available_capital_usd": 20,
        "deployed_capital_usd": 966,
        "equity_snapshot": 986,
        "holdings": [{"symbol": "LABD", "capital_usd": 333}],
        "recommendations": [{"symbol": "NVDA", "capital_usd": 20}],
    }
    png = card_from_plan_summary(plan)
    assert png.startswith(b"\x89PNG")

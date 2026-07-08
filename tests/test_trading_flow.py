"""Tests for simplified trading flow helpers."""

from __future__ import annotations

from trading_pulse.agent.dryrun_agent import parse_telegram_user_command
from trading_pulse.agent.trading_flow import initial_deploy_slots, is_empty_portfolio, plan_intent


def test_parse_sell_and_swap():
    assert parse_telegram_user_command("מכור LABU")["kind"] == "sell"
    assert parse_telegram_user_command("מכור 50% LABU")["fraction"] == 0.5
    swap = parse_telegram_user_command("החלף LABU HOOD")
    assert swap["kind"] == "swap"
    assert swap["from_symbol"] == "LABU"
    assert swap["to_symbol"] == "HOOD"
    nl = parse_telegram_user_command("למכור SOXL ולקנות HOOD")
    assert nl["kind"] == "swap"
    assert nl["from_symbol"] == "SOXL"
    assert nl["to_symbol"] == "HOOD"


def test_first_investment_intent():
    from dataclasses import dataclass

    @dataclass
    class Cfg:
        max_trades_per_day = 3
        max_open_positions = 4
        initial_deploy_stocks = 3
        initial_capital = 1000.0
        max_position_pct = 0.34

    state = {"equity": 1000, "open_positions": []}
    plan = {"recommendations": [{"symbol": "A"}], "holdings": []}
    assert is_empty_portfolio(state)
    assert plan_intent(plan, state, Cfg()) == "first_investment"
    assert initial_deploy_slots(Cfg(), state) == 3

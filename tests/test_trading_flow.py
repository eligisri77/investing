"""Tests for simplified trading flow helpers."""

from __future__ import annotations

from datetime import date

import pytest

import trading_pulse.agent.dryrun_agent as agent
from trading_pulse.agent.dryrun_agent import AgentConfig, parse_telegram_user_command
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
    assert nl["from_ref"] == "SOXL"
    assert nl["to_ref"] == "HOOD"


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


@pytest.mark.parametrize(
    "manual_pnls",
    [
        [5.0],
        [5.0, -1.0],
    ],
)
def test_simulate_day_merges_manual_exits_once_and_keeps_equity_transition(
    tmp_path, monkeypatch, manual_pnls
):
    trading_day = date(2026, 7, 17)
    plan_file = tmp_path / "plan.json"
    report_file = tmp_path / "report.json"
    state_file = tmp_path / "state.json"
    agent.save_json(
        plan_file,
        {
            "for_trading_day": trading_day.isoformat(),
            "status": "executed",
            "recommendations": [],
        },
    )
    manual_rows = [
        {
            "exit_id": f"manual:{index}",
            "symbol": "U",
            "trading_day": trading_day.isoformat(),
            "exit_reason": "user_sell",
            "manual_exit": True,
            "pnl_usd": pnl,
            "fees_usd": 0.5,
        }
        for index, pnl in enumerate(manual_pnls)
    ]
    booked_pnl = sum(manual_pnls)
    state = {
        "equity": 1000.0 + booked_pnl,
        "open_positions": [],
        "intraday_floor_exits": manual_rows,
        "history": [],
    }
    automatic = {
        "symbol": "AUTO",
        "exit_reason": "take_profit",
        "pnl_usd": -2.0,
        "fees_usd": 1.0,
    }

    monkeypatch.setattr(agent, "plan_path", lambda _day: plan_file)
    monkeypatch.setattr(agent, "report_path", lambda _day: report_file)
    monkeypatch.setattr(agent, "STATE_FILE", state_file)
    monkeypatch.setattr(agent, "ensure_plan_allocation", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "trading_pulse.agent.trading_flow.entries_already_run",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        "trading_pulse.agent.positions.simulate_swing_day",
        lambda *_args, **_kwargs: ([automatic], [], -2.0, 1.0),
    )
    monkeypatch.setattr(
        "trading_pulse.agent.positions.enrich_held_unrealized",
        lambda held, _day: (held, 0.0),
    )

    report = agent.simulate_day(AgentConfig(), state, trading_day)

    assert [row["exit_id"] for row in report["executed"] if row.get("manual_exit")] == [
        row["exit_id"] for row in reversed(manual_rows)
    ]
    assert len(report["executed"]) == len(manual_rows) + 1
    assert report["pnl_usd"] == booked_pnl - 2.0
    assert report["pnl_applied_at_eod"] == -2.0
    assert report["equity_before"] == 1000.0
    assert report["equity_after"] == 1000.0 + booked_pnl - 2.0
    assert state["equity"] == report["equity_after"]
    assert state["history"] == [report]


def test_successful_manual_buy_syncs_active_plan(monkeypatch):
    from trading_pulse.telegram import reply_cards

    cfg = AgentConfig(notification_mode="telegram")
    state = {"equity": 1000.0, "open_positions": [], "history": []}
    sync_calls = []
    monkeypatch.setattr(agent, "load_state", lambda _cfg: state)
    monkeypatch.setattr(agent, "resolve_trading_day", lambda _day: "2026-07-20")
    monkeypatch.setattr(
        agent,
        "_buy_symbol_usd",
        lambda _cfg, st, symbol, amount, _day: (
            st["open_positions"].append(
                {
                    "symbol": symbol,
                    "capital_usd": amount,
                    "entry_price": 25.0,
                }
            )
            or st["open_positions"][-1]
        ),
    )
    monkeypatch.setattr(agent, "save_json", lambda *_args: None)
    monkeypatch.setattr(
        agent,
        "_sync_plan_after_manual_action",
        lambda _cfg, synced_state, action: sync_calls.append(
            (synced_state, action)
        ),
    )
    monkeypatch.setattr(agent, "send_telegram_card", lambda *_args: True)
    monkeypatch.setattr(reply_cards, "card_buy", lambda *_args, **_kwargs: b"png")

    assert agent.execute_buy_command(cfg, "u", 100) == ""
    assert sync_calls == [(state, "קנייה ידנית של U")]


def test_failed_manual_buy_does_not_sync_plan(monkeypatch):
    cfg = AgentConfig(notification_mode="telegram")
    state = {"equity": 1000.0, "open_positions": [], "history": []}
    sync_calls = []
    monkeypatch.setattr(agent, "load_state", lambda _cfg: state)
    monkeypatch.setattr(agent, "resolve_trading_day", lambda _day: "2026-07-20")
    monkeypatch.setattr(
        agent, "_buy_symbol_usd", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        agent,
        "_sync_plan_after_manual_action",
        lambda *_args: sync_calls.append(True),
    )

    reply = agent.execute_buy_command(cfg, "U", 100)
    assert "לא הצלחתי לקנות U" in reply
    assert sync_calls == []

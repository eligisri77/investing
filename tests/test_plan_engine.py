"""Broker-style plan lifecycle tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from trading_pulse.agent.dryrun_agent import AgentConfig, save_json
from trading_pulse.agent.plan_engine import (
    STATUS_CONFIRMED,
    STATUS_DRAFT,
    apply_confirm,
    apply_partial_confirm_manual,
    finalize_manual_confirm,
    is_locked,
    mark_offer_skipped,
    normalize_status,
    pending_buy_symbols,
    plan_is_protected,
    reallocate_approved_capital,
    sync_active_plan_after_manual_action,
    supersede_other_plans,
)


def test_normalize_legacy_approved_to_confirmed():
    plan = {
        "status": "approved",
        "recommendations": [{"symbol": "LABU", "approved": True}],
        "allocation": {"status": "applied"},
    }
    assert normalize_status(plan) == STATUS_CONFIRMED


def test_not_locked_when_already_holding_all_picks():
    plan = {
        "for_trading_day": "2026-07-06",
        "status": STATUS_CONFIRMED,
        "recommendations": [
            {"symbol": "SOXL", "approved": True, "capital_usd": 333},
            {"symbol": "MSTR", "approved": True, "capital_usd": 333},
        ],
        "allocation": {"status": "applied"},
    }
    state = {
        "equity": 997,
        "open_positions": [
            {"symbol": "SOXL", "capital_usd": 333},
            {"symbol": "MSTR", "capital_usd": 333},
        ],
    }
    cfg = AgentConfig()
    assert pending_buy_symbols(plan, state) == []
    assert is_locked(plan, state, cfg, as_of=date(2026, 7, 5)) is False
    assert plan_is_protected(plan, state=state, as_of=date(2026, 7, 5)) is False


def test_locked_when_confirmed_and_pending_before_open():
    plan = {
        "for_trading_day": "2026-07-07",
        "status": STATUS_CONFIRMED,
        "recommendations": [{"symbol": "LABU", "approved": True, "capital_usd": 500}],
        "allocation": {"status": "applied"},
    }
    state = {"equity": 1000, "open_positions": []}
    cfg = AgentConfig(entry_sim_time="13:35")
    with patch("trading_pulse.agent.trading_flow.before_market_entry", return_value=True):
        assert is_locked(plan, state, cfg, as_of=date(2026, 7, 6)) is True


def test_apply_confirm_sets_status_and_allocation():
    plan = {
        "for_trading_day": "2026-07-07",
        "status": STATUS_DRAFT,
        "available_capital_usd": 1000,
        "recommendations": [
            {"symbol": "A", "capital_usd": 500},
            {"symbol": "B", "capital_usd": 500},
        ],
    }
    state = {"equity": 1000, "open_positions": []}
    cfg = AgentConfig()
    out = apply_confirm(plan, state, cfg)
    assert normalize_status(out) == STATUS_CONFIRMED
    assert out["allocation"]["status"] == "applied"
    assert all(r["approved"] for r in out["recommendations"])


def test_supersede_other_plans(tmp_path, monkeypatch):
    from trading_pulse.core.app_paths import PLANS_DIR

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.PLANS_DIR", plans_dir)

    save_json(
        plans_dir / "plan_2099-01-04.json",
        {"for_trading_day": "2099-01-04", "status": STATUS_CONFIRMED, "recommendations": []},
    )
    supersede_other_plans(date(2099, 1, 5))
    old = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plans_dir / "plan_2099-01-04.json"
    )
    assert old["status"] == "superseded"


def test_cancel_plan_marks_superseded(tmp_path, monkeypatch):
    from trading_pulse.agent.plan_engine import STATUS_SUPERSEDED, cancel_plan

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.PLANS_DIR", plans_dir)

    save_json(
        plans_dir / "plan_2099-01-05.json",
        {
            "for_trading_day": "2099-01-05",
            "status": STATUS_DRAFT,
            "recommendations": [{"symbol": "MSTX"}, {"symbol": "RIVN"}],
        },
    )
    result = cancel_plan(as_of=date(2099, 1, 4))
    assert result["ok"] is True
    assert result["day"] == "2099-01-05"
    assert set(result["symbols"]) == {"MSTX", "RIVN"}

    reread = __import__("trading_pulse.agent.dryrun_agent", fromlist=["read_json"]).read_json(
        plans_dir / "plan_2099-01-05.json"
    )
    assert reread["status"] == STATUS_SUPERSEDED
    assert "cancelled_at" in reread


def test_cancel_plan_no_active_returns_reason(tmp_path, monkeypatch):
    from trading_pulse.agent.plan_engine import cancel_plan

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.PLANS_DIR", plans_dir)

    result = cancel_plan(as_of=date(2099, 1, 4))
    assert result["ok"] is False
    assert result["reason"] == "no_active_plan"


def test_manual_action_refreshes_draft_plan_snapshot(tmp_path, monkeypatch):
    plan_file = tmp_path / "plan.json"
    save_json(
        plan_file,
        {
            "for_trading_day": "2026-07-20",
            "status": STATUS_DRAFT,
            "equity_snapshot": 1000,
            "holdings": [{"symbol": "U", "capital_usd": 200}],
            "recommendations": [{"symbol": "NVDA", "capital_usd": 300}],
        },
    )
    state = {
        "equity": 1012.5,
        "open_positions": [
            {
                "symbol": "U",
                "capital_usd": 100,
                "entry_price": 50,
                "entry_day": "2026-07-15",
            }
        ],
    }
    monkeypatch.setattr(
        "trading_pulse.agent.plan_engine.active_trading_day",
        lambda: "2026-07-20",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.plan_path",
        lambda _day: plan_file,
    )

    assert sync_active_plan_after_manual_action(
        AgentConfig(), state, action="מכירה ידנית של U"
    )
    updated = __import__(
        "trading_pulse.agent.dryrun_agent", fromlist=["read_json"]
    ).read_json(plan_file)
    assert updated["holdings"][0]["capital_usd"] == 100
    assert updated["equity_snapshot"] == 1012.5
    assert updated["portfolio_snapshot_stale"] is False
    assert updated["last_manual_action"] == "מכירה ידנית של U"
    assert "portfolio_synced_at" in updated


def test_swap_sync_marks_confirmed_plan_stale_without_reallocating(
    tmp_path, monkeypatch
):
    plan_file = tmp_path / "plan.json"
    original = {
        "for_trading_day": "2026-07-20",
        "status": STATUS_CONFIRMED,
        "equity_snapshot": 1000,
        "holdings": [{"symbol": "U", "capital_usd": 200}],
        "recommendations": [
            {"symbol": "NVDA", "capital_usd": 300, "approved": True}
        ],
        "allocation": {"status": "applied", "amounts": {"NVDA": 300}},
    }
    save_json(plan_file, original)
    monkeypatch.setattr(
        "trading_pulse.agent.plan_engine.active_trading_day",
        lambda: "2026-07-20",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.plan_path",
        lambda _day: plan_file,
    )

    assert sync_active_plan_after_manual_action(
        AgentConfig(),
        {"equity": 1010, "open_positions": []},
        action="החלפה ידנית של U ב־NVDA",
    )
    updated = __import__(
        "trading_pulse.agent.dryrun_agent", fromlist=["read_json"]
    ).read_json(plan_file)
    assert updated["portfolio_snapshot_stale"] is True
    assert updated["recommendations"] == original["recommendations"]
    assert updated["allocation"] == original["allocation"]
    assert updated["equity_snapshot"] == 1000
    assert updated["last_manual_action"] == "החלפה ידנית של U ב־NVDA"


def test_prune_holding_actions_drops_symbols_not_held():
    from trading_pulse.agent.plan_engine import _prune_holding_actions

    state = {
        "open_positions": [
            {"symbol": "LABD", "capital_usd": 200, "entry_price": 10.0},
        ]
    }
    actions = [
        {"symbol": "LABD", "verdict": "sell"},
        {"symbol": "PATH", "verdict": "sell"},
        {"symbol": "RIVN", "verdict": "swap", "swap_to": "NVDA"},
    ]
    out = _prune_holding_actions(actions, state)
    assert [a["symbol"] for a in out] == ["LABD"]


def test_manual_action_prunes_holding_actions_for_closed_symbols(
    tmp_path, monkeypatch
):
    plan_file = tmp_path / "plan.json"
    save_json(
        plan_file,
        {
            "for_trading_day": "2026-07-20",
            "status": STATUS_DRAFT,
            "equity_snapshot": 1000,
            "holdings": [
                {"symbol": "LABD", "capital_usd": 200},
                {"symbol": "PATH", "capital_usd": 200},
            ],
            "holding_actions": [
                {"symbol": "LABD", "verdict": "sell"},
                {"symbol": "PATH", "verdict": "sell"},
            ],
            "recommendations": [{"symbol": "NVDA", "capital_usd": 300}],
        },
    )
    state = {
        "equity": 1000,
        "open_positions": [
            {
                "symbol": "LABD",
                "capital_usd": 200,
                "entry_price": 10,
                "entry_day": "2026-07-15",
            }
        ],
    }
    monkeypatch.setattr(
        "trading_pulse.agent.plan_engine.active_trading_day",
        lambda: "2026-07-20",
    )
    monkeypatch.setattr(
        "trading_pulse.agent.dryrun_agent.plan_path",
        lambda _day: plan_file,
    )

    assert sync_active_plan_after_manual_action(
        AgentConfig(), state, action="מכירה ידנית של PATH"
    )
    updated = __import__(
        "trading_pulse.agent.dryrun_agent", fromlist=["read_json"]
    ).read_json(plan_file)
    assert [a["symbol"] for a in updated["holding_actions"]] == ["LABD"]
    assert {h["symbol"] for h in updated["holdings"]} == {"LABD"}


def test_apply_partial_confirm_manual_approves_one_rec_with_amount():
    plan = {
        "recommendations": [
            {"symbol": "NVDA", "score": 14.0},
            {"symbol": "AMD", "score": 10.0},
        ],
    }
    out = apply_partial_confirm_manual(plan, "NVDA", 123.456)
    nvda = next(r for r in out["recommendations"] if r["symbol"] == "NVDA")
    amd = next(r for r in out["recommendations"] if r["symbol"] == "AMD")
    assert nvda["approved"] is True
    assert nvda["capital_usd"] == 123.46
    assert "approved_at" in nvda
    assert amd.get("approved") is None
    assert out["allocation"]["status"] == "pending"
    assert out["allocation"]["manual_offer_flow"] is True
    assert out["allocation"]["amounts"] == {"NVDA": 123.46}


def test_apply_partial_confirm_manual_merges_amounts_across_calls():
    plan = {"recommendations": [{"symbol": "NVDA"}, {"symbol": "AMD"}]}
    apply_partial_confirm_manual(plan, "NVDA", 100.0)
    apply_partial_confirm_manual(plan, "AMD", 50.0)
    assert plan["allocation"]["amounts"] == {"NVDA": 100.0, "AMD": 50.0}
    assert all(r["approved"] for r in plan["recommendations"])


def test_apply_partial_confirm_manual_clears_offer_skipped():
    plan = {"recommendations": [{"symbol": "NVDA", "offer_skipped": True}]}
    out = apply_partial_confirm_manual(plan, "NVDA", 100.0)
    nvda = out["recommendations"][0]
    assert nvda["approved"] is True
    assert "offer_skipped" not in nvda


def test_apply_partial_confirm_manual_does_not_trigger_old_allocation_choice_ui():
    """Regression: mid offer-queue, allocation.status="pending" must not be
    mistaken for the old ח1..ח5 multi-option allocation-choice flow (which
    would wrongly surface its guidance/UI while the Telegram offer
    conversation is still in progress)."""
    from trading_pulse.agent.capital_allocation import allocation_pending

    plan = {
        "recommendations": [
            {"symbol": "NVDA", "score": 14.0},
            {"symbol": "AMD", "score": 10.0},
        ],
    }
    out = apply_partial_confirm_manual(plan, "NVDA", 100.0)
    assert allocation_pending(out) is False


def test_mark_offer_skipped_sets_flag_and_unapproves():
    plan = {"recommendations": [{"symbol": "NVDA", "approved": False, "capital_usd": 100}]}
    out = mark_offer_skipped(plan, "NVDA")
    nvda = out["recommendations"][0]
    assert nvda["approved"] is False
    assert nvda["offer_skipped"] is True


def test_mark_offer_skipped_preserves_prior_approve():
    plan = {"recommendations": [{"symbol": "NVDA", "approved": True, "capital_usd": 100}]}
    out = mark_offer_skipped(plan, "NVDA")
    nvda = out["recommendations"][0]
    assert nvda["approved"] is True
    assert nvda.get("offer_skipped") is not True


def test_finalize_manual_confirm_stays_draft_when_nothing_approved():
    plan = {
        "status": STATUS_DRAFT,
        "recommendations": [
            {"symbol": "NVDA", "approved": False, "offer_skipped": True},
        ],
    }
    out = finalize_manual_confirm(plan, {"equity": 1000}, AgentConfig())
    assert out["status"] == STATUS_DRAFT
    assert "confirmed_at" not in out
    assert "allocation" not in out


def test_finalize_manual_confirm_confirms_with_chosen_amounts():
    plan = {
        "status": STATUS_DRAFT,
        "recommendations": [
            {"symbol": "NVDA", "approved": True, "capital_usd": 150.0},
            {"symbol": "AMD", "approved": False, "offer_skipped": True},
        ],
    }
    state = {"equity": 1000.0, "open_positions": []}
    out = finalize_manual_confirm(plan, state, AgentConfig())
    assert out["status"] == STATUS_CONFIRMED
    assert "confirmed_at" in out
    assert out["pre_entry_equity"] == 1000.0
    assert out["allocation"]["status"] == "applied"
    assert out["allocation"]["auto"] is False
    assert out["allocation"]["manual_offer_flow"] is True
    assert out["allocation"]["amounts"] == {"NVDA": 150.0}  # only approved recs


def test_finalize_manual_confirm_does_not_equal_split_amounts():
    """Unlike apply_confirm, amounts come from the conversation, not an equal split."""
    plan = {
        "status": STATUS_DRAFT,
        "recommendations": [
            {"symbol": "NVDA", "approved": True, "capital_usd": 250.0},
            {"symbol": "AMD", "approved": True, "capital_usd": 75.0},
        ],
    }
    state = {"equity": 1000.0, "open_positions": []}
    out = finalize_manual_confirm(plan, state, AgentConfig())
    assert out["allocation"]["amounts"] == {"NVDA": 250.0, "AMD": 75.0}
    assert out["recommendations"][0]["capital_usd"] == 250.0
    assert out["recommendations"][1]["capital_usd"] == 75.0

def test_reallocate_approved_capital_moves_slice_and_keeps_donor():
    plan = {
        "holdings": [],
        "recommendations": [
            {"symbol": "ELF", "approved": True, "capital_usd": 950.0},
            {"symbol": "U", "approved": False, "capital_usd": 0},
        ],
    }
    moved = reallocate_approved_capital(plan, "ELF", "U", 190.0)
    assert moved is not None
    assert moved["moved_usd"] == 190.0
    assert moved["from_left_usd"] == 760.0
    elf = plan["recommendations"][0]
    u = plan["recommendations"][1]
    assert elf["capital_usd"] == 760.0 and elf["approved"]
    assert u["approved"] and u["capital_usd"] == 190.0


def test_reallocate_approved_capital_clears_donor_when_fully_moved():
    plan = {
        "holdings": [],
        "recommendations": [
            {"symbol": "ELF", "approved": True, "capital_usd": 100.0},
        ],
    }
    moved = reallocate_approved_capital(plan, "ELF", "U", 100.0)
    assert moved["from_left_usd"] == 0.0
    assert plan["recommendations"][0]["approved"] is False
    u = next(r for r in plan["recommendations"] if r["symbol"] == "U")
    assert u["approved"] and u["capital_usd"] == 100.0


def test_reallocate_approved_capital_rejects_when_from_is_held():
    """Live position must be sold — paper reallocation is blocked."""
    plan = {
        "holdings": [{"symbol": "ELF", "capital_usd": 400.0}],
        "recommendations": [
            {"symbol": "ELF", "approved": True, "capital_usd": 400.0},
            {"symbol": "U", "approved": False, "capital_usd": 0},
        ],
    }
    assert reallocate_approved_capital(plan, "ELF", "U", 190.0) is None
    assert plan["recommendations"][0]["capital_usd"] == 400.0
    assert plan["recommendations"][1]["approved"] is False

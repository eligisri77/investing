"""Tests for empty-plan UX, month tracking, and config profile overrides."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from trading_pulse.agent.dryrun_agent import AgentConfig, apply_risk_profile, ensure_month_tracking, generate_plan, load_config, plan_is_protected, save_json
from trading_pulse.telegram.telegram_format import format_plan


def test_apply_risk_profile_respects_config_overrides():
    raw = {
        "risk_profile": "speculative",
        "max_trades_per_day": 1,
        "min_volume_ratio": 1.3,
        "stop_loss_pct": 0.12,
    }
    cfg = AgentConfig(**raw)
    apply_risk_profile(cfg, raw)
    assert cfg.max_trades_per_day == 1
    assert cfg.min_volume_ratio == 1.3
    assert cfg.stop_loss_pct == 0.12


def test_apply_risk_profile_uses_profile_defaults_when_missing():
    raw = {"risk_profile": "speculative"}
    cfg = AgentConfig(**raw)
    apply_risk_profile(cfg, raw)
    assert cfg.max_trades_per_day == 4


def test_ensure_month_tracking_uses_experiment_month_key():
    cfg = AgentConfig()
    state = {
        "equity": 1000.0,
        "month_key": "2026-06",
        "month_start_date": "2026-06-01",
        "experiment": {"label": "july_2026", "month_key": "2026-07"},
    }
    with patch("trading_pulse.agent.dryrun_agent.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 28)
        mock_date.fromisoformat = date.fromisoformat
        ensure_month_tracking(cfg, state)
    assert state["month_key"] == "2026-07"
    assert state["month_start_date"] == "2026-07-01"


def test_format_plan_no_picks_skips_approval_steps():
    plan = {
        "for_trading_day": "2026-06-29",
        "equity_snapshot": 1000,
        "available_capital_usd": 1000,
        "recommendations": [],
        "holdings": [],
        "status": "no_picks",
        "no_picks_reason": "סף ציון 8 — הציונים הגבוהים: AMD (7.5)",
        "scan_stats": {
            "tickers_scanned": 13,
            "before_quality": 1,
            "after_quality": 0,
            "min_entry_score": 7.0,
            "min_volume_ratio": 1.1,
            "top_skipped_scores": [{"symbol": "LABU", "score": 6.8}],
        },
    }
    text = format_plan(plan, rec_formatter=lambda r, i, p: "")
    assert "שלב 1" not in text
    assert "אין המלצות היום" in text
    assert "נסרקו מניות" in text
    assert "13" in text
    assert "LABU (6.8)" in text
    assert "ח1" not in text


def test_format_scan_summary_funnel():
    from trading_pulse.telegram.telegram_format import format_scan_summary

    plan = {
        "recommendations": [],
        "scan_stats": {
            "tickers_scanned": 13,
            "before_quality": 1,
            "after_quality": 0,
            "min_entry_score": 7.0,
            "min_volume_ratio": 1.1,
            "top_skipped_scores": [{"symbol": "LABU", "score": 6.8}],
        },
    }
    text = format_scan_summary(plan, html=False)
    assert "נסרקו מניות: 13" in text
    assert "עברו סינון אותות: 1" in text
    assert "LABU (6.8)" in text


def test_format_plan_with_recommendations_shows_approval():
    plan = {
        "for_trading_day": "2026-06-29",
        "equity_snapshot": 1000,
        "available_capital_usd": 1000,
        "deployed_capital_usd": 0,
        "flow_intent": "first_investment",
        "recommendations": [{"symbol": "NVDA", "capital_usd": 500}],
        "holdings": [],
    }
    text = format_plan(plan, rec_formatter=lambda r, i, p: "")
    assert "יום ראשון" in text
    assert "NVDA" in text
    assert "הכל" in text


def test_format_plan_table_caption_with_picks():
    from trading_pulse.telegram.telegram_format import format_plan_table_caption

    plan = {"for_trading_day": "2026-06-29", "recommendations": [{"symbol": "NVDA"}]}
    cap = format_plan_table_caption(plan)
    assert "הכל" in cap


def test_format_plan_table_caption_no_picks():
    from trading_pulse.telegram.telegram_format import format_plan_table_caption

    plan = {
        "for_trading_day": "2026-06-29",
        "recommendations": [],
        "scan_stats": {
            "tickers_scanned": 13,
            "before_quality": 1,
            "after_quality": 0,
            "min_entry_score": 7.0,
            "top_skipped_scores": [{"symbol": "LABU", "score": 7.7}],
        },
    }
    cap = format_plan_table_caption(plan)
    assert "שלב 1" not in cap
    assert "LABU" in cap


def test_load_config_keeps_max_trades_from_file(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(
        '{"risk_profile": "speculative", "max_trades_per_day": 1, "min_volume_ratio": 1.3}',
        encoding="utf-8",
    )
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.CONFIG_FILE", config)
    cfg = load_config()
    assert cfg.max_trades_per_day == 1
    assert cfg.min_volume_ratio == 1.3


def test_plan_is_protected_when_allocated():
    plan = {
        "status": "approved",
        "recommendations": [{"symbol": "LABU", "approved": True}],
        "allocation": {"status": "applied", "amounts": {"LABU": 1000.0}},
    }
    assert plan_is_protected(plan) is True


def test_plan_is_protected_when_approved_only():
    plan = {"status": "pending_approval", "recommendations": [{"symbol": "NVDA", "approved": True}]}
    assert plan_is_protected(plan) is True


def test_plan_is_not_protected_when_pending():
    plan = {"status": "pending_approval", "recommendations": [{"symbol": "NVDA", "approved": False}]}
    assert plan_is_protected(plan) is False


def test_generate_plan_skips_protected_plan(tmp_path, monkeypatch):
    from trading_pulse.core.app_paths import PLANS_DIR

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.PLANS_DIR", plans_dir)
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.plan_path", lambda d: plans_dir / f"plan_{d.isoformat()}.json")

    protected = {
        "for_trading_day": "2026-07-02",
        "status": "approved",
        "recommendations": [{"symbol": "LABU", "approved": True}],
        "allocation": {"status": "applied", "amounts": {"LABU": 1000.0}},
    }
    save_json(plans_dir / "plan_2026-07-02.json", protected)

    cfg = AgentConfig(tickers=["LABU"])
    state = {"equity": 1000.0}
    with patch("trading_pulse.agent.dryrun_agent.get_next_us_trading_day", return_value=date(2026, 7, 2)):
        with patch("trading_pulse.agent.dryrun_agent.fetch_signal_universe") as mock_fetch:
            plan = generate_plan(cfg, state, date(2026, 7, 1))
    assert plan["_regeneration_skipped"] is True
    assert plan["recommendations"][0]["symbol"] == "LABU"
    mock_fetch.assert_not_called()

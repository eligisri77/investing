"""Tests for empty-plan UX, month tracking, and config profile overrides."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from trading_pulse.agent.dryrun_agent import (
    AgentConfig,
    apply_risk_profile,
    ensure_month_tracking,
    generate_plan,
    load_config,
    plan_is_protected,
    risk_profile_summary,
    save_json,
)
from trading_pulse.telegram.telegram_format import (
    format_days_he,
    format_heartbeat,
    format_plan,
    format_report,
)


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
    assert "יש מזומן פנוי" in text  # idle cash ≥ $20
    assert "קנה SYMBOL" in text  # empty holdings


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


def test_format_plan_with_holdings_explains_new_vs_held():
    plan = {
        "for_trading_day": "2026-07-09",
        "equity_snapshot": 1000,
        "available_capital_usd": 320,
        "deployed_capital_usd": 666,
        "flow_intent": "add_with_cash",
        "holdings": [
            {"symbol": "LABD", "capital_usd": 333, "days_held": 1, "entry_price": 7.1},
            {"symbol": "RIVN", "capital_usd": 333, "days_held": 1, "entry_price": 15.6},
        ],
        "holding_actions": [
            {
                "symbol": "LABD",
                "verdict": "hold",
                "pnl_pct": 2.3,
                "capital_usd": 333,
                "reason": "מגמה תקינה",
            },
            {
                "symbol": "RIVN",
                "verdict": "swap",
                "pnl_pct": 5.6,
                "capital_usd": 333,
                "swap_to": "BEAM",
                "reason": "מחר יש מניה חזקה יותר",
            },
        ],
        "recommendations": [
            {"symbol": "BEAM", "capital_usd": 320, "entry_ref_price": 36.5},
            {"symbol": "RIVN", "capital_usd": 333, "entry_ref_price": 16.5},
        ],
    }
    text = format_plan(plan, rec_formatter=lambda r, i, p: "")
    assert "התיק שלך עכשיו" in text
    assert "LABD" in text and "מושקע" in text
    assert "קניות חדשות" in text or "המלצות קנייה חדשות" in text
    assert "BEAM" in text
    assert "כבר בתיק" in text
    assert "RIVN" in text
    assert "איך לבצע" in text
    assert "החלף" in text
    assert "הכל" in text
    # New buys + idle cash: advice mentions הכל and prefers hold (LABD) over swap (RIVN)
    assert "יש מזומן פנוי" in text
    assert "תקנה LABD" in text or "תקנה" in text


def test_format_approval_reply_new_vs_held():
    from trading_pulse.telegram.telegram_format import format_approval_reply

    plan = {
        "recommendations": [
            {"symbol": "RIVN", "approved": True, "capital_usd": 333},
            {"symbol": "LABD", "approved": True, "capital_usd": 333},
            {"symbol": "BEAM", "approved": True, "capital_usd": 320},
        ],
        "holdings": [],
        "allocation": {
            "status": "applied",
            "amounts": {"BEAM": 320.02},
            "holdings": [
                {"symbol": "LABD", "capital_usd": 333.33},
                {"symbol": "RIVN", "capital_usd": 333.33},
            ],
        },
    }
    text = format_approval_reply(
        trading_day="2026-07-09",
        picked_symbols=["RIVN", "LABD", "BEAM"],
        all_approved_symbols=["RIVN", "LABD", "BEAM"],
        auto_allocated=True,
        plan=plan,
    )
    assert "תוכנית מאושרת" in text
    assert "קניות מחר בפתיחה" in text
    assert "BEAM" in text
    assert "נשאר בתיק" in text
    assert "LABD" in text and "RIVN" in text
    assert "מאושר — RIVN, LABD, BEAM" not in text
    assert "לא נקנה שוב" in text


def test_format_approval_reply_lists_unfinished_holding_actions():
    from trading_pulse.telegram.telegram_format import format_approval_reply

    plan = {
        "recommendations": [
            {"symbol": "BEAM", "approved": True, "capital_usd": 400},
        ],
        "holdings": [
            {"symbol": "LABD", "capital_usd": 200},
            {"symbol": "RIVN", "capital_usd": 200},
        ],
        "holding_actions": [
            {"symbol": "LABD", "verdict": "sell"},
            {"symbol": "RIVN", "verdict": "swap", "swap_to": "NVDA"},
        ],
        "allocation": {
            "status": "applied",
            "amounts": {"BEAM": 400},
            "holdings": [
                {"symbol": "LABD", "capital_usd": 200},
                {"symbol": "RIVN", "capital_usd": 200},
            ],
        },
    }
    text = format_approval_reply(
        trading_day="2026-07-20",
        picked_symbols=["BEAM"],
        all_approved_symbols=["BEAM"],
        auto_allocated=True,
        plan=plan,
    )
    assert "תוכנית מאושרת" in text
    assert "עדיין ידני" in text
    assert "הכל לא ביצע" in text
    assert "מכור LABD" in text
    assert "החלף RIVN NVDA" in text


def test_format_approval_reply_skips_holding_actions_not_in_plan_holdings():
    """Closed positions (e.g. PATH at EOD) must not appear in «עדיין ידני»."""
    from trading_pulse.telegram.telegram_format import format_approval_reply

    plan = {
        "recommendations": [
            {"symbol": "BEAM", "approved": True, "capital_usd": 400},
        ],
        "holdings": [
            {"symbol": "LABD", "capital_usd": 200},
        ],
        "holding_actions": [
            {"symbol": "LABD", "verdict": "sell"},
            {"symbol": "PATH", "verdict": "sell"},
            {"symbol": "RIVN", "verdict": "swap", "swap_to": "NVDA"},
        ],
        "allocation": {
            "status": "applied",
            "amounts": {"BEAM": 400},
            "holdings": [
                {"symbol": "LABD", "capital_usd": 200},
            ],
        },
    }
    text = format_approval_reply(
        trading_day="2026-07-20",
        picked_symbols=["BEAM"],
        all_approved_symbols=["BEAM"],
        auto_allocated=True,
        plan=plan,
    )
    assert "מכור LABD" in text
    assert "PATH" not in text
    assert "מכור PATH" not in text
    assert "החלף RIVN" not in text
    assert "RIVN NVDA" not in text


def test_format_approval_reply_method2_short_wording():
    from trading_pulse.telegram.telegram_format import format_approval_reply

    plan = {
        "recommendations": [
            {
                "symbol": "SHORT1",
                "approved": True,
                "capital_usd": 200,
                "strategy": "method2",
                "side": "SHORT",
                "trigger": "2-1-2",
            },
        ],
        "holdings": [],
        "allocation": {"status": "applied", "amounts": {"SHORT1": 200}, "holdings": []},
    }
    text = format_approval_reply(
        trading_day="2026-07-20",
        picked_symbols=["SHORT1"],
        all_approved_symbols=["SHORT1"],
        auto_allocated=True,
        plan=plan,
    )
    assert "שורט" in text
    assert "נרות סיניים 2" in text
    assert "רווח כשהמחיר יורד" in text


def test_format_entry_notification_gap_note_when_open_differs():
    from trading_pulse.telegram.telegram_format import format_entry_notification

    with_gap = format_entry_notification(
        [
            {
                "symbol": "GAP",
                "capital_usd": 300,
                "entry_price": 110.0,
                "entry_ref_price": 100.0,
            }
        ],
        trading_day="2026-07-20",
    )
    assert "נפתח בפער" in with_gap
    assert "+10.0%" in with_gap

    no_gap = format_entry_notification(
        [
            {
                "symbol": "OK",
                "capital_usd": 300,
                "entry_price": 101.0,
                "entry_ref_price": 100.0,
            }
        ],
        trading_day="2026-07-20",
    )
    assert "נפתח בפער" not in no_gap
    from trading_pulse.agent.plan_engine import apply_confirm

    state = {
        "equity": 986.68,
        "open_positions": [
            {"symbol": "LABD", "capital_usd": 333.33, "entry_price": 7.1, "days_held": 1, "entry_day": "2026-07-08"},
            {"symbol": "RIVN", "capital_usd": 333.33, "entry_price": 15.6, "days_held": 1, "entry_day": "2026-07-08"},
        ],
    }
    plan = {
        "equity_snapshot": 1000,
        "deployed_capital_usd": 0,
        "available_capital_usd": 1000,
        "holdings": [],
        "flow_intent": "first_investment",
        "recommendations": [
            {"symbol": "BEAM", "approved": False, "capital_usd": 333},
            {"symbol": "RIVN", "approved": False, "capital_usd": 333},
        ],
    }
    cfg = AgentConfig()
    result = apply_confirm(plan, state, cfg)
    assert len(result["holdings"]) == 2
    assert result["flow_intent"] == "add_with_cash"
    assert result["deployed_capital_usd"] > 600
    assert result["allocation"]["amounts"].get("BEAM") is not None
    assert "RIVN" not in result["allocation"].get("amounts", {})


def test_format_plan_emphasizes_no_buys_with_swap_howto():
    plan = {
        "for_trading_day": "2026-07-14",
        "equity_snapshot": 1000,
        "available_capital_usd": 0,
        "deployed_capital_usd": 1000,
        "recommendations": [],
        "holdings": [
            {"symbol": "META", "capital_usd": 500, "days_held": 1, "entry_price": 660},
        ],
        "holding_actions": [
            {
                "symbol": "META",
                "verdict": "swap",
                "pnl_pct": -1.0,
                "capital_usd": 500,
                "swap_to": "MPC",
                "reason": "יש מניה חזקה יותר",
            }
        ],
        "scan_stats": {
            "tickers_scanned": 35,
            "before_quality": 2,
            "after_quality": 0,
            "min_entry_score": 7.0,
            "top_skipped_scores": [{"symbol": "PATH", "score": 6.2}],
        },
    }
    text = format_plan(plan, rec_formatter=lambda r, i, p: "")
    assert "אין המלצות היום" in text
    assert "איך לבצע" in text
    assert "החלף META MPC" in text
    assert "אין צורך לשלוח" in text or "אין צורך באישור" in text or "אין צורך" in text


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
        "for_trading_day": "2026-07-02",
        "status": "confirmed",
        "recommendations": [{"symbol": "LABU", "approved": True}],
        "allocation": {"status": "applied", "amounts": {"LABU": 1000.0}},
    }
    state = {"equity": 1000, "open_positions": []}
    with patch("trading_pulse.agent.trading_flow.before_market_entry", return_value=True):
        assert plan_is_protected(plan, state=state, as_of=date(2026, 7, 1)) is True


def test_plan_is_protected_when_approved_only():
    plan = {
        "for_trading_day": "2026-07-02",
        "status": "draft",
        "recommendations": [{"symbol": "NVDA", "approved": True}],
    }
    assert plan_is_protected(plan, state={"open_positions": []}, as_of=date(2026, 7, 1)) is False


def test_plan_is_not_protected_when_pending():
    plan = {"status": "pending_approval", "recommendations": [{"symbol": "NVDA", "approved": False}]}
    assert plan_is_protected(plan) is False


def test_generate_plan_skips_locked_plan(tmp_path, monkeypatch):
    from trading_pulse.core.app_paths import PLANS_DIR

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.PLANS_DIR", plans_dir)
    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.plan_path", lambda d: plans_dir / f"plan_{d.isoformat()}.json")

    protected = {
        "for_trading_day": "2026-07-02",
        "status": "confirmed",
        "recommendations": [{"symbol": "LABU", "approved": True}],
        "allocation": {"status": "applied", "amounts": {"LABU": 1000.0}},
    }
    save_json(plans_dir / "plan_2026-07-02.json", protected)

    cfg = AgentConfig(tickers=["LABU"])
    state = {"equity": 1000.0, "open_positions": []}
    with patch("trading_pulse.agent.dryrun_agent.get_next_us_trading_day", return_value=date(2026, 7, 2)):
        with patch("trading_pulse.agent.trading_flow.before_market_entry", return_value=True):
            with patch("trading_pulse.agent.dryrun_agent.fetch_signal_universe") as mock_fetch:
                plan = generate_plan(cfg, state, date(2026, 7, 1))
    assert plan["_regeneration_skipped"] is True
    assert plan["recommendations"][0]["symbol"] == "LABU"
    mock_fetch.assert_not_called()


def test_weekend_heartbeat_explains_closed_market_and_next_session():
    cfg = AgentConfig()
    text = format_heartbeat(
        cfg,
        {"equity": 1000},
        summary_fn=lambda *_args: "סיכון שמרני",
        monthly_fn=lambda *_args: "",
        speculative_fn=lambda _cfg: False,
        market_day=False,
        next_trading_day="2026-07-20",
    )
    assert "וול סטריט סגורה היום" in text
    assert "אין כניסות או דוח מסחר" in text
    assert "2026-07-20" in text
    assert "תוכנית:" not in text or "2026-07-20" in text
    # Market-closed path must not advertise today's plan/report times
    assert "דוח:" not in text


def test_heartbeat_signed_amounts_use_ltr_code_not_flipped_dollar():
    cfg = AgentConfig(risk_profile="speculative", monthly_target_usd=2000)
    cfg.risk_profile = "speculative"
    state = {
        "equity": 969.81,
        "month_start_equity": 1000.0,
        "open_positions": [],
    }
    text = format_heartbeat(
        cfg,
        state,
        summary_fn=lambda *_a: "x",
        monthly_fn=lambda *_a: "y",
        speculative_fn=lambda _c: True,
        market_day=True,
    )
    assert "הפסד החודש" in text or "רווח החודש" in text or "חודש:" in text
    assert "-$30.19" in text or "\u2212$30.19" in text
    assert "30.19$" not in text  # old flipped form
    assert "נותר ליעד" in text or "מעל היעד" in text
    assert "ימי מסחר שנותרו" in text
    assert "פרופיל:" in text
    assert "תוכנית:" in text and "ישראל" in text


def test_hebrew_day_grammar_and_report_outcomes():
    assert format_days_he(1) == "יום אחד"
    assert format_days_he(2) == "2 ימים"
    report = {
        "trading_day": "2026-07-17",
        "pnl_usd": 0,
        "equity_before": 1000,
        "equity_after": 1000,
        "held_eod": [{"symbol": "U", "capital_usd": 100, "days_held": 1}],
        "executed": [],
    }
    text = format_report(report)
    assert "ללא שינוי $0.00" in text
    assert "יום אחד" in text
    assert "1 ימים" not in text


def test_risk_summary_uses_hebrew_labels_only():
    text = risk_profile_summary(AgentConfig(), equity=1000)
    assert "עד " in text
    assert "מההון מושקע" in text
    assert "עסקאות" in text
    assert "לעסקה" in text
    assert "up to" not in text
    assert "trades" not in text
    assert "conservative" not in text


def test_plan_copy_distinguishes_synced_draft_from_stale_confirmed():
    base = {
        "for_trading_day": "2026-07-20",
        "generated_at": "2026-07-18T17:00:00+00:00",
        "equity_snapshot": 1000,
        "available_capital_usd": 1000,
        "deployed_capital_usd": 0,
        "recommendations": [],
        "holdings": [],
        "last_manual_action": "מכירה ידנית של U",
    }
    synced = format_plan(
        {**base, "portfolio_snapshot_stale": False},
        rec_formatter=lambda *_args: "",
    )
    stale = format_plan(
        {**base, "portfolio_snapshot_stale": True},
        rec_formatter=lambda *_args: "",
    )
    assert "התוכנית עודכנה לאחר מכירה ידנית של U" in synced
    assert "ההזמנה שכבר אושרה לא שונתה" not in synced
    assert "התיק השתנה לאחר מכירה ידנית של U" in stale
    assert "ההזמנה שכבר אושרה לא שונתה" in stale

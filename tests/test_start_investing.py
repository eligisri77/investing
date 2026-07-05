"""One-click start investing flow."""

from unittest.mock import patch

from trading_pulse.agent.dryrun_agent import get_active_trading_day, parse_telegram_user_command


def test_parse_start_command():
    assert parse_telegram_user_command("התחל")["kind"] == "start"
    assert parse_telegram_user_command("כן")["kind"] == "approve"


def test_active_plan_prefers_today(tmp_path, monkeypatch):
    from datetime import date
    from trading_pulse.agent import dryrun_agent

    plans = tmp_path / "plans"
    plans.mkdir()
    today = date.today().isoformat()
    (plans / f"plan_{today}.json").write_text(
        '{"for_trading_day": "' + today + '", "generated_at": "2026-07-03T10:00:00"}',
        encoding="utf-8",
    )
    (plans / "plan_2026-07-06.json").write_text(
        '{"for_trading_day": "2026-07-06", "generated_at": "2026-07-03T09:00:00"}',
        encoding="utf-8",
    )
    reports = tmp_path / "reports"
    reports.mkdir()

    monkeypatch.setattr(dryrun_agent, "PLANS_DIR", plans)
    monkeypatch.setattr(dryrun_agent, "REPORTS_DIR", reports)

    assert get_active_trading_day() == today

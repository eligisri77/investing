"""Plan target day resolution."""

from datetime import date

from trading_pulse.agent.dryrun_agent import get_next_us_trading_day, resolve_plan_target_day


def test_force_on_friday_targets_friday_when_no_report(monkeypatch):
    friday = date(2026, 7, 3)

    def fake_report_path(day):
        class P:
            def exists(self):
                return False

        return P()

    monkeypatch.setattr("trading_pulse.agent.dryrun_agent.report_path", fake_report_path)
    assert resolve_plan_target_day(friday, force=True) == friday


def test_scheduled_friday_targets_monday():
    friday = date(2026, 7, 3)
    assert get_next_us_trading_day(friday) == date(2026, 7, 6)
    assert resolve_plan_target_day(friday, force=False) == date(2026, 7, 6)

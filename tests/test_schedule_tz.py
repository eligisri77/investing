"""Schedule timezone display."""

from datetime import date

from trading_pulse.core.schedule_tz import format_dual_time, format_local_entry_moment, utc_hhmm_to_zone
from trading_pulse.core.schedule_tz import ISRAEL, US_EASTERN


def test_entry_time_israel_summer():
    # 13:35 UTC = 16:35 Israel in July (IDT, UTC+3)
    assert utc_hhmm_to_zone("13:35", ISRAEL, on_day=date(2026, 7, 3)) == "16:35"
    assert format_dual_time("13:35", on_day=date(2026, 7, 3)) == "13:35 UTC · 16:35 ישראל"


def test_plan_time_israel_summer():
    assert format_dual_time("20:15", on_day=date(2026, 7, 3)) == "20:15 UTC · 23:15 ישראל"


def test_report_time_israel_summer():
    assert format_dual_time("20:20", on_day=date(2026, 7, 3)) == "20:20 UTC · 23:20 ישראל"


def test_minutes_until_utc_hhmm():
    from datetime import datetime, timezone

    from trading_pulse.core.schedule_tz import minutes_until_utc_hhmm

    now = datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc)
    assert minutes_until_utc_hhmm("20:20", now=now) == 20
    assert minutes_until_utc_hhmm("19:00", now=now) == 0


def test_us_trading_session_date_evening_israel():
    from datetime import datetime, timezone

    from trading_pulse.core.schedule_tz import us_trading_session_date

    # 23:20 Israel summer = 20:20 UTC — still same US session day.
    now = datetime(2026, 7, 10, 20, 20, tzinfo=timezone.utc)
    assert us_trading_session_date(now=now) == date(2026, 7, 10)
    # After midnight Israel but still US afternoon: 00:30 Israel = 21:30 UTC prev calendar in IL
    # 21:30 UTC July 10 = 17:30 ET July 10 = still July 10 US session
    now2 = datetime(2026, 7, 10, 21, 30, tzinfo=timezone.utc)
    assert us_trading_session_date(now=now2) == date(2026, 7, 10)


def test_schedule_daily_at_uses_utc():
    import schedule
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from trading_pulse.core.schedule_tz import schedule_daily_at

    schedule.clear()
    job = schedule_daily_at("20:20").do(lambda: None)
    assert job.next_run is not None
    # schedule stores next_run as naive local time; convert expected UTC→local.
    expected_local = (
        datetime(job.next_run.year, job.next_run.month, job.next_run.day, 20, 20, tzinfo=ZoneInfo("UTC"))
        .astimezone()
    )
    assert job.next_run.hour == expected_local.hour
    assert job.next_run.minute == expected_local.minute
    schedule.clear()


def test_us_eastern_summer():
    assert utc_hhmm_to_zone("13:35", US_EASTERN, on_day=date(2026, 7, 3)) == "09:35"


def test_entry_moment_israel():
    assert format_local_entry_moment("2026-07-03T06:49:13.231065+00:00") == "03/07 09:49"

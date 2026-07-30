"""Schedule timezone display."""

from datetime import date

from trading_pulse.core.schedule_tz import (
    ISRAEL,
    ISRAEL_SCHEDULE_TIME_KEYS,
    US_EASTERN,
    dual_times_from_config,
    format_dual_time,
    format_dual_time_from_israel,
    format_local_entry_moment,
    utc_hhmm_to_zone,
    zone_hhmm_to_utc,
)


def test_entry_time_israel_summer():
    # 13:35 UTC = 16:35 Israel in July (IDT, UTC+3)
    assert utc_hhmm_to_zone("13:35", ISRAEL, on_day=date(2026, 7, 3)) == "16:35"
    assert format_dual_time("13:35", on_day=date(2026, 7, 3)) == "\u200e16:35\u200e ישראל (\u200e13:35\u200e UTC)"


def test_plan_time_israel_summer():
    assert format_dual_time("20:15", on_day=date(2026, 7, 3)) == "\u200e23:15\u200e ישראל (\u200e20:15\u200e UTC)"


def test_report_time_israel_summer():
    assert format_dual_time("20:20", on_day=date(2026, 7, 3)) == "\u200e23:20\u200e ישראל (\u200e20:20\u200e UTC)"


def test_format_dual_time_israel_first_and_lrm():
    text = format_dual_time("13:35", on_day=date(2026, 7, 3))
    assert text.index("ישראל") < text.index("UTC")
    assert text.count("\u200e") == 4
    assert "13:35 UTC ·" not in text  # old UTC-first format


def test_format_dual_time_invalid_returns_empty():
    assert format_dual_time("") == ""
    assert format_dual_time("1:30") == ""  # must be HH:MM
    assert format_dual_time("noon") == ""


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


def test_zone_hhmm_to_utc_israel_summer():
    # 17:00 Israel summer (IDT, UTC+3) → 14:00 UTC
    assert zone_hhmm_to_utc("17:00", ISRAEL, on_day=date(2026, 7, 3)) == "14:00"


def test_zone_hhmm_to_utc_israel_winter():
    # 17:00 Israel winter (IST, UTC+2) → 15:00 UTC — DST-stable local wall clock
    assert zone_hhmm_to_utc("17:00", ISRAEL, on_day=date(2026, 1, 15)) == "15:00"


def test_format_dual_time_from_israel_summer():
    assert (
        format_dual_time_from_israel("17:00", on_day=date(2026, 7, 3))
        == "\u200e17:00\u200e ישראל (\u200e14:00\u200e UTC)"
    )


def test_format_dual_time_from_israel_winter():
    assert (
        format_dual_time_from_israel("17:00", on_day=date(2026, 1, 15))
        == "\u200e17:00\u200e ישראל (\u200e15:00\u200e UTC)"
    )


def test_format_dual_time_from_israel_lrm_and_order():
    text = format_dual_time_from_israel("17:00", on_day=date(2026, 7, 3))
    assert text.index("ישראל") < text.index("UTC")
    assert text.count("\u200e") == 4


def test_format_dual_time_from_israel_invalid_returns_empty():
    assert format_dual_time_from_israel("") == ""
    assert format_dual_time_from_israel("17") == ""
    assert format_dual_time_from_israel("noon") == ""


def test_israel_schedule_time_keys_includes_portfolio_review():
    assert "portfolio_review_time" in ISRAEL_SCHEDULE_TIME_KEYS


def test_dual_times_from_config_formats_israel_anchored_key():
    out = dual_times_from_config(
        {"portfolio_review_time": "15:00", "entry_sim_time": "13:35"}
    )
    assert "portfolio_review_time" in out
    assert "15:00" in out["portfolio_review_time"]
    assert "ישראל" in out["portfolio_review_time"]
    assert "entry_sim_time" in out
    assert "13:35" in out["entry_sim_time"]


def test_schedule_daily_at_israel_uses_jerusalem_tz():
    import schedule
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from trading_pulse.core.schedule_tz import schedule_daily_at_israel

    schedule.clear()
    job = schedule_daily_at_israel("17:00").do(lambda: None)
    assert job.next_run is not None
    # schedule stores next_run as naive local PC time; convert Israel 17:00 → local.
    expected_local = (
        datetime(
            job.next_run.year,
            job.next_run.month,
            job.next_run.day,
            17,
            0,
            tzinfo=ZoneInfo("Asia/Jerusalem"),
        ).astimezone()
    )
    assert job.next_run.hour == expected_local.hour
    assert job.next_run.minute == expected_local.minute
    schedule.clear()

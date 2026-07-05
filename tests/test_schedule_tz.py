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


def test_us_eastern_summer():
    assert utc_hhmm_to_zone("13:35", US_EASTERN, on_day=date(2026, 7, 3)) == "09:35"


def test_entry_moment_israel():
    assert format_local_entry_moment("2026-07-03T06:49:13.231065+00:00") == "03/07 09:49"

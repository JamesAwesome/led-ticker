from datetime import datetime
from zoneinfo import ZoneInfo

from led_ticker.config import ScheduleConfig, ScheduleWindow
from led_ticker.schedule import (
    Scheduler,
    format_schedule_summary,
    to_minutes,
    unreachable_window_indices,
)

MON, FRI, SAT, SUN = 0, 4, 5, 6  # datetime.weekday()


def _sched(*windows):
    return Scheduler.from_config(ScheduleConfig(enabled=True, windows=list(windows)))


def _w(start, end, brightness, days=None):
    return ScheduleWindow(start=start, end=end, brightness=brightness, days=days or [])


def _at(weekday, hh, mm):
    # 2026-06-15 is a Monday; add weekday days to land on the target weekday.
    return datetime(2026, 6, 15 + weekday, hh, mm)


def test_to_minutes():
    assert to_minutes("00:00") == 0
    assert to_minutes("07:30") == 450
    assert to_minutes("23:59") == 1439
    assert to_minutes("24:00") is None
    assert to_minutes("7:00") is None  # must be zero-padded HH
    assert to_minutes("aa:bb") is None
    assert to_minutes(None) is None
    assert to_minutes(700) is None


def test_outside_all_windows_returns_base():
    s = _sched(_w("07:00", "18:00", 100))
    assert s.brightness_for(_at(MON, 6, 0), base=60) == 60


def test_in_window_returns_its_brightness():
    s = _sched(_w("07:00", "18:00", 100))
    assert s.brightness_for(_at(MON, 12, 0), base=60) == 100


def test_boundaries_start_inclusive_end_exclusive():
    s = _sched(_w("07:00", "18:00", 100))
    assert s.brightness_for(_at(MON, 7, 0), base=60) == 100  # start inclusive
    assert s.brightness_for(_at(MON, 18, 0), base=60) == 60  # end exclusive


def test_midnight_wrap_both_halves():
    s = _sched(_w("23:00", "07:00", 0))
    assert s.brightness_for(_at(MON, 23, 30), base=60) == 0  # pre-midnight half
    assert s.brightness_for(_at(MON, 2, 0), base=60) == 0  # post-midnight half
    assert s.brightness_for(_at(MON, 12, 0), base=60) == 60  # midday → base


def test_days_filter_non_wrap():
    s = _sched(_w("09:00", "17:00", 100, days=["mon", "tue", "wed", "thu", "fri"]))
    assert s.brightness_for(_at(FRI, 12, 0), base=60) == 100
    assert s.brightness_for(_at(SAT, 12, 0), base=60) == 60  # weekend → base


def test_wrap_window_owned_by_start_day():
    # Fri 23:00 → Sat 07:00 active; Sat-night not (days=[fri]).
    s = _sched(_w("23:00", "07:00", 0, days=["fri"]))
    assert s.brightness_for(_at(FRI, 23, 30), base=60) == 0  # Fri night
    assert s.brightness_for(_at(SAT, 2, 0), base=60) == 0  # Sat early AM = Fri's tail
    assert s.brightness_for(_at(SAT, 23, 30), base=60) == 60  # Sat night NOT owned
    assert s.brightness_for(_at(SUN, 2, 0), base=60) == 60  # Sun early AM NOT owned


def test_last_matching_window_wins():
    s = _sched(
        _w("07:00", "23:00", 100),  # general
        _w("12:00", "13:00", 30),  # lunch override (later → wins)
    )
    assert s.brightness_for(_at(MON, 12, 30), base=60) == 30
    assert s.brightness_for(_at(MON, 9, 0), base=60) == 100


def test_unreachable_window_detected():
    cfg = ScheduleConfig(
        enabled=True,
        windows=[
            _w("12:00", "13:00", 30),  # fully covered by the next, same days
            _w("07:00", "23:00", 100),
        ],
    )
    # window 0 (12–13) is shadowed by window 1 (07–23) which comes later → wins always
    assert unreachable_window_indices(cfg) == [0]


def test_brightness_for_is_tz_aware():
    # A tz-aware now resolves by its LOCAL wall clock, not UTC.
    s = _sched(_w("07:00", "18:00", 100))
    ny = ZoneInfo("America/New_York")
    # 12:00 local NY is in-window regardless of UTC offset/DST
    assert s.brightness_for(datetime(2026, 6, 15, 12, 0, tzinfo=ny), base=60) == 100


def test_summary_lines():
    cfg = ScheduleConfig(
        enabled=True,
        timezone="America/New_York",
        windows=[_w("23:00", "07:00", 0)],
    )
    lines = format_schedule_summary(cfg, base=60)
    text = "\n".join(lines)
    assert "America/New_York" in text
    assert "overnight" in text  # wrap annotated
    assert "0%" in text and "dark" in text
    assert "base" in text  # base fallback shown

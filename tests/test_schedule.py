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


def test_all_invalid_days_window_is_skipped():
    """A window with days=['funday','noday'] (all invalid) must be skipped.
    brightness_for returns base on any weekday (FIX 4)."""
    s = _sched(_w("09:00", "17:00", 80, days=["funday", "noday"]))
    # The window was skipped — no windows active — base returned for any day
    for wd in range(7):
        assert s.brightness_for(_at(wd, 12, 0), base=60) == 60


def test_empty_days_still_means_every_day():
    """Omitted/empty days must still match every day (FIX 4 — no regression)."""
    s = _sched(_w("09:00", "17:00", 80, days=[]))
    for wd in range(7):
        assert s.brightness_for(_at(wd, 12, 0), base=60) == 80


def test_unreachable_reports_original_index_with_malformed_first():
    """When a malformed-time window precedes a shadowed one,
    unreachable_window_indices must point at the SHADOWED window's original
    index, not the malformed one (FIX 5)."""
    from led_ticker.config import ScheduleConfig, ScheduleWindow

    # windows[0]: malformed time (will be skipped by to_minutes → None)
    # windows[1]: genuinely shadowed (09:00–17:00, brightness=30)
    # windows[2]: broad cover (08:00–18:00, brightness=100) — shadows [1]
    cfg = ScheduleConfig(
        enabled=True,
        windows=[
            ScheduleWindow(start="9:00", end="17:00", brightness=30),  # 0: bad
            ScheduleWindow(start="09:00", end="17:00", brightness=30),  # 1: shadowed
            ScheduleWindow(start="08:00", end="18:00", brightness=100),  # 2: broad
        ],
    )
    result = unreachable_window_indices(cfg)
    # Must report index 1 (shadowed), NOT index 0 (malformed, skipped)
    assert result == [1]


def test_summary_invalid_time_window_marked():
    """format_schedule_summary must mark a window with invalid times as
    '(invalid — see errors)' instead of rendering it as a normal row (FIX 7)."""
    from led_ticker.config import ScheduleConfig, ScheduleWindow

    cfg = ScheduleConfig(
        enabled=True,
        timezone="",
        windows=[
            ScheduleWindow(start="bad", end="17:00", brightness=80),  # invalid start
            ScheduleWindow(start="07:00", end="18:00", brightness=100),
        ],
    )
    lines = format_schedule_summary(cfg, base=60)
    text = "\n".join(lines)
    assert "invalid" in text
    assert "see errors" in text
    # The valid window should still render normally
    assert "07:00" in text and "100%" in text


class TestTimeWindow:
    """Shared window primitive — the same matching logic brightness windows use."""

    def test_same_day_window(self):
        from led_ticker.schedule import TimeWindow

        w = TimeWindow(start=9 * 60, end=17 * 60, days=frozenset())
        assert w.active_at(9 * 60, 0) is True  # 09:00 inclusive
        assert w.active_at(16 * 60 + 59, 0) is True
        assert w.active_at(17 * 60, 0) is False  # end exclusive
        assert w.active_at(8 * 60, 0) is False

    def test_overnight_wrap(self):
        from led_ticker.schedule import TimeWindow

        w = TimeWindow(start=22 * 60, end=6 * 60, days=frozenset())
        assert w.active_at(23 * 60, 0) is True
        assert w.active_at(5 * 60, 0) is True
        assert w.active_at(12 * 60, 0) is False

    def test_wrap_tail_owned_by_previous_day(self):
        from led_ticker.schedule import TimeWindow

        # Window starts Friday 22:00 (weekday 4); the 02:00 tail on Saturday
        # (weekday 5) belongs to Friday's day filter.
        w = TimeWindow(start=22 * 60, end=6 * 60, days=frozenset({4}))
        assert w.active_at(23 * 60, 4) is True  # Fri 23:00
        assert w.active_at(2 * 60, 5) is True  # Sat 02:00 — Friday's tail
        assert w.active_at(2 * 60, 4) is False  # Fri 02:00 — Thursday's tail

    def test_window_subclass_field_order(self):
        from led_ticker.schedule import _Window

        w = _Window(start=0, end=60, days=frozenset(), brightness=50)
        assert (w.start, w.end, w.brightness) == (0, 60, 50)

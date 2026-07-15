"""VisibilitySchedule model + strict parser + timezone global."""

from datetime import datetime

import pytest

from led_ticker import schedule
from led_ticker.schedule import (
    parse_visibility_schedule,
    set_schedule_timezone,
)


@pytest.fixture(autouse=True)
def _reset_tz():
    yield
    set_schedule_timezone("")


class TestParse:
    def test_minimal_window(self):
        s = parse_visibility_schedule({"start": "09:00", "end": "17:00"}, location="w")
        assert s.window.start == 9 * 60
        assert s.window.end == 17 * 60
        assert s.window.days == frozenset()

    def test_days_parsed_to_weekday_ints(self):
        s = parse_visibility_schedule(
            {"start": "09:00", "end": "17:00", "days": ["mon", "fri"]},
            location="w",
        )
        assert s.window.days == frozenset({0, 4})

    def test_not_a_table(self):
        with pytest.raises(ValueError, match=r"w: schedule must be an inline table"):
            parse_visibility_schedule("09:00-17:00", location="w")

    def test_brightness_key_points_at_display_schedule(self):
        with pytest.raises(ValueError, match=r"\[display\.schedule\]"):
            parse_visibility_schedule(
                {"start": "09:00", "end": "17:00", "brightness": 0}, location="w"
            )

    def test_unknown_key(self):
        with pytest.raises(ValueError, match=r"unknown schedule key\(s\) \['stop'\]"):
            parse_visibility_schedule({"start": "09:00", "stop": "17:00"}, location="w")

    def test_bad_time(self):
        with pytest.raises(ValueError, match=r"start '9am' is not a valid"):
            parse_visibility_schedule({"start": "9am", "end": "17:00"}, location="w")

    def test_missing_end(self):
        with pytest.raises(ValueError, match=r"end None is not a valid"):
            parse_visibility_schedule({"start": "09:00"}, location="w")

    def test_start_equals_end(self):
        with pytest.raises(ValueError, match=r"start and end are equal"):
            parse_visibility_schedule({"start": "09:00", "end": "09:00"}, location="w")

    def test_bad_day_name(self):
        with pytest.raises(ValueError, match=r"invalid day name\(s\) \['monday'\]"):
            parse_visibility_schedule(
                {"start": "09:00", "end": "17:00", "days": ["monday"]}, location="w"
            )

    def test_days_not_a_list(self):
        with pytest.raises(ValueError, match=r"days must be a list"):
            parse_visibility_schedule(
                {"start": "09:00", "end": "17:00", "days": "mon"}, location="w"
            )


class TestIsActive:
    def _sched(self, start="09:00", end="17:00", days=None):
        raw = {"start": start, "end": end}
        if days is not None:
            raw["days"] = days
        return parse_visibility_schedule(raw, location="w")

    def test_active_with_injected_now(self):
        s = self._sched()
        # Wednesday 2026-07-15 12:00
        assert s.is_active(datetime(2026, 7, 15, 12, 0)) is True
        assert s.is_active(datetime(2026, 7, 15, 18, 0)) is False

    def test_overnight_wrap_active(self):
        s = self._sched(start="17:00", end="09:00")
        assert s.is_active(datetime(2026, 7, 15, 23, 0)) is True
        assert s.is_active(datetime(2026, 7, 15, 12, 0)) is False
        assert s.is_active(datetime(2026, 7, 16, 3, 0)) is True

    def test_day_filter(self):
        # 2026-07-15 is a Wednesday
        s = self._sched(days=["wed"])
        assert s.is_active(datetime(2026, 7, 15, 12, 0)) is True
        assert s.is_active(datetime(2026, 7, 16, 12, 0)) is False  # Thursday

    def test_now_default_uses_module_clock(self):
        # Full-day-minus-a-minute window: whatever "now" is, this is active
        # (except exactly 23:59, a 1-in-1440 flake we accept in a smoke test).
        s = self._sched(start="00:00", end="23:59")
        assert s.is_active() is True


class TestSetScheduleTimezone:
    def test_valid_zone_is_set(self):
        set_schedule_timezone("America/New_York")
        assert schedule._SCHEDULE_TZ is not None
        assert str(schedule._SCHEDULE_TZ) == "America/New_York"

    def test_empty_resets_to_system_local(self):
        set_schedule_timezone("America/New_York")
        set_schedule_timezone("")
        assert schedule._SCHEDULE_TZ is None

    def test_invalid_zone_warns_and_falls_back(self, caplog):
        set_schedule_timezone("America/New_York")
        with caplog.at_level("WARNING"):
            set_schedule_timezone("Not/AZone")
        assert schedule._SCHEDULE_TZ is None
        assert "invalid timezone" in caplog.text

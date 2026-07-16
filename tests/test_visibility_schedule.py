"""VisibilitySchedule model + strict parser + timezone global."""

import gc
from datetime import datetime

import pytest

from led_ticker import schedule
from led_ticker.schedule import (
    bind_schedule,
    parse_visibility_schedule,
    schedule_for,
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


class TestIsActiveConsultsConfiguredTimezone:
    """Fix F.1a (2026-07-15): with no `now` arg, `is_active()` must actually
    CONSULT `datetime.now(_SCHEDULE_TZ)` — the tz set via
    `set_schedule_timezone` — not just happen to agree with system local
    time. Mutation-proof via a recording `datetime` subclass so a change
    that drops the `tz=` argument (e.g. `datetime.now()`) is caught even
    when the test machine happens to be in the configured zone."""

    def test_inside_window_consults_now_with_schedule_tz(self, monkeypatch):
        recorded = {}

        class _Fixed(datetime):
            @classmethod
            def now(cls, tz=None):
                recorded["tz"] = tz
                return cls(2026, 7, 15, 12, 0, tzinfo=tz)  # inside 09:00-17:00

        monkeypatch.setattr(schedule, "datetime", _Fixed)
        set_schedule_timezone("America/New_York")
        s = parse_visibility_schedule({"start": "09:00", "end": "17:00"}, location="w")
        assert s.is_active() is True
        assert recorded["tz"] is schedule._SCHEDULE_TZ
        assert str(recorded["tz"]) == "America/New_York"

    def test_outside_window_consults_now_with_schedule_tz(self, monkeypatch):
        recorded = {}

        class _Fixed(datetime):
            @classmethod
            def now(cls, tz=None):
                recorded["tz"] = tz
                return cls(2026, 7, 15, 20, 0, tzinfo=tz)  # outside 09:00-17:00

        monkeypatch.setattr(schedule, "datetime", _Fixed)
        set_schedule_timezone("America/New_York")
        s = parse_visibility_schedule({"start": "09:00", "end": "17:00"}, location="w")
        assert s.is_active() is False
        assert recorded["tz"] is schedule._SCHEDULE_TZ
        assert str(recorded["tz"]) == "America/New_York"


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


def _sched():
    return parse_visibility_schedule({"start": "09:00", "end": "17:00"}, location="t")


class TestBindingRegistry:
    def test_unbound_widget_has_no_schedule(self):
        class W:
            pass

        assert schedule_for(W()) is None

    def test_bind_then_lookup(self):
        class W:
            pass

        w = W()
        s = _sched()
        bind_schedule(w, s)
        assert schedule_for(w) is s

    def test_rebind_overwrites(self):
        class W:
            pass

        w = W()
        bind_schedule(w, _sched())
        s2 = parse_visibility_schedule({"start": "10:00", "end": "11:00"}, location="t")
        bind_schedule(w, s2)
        assert schedule_for(w) is s2

    def test_binding_evicted_on_gc(self):
        class W:
            pass

        w = W()
        bind_schedule(w, _sched())
        key = id(w)
        del w
        gc.collect()
        assert key not in schedule._BINDINGS

    def test_slotted_attrs_widget_is_bindable(self):
        # Real widgets are slotted @attrs.define classes; attrs' default
        # weakref_slot=True makes them weakref-able. TickerMessage is the
        # canonical case.
        from led_ticker.widgets.message import TickerMessage

        w = TickerMessage("hello")
        s = _sched()
        bind_schedule(w, s)
        assert schedule_for(w) is s

    def test_stale_ref_entry_treated_as_unbound(self):
        """Fix F.5 (2026-07-15): `schedule_for` guards against an id() reuse
        where the weakref no longer resolves to the queried widget (a stale
        entry) — inject a mismatched entry directly (bypassing the normal
        `bind_schedule` weakref-callback wiring) and confirm the ref()
        mismatch check (`schedule_for`'s `if ref() is not widget`) rejects
        it rather than returning the stale schedule."""

        class W:
            pass

        w = W()
        sched = _sched()
        key = id(w)
        schedule._BINDINGS[key] = (lambda: object(), sched)
        try:
            assert schedule_for(w) is None
        finally:
            schedule._BINDINGS.pop(key, None)

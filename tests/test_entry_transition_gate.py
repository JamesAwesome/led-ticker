"""The inter-section ENTRY transition must not use a stale out-of-range outgoing
widget — otherwise a countdown that crossed its date would flash its negative
count as the transition's outgoing frame. Same reasoning applies to a widget
whose bound `schedule = {...}` has gone inactive between sections (Fix 5,
2026-07-15) — it must not flash as the transition's outgoing frame either."""

from datetime import date, timedelta
from typing import cast

from led_ticker.app.run import _entry_transition_active
from led_ticker.schedule import VisibilitySchedule, bind_schedule
from led_ticker.widgets.count import TickerCountdown
from led_ticker.widgets.message import TickerMessage


def _trans():
    return object()  # any non-None entry transition object


class _InactiveSchedule:
    def is_active(self, now=None):
        return False


class _ActiveSchedule:
    def is_active(self, now=None):
        return True


def test_active_with_in_range_outgoing():
    incoming = object()
    in_range = TickerCountdown("X", countdown_date=date.today() + timedelta(days=1))
    assert _entry_transition_active(in_range, incoming, _trans()) is True


def test_skips_out_of_range_outgoing():
    incoming = object()
    out_of_range = TickerCountdown("X", countdown_date=date.today() - timedelta(days=1))
    assert _entry_transition_active(out_of_range, incoming, _trans()) is False


def test_existing_none_guards_hold():
    incoming = object()
    in_range = TickerCountdown("X", countdown_date=date.today() + timedelta(days=1))
    assert _entry_transition_active(None, incoming, _trans()) is False
    assert _entry_transition_active(in_range, None, _trans()) is False
    assert _entry_transition_active(in_range, incoming, None) is False


def test_skips_schedule_inactive_outgoing():
    incoming = object()
    outgoing = TickerMessage("outgoing")
    bind_schedule(outgoing, cast(VisibilitySchedule, _InactiveSchedule()))
    assert _entry_transition_active(outgoing, incoming, _trans()) is False


def test_active_with_schedule_active_outgoing():
    incoming = object()
    outgoing = TickerMessage("outgoing")
    bind_schedule(outgoing, cast(VisibilitySchedule, _ActiveSchedule()))
    assert _entry_transition_active(outgoing, incoming, _trans()) is True

"""The inter-section ENTRY transition must not use a stale out-of-range outgoing
widget — otherwise a countdown that crossed its date would flash its negative
count as the transition's outgoing frame."""

from datetime import date, timedelta

from led_ticker.app.run import _entry_transition_active
from led_ticker.widgets.count import TickerCountdown


def _trans():
    return object()  # any non-None entry transition object


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

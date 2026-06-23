"""_expand_sources drops widgets that opt out of a pass via should_display()."""

from datetime import date, timedelta

from led_ticker.ticker import _expand_sources
from led_ticker.widgets.count import TickerCountdown, TickerCountup


class _Plain:
    """A widget with no should_display() — always shown."""


class _Hidden:
    def should_display(self):
        return False


class _Shown:
    def should_display(self):
        return True


def test_widget_without_should_display_is_kept():
    w = _Plain()
    assert _expand_sources([w]) == [w]


def test_should_display_false_is_dropped():
    assert _expand_sources([_Hidden()]) == []


def test_should_display_true_is_kept():
    w = _Shown()
    assert _expand_sources([w]) == [w]


def test_out_of_range_countdown_is_dropped():
    # Behavior change: a countdown past its date now disappears (was: rendered -N).
    past = TickerCountdown("X", countdown_date=date.today() - timedelta(days=1))
    assert _expand_sources([past]) == []


def test_in_range_countup_is_kept():
    cu = TickerCountup("X", countup_date=date.today() - timedelta(days=1))
    assert _expand_sources([cu]) == [cu]


def test_should_display_raising_keeps_widget():
    class _Boom:
        def should_display(self):
            raise RuntimeError("boom")

    w = _Boom()
    # A visibility check must never crash the render loop or silently hide content.
    assert _expand_sources([w]) == [w]

"""countup/countdown shared-base widgets: _days math, should_display, render."""

from datetime import date, timedelta

from led_ticker.widgets.count import TickerCountdown, TickerCountup


def _future(days=10):
    return date.today() + timedelta(days=days)


def _past(days=10):
    return date.today() - timedelta(days=days)


def test_countdown_days_positive_for_future():
    assert TickerCountdown("Launch", countdown_date=_future(5))._days() == 5


def test_countdown_days_zero_today():
    assert TickerCountdown("Launch", countdown_date=date.today())._days() == 0


def test_countdown_days_negative_for_past():
    assert TickerCountdown("Launch", countdown_date=_past(3))._days() == -3


def test_countup_days_positive_for_past():
    assert TickerCountup("Since", countup_date=_past(7))._days() == 7


def test_countup_days_zero_today():
    assert TickerCountup("Since", countup_date=date.today())._days() == 0


def test_countup_days_negative_for_future():
    assert TickerCountup("Since", countup_date=_future(4))._days() == -4


def test_should_display_in_range_true():
    assert TickerCountdown("X", countdown_date=_future(1)).should_display() is True
    assert TickerCountup("X", countup_date=_past(1)).should_display() is True


def test_should_display_out_of_range_false():
    assert TickerCountdown("X", countdown_date=_past(1)).should_display() is False
    assert TickerCountup("X", countup_date=_future(1)).should_display() is False


def test_countup_renders_label_and_count(canvas):
    # The `canvas` fixture (tests/conftest.py:45) is the test stub canvas that
    # writes real pixels; draw() returns the same canvas + an advanced cursor.
    w = TickerCountup("Days", countup_date=_past(42))
    result_canvas, cursor = w.draw(canvas, 0)
    assert result_canvas is canvas
    assert cursor > 0


def test_registered_names():
    from led_ticker.widgets import get_widget_class

    assert get_widget_class("countdown") is TickerCountdown
    assert get_widget_class("countup") is TickerCountup


def test_back_compat_countdown_import():
    # The move must not break the historical import path.
    from led_ticker.widgets.message import TickerCountdown as FromMessage

    assert FromMessage is TickerCountdown

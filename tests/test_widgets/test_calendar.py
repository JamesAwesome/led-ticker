"""Tests for the calendar widget."""

from led_ticker.widgets import get_widget_class


def test_calendar_registered():
    cls = get_widget_class("calendar")
    assert cls.__name__ == "Calendar"

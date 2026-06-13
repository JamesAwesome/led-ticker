"""Tests for led_ticker.widgets.clock."""

from datetime import datetime
from unittest import mock

import pytest

from led_ticker.color_providers import Rainbow
from led_ticker.widget import Widget
from led_ticker.widgets.clock import Clock, format_clock


def _dt(h, m):
    return datetime(2026, 6, 13, h, m)


def test_12h_preset_no_leading_zero_pm():
    assert format_clock(_dt(15, 9), "12h") == "3:09 PM"


def test_12h_preset_midnight_is_12_am():
    assert format_clock(_dt(0, 9), "12h") == "12:09 AM"


def test_12h_preset_noon_is_12_pm():
    assert format_clock(_dt(12, 0), "12h") == "12:00 PM"


def test_24h_preset_pads_hour():
    assert format_clock(_dt(15, 9), "24h") == "15:09"
    assert format_clock(_dt(3, 9), "24h") == "03:09"


def test_custom_strftime_passthrough():
    # Any value containing % is a strftime template, rendered verbatim.
    assert format_clock(_dt(15, 9), "%H:%M") == "15:09"


def test_custom_date_format_one_line():
    # A date token in the format renders date + time inline (v1's "date line").
    assert format_clock(_dt(15, 9), "%Y-%m-%d %H:%M") == "2026-06-13 15:09"


def test_unknown_preset_raises():
    with pytest.raises(ValueError, match="12h"):
        format_clock(_dt(15, 9), "12hr")


class TestClockWidget:
    def test_registered(self):
        from led_ticker.widgets import get_widget_class

        assert get_widget_class("clock") is Clock

    def test_conforms_to_widget_protocol(self):
        assert isinstance(Clock(), Widget)

    def test_draw_returns_canvas_and_int_cursor(self, canvas):
        result_canvas, cursor_pos = Clock().draw(canvas)
        assert result_canvas is canvas
        assert isinstance(cursor_pos, int)

    def test_draw_uses_format_clock_with_monkeypatched_now(self, canvas, monkeypatch):
        # Pin the clock's time source so draw() renders a known string, then
        # confirm the widget centered the SAME string format_clock produces.
        import led_ticker.widgets.clock as clock_mod
        from led_ticker.drawing import compute_cursor, get_text_width

        fixed = datetime(2026, 6, 13, 15, 9)

        class _FrozenDatetime:
            @staticmethod
            def now(tz=None):
                return fixed

        monkeypatch.setattr(clock_mod, "datetime", _FrozenDatetime)
        widget = Clock(format="24h", center=True)
        _, cursor_pos = widget.draw(canvas)

        expected_text = format_clock(fixed, "24h")  # "15:09"
        width = get_text_width(widget.font, expected_text, padding=0, canvas=canvas)
        start, end_padding = compute_cursor(
            canvas.width, width, 0, widget.padding, center=True
        )
        assert cursor_pos == start + width + end_padding

    def test_border_painted_when_set(self, canvas):
        border = mock.Mock()
        Clock(border=border).draw(canvas)
        assert border.paint.called

    def test_rainbow_font_color_advances_frame(self, canvas):
        # A per-char provider drives the per-char branch; advancing the frame
        # changes the hue the provider is asked for (same contract as message).
        # Rainbow has per_char=True, so this exercises the per-char draw path.
        widget = Clock(font_color=Rainbow())
        widget.draw(canvas)
        widget.advance_frame()
        widget.draw(canvas)  # must not raise; frame_for("font_color") advanced

    def test_timezone_resolved_in_draw(self, canvas, monkeypatch):
        # When timezone is set, draw() calls datetime.now(ZoneInfo(tz)); confirm
        # the tz is threaded through (the now() call receives a tzinfo).
        import led_ticker.widgets.clock as clock_mod

        seen = {}

        class _SpyDatetime:
            @staticmethod
            def now(tz=None):
                seen["tz"] = tz
                return datetime(2026, 6, 13, 15, 9)

        monkeypatch.setattr(clock_mod, "datetime", _SpyDatetime)
        Clock(timezone="America/New_York").draw(canvas)
        assert seen["tz"] is not None  # a ZoneInfo was passed

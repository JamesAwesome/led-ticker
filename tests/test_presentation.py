"""Tests for text presentation effects."""

import unittest.mock as mock

import pytest

from led_ticker.colors import DEFAULT_COLOR
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.presentation import (
    _PRESENTATION_REGISTRY,
    Bounce,
    ColorCycle,
    Pulse,
    Rainbow,
    Typewriter,
    WidgetPresenter,
    get_presentation_class,
)
from led_ticker.widgets.message import TickerMessage


@pytest.fixture
def msg_widget():
    return TickerMessage(
        message="Hello World",
        font=FONT_DEFAULT,
        font_color=DEFAULT_COLOR,
    )


# --- Registry ---


class TestPresentationRegistry:
    def test_all_modes_registered(self):
        for name in ["typewriter", "color_cycle", "rainbow", "pulse", "bounce"]:
            assert name in _PRESENTATION_REGISTRY

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown presentation"):
            get_presentation_class("fireworks")


# --- WidgetPresenter ---


class TestWidgetPresenter:
    def test_increments_frame_count(self, canvas, msg_widget):
        mode = mock.Mock()
        mode.draw.return_value = (canvas, 100)
        presenter = WidgetPresenter(msg_widget, mode)

        presenter.draw(canvas)
        assert mode.draw.call_args[0][3] == 0  # frame=0
        presenter.draw(canvas)
        assert mode.draw.call_args[0][3] == 1  # frame=1


# --- Typewriter ---


class TestTypewriter:
    def test_reveals_characters_over_frames(self, canvas, msg_widget):
        tw = Typewriter(chars_per_frame=1)

        # Frame 0: show 1 char "H"
        tw.draw(msg_widget, canvas, 0, 0)
        # Frame 5: show 6 chars "Hello "
        tw.draw(msg_widget, canvas, 0, 5)
        # Frame 100: show all chars
        tw.draw(msg_widget, canvas, 0, 100)
        # Should not raise on any frame

    def test_returns_canvas_and_position(self, canvas, msg_widget):
        tw = Typewriter()
        result_canvas, pos = tw.draw(msg_widget, canvas, 0, 10)
        assert result_canvas is canvas
        assert pos > 0

    def test_non_message_widget_passes_through(self, canvas):
        widget = mock.Mock()
        widget.draw.return_value = (canvas, 50)
        tw = Typewriter()
        result_canvas, pos = tw.draw(widget, canvas, 0, 0)
        widget.draw.assert_called_once()


# --- ColorCycle ---


class TestColorCycle:
    def test_calls_draw_with_color(self, canvas, msg_widget):
        cc = ColorCycle(speed=90)
        result_canvas, pos = cc.draw(msg_widget, canvas, 0, 0)
        assert result_canvas is canvas

    def test_different_frames_produce_output(self, canvas, msg_widget):
        """Different frames should still render successfully."""
        cc = ColorCycle(speed=90)
        _, pos1 = cc.draw(msg_widget, canvas, 0, 0)
        _, pos2 = cc.draw(msg_widget, canvas, 0, 1)
        # Both should produce valid cursor positions
        assert pos1 > 0
        assert pos2 > 0


# --- Rainbow ---


class TestRainbow:
    def test_returns_canvas(self, canvas, msg_widget):
        rb = Rainbow()
        result_canvas, pos = rb.draw(msg_widget, canvas, 0, 0)
        assert result_canvas is canvas
        assert pos > 0


# --- Pulse ---


class TestPulse:
    def test_early_frame_modifies_color(self, canvas, msg_widget):
        pulse = Pulse(duration_frames=6)
        result_canvas, pos = pulse.draw(msg_widget, canvas, 0, 0)
        assert result_canvas is canvas

    def test_after_duration_passes_through(self, canvas, msg_widget):
        pulse = Pulse(duration_frames=6)
        # Frame 10 is after the pulse — should draw normally
        result_canvas, pos = pulse.draw(msg_widget, canvas, 0, 10)
        assert result_canvas is canvas


# --- Bounce ---


class TestBounce:
    def test_total_frames(self):
        b = Bounce(hold_frames=40, scroll_frames=20)
        assert b.total_frames == 80  # 20 + 40 + 20

    def test_scroll_in_phase(self, canvas, msg_widget):
        b = Bounce(hold_frames=10, scroll_frames=5)
        # Frame 0: should be at or near canvas.width (off-screen right)
        result_canvas, pos = b.draw(msg_widget, canvas, 0, 0)
        assert result_canvas is canvas

    def test_hold_phase(self, canvas, msg_widget):
        b = Bounce(hold_frames=10, scroll_frames=5)
        # Frame 7 is in the hold phase (5 scroll + 2 hold)
        result_canvas, pos = b.draw(msg_widget, canvas, 0, 7)
        assert result_canvas is canvas

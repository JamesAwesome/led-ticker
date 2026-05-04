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

    def test_pause_freezes_frame_count(self, canvas, msg_widget):
        # Regression test: a Bounce/Typewriter/Rainbow presenter on the
        # outgoing widget of a transition would advance frame_count during
        # the transition's compositing draws, and re-enter the next section
        # at a wrong phase.
        mode = mock.Mock()
        mode.draw.return_value = (canvas, 100)
        presenter = WidgetPresenter(msg_widget, mode)

        presenter.draw(canvas)  # frame=0 -> count becomes 1
        presenter.pause()
        presenter.draw(canvas)  # should still pass frame=1
        presenter.draw(canvas)  # still frame=1
        assert mode.draw.call_args[0][3] == 1
        assert presenter.frame_count == 1

        presenter.resume()
        presenter.draw(canvas)
        assert mode.draw.call_args[0][3] == 1  # this draw used frame=1
        assert presenter.frame_count == 2  # then advanced


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

    def test_caches_content_width(self, canvas, msg_widget):
        # Regression: get_text_width was called every frame for fixed text.
        # On the bigsign at 20fps that's ~30 char-widths/frame × 600 frames
        # for a 30s message — ~18K wasted C-calls. The module-level
        # `_TEXT_WIDTH_CACHE` in `drawing.py` keys on
        # `(id(font), text, padding, scale)`, so repeated draws with
        # the same font + message hit the cache from the second call
        # onward. Pin that the cache doesn't grow per frame.
        from led_ticker.drawing import _TEXT_WIDTH_CACHE

        _TEXT_WIDTH_CACHE.clear()

        tw = Typewriter(chars_per_frame=1)
        tw.draw(msg_widget, canvas, 0, 0)
        size_after_first = len(_TEXT_WIDTH_CACHE)
        for f in range(1, 20):
            tw.draw(msg_widget, canvas, 0, f)
        # Cache should be unchanged across 19 subsequent draws — same
        # (font, message, padding, scale) key hits the cache each time.
        assert len(_TEXT_WIDTH_CACHE) == size_after_first, (
            f"cache grew from {size_after_first} to "
            f"{len(_TEXT_WIDTH_CACHE)} entries across 19 draws — caching "
            f"broken"
        )

    def test_y_offset_threaded_to_draw_text(self, canvas, msg_widget, monkeypatch):
        # Regression: Typewriter hardcoded y=12, dropping y_offset from
        # vertical transitions like push_up.
        import led_ticker.presentation as presentation

        captured: list[int] = []

        def fake_draw(canvas, font, x, y, color, text):
            captured.append(y)
            return 10  # advance width

        monkeypatch.setattr(presentation, "draw_text", fake_draw)

        tw = Typewriter()
        tw.draw(msg_widget, canvas, 0, 0, y_offset=5)
        assert captured == [12 + 5]

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


class TestBgColorForwarding:
    def test_bg_color_returns_wrapped_widget_bg(self):
        from led_ticker.presentation import Rainbow, WidgetPresenter
        from led_ticker.widgets.message import TickerMessage

        # Need a stub Color (graphics.Color isn't available in unit tests
        # without going through the compat shim).
        class StubColor:
            red, green, blue = 10, 20, 30

        msg = TickerMessage(message="hi", bg_color=StubColor())
        wrapped = WidgetPresenter(msg, Rainbow())
        assert wrapped.bg_color is msg.bg_color

    def test_bg_color_returns_none_when_widget_has_no_bg(self):
        from led_ticker.presentation import Rainbow, WidgetPresenter
        from led_ticker.widgets.message import TickerMessage

        msg = TickerMessage(message="hi")  # bg_color defaults to None
        wrapped = WidgetPresenter(msg, Rainbow())
        assert wrapped.bg_color is None

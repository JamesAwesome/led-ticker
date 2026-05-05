"""Tests for led_ticker.widgets.message."""

from datetime import date

from led_ticker.colors import DEFAULT_COLOR, RGB_WHITE
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widget import Widget
from led_ticker.widgets.message import TickerCountdown, TickerMessage


class TestTickerMessage:
    def test_conforms_to_widget_protocol(self):
        msg = TickerMessage(message="hello")
        assert isinstance(msg, Widget)

    def test_draw_centered(self, canvas):
        msg = TickerMessage(
            message="This is a message",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
        )
        _, cursor_pos = msg.draw(canvas)
        assert cursor_pos == 160  # centered fills canvas width

    def test_draw_uncentered(self, canvas):
        msg = TickerMessage(
            message="This is a message",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            center=False,
        )
        _, cursor_pos = msg.draw(canvas)
        # 17 chars * 6px = 102px text + 6px padding = 108
        assert cursor_pos == 108

    def test_draw_overflow_not_centered(self, canvas):
        long_text = "This is a message" * 10
        msg = TickerMessage(
            message=long_text,
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
        )
        _, cursor_pos = msg.draw(canvas)
        # 170 chars * 6px = 1020px + 6px padding = 1026
        assert cursor_pos == 1026

    def test_draw_with_font_color_kwarg(self, canvas):
        msg = TickerMessage(
            message="test",
            font=FONT_DEFAULT,
            font_color=DEFAULT_COLOR,
        )
        # Should use the kwarg color, not the instance color
        canvas2, _ = msg.draw(canvas, font_color=RGB_WHITE)
        assert canvas2 is canvas

    def test_draw_returns_canvas(self, canvas):
        msg = TickerMessage(message="hi")
        result_canvas, _ = msg.draw(canvas)
        assert result_canvas is canvas

    def test_emoji_detected_only_for_slug_pattern(self):
        # Real emoji slugs trigger the emoji renderer
        assert TickerMessage(message=":taco: lunch")._has_emoji is True
        assert TickerMessage(message="hi :baseball:")._has_emoji is True

    def test_url_does_not_trigger_emoji_path(self):
        # Two-colon strings that are NOT emoji slugs (URLs, timestamps,
        # "key: value: more") must not be routed through the emoji renderer.
        assert TickerMessage(message="https://x.com/path")._has_emoji is False
        assert TickerMessage(message="Now: 12:30 PM")._has_emoji is False
        assert TickerMessage(message="A: B: C")._has_emoji is False

    def test_emoji_pattern_rejects_uppercase_and_digits(self):
        # Pattern is :[a-z_]+: — uppercase or digits in the slug shouldn't match.
        assert TickerMessage(message=":Taco: lunch")._has_emoji is False
        assert TickerMessage(message=":taco1: lunch")._has_emoji is False


class TestTickerCountdown:
    def test_conforms_to_widget_protocol(self):
        cd = TickerCountdown(message="Test", countdown_date=date(2030, 1, 1))
        assert isinstance(cd, Widget)

    def test_draw_shows_days(self, canvas):
        future = date(2099, 12, 31)
        cd = TickerCountdown(
            message="Future",
            countdown_date=future,
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
        )
        _, cursor_pos = cd.draw(canvas)
        # Should render without error and return a position
        assert cursor_pos > 0

    def test_draw_past_date_negative_days(self, canvas):
        past = date(2020, 1, 1)
        cd = TickerCountdown(
            message="Past",
            countdown_date=past,
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
        )
        # Should not raise, just show negative days
        _, cursor_pos = cd.draw(canvas)
        assert cursor_pos > 0


class TestBgColor:
    def test_bg_color_default_is_none(self):
        msg = TickerMessage(message="hi")
        assert msg.bg_color is None

    def test_bg_color_accepts_color(self):
        from rgbmatrix.graphics import Color

        bg = Color(20, 40, 60)
        msg = TickerMessage(message="hi", bg_color=bg)
        assert msg.bg_color is bg

    def test_countdown_bg_color_default_is_none(self):
        cd = TickerCountdown(message="X", countdown_date=date(2099, 1, 1))
        assert cd.bg_color is None

    def test_countdown_accepts_bg_color(self):
        from rgbmatrix.graphics import Color

        cd = TickerCountdown(
            message="X", countdown_date=date(2099, 1, 1), bg_color=Color(1, 2, 3)
        )
        assert cd.bg_color.red == 1


class TestTickerMessageColorProvider:
    """TickerMessage materializes a Color from font_color (a
    ColorProvider) per draw call. Per-char providers iterate chars."""

    def test_constructor_wraps_raw_color_in_constant_provider(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage("HELLO", font_color=Color(255, 0, 0))
        assert isinstance(widget.font_color, _ConstantColor)

    def test_constructor_passes_through_existing_provider(self):
        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.message import TickerMessage

        rainbow = Rainbow()
        widget = TickerMessage("HELLO", font_color=rainbow)
        assert widget.font_color is rainbow

    def test_advance_frame_increments_count(self):
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage("HI")
        assert widget._frame_count == 0
        widget.advance_frame()
        assert widget._frame_count == 1


class TestTickerMessageAnimation:
    """`animation` field consumed by TickerMessage's draw — typewriter
    slices, bounce repositions."""

    def test_typewriter_set_via_constructor(self):
        from led_ticker.animations import Typewriter
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage("HELLO", animation=Typewriter())
        assert isinstance(widget.animation, Typewriter)

    def test_no_animation_by_default(self):
        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage("HELLO")
        assert widget.animation is None


class TestTickerCountdownColorProvider:
    def test_constructor_wraps_raw_color_in_constant_provider(self):
        from datetime import date

        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.message import TickerCountdown

        widget = TickerCountdown(
            "Days", countdown_date=date(2027, 1, 1), font_color=Color(255, 0, 0)
        )
        assert isinstance(widget.font_color, _ConstantColor)

    def test_advance_frame_increments_count(self):
        from datetime import date

        from led_ticker.widgets.message import TickerCountdown

        widget = TickerCountdown("Days", countdown_date=date(2027, 1, 1))
        assert widget._frame_count == 0
        widget.advance_frame()
        assert widget._frame_count == 1


class TestHiresPerCharCursorMatchesHolistic:
    """Regression: HiresFont per-char rendering must return the same
    `cursor_pos` as `get_text_width(font, message, canvas)` on the
    SAME canvas, otherwise scroll detection in `_swap_and_scroll`
    disagrees with the visible per-char render and text gets drawn
    off-canvas without triggering scroll.

    Tripwire for the on-hardware bug where "INTER BOLD RAINBOW" with
    Inter-Bold @ 24 measured at 64 logical (canvas.width) but the
    per-char loop accumulated 72 logical worth of ceil-rounded
    advances — last char "W" rendered at logical x=68 → real x=272,
    off-screen, no scroll triggered."""

    def test_per_char_cursor_pos_matches_holistic_measure(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.color_providers import Rainbow
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.message import TickerMessage

        font = resolve_font("Inter-Bold", 24)
        widget = TickerMessage(
            "INTER BOLD RAINBOW",
            font=font,
            font_color=Rainbow(),
            padding=0,  # remove end-padding to compare cursor_pos directly
        )
        real = _StubCanvas(width=256, height=64)
        canvas = ScaledCanvas(real, scale=4)

        # Holistic measure (one ceil-div on real-px total)
        holistic = get_text_width(font, "INTER BOLD RAINBOW", padding=0, canvas=canvas)

        # Per-char render path: ask the widget to draw and return cursor_pos.
        _, cursor_pos = widget.draw(canvas, cursor_pos=0)

        assert cursor_pos == holistic, (
            f"Per-char cursor drift: holistic={holistic}, returned={cursor_pos}. "
            f"Sum-of-ceils accumulation can overshoot ceil-of-sum and break "
            f"scroll detection."
        )

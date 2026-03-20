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


class TestTickerCountdown:
    def test_conforms_to_widget_protocol(self):
        cd = TickerCountdown(
            message="Test", countdown_date=date(2030, 1, 1)
        )
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

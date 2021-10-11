#!/usr/bin/env python3

import mock
import pytest

from async_ticker import widgets
from async_ticker.colors import RGB_WHITE
from async_ticker.fonts import FONT_DEFAULT
from async_ticker.helpers import get_text_width


def test_ticker_message_draw(mock_draw_text, mock_canvas):
    msg_text = 'This is a message'

    # Test Centered
    ticker_msg = widgets.TickerMessage(
        msg_text,
        font=FONT_DEFAULT,
        font_color=RGB_WHITE,
    )
    canvas, cursor_pos = ticker_msg.draw(mock_canvas)

    assert cursor_pos == 160

    mock_draw_text.assert_called_with(
        mock_canvas, FONT_DEFAULT, 29.0, 12, RGB_WHITE, msg_text
    )

    # Test Custom Font Color on Draw
    ticker_msg = widgets.TickerMessage(
        msg_text,
        font=FONT_DEFAULT,
    )

    ticker_msg.draw(mock_canvas, font_color=RGB_WHITE)

    mock_draw_text.assert_called_with(
        mock_canvas, FONT_DEFAULT, 29.0, 12, RGB_WHITE, msg_text
    )

    # Test Uncentered
    ticker_msg = widgets.TickerMessage(
        msg_text,
        center=False,
        font=FONT_DEFAULT,
        font_color=RGB_WHITE,
    )
    canvas, cursor_pos = ticker_msg.draw(mock_canvas)

    assert cursor_pos == 108

    mock_draw_text.assert_called_with(
        mock_canvas, FONT_DEFAULT, 0, 12, RGB_WHITE, msg_text
    )

    # Test too big to be centered
    too_big_message = msg_text * 10
    ticker_msg = widgets.TickerMessage(
        too_big_message,
        font=FONT_DEFAULT,
        font_color=RGB_WHITE,
    )

    canvas, cursor_pos = ticker_msg.draw(mock_canvas)

    assert cursor_pos == 1026

    mock_draw_text.assert_called_with(
        mock_canvas, FONT_DEFAULT, 0, 12, RGB_WHITE, too_big_message
    )

#!/usr/bin/env python3

import mock
import pytest

from async_ticker.helpers import get_text_width


@pytest.fixture
def mock_canvas():
    mock_canvas = mock.Mock()
    mock_canvas.width = 160
    return mock_canvas


def _mock_draw_text(canvas, font, cursor_pos, x_pos, font_color, msg):
    return get_text_width(font, msg, padding=0)


@pytest.fixture
def mock_draw_text(mocker):
    mock_draw_text = mocker.patch('rgbmatrix.graphics.DrawText')
    mock_draw_text.side_effect = _mock_draw_text
    return mock_draw_text

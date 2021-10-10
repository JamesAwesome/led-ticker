#!/usr/bin/env python3


import pytest
import mock

from async_ticker import helpers
from async_ticker.fonts import FONT_DEFAULT


def test_get_text_width():
    assert helpers.get_text_width(FONT_DEFAULT, ' ') == 12
    assert helpers.get_text_width(FONT_DEFAULT, ' ', padding=0) == 6


def test_find_center():
    canvas = mock.Mock()
    canvas.width = 160
    assert helpers.find_center(canvas, 6) == 77.0

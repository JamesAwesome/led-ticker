"""Shared test fixtures."""

import itertools
import os
import sys
import unittest.mock as mock

import pytest

# Ensure the rgbmatrix stub is available before any led_ticker imports
stubs_path = os.path.join(os.path.dirname(__file__), "stubs")
if stubs_path not in sys.path:
    sys.path.insert(0, stubs_path)


@pytest.fixture
def canvas():
    """Mock LED canvas with standard width and height."""
    c = mock.Mock()
    c.width = 160
    c.height = 16
    return c


@pytest.fixture
def mock_frame(canvas):
    """Mock LedFrame with canvas and SwapOnVSync."""
    frame = mock.Mock()
    frame.get_clean_canvas.return_value = canvas
    frame.matrix.SwapOnVSync.return_value = canvas
    return frame


@pytest.fixture
def swapping_frame():
    """Mock LedFrame whose SwapOnVSync rotates between two canvas objects.

    Use this for regression tests of the SwapOnVSync-capture rule
    (CLAUDE.md constraint #1). On real hardware, SwapOnVSync returns the
    previous front buffer (a different object) which becomes the new
    back buffer. If production code drops the return value, drawing
    continues on the front buffer and tearing/corruption results.

    With this fixture, dropping the return is detectable by asserting
    that downstream draw() calls saw multiple distinct canvas objects.
    """
    canvas_a = mock.Mock(name="canvas_a")
    canvas_a.width = 160
    canvas_a.height = 16
    canvas_b = mock.Mock(name="canvas_b")
    canvas_b.width = 160
    canvas_b.height = 16

    frame = mock.Mock()
    frame.get_clean_canvas.return_value = canvas_a
    frame.matrix.SwapOnVSync.side_effect = itertools.cycle([canvas_b, canvas_a])
    # Stash for assertions
    frame._canvas_a = canvas_a
    frame._canvas_b = canvas_b
    return frame


@pytest.fixture
def make_widget():
    """Factory for mock widgets with configurable draw width."""

    def _factory(content_width=40):
        widget = mock.Mock()
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            cursor_pos + content_width,
        )
        return widget

    return _factory


def make_aiohttp_session(json_response=None, text_response=None):
    """Create a mock aiohttp session that returns the given response."""
    session = mock.MagicMock()
    response = mock.AsyncMock()
    if json_response is not None:
        response.json.return_value = json_response
    if text_response is not None:
        response.text.return_value = text_response
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = response
    session.get.return_value = ctx
    return session

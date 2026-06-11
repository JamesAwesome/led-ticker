"""Shared test fixtures."""

import asyncio
import itertools
import os
import sys
import unittest.mock as mock

import pytest

# Ensure the rgbmatrix stub is available before any led_ticker imports
stubs_path = os.path.join(os.path.dirname(__file__), "stubs")
if stubs_path not in sys.path:
    sys.path.insert(0, stubs_path)


@pytest.fixture(autouse=True)
def _hermetic_entry_point_plugins(monkeypatch):
    """Keep the core suite hermetic with respect to pip-installed plugins.

    A first-party plugin (led-ticker-baseball, led-ticker-pool) installed into
    the dev venv registers its widgets/emoji into the core registries via
    entry-point discovery, which deterministically breaks core tests that assume
    a core-only environment (the exact widget count, the hires-sprite sweep, the
    config-dir loader tests). Stub entry-point discovery for the
    ``led_ticker.plugins`` group to empty so an installed plugin can't perturb
    core tests. The two tests that exercise entry-point loading
    (``test_loader_entrypoints``, ``test_loader_policy``) monkeypatch
    ``importlib.metadata.entry_points`` with their own fakes, which overrides
    this default for those tests.
    """
    import importlib.metadata

    real_entry_points = importlib.metadata.entry_points

    def _no_plugin_entry_points(*args, **kwargs):
        if kwargs.get("group") == "led_ticker.plugins":
            return []
        return real_entry_points(*args, **kwargs)

    monkeypatch.setattr(importlib.metadata, "entry_points", _no_plugin_entry_points)


@pytest.fixture
def canvas():
    """Mock LED canvas with standard width and height."""
    c = mock.Mock()
    c.width = 160
    c.height = 16
    return c


@pytest.fixture
def mock_frame(canvas):
    """Mock LedFrame with canvas and swap method."""
    frame = mock.Mock()
    frame.get_clean_canvas.return_value = canvas
    frame.swap.return_value = canvas
    return frame


@pytest.fixture
def swapping_frame():
    """Mock LedFrame whose swap rotates between two canvas objects.

    Use this for regression tests of the swap-capture rule
    (CLAUDE.md constraint #1). On real hardware, swap returns the
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
    frame.swap.side_effect = itertools.cycle([canvas_b, canvas_a])
    # Stash for assertions
    frame._canvas_a = canvas_a
    frame._canvas_b = canvas_b
    return frame


@pytest.fixture
def make_widget():
    """Factory for mock widgets with configurable draw width."""

    def _factory(content_width=40):
        widget = mock.Mock()
        widget.hold_time = 0.0
        widget.draw.side_effect = lambda c, cursor_pos=0, **kw: (
            c,
            cursor_pos + content_width,
        )
        return widget

    return _factory


@pytest.fixture
def no_sleep(monkeypatch):
    """Patch asyncio.sleep to yield to the event loop without real delay.

    Replaces the ``asyncio.sleep`` binding inside every led_ticker module
    that calls it so tests run fast while still giving the event loop a chance
    to schedule other coroutines (important for tests that drive multiple
    concurrent tasks).

    Each led_ticker module does ``import asyncio`` and then calls
    ``asyncio.sleep(...)``, so the live reference lives on the shared
    ``asyncio`` module object.  Patching ``asyncio.sleep`` once is sufficient
    because all modules share the same import.
    """
    _real_sleep = asyncio.sleep

    async def _zero_sleep(seconds):
        await _real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _zero_sleep)


@pytest.fixture
def bigsign_canvas():
    """Bigsign 2x4 vertical-serpentine real canvas (256×64).

    Equivalent to the ``_bigsign_real_canvas()`` helpers that used to live in
    individual test modules.  The stub RGBMatrix with U-mapper produces a
    256-wide × 64-tall canvas which is what ScaledCanvas(scale=4) wraps on the
    bigsign hardware.
    """
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


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

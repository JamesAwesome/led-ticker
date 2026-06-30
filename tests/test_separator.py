"""Unit tests for the shared separator renderer."""

from unittest.mock import MagicMock

from led_ticker.colors import RGB_WHITE
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.separator import (
    DEFAULT_CIRCLE_SPEC,
    DEFAULT_DOT_SPEC,
    SCROLL_GAP,
    SeparatorSpec,
    render_separator,
    scroll_separator_width,
    separator_width,
)


def _plain(width=160, height=16):
    c = MagicMock()
    c.width, c.height = width, height
    return c


def test_separator_width_dot_and_circle():
    assert separator_width(DEFAULT_DOT_SPEC) == 2
    assert separator_width(DEFAULT_CIRCLE_SPEC) == 8


def test_scroll_separator_width_default_is_14():
    assert scroll_separator_width(DEFAULT_DOT_SPEC) == SCROLL_GAP + 2 + SCROLL_GAP
    assert scroll_separator_width() == 14  # default dot, gap 6


def test_render_dot_paints_2x2_white_and_returns_width():
    canvas = _plain()
    width = render_separator(canvas, x=10, frame=0, spec=DEFAULT_DOT_SPEC)
    assert width == 2
    painted = {(c.args[0], c.args[1]) for c in canvas.SetPixel.call_args_list}
    # 2x2 block at x=10, rows y_center-1 and y_center (h//2 = 8)
    assert painted == {(10, 7), (11, 7), (10, 8), (11, 8)}
    for c in canvas.SetPixel.call_args_list:
        assert c.args[2:5] == (255, 255, 255)


def test_render_dot_parity_with_ticker_draw_bullet():
    """render_separator dot == the existing _draw_bullet (still present)."""
    from led_ticker.ticker import _draw_bullet

    a, b = _plain(), _plain()
    _draw_bullet(a, x=12)
    render_separator(b, x=12, frame=0, spec=DEFAULT_DOT_SPEC)
    assert a.SetPixel.call_args_list == b.SetPixel.call_args_list


def test_render_circle_uses_provider_color_via_frame():
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    spec = SeparatorSpec(kind="circle", color=RGB_WHITE, size=8)
    render_separator(canvas, x=1, frame=0, spec=spec)
    assert real.SetPixel.called


def test_resolve_rgb_accepts_color_provider():
    """The provider path (.red/.green/.blue) — the basis for Phase 2's
    rainbow/gradient separator colors — resolves correctly."""
    from unittest.mock import MagicMock

    from led_ticker.separator import _resolve_rgb

    provider = MagicMock()
    color_obj = MagicMock(red=255, green=0, blue=128)
    provider.color_for.return_value = color_obj
    assert _resolve_rgb(provider, frame=5) == (255, 0, 128)
    provider.color_for.assert_called_once_with(5, 0, 1)

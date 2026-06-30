"""Unit + parity tests for the shared separator renderer (Phase 1).

Parity tests compare render_separator against the still-present
ticker._draw_hires_circle / ticker._draw_bullet to prove byte-identical
output before the consumers are rewired.
"""

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


def test_render_circle_parity_with_ticker_draw_hires_circle():
    """render_separator circle == the existing _draw_hires_circle (still present).

    The widget passes x = cursor_pos + _CIRCLE_LOGICAL_PAD; _draw_hires_circle
    bakes that pad into its own centering, so compare at matching x."""
    from led_ticker.separator import _CIRCLE_LOGICAL_PAD
    from led_ticker.ticker import _draw_hires_circle

    real_a = MagicMock()
    real_a.width, real_a.height = 256, 64
    canvas_a = ScaledCanvas(real_a, scale=4, content_height=16)
    real_b = MagicMock()
    real_b.width, real_b.height = 256, 64
    canvas_b = ScaledCanvas(real_b, scale=4, content_height=16)

    _draw_hires_circle(canvas_a, cursor_pos=0, color=(255, 255, 255))
    render_separator(
        canvas_b, x=0 + _CIRCLE_LOGICAL_PAD, frame=0, spec=DEFAULT_CIRCLE_SPEC
    )
    assert real_a.SetPixel.call_args_list == real_b.SetPixel.call_args_list


def test_render_circle_uses_provider_color_via_frame():
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    spec = SeparatorSpec(kind="circle", color=RGB_WHITE, size=8)
    render_separator(canvas, x=1, frame=0, spec=spec)
    assert real.SetPixel.called

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


def test_render_circle_geometry_at_scale4():
    """Circle lands in the expected physical bounding box with correct pixel
    count — restores the geometry coverage lost when the direct
    _draw_hires_circle tests were removed."""
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    render_separator(canvas, x=1, frame=0, spec=DEFAULT_CIRCLE_SPEC)

    coords = {(c.args[0], c.args[1]) for c in real.SetPixel.call_args_list}
    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    # x=1 (pad), radius_physical=16 -> center_x = 1*4+16 = 20 -> x in [4, 36]
    # y_offset_real=0, center_y = (16*4)//2 = 32 -> y in [16, 48]
    assert min(xs) >= 4 and max(xs) <= 36, f"x out of [4,36]: {min(xs)}..{max(xs)}"
    assert min(ys) >= 16 and max(ys) <= 48, f"y out of [16,48]: {min(ys)}..{max(ys)}"
    assert 760 <= len(coords) <= 850, f"disk pixel count {len(coords)} out of range"


def test_render_circle_color_applied_uniformly():
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    spec = SeparatorSpec(kind="circle", color=(225, 48, 108), size=8)

    render_separator(canvas, x=1, frame=0, spec=spec)

    for call in real.SetPixel.call_args_list:
        _, _, r, g, b = call.args
        assert (r, g, b) == (225, 48, 108)

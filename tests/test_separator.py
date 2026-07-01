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


def test_separator_width_glyph_uses_font_advance():
    from led_ticker.drawing import get_text_width
    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.separator import SeparatorSpec, separator_width

    spec = SeparatorSpec(kind="glyph", color=RGB_WHITE, glyph="-", font=FONT_DEFAULT)
    assert separator_width(spec) == get_text_width(FONT_DEFAULT, "-", padding=0)


def test_render_glyph_paints_on_plain_canvas_and_returns_width():
    from led_ticker.drawing import get_text_width
    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.separator import SeparatorSpec, render_separator

    canvas = _plain()
    spec = SeparatorSpec(kind="glyph", color=RGB_WHITE, glyph="-", font=FONT_DEFAULT)
    width = render_separator(canvas, x=20, frame=0, spec=spec)
    # BDF rasterizer must have painted at least one pixel
    assert canvas.SetPixel.call_count > 0, "expected SetPixel calls from BDF rasterizer"
    # All painted x coords must fall within the glyph's span starting at x=20
    painted_xs = [c.args[0] for c in canvas.SetPixel.call_args_list]
    assert all(px >= 20 for px in painted_xs), (
        f"pixel(s) painted left of x=20: {[px for px in painted_xs if px < 20]}"
    )
    assert width == get_text_width(FONT_DEFAULT, "-", padding=0, canvas=canvas)


def test_render_glyph_normalizes_tuple_color_to_graphics_color():
    """A provider that yields a tuple must be wrapped to a graphics.Color
    (draw_text reads .red/.green/.blue)."""
    from unittest.mock import patch

    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.separator import SeparatorSpec, render_separator

    canvas = _plain()
    spec = SeparatorSpec(kind="glyph", color=(10, 20, 30), glyph="-", font=FONT_DEFAULT)
    with patch("led_ticker.text_render.draw_text", return_value=5) as mock_dt:
        render_separator(canvas, x=0, frame=0, spec=spec)
    color_arg = mock_dt.call_args.args[4]  # draw_text(canvas, font, x, y, color, text)
    assert (color_arg.red, color_arg.green, color_arg.blue) == (10, 20, 30)


def test_no_inline_hardcoded_dot_remains():
    """The scroll dot goes through render_separator — the old dot symbols
    are fully gone (Phase 1 unification). (A blanket '255,255,255' scan is
    intentionally NOT used: it false-positives on ColorFlash's legitimate
    white default in effects.py.)"""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src" / "led_ticker"
    for rel in ("ticker.py", "transitions/effects.py"):
        text = (root / rel).read_text()
        assert "BULLET_WIDTH" not in text, f"{rel} still references BULLET_WIDTH"
        assert "BULLET_COLOR" not in text, f"{rel} still references BULLET_COLOR"
        assert "_draw_bullet" not in text, f"{rel} still defines/uses _draw_bullet"


# ---------------------------------------------------------------------------
# D1: glyph on a ScaledCanvas (bigsign path)
# ---------------------------------------------------------------------------


def test_render_glyph_on_scaled_canvas_paints_and_returns_width():
    """BDF glyph renders on a ScaledCanvas via draw_bdf_text → real.SubFill.

    Mirrors test_render_circle_geometry_at_scale4 to verify the glyph branch
    of render_separator reaches the real canvas when wrapped in a ScaledCanvas.
    """
    from led_ticker.fonts import FONT_DEFAULT

    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    spec = SeparatorSpec(kind="glyph", color=RGB_WHITE, glyph="-", font=FONT_DEFAULT)

    width = render_separator(canvas, x=10, frame=0, spec=spec)

    # ScaledCanvas.draw_bdf_text calls self.SetPixel → self.real.SubFill
    assert real.SubFill.called, "expected real.SubFill to be called via draw_bdf_text"
    assert width > 0, "expected a non-zero logical width for glyph '-'"


# ---------------------------------------------------------------------------
# D2: empty glyph
# ---------------------------------------------------------------------------


def test_empty_glyph_width_and_render_are_zero():
    """An empty glyph string renders nothing and contributes zero mark width."""
    from led_ticker.fonts import FONT_DEFAULT

    spec = SeparatorSpec(kind="glyph", glyph="", font=FONT_DEFAULT)

    assert separator_width(spec) == 0
    # scroll_separator_width = gap + mark + gap = 6 + 0 + 6 = 12
    assert scroll_separator_width(spec) == 2 * SCROLL_GAP

    canvas = _plain()
    result = render_separator(canvas, x=0, frame=0, spec=spec)
    assert result == 0
    canvas.SetPixel.assert_not_called()


# ---------------------------------------------------------------------------
# D3: multi-char glyph width
# ---------------------------------------------------------------------------


def test_multi_char_glyph_width_uses_font_advance():
    """separator_width of a multi-char glyph equals get_text_width for the
    same string (no canvas; uses SCALE_FALLBACK internally)."""
    from led_ticker.drawing import get_text_width
    from led_ticker.fonts import FONT_DEFAULT

    spec = SeparatorSpec(kind="glyph", glyph="--", font=FONT_DEFAULT)
    assert separator_width(spec) == get_text_width(FONT_DEFAULT, "--", padding=0)


# ---------------------------------------------------------------------------
# D4: animated glyph color advances with frame
# ---------------------------------------------------------------------------


def test_animated_glyph_color_changes_with_frame():
    """Rainbow color provider yields different colors at frame=0 vs frame=40."""
    from unittest.mock import patch

    from led_ticker.color_providers import Rainbow
    from led_ticker.fonts import FONT_DEFAULT

    spec = SeparatorSpec(kind="glyph", color=Rainbow(), glyph="-", font=FONT_DEFAULT)
    canvas = _plain()

    with patch("led_ticker.text_render.draw_text", return_value=5) as mock_dt:
        render_separator(canvas, x=0, frame=0, spec=spec)
        color_at_0 = mock_dt.call_args.args[4]

        render_separator(canvas, x=0, frame=40, spec=spec)
        color_at_40 = mock_dt.call_args.args[4]

    # Rainbow sweeps hue with frame — colors must differ between frame 0 and 40
    assert (color_at_0.red, color_at_0.green, color_at_0.blue) != (
        color_at_40.red,
        color_at_40.green,
        color_at_40.blue,
    ), "expected Rainbow to produce different colors at frame=0 and frame=40"

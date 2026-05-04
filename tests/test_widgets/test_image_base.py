"""Tests for _BaseImageWidget bg_color handling and _paint_image dispatch."""

from __future__ import annotations

import unittest.mock as mock

import attrs

from led_ticker._types import Canvas
from led_ticker.widgets._image_base import _BaseImageWidget


@attrs.define
class _DummyImage(_BaseImageWidget):
    """Test stub: tracks which paint path was called."""

    paint_full_calls: list = attrs.field(factory=list)
    paint_skip_black_calls: list = attrs.field(factory=list)

    def __attrs_post_init__(self) -> None:
        self._validate_common(image_align="center", fit="pillarbox")

    def _paint_full(self, canvas: Canvas) -> None:
        self.paint_full_calls.append(canvas)

    def _paint_skip_black(self, canvas: Canvas) -> None:
        self.paint_skip_black_calls.append(canvas)

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        pass


class TestPaintImageDispatch:
    def test_no_bg_uses_paint_full(self):
        """bg_color=None → _paint_image calls _paint_full (SetImage fast path)."""
        w = _DummyImage()
        canvas = mock.Mock()
        w._paint_image(canvas)
        assert len(w.paint_full_calls) == 1
        assert len(w.paint_skip_black_calls) == 0

    def test_bg_set_uses_skip_black(self):
        """bg_color set → _paint_image calls _paint_skip_black so the
        pre-painted bg shows through pillarbox/letterbox/transparency."""
        from rgbmatrix.graphics import Color

        w = _DummyImage(bg_color=Color(10, 20, 30))
        canvas = mock.Mock()
        w._paint_image(canvas)
        assert len(w.paint_skip_black_calls) == 1
        assert len(w.paint_full_calls) == 0


class TestRenderTickResetsCanvas:
    """`_render_tick` calls reset_canvas(canvas, bg_color) instead of Clear()."""

    def test_no_bg_calls_clear(self):
        w = _DummyImage()
        canvas = mock.Mock()
        text_canvas = mock.Mock()
        w.text_align = "left"
        w._render_tick(canvas, text_canvas, 0, 10, 0, 100)
        canvas.Clear.assert_called_once_with()
        canvas.Fill.assert_not_called()

    def test_bg_calls_fill(self):
        from rgbmatrix.graphics import Color

        w = _DummyImage(bg_color=Color(40, 50, 60))
        canvas = mock.Mock()
        text_canvas = mock.Mock()
        w.text_align = "left"
        w._render_tick(canvas, text_canvas, 0, 10, 0, 100)
        canvas.Clear.assert_not_called()
        canvas.Fill.assert_called_once_with(40, 50, 60)


class TestFieldSurface:
    """Field-surface tripwire — catches the specific class of bug that
    bit us with `_BaseImageWidget.font` originally declared `init=False`
    (caused `TypeError: GifPlayer.__init__() got an unexpected keyword
    argument 'font'` on hardware). If anyone accidentally flips a
    user-facing field to `init=False`, or the `init`-eligibility of a
    documented kwarg drifts, this test catches it before it surfaces
    as a runtime error in production.
    """

    USER_FACING_FIELDS = {
        "text",
        "text_align",
        "text_valign",
        "text_y_offset",
        "text_x_offset",
        "scroll_direction",
        "font_color",
        "bg_color",
        "scroll_speed_ms",
        "text_scale",
        "text_loops",
        "font",
    }

    def test_all_documented_user_fields_are_init_eligible(self):
        """Every TOML-settable kwarg on `_BaseImageWidget` must be
        `init=True` so `_build_widget` can pass it through."""
        init_fields = {a.name for a in attrs.fields(_BaseImageWidget) if a.init}
        missing = self.USER_FACING_FIELDS - init_fields
        assert not missing, (
            f"User-facing fields {missing!r} are not init-eligible; "
            f"configs setting them via _build_widget will TypeError "
            f"at construction. Compare current init=True/False values "
            f"in widgets/_image_base.py with this test's USER_FACING_FIELDS."
        )

    def test_dummy_image_constructs_with_every_user_kwarg(self):
        """Sanity: the base class accepts every documented kwarg in
        a single construction. Catches type-shape regressions (e.g.
        changing `text: str` to `text: int`)."""
        from led_ticker.fonts import FONT_DEFAULT

        # No assertion needed beyond construction success.
        _DummyImage(
            text="hi",
            text_align="left",
            text_valign="top",
            text_y_offset=2,
            text_x_offset=3,
            scroll_direction="left",
            bg_color=None,
            scroll_speed_ms=50,
            text_scale=1,
            text_loops=0,
            font=FONT_DEFAULT,
        )


class TestFontKwarg:
    """Regression: image widgets (gif, image) accept `font` (and the
    resolved HiresFont it points to) as a constructor kwarg. Before the
    fix, _BaseImageWidget declared `font` with `init=False`, so configs
    setting `font = "Inter-Regular"` raised
    `TypeError: __init__() got an unexpected keyword argument 'font'`
    when _build_widget passed the resolved object through.
    """

    def test_font_kwarg_accepted(self):
        from led_ticker.fonts import FONT_SMALL

        w = _DummyImage(font=FONT_SMALL)
        assert w.font is FONT_SMALL

    def test_default_font_when_not_specified(self):
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage()
        assert w.font is FONT_DEFAULT

    def test_hires_font_kwarg_accepted(self):
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        assert isinstance(font, HiresFont)
        w = _DummyImage(font=font)
        assert w.font is font


class TestHiresFontTextScaleRejection:
    """`text_scale > 1` is BDF block-expansion semantics. With a hires
    font, the renderer paints to the unwrapped real canvas at native
    pixels — text_scale becomes a silent no-op for the glyph size
    while still affecting measurement (`get_text_width` ceil-divides
    by canvas.scale). Refuse the combo at validation time so users
    don't get measurement-vs-render disagreement on the panel.
    """

    def test_hires_font_with_text_scale_2_raises(self):
        import pytest

        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        with pytest.raises(ValueError, match="text_scale"):
            _DummyImage(font=font, text_scale=2)

    def test_hires_font_with_text_scale_1_ok(self):
        """text_scale=1 (default) is fine — no wrapper, no conflict."""
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        w = _DummyImage(font=font, text_scale=1)
        assert w.font is font
        assert w.text_scale == 1

    def test_bdf_font_with_text_scale_2_still_ok(self):
        """BDF fonts go through the ScaledCanvas wrapper — text_scale
        is the supported way to block-expand them."""
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(font=FONT_DEFAULT, text_scale=2)
        assert w.text_scale == 2

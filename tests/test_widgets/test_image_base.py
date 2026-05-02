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

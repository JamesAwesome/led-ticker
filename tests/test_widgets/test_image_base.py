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


class TestTwoRowMode:
    """`bottom_text != ""` switches `_BaseImageWidget` to held-top +
    scroll-on-overflow-bottom semantics over an image background.
    Mirrors `TwoRowMessage`'s contract; the per-row knobs (`top_text`,
    `bottom_color`, `top_align`, `top_font`, `top_text_y_offset`,
    etc.) parallel TwoRow's. Single-row mode (default) is unchanged.
    """

    def test_default_is_single_row_mode(self):
        """Without bottom_text, widget is in single-row mode."""
        w = _DummyImage(text="hello")
        assert not w._is_two_row()

    def test_bottom_text_enables_two_row_mode(self):
        w = _DummyImage(top_text="@brand", bottom_text="follow us")
        assert w._is_two_row()

    def test_text_alias_works_for_top_in_two_row_mode(self):
        """`text="..."` is a back-compat alias for `top_text` when
        bottom_text is also set — configs that just add bottom_text
        keep working without renaming `text` to `top_text`."""
        w = _DummyImage(text="@brand", bottom_text="follow us")
        assert w._row_text(0) == "@brand"
        assert w._row_text(1) == "follow us"

    def test_explicit_top_text_overrides_text_alias(self):
        """If top_text is set, it wins over `text`."""
        w = _DummyImage(top_text="EXPLICIT", bottom_text="bottom")
        assert w._row_text(0) == "EXPLICIT"

    def test_setting_both_text_and_top_text_raises(self):
        """In two-row mode, setting both `text` AND `top_text`
        is ambiguous — refuse at construction."""
        import pytest

        with pytest.raises(ValueError, match="text.*top_text"):
            _DummyImage(text="A", top_text="B", bottom_text="C")

    def test_two_row_with_text_align_scroll_raises(self):
        """text_align scroll modes conflict with two-row's auto-scroll
        contract — refuse at construction."""
        import pytest

        with pytest.raises(ValueError, match="text_align"):
            _DummyImage(
                top_text="A",
                bottom_text="B",
                text_align="scroll",
            )

    def test_two_row_with_text_valign_top_raises(self):
        """text_valign is meaningless in two-row mode (rows positioned
        by the split, not the global valign)."""
        import pytest

        with pytest.raises(ValueError, match="text_valign"):
            _DummyImage(
                top_text="A",
                bottom_text="B",
                text_valign="top",
            )

    def test_two_row_with_text_x_offset_raises(self):
        """text_x_offset is replaced by per-row align in two-row mode."""
        import pytest

        with pytest.raises(ValueError, match="text_x_offset"):
            _DummyImage(
                top_text="A",
                bottom_text="B",
                text_x_offset=5,
            )

    def test_two_row_with_text_scale_2_raises(self):
        """text_scale > 1 conflicts with per-row band sizing."""
        import pytest

        with pytest.raises(ValueError, match="text_scale"):
            _DummyImage(
                top_text="A",
                bottom_text="B",
                text_scale=2,
            )

    def test_per_row_font_falls_back_to_font(self):
        """`top_font` / `bottom_font` default to None and fall back to
        `font`. Configs only need to set per-row fonts when they
        actually differ."""
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(
            top_text="A",
            bottom_text="B",
            font=FONT_DEFAULT,
        )
        assert w._row_font(0) is FONT_DEFAULT
        assert w._row_font(1) is FONT_DEFAULT

    def test_per_row_font_overrides_font(self):
        from led_ticker.fonts import FONT_DEFAULT, FONT_LABEL

        w = _DummyImage(
            top_text="A",
            bottom_text="B",
            font=FONT_DEFAULT,
            top_font=FONT_LABEL,
        )
        assert w._row_font(0) is FONT_LABEL
        assert w._row_font(1) is FONT_DEFAULT  # falls back to font

    def test_per_row_color_falls_back_to_font_color(self):
        from rgbmatrix.graphics import Color

        red = Color(255, 0, 0)
        w = _DummyImage(top_text="A", bottom_text="B", font_color=red)
        assert w._row_color(0) is red
        assert w._row_color(1) is red

    def test_per_row_color_overrides_font_color(self):
        from rgbmatrix.graphics import Color

        red = Color(255, 0, 0)
        blue = Color(0, 0, 255)
        w = _DummyImage(
            top_text="A",
            bottom_text="B",
            font_color=red,
            bottom_color=blue,
        )
        assert w._row_color(0) is red
        assert w._row_color(1) is blue

    def test_per_row_align_defaults_to_center(self):
        """Both rows default to center alignment, matching TwoRow."""
        w = _DummyImage(top_text="A", bottom_text="B")
        assert w._row_align(0) == "center"
        assert w._row_align(1) == "center"


class TestFieldSurfaceMatchesTwoRow:
    """Field-surface tripwire (Guardrail #3 from the architectural
    review): the per-row knobs on `_BaseImageWidget`'s two-row mode
    must match `TwoRowMessage`'s — same names, same defaults, same
    types. If anyone adds a knob to one and forgets the other, this
    test catches the drift at the test layer rather than letting it
    ship as a "works on TwoRow but not on gif" surprise.
    """

    PER_ROW_FIELDS = {
        # name → expected default
        "top_text": "",
        "bottom_text": "",
        "top_color": None,
        "bottom_color": None,
        "top_align": "center",
        "bottom_align": "center",
        "top_font": None,
        "bottom_font": None,
        "top_text_y_offset": 0,
        "bottom_text_y_offset": 0,
        "top_emoji_y_offset": 0,
        "bottom_emoji_y_offset": 0,
        "top_row_height": None,
    }

    def test_two_row_message_has_all_per_row_fields(self):
        """Sanity check that TwoRowMessage exposes the same per-row
        field set we expect on _BaseImageWidget. Tests the source
        of truth: if these drift, the consistency check below fails
        too."""
        from led_ticker.widgets.two_row import TwoRowMessage

        tw_field_names = {a.name for a in attrs.fields(TwoRowMessage) if a.init}
        # `top_text`/`bottom_text`/`top_color`/`bottom_color` are
        # required in TwoRow; the rest are optional knobs. Just
        # verify the names exist.
        for name in self.PER_ROW_FIELDS:
            assert name in tw_field_names, (
                f"TwoRowMessage lost field {name!r} — drift between "
                f"the source-of-truth widget and the field-surface "
                f"tripwire"
            )

    def test_image_base_has_all_per_row_fields(self):
        """The actual tripwire: every per-row field on TwoRow must
        be init-eligible on `_BaseImageWidget` too, so configs setting
        them via `_build_widget` work uniformly."""
        ib_field_names = {a.name for a in attrs.fields(_BaseImageWidget) if a.init}
        missing = set(self.PER_ROW_FIELDS) - ib_field_names
        assert not missing, (
            f"`_BaseImageWidget` is missing per-row fields {missing!r} "
            f"that exist on TwoRowMessage. Add the fields with matching "
            f"defaults so two-row mode behaves identically across both "
            f"widgets."
        )

    def test_image_base_per_row_field_defaults_match(self):
        """Defaults must agree — a widget that defaults `top_align`
        to 'left' on TwoRow but 'center' on image widgets is a
        cross-widget surprise."""
        ib_fields = {a.name: a for a in attrs.fields(_BaseImageWidget)}
        for name, expected_default in self.PER_ROW_FIELDS.items():
            field = ib_fields[name]
            actual = field.default
            # `attrs.NOTHING` sentinel for required fields — we don't
            # expect any of these to be required, so the default
            # should match.
            assert actual == expected_default, (
                f"`_BaseImageWidget.{name}` default = {actual!r}, "
                f"expected {expected_default!r} (matching TwoRowMessage)"
            )

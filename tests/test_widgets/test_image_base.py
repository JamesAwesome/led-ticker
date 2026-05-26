"""Tests for _BaseImageWidget bg_color handling and _paint_image dispatch."""

from __future__ import annotations

import unittest.mock as mock

import attrs
import pytest

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
        "text_loops",
        "font",
        "font_size",
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
            text_loops=0,
            font=FONT_DEFAULT,
            font_size=24,
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

    def test_has_text_content_true_when_only_two_row_fields_set(self):
        """Regression: gif/still `play()` dispatches on
        `_has_text_content()` to pick the text-overlay vs no-text code
        path. In two-row mode users typically leave `text=""` and set
        `top_text` + `bottom_text` only — the dispatch must still see
        text content, otherwise the overlay path is skipped silently
        and nothing renders."""
        w_top = _DummyImage(top_text="@brand")
        assert w_top._has_text_content()

        w_bottom = _DummyImage(bottom_text="follow us")
        assert w_bottom._has_text_content()

        w_both = _DummyImage(top_text="@brand", bottom_text="follow us")
        assert w_both._has_text_content()

        w_none = _DummyImage()
        assert not w_none._has_text_content()

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

    def test_with_font_size_raises(self):
        """font_size is the single-row knob; two-row mode uses
        top_font_size / bottom_font_size for per-row sizing."""
        import pytest

        with pytest.raises(ValueError, match="font_size"):
            _DummyImage(
                top_text="A",
                bottom_text="B",
                font_size=24,
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
        """_row_color falls back to font_color. After coercion both are
        providers; verify they materialize the same Color value."""
        from rgbmatrix.graphics import Color

        red = Color(255, 0, 0)
        w = _DummyImage(top_text="A", bottom_text="B", font_color=red)
        # Both rows resolve to the font_color provider (same object).
        assert w._row_color(0) is w.font_color
        assert w._row_color(1) is w.font_color
        # Provider materializes the correct color.
        assert w._row_color(0).color_for(0, 0, 1).red == 255

    def test_per_row_color_overrides_font_color(self):
        """Per-row color providers override font_color for that row."""
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor

        red = Color(255, 0, 0)
        blue = Color(0, 0, 255)
        w = _DummyImage(
            top_text="A",
            bottom_text="B",
            font_color=red,
            bottom_color=blue,
        )
        # After coercion, each is a _ConstantColor provider.
        assert isinstance(w._row_color(0), _ConstantColor)
        assert isinstance(w._row_color(1), _ConstantColor)
        # Top falls back to font_color (wrapped red); bottom is wrapped blue.
        assert w._row_color(0).color_for(0, 0, 1).red == 255
        assert w._row_color(1).color_for(0, 0, 1).blue == 255

    def test_per_row_align_defaults_to_center(self):
        """Both rows default to center alignment, matching TwoRow."""
        w = _DummyImage(top_text="A", bottom_text="B")
        assert w._row_align(0) == "center"
        assert w._row_align(1) == "center"


class TestTwoRowLogicalUnits:
    """`top_row_height` is in LOGICAL rows (matches TwoRowMessage's
    convention). The image-widget two-row path paints to the unwrapped
    real canvas, so the value must be multiplied by the section's
    logical scale before being passed to `resolve_band_heights`. The
    ticker stashes the wrapper scale on `widget._logical_scale` before
    handing off the real canvas; without that, `top_row_height = 5`
    on bigsign was being read as 5 REAL pixels (way too small for any
    hi-res font), surfacing as a confusing "font line-height exceeds
    band" exception on hardware.
    """

    async def test_top_row_height_interpreted_as_logical(
        self, monkeypatch, swapping_frame
    ):
        """Set `_logical_scale = 4` (bigsign), `top_row_height = 5`
        (logical) → effective top band should be 20 real px, leaving
        44 real px for the bottom on a 64-row canvas. Hires Inter @
        14 px line-height fits in a 20-px band, so no exception. Uses
        a real `_StubCanvas` (not a Mock) so a method-rename inside
        `_play_with_two_row_text` would surface as an actual error
        instead of being swallowed by a broad `except`."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont
        from led_ticker.scaled_canvas import ScaledCanvas

        font = resolve_font("Inter-Regular", size=14)
        assert isinstance(font, HiresFont)

        w = _DummyImage(
            top_text="A",
            bottom_text="B",
            top_font=font,
            bottom_font=font,
            top_row_height=5,
        )
        w._logical_scale = 4

        real = _StubCanvas(width=256, height=64)
        swapping_frame.swap.return_value = _StubCanvas(width=256, height=64)

        # Spy: the static fast-path renders one tick. Capture that
        # `_render_two_row_tick` actually got called — proves we passed
        # the validation block AND reached the render path. If the
        # method were renamed, this spy never installs and the assert
        # fails loudly instead of being absorbed by a generic except.
        captured: list = []
        orig = _BaseImageWidget._render_two_row_tick

        def spy(self, real_c, text_c, *args, **kwargs):
            captured.append(isinstance(text_c, ScaledCanvas))
            return orig(self, real_c, text_c, *args)

        monkeypatch.setattr(_BaseImageWidget, "_render_two_row_tick", spy)
        await w._play_with_two_row_text(real, swapping_frame, n_ticks=1)

        assert captured, (
            "_render_two_row_tick was never reached — validation may "
            "have rejected the logical-rows config or the method was "
            "renamed."
        )
        assert all(captured), "Expected text_canvas to be wrapped"

    async def test_hires_emoji_fires_on_text_canvas_wrapper(
        self, monkeypatch, swapping_frame
    ):
        """Regression: the two-row image path must wrap the real canvas
        in a ScaledCanvas before drawing text/emoji, so hires emoji
        (e.g. `:instagram:`) fires the `isinstance(c, ScaledCanvas)`
        gate in `pixel_emoji.draw_with_emoji`. Without the wrap, the
        emoji silently falls back to the 8×8 lores sprite — which is
        what the user observed on hardware before this fix."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import resolve_font
        from led_ticker.scaled_canvas import ScaledCanvas

        font = resolve_font("Inter-Regular", size=14)
        w = _DummyImage(
            top_text="@brand",
            bottom_text="follow :instagram:",
            top_font=font,
            bottom_font=font,
        )
        w._logical_scale = 4

        # Capture the text_canvas passed to _render_two_row_tick so we
        # can assert it's a ScaledCanvas wrapper (where emoji's gate
        # fires), not the raw real canvas.
        captured: list = []
        orig = _BaseImageWidget._render_two_row_tick

        def spy(self, real_c, text_c, *args, **kwargs):
            captured.append((type(text_c).__name__, isinstance(text_c, ScaledCanvas)))
            return orig(self, real_c, text_c, *args)

        monkeypatch.setattr(_BaseImageWidget, "_render_two_row_tick", spy)

        real = _StubCanvas(width=256, height=64)
        swapping_frame.swap.return_value = _StubCanvas(width=256, height=64)

        await w._play_with_two_row_text(real, swapping_frame, n_ticks=1)

        assert captured, "_render_two_row_tick was never called"
        assert all(is_wrapped for _name, is_wrapped in captured), (
            f"Expected text_canvas to be a ScaledCanvas wrapper so "
            f"hires emoji fires; got: {captured!r}"
        )

    async def test_emoji_cap_scales_with_band_height(self, monkeypatch, swapping_frame):
        """Hi-res emoji on the top row of two-row needs the per-row
        emoji cap to scale with band height. With default content_height
        = 16 and 50/50 split, top band = 8 logical = 8 cap; the 32-real
        hi-res sprite at scale=2 (16 logical) > 8 cap → falls back to
        lores. Bumping content_height to 24 + top_row_height = 16 makes
        the top band 16 logical, so the cap should also be 16, allowing
        the hi-res sprite through.

        Pin the per-row cap that gets passed to draw_with_emoji."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import (
            FONT_SMALL,  # noqa: F401
            resolve_font,
        )

        font = resolve_font("Inter-Regular", size=14)
        # Use 5x8 BDF on the bottom — 8 logical line_height fits the 8-row
        # bottom band exactly. Inter on top is fine in the 16-row top band.
        w = _DummyImage(
            top_text=":instagram: @brand",
            bottom_text="hi",
            top_font=font,
            bottom_font=resolve_font("5x8"),
            top_row_height=16,
        )
        # Force a tall content_height via the section wrap. _logical_scale
        # is the wrapper scale; section content_height here is read from
        # the wrapper's height, which we set via the canvas dims below.
        w._logical_scale = 2

        # _render_two_row_tick receives top_emoji_cap / bottom_emoji_cap
        # kwargs from _play_with_two_row_text. Capture them.
        captured: dict = {}
        orig = _BaseImageWidget._render_two_row_tick

        def spy(self, real_c, text_c, *args, **kwargs):
            captured["top"] = kwargs.get("top_emoji_cap")
            captured["bottom"] = kwargs.get("bottom_emoji_cap")
            return orig(self, real_c, text_c, *args, **kwargs)

        monkeypatch.setattr(_BaseImageWidget, "_render_two_row_tick", spy)

        # 256x48 real → wrapped at scale=2 = 128x24 logical, content_height=24.
        # top_row_height=16 → top band 16 logical, bottom 8 logical.
        real = _StubCanvas(width=256, height=48)
        swapping_frame.swap.return_value = _StubCanvas(width=256, height=48)

        await w._play_with_two_row_text(real, swapping_frame, n_ticks=1)

        # top band = 16 logical → cap raised from 8 default to 16.
        # bottom band = 8 logical → cap stays 8.
        assert (
            captured["top"] == 16
        ), f"expected top_emoji_cap = 16 (band size), got {captured['top']!r}"
        assert (
            captured["bottom"] == 8
        ), f"expected bottom_emoji_cap = 8 (default floor), got {captured['bottom']!r}"

    async def test_oversized_logical_top_row_still_rejects(self, swapping_frame):
        """Even with logical-units conversion, a band that's too small
        for the font must raise. `top_row_height = 1` (logical) →
        4 real px → too small for a 14-px hires font → raise. Error
        message names logical rows (matches TwoRowMessage's wording)."""
        import pytest

        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", size=14)
        w = _DummyImage(
            top_text="A",
            bottom_text="B",
            top_font=font,
            bottom_font=font,
            top_row_height=1,
        )
        w._logical_scale = 4

        canvas = mock.MagicMock()
        canvas.width = 256
        canvas.height = 64

        with pytest.raises(ValueError, match="logical rows"):
            await w._play_with_two_row_text(canvas, swapping_frame, n_ticks=0)


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
        "bottom_text_scroll": "marquee",
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


class TestImageTwoRowHiresEmojiAnchoring:
    """Hi-res emoji in a band sized to fit it should anchor at the
    band's top edge, not at the 8-row low-res-sprite centering
    position. Mirrors `test_hires_sprite_anchors_within_full_band`
    in test_two_row.py for the image two-row text overlay path."""

    def test_hires_sprite_anchors_within_full_band(self):
        from types import SimpleNamespace

        from led_ticker.fonts import FONT_SMALL
        from led_ticker.widgets._row_layout import row_layout

        canvas = SimpleNamespace(height=24, scale=2, width=128)
        _, top_emoji_y = row_layout(
            canvas,
            FONT_SMALL,
            band_height=16,
            band_offset=0,
            sprite_logical_height=16,
        )
        assert top_emoji_y == 0


class TestResolvedFontSize:
    """`_resolved_font_size()` is the smart-default hook. If
    `self.font_size` is set, it returns as-is. If None, BDF returns
    `cell_h × _logical_scale`; HiresFont returns its already-baked
    natural size (font.size attribute on HiresFont, or
    line_height for BDF as a back-stop)."""

    def test_explicit_font_size_returned_as_is(self):
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(font=FONT_DEFAULT, font_size=24)
        assert w._resolved_font_size() == 24

    def test_bdf_smart_default_uses_cell_times_logical_scale(self):
        """BDF + `font_size=None` + bigsign (_logical_scale=4) →
        12 × 4 = 48 real px. Preserves bd61140 panel-scale behavior
        in the new vocabulary."""
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(font=FONT_DEFAULT, font_size=None)
        w._logical_scale = 4
        assert w._resolved_font_size() == 48

    def test_bdf_smart_default_on_small_sign(self):
        """BDF + `font_size=None` + small sign (_logical_scale=1) →
        12 × 1 = 12 real px. Native BDF, no block-expansion."""
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(font=FONT_DEFAULT, font_size=None)
        w._logical_scale = 1
        assert w._resolved_font_size() == 12

    def test_hires_uses_font_internal_size(self):
        """HiresFont's `size` is set at construction (from
        rasterizer target). When the widget's `self.font_size` is
        None, fall back to the HiresFont's own `size` attr."""
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        w = _DummyImage(font=font, font_size=None)
        w._logical_scale = 4
        # HiresFont remembers its rasterized size; that's the natural
        # default if the widget didn't get an explicit override.
        assert w._resolved_font_size() == 24

    def test_explicit_font_size_overrides_hires_natural_size(self):
        """Even with HiresFont, an explicit `font_size` on the widget
        takes precedence (rare — usually equal — but allowed)."""
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        w = _DummyImage(font=font, font_size=32)
        assert w._resolved_font_size() == 32

    def test_construction_rejects_zero_font_size(self):
        """`font_size = 0` is rejected at construction (validation
        layer, separate from the helper's same check)."""
        import pytest

        from led_ticker.fonts import FONT_DEFAULT

        with pytest.raises(ValueError, match="font_size must be > 0"):
            _DummyImage(font=FONT_DEFAULT, font_size=0)

    def test_construction_rejects_negative_font_size(self):
        import pytest

        from led_ticker.fonts import FONT_DEFAULT

        with pytest.raises(ValueError, match="font_size must be > 0"):
            _DummyImage(font=FONT_DEFAULT, font_size=-5)


class TestSingleRowFontSize:
    """`_play_with_text` derives the wrap scale from `font_size` via
    `block_scale_for_font_size`. Smart default: BDF + `font_size=None`
    on bigsign wraps at scale=`_logical_scale`; small sign no wrap;
    explicit `font_size` honored exactly."""

    async def test_bdf_default_wraps_at_logical_scale_on_bigsign(
        self, swapping_frame, monkeypatch
    ):
        """BDF + `font_size=None` (smart default) + bigsign → wraps at
        scale=4. Same observable behavior as the old `text_scale=1`
        path post-bd61140."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.scaled_canvas import ScaledCanvas

        async def _instant(_):
            pass

        monkeypatch.setattr("led_ticker.widgets._image_base.asyncio.sleep", _instant)

        w = _DummyImage(text="hi", font=FONT_DEFAULT, font_size=None)
        w._logical_scale = 4

        captured: list = []
        orig = _BaseImageWidget._render_tick

        def spy(self, canvas, text_canvas, *args, **kwargs):
            captured.append(
                {
                    "is_wrapped": isinstance(text_canvas, ScaledCanvas),
                    "scale": getattr(text_canvas, "scale", None),
                }
            )
            return orig(self, canvas, text_canvas, *args)

        _BaseImageWidget._render_tick = spy  # type: ignore[method-assign]
        real = _StubCanvas(width=256, height=64)
        swapping_frame.swap.return_value = _StubCanvas(width=256, height=64)

        try:
            await w._play_with_text(real, swapping_frame, n_ticks=1)
        finally:
            _BaseImageWidget._render_tick = orig  # type: ignore[method-assign]

        assert len(captured) >= 1
        assert all(c["is_wrapped"] for c in captured)
        assert all(
            c["scale"] == 4 for c in captured
        ), f"Expected wrapper at logical-scale (4); got {captured!r}"

    async def test_explicit_font_size_24_wraps_at_2(self, swapping_frame, monkeypatch):
        """Explicit `font_size=24` with BDF 6×12 on bigsign → block
        scale = 24 // 12 = 2. User intent honored over `_logical_scale`."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.scaled_canvas import ScaledCanvas

        async def _instant(_):
            pass

        monkeypatch.setattr("led_ticker.widgets._image_base.asyncio.sleep", _instant)

        w = _DummyImage(text="hi", font=FONT_DEFAULT, font_size=24)
        w._logical_scale = 4

        captured: list = []
        orig = _BaseImageWidget._render_tick

        def spy(self, canvas, text_canvas, *args, **kwargs):
            if isinstance(text_canvas, ScaledCanvas):
                captured.append(text_canvas.scale)
            return orig(self, canvas, text_canvas, *args)

        _BaseImageWidget._render_tick = spy  # type: ignore[method-assign]
        real = _StubCanvas(width=256, height=64)
        swapping_frame.swap.return_value = _StubCanvas(width=256, height=64)

        try:
            await w._play_with_text(real, swapping_frame, n_ticks=1)
        finally:
            _BaseImageWidget._render_tick = orig  # type: ignore[method-assign]

        assert captured, "Wrapper not used"
        assert all(
            s == 2 for s in captured
        ), f"Expected wrapper.scale=2 (24px / 12px cell); got {captured!r}"

    async def test_no_wrap_on_small_sign_with_default(
        self, swapping_frame, monkeypatch
    ):
        """Small sign (`_logical_scale=1`) + BDF + `font_size=None` →
        block scale = 12 // 12 = 1 → no wrap."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.scaled_canvas import ScaledCanvas

        async def _instant(_):
            pass

        monkeypatch.setattr("led_ticker.widgets._image_base.asyncio.sleep", _instant)

        w = _DummyImage(text="hi", font=FONT_DEFAULT, font_size=None)
        w._logical_scale = 1

        captured: list = []
        orig = _BaseImageWidget._render_tick

        def spy(self, canvas, text_canvas, *args, **kwargs):
            captured.append(isinstance(text_canvas, ScaledCanvas))
            return orig(self, canvas, text_canvas, *args)

        _BaseImageWidget._render_tick = spy  # type: ignore[method-assign]
        real = _StubCanvas(width=160, height=16)
        swapping_frame.swap.return_value = _StubCanvas(width=160, height=16)

        try:
            await w._play_with_text(real, swapping_frame, n_ticks=1)
        finally:
            _BaseImageWidget._render_tick = orig  # type: ignore[method-assign]

        assert len(captured) >= 1, "_render_tick was never called"
        assert not any(captured), f"Expected NO wrap at scale=1; got {captured!r}"


class TestImageBaseColorProvider:
    def test_font_color_wrapped(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor

        w = _DummyImage(font_color=Color(255, 100, 50))
        assert isinstance(w.font_color, _ConstantColor)

    def test_top_color_wrapped(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor

        w = _DummyImage(top_text="A", bottom_text="B", top_color=Color(255, 100, 50))
        assert isinstance(w.top_color, _ConstantColor)

    def test_bottom_color_wrapped(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor

        w = _DummyImage(top_text="A", bottom_text="B", bottom_color=Color(0, 200, 100))
        assert isinstance(w.bottom_color, _ConstantColor)

    def test_provider_passed_through(self):
        from led_ticker.color_providers import Rainbow

        rainbow = Rainbow()
        w = _DummyImage(font_color=rainbow)
        assert w.font_color is rainbow

    def test_frame_aware_mixin(self):
        w = _DummyImage()
        assert w._frame_count == 0
        w.advance_frame()
        assert w._frame_count == 1


class TestPlayLoopAdvancesFrame:
    """Tripwire: `_play_with_text` and `_play_with_two_row_text` must
    call `advance_frame()` per tick so ColorProviders (Rainbow,
    ColorCycle) animate during gif/still playback. Without this, a
    rainbow `font_color` renders as a frozen gradient on hardware —
    the per-char hue offset is visible but doesn't sweep over time.
    """

    async def test_single_row_advances_frame_per_tick(
        self, swapping_frame, monkeypatch
    ):
        """Per-tick loop with scrolling text must increment _frame_count
        once per tick. The marquee auto-floor may extend the actual
        loop count past `n_ticks`, so assert `_frame_count` matches
        the painted-frame count rather than `n_ticks` directly."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT

        async def _instant(_):
            pass

        monkeypatch.setattr("led_ticker.widgets._image_base.asyncio.sleep", _instant)

        w = _DummyImage(
            text="hi", text_align="scroll_over", font=FONT_DEFAULT, font_size=None
        )
        w._logical_scale = 1
        real = _StubCanvas(width=160, height=16)
        swapping_frame.swap.return_value = _StubCanvas(width=160, height=16)

        await w._play_with_text(real, swapping_frame, n_ticks=5)

        # Each tick paints the image once; frame_count advances once
        # per tick. Both must have run at least n_ticks (5) but may
        # run more due to the marquee auto-floor.
        assert w._frame_count >= 5
        assert w._frame_count == len(w.paint_full_calls)

    async def test_two_row_advances_frame_per_tick(self, swapping_frame, monkeypatch):
        """Two-row per-tick loop must also advance _frame_count.
        FONT_SMALL (5×8) fits a 16-row canvas split 8/8."""
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_SMALL

        async def _instant(_):
            pass

        monkeypatch.setattr("led_ticker.widgets._image_base.asyncio.sleep", _instant)

        w = _DummyImage(
            top_text="A", bottom_text="B" * 80, font=FONT_SMALL, font_size=None
        )
        w._logical_scale = 1
        real = _StubCanvas(width=160, height=16)
        swapping_frame.swap.return_value = _StubCanvas(width=160, height=16)

        await w._play_with_two_row_text(real, swapping_frame, n_ticks=4)

        assert w._frame_count >= 4
        assert w._frame_count == len(w.paint_full_calls)

    async def test_static_fast_path_bypassed_for_animated_provider(
        self, swapping_frame
    ):
        """Static image + static text + Rainbow font_color must NOT
        take the fast path — the rainbow needs the per-tick loop to
        advance its frame counter. Tripwires that future fast-path
        conditions don't accidentally swallow non-constant providers.
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.color_providers import Rainbow
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(
            text="hi",
            text_align="left",
            font=FONT_DEFAULT,
            font_size=None,
            font_color=Rainbow(),
        )
        w._logical_scale = 1
        real = _StubCanvas(width=160, height=16)
        swapping_frame.swap.return_value = _StubCanvas(width=160, height=16)

        await w._play_with_text(real, swapping_frame, n_ticks=3)

        # If the fast path were taken, _frame_count would be 0 (one
        # paint, no tick loop). Per-tick loop ran → frame advanced.
        assert w._frame_count == 3

    async def test_static_fast_path_kept_for_constant_color(self, swapping_frame):
        """Static image + static text + constant Color → fast path
        still applies (paint once + sleep). _frame_count stays at 0.
        Asserts the fix didn't regress the fast-path optimization for
        the common case.
        """
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(
            text="hi",
            text_align="left",
            font=FONT_DEFAULT,
            font_size=None,
            font_color=Color(255, 100, 50),
        )
        w._logical_scale = 1
        real = _StubCanvas(width=160, height=16)
        swapping_frame.swap.return_value = _StubCanvas(width=160, height=16)

        await w._play_with_text(real, swapping_frame, n_ticks=10)

        # Fast path: one paint, no per-tick increment.
        assert w._frame_count == 0

    async def test_static_fast_path_kept_for_gradient_provider(self, swapping_frame):
        """Gradient is `frame_invariant=True` (output depends on
        char_index/total only — not frame). Static image + static text
        + Gradient → fast path applies. Tripwires that the fast-path
        gate uses the `frame_invariant` flag, not a strict
        isinstance(_ConstantColor) check that would penalize Gradient
        with an unnecessary per-tick loop."""
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import Gradient
        from led_ticker.fonts import FONT_DEFAULT

        w = _DummyImage(
            text="hi",
            text_align="left",
            font=FONT_DEFAULT,
            font_size=None,
            font_color=Gradient(Color(255, 0, 0), Color(0, 0, 255)),
        )
        w._logical_scale = 1
        real = _StubCanvas(width=160, height=16)
        swapping_frame.swap.return_value = _StubCanvas(width=160, height=16)

        await w._play_with_text(real, swapping_frame, n_ticks=10)

        assert w._frame_count == 0


class TestPlayWithTextDriftCompensation:
    """_play_with_text and _play_with_two_row_text must subtract elapsed
    work time from each tick's sleep so scroll speed stays accurate (C3).
    Each tick calls loop.time() twice: once at t0 and once inside max().
    """

    async def test_single_row_subtracts_work_time(self, monkeypatch):
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT

        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("led_ticker.widgets._image_base.asyncio.sleep", _record)

        tick_times = iter([0.000, 0.025] * 500)  # 25 ms work per tick
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.widgets._image_base.asyncio.get_running_loop",
            lambda: mock_loop,
        )

        frame = mock.Mock()
        frame.swap.return_value = _StubCanvas(width=160, height=16)

        w = _DummyImage(
            text="hi",
            text_align="scroll_over",
            font=FONT_DEFAULT,
            font_size=None,
            scroll_speed_ms=50,
        )
        w._logical_scale = 1
        real = _StubCanvas(width=160, height=16)

        await w._play_with_text(real, frame, n_ticks=3)

        tick_s = 50 / 1000  # scroll_speed_ms / 1000 = 0.05
        expected = tick_s - 0.025  # 0.025
        assert sleep_calls, "no per-tick sleep calls recorded"
        assert all(
            abs(s - expected) < 1e-9 for s in sleep_calls
        ), f"expected {expected}s sleeps (drift-compensated), got {sleep_calls}"


class _TrackingProvider:
    """Test provider: per_char=True, records every (frame, idx, total)."""

    per_char = True

    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    def color_for(self, frame, char_index, total_chars):
        from rgbmatrix.graphics import Color

        self.calls.append((frame, char_index, total_chars))
        return Color(255, 255, 255)


class TestPerCharProviderNonEmojiPath:
    """Tripwire: per-char providers (Rainbow, Gradient) must iterate
    chars on the plain-text path too — not just the emoji path. The
    smoke config §3 happens to use `:taco:` slugs so the bug hid
    behind the emoji path; this test pins the non-emoji path
    explicitly."""

    def test_single_row_per_char_provider_iterates_chars(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT

        provider = _TrackingProvider()
        w = _DummyImage(text="ABC", font=FONT_DEFAULT, font_color=provider)
        canvas = _StubCanvas(width=64, height=16)

        w._draw_text(canvas, 0, 12, w.font_color)

        assert [c[1] for c in provider.calls] == [0, 1, 2], (
            f"Expected per-char iteration with indices [0,1,2]; got "
            f"{[c[1] for c in provider.calls]!r}. Plain-text path is "
            f"materializing the provider once at char_index=0 instead "
            f"of dispatching to draw_text_per_char."
        )
        assert all(c[2] == 3 for c in provider.calls)

    def test_two_row_per_char_provider_iterates_chars(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT

        provider = _TrackingProvider()
        w = _DummyImage(
            top_text="A",
            bottom_text="DEF",
            font=FONT_DEFAULT,
            font_color=provider,
        )
        canvas = _StubCanvas(width=64, height=16)

        # Bottom row (the longer one) — should iterate 3 chars.
        w._draw_row_text(
            canvas,
            font=FONT_DEFAULT,
            text="DEF",
            color=provider,
            x=0,
            baseline_y=12,
            emoji_y=4,
            frame_count=0,
        )

        assert [c[1] for c in provider.calls] == [0, 1, 2]
        assert all(c[2] == 3 for c in provider.calls)


class TestImageBorderField:
    """`_BaseImageWidget` exposes a `border: BorderEffect | None`
    field that subclasses (StillImage, GifPlayer) inherit. Default
    is None — no border, no animation overhead."""

    def test_border_field_default(self):
        from led_ticker.widgets.still import StillImage

        # Use a tiny test PNG already shipped with the repo if any;
        # otherwise the field default is observable on the class
        # without instantiation.
        assert StillImage.__attrs_attrs__  # sanity: attrs class
        names = [a.name for a in StillImage.__attrs_attrs__]
        assert (
            "border" in names
        ), f"StillImage missing inherited `border` field; fields: {names}"

    def test_border_default_is_none(self, tmp_path):
        """Default value is None — confirmed via construction."""
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        widget = StillImage(path=img_path)
        assert widget.border is None


class TestRenderTickBorder:
    """Border integration in `_render_tick` — paints AFTER image
    paint and BEFORE text paint (non-scroll / scroll_over) or after
    everything (skip-black scroll). The 'border frames the panel'
    convention: text overlaps border on collision in modes where
    text paints on top of image; border overlaps text + image
    silhouette in skip-black mode."""

    @pytest.fixture
    def order_recorder(self, monkeypatch):
        """Patch `_paint_image`, `_paint_skip_black`, `_draw_text`,
        and a mock `border.paint` to record call order."""
        order: list[str] = []

        def _record(name):
            def _fn(self, *a, **kw):
                order.append(name)
                return 0  # _draw_text returns int (cursor advance)

            return _fn

        # Patch on `StillImage` (the subclass) — `_paint_skip_black`
        # is overridden there, so a base-class patch wouldn't
        # intercept the call. `raising=False` because `_paint_image`
        # / `_draw_text` are base-only and may not exist on the
        # subclass yet (monkeypatch adds them, which shadows the
        # base method via Python's attribute lookup order).
        from led_ticker.widgets.still import StillImage

        monkeypatch.setattr(
            StillImage, "_paint_image", _record("paint_image"), raising=False
        )
        monkeypatch.setattr(
            StillImage,
            "_paint_skip_black",
            _record("paint_skip_black"),
            raising=False,
        )
        monkeypatch.setattr(
            StillImage, "_draw_text", _record("draw_text"), raising=False
        )
        return order

    def _make_widget(self, tmp_path, text_align: str, border):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(
            path=img_path,
            text="hi",
            text_align=text_align,
            border=border,
        )

    def test_render_tick_left_paints_image_then_border_then_text(
        self, tmp_path, order_recorder
    ):
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order_recorder.append("border")

        widget = self._make_widget(tmp_path, "left", border)
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        assert order_recorder == [
            "paint_image",
            "border",
            "draw_text",
        ], f"left: expected image→border→text; got {order_recorder}"

    def test_render_tick_scroll_over_paints_image_then_border_then_text(
        self, tmp_path, order_recorder
    ):
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order_recorder.append("border")

        widget = self._make_widget(tmp_path, "scroll_over", border)
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        assert order_recorder == [
            "paint_image",
            "border",
            "draw_text",
        ], f"scroll_over: expected image→border→text; got {order_recorder}"

    def test_render_tick_scroll_paints_text_then_image_then_border(
        self, tmp_path, order_recorder
    ):
        """Skip-black scroll: text walks behind silhouette (existing
        semantics) — border lands LAST so it remains visible over
        both image and any text at panel edges."""
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order_recorder.append("border")

        widget = self._make_widget(tmp_path, "scroll", border)
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        assert order_recorder == [
            "draw_text",
            "paint_skip_black",
            "border",
        ], f"scroll: expected text→image-skip-black→border; got {order_recorder}"

    def test_render_tick_no_border_omits_paint(self, tmp_path, order_recorder):
        """Border=None: no border calls, image+text path unchanged."""
        from rgbmatrix import _StubCanvas as RealStub

        widget = self._make_widget(tmp_path, "left", None)
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        assert order_recorder == ["paint_image", "draw_text"]

    def test_render_tick_passes_frame_count_to_border(self, tmp_path):
        """border.paint receives the widget's current `_frame_count`."""
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False

        widget = self._make_widget(tmp_path, "left", border)
        widget._frame_count = 17
        canvas = RealStub(width=64, height=32)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        border.paint.assert_called_once_with(canvas, 17)


class TestRenderTwoRowTickBorder:
    """Border in two-row mode: paint AFTER image, BEFORE either
    row's text. Border target is the unwrapped real canvas (where
    the image was painted) — same convention as TwoRowMessage."""

    @pytest.fixture
    def order_recorder(self, monkeypatch):
        order: list[str] = []

        def _record(name):
            def _fn(self, *a, **kw):
                order.append(name)

            return _fn

        from led_ticker.widgets import _image_base

        monkeypatch.setattr(
            _image_base._BaseImageWidget,
            "_paint_image",
            _record("paint_image"),
            raising=False,
        )
        monkeypatch.setattr(
            _image_base._BaseImageWidget,
            "_draw_row_text",
            _record("draw_row_text"),
            raising=False,
        )
        return order

    def _make_widget(self, tmp_path, border):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(
            path=img_path,
            top_text="@brand",
            bottom_text="tagline",
            border=border,
        )

    def test_two_row_paints_image_then_border_then_rows(self, tmp_path, order_recorder):
        from rgbmatrix import _StubCanvas as RealStub

        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order_recorder.append("border")

        widget = self._make_widget(tmp_path, border)
        real_canvas = RealStub(width=128, height=32)
        # Pre-resolved row tuples are what the loop passes; values
        # here are placeholders (color/x/baseline don't matter
        # because _draw_row_text is patched to a recorder).
        top = (None, "@brand", None, 0, 6, 0)
        bottom = (None, "tagline", None, 0, 22, 0)

        widget._render_two_row_tick(real_canvas, real_canvas, top, bottom)

        assert order_recorder == [
            "paint_image",
            "border",
            "draw_row_text",
            "draw_row_text",
        ], f"expected image→border→top→bottom; got {order_recorder}"

    def test_two_row_no_border_runs_clean(self, tmp_path, order_recorder):
        """Border=None: image + 2 row draws, no border calls."""
        from rgbmatrix import _StubCanvas as RealStub

        widget = self._make_widget(tmp_path, None)
        real_canvas = RealStub(width=128, height=32)
        top = (None, "@brand", None, 0, 6, 0)
        bottom = (None, "tagline", None, 0, 22, 0)

        widget._render_two_row_tick(real_canvas, real_canvas, top, bottom)

        assert order_recorder == [
            "paint_image",
            "draw_row_text",
            "draw_row_text",
        ]

    def test_two_row_border_receives_widget_frame_count(self, tmp_path, monkeypatch):
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets import _image_base

        border = mock.Mock()
        border.frame_invariant = False

        monkeypatch.setattr(
            _image_base._BaseImageWidget,
            "_draw_row_text",
            lambda self, *a, **kw: None,
            raising=False,
        )

        widget = self._make_widget(tmp_path, border)
        widget._frame_count = 99
        real_canvas = RealStub(width=128, height=32)
        top = (None, "@brand", None, 0, 6, 0)
        bottom = (None, "tagline", None, 0, 22, 0)

        widget._render_two_row_tick(real_canvas, real_canvas, top, bottom)

        border.paint.assert_called_once_with(real_canvas, 99)


class TestRowColorFrameFallback:
    """When `top_color` / `bottom_color` are None, `_row_color()` falls
    back to `self.font_color`. The per-effect frame lookup must follow
    the same fallback — otherwise a continuous-phase rainbow set via
    `font_color` (with `restart_on_visit = False`) would silently restart
    its chase on each visit, because the `top_color`/`bottom_color`
    keys aren't registered in `_effect_frames` (no effect there to
    register) and `frame_for()` would fall through to the primary
    `_frame_count` (which always resets per visit).
    """

    def _make_widget(self, tmp_path, *, top_color=None, bottom_color=None):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(
            path=img_path,
            top_text="@brand",
            bottom_text="tagline",
            top_color=top_color,
            bottom_color=bottom_color,
        )

    def test_row_color_attr_falls_back_to_font_color_when_per_row_none(self, tmp_path):
        widget = self._make_widget(tmp_path, top_color=None, bottom_color=None)
        assert widget._row_color_attr(0) == "font_color"
        assert widget._row_color_attr(1) == "font_color"

    def test_row_color_attr_uses_per_row_key_when_set(self, tmp_path):
        from rgbmatrix import graphics

        widget = self._make_widget(
            tmp_path,
            top_color=graphics.Color(255, 0, 0),
            bottom_color=graphics.Color(0, 255, 0),
        )
        assert widget._row_color_attr(0) == "top_color"
        assert widget._row_color_attr(1) == "bottom_color"

    def test_row_color_attr_mixed_per_row_and_fallback(self, tmp_path):
        from rgbmatrix import graphics

        widget = self._make_widget(
            tmp_path, top_color=graphics.Color(255, 0, 0), bottom_color=None
        )
        assert widget._row_color_attr(0) == "top_color"
        assert widget._row_color_attr(1) == "font_color"

    def test_two_row_render_reads_font_color_counter_when_no_per_row(
        self, tmp_path, monkeypatch
    ):
        """Regression: when both per-row colors are None and the
        widget's `font_color` is the actual provider, the row's
        `_draw_row_text` call must receive `frame_for("font_color")`
        — NOT `frame_for("top_color")` (which falls back to
        `_frame_count` since no effect is registered there).
        """
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets import _image_base

        captured: list[int] = []

        def _capture(self, *args, **kwargs):
            captured.append(kwargs["frame_count"])

        monkeypatch.setattr(
            _image_base._BaseImageWidget,
            "_draw_row_text",
            _capture,
            raising=False,
        )

        widget = self._make_widget(tmp_path, top_color=None, bottom_color=None)
        # Simulate: rainbow on font_color advanced 7 ticks across visits
        # (continuous-phase, would NOT reset on visit-entry); engine tick
        # counter just got reset for the new visit.
        widget._effect_frames["font_color"] = 7
        widget._frame_count = 0

        real_canvas = RealStub(width=128, height=32)
        top = (None, "@brand", None, 0, 6, 0)
        bottom = (None, "tagline", None, 0, 22, 0)

        widget._render_two_row_tick(real_canvas, real_canvas, top, bottom)

        assert captured == [
            7,
            7,
        ], f"both rows should read font_color's counter (7); got {captured}"

    def test_two_row_render_reads_per_row_counter_when_set(self, tmp_path, monkeypatch):
        """Per-row knob set: the row reads its own counter,
        independent of `font_color`. This is the path TwoRowMessage
        already exercised; the test is here so the two paths can't
        drift — image two-row honors the per-row key when present.
        """
        from rgbmatrix import _StubCanvas as RealStub
        from rgbmatrix import graphics

        from led_ticker.widgets import _image_base

        captured: list[int] = []

        def _capture(self, *args, **kwargs):
            captured.append(kwargs["frame_count"])

        monkeypatch.setattr(
            _image_base._BaseImageWidget,
            "_draw_row_text",
            _capture,
            raising=False,
        )

        widget = self._make_widget(
            tmp_path,
            top_color=graphics.Color(255, 0, 0),
            bottom_color=graphics.Color(0, 255, 0),
        )
        widget._effect_frames["top_color"] = 11
        widget._effect_frames["bottom_color"] = 22
        widget._effect_frames["font_color"] = 99  # should NOT be read
        widget._frame_count = 0

        real_canvas = RealStub(width=128, height=32)
        top = (None, "@brand", None, 0, 6, 0)
        bottom = (None, "tagline", None, 0, 22, 0)

        widget._render_two_row_tick(real_canvas, real_canvas, top, bottom)

        assert captured == [
            11,
            22,
        ], f"rows should read their own per-row counters; got {captured}"


class TestPlayWithTextBorderFastPath:
    """Fast-path gate in `_play_with_text` must consider
    `border.frame_invariant`. Animated border (rainbow with
    speed>0) forces the per-tick loop; constant border keeps the
    fast path."""

    @pytest.fixture
    def static_widget(self, tmp_path):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        # Static text: text_align="left", no scroll, text_loops=0,
        # is_static() True (StillImage), color_is_static (default).
        return StillImage(
            path=img_path,
            text="HI",
            text_align="left",
            hold_seconds=0.5,  # 10 ticks at 50ms
        )

    async def test_fast_path_with_constant_border_runs_once(
        self, static_widget, mock_frame
    ):
        """ConstantBorder is frame_invariant=True; fast path stays
        valid. _render_tick runs once, then the path sleeps."""
        from led_ticker.borders import ConstantBorder

        static_widget.border = ConstantBorder([255, 0, 0])

        with (
            mock.patch.object(type(static_widget), "_render_tick") as render_mock,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            await static_widget._play_with_text(
                mock_frame.swap.return_value,
                mock_frame,
                n_ticks=10,
            )
        assert render_mock.call_count == 1, (
            f"ConstantBorder (frame_invariant) must take fast path; "
            f"got {render_mock.call_count} render calls"
        )

    async def test_fast_path_bypassed_with_animated_border(
        self, static_widget, mock_frame
    ):
        """RainbowChaseBorder(speed=4) is NOT frame_invariant; fast
        path bypassed; per-tick loop runs n_ticks times."""
        from led_ticker.borders import RainbowChaseBorder

        static_widget.border = RainbowChaseBorder(speed=4)

        with (
            mock.patch.object(type(static_widget), "_render_tick") as render_mock,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            await static_widget._play_with_text(
                mock_frame.swap.return_value,
                mock_frame,
                n_ticks=10,
            )
        assert render_mock.call_count == 10, (
            f"Animated border must force per-tick loop; got "
            f"{render_mock.call_count} renders, expected 10"
        )


class TestPlayWithTwoRowBorderFastPath:
    """Same fast-path gate logic on the two-row playback path."""

    @pytest.fixture
    def static_widget(self, tmp_path):
        from PIL import Image

        from led_ticker.fonts import FONT_SMALL
        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        # Two-row mode: bottom_text non-empty + bottom fits (no scroll).
        # FONT_SMALL (5×8) has line-height=8 which fits the 8-row band
        # of a 50/50 split on a 16-tall mock canvas.
        return StillImage(
            path=img_path,
            top_text="@",
            bottom_text="x",
            top_align="center",
            bottom_align="center",
            hold_seconds=0.5,
            font=FONT_SMALL,
        )

    async def test_two_row_fast_path_with_constant_border(
        self, static_widget, mock_frame
    ):
        from led_ticker.borders import ConstantBorder

        static_widget.border = ConstantBorder([0, 255, 0])

        with (
            mock.patch.object(
                type(static_widget), "_render_two_row_tick"
            ) as render_mock,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            await static_widget._play_with_two_row_text(
                mock_frame.swap.return_value,
                mock_frame,
                n_ticks=10,
            )
        assert render_mock.call_count == 1

    async def test_two_row_fast_path_bypassed_with_animated_border(
        self, static_widget, mock_frame
    ):
        from led_ticker.borders import RainbowChaseBorder

        static_widget.border = RainbowChaseBorder(speed=4)

        with (
            mock.patch.object(
                type(static_widget), "_render_two_row_tick"
            ) as render_mock,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            await static_widget._play_with_two_row_text(
                mock_frame.swap.return_value,
                mock_frame,
                n_ticks=10,
            )
        assert render_mock.call_count == 10


class TestImageBorderPhysicalResolution:
    """End-to-end tripwire: rendering an image widget with a border
    on a bigsign-style ScaledCanvas (scale=4) MUST paint border
    pixels on the real 256×64 panel perimeter, NOT on the wrapper's
    logical 64×16 perimeter. Mirrors the TwoRowMessage tripwire."""

    def test_border_paints_to_real_perimeter_through_scaled_canvas(self, tmp_path):
        from PIL import Image
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.borders import ConstantBorder
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.still import StillImage

        # Build a still + ConstantBorder([255, 255, 255]).
        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        widget = StillImage(
            path=img_path,
            text="HI",
            text_align="left",
            border=ConstantBorder([255, 255, 255], thickness=1),
        )

        # Real bigsign-style canvas (256x64) wrapped at scale=4 →
        # logical 64x16.
        real = RealStub(width=256, height=64)
        wrapper = ScaledCanvas(real, scale=4, content_height=16)

        widget._render_tick(wrapper, wrapper, 0, 12, 2, 60)

        # The border is white (255,255,255) — assert that the corner
        # pixels of the REAL 256x64 canvas are lit.
        # Top-left corner: real (0, 0) should be white.
        # Top-right corner: real (255, 0) should be white.
        # Bottom-left: real (0, 63). Bottom-right: real (255, 63).
        for x, y in [(0, 0), (255, 0), (0, 63), (255, 63)]:
            r, g, b = real.get_pixel(x, y)
            assert (r, g, b) == (255, 255, 255), (
                f"real corner ({x}, {y}) expected white border; "
                f"got ({r}, {g}, {b}). Border did not paint at "
                f"physical resolution — `unwrap_to_real` may have "
                f"been dropped."
            )

        # And: the next-inner ring of REAL pixels (1, 1), (254, 1)
        # etc. must NOT be white (they're either image or black) —
        # otherwise the border is leaking inward (4×4 block painting).
        for x, y in [(1, 1), (254, 1), (1, 62), (254, 62)]:
            r, g, b = real.get_pixel(x, y)
            assert (r, g, b) != (255, 255, 255), (
                f"real ({x}, {y}) is white — border painting at "
                f"4×4 block resolution instead of 1 LED. Likely "
                f"missing `unwrap_to_real` in the border path."
            )


class TestImageTypewriter:
    """Single-row typewriter on image widgets. Validation + render
    + fast-path bypass + per-effect counter wiring."""

    def _make_still(self, tmp_path, **kwargs):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(path=img_path, **kwargs)

    def test_animation_with_bottom_text_raises(self, tmp_path):
        from led_ticker.animations import Typewriter

        with pytest.raises(ValueError, match="two-row mode"):
            self._make_still(
                tmp_path,
                top_text="hi",
                bottom_text="there",
                animation=Typewriter(),
            )

    def test_animation_with_scroll_align_raises(self, tmp_path):
        from led_ticker.animations import Typewriter

        with pytest.raises(ValueError, match="text_align"):
            self._make_still(
                tmp_path,
                text="Hello",
                text_align="scroll",
                fit="pillarbox",
                animation=Typewriter(),
            )

    def test_animation_with_scroll_over_align_raises(self, tmp_path):
        from led_ticker.animations import Typewriter

        with pytest.raises(ValueError, match="text_align"):
            self._make_still(
                tmp_path,
                text="Hello",
                text_align="scroll_over",
                animation=Typewriter(),
            )

    def test_animation_with_empty_text_raises(self, tmp_path):
        from led_ticker.animations import Typewriter

        with pytest.raises(ValueError, match="non-empty text"):
            self._make_still(
                tmp_path,
                text="",
                text_align="left",
                animation=Typewriter(),
            )

    def test_animation_field_accepts_typewriter(self, tmp_path):
        """No validation conflict: text_align=left, single-row, non-empty
        text → construction succeeds."""
        from led_ticker.animations import Typewriter

        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="left",
            animation=Typewriter(),
        )
        assert widget.animation is not None
        assert isinstance(widget.animation, Typewriter)

    def test_visible_text_slices_per_frame(self, tmp_path):
        """Pre-populate the animation per-effect counter to specific
        values; assert `_visible_text` returns the typed-so-far slice
        at each frame. At default frames_per_char=3 with chars_per_frame=1:
          frame=0 → 1 char (Typewriter's `progress = (0 // 3) + 1 = 1`)
          frame=2 → 1 char (still in the first frames_per_char window)
          frame=3 → 2 chars
          frame=6 → 3 chars
          frame=999 → all 5 chars (clamped to len(text)).
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter

        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="left",
            animation=Typewriter(),
        )
        canvas = _StubCanvas(width=64, height=16)

        # frame_count is passed directly; the helper does not read
        # `_effect_frames` (the caller resolves the counter via
        # `self.frame_for("animation")` and passes the result here).
        assert widget._visible_text(0, canvas) == "H"
        assert widget._visible_text(3, canvas) == "He"
        assert widget._visible_text(6, canvas) == "Hel"
        assert widget._visible_text(999, canvas) == "Hello"

    def test_visible_text_returns_full_text_when_no_animation(self, tmp_path):
        """`animation = None` (default): helper returns `self.text`
        unchanged so layout / draw code that always calls the helper
        is correct for the no-animation case too."""
        from rgbmatrix import _StubCanvas

        widget = self._make_still(tmp_path, text="Hello", text_align="left")
        canvas = _StubCanvas(width=64, height=16)
        assert widget.animation is None
        assert widget._visible_text(0, canvas) == "Hello"
        assert widget._visible_text(99, canvas) == "Hello"

    async def test_fast_path_bypassed_with_animation(self, tmp_path, mocker):
        """Static still + text_align=left + animation=Typewriter must
        bypass the paint-once-and-sleep fast path so the typewriter's
        per-tick reveal actually runs. Mirrors the existing
        TestPlayWithTextBorderFastPath bypass for animated borders.

        Fast path: `SwapOnVSync.call_count == 1`. Slow path:
        `SwapOnVSync.call_count > 1`. We assert > 1.
        """
        from led_ticker.animations import Typewriter

        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="left",
            hold_seconds=0.5,
            animation=Typewriter(),
        )

        frame = mocker.MagicMock()
        # Each swap returns a fresh canvas (mirrors swapping_frame fixture
        # — see CLAUDE.md tripwire #1).
        frame.swap.side_effect = lambda c: c
        # Auto-MagicMock canvas needs concrete width/height for _load's
        # panel-dim arithmetic and for downstream layout math.
        frame.swap.return_value.width = 64
        frame.swap.return_value.height = 16
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await widget.play(frame.swap.return_value, frame, loop_count=1)

        # Slow path runs N ticks; we just need > 1 to prove fast path
        # was bypassed. Default `hold_seconds=0.5` → ~10 ticks at 50ms.
        assert frame.swap.call_count > 1, (
            f"animation=Typewriter must force per-tick loop; "
            f"got SwapOnVSync.call_count={frame.swap.call_count} "
            f"(==1 means fast path ran, freezing typewriter at frame=0)"
        )

    def test_right_align_typewriter_anchors_to_full_text_position(self, tmp_path):
        """Layout invariant: under right-align, each typed-in char
        appears at its FINAL panel position — the partial text occupies
        the same span the full text will eventually occupy. Concretely:
        text_x_right is computed once from the FULL text width, and the
        leading char "H" appears at that x at frame=0 and stays there
        as "He", "Hel", ... grow to the right.

        If the implementation regressed to recomputing text_x_right
        against the visible slice, "H" alone would be drawn flush-right
        (x ~ canvas.width-EDGE_PAD-1char) and would visibly slide LEFT
        as more chars are typed in. This tripwire pins the leftmost
        lit pixel as the layout anchor.

        Spec: docs/superpowers/specs/2026-05-07-image-typewriter-design.md
        — "Layout (text_x, baseline_y) is already computed against the
        FULL text width by the caller — we only override the rendered
        string here. This is what makes typewriter feel 'anchored' under
        right-align."
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter

        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="right",
            animation=Typewriter(),
        )
        # Mirror the text_x_right math from `_play_with_text`:
        # max(EDGE_PAD, text_w - full_text_width - EDGE_PAD) + offset.
        # We compute against the full-text width (not visible slice).
        sizing_canvas = _StubCanvas(width=64, height=16)
        full_text_w = widget._measure_text(sizing_canvas)
        text_w = 64
        TEXT_EDGE_PADDING_PX = 2
        text_x_right = max(
            TEXT_EDGE_PADDING_PX,
            text_w - full_text_w - TEXT_EDGE_PADDING_PX,
        )
        text_x_left = TEXT_EDGE_PADDING_PX

        leftmost_x_per_frame: list[int] = []
        for frame_count in (0, 3, 6):
            widget._effect_frames["animation"] = frame_count
            canvas = _StubCanvas(width=64, height=16)
            widget._render_tick(canvas, canvas, 0, 12, text_x_left, text_x_right)
            lit_xs = [
                x
                for y in range(16)
                for x in range(64)
                if canvas.get_pixel(x, y) != (0, 0, 0)
            ]
            leftmost_x_per_frame.append(min(lit_xs) if lit_xs else -1)

        # All three should report the same leftmost x — "H" sits where
        # "H" of the full "Hello" will sit. If text_x recomputed off
        # the visible slice, "H" alone would land far right (flush
        # against the panel edge) and slide left at frame 3 / 6.
        spread = max(leftmost_x_per_frame) - min(leftmost_x_per_frame)
        assert spread <= 2, (
            f"right-align typewriter should anchor leftmost char to "
            f"full-text position; got leftmost-x per frame: "
            f"{leftmost_x_per_frame} (spread={spread}). A spread > 2 "
            f"means text shifted as visible_text grew — text_x_right "
            f"was recomputed against the visible slice instead of the "
            f"full text width."
        )

    def test_per_char_hue_anchors_to_full_text_length(self, tmp_path):
        """When typewriter mid-cycles a per-char rainbow, total_chars
        must be `len(self.text)` (full eventual length) — not the
        visible slice length. Otherwise hue per char drifts as reveal
        grows. Spec: docs/superpowers/specs/2026-05-07-image-typewriter-design.md
        "Per-char providers ... pass total_chars=len(self.text)".
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter

        class _LocalTrackingProvider:
            per_char = True
            frame_invariant = False

            def __init__(self):
                self.calls: list[tuple[int, int, int]] = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color

                self.calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        provider = _LocalTrackingProvider()
        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="left",
            font_color=provider,
            animation=Typewriter(),
        )

        # Drive two frames with different visible-slice lengths.
        # frame=3 → "He" visible (2 chars), frame=6 → "Hel" (3 chars).
        widget._effect_frames["animation"] = 3
        canvas = _StubCanvas(width=64, height=16)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)
        totals_at_frame_3 = {c[2] for c in provider.calls}
        provider.calls.clear()

        widget._effect_frames["animation"] = 6
        canvas = _StubCanvas(width=64, height=16)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)
        totals_at_frame_6 = {c[2] for c in provider.calls}

        # Both runs should report total=5 (length of "Hello"). If the
        # implementation regresses to total=visible-len, frame=3 would
        # see total=2 and frame=6 would see total=3.
        assert totals_at_frame_3 == {5}, (
            f"At frame=3 (visible='He'), provider should see total=5 "
            f"(len of full text 'Hello'); got {totals_at_frame_3}"
        )
        assert totals_at_frame_6 == {5}, (
            f"At frame=6 (visible='Hel'), provider should see total=5; "
            f"got {totals_at_frame_6}"
        )

    def test_per_char_hue_anchors_across_emoji_boundaries(self, tmp_path):
        """Tripwire for the emoji-branch hue-anchoring fix:
        typewriter + emoji + per-char rainbow must keep a char's
        hue stable across the reveal, not drift as more chars type
        in. Specifically: the (frame, char_index, total_chars) tuple
        for char index 0 at a mid-type frame should have the same
        `total_chars` as at completion. Without the `total_chars`
        override into `draw_with_emoji`, the slice-length total
        would drift.
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter

        class _TrackingProvider:
            per_char = True
            frame_invariant = False

            def __init__(self):
                self.calls = []

            def color_for(self, frame, char_index, total_chars):
                from rgbmatrix.graphics import Color

                self.calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        provider = _TrackingProvider()
        widget = self._make_still(
            tmp_path,
            text="Hi :star:",  # 3 text chars ("H", "i", " ") + emoji
            text_align="left",
            font_color=provider,
            animation=Typewriter(),
        )
        canvas = _StubCanvas(width=64, height=16)

        # Mid-type: visible slice is "H" (frame=0, 1 char visible).
        widget._effect_frames["animation"] = 0
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)
        mid_type_totals = {c[2] for c in provider.calls}
        provider.calls.clear()

        # Completion: full text typed and rendered.
        widget._effect_frames["animation"] = 999
        canvas = _StubCanvas(width=64, height=16)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)
        completion_totals = {c[2] for c in provider.calls}

        # Both runs should report total=3 (text chars in "Hi :star:":
        # "H", "i", " " — emoji excluded). If the implementation regressed
        # to slice-length total, mid-type would see total=1 (just "H").
        assert mid_type_totals == {3}, (
            f"At frame=0 (visible='H'), provider should see total=3 "
            f"(text-char count of full 'Hi :star:'); got {mid_type_totals}"
        )
        assert completion_totals == {
            3
        }, f"At completion, provider should see total=3; got {completion_totals}"

    def test_three_effect_composition_independent_counters(self, tmp_path):
        """Architectural promise from PR #12: typewriter + rainbow font +
        rainbow border on the same widget tick on independent per-effect
        counters. This test verifies all three counters flow through to
        their respective effects without cross-contamination.
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.animations import Typewriter
        from led_ticker.borders import RainbowChaseBorder
        from led_ticker.color_providers import Rainbow

        border = RainbowChaseBorder(speed=4)
        border_frames_seen: list[int] = []
        original_paint = border.paint

        def _spy(canvas, frame_count):
            border_frames_seen.append(frame_count)
            return original_paint(canvas, frame_count)

        border.paint = _spy  # type: ignore[method-assign]

        widget = self._make_still(
            tmp_path,
            text="Hello",
            text_align="left",
            font_color=Rainbow(),
            animation=Typewriter(),
            border=border,
        )

        # Pre-populate distinct per-effect counters; reset _frame_count
        # to confirm effects do NOT read it directly.
        widget._effect_frames["animation"] = 2
        widget._effect_frames["font_color"] = 50
        widget._effect_frames["border"] = 100
        widget._frame_count = 0

        canvas = _StubCanvas(width=64, height=16)
        widget._render_tick(canvas, canvas, 0, 12, 2, 60)

        # Border read its own counter (100), not _frame_count (0).
        assert border_frames_seen == [100], (
            f"border.paint should see border counter (100); got "
            f"{border_frames_seen} — likely _frame_count was read"
        )
        # Typewriter slice from animation counter (2) — at default
        # frames_per_char=3, frame=2 is still in the first window so
        # only 1 char visible.
        assert (
            widget._visible_text(2, canvas) == "H"
        ), "animation counter should drive _visible_text; got wrong slice"

"""Tests for led_ticker.borders — perimeter geometry + animation."""

from __future__ import annotations

import unittest.mock as mock

import pytest

from led_ticker.app.coercion import _coerce_border
from led_ticker.borders import (
    BAND_PALETTES,
    ColorBandsBorder,
    ColorCycleBorder,
    ConstantBorder,
    LightbulbBorder,
    RainbowChaseBorder,
    _lightbulb_positions,
    _perimeter_pixels,
)
from led_ticker.color_lut import hue_color
from led_ticker.scaled_canvas import ScaledCanvas


class TestPerimeterGeometry:
    """`_perimeter_pixels` must walk every panel-perimeter pixel
    exactly once in clockwise order. Used as the index map for the
    rainbow-chase hue formula — index drift = visible artifacts."""

    def test_count_thickness_1(self):
        # 2×(W+H) − 4 corners that would otherwise be double-counted
        for w, h in [(10, 4), (256, 64), (160, 16), (5, 5)]:
            px = _perimeter_pixels(w, h, thickness=1)
            assert len(px) == 2 * (w + h) - 4, (
                f"{w}×{h}: expected {2 * (w + h) - 4}, got {len(px)}"
            )

    def test_no_duplicates_thickness_1(self):
        px = _perimeter_pixels(20, 8, thickness=1)
        assert len(set(px)) == len(px), "perimeter pixels must be unique"

    def test_clockwise_starts_at_origin(self):
        px = _perimeter_pixels(10, 4, thickness=1)
        assert px[0] == (0, 0)
        # Top edge first: row y=0
        for i in range(9):  # cols 0..8
            assert px[i] == (i, 0)
        # Right edge: col x=9, rows 0..2 (3 pixels — 0 is corner already counted)
        assert px[9] == (9, 0)
        assert px[10] == (9, 1)
        assert px[11] == (9, 2)

    def test_thickness_2_produces_two_rings(self):
        # 10×4 panel, thickness=2: outer ring 24 + inner ring (8x2 frame
        # = 2*(8+2)-4 = 16) = 40 pixels total.
        px = _perimeter_pixels(10, 4, thickness=2)
        assert len(px) == 24 + 16, (
            f"thickness=2 on 10×4 should give 40 pixels; got {len(px)}"
        )
        # All unique
        assert len(set(px)) == len(px)

    def test_thickness_collapses_on_tiny_canvas(self):
        # 4×4 panel, thickness=2: outer ring is 12 pixels; inner ring
        # would be 2×2 = 4 pixels (the entire inner area).
        px = _perimeter_pixels(4, 4, thickness=2)
        assert len(set(px)) == len(px)
        assert all(0 <= x < 4 and 0 <= y < 4 for x, y in px)

    def test_thickness_zero_returns_empty(self):
        assert _perimeter_pixels(10, 4, thickness=0) == []

    def test_collapsed_ring_does_not_duplicate_on_narrow_panel(self):
        """Tripwire: when an inner ring collapses to a single column
        (`x1 == x0`) or single row (`y1 == y0`), the function must
        skip that ring instead of walking the same column/row twice.
        Without the bail, the right-edge AND left-edge walks would
        each emit the same column, producing duplicate pixels and
        misaligning the chase pattern's perimeter index.

        `_perimeter_pixels(3, 10, 2)` exercises the failure case:
        outer ring is healthy (3-wide, 10-tall), inner ring at
        `ring=1` has `x0=1, x1=1` (degenerate single column). Pre-
        fix output had 36 pixels with only 30 unique."""
        for w, h, t in [(3, 10, 2), (10, 3, 2), (1, 10, 1), (10, 1, 1)]:
            px = _perimeter_pixels(w, h, thickness=t)
            assert len(set(px)) == len(px), (
                f"{w}×{h} t={t}: expected no duplicates, got "
                f"{len(px) - len(set(px))} duplicates"
            )

    def test_collapsed_inner_ring_skipped_outer_kept(self):
        """On 3×10 thickness=2: outer ring should still be the
        healthy 2*(3+10)-4 = 22-pixel outline; inner ring should
        contribute nothing (skipped via the bail)."""
        px = _perimeter_pixels(3, 10, thickness=2)
        assert len(px) == 2 * (3 + 10) - 4 == 22

    def test_same_args_return_cached_object(self):
        """_perimeter_pixels is pure — repeated calls with the same
        args must return the same list object, not a freshly-built one.
        Without caching, each call allocates a new list every frame."""
        a = _perimeter_pixels(160, 16, thickness=1)
        b = _perimeter_pixels(160, 16, thickness=1)
        assert a is b, (
            "_perimeter_pixels should be @functools.cache'd — same args must "
            "return the same list object"
        )


class _StubCanvas:
    """Minimal canvas double for paint tests — captures SetPixel calls."""

    def __init__(self, w: int, h: int):
        self.width = w
        self.height = h
        self.pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self.pixels[(x, y)] = (r, g, b)


class TestRainbowChaseBorder:
    """Per-pixel rainbow chase. Hue at perimeter index `idx` and frame
    `f`: ((idx * char_offset) + f * speed) % 360."""

    def test_rainbow_chase_border_satisfies_protocol(self):
        """RainbowChaseBorder must structurally satisfy BorderEffect even
        though its frame_invariant is a @property rather than a plain class
        attribute.  BorderEffect is not @runtime_checkable (isinstance is
        unavailable), so we verify the two required members directly:
        frame_invariant is accessible on an instance and paint is callable."""
        b = RainbowChaseBorder()
        # frame_invariant is a @property — hasattr resolves it correctly.
        assert hasattr(b, "frame_invariant"), "frame_invariant must be accessible"
        assert isinstance(b.frame_invariant, bool), (
            "frame_invariant must return bool (property, not plain attribute)"
        )
        assert callable(b.paint), "paint must be callable"

    def test_frame_invariant_false_for_default_speed(self):
        """Default speed=4 means the chase advances per frame —
        output is frame-variant."""
        assert RainbowChaseBorder().frame_invariant is False

    def test_frame_invariant_true_for_speed_zero(self):
        """speed=0 makes the chase stationary — output is identical
        every frame, so the effect is genuinely frame-invariant.
        Dynamic property lets a future fast-path gate correctly
        skip per-tick redraws on a pinned-but-rainbow border."""
        assert RainbowChaseBorder(speed=0).frame_invariant is True
        # char_offset doesn't affect frame-invariance — only speed.
        assert RainbowChaseBorder(speed=0, char_offset=12).frame_invariant is True
        assert RainbowChaseBorder(speed=0, char_offset=0).frame_invariant is True

    def test_frame_invariant_false_for_speed_zero_with_nonzero_default(self):
        """Sanity: any nonzero speed → frame-variant regardless of
        char_offset value."""
        assert RainbowChaseBorder(speed=1, char_offset=0).frame_invariant is False
        assert RainbowChaseBorder(speed=99).frame_invariant is False

    def test_paints_every_perimeter_pixel(self):
        c = _StubCanvas(20, 8)
        RainbowChaseBorder().paint(c, frame_count=0)
        # Should hit exactly the perimeter (2*(20+8)-4 = 52 pixels).
        assert len(c.pixels) == 52
        # Every painted pixel is on the perimeter (x==0 or x==19 or y==0 or y==7).
        for x, y in c.pixels:
            assert x in (0, 19) or y in (0, 7)

    def test_chase_advances_with_frame(self):
        """Different frame_count values produce different hues at the
        same perimeter position. Without this, the chase would be
        static."""
        c0 = _StubCanvas(20, 8)
        c1 = _StubCanvas(20, 8)
        RainbowChaseBorder(speed=8, char_offset=12).paint(c0, frame_count=0)
        RainbowChaseBorder(speed=8, char_offset=12).paint(c1, frame_count=10)
        # Same pixel address must have different colors across frames.
        differing = sum(1 for k in c0.pixels if c0.pixels[k] != c1.pixels[k])
        assert differing > 0, "chase did not advance with frame_count"

    def test_unwraps_scaled_canvas_to_paint_real_pixels(self):
        """When given a ScaledCanvas, the border paints to the
        underlying real canvas (1 LED per pixel) — not through the
        wrapper's scale × scale block expansion."""
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _StubCanvas(64, 32)
        wrapper = ScaledCanvas(real, scale=4, content_height=8)
        RainbowChaseBorder().paint(wrapper, frame_count=0)
        # Pixels should appear on the REAL canvas at native resolution
        # (no block expansion). Real perimeter is 2*(64+32)-4 = 188 px.
        assert len(real.pixels) == 188
        # Wrapper itself should NOT have received any SetPixel calls
        # — but `_StubCanvas` doesn't know it's wrapped, so this is
        # implicit in the count check above.

    def test_char_offset_zero_uniform_per_frame(self):
        """char_offset=0 means every perimeter pixel shares one hue
        per frame (synchronized whole-border cycle). Sanity check
        that the formula simplifies correctly."""
        c = _StubCanvas(20, 8)
        RainbowChaseBorder(char_offset=0, speed=4).paint(c, frame_count=0)
        # All pixels should be the same color at frame=0 with char_offset=0.
        colors = set(c.pixels.values())
        assert len(colors) == 1, f"expected uniform color, got {colors}"

    def test_char_offset_zero_cycles_across_frames(self):
        """Pairs with `test_char_offset_zero_uniform_per_frame`. With
        char_offset=0 AND speed>0, each frame produces a uniform
        color, but that color cycles between frames. Without this,
        the synchronized whole-border cycle would be stuck on a
        single hue."""
        c0 = _StubCanvas(20, 8)
        c1 = _StubCanvas(20, 8)
        RainbowChaseBorder(char_offset=0, speed=4).paint(c0, frame_count=0)
        RainbowChaseBorder(char_offset=0, speed=4).paint(c1, frame_count=10)
        color0 = next(iter(set(c0.pixels.values())))
        color1 = next(iter(set(c1.pixels.values())))
        assert color0 != color1, (
            f"Expected the synchronized cycle to advance with frame_count; "
            f"got identical hue {color0} at frame=0 and frame=10."
        )


class TestRainbowChaseBorderHueRange:
    """from_hue / to_hue arc restriction on RainbowChaseBorder."""

    def test_all_hues_within_arc(self):
        """With from/to set, every painted hue must fall within the arc."""
        import colorsys

        c = _StubCanvas(20, 8)
        # Red (0°) → green (120°) — 120° forward arc
        RainbowChaseBorder(from_hue=0.0, to_hue=120.0).paint(c, frame_count=0)
        for (x, y), (r, g, b) in c.pixels.items():
            h, _s, _v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            hue_deg = h * 360
            assert 0 <= hue_deg <= 120, (
                f"hue {hue_deg:.1f}° outside 0–120° arc at ({x},{y})"
            )

    def test_arc_advances_with_frame(self):
        """frame_count advances the phase within the arc, producing
        different colors across frames."""
        c0 = _StubCanvas(20, 8)
        c1 = _StubCanvas(20, 8)
        RainbowChaseBorder(from_hue=0.0, to_hue=90.0, speed=4).paint(c0, frame_count=0)
        RainbowChaseBorder(from_hue=0.0, to_hue=90.0, speed=4).paint(c1, frame_count=10)
        differing = sum(1 for k in c0.pixels if c0.pixels[k] != c1.pixels[k])
        assert differing > 0, "arc-restricted chase did not advance with frame_count"

    def test_shorter_arc_chosen_for_obtuse_span(self):
        """Red→blue spans 240° forward or 120° backward. The shorter
        (backward) arc must be selected, keeping hues in 240–360°."""
        import colorsys

        c = _StubCanvas(20, 8)
        # Red 0°, Blue 240°. Shorter arc is −120° (through magenta/purple).
        RainbowChaseBorder(from_hue=0.0, to_hue=240.0, char_offset=1).paint(
            c, frame_count=0
        )
        for (x, y), (r, g, b) in c.pixels.items():
            h, _s, _v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            hue_deg = h * 360
            in_arc = hue_deg >= 240 or hue_deg == 0
            assert in_arc, f"hue {hue_deg:.1f}° not in 240–360° arc at ({x},{y})"

    def test_speed_zero_is_frame_invariant(self):
        """speed=0 with an arc produces identical output every frame."""
        assert (
            RainbowChaseBorder(from_hue=0.0, to_hue=120.0, speed=0).frame_invariant
            is True
        )

    def test_full_wheel_when_no_from_to(self):
        """Without from/to, _arc sentinel is 360.0 (full wheel)."""
        b = RainbowChaseBorder()
        assert b._arc == 360.0
        assert b._from_hue == 0.0


class TestConstantBorder:
    def test_frame_invariant_is_true(self):
        assert ConstantBorder(color=(255, 0, 0)).frame_invariant is True

    def test_paints_uniform_color(self):
        c = _StubCanvas(10, 4)
        ConstantBorder(color=(255, 100, 50)).paint(c, frame_count=0)
        assert all(rgb == (255, 100, 50) for rgb in c.pixels.values())
        assert len(c.pixels) == 24  # 2*(10+4)-4

    def test_accepts_graphics_color_object(self):
        from rgbmatrix.graphics import Color

        c = _StubCanvas(10, 4)
        ConstantBorder(color=Color(50, 100, 200)).paint(c, frame_count=0)
        assert all(rgb == (50, 100, 200) for rgb in c.pixels.values())

    def test_thickness_2_paints_both_rings(self):
        c = _StubCanvas(10, 4)
        ConstantBorder(color=(255, 0, 0), thickness=2).paint(c, frame_count=0)
        # Outer ring (24) + inner ring (16 for 8×2 inner frame) = 40
        assert len(c.pixels) == 40

    def test_paint_ignores_frame_count(self):
        """Output must NOT depend on frame_count (frame_invariant=True).
        Two paints at different frames produce identical pixel sets."""
        c0 = _StubCanvas(10, 4)
        c1 = _StubCanvas(10, 4)
        ConstantBorder(color=(255, 0, 0)).paint(c0, frame_count=0)
        ConstantBorder(color=(255, 0, 0)).paint(c1, frame_count=999)
        assert c0.pixels == c1.pixels


class TestColorCycleBorder:
    """Whole-border single animated hue — complement to rainbow chase."""

    def test_frame_invariant_is_false(self):
        assert ColorCycleBorder().frame_invariant is False

    def test_paints_every_perimeter_pixel(self):
        c = _StubCanvas(10, 4)
        ColorCycleBorder().paint(c, frame_count=0)
        assert len(c.pixels) == 24  # 2*(10+4)-4

    def test_all_pixels_same_color_per_frame(self):
        """Every perimeter pixel gets the same color within one paint call."""
        c = _StubCanvas(10, 4)
        ColorCycleBorder(speed=5).paint(c, frame_count=7)
        colors = set(c.pixels.values())
        assert len(colors) == 1, f"Expected 1 unique color, got {len(colors)}: {colors}"

    def test_color_advances_with_frame(self):
        """Different frames must produce different hues."""
        c0 = _StubCanvas(10, 4)
        c10 = _StubCanvas(10, 4)
        ColorCycleBorder(speed=5).paint(c0, frame_count=0)
        ColorCycleBorder(speed=5).paint(c10, frame_count=10)
        assert next(iter(c0.pixels.values())) != next(iter(c10.pixels.values()))

    def test_no_range_full_wheel(self):
        """Without from/to, hues from different frames should span a wide range."""
        import colorsys

        hues = set()
        b = ColorCycleBorder(speed=5)
        for frame in range(72):  # 72 frames × 5°/frame = full 360°
            c = _StubCanvas(10, 4)
            b.paint(c, frame_count=frame)
            r, g, bl = next(iter(c.pixels.values()))
            h, _, _ = colorsys.rgb_to_hsv(r / 255, g / 255, bl / 255)
            hues.add(round(h * 360))
        # Full wheel: should see hues spread across all 360°
        assert max(hues) - min(hues) > 300

    def test_range_shorter_arc_red_to_blue(self):
        """Red→Blue (shorter arc = magenta band): hues must stay in [240°, 360°]."""
        import colorsys

        b = ColorCycleBorder(speed=1, from_hue=0.0, to_hue=240.0)
        for frame in range(1, 150):
            c = _StubCanvas(10, 4)
            b.paint(c, frame_count=frame)
            r, g, bl = next(iter(c.pixels.values()))
            h, _, _ = colorsys.rgb_to_hsv(r / 255, g / 255, bl / 255)
            hue_deg = h * 360
            assert hue_deg >= 240.0 or hue_deg == 0.0, (
                f"frame {frame}: hue {hue_deg:.1f}° — expected magenta band (240–360°)"
            )

    def test_thickness_2_paints_both_rings(self):
        c = _StubCanvas(10, 4)
        ColorCycleBorder(thickness=2).paint(c, frame_count=0)
        assert len(c.pixels) == 40  # outer (24) + inner (16)


class TestBorderPaintsBeforeText:
    """Tripwire: when a TickerMessage has both `border` and text
    rendering, border paints FIRST so text overlaps the border on
    collision (border frames the panel; text floats inside)."""

    def test_border_paint_called_before_draw_text(self):
        """Order verified by patching both and recording call order."""
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.message import TickerMessage

        order: list[str] = []
        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order.append("border")

        widget = TickerMessage(text="HELLO", border=border)
        canvas = RealStub(width=64, height=16)

        # `draw_text` lives in text_render — patching it here lets us
        # observe its call relative to border.paint.
        with mock.patch(
            "led_ticker.widgets.message.draw_text",
            side_effect=lambda *a, **kw: order.append("draw_text") or 30,
        ):
            widget.draw(canvas)

        assert order, "neither border nor draw_text was called"
        assert order[0] == "border", (
            f"Expected border first; got order={order}. "
            f"If text paints first, the border draws ON TOP of it — "
            f"reverses the intended 'frame contains text' visual."
        )

    def test_border_receives_widget_frame_count(self):
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.message import TickerMessage

        border = mock.Mock()
        border.frame_invariant = False

        widget = TickerMessage(text="HELLO", border=border)
        for _ in range(42):
            widget.advance_frame()
        canvas = RealStub(width=64, height=16)
        widget.draw(canvas)

        border.paint.assert_called_once_with(canvas, 42)

    def test_no_border_no_paint(self):
        """Widget without `border` doesn't reach for one."""
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage(text="HELLO")  # border=None default
        canvas = RealStub(width=64, height=16)
        # Should run without error and produce no border-related calls.
        widget.draw(canvas)


class TestCountdownBorder:
    """TickerCountdown supports `border` with the same contract as
    TickerMessage — paint before text, reads `_frame_count` for
    animation, frame-aware effects compose with transition pause/
    resume."""

    def test_border_paint_called_with_widget_frame_count(self):
        from datetime import date

        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.message import TickerCountdown

        border = mock.Mock()
        border.frame_invariant = False

        widget = TickerCountdown("Days", countdown_date=date(2027, 1, 1), border=border)
        for _ in range(17):
            widget.advance_frame()
        canvas = RealStub(width=64, height=16)
        widget.draw(canvas)

        border.paint.assert_called_once_with(canvas, 17)

    def test_border_paints_before_text_on_countdown(self):
        """Same paint-order contract as TickerMessage — border first
        so text overlaps on collision."""
        from datetime import date

        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.message import TickerCountdown

        order: list[str] = []
        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order.append("border")

        widget = TickerCountdown("Days", countdown_date=date(2027, 1, 1), border=border)
        canvas = RealStub(width=64, height=16)

        with mock.patch(
            "led_ticker.widgets.message.draw_text",
            side_effect=lambda *a, **kw: order.append("draw_text") or 30,
        ):
            widget.draw(canvas)

        assert order, "neither border nor draw_text was called"
        assert order[0] == "border", (
            f"Expected border first; got order={order}. Same contract as "
            f"TickerMessage — border frames the panel, text floats inside."
        )

    def test_no_border_no_paint(self):
        from datetime import date

        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.message import TickerCountdown

        widget = TickerCountdown("Days", countdown_date=date(2027, 1, 1))
        canvas = RealStub(width=64, height=16)
        widget.draw(canvas)  # Should run without error.


class TestTwoRowBorder:
    """TwoRowMessage supports `border` with the same contract as
    TickerMessage / TickerCountdown: paint before text at physical
    resolution, reads `_frame_count` for animation, frame-aware
    effects compose with transition pause/resume.

    Particular to two-row: at scale=2 (typical for handle layouts)
    the border paints to the unwrapped real canvas — traces the
    actual panel edge, not the logical canvas edge."""

    def test_border_paint_called_with_widget_frame_count(self):
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.two_row import TwoRowMessage

        border = mock.Mock()
        border.frame_invariant = False

        widget = TwoRowMessage(
            top_text="@brand",
            bottom_text="tagline",
            border=border,
        )
        for _ in range(42):
            widget.advance_frame()
        canvas = RealStub(width=128, height=16)
        widget.draw(canvas)

        border.paint.assert_called_once_with(canvas, 42)

    def test_border_paints_before_text_on_tworow(self):
        """Same paint-order contract as TickerMessage — border first
        so text overlaps on collision. Verified by intercepting
        `draw_with_emoji` (the path TwoRowMessage uses for both
        rows) and asserting border fires before either row's draw."""
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.two_row import TwoRowMessage

        order: list[str] = []
        border = mock.Mock()
        border.frame_invariant = False
        border.paint.side_effect = lambda *a, **kw: order.append("border")

        widget = TwoRowMessage(
            top_text="@brand",
            bottom_text="tagline",
            border=border,
        )
        canvas = RealStub(width=128, height=16)

        with mock.patch(
            "led_ticker.widgets.two_row.draw_with_emoji",
            side_effect=lambda *a, **kw: order.append("draw_with_emoji") or 30,
        ):
            widget.draw(canvas)

        assert order, "neither border nor draw_with_emoji was called"
        assert order[0] == "border", (
            f"Expected border first; got order={order}. Border must paint "
            f"before either row's text so text overlaps the border on "
            f"collision (border frames the panel, text floats inside)."
        )
        # And both rows still drew
        assert order.count("draw_with_emoji") == 2

    def test_no_border_no_paint(self):
        """TwoRowMessage without `border` defaults to None and
        runs cleanly — no border-related calls."""
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.two_row import TwoRowMessage

        widget = TwoRowMessage(top_text="A", bottom_text="B")
        canvas = RealStub(width=128, height=16)
        widget.draw(canvas)  # Should run without error.


class TestRainbowChaseBorderRestartOnVisit:
    """Pin `RainbowChaseBorder.restart_on_visit = False`. Read by
    `FrameAwareBase.reset_frame` in widgets/_frame_aware.py. Catches a
    future change that flips the default."""

    def test_rainbow_chase_border_restart_on_visit_is_false(self):
        from led_ticker.borders import RainbowChaseBorder

        assert RainbowChaseBorder.restart_on_visit is False, (
            "RainbowChaseBorder.restart_on_visit must be False — "
            "the perimeter chase should advance continuously across "
            "loop_count boundaries within a section"
        )


class TestBorderEffectBase:
    def test_subclass_without_frame_invariant_raises(self):
        from led_ticker.borders import BorderEffectBase

        with pytest.raises(TypeError, match="frame_invariant"):

            class BadBorder(BorderEffectBase):
                def paint(self, canvas, frame_count):
                    pass  # pragma: no cover

    def test_subclass_with_class_attribute_ok(self):
        from led_ticker.borders import BorderEffectBase

        class GoodBorder(BorderEffectBase):
            frame_invariant = True

            def paint(self, canvas, frame_count):
                pass  # pragma: no cover

    def test_subclass_with_property_ok(self):
        from led_ticker.borders import BorderEffectBase

        class DynamicBorder(BorderEffectBase):
            @property
            def frame_invariant(self) -> bool:
                return False

            def __init__(self, speed: int) -> None:
                self._speed = speed

            def paint(self, canvas, frame_count):
                pass  # pragma: no cover

    def test_existing_borders_satisfy_base(self):
        from led_ticker.borders import (
            BorderEffectBase,
            ColorCycleBorder,
            ConstantBorder,
            RainbowChaseBorder,
        )

        for cls in (RainbowChaseBorder, ColorCycleBorder, ConstantBorder):
            assert issubclass(cls, BorderEffectBase), f"{cls.__name__} not a subclass"


class TestColorLUTBorders:
    """RainbowChaseBorder and ColorCycleBorder use the shared LUT instead
    of per-call colorsys.hsv_to_rgb."""

    def test_rainbow_chase_same_position_same_frame_returns_same_pixel(self):
        """Same perimeter position at same frame must produce the same RGB.
        Verifies the LUT is consistent across calls."""
        c1 = _StubCanvas(20, 8)
        c2 = _StubCanvas(20, 8)
        b = RainbowChaseBorder(speed=4, char_offset=6)
        b.paint(c1, frame_count=5)
        b.paint(c2, frame_count=5)
        assert c1.pixels == c2.pixels, "Same frame must produce identical pixels"

    def test_color_cycle_border_frame_zero_hue_zero_is_red(self):
        """ColorCycleBorder at frame=0 with speed=1: hue=(0*1)%360=0 → red (255,0,0)."""
        c = _StubCanvas(10, 4)
        ColorCycleBorder(speed=1).paint(c, frame_count=0)
        assert all(rgb == (255, 0, 0) for rgb in c.pixels.values()), (
            f"Expected all red at frame=0, got: {set(c.pixels.values())}"
        )


class TestLightbulbPositions:
    def test_bigsign_3x3_gap3_count(self):
        """Exact bulb count for bigsign-default geometry.

        Formula: top edge has bulbs at x0 ∈ {N+gap, 2*(N+gap), ...} where
        x0 ≤ w - 2N - gap. For w=256, h=64, N=3, gap=3, stride=6:
        - Top between-corner: x0 ∈ {6, 12, ..., 246} → 41 bulbs
        - Right between-corner: y0 ∈ {6, 12, ..., 54} → 9 bulbs
        - Bottom mirrors top: 41 bulbs
        - Left mirrors right: 9 bulbs
        - 4 corners
        - Total: 4 + 41 + 9 + 41 + 9 = 104
        """
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert len(positions) == 104

    def test_includes_four_corners(self):
        """Corner bulbs appear in the clockwise list exactly once each."""
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert (0, 0) in positions
        assert (256 - 3, 0) in positions
        assert (256 - 3, 64 - 3) in positions
        assert (0, 64 - 3) in positions

    def test_clockwise_order(self):
        """First bulb is top-left, sequence walks clockwise."""
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert positions[0] == (0, 0)
        # Last bulb should be on the left edge going up — y decreasing, x = 0.
        assert positions[-1][0] == 0
        # The second bulb should be on the top edge (y=0)
        assert positions[1][1] == 0
        # Walk continues clockwise: top edge x increases
        top_edge = [(x, y) for x, y in positions if y == 0]
        xs = [x for x, _ in top_edge]
        assert xs == sorted(xs)

    def test_no_duplicates(self):
        """Each bulb position appears exactly once."""
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert len(positions) == len(set(positions))

    def test_smallsign_1x1_gap1(self):
        """1x1 bulbs on smallsign-class panel, exact count."""
        # Top: x0 ∈ {N+gap=2, ..., ≤ w-2N-gap = 157}. Largest even ≤ 157 = 156.
        # Count = (156-2)/2+1 = 78.
        # Right: y0 ∈ {2, ..., ≤ h-2N-gap = 13}. Largest even ≤ 13 = 12.
        # Count = (12-2)/2+1 = 6.
        # Total: 4 + 78 + 6 + 78 + 6 = 172.
        positions = _lightbulb_positions(160, 16, bulb_size=1, gap=1)
        assert len(positions) == 172

    def test_cached(self):
        """Repeated calls with identical args return the SAME list object."""
        a = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        b = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        assert a is b  # functools.cache returns the same object


class _FakeRealCanvas:
    """Minimal stub: just records SetPixel calls."""

    def __init__(self, w, h):
        self.width = w
        self.height = h
        self.pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(x, y)] = (r, g, b)


class TestLightbulbBorderConstruction:
    def test_class_attrs(self):
        """frame_invariant=False (animates), restart_on_visit=False (continuous)."""
        b = LightbulbBorder(mode="chase")
        assert b.frame_invariant is False
        # restart_on_visit is a CLASS attribute
        assert LightbulbBorder.restart_on_visit is False

    def test_defaults(self):
        """Default mode='chase', gap=3, sensible defaults for everything else."""
        b = LightbulbBorder(mode="chase")
        assert b.mode == "chase"
        assert b.gap == 3
        assert b.lit_color == (255, 220, 140)
        assert b.unlit_color == (40, 20, 0)
        assert b.direction == "cw"
        assert b.chase_density == 3

    def test_mode_dependent_speed_default_chase(self):
        """Default speed_frames=2 for chase."""
        b = LightbulbBorder(mode="chase")
        assert b.speed_frames == 2

    def test_explicit_speed_frames_overrides_default(self):
        b = LightbulbBorder(mode="chase", speed_frames=10)
        assert b.speed_frames == 10


class TestLightbulbBorderChase:
    def test_paints_lit_and_unlit_colors(self):
        """At frame=0 with chase_density=3, every 3rd bulb is lit;
        the rest get unlit_color."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=3,
            lit_color=(255, 0, 0),
            unlit_color=(10, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas, frame_count=0)
        # Every pixel of the canvas perimeter region got SOME color
        # (either lit_color or unlit_color). Sample: pixel (0,0) is
        # part of the top-left corner bulb (idx=0); idx % 3 == 0 so lit.
        assert canvas.pixels[(0, 0)] == (255, 0, 0)
        # Idx 1 (next clockwise) is on the top edge — unlit (1 % 3 != 0).
        # Find its position: second bulb in the list at gap+N from top-left = 6.
        assert canvas.pixels[(6, 0)] == (10, 0, 0)

    def test_chase_advances_clockwise(self):
        """Frame=speed_frames vs frame=0: lit set rotated by 1 bulb cw."""
        canvas_0 = _FakeRealCanvas(256, 64)
        canvas_1 = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=3,
            speed_frames=2,
            lit_color=(255, 0, 0),
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas_0, frame_count=0)
        b.paint(canvas_1, frame_count=2)
        # Bulb idx 0 (top-left corner at (0,0)) is lit at frame=0,
        # unlit at frame=speed_frames (step advanced by 1, so
        # (0 - 1) % 3 != 0).
        assert canvas_0.pixels[(0, 0)] == (255, 0, 0)
        assert canvas_1.pixels[(0, 0)] == (0, 0, 0)
        # Bulb idx 1 (top edge x=6) was unlit at frame=0, becomes lit at
        # frame=speed_frames: (1 - 1) % 3 == 0.
        assert canvas_0.pixels[(6, 0)] == (0, 0, 0)
        assert canvas_1.pixels[(6, 0)] == (255, 0, 0)

    def test_chase_ccw_reverses(self):
        """direction='ccw' rotates the opposite way."""
        canvas_cw = _FakeRealCanvas(256, 64)
        canvas_ccw = _FakeRealCanvas(256, 64)
        b_cw = LightbulbBorder(
            mode="chase",
            direction="cw",
            chase_density=3,
            speed_frames=2,
            lit_color=(255, 0, 0),
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b_ccw = LightbulbBorder(
            mode="chase",
            direction="ccw",
            chase_density=3,
            speed_frames=2,
            lit_color=(255, 0, 0),
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b_cw.paint(canvas_cw, frame_count=2)
        b_ccw.paint(canvas_ccw, frame_count=2)
        # Bulb 2 (idx=2). cw: (2-1)%3=1, unlit. ccw: (2+1)%3=0, lit.
        bulb_2_pos = (12, 0)  # third bulb on top edge, x=2*stride=12
        assert canvas_cw.pixels[bulb_2_pos] == (0, 0, 0)
        assert canvas_ccw.pixels[bulb_2_pos] == (255, 0, 0)

    def test_bulb_size_paints_NxN_block(self):
        """A 3x3 bulb covers all 9 pixels of its NxN square."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=1,  # all lit
            lit_color=(123, 45, 67),
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas, frame_count=0)
        # Top-left corner bulb at (0,0) lit; should fill (0..2, 0..2).
        for dy in range(3):
            for dx in range(3):
                assert canvas.pixels[(dx, dy)] == (
                    123,
                    45,
                    67,
                ), f"bulb pixel ({dx},{dy}) not painted lit"


class TestLightbulbBorderAlternate:
    def test_complementary_toggle(self):
        """frame=0 and frame=speed_frames produce complementary lit-sets
        (every bulb is in exactly one of the two)."""
        canvas_0 = _FakeRealCanvas(256, 64)
        canvas_1 = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="alternate",
            speed_frames=5,
            lit_color=(255, 0, 0),
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas_0, frame_count=0)
        b.paint(canvas_1, frame_count=5)
        # Bulb idx 0 lit at frame=0 (0+0)%2=0; unlit at frame=5 (0+1)%2=1.
        assert canvas_0.pixels[(0, 0)] == (255, 0, 0)
        assert canvas_1.pixels[(0, 0)] == (0, 0, 0)
        # Bulb idx 1 unlit at frame=0 (1+0)%2=1; lit at frame=5 (1+1)%2=0.
        assert canvas_0.pixels[(6, 0)] == (0, 0, 0)
        assert canvas_1.pixels[(6, 0)] == (255, 0, 0)


class TestLightbulbBorderUnison:
    def test_all_lit_then_all_unlit(self):
        """frame=0 paints lit; frame=speed_frames paints unlit; all bulbs
        share state."""
        canvas_lit = _FakeRealCanvas(256, 64)
        canvas_dark = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="unison",
            speed_frames=8,
            lit_color=(255, 0, 0),
            unlit_color=(20, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas_lit, frame_count=0)
        b.paint(canvas_dark, frame_count=8)
        # Sample multiple bulb positions: all should be lit at frame=0.
        for pos in [(0, 0), (6, 0), (256 - 3, 0), (0, 64 - 3)]:
            assert canvas_lit.pixels[pos] == (
                255,
                0,
                0,
            ), f"bulb at {pos} not lit at frame=0"
            assert canvas_dark.pixels[pos] == (
                20,
                0,
                0,
            ), f"bulb at {pos} not unlit at frame=8"


class TestLightbulbAutoBulbSize:
    def test_bigsign_auto_3x3(self):
        """No bulb_size override on a 64-tall panel → 3x3 bulbs."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(mode="chase", lit_color=(1, 1, 1), unlit_color=(0, 0, 0))
        b.paint(canvas, frame_count=0)
        # Top-left corner bulb is 3x3 → pixel (2, 2) painted with the
        # corner bulb's color (idx=0, chase_density=3 → lit).
        assert (2, 2) in canvas.pixels

    def test_smallsign_auto_1x1(self):
        """No bulb_size override on a 16-tall panel → 1x1 bulbs."""
        canvas = _FakeRealCanvas(160, 16)
        b = LightbulbBorder(mode="chase", lit_color=(1, 1, 1), unlit_color=(0, 0, 0))
        b.paint(canvas, frame_count=0)
        # 1x1 means each bulb is a single pixel. Top-left corner is (0,0)
        # painted; pixel (1, 1) should NOT have been touched.
        assert (0, 0) in canvas.pixels
        assert (1, 1) not in canvas.pixels


class TestLightbulbPhysicalResolution:
    def test_paints_through_unwrap_to_real(self):
        """When given a ScaledCanvas, paint() targets the real canvas
        underneath (1-pixel sprites, not block-expanded)."""
        real = _FakeRealCanvas(256, 64)
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        b = LightbulbBorder(
            mode="unison",
            speed_frames=1,
            lit_color=(255, 0, 0),
            unlit_color=(0, 0, 0),
            bulb_size=1,
            gap=1,
        )
        b.paint(wrapped, frame_count=0)
        # Real canvas pixels should be set at physical positions, NOT
        # at logical positions * scale.
        assert (0, 0) in real.pixels
        # If paint had used wrapped.SetPixel, it would have block-
        # expanded the 1x1 bulb to a 4x4 region, painting (0..3, 0..3).
        # In physical-resolution mode only (0, 0) gets painted from
        # that one bulb.
        # (1, 1) should NOT be painted — it's inside the rectangle,
        # not on the perimeter.
        assert (1, 1) not in real.pixels


class TestLightbulbBorderRainbow:
    def test_rainbow_flag_set_via_sentinel(self):
        b = LightbulbBorder(mode="chase", lit_color="rainbow")
        assert b._rainbow_lit is True
        assert b.hue_wraps == 1.0

    def test_non_rainbow_keeps_tuple(self):
        b = LightbulbBorder(mode="chase", lit_color=(1, 2, 3))
        assert b._rainbow_lit is False
        assert b.lit_color == (1, 2, 3)

    def test_lit_bulbs_get_per_index_hues(self):
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=1,
            lit_color="rainbow",
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas, frame_count=0)
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        n = len(positions)
        quarter = n // 4
        x0, y0 = positions[0]
        c0 = hue_color((0 / n) * 360 * 1.0)
        assert canvas.pixels[(x0, y0)] == (c0.red, c0.green, c0.blue)
        qx, qy = positions[quarter]
        cq = hue_color((quarter / n) * 360 * 1.0)
        assert canvas.pixels[(qx, qy)] == (cq.red, cq.green, cq.blue)
        assert canvas.pixels[(qx, qy)] != canvas.pixels[(0, 0)]

    def test_hue_wraps_tiles_multiple_spectra(self):
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=1,
            lit_color="rainbow",
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
            hue_wraps=2.0,
        )
        b.paint(canvas, frame_count=0)
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        n = len(positions)
        # n=104 (even), so half=52; (52/104)*360*2 = 360 ≡ 0 (mod 360)
        # meaning bulb 52 should match hue_color(0), same as bulb 0.
        # This proves hue_wraps=2 tiles a second spectrum: halfway around
        # the ring the hues repeat from the start.
        half = n // 2
        hx, hy = positions[half]
        expect = hue_color((half / n) * 360 * 2.0)
        assert canvas.pixels[(hx, hy)] == (expect.red, expect.green, expect.blue)
        c0 = hue_color(0)
        assert canvas.pixels[(hx, hy)] == (c0.red, c0.green, c0.blue)

    def test_unlit_bulbs_keep_unlit_color_in_rainbow(self):
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=3,
            lit_color="rainbow",
            unlit_color=(7, 8, 9),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas, frame_count=0)
        assert canvas.pixels[(6, 0)] == (7, 8, 9)

    def test_rainbow_composes_with_alternate(self):
        """Alternate mode + rainbow: lit bulbs (even idx at flip=0) get
        per-index hues; unlit bulbs (odd idx) keep unlit_color."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="alternate",
            lit_color="rainbow",
            unlit_color=(3, 3, 3),
            bulb_size=3,
            gap=3,
            speed_frames=5,
        )
        b.paint(canvas, frame_count=0)  # phase 0, flip 0 → even idx lit
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        n = len(positions)
        # idx 0 is lit (even): rainbow hue.
        x0, y0 = positions[0]
        c0 = hue_color((0 / n) * 360 * 1.0)
        assert canvas.pixels[(x0, y0)] == (c0.red, c0.green, c0.blue)
        # idx 1 is unlit (odd): unlit_color.
        x1, y1 = positions[1]
        assert canvas.pixels[(x1, y1)] == (3, 3, 3)

    def test_rainbow_composes_with_unison(self):
        lit_canvas = _FakeRealCanvas(256, 64)
        off_canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="unison",
            lit_color="rainbow",
            unlit_color=(2, 2, 2),
            bulb_size=3,
            gap=3,
            speed_frames=1,
        )
        b.paint(lit_canvas, frame_count=0)
        b.paint(off_canvas, frame_count=1)
        c0 = hue_color(0)
        assert lit_canvas.pixels[(0, 0)] == (c0.red, c0.green, c0.blue)
        assert off_canvas.pixels[(0, 0)] == (2, 2, 2)

    def test_rainbow_hues_are_static_across_frames(self):
        """The defining property: rainbow hues are keyed to perimeter
        index, NOT frame_count. With chase_density=1 every bulb is lit
        at every frame, so the painted output must be identical across
        frames — a regression that added frame_count to the hue formula
        would change this and is otherwise invisible to single-frame
        tests."""
        c0 = _FakeRealCanvas(256, 64)
        c50 = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=1,  # all bulbs lit at every frame
            lit_color="rainbow",
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b.paint(c0, frame_count=0)
        b.paint(c50, frame_count=50)
        assert c0.pixels == c50.pixels


class TestLightbulbRainbowCoercion:
    def test_rainbow_sentinel_builds_border(self):
        b = _coerce_border(
            {"style": "lightbulbs", "mode": "chase", "lit_color": "rainbow"}
        )
        assert isinstance(b, LightbulbBorder)
        assert b._rainbow_lit is True

    def test_hue_wraps_accepted(self):
        b = _coerce_border(
            {"style": "lightbulbs", "lit_color": "rainbow", "hue_wraps": 3}
        )
        assert b.hue_wraps == 3

    def test_junk_lit_color_string_rejected(self):
        with pytest.raises(ValueError, match="lit_color"):
            _coerce_border({"style": "lightbulbs", "lit_color": "banana"})

    def test_rgb_lit_color_still_validated(self):
        b = _coerce_border({"style": "lightbulbs", "lit_color": [10, 20, 30]})
        assert b.lit_color == (10, 20, 30)


class TestBandPalettes:
    """BAND_PALETTES registry sanity — every named palette must be a
    usable bands spec: >= 2 colors, each a valid (r, g, b) tuple."""

    def test_expected_palettes_present(self):
        assert set(BAND_PALETTES) == {
            "rainbow",
            "rasta",
            "usa",
            "christmas",
            "halloween",
            "candy_cane",
        }

    def test_all_palettes_valid(self):
        for name, colors in BAND_PALETTES.items():
            assert len(colors) >= 2, f"palette {name!r} needs >= 2 colors"
            for c in colors:
                assert len(c) == 3, f"palette {name!r} entry {c!r} not RGB"
                for v in c:
                    assert isinstance(v, int) and not isinstance(v, bool)
                    assert 0 <= v <= 255, f"palette {name!r} value {v} out of range"


class TestColorBandsBorder:
    """Discrete solid-color bands marching around the perimeter.
    Band at perimeter index `idx`, frame `f`:
    ((idx - f * speed) // band_width) % len(colors)."""

    RED = (255, 0, 0)
    WHITE = (255, 255, 255)

    def _border(self, **kw):
        kw.setdefault("colors", [self.RED, self.WHITE])
        return ColorBandsBorder(**kw)

    def test_satisfies_protocol(self):
        b = self._border()
        assert hasattr(b, "frame_invariant")
        assert isinstance(b.frame_invariant, bool)
        assert callable(b.paint)

    def test_defaults(self):
        b = self._border()
        assert b.band_width == 6
        assert b.speed == 1
        assert b.thickness == 1

    def test_frame_invariant_false_for_default_speed(self):
        assert self._border().frame_invariant is False

    def test_frame_invariant_true_for_speed_zero(self):
        assert self._border(speed=0).frame_invariant is True

    def test_restart_on_visit_is_false(self):
        """Continuous march across loop_count boundaries, like the
        other animated borders."""
        assert ColorBandsBorder.restart_on_visit is False

    def test_band_pattern_at_frame_zero(self):
        """First band_width perimeter pixels are color 0, next
        band_width are color 1, wrapping modulo len(colors)."""
        b = self._border(band_width=4, speed=1)
        c = _StubCanvas(20, 8)
        b.paint(c, frame_count=0)
        px = _perimeter_pixels(20, 8, 1)
        for i in range(4):
            assert c.pixels[px[i]] == self.RED, f"idx {i}"
        for i in range(4, 8):
            assert c.pixels[px[i]] == self.WHITE, f"idx {i}"
        # Wraps modulo: idx 8 starts the next RED band.
        assert c.pixels[px[8]] == self.RED

    def test_paints_every_perimeter_pixel(self):
        c = _StubCanvas(20, 8)
        self._border().paint(c, frame_count=0)
        assert len(c.pixels) == 2 * (20 + 8) - 4  # 52

    def test_positive_speed_marches_clockwise(self):
        """At frame f the pattern is the frame-0 pattern shifted
        forward (clockwise) by f * speed perimeter pixels:
        color(idx + shift, f) == color(idx, 0)."""
        b = self._border(band_width=4, speed=1)
        c0, c2 = _StubCanvas(20, 8), _StubCanvas(20, 8)
        b.paint(c0, frame_count=0)
        b.paint(c2, frame_count=2)
        px = _perimeter_pixels(20, 8, 1)
        for i in range(len(px) - 2):
            assert c2.pixels[px[i + 2]] == c0.pixels[px[i]], f"idx {i}"

    def test_negative_speed_reverses(self):
        """speed=-1 marches counter-clockwise:
        color(idx, f=1) == color(idx + 1, 0)."""
        b = self._border(band_width=4, speed=-1)
        c0, c1 = _StubCanvas(20, 8), _StubCanvas(20, 8)
        b.paint(c0, frame_count=0)
        b.paint(c1, frame_count=1)
        px = _perimeter_pixels(20, 8, 1)
        for i in range(len(px) - 1):
            assert c1.pixels[px[i]] == c0.pixels[px[i + 1]], f"idx {i}"

    def test_speed_zero_is_static(self):
        b = self._border(speed=0)
        c0, c7 = _StubCanvas(20, 8), _StubCanvas(20, 8)
        b.paint(c0, frame_count=0)
        b.paint(c7, frame_count=7)
        assert c0.pixels == c7.pixels

    def test_three_color_palette_cycles_in_order(self):
        b = ColorBandsBorder(
            colors=[(255, 0, 0), (255, 191, 0), (0, 255, 0)], band_width=2
        )
        c = _StubCanvas(20, 8)
        b.paint(c, frame_count=0)
        px = _perimeter_pixels(20, 8, 1)
        assert c.pixels[px[0]] == (255, 0, 0)
        assert c.pixels[px[2]] == (255, 191, 0)
        assert c.pixels[px[4]] == (0, 255, 0)
        assert c.pixels[px[6]] == (255, 0, 0)  # wraps

    def test_accepts_color_objects(self):
        """Constructor materializes .red/.green/.blue objects to plain
        tuples (same trick as ConstantBorder)."""
        import types

        b = ColorBandsBorder(
            colors=[
                types.SimpleNamespace(red=10, green=20, blue=30),
                (40, 50, 60),
            ]
        )
        c = _StubCanvas(20, 8)
        b.paint(c, frame_count=0)
        px = _perimeter_pixels(20, 8, 1)
        assert c.pixels[px[0]] == (10, 20, 30)

    def test_unwraps_scaled_canvas_to_paint_real_pixels(self):
        """Paints at PHYSICAL resolution — 1 px border = 1 real LED on
        bigsign, not a scale x scale block (mirrors the RainbowChase
        test of the same name)."""
        real = _StubCanvas(64, 32)
        wrapper = ScaledCanvas(real, scale=4, content_height=8)
        self._border().paint(wrapper, frame_count=0)
        assert len(real.pixels) == 2 * (64 + 32) - 4  # 188

    def test_thickness_2_paints_both_rings(self):
        c = _StubCanvas(10, 4)
        self._border(thickness=2).paint(c, frame_count=0)
        # Outer ring 24 + inner ring 16 (matches TestPerimeterGeometry).
        assert len(c.pixels) == 40

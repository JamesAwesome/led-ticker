"""Tests for led_ticker.borders — perimeter geometry + animation."""

from __future__ import annotations

import unittest.mock as mock

import pytest

from led_ticker.borders import (
    ColorCycleBorder,
    ConstantBorder,
    RainbowChaseBorder,
    _perimeter_pixels,
)


class TestPerimeterGeometry:
    """`_perimeter_pixels` must walk every panel-perimeter pixel
    exactly once in clockwise order. Used as the index map for the
    rainbow-chase hue formula — index drift = visible artifacts."""

    def test_count_thickness_1(self):
        # 2×(W+H) − 4 corners that would otherwise be double-counted
        for w, h in [(10, 4), (256, 64), (160, 16), (5, 5)]:
            px = _perimeter_pixels(w, h, thickness=1)
            assert (
                len(px) == 2 * (w + h) - 4
            ), f"{w}×{h}: expected {2 * (w + h) - 4}, got {len(px)}"

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
        assert (
            len(px) == 24 + 16
        ), f"thickness=2 on 10×4 should give 40 pixels; got {len(px)}"
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
            assert (
                0 <= hue_deg <= 120
            ), f"hue {hue_deg:.1f}° outside 0–120° arc at ({x},{y})"

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
            assert (
                hue_deg >= 240.0 or hue_deg == 0.0
            ), f"frame {frame}: hue {hue_deg:.1f}° — expected magenta band (240–360°)"

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

        widget = TickerMessage("HELLO", border=border)
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

        widget = TickerMessage("HELLO", border=border)
        widget._frame_count = 42
        canvas = RealStub(width=64, height=16)
        widget.draw(canvas)

        border.paint.assert_called_once_with(canvas, 42)

    def test_no_border_no_paint(self):
        """Widget without `border` doesn't reach for one."""
        from rgbmatrix import _StubCanvas as RealStub

        from led_ticker.widgets.message import TickerMessage

        widget = TickerMessage("HELLO")  # border=None default
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
        widget._frame_count = 17
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
        widget._frame_count = 42
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
    `_FrameAware.reset_frame` in widgets/_frame_aware.py. Catches a
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

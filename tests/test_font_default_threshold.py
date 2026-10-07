"""Per-font default rasterization threshold.

`resolve_font(name, size)` with no `threshold` used to mean 128 for every
hi-res font. That single value cannot serve both bundled Inter weights at
small sizes: at 80, Bold ink grows wider than the glyph's own advance and
adjacent letters fuse into blobs (the stocks watchlist, the weather hero
location); at 128, Regular's thin antialiased strokes drop out and glyphs
shatter (15–37% of lit pixels lost at 11px). So the default now follows
the font: Inter-Regular → 80, everything else → 128.

The ink assertions below pin the measurements this design rests on. They
are invariant-based, not pixel pins — nothing here encodes a glyph bitmap,
so the rasterizer stays free to change while the premise stays checked.
"""

import attrs
import pytest

from led_ticker.fonts import resolve_font
from led_ticker.fonts.hires_loader import THRESHOLD, default_threshold
from led_ticker.plugin import draw_text

_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


@attrs.define
class _Color:
    red: int
    green: int
    blue: int


class _InkCanvas:
    """Collects lit pixels; `draw_text` only needs SetPixel + size."""

    def __init__(self, width: int = 512, height: int = 64) -> None:
        self.width = width
        self.height = height
        self.lit: set[tuple[int, int]] = set()

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        if r or g or b:
            self.lit.add((x, y))


def _paint(
    text: str, name: str, size: int, threshold: int | None
) -> set[tuple[int, int]]:
    font = resolve_font(name, size, threshold)
    canvas = _InkCanvas()
    draw_text(canvas, font, text, 2, 2 + font.ascent, _Color(200, 200, 200))
    return canvas.lit


def _components(lit: set[tuple[int, int]]) -> int:
    """8-connected ink blobs — one per glyph when nothing has fused."""
    remaining = set(lit)
    components = 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            x, y = stack.pop()
            for dx, dy in _NEIGHBOURS:
                neighbour = (x + dx, y + dy)
                if neighbour in remaining:
                    remaining.discard(neighbour)
                    stack.append(neighbour)
    return components


class TestDefaultThreshold:
    def test_inter_regular_defaults_low(self):
        assert default_threshold("Inter-Regular") == 80

    def test_inter_bold_keeps_the_loader_default(self):
        assert default_threshold("Inter-Bold") == THRESHOLD == 128

    def test_unknown_font_keeps_the_loader_default(self):
        """Third-party and plugin fonts are unmeasured — their rendering
        must not change. Only names in the table get a per-font value."""
        assert default_threshold("Beloved-Sans-Regular") == THRESHOLD
        assert default_threshold("acme.Brand") == THRESHOLD

    def test_exported_through_the_plugin_api(self):
        import led_ticker.plugin as p

        assert p.default_threshold is default_threshold
        assert "default_threshold" in p.__all__


class TestResolveFontUsesPerFontDefault:
    def test_regular_without_threshold_resolves_at_80(self):
        assert resolve_font("Inter-Regular", 24) is resolve_font(
            "Inter-Regular", 24, threshold=80
        )

    def test_bold_without_threshold_resolves_at_128(self):
        assert resolve_font("Inter-Bold", 24) is resolve_font(
            "Inter-Bold", 24, threshold=128
        )

    def test_explicit_threshold_still_wins(self):
        """A caller that passes a value gets exactly that value — the
        per-font default is only a fallback for `None`."""
        explicit = resolve_font("Inter-Regular", 24, threshold=128)
        assert explicit.threshold == 128
        assert explicit is not resolve_font("Inter-Regular", 24)


class TestDefaultPairingMeasurements:
    """The numbers behind the table, so nobody re-derives them wrong."""

    @pytest.mark.parametrize("size", (9, 11, 14, 18, 24, 32))
    def test_weight_contrast_survives_the_default_pairing(self, size):
        """Core's docs warn that a lower Regular threshold can out-weigh
        Bold ("weight contrast may invert"). For Inter it does not: at
        every size the default pairing keeps Regular lighter than Bold.
        If this fails, the table is inverting weights on real panels."""
        regular = len(_paint("BOSTON", "Inter-Regular", size, None))
        bold = len(_paint("BOSTON", "Inter-Bold", size, None))
        assert regular < bold, (
            f"size {size}: Inter-Regular at its default threshold lit {regular} px, "
            f"Inter-Bold lit {bold} — Regular now out-weighs Bold"
        )

    @pytest.mark.parametrize("size", (11, 14, 18, 24))
    def test_bold_default_keeps_adjacent_glyphs_separate(self, size):
        """At the Bold default, BOSTON renders as six ink blobs. (At 80 it
        renders as five or fewer — see the test below — which is the
        fusion the plugins shipped with.)"""
        assert _components(_paint("BOSTON", "Inter-Bold", size, None)) == 6

    def test_the_thin_font_value_fuses_bold_text(self):
        """Pins why Bold must NOT share Regular's 80: the thin-stroke
        value grows bold ink past its advance so neighbours touch. If this
        stops failing at 80, the rasterizer changed — re-measure the table
        rather than trusting this module's premise."""
        assert _components(_paint("BOSTON", "Inter-Bold", 14, 80)) < 6

    def test_regular_default_keeps_more_ink_than_128_at_small_sizes(self):
        """Pins why Regular needs 80: at 128 it loses a large share of its
        thin strokes at the sizes the plugins paint labels at."""
        at_default = len(_paint("7:05 PM", "Inter-Regular", 11, None))
        at_128 = len(_paint("7:05 PM", "Inter-Regular", 11, 128))
        assert at_default > at_128 * 1.10, (
            f"expected ≥10% more ink at the Regular default than at 128; "
            f"got {at_default} vs {at_128}"
        )

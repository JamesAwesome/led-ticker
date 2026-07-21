"""Spleen pixel fonts — the binary-grid property the feature rests on.

A Spleen OTF rendered at its native pixel size (or an integer multiple)
produces strictly binary output through PIL: every pixel 0 or 255, exact
integer advances. If a Pillow upgrade ever breaks grid alignment, these
fail loudly. Exact-advance pins are safe HERE (integer grid by
construction) — they remain banned for outline fonts (Inter/DejaVu).
"""

from PIL import Image, ImageDraw, ImageFont

from led_ticker.fonts import resolve_font
from led_ticker.fonts.hires_loader import BUNDLED_HIRES_DIR, load_hires_font

_SPLEEN = {  # name -> (native_px, advance_px at native)
    "spleen-6x12": (12, 6),
    "spleen-8x16": (16, 8),
    "spleen-16x32": (32, 16),
}
_SAMPLE = "EV 104.6e MA%?"


def _gray_values(name: str, size: int) -> set[int]:
    """Raw PIL rendering (pre-threshold) of the sample text."""
    pil = ImageFont.truetype(str(BUNDLED_HIRES_DIR / f"{name}.otf"), size)
    asc, desc = pil.getmetrics()
    img = Image.new("L", (len(_SAMPLE) * size, asc + desc), 0)
    ImageDraw.Draw(img).text((0, 0), _SAMPLE, font=pil, fill=255)
    px = img.load()
    return {px[x, y] for x in range(img.width) for y in range(img.height)}


class TestSpleenResolves:
    def test_all_four_names_resolve_at_native(self):
        for name, (native, _adv) in _SPLEEN.items():
            font = resolve_font(name, native)
            g = font.resolve_glyph("M")
            assert g is not None and g.lit, name


class TestBinaryGrid:
    def test_native_size_renders_strictly_binary(self):
        for name, (native, _adv) in _SPLEEN.items():
            vals = _gray_values(name, native)
            assert vals <= {0, 255}, (
                f"{name}@{native}: intermediate grays {sorted(v for v in vals if 0 < v < 255)[:5]}"  # noqa: E501
            )

    def test_double_size_renders_strictly_binary(self):
        vals = _gray_values("spleen-6x12", 24)
        assert vals <= {0, 255}

    def test_off_grid_renders_antialiased(self):
        # The rule-69 premise: off-grid = intermediate grays = mush.
        vals = _gray_values("spleen-6x12", 11)
        assert any(0 < v < 255 for v in vals)

    def test_threshold_is_a_noop_at_native(self):
        # Through OUR loader: thresholds 1 and 254 must yield identical lit
        # sets (cache keys differ, so these are fresh rasterizations).
        lo = load_hires_font("spleen-6x12", 12, 1)
        hi = load_hires_font("spleen-6x12", 12, 254)
        assert lo is not None and hi is not None
        for ch in "EVLADIST04.62%":
            gl, gh = lo.resolve_glyph(ch), hi.resolve_glyph(ch)
            assert gl is not None and gh is not None, ch
            assert gl.lit == gh.lit, ch

    def test_exact_integer_advance_at_native(self):
        for name, (native, adv) in _SPLEEN.items():
            font = resolve_font(name, native)
            g = font.resolve_glyph("M")
            assert g is not None and g.advance == adv, name

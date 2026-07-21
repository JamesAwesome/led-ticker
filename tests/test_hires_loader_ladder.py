"""The glyph resolution ladder — notdef detection + lazy rasterization."""

import dataclasses

from led_ticker.fonts import hires_loader
from led_ticker.fonts.hires_loader import load_hires_font

_INTER = "Inter-Bold"  # bundled


class TestNotdefDetection:
    def test_char_font_lacks_resolves_to_missing_not_box(self, monkeypatch):
        # NOTE: the brief's premise was that ▲ U+25B2 (in GEOMETRIC_SHAPES,
        # eagerly rasterized) is a glyph Inter-Bold lacks. On THIS machine's
        # Pillow/FreeType build that no longer holds — Inter-Bold ships a
        # real ▲ glyph here (verified: non-empty lit that doesn't match the
        # notdef fingerprint). Probing further, this Pillow build's
        # missing-glyph rendering is itself not one fixed box per font —
        # it varies per requested char/script (macOS font-fallback
        # substitution) — so no single real "Inter lacks this eager char"
        # example is portable across environments.
        #
        # To exercise the exact property the original assertion wanted —
        # an eager-charset char the font lacks must be PRUNED at load and
        # detected as MISSING, never stored as a tofu box — we force the
        # condition deterministically: monkeypatch `_rasterize_glyph` so a
        # chosen char (漢, U+6F22 — Inter has no CJK glyphs, kept as a
        # semantically-honest choice) rasterizes to EXACTLY this font's
        # real notdef fingerprint, and add it to the eager charset. This
        # keeps `_rasterize`'s real notdef-probe call and every other
        # glyph's rasterization untouched — only the one synthetic "font
        # lacks this" case is pinned, so the test is not tied to
        # platform-specific glyph coverage or fallback rendering.
        original_rasterize_glyph = hires_loader._rasterize_glyph
        captured_notdef_lit: dict[str, tuple[tuple[int, int], ...]] = {}

        def fake_rasterize_glyph(pil_font, ch, ascent, descent, threshold):
            glyph = original_rasterize_glyph(pil_font, ch, ascent, descent, threshold)
            if ch == hires_loader._NOTDEF_PROBE:
                captured_notdef_lit["lit"] = glyph.lit
            elif ch == "漢" and "lit" in captured_notdef_lit:
                return dataclasses.replace(glyph, lit=captured_notdef_lit["lit"])
            return glyph

        monkeypatch.setattr(hires_loader, "_rasterize_glyph", fake_rasterize_glyph)
        monkeypatch.setattr(
            hires_loader, "GEOMETRIC_SHAPES", hires_loader.GEOMETRIC_SHAPES + "漢"
        )
        # Fresh (name, size) so functools.lru_cache doesn't hand back a
        # font rasterized before the patches were applied.
        font = load_hires_font(_INTER, 31)
        assert font is not None
        # No eager notdef glyph survives in the dict...
        assert "漢" not in font.glyphs
        # ...and resolve_glyph returns None (Task 1) — DejaVu (Task 2)
        # fills it.
        assert font.resolve_glyph("漢") is None

    def test_present_char_still_resolves(self):
        font = load_hires_font(_INTER, 30)
        g = font.resolve_glyph("A")
        assert g is not None and g.lit  # real glyph, lit pixels

    def test_notdef_fingerprint_captured(self):
        font = load_hires_font(_INTER, 30)
        # A private-use codepoint has no assignment → notdef. Its lit set
        # is the captured fingerprint (non-empty for a boxed notdef).
        assert isinstance(font.notdef_lit, tuple)


class TestLazyRasterization:
    def test_char_outside_charset_lazily_rasterizes(self):
        # '∑' N-ARY SUMMATION (U+2211) is NOT in the eager charset. Inter
        # lacks it too → resolves None here (DejaVu has it, Task 2). But a
        # char Inter HAS that's outside the charset must lazily render.
        font = load_hires_font(_INTER, 30)
        # 'ǽ' (U+01FD) — Latin, outside EXTENDED_LATIN, Inter has it.
        g = font.resolve_glyph("ǽ")
        assert g is not None and g.lit

    def test_lazy_result_is_cached(self):
        font = load_hires_font(_INTER, 30)
        a = font.resolve_glyph("ǽ")
        b = font.resolve_glyph("ǽ")
        assert a is b  # same object → cached, not re-rasterized

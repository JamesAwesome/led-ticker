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


class TestDejaVuRung:
    def test_arrow_font_lacks_resolves_via_dejavu(self):
        # ▲ U+25B2: the brief's premise is that Inter lacks it, so rung 1
        # returns None and rung 2 (DejaVu) fills it. On THIS machine's
        # Pillow/FreeType build that premise doesn't hold deterministically
        # — per TestNotdefDetection's note above, macOS font-substitution
        # can make Inter appear to "have" ▲ via a substituted system glyph,
        # which would mask rung 1's miss and make this test pass without
        # ever touching rung 2.
        #
        # To exercise the REAL production path — resolve_glyph falling
        # through to `_dejavu_glyph` — deterministically on any platform,
        # seed the font's glyph cache directly with the `_MISSING`
        # sentinel for "▲": exactly what rung 1 caches on a genuine miss,
        # per `resolve_glyph`'s own contract. From there the rest of
        # `resolve_glyph` runs unmodified. Fresh size (33) so mutating the
        # shared `glyphs` dict (cached forever by `load_hires_font`'s
        # `lru_cache`) can't leak into any other test using `_INTER`.
        font = load_hires_font(_INTER, 33)
        assert font is not None
        font.glyphs["▲"] = hires_loader._MISSING
        g = font.resolve_glyph("▲")
        assert g is not None and g.lit  # real arrow from DejaVu, not a box

    def test_dejavu_glyph_is_not_notdef(self):
        from led_ticker.fonts.hires_loader import _dejavu_glyph

        g = _dejavu_glyph("▲", 30, 24, 6, 128)
        assert g is not None and g.lit

    def test_dejavu_also_lacking_returns_none(self):
        # A rare CJK ideograph (鿿, U+9FBF) neither Inter nor DejaVu cover →
        # still None (→ ? later, a future rung). Verified directly against
        # `_dejavu_glyph` that DejaVu genuinely lacks it (not a platform
        # substitution artifact). Force rung 1's miss deterministically too
        # — per the notes above, this Mac's Pillow/FreeType build can
        # substitute a real system glyph for CJK requests even on a font
        # like Inter that ships none, which would mask rung 1 ever
        # reaching rung 2 here. Fresh size (35) to isolate the seeded
        # `glyphs` mutation from other tests.
        font = load_hires_font(_INTER, 35)
        assert font is not None
        font.glyphs["鿿"] = hires_loader._MISSING
        assert font.resolve_glyph("鿿") is None

    def test_repeat_lookup_after_cached_miss_still_reaches_dejavu(self):
        # A cached _MISSING sentinel (rung 1 already proved it lacks `ch`)
        # must not short-circuit resolve_glyph to None on a repeat lookup —
        # every call has to keep falling through to rung 2. Regression
        # guard for the cache-hit branch rewrite in resolve_glyph. Fresh
        # size (34), same reasoning as above.
        font = load_hires_font(_INTER, 34)
        assert font is not None
        font.glyphs["▲"] = hires_loader._MISSING
        first = font.resolve_glyph("▲")
        second = font.resolve_glyph("▲")
        assert first is not None and first.lit
        assert second is not None and second.lit


class TestAsciiRungAndWarn:
    def test_font_real_glyph_wins_over_ascii_table(self, monkeypatch):
        """REAL GLYPH WINS: U+2212 is in the ASCII table (→ '-'), but Inter
        ships a real minus, so rung 1 keeps it — the table does NOT fire.
        DejaVu stubbed off to isolate rung 1 vs rung 3."""
        import led_ticker.fonts.hires_loader as m

        monkeypatch.setattr(m, "_dejavu_glyph", lambda *a, **k: None)
        font = load_hires_font(_INTER, 36)
        minus = font.resolve_glyph("−")
        hyphen = font.resolve_glyph("-")
        assert minus is not None and hyphen is not None
        assert minus is not hyphen  # real minus kept, not the hyphen sub
        assert minus.advance != hyphen.advance  # Inter's minus is its own glyph

    def test_ascii_table_fires_when_font_and_dejavu_both_miss(self, monkeypatch):
        """Rung 3: when rung 1 (font) AND rung 2 (DejaVu) miss, − rescues to
        the hyphen glyph. Seed glyphs[−]=_MISSING to force a deterministic
        rung-1 miss; stub DejaVu off so only rung 3 can save it."""
        import led_ticker.fonts.hires_loader as m

        monkeypatch.setattr(m, "_dejavu_glyph", lambda *a, **k: None)
        font = load_hires_font(_INTER, 37)
        font.glyphs["−"] = m._MISSING
        sub = font.resolve_glyph("−")
        hyph = font.resolve_glyph("-")
        assert sub is not None and sub is hyph  # rendered as the real hyphen

    def test_unrenderable_returns_none_and_warns_once(self, monkeypatch, caplog):
        """Rung 4: a char nobody has → None, and exactly one WARN per
        (font, char). Seed _MISSING + stub DejaVu so the miss is real on any
        platform."""
        import logging

        import led_ticker.fonts.hires_loader as m

        monkeypatch.setattr(m, "_dejavu_glyph", lambda *a, **k: None)
        m._WARNED_MISSING.clear()
        font = load_hires_font(_INTER, 38)
        font.glyphs["鿿"] = m._MISSING  # U+9FFF, force deterministic miss
        cp = f"{ord('鿿'):04x}"
        with caplog.at_level(logging.WARNING):
            assert font.resolve_glyph("鿿") is None
            font.resolve_glyph("鿿")  # second call — must NOT re-warn
        warns = [
            r
            for r in caplog.records
            if cp in r.getMessage().lower() or "鿿" in r.getMessage()
        ]
        assert len(warns) == 1

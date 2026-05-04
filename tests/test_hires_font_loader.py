"""Tests for the hi-res font loader."""

from __future__ import annotations

import pytest


class TestHiresGlyphDataclass:
    def test_constructs_with_required_fields(self):
        from led_ticker.fonts.hires_loader import HiresGlyph

        glyph = HiresGlyph(
            width=10,
            height=20,
            advance=12,
            bearing_x=0,
            bearing_y=18,
            lit=((0, 0), (1, 1)),
        )
        assert glyph.width == 10
        assert glyph.lit == ((0, 0), (1, 1))

    def test_is_frozen(self):
        from led_ticker.fonts.hires_loader import HiresGlyph

        glyph = HiresGlyph(
            width=10, height=20, advance=12, bearing_x=0, bearing_y=18, lit=()
        )
        try:
            glyph.width = 99
        except Exception as e:  # noqa: BLE001
            assert "FrozenInstanceError" in type(e).__name__
            return
        raise AssertionError("expected FrozenInstanceError on attribute set")


class TestHiresFontDataclass:
    def test_constructs(self):
        from led_ticker.fonts.hires_loader import HiresFont, HiresGlyph

        glyph = HiresGlyph(
            width=10, height=20, advance=12, bearing_x=0, bearing_y=18, lit=()
        )
        font = HiresFont(
            name="test",
            size=32,
            ascent=30,
            descent=8,
            line_height=38,
            glyphs={"A": glyph},
        )
        assert font.name == "test"
        assert font.size == 32
        assert font.glyphs["A"] is glyph

    def test_is_frozen(self):
        from led_ticker.fonts.hires_loader import HiresFont

        font = HiresFont(
            name="t", size=8, ascent=6, descent=2, line_height=8, glyphs={}
        )
        try:
            font.size = 99
        except Exception as e:  # noqa: BLE001
            assert "FrozenInstanceError" in type(e).__name__
            return
        raise AssertionError("expected FrozenInstanceError on attribute set")


class TestThresholdConstant:
    def test_threshold_is_at_50_percent(self):
        from led_ticker.fonts.hires_loader import THRESHOLD

        # 50% of 0-255 ≈ 128
        assert THRESHOLD == 128


@pytest.fixture(autouse=True)
def _clear_loader_cache():
    """Clear @functools.cache between tests."""
    from led_ticker.fonts.hires_loader import load_hires_font

    load_hires_font.cache_clear()
    yield
    load_hires_font.cache_clear()


class TestFindFontPath:
    def test_finds_bundled_inter_regular(self):
        from led_ticker.fonts.hires_loader import _find_font_path

        path = _find_font_path("Inter-Regular")
        assert path is not None
        assert path.name == "Inter-Regular.otf"
        assert path.is_absolute()

    def test_returns_none_for_unknown(self):
        from led_ticker.fonts.hires_loader import _find_font_path

        assert _find_font_path("definitely-not-a-font") is None

    def test_user_dir_overrides_bundled(self, tmp_path, monkeypatch):
        """If a font with the same name exists in config/fonts/ AND the
        bundled hires/ dir, the user-supplied one wins."""
        import led_ticker.fonts.hires_loader as hl

        user_dir = tmp_path / "user-fonts"
        user_dir.mkdir()
        # Drop a fake .otf with the same name as a bundled font.
        fake = user_dir / "Inter-Regular.otf"
        fake.write_bytes(b"not really a font")
        monkeypatch.setattr(hl, "USER_FONT_DIR", user_dir)

        from led_ticker.fonts.hires_loader import _find_font_path

        found = _find_font_path("Inter-Regular")
        assert found == fake


class TestLoadHiresFont:
    def test_loads_bundled_inter_regular(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        assert font.name == "Inter-Regular"
        assert font.size == 32
        assert font.ascent > 0
        assert font.descent > 0
        assert font.line_height == font.ascent + font.descent

    def test_glyphs_for_ascii_printable(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        for ch in "ABCabc0123!?":
            assert ch in font.glyphs, f"missing glyph for {ch!r}"

    def test_glyph_has_lit_pixels(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        # 'M' is dense — should have many lit pixels.
        m = font.glyphs["M"]
        assert len(m.lit) > 0
        # 'M' should have more lit pixels than 'i' at the same size.
        i_glyph = font.glyphs["i"]
        assert len(m.lit) > len(i_glyph.lit)

    def test_glyph_advance_is_positive(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        assert font.glyphs["A"].advance > 0

    def test_returns_none_for_unknown_name(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        assert load_hires_font("not-a-real-font", 32) is None

    def test_caches_result(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        first = load_hires_font("Inter-Regular", 24)
        second = load_hires_font("Inter-Regular", 24)
        assert first is second  # @functools.cache returns same object

    def test_different_sizes_are_different_objects(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        a = load_hires_font("Inter-Regular", 24)
        b = load_hires_font("Inter-Regular", 32)
        assert a is not None and b is not None
        assert a is not b
        assert a.size == 24
        assert b.size == 32

    def test_bearing_y_is_baseline_relative_not_image_relative(self):
        """Hotfix 00145b7: bearing_y is the distance from baseline UP to
        glyph top. Pillow's getbbox returns coords in anchor='la' space
        (left-ascender), NOT baseline. Wrong anchor handling caused glyphs
        to render only their bottom strip on hardware. Pin bearing_y values
        so a future getbbox-coord refactor can't silently re-introduce the
        bug."""
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 24)
        assert font is not None
        # 'M' has cap-height ascender; bearing_y should be ~18 (most of
        # glyph rises above baseline). NOT a small negative number (would
        # mean we used baseline-relative bbox math).
        assert 14 < font.glyphs["M"].bearing_y < 22
        # 'g' has a descender; its body sits lower. Should be ~13.
        assert 10 < font.glyphs["g"].bearing_y < 16
        # Sanity: 'M' rises higher above baseline than 'g'.
        assert font.glyphs["M"].bearing_y > font.glyphs["g"].bearing_y


class TestListAvailableHiresFonts:
    def test_lists_bundled_fonts(self):
        from led_ticker.fonts.hires_loader import list_available_hires_fonts

        names = list_available_hires_fonts()
        assert "Inter-Regular" in names
        assert "Inter-Bold" in names

    def test_returns_sorted(self):
        from led_ticker.fonts.hires_loader import list_available_hires_fonts

        names = list_available_hires_fonts()
        assert names == sorted(names)


class TestResolveFont:
    def test_returns_hires_for_bundled_name(self):
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 32)
        assert isinstance(font, HiresFont)
        assert font.size == 32

    def test_returns_bdf_for_alias_6x12(self):
        from led_ticker.fonts import FONT_DEFAULT, resolve_font

        font = resolve_font("6x12")
        # Identity check: same C font object as FONT_DEFAULT.
        assert font is FONT_DEFAULT

    def test_returns_bdf_for_alias_5x8(self):
        from led_ticker.fonts import FONT_SMALL, resolve_font

        font = resolve_font("5x8")
        assert font is FONT_SMALL

    def test_raises_for_unknown_name(self):
        from led_ticker.fonts import UnknownFontError, resolve_font

        try:
            resolve_font("totally-not-a-real-font")
        except UnknownFontError as e:
            assert "totally-not-a-real-font" in str(e)
            # Error message should list available names.
            assert "Inter-Regular" in str(e)
            assert "6x12" in str(e)
            return
        raise AssertionError("expected UnknownFontError")

    def test_default_size_used_when_size_omitted(self):
        from led_ticker.fonts import DEFAULT_HIRES_SIZE, resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular")
        assert isinstance(font, HiresFont)
        assert font.size == DEFAULT_HIRES_SIZE

    def test_raises_for_size_below_8(self):
        """font_size < 8 produces unreadable glyphs — reject at resolve time."""
        from led_ticker.fonts import resolve_font

        try:
            resolve_font("Inter-Regular", 4)
        except ValueError as e:
            assert "font_size" in str(e)
            assert ">=" in str(e) or "8" in str(e)
            return
        raise AssertionError("expected ValueError for size < 8")


class TestListAvailableFonts:
    def test_includes_hires_and_bdf(self):
        from led_ticker.fonts import list_available_fonts

        names = list_available_fonts()
        assert "Inter-Regular" in names
        assert "Inter-Bold" in names
        assert "6x12" in names
        assert "5x8" in names


class TestFontLineHeight:
    def test_line_height_for_hires_font(self):
        from led_ticker.fonts import font_line_height, resolve_font

        font = resolve_font("Inter-Regular", 32)
        h = font_line_height(font)
        # Inter at 32px should have line_height around 38-40.
        assert 30 < h < 50

    def test_line_height_for_bdf_font(self):
        from led_ticker.fonts import FONT_DEFAULT, font_line_height

        # FONT_DEFAULT is 6x12 — height is 12.
        h = font_line_height(FONT_DEFAULT)
        assert h == 12

    def test_line_height_for_bdf_small_font(self):
        from led_ticker.fonts import FONT_SMALL, font_line_height

        # FONT_SMALL is 5x8 — height is 8.
        h = font_line_height(FONT_SMALL)
        assert h == 8

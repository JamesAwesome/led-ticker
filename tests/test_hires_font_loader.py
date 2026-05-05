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

    def test_space_glyph_has_zero_lit_pixels_and_positive_advance(self):
        """The rasterizer's whitespace branch (`bbox is None or zero-area`)
        emits an empty `HiresGlyph` with advance preserved. If a future
        change drops the advance, words separate visually break ("hello
        world" → "helloworld"); if the lit-pixels guard breaks, render
        cost spikes from rasterizing empty glyph rectangles. Pin both."""
        from led_ticker.fonts.hires_loader import load_hires_font

        font = load_hires_font("Inter-Regular", 32)
        assert font is not None
        space = font.glyphs[" "]
        assert space.lit == (), "space must have no lit pixels"
        assert space.width == 0
        assert space.height == 0
        assert space.advance > 0, (
            "space must advance the cursor — a zero-advance space "
            "would collapse word breaks"
        )

    def test_returns_none_for_unknown_name(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        assert load_hires_font("not-a-real-font", 32) is None

    def test_caches_result(self):
        from led_ticker.fonts.hires_loader import load_hires_font

        first = load_hires_font("Inter-Regular", 24)
        second = load_hires_font("Inter-Regular", 24)
        assert first is second  # @functools.cache returns same object

    def test_cache_is_bounded_at_maxsize(self):
        """`load_hires_font` is `@lru_cache(maxsize=16)` to bound memory
        if a misconfigured TOML spams font/size combos. Verify the cap
        actually evicts beyond maxsize.
        """
        from led_ticker.fonts.hires_loader import (
            _FONT_CACHE_MAXSIZE,
            load_hires_font,
        )

        load_hires_font.cache_clear()
        # Spawn maxsize + 4 distinct entries by varying size. Inter-Regular
        # at sizes 8..maxsize+12 → all distinct cache keys.
        sizes = list(range(8, 8 + _FONT_CACHE_MAXSIZE + 4))
        for s in sizes:
            load_hires_font("Inter-Regular", s)
        info = load_hires_font.cache_info()
        # The LRU cap should hold steady at maxsize regardless of how
        # many distinct keys we pushed through.
        assert info.currsize == _FONT_CACHE_MAXSIZE
        assert info.maxsize == _FONT_CACHE_MAXSIZE

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
            resolve_font("totally-not-a-real-font", size=24)
        except UnknownFontError as e:
            assert "totally-not-a-real-font" in str(e)
            # Error message should list available names.
            assert "Inter-Regular" in str(e)
            assert "6x12" in str(e)
            return
        raise AssertionError("expected UnknownFontError")

    def test_resolve_font_hires_without_size_raises(self):
        """HiresFont requires explicit size at resolve time — the
        rasterizer needs a real-px target and silent fallback to
        DEFAULT_HIRES_SIZE could mismatch the panel."""
        import pytest

        from led_ticker.fonts import resolve_font

        with pytest.raises(ValueError, match="requires a size"):
            resolve_font("Inter-Regular")

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

    def test_threshold_param_changes_lit_pixel_count(self):
        """A lower threshold lets more antialiased pixels survive — used to
        keep thin-stroked fonts (Beloved Sans Regular) from losing strokes."""
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        default_font = resolve_font("Inter-Regular", 24)
        low_thr_font = resolve_font("Inter-Regular", 24, threshold=64)
        assert isinstance(default_font, HiresFont)
        assert isinstance(low_thr_font, HiresFont)
        # Same font/size at lower threshold = same or more lit pixels per glyph.
        # Pick a glyph with lots of antialiased edges so the difference is real.
        default_lit = len(default_font.glyphs["a"].lit)
        low_thr_lit = len(low_thr_font.glyphs["a"].lit)
        assert low_thr_lit > default_lit, (
            f"lowered threshold should add lit pixels: "
            f"default={default_lit} thr=64={low_thr_lit}"
        )

    def test_threshold_omitted_uses_default(self):
        """Default behaviour preserved: no threshold = identical to threshold=128."""
        from led_ticker.fonts import resolve_font

        no_thr = resolve_font("Inter-Regular", 24)
        explicit = resolve_font("Inter-Regular", 24, threshold=128)
        assert no_thr is explicit  # same cache entry

    def test_threshold_out_of_range_raises(self):
        from led_ticker.fonts import resolve_font

        for bad in (-1, 256, 999):
            try:
                resolve_font("Inter-Regular", 24, threshold=bad)
            except ValueError as e:
                assert "font_threshold" in str(e)
                continue
            raise AssertionError(f"expected ValueError for threshold={bad}")

    def test_threshold_non_int_raises(self):
        """Reject str / float / bool early so they can't pollute the
        load_hires_font @functools.cache key. Floats hash distinctly
        from int-equal values (e.g. `80` and `80.0` would double-rasterize
        the same glyphs); strings would TypeError deep inside the loader.
        """
        from led_ticker.fonts import resolve_font

        for bad in ("80", 80.5, 80.0, True, False):
            try:
                resolve_font("Inter-Regular", 24, threshold=bad)  # type: ignore[arg-type]
            except ValueError as e:
                assert "font_threshold" in str(e)
                continue
            raise AssertionError(f"expected ValueError for non-int threshold={bad!r}")

    def test_threshold_ignored_for_bdf_aliases(self):
        """BDF fonts are pre-rasterized bitmaps; threshold has no meaning."""
        from led_ticker.fonts import FONT_DEFAULT, resolve_font

        # Resolve with a non-default threshold; BDF should still come back.
        font = resolve_font("6x12", threshold=80)
        assert font is FONT_DEFAULT

    def test_bold_renders_stroke_complete_at_default_threshold(self):
        """Bold weights have fat enough strokes to survive THRESHOLD=128
        unchanged — they don't need a `font_threshold` override.

        Beloved Sans Regular at 24px loses the left vertical of `n` at
        thr=128 (antialiased pixels come out ~60-100 grey, below cutoff).
        Bold weights don't suffer this because their strokes are thicker
        and saturate above the cutoff.

        Pin Inter-Bold at 24px @ thr=128 as the in-tree proxy for the
        property: every glyph column in the first/last few should have
        lit pixels (no missing strokes), and Bold should render denser
        than Regular at the same threshold.
        """
        from led_ticker.fonts.hires_loader import load_hires_font

        bold = load_hires_font("Inter-Bold", 24)
        regular = load_hires_font("Inter-Regular", 24)
        assert bold is not None
        assert regular is not None

        # The 'n' glyph is the canonical bug-witness from the hardware
        # photo. At thr=128 its left vertical must survive — i.e. the
        # leftmost column of the bbox must have lit pixels.
        bold_n = bold.glyphs["n"]
        bold_cols = sorted({dx for dx, _dy in bold_n.lit})
        assert bold_cols, "bold 'n' must have lit pixels at default threshold"
        # Leftmost lit column should be flush with bbox start (allow 0-2
        # px slack for any side-bearing whitespace inside the bbox).
        assert (
            bold_cols[0] <= 2
        ), f"bold 'n' left stroke missing at thr=128: leftmost_col={bold_cols[0]}"
        # Right stroke must also reach the bbox edge.
        assert bold_cols[-1] >= bold_n.width - 3, (
            f"bold 'n' right stroke incomplete: rightmost_col={bold_cols[-1]} "
            f"vs width={bold_n.width}"
        )

        # Bold should be denser than Regular at the same threshold —
        # if this ever inverts, the rasterizer is rendering the wrong
        # weight or something is bypassing the threshold.
        bold_lit = len(bold_n.lit)
        reg_lit = len(regular.glyphs["n"].lit)
        assert bold_lit > reg_lit, (
            f"bold 'n' should have more lit pixels than regular at thr=128: "
            f"bold={bold_lit} regular={reg_lit}"
        )


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

    def test_line_height_tolerates_method_shaped_height(self):
        """Back-compat shim: `font.height` was a CALLABLE in older
        stub generations and could be again if the rgbmatrix C
        extension's API evolves. `font_line_height` reads `font.height`
        and calls it if callable, else uses the value directly. The
        production stub and real C extension both expose `height` as
        an int attribute (via @property), so the callable path is
        only exercised by this test — proving the back-compat branch
        actually works rather than just being trusted.
        """
        from led_ticker.fonts import font_line_height

        class _MethodShapedFont:
            """Mock font whose `height` is a method, not an attribute."""

            def height(self) -> int:  # type: ignore[override]
                return 9

        result = font_line_height(_MethodShapedFont())
        assert result == 9, (
            f"font_line_height failed to call `height()` on a method-shaped "
            f"font: got {result!r} (expected 9)"
        )

    def test_line_height_tolerates_attribute_shaped_height(self):
        """Mirror of the above: real C extension exposes `height` as
        an int attribute. Pin this path explicitly too."""
        from led_ticker.fonts import font_line_height

        class _AttrShapedFont:
            height: int = 7

        assert font_line_height(_AttrShapedFont()) == 7

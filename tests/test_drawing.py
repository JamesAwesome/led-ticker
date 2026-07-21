"""Tests for led_ticker.drawing helpers."""

from types import SimpleNamespace

from led_ticker.drawing import (
    Region,
    compute_baseline,
    compute_cursor,
    find_center,
    get_text_width,
)
from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL


def test_region_full_canvas_defaults():
    r = Region(0, 0, 160, 16)
    assert r.x == 0
    assert r.y == 0
    assert r.width == 160
    assert r.height == 16


def test_region_subregion():
    r = Region(10, 4, 80, 8)
    assert r.x == 10
    assert r.y == 4
    assert r.width == 80
    assert r.height == 8


def test_get_text_width_with_padding():
    assert get_text_width(FONT_DEFAULT, " ") == 12  # 6px char + 6px padding


def test_get_text_width_no_padding():
    assert get_text_width(FONT_DEFAULT, " ", padding=0) == 6


def test_get_text_width_multi_char():
    assert get_text_width(FONT_DEFAULT, "abc", padding=0) == 18  # 3 * 6px


def test_find_center():
    assert find_center(160, 6) == 77.0


def test_find_center_wide_content():
    assert find_center(160, 160) == 0.0


def test_compute_cursor_centered():
    cursor, end_pad = compute_cursor(
        canvas_width=160, content_width=100, cursor_pos=0, padding=6, center=True
    )
    # center_pos = 160/2 - floor(100/2) = 80 - 50 = 30
    assert cursor == 30
    assert end_pad == 160 - (30 + 100)  # 30


def test_compute_cursor_not_centered():
    cursor, end_pad = compute_cursor(
        canvas_width=160, content_width=100, cursor_pos=0, padding=6, center=False
    )
    assert cursor == 0
    assert end_pad == 6


def test_compute_cursor_overflow_stays_at_cursor():
    """When content is wider than canvas, centering is skipped."""
    cursor, end_pad = compute_cursor(
        canvas_width=160, content_width=200, cursor_pos=5, padding=6, center=True
    )
    assert cursor == 5
    assert end_pad == 6


class TestGetTextWidthHiresFont:
    def test_hires_font_sums_advances(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        width = get_text_width(font, "ABC", padding=0)
        # Sum of glyph advances for A, B, C — should be positive.
        assert width > 0
        # And consistent: same call returns same result.
        assert get_text_width(font, "ABC", padding=0) == width

    def test_hires_font_padding_added(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        no_pad = get_text_width(font, "X", padding=0)
        with_pad = get_text_width(font, "X", padding=6)
        assert with_pad == no_pad + 6

    def test_hires_font_empty_string(self):
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        assert get_text_width(font, "", padding=0) == 0

    def test_hires_font_unknown_char_uses_fallback(self, monkeypatch):
        """A char `resolve_glyph` can't resolve at all falls back to the
        '?' advance in `get_text_width`.

        Pre glyph-resolution-ladder, 'Ω' (outside the eager charset) was a
        reliable stand-in for "unresolvable" — the charset was a hard wall.
        Post-ladder (core), an out-of-charset char the font actually ships
        (as Inter-Regular does for 'Ω' on this Pillow/FreeType build)
        lazily rasterizes to its REAL glyph instead of falling back — that
        charset-wall removal is the intended behavior, not a regression.
        Force the "font genuinely lacks this" case deterministically via
        `resolve_glyph` instead of relying on a specific codepoint's
        presence/absence, which now varies by font/platform.
        """
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        original_resolve_glyph = HiresFont.resolve_glyph

        def fake_resolve_glyph(self, ch):
            if ch == "Ω":
                return None
            return original_resolve_glyph(self, ch)

        monkeypatch.setattr(HiresFont, "resolve_glyph", fake_resolve_glyph)

        omega_width = get_text_width(font, "Ω", padding=0)
        question_width = get_text_width(font, "?", padding=0)
        assert omega_width == question_width

    def test_bdf_font_path_unchanged(self):
        """Existing BDF behavior preserved."""
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import FONT_DEFAULT

        # FONT_DEFAULT is 6×12 — 'A' is 6 wide.
        width = get_text_width(FONT_DEFAULT, "A", padding=0)
        assert width == 6

    def test_returns_logical_pixel_advance_not_real(self):
        """Hotfix ec30a97: get_text_width must return LOGICAL pixels for
        HiresFont (ceil-div by SCALE_FALLBACK=4). Otherwise widget layout
        math against canvas.width (logical) breaks."""
        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        real_total = sum(font.glyphs[c].advance for c in "ABC")
        expected_logical = -(-real_total // 4)
        width = get_text_width(font, "ABC", padding=0)
        assert width == expected_logical
        # Pre-hotfix would have returned real_total (4x larger).
        assert width < real_total

    def test_canvas_arg_supplies_scale(self):
        """When `canvas` is provided, get_text_width reads scale from it
        instead of falling back to SCALE_FALLBACK=4. A scale=1 canvas
        (small sign) should produce REAL-pixel widths since real == logical
        at scale 1; a scale=4 canvas should match the no-canvas (fallback)
        behavior; a scale=2 canvas should land between them.
        """
        from types import SimpleNamespace

        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        real_total = sum(font.glyphs[c].advance for c in "ABC")

        # scale=1 (small sign): logical == real, no division.
        scale1_canvas = SimpleNamespace(scale=1)
        assert get_text_width(font, "ABC", padding=0, canvas=scale1_canvas) == (
            real_total
        )

        # scale=4 (bigsign): matches the SCALE_FALLBACK no-canvas path.
        scale4_canvas = SimpleNamespace(scale=4)
        no_canvas = get_text_width(font, "ABC", padding=0)
        with_canvas = get_text_width(font, "ABC", padding=0, canvas=scale4_canvas)
        assert no_canvas == with_canvas

        # scale=2 (hypothetical): half the real, between scale=1 and scale=4.
        scale2_canvas = SimpleNamespace(scale=2)
        scale2_w = get_text_width(font, "ABC", padding=0, canvas=scale2_canvas)
        assert scale2_w == -(-real_total // 2)
        assert scale2_w < real_total
        assert scale2_w > with_canvas

    def test_canvas_without_scale_attr_treated_as_scale_1(self):
        """A real RGBMatrix canvas has no `scale` attribute — treat as
        scale=1 (it IS the physical panel). This is the small-sign or
        unwrapped-bigsign-real case. Distinct from `canvas=None`, which
        falls back to SCALE_FALLBACK for back-compat with the lone
        TickerMessage.__init__ pre-draw caller.
        """
        from types import SimpleNamespace

        from led_ticker.drawing import get_text_width
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        bare_canvas = SimpleNamespace()  # no `scale` attr → scale=1
        scale1_canvas = SimpleNamespace(scale=1)
        with_bare = get_text_width(font, "ABC", padding=0, canvas=bare_canvas)
        with_scale1 = get_text_width(font, "ABC", padding=0, canvas=scale1_canvas)
        assert with_bare == with_scale1
        # Both should differ from the canvas=None fallback (which uses
        # SCALE_FALLBACK=4) since real-pixel advance / 4 < real-pixel /1.
        no_canvas = get_text_width(font, "ABC", padding=0)
        assert with_bare > no_canvas


class TestComputeBaseline:
    """`compute_baseline` replaces the BDF-hardcoded `y = 12` baseline.
    Returns the logical-pixel y to pass to draw_text — works for both
    BDF and HiresFont, on plain real canvases and ScaledCanvas wrappers.
    """

    def test_bdf_default_on_small_sign_matches_legacy_baseline(self):
        """BDF 6×12 on a 16-row canvas (small sign or scale=1) returns
        y=12 for "center" — same as the old hardcoded value, so existing
        configs render unchanged."""
        canvas = SimpleNamespace(height=16, scale=1)
        assert compute_baseline(FONT_DEFAULT, canvas, valign="center") == 12

    def test_bdf_default_on_bigsign_scaled_canvas(self):
        """BDF 6×12 on a 16-row LOGICAL ScaledCanvas with scale=4 (real
        height 64) still returns y=12. The function multiplies BDF
        metrics by scale internally so the answer matches the small-sign
        case — that's what keeps current bigsign BDF text where it was."""
        canvas = SimpleNamespace(height=16, scale=4)
        assert compute_baseline(FONT_DEFAULT, canvas, valign="center") == 12

    def test_bdf_top_valign(self):
        canvas = SimpleNamespace(height=16, scale=1)
        # BDF 6×12 ascent = 10. Top alignment puts baseline at ascent.
        assert compute_baseline(FONT_DEFAULT, canvas, valign="top") == 10

    def test_bdf_bottom_valign(self):
        canvas = SimpleNamespace(height=16, scale=1)
        # BDF 6×12 descent = 12-10 = 2. Bottom alignment: baseline = h - descent.
        assert compute_baseline(FONT_DEFAULT, canvas, valign="bottom") == 14

    def test_bdf_5x8_metrics(self):
        """5×8 has FONT_ASCENT=7 + descent=1; verify the helper picks
        up the parsed BDF ascent (not a hardcoded 10) by switching font."""
        canvas = SimpleNamespace(height=8, scale=1)
        assert compute_baseline(FONT_SMALL, canvas, valign="top") == 7
        assert compute_baseline(FONT_SMALL, canvas, valign="bottom") == 7

    def test_hires_center_on_bigsign_real_canvas(self):
        """Inter-Regular @ 24px on a 64-row real canvas (the actual
        bigsign-with-text-canvas-scale-1 case): centered baseline puts
        the glyph in the visual middle. With Inter @ 24px (line_h ~28,
        ascent ~22), centered top is at row (64-28)/2 = 18, baseline at
        18+22 = 40. Pin to ±2 of 40 since the FT metrics vary slightly.
        """
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        canvas = SimpleNamespace(height=64, scale=1)
        baseline = compute_baseline(font, canvas, valign="center")
        assert 38 <= baseline <= 42, baseline

    def test_hires_top_doesnt_clip_ascender(self):
        """Top valign for a hires font must position baseline = ascent
        so the tallest cap-height glyph just reaches y=0 (not above)."""
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        canvas = SimpleNamespace(height=64, scale=1)
        baseline = compute_baseline(font, canvas, valign="top")
        # Baseline should equal ascent (rounded up so we don't clip).
        assert baseline >= font.ascent
        # And not absurdly large (would push glyph below visible top).
        assert baseline <= font.ascent + 1

    def test_hires_bottom_doesnt_clip_descender(self):
        """Bottom valign must keep descenders inside the panel."""
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        h = 64
        canvas = SimpleNamespace(height=h, scale=1)
        baseline = compute_baseline(font, canvas, valign="bottom")
        # Glyph bottom = baseline + descent must be ≤ h.
        glyph_bottom = baseline + font.descent
        assert glyph_bottom <= h

    def test_hires_on_scaled_canvas_returns_logical(self):
        """On a ScaledCanvas wrapper at scale=4, compute_baseline must
        return a LOGICAL y so draw_text's `real_y = y * scale` lands at
        the right physical pixel. Scale-1 and scale-4 should produce
        equivalent visual baselines (different logical units, same
        real position).
        """
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)
        # Scale=1 logical canvas = 64 rows. Scale=4 logical canvas = 16
        # rows wrapping a 64 real-row panel.
        c1 = SimpleNamespace(height=64, scale=1)
        c4 = SimpleNamespace(height=16, scale=4)
        b1 = compute_baseline(font, c1, valign="center")
        b4 = compute_baseline(font, c4, valign="center")
        # Real positions: b1 * 1 vs b4 * 4. Should be within scale-1
        # of each other (rounding loss).
        assert abs(b1 - b4 * 4) <= 4

    def test_mock_canvas_scale_attr_treated_as_scale_1(self):
        """A Mock canvas auto-generates `.scale` (not an int). The
        helper must treat that as scale=1 instead of crashing —
        otherwise widget tests using the standard Mock fixture would
        all fail when they call draw()."""
        import unittest.mock as _mock

        canvas = _mock.Mock()
        canvas.height = 16  # set explicitly so .height is an int
        # canvas.scale is auto-Mock
        baseline = compute_baseline(FONT_DEFAULT, canvas, valign="center")
        assert baseline == 12  # falls back to scale=1 like a small sign


class TestHiresMessageBaselineCentersOnBigsign:
    """End-to-end: TickerMessage with a hires font on a bigsign canvas
    paints the glyph at the centered position, not the BDF-shifted-down
    position the old hardcoded `y=12` formula produced.
    """

    def test_hires_text_visually_centered(self):
        """Confirm pixels land within the centered band, not 4-8 px below."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.message import TickerMessage

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        font = resolve_font("Inter-Regular", 24)
        widget = TickerMessage(
            text="MM",  # dense glyphs, ensures lit pixels in the band
            font=font,
            font_color=Color(255, 255, 255),
            center=False,
        )
        widget.draw(wrapped, cursor_pos=10)

        # Find rows that have any lit pixels.
        lit_rows = sorted(
            {
                y
                for y in range(real.height)
                for x in range(real.width)
                if real.get_pixel(x, y) != (0, 0, 0)
            }
        )
        assert lit_rows, "expected lit pixels somewhere"
        # Pre-fix: glyph top was at row ~26, bottom ~54 (shifted down).
        # Post-fix: glyph top ~18, bottom ~46 (centered ±2 px). The
        # band's center should be near the panel center (32).
        band_center = (lit_rows[0] + lit_rows[-1]) / 2
        assert abs(band_center - 32) <= 4, (
            f"glyph band centered at {band_center} on a 64-row panel — "
            f"expected within 4 px of 32"
        )


class TestGetTextWidthMemoization:
    """`get_text_width` memoizes results in a module-level cache so
    per-frame callers (weather, two-row tickers) hit a dict get
    instead of re-summing glyph advances every draw. Cache key
    includes `(id(font), text, padding, scale)` so different scales
    produce distinct entries — a width measured at scale=1 doesn't
    pollute a scale=4 measurement.
    """

    def test_repeated_call_hits_cache(self):
        from led_ticker.drawing import _TEXT_WIDTH_CACHE

        _TEXT_WIDTH_CACHE.clear()
        canvas = SimpleNamespace(scale=1, width=160)
        get_text_width(FONT_DEFAULT, "abc", padding=0, canvas=canvas)
        size_after_first = len(_TEXT_WIDTH_CACHE)
        get_text_width(FONT_DEFAULT, "abc", padding=0, canvas=canvas)
        get_text_width(FONT_DEFAULT, "abc", padding=0, canvas=canvas)
        # No new entries added on subsequent calls — cache hit each time.
        assert len(_TEXT_WIDTH_CACHE) == size_after_first

    def test_different_canvas_scale_separate_cache_entries(self):
        """Width depends on scale (hires fonts ceil-divide by canvas
        scale). Two canvases with different scales must NOT share a
        cached entry — would return the wrong width.
        """
        from led_ticker.drawing import _TEXT_WIDTH_CACHE
        from led_ticker.fonts import resolve_font

        _TEXT_WIDTH_CACHE.clear()
        font = resolve_font("Inter-Regular", 24)
        c1 = SimpleNamespace(scale=1)
        c4 = SimpleNamespace(scale=4)
        w1 = get_text_width(font, "ABC", padding=0, canvas=c1)
        w4 = get_text_width(font, "ABC", padding=0, canvas=c4)
        assert w1 != w4  # different scales → different widths
        assert len(_TEXT_WIDTH_CACHE) == 2  # two entries cached

    def test_cache_evicts_at_maxsize(self):
        """Cache evicts at maxsize so memory stays bounded even if a
        config spawns many unique strings. After eviction the cache
        must contain exactly maxsize entries — pop-one-oldest, not
        wholesale-clear."""
        from led_ticker.drawing import (
            _TEXT_WIDTH_CACHE,
            _TEXT_WIDTH_CACHE_MAXSIZE,
        )

        _TEXT_WIDTH_CACHE.clear()
        canvas = SimpleNamespace(scale=1, width=160)
        for i in range(_TEXT_WIDTH_CACHE_MAXSIZE + 5):
            get_text_width(FONT_DEFAULT, f"text_{i}", padding=0, canvas=canvas)
        # Pop-oldest keeps exactly maxsize entries; wholesale-clear would leave ~6.
        assert len(_TEXT_WIDTH_CACHE) == _TEXT_WIDTH_CACHE_MAXSIZE

    def test_cache_retains_most_recent_entry_after_overflow(self):
        """The entry that triggered eviction must survive. Wholesale-clear
        would also evict the triggering entry (cache drops from maxsize
        to 1 right after clear), leaving the very next call a miss too.
        """
        from led_ticker.drawing import (
            _TEXT_WIDTH_CACHE,
            _TEXT_WIDTH_CACHE_MAXSIZE,
        )

        _TEXT_WIDTH_CACHE.clear()
        canvas = SimpleNamespace(scale=1, width=160)

        # Fill to exactly maxsize.
        for i in range(_TEXT_WIDTH_CACHE_MAXSIZE):
            get_text_width(FONT_DEFAULT, f"old_{i}", padding=0, canvas=canvas)

        assert len(_TEXT_WIDTH_CACHE) == _TEXT_WIDTH_CACHE_MAXSIZE

        # This call triggers eviction (len >= maxsize), then inserts the new key.
        result = get_text_width(FONT_DEFAULT, "the_new_entry", padding=0, canvas=canvas)

        # Cache must stay at maxsize (evict-1 + insert-1).
        assert len(_TEXT_WIDTH_CACHE) == _TEXT_WIDTH_CACHE_MAXSIZE

        # The new entry survives — calling again hits the cache, no new entries.
        result2 = get_text_width(
            FONT_DEFAULT, "the_new_entry", padding=0, canvas=canvas
        )
        assert result == result2
        assert len(_TEXT_WIDTH_CACHE) == _TEXT_WIDTH_CACHE_MAXSIZE


class TestHiresTextWidthAndFit:
    def test_width_positive_and_grows_with_size(self):
        from led_ticker.drawing import hires_text_width

        w22 = hires_text_width("EUR/USD", 22)
        w11 = hires_text_width("EUR/USD", 11)
        assert w22 > w11 > 0

    def test_minus_sign_measures_as_hyphen(self):
        """U+2212 draws as the hyphen glyph (resolve_glyph fallback) — the
        measurement must agree with the draw, or right-aligned negatives
        drift (the stocks '?'-overlap class)."""
        from led_ticker.drawing import hires_text_width

        assert hires_text_width("−1.98%", 22) == hires_text_width("-1.98%", 22)

    def test_threshold_param_accepted(self):
        from led_ticker.drawing import hires_text_width

        # Same advances regardless of threshold (threshold affects lit
        # pixels, not advances) — the param exists for font-cache sharing.
        assert hires_text_width("AAPL", 22, threshold=80) == hires_text_width(
            "AAPL", 22
        )

    def test_threshold_is_forwarded_to_resolve_font(self, monkeypatch):
        """The param must actually REACH resolve_font (font-cache sharing
        with a caller's paint) — width equality alone can't catch a silently
        dropped parameter."""
        import led_ticker.drawing as drawing_mod
        from led_ticker.fonts import resolve_font as real_resolve_font

        seen = []

        def spy(name, size=None, threshold=None):
            seen.append((name, size, threshold))
            return real_resolve_font(name, size, threshold)

        monkeypatch.setattr(drawing_mod, "resolve_font", spy)
        drawing_mod.hires_text_width("AAPL", 22, threshold=80)
        assert seen == [("Inter-Bold", 22, 80)]

    def test_fit_keeps_design_size_when_it_fits(self):
        from led_ticker.drawing import fit_text_size

        assert fit_text_size("AAPL", (22, 18, 11), 10_000) == 22

    def test_fit_steps_down_and_result_fits(self):
        from led_ticker.drawing import fit_text_size, hires_text_width

        budget = hires_text_width("64,906.62", 22) - 1  # 22 must NOT fit
        size = fit_text_size("64,906.62", (22, 18, 16, 14, 12, 11), budget)
        assert size < 22
        assert hires_text_width("64,906.62", size) <= budget or size == 11

    def test_fit_floor_when_nothing_fits(self):
        from led_ticker.drawing import fit_text_size

        assert fit_text_size("WWWWWWWWWW", (22, 11), 1) == 11

    def test_fit_empty_sizes_raises(self):
        import pytest

        from led_ticker.drawing import fit_text_size

        with pytest.raises(ValueError):
            fit_text_size("X", (), 100)

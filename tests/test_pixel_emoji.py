"""Smoke tests for pixel_emoji rendering on ScaledCanvas.

Ensures the bigsign path renders inline emoji + text correctly: emoji
SetPixel calls and text draw_text calls both work through the wrapper.
"""

from __future__ import annotations

import pytest
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.fonts import FONT_SMALL
from led_ticker.pixel_emoji import draw_with_emoji, measure_width
from led_ticker.scaled_canvas import ScaledCanvas


def _bigsign_real_canvas():
    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


class TestCountTextChars:
    """Counts text chars excluding emoji slugs — used by callers
    that need to pass an explicit `total_chars` to `draw_with_emoji`
    (e.g. image widgets with typewriter mid-cycle)."""

    def test_pure_text(self):
        from led_ticker.pixel_emoji import count_text_chars

        assert count_text_chars("Hello") == 5

    def test_empty(self):
        from led_ticker.pixel_emoji import count_text_chars

        assert count_text_chars("") == 0

    def test_pure_emoji(self):
        from led_ticker.pixel_emoji import count_text_chars

        assert count_text_chars(":star:") == 0

    def test_text_with_emoji(self):
        """Emoji slug excluded from count; surrounding text counted."""
        from led_ticker.pixel_emoji import count_text_chars

        # "Hi " (3) + ":star:" (0) + " there" (6) = 9
        assert count_text_chars("Hi :star: there") == 9

    def test_multiple_emojis(self):
        from led_ticker.pixel_emoji import count_text_chars

        # "x" (1) + ":star:" (0) + "y" (1) + ":sun:" (0) + "z" (1) = 3
        assert count_text_chars("x:star:y:sun:z") == 3


def test_draw_with_emoji_runs_on_scaled_canvas_text_only():
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    color = (255, 0, 0)
    advance = draw_with_emoji(sc, FONT_SMALL, cursor_pos=0, y=8, color=color, text="HI")
    # 5x8 advance is 5 per char + 0 padding from emoji segments
    assert advance == 10


def test_draw_with_emoji_runs_on_scaled_canvas_with_emoji():
    """Emoji segment SetPixels and text segment goes through draw_text."""
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    color = (255, 255, 255)
    # Should not raise. Baseball emoji is 8 wide; "Hi" follows.
    advance = draw_with_emoji(
        sc, FONT_SMALL, cursor_pos=0, y=8, color=color, text=":baseball: Hi"
    )
    # emoji advance (8 + 2 padding) + text advance varies, just sanity check
    assert advance > 0


def test_draw_with_emoji_at_scale_1_unchanged():
    """The existing sign's path (scale=1, real canvas) still works."""
    opts = RGBMatrixOptions()
    opts.cols = 32
    opts.chain_length = 5
    opts.rows = 16
    real = RGBMatrix(options=opts).CreateFrameCanvas()
    advance = draw_with_emoji(
        real, FONT_SMALL, cursor_pos=0, y=8, color=(0, 255, 0), text="A"
    )
    assert advance > 0


def test_measure_width_with_emoji():
    """Smoke: measure_width handles mixed emoji + text."""
    width = measure_width(FONT_SMALL, ":baseball: Hi")
    assert width > 0


def test_measure_width_uses_hires_logical_width_on_scaled_canvas():
    """Regression: when rendered on a ScaledCanvas, measure_width must
    use the hi-res sprite's logical width — otherwise low-res-shorter
    emoji like :flower: (5 wide low-res, 8 wide at scale=4 hi-res) cause
    overflow-scroll detection to silently fail because measured width
    underestimates rendered width.
    """
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    # Low-res :flower: is 5 wide; hi-res at scale=4 is 8 logical wide
    no_canvas = measure_width(FONT_SMALL, ":flower:")
    with_canvas = measure_width(FONT_SMALL, ":flower:", sc)
    # Without the canvas, measure_width uses the low-res 5+padding=7
    # With the canvas, hi-res 8+padding=10
    assert no_canvas == 7
    assert with_canvas == 10


def test_measure_width_respects_max_emoji_height():
    """When max_emoji_height forces hi-res→low-res fallback (e.g. two_row
    at scale=2 caps emoji height at 8 logical), measure_width must mirror
    that fallback so cached widths match what gets rendered.
    """
    real = _bigsign_real_canvas()
    # At scale=2, hi-res 32px is 16 logical tall — exceeds the 8-row cap
    sc = ScaledCanvas(real, scale=2)
    capped = measure_width(FONT_SMALL, ":flower:", sc, max_emoji_height=8)
    # Falls back to low-res: 5 + padding 2 = 7
    assert capped == 7
    # Without cap: hi-res 32/2=16 logical wide + padding = 18
    uncapped = measure_width(FONT_SMALL, ":flower:", sc)
    assert uncapped == 18


def test_message_widget_overflow_scroll_with_hires_emoji():
    """Regression for the bigsign bug where 7 hi-res emojis (=70 logical
    px at scale=4) didn't trigger scroll because measure_width returned
    64 (low-res widths sum). Verifies TickerMessage now reports a width
    that exceeds canvas.width when hi-res rendering would overflow.
    """
    from led_ticker.widgets.message import TickerMessage

    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    msg = TickerMessage(message=":moon::sun::star::instagram::email::baseball::flower:")
    _, cursor_pos = msg.draw(sc, cursor_pos=0)
    # Canvas is 64 logical wide (256 / 4). 7 hi-res emojis = 7 × (8 + 2) = 70.
    # cursor_pos returns content_width + padding (default 6) = 76. Caller
    # uses cursor_pos > canvas.width to decide whether to scroll.
    assert cursor_pos > sc.width, (
        f"Expected cursor_pos > {sc.width} to trigger scroll; got {cursor_pos}. "
        "If this is 64-70 the low-res-width-only bug has regressed."
    )


def test_instagram_and_email_emojis_registered():
    """Regression: the Instagram + email icons are wired into the registry
    so configs can use `:instagram:` and `:email:` slugs.
    """
    from led_ticker.pixel_emoji import _get_registry

    registry = _get_registry()
    assert "instagram" in registry
    assert "email" in registry
    # Both icons render as 8x8 (or close)
    assert len(registry["instagram"]) > 0
    assert len(registry["email"]) > 0


def test_instagram_emoji_renders_through_scaled_canvas():
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    advance = draw_with_emoji(
        sc,
        FONT_SMALL,
        cursor_pos=0,
        y=8,
        color=(255, 255, 255),
        text=":instagram: @moonbunnyaerial",
    )
    assert advance > 0


def test_email_emoji_renders_through_scaled_canvas():
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    advance = draw_with_emoji(
        sc,
        FONT_SMALL,
        cursor_pos=0,
        y=8,
        color=(255, 255, 255),
        text=":email: info@moonbunnyaerial.com",
    )
    assert advance > 0


def test_moon_emoji_registered():
    from led_ticker.pixel_emoji import _get_registry

    registry = _get_registry()
    assert "moon" in registry
    assert len(registry["moon"]) > 0


def test_moon_emoji_renders_through_scaled_canvas():
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    advance = draw_with_emoji(
        sc, FONT_SMALL, cursor_pos=0, y=8, color=(255, 255, 255), text=":moon: hi"
    )
    assert advance > 0


def test_moon_emoji_is_8x8():
    """All bundled emoji should fit an 8x8 grid for inline use. Catches a
    regression where someone copies a wider sprite (like TACO at 14x8)
    into the moon slot.
    """
    from led_ticker.pixel_emoji import MOON

    max_x = max(x for x, _, _, _, _ in MOON)
    max_y = max(y for _, y, _, _, _ in MOON)
    assert max_x <= 7, f"moon icon too wide: max x={max_x}"
    assert max_y <= 7, f"moon icon too tall: max y={max_y}"


# --- Hi-res emoji ---


def test_hires_moon_registered():
    """The registry holds the AUTO-TRIMMED moon (pixels shifted to
    left edge, physical_width = lit bbox), not the raw `MOON_HIRES`
    constant. `_auto_trim_hires` recomputes physical_width from lit
    pixels, so the registry entry differs from the source constant.
    """
    from led_ticker.pixel_emoji import HIRES_REGISTRY, MOON_HIRES

    assert "moon" in HIRES_REGISTRY
    assert HIRES_REGISTRY["moon"].physical_size == 32
    # Source constant unchanged; registry entry is the trimmed version.
    assert MOON_HIRES.physical_size == 32


def test_hires_moon_logical_width_matches_lowres():
    """After auto-trim the crescent's lit pixels span 19 cols
    (cols 0..18 post-shift). `logical_width` ceil-divides:
    ceil(19/4) = 5 logical cols at scale=4 — matches the low-res
    MOON's 5-col footprint and matches the previously hand-tuned
    `physical_width=20` value. At scale=2: ceil(19/2) = 10.
    """
    from led_ticker.pixel_emoji import HIRES_REGISTRY

    moon = HIRES_REGISTRY["moon"]
    assert moon.logical_width(scale=4) == 5
    assert moon.logical_width(scale=2) == 10
    assert moon.physical_size == 32  # full canvas height preserved


def test_hires_moon_paints_real_canvas_at_physical_resolution():
    """Hi-res emoji writes individual physical pixels — proven by checking
    that lit pixels appear at columns NOT divisible by `scale`. The
    low-res path would expand each 8×8 logical pixel into a 4×4 block,
    so its lit columns are always 0,1,2,3 then 4,5,6,7 etc. — every
    block-aligned. A lit pixel at col 11 (mod 4 = 3) only happens when
    the hi-res path is in use.
    """
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)

    # y=12 is the standard BDF baseline; iy_default = y - 8 = 4
    # (anchors emoji bottom to baseline). emoji_y_anchor = 4*4 = 16.
    draw_with_emoji(
        sc, FONT_SMALL, cursor_pos=0, y=12, color=(255, 255, 255), text=":moon:"
    )

    # The hi-res moon has its leftmost lit pixel at col 11 in row 1
    # (= real row 17 with emoji_y=4*4=16 offset). If the low-res path
    # were used, real col 11 in any row would be black (low-res lights
    # blocks: cols 0-3, 4-7, 8-11... but only where the 8×8 sprite has
    # lit logical pixels, and MOON's leftmost is logical col 0).
    assert real.get_pixel(11, 17) != (0, 0, 0), (
        "real(11, 17) should be lit by the hi-res sprite. If it's black, "
        "the hi-res path didn't activate and the wrapper expansion took "
        "over (which can't produce non-block-aligned pixels)."
    )


def test_hires_falls_back_to_lowres_on_real_canvas():
    """No ScaledCanvas → no hi-res path. The 8×8 :moon: should render
    on the small sign's plain canvas.
    """
    real = _bigsign_real_canvas()  # not wrapped in ScaledCanvas
    advance = draw_with_emoji(
        real,
        FONT_SMALL,
        cursor_pos=0,
        y=8,
        color=(255, 255, 255),
        text=":moon:",
    )
    # 8×8 MOON (uniform 3-wide crescent) has lit pixels through col 4
    # → width 5 → +2 padding = 7.
    assert advance == 7


def test_generate_moon_hires_produces_pixels():
    from led_ticker.pixel_emoji import _generate_moon_hires

    pixels = _generate_moon_hires(size=32, color=(255, 220, 130), bite_offset=0.30)
    assert len(pixels) > 200  # crescent shape lit pixel count
    # Every pixel within the 32×32 bounds
    for x, y, *_ in pixels:
        assert 0 <= x < 32
        assert 0 <= y < 32


@pytest.mark.parametrize("slug", ["moon", "instagram", "sun", "star", "email"])
def test_hires_emoji_in_registry(slug):
    """Every slug we promised to upgrade should have a hi-res variant."""
    from led_ticker.pixel_emoji import HIRES_REGISTRY

    assert slug in HIRES_REGISTRY
    h = HIRES_REGISTRY[slug]
    assert h.physical_size == 32
    # Sanity: hi-res sprites should fill at least 50 pixels (otherwise
    # something's wrong with the generator)
    assert len(h.pixels) > 50, f"{slug} has only {len(h.pixels)} lit pixels"
    # All pixels in bounds
    for x, y, *_ in h.pixels:
        assert 0 <= x < 32, f"{slug}: x={x} out of bounds"
        assert 0 <= y < 32, f"{slug}: y={y} out of bounds"


def test_instagram_hires_uses_gradient_colors():
    """The IG hi-res sprite should have multiple distinct colors (the
    gradient). 8×8 low-res ships in a single magenta — this proves the
    hi-res variant actually carries the multi-stop gradient.
    """
    from led_ticker.pixel_emoji import INSTAGRAM_HIRES

    distinct_colors = {(r, g, b) for _, _, r, g, b in INSTAGRAM_HIRES.pixels}
    assert (
        len(distinct_colors) > 50
    ), f"IG hi-res should have many gradient colors; got {len(distinct_colors)}"


def test_instagram_hires_has_central_lens_hole():
    """The lens hole at the center should NOT be lit (negative-space eye)."""
    from led_ticker.pixel_emoji import INSTAGRAM_HIRES

    lit = {(x, y) for x, y, *_ in INSTAGRAM_HIRES.pixels}
    # Center pixel at (15, 15) or (16, 16) should be empty (lens hole)
    assert (15, 15) not in lit
    assert (16, 16) not in lit


def test_max_emoji_height_falls_back_to_lowres():
    """When `max_emoji_height` is below the hi-res sprite's logical
    height, the renderer must fall back to the 8×8 sprite — otherwise
    the hi-res icon overflows the row in a two_row layout (the bug
    seen on the bigsign at scale=2 where 32 physical = 16 logical
    pixels tall, exceeding the 8-tall row band).
    """
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=2)  # 32 physical / 2 = 16 logical tall sprite

    # First, no cap → hi-res used. Real(11, _) should be lit (non-block-aligned).
    real.Clear()
    draw_with_emoji(
        sc, FONT_SMALL, cursor_pos=0, y=8, color=(255, 255, 255), text=":moon:"
    )
    # With scale=2 and 16-tall canvas (default), emoji_y=4 → real_y_anchor=8.
    # Hi-res moon col 11 is lit somewhere in rows 8-39.
    hires_lit_at_11 = any(
        real.get_pixel(11, y) != (0, 0, 0) for y in range(real.height)
    )
    assert hires_lit_at_11, "hi-res should be active when no cap"

    # Now with a cap of 8 logical (the row band). Hi-res sprite is 16
    # logical tall at scale=2 → exceeds cap → fall back to low-res.
    real.Clear()
    advance = draw_with_emoji(
        sc,
        FONT_SMALL,
        cursor_pos=0,
        y=8,
        color=(255, 255, 255),
        text=":moon:",
        max_emoji_height=8,
    )
    # Low-res advance: 8x8 MOON (uniform 3-wide) has lit pixels through
    # col 4 → width 5 → +2 padding = 7.
    assert advance == 7, (
        f"With max_emoji_height=8 < hi-res 16, should fall back to low-res "
        f"(width=7); got advance={advance}"
    )


@pytest.mark.parametrize("slug", ["instagram", "sun", "star", "email"])
def test_hires_emoji_renders_via_scaled_canvas(slug):
    """Each new hi-res emoji should render through the wrapper-bypass path."""
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)
    advance = draw_with_emoji(
        sc, FONT_SMALL, cursor_pos=0, y=8, color=(255, 255, 255), text=f":{slug}:"
    )
    assert advance > 0
    # Some real-canvas pixels should be lit
    lit_count = sum(
        1
        for x in range(real.width)
        for y in range(real.height)
        if real.get_pixel(x, y) != (0, 0, 0)
    )
    assert lit_count > 50, f"{slug} hi-res produced only {lit_count} lit pixels"


class TestDrawWithEmojiHiresFont:
    def test_default_emoji_y_uses_font_line_height(self):
        """When emoji_y is not specified, the default position should be
        derived from the font's line_height (centering the 8x8 sprite
        on the glyph cell), not hardcoded for BDF."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.pixel_emoji import draw_with_emoji
        from led_ticker.scaled_canvas import ScaledCanvas

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        font = resolve_font("Inter-Regular", 24)
        # Should not crash; should return positive total.
        total = draw_with_emoji(
            wrapped,
            font,
            cursor_pos=10,
            y=12,
            color=Color(255, 255, 255),
            text=":taco: hi",
        )
        assert total > 0

    def test_measure_width_with_hires_font(self):
        """measure_width should handle hi-res fonts for non-emoji text."""
        from led_ticker.fonts import resolve_font
        from led_ticker.pixel_emoji import measure_width

        font = resolve_font("Inter-Regular", 24)
        width = measure_width(font, "hi")
        assert width > 0

    def test_emoji_y_default_anchors_to_baseline_for_hires(self):
        """Tripwire: with HiresFont, the default emoji_y must anchor
        the 8-logical-px-tall sprite to the text baseline (`iy = y -
        8`), NOT use the broken `(line_h - 8) // 2` formula that
        mixed real-px line_h with logical iy.

        Hardware bug: §16 (HiresFont + emoji + rainbow) had
        Inter-Bold @ 24 with baseline_y=10 logical. The buggy formula
        produced `iy = (28 - 8) // 2 = 10`, so the 32×32 hires taco
        painted at real y=40..72 — bottom 8 px clipped, and the
        rainbow text at y=12..48 sat above the visible taco tops with
        an empty band between them.
        """
        import unittest.mock as mock

        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.pixel_emoji import draw_with_emoji
        from led_ticker.scaled_canvas import ScaledCanvas

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        font = resolve_font("Inter-Bold", 24)

        captured_iy: list[int] = []

        def _spy(canvas, hires, ix, iy):
            captured_iy.append(iy)

        with mock.patch("led_ticker.pixel_emoji._draw_hires_emoji", _spy):
            draw_with_emoji(
                wrapped,
                font,
                cursor_pos=0,
                y=10,  # baseline for Inter-Bold @ 24 on 64-tall panel
                color=Color(255, 255, 255),
                text=":taco: hi",
            )

        assert captured_iy, "hires path didn't fire"
        # iy = y - 8 = 2 (logical). Anchors emoji bottom to baseline:
        # real y_anchor = 2*4 = 8, sprite extends to real y=40 = baseline.
        assert captured_iy[0] == 2, (
            f"Expected iy=2 (baseline-anchored: y=10 - emoji_h=8); "
            f"got {captured_iy[0]}. Likely regression of the unit-"
            f"mismatched (line_h - 8) // 2 formula that produced 10 "
            f"and clipped the emoji off the bottom of the panel."
        )

    def test_emoji_y_default_unchanged_for_bdf(self):
        """Counter-test: BDF default must still equal 4 (the hardcoded
        visually-validated value). Confirms the unified `y - 8`
        formula doesn't break BDF — for BDF baseline_y=12, y - 8 = 4
        which matches the previous hardcoded constant."""
        import unittest.mock as mock

        from rgbmatrix.graphics import Color

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.pixel_emoji import draw_with_emoji

        # Use a small canvas without ScaledCanvas — lowres path fires.
        # We intercept the lowres SetPixel to read the iy used.
        canvas = mock.MagicMock()
        canvas.width = 64
        canvas.height = 16

        # Capture every SetPixel call and look at the y value used for
        # emoji pixels. The first emoji is `:taco:` whose sprite has
        # a known relative-y range — the absolute y for the first
        # pixel painted gives us the iy default.
        from led_ticker.pixel_emoji import _get_registry

        taco = _get_registry()["taco"]
        # Find the minimum y in the sprite — that pixel is at iy + min_y.
        min_relative_y = min(py for _, py, *_ in taco)

        captured_y: list[int] = []
        canvas.SetPixel.side_effect = lambda x, y, r, g, b: captured_y.append(y)

        draw_with_emoji(
            canvas,
            FONT_DEFAULT,
            cursor_pos=0,
            y=12,  # BDF baseline
            color=Color(255, 255, 255),
            text=":taco:",
        )

        # iy_default = 12 - 8 = 4 → first emoji pixel y = iy + min_relative_y.
        assert captured_y, "lowres path didn't paint any pixels"
        assert min(captured_y) == 4 + min_relative_y, (
            f"Expected min y = 4 + {min_relative_y} = {4 + min_relative_y} "
            f"(BDF baseline=12, emoji top=baseline-8=4); "
            f"got min y = {min(captured_y)}"
        )


class TestDrawWithEmojiColorProvider:
    """`draw_with_emoji` accepts a ColorProvider in addition to a raw
    Color. Per-char providers (rainbow, gradient) sweep continuously
    across emoji boundaries — char_index advances only on text
    characters, so the rainbow doesn't reset at each `:slug:`.

    Tripwire for the bug where `:taco: HOT TACOS :taco:` + rainbow used
    to call `provider.color_for(frame, 0, total)` once for the whole
    string (whole-string degradation), losing the per-char effect on
    the letters between sprites."""

    def test_per_char_provider_iterates_text_chars(self):
        """When a per-char provider is passed, draw_with_emoji should
        materialize a different color for each text character. Spy on
        the provider's color_for to count calls."""
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.pixel_emoji import draw_with_emoji

        calls: list[tuple[int, int, int]] = []

        class _SpyProvider:
            per_char = True

            def color_for(self, frame, char_index, total_chars):
                calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        canvas = _StubCanvas(width=160, height=16)
        draw_with_emoji(
            canvas,
            FONT_DEFAULT,
            cursor_pos=0,
            y=10,
            color=_SpyProvider(),
            text=":taco: HI :taco:",
            frame=5,
        )

        # Text segments: " HI " (4 chars total — including spaces).
        # Emoji slugs don't trigger color_for. So we expect 4 calls.
        assert len(calls) == 4
        # All calls share the same frame and total_chars.
        assert all(f == 5 for f, _, _ in calls)
        assert all(t == 4 for _, _, t in calls)
        # char_index advances continuously across the emoji boundary
        # (the second emoji doesn't reset the index).
        assert [idx for _, idx, _ in calls] == [0, 1, 2, 3]

    def test_whole_string_provider_materializes_once_per_segment(self):
        """A whole-string provider (per_char = False) materializes one
        color per text segment — emoji breaks restart at the running
        char_index but each call still gets the same color since the
        provider ignores char_index."""
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.pixel_emoji import draw_with_emoji

        calls: list[tuple[int, int, int]] = []

        class _WholeProvider:
            per_char = False

            def color_for(self, frame, char_index, total_chars):
                calls.append((frame, char_index, total_chars))
                return Color(0, 200, 100)

        canvas = _StubCanvas(width=160, height=16)
        # Two text segments separated by an emoji: " HI " and " BYE".
        draw_with_emoji(
            canvas,
            FONT_DEFAULT,
            cursor_pos=0,
            y=10,
            color=_WholeProvider(),
            text=" HI :taco: BYE",
            frame=7,
        )

        # 2 calls — one per text segment (whole-string materialization).
        assert len(calls) == 2
        assert all(f == 7 for f, _, _ in calls)

    def test_raw_color_legacy_path_still_works(self):
        """Existing callers that pass a raw graphics.Color must
        continue to work — the function should detect the absence of
        `color_for` and fall through to the single draw_text path."""
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import FONT_DEFAULT
        from led_ticker.pixel_emoji import draw_with_emoji

        canvas = _StubCanvas(width=160, height=16)
        # Should not raise.
        advance = draw_with_emoji(
            canvas,
            FONT_DEFAULT,
            cursor_pos=0,
            y=10,
            color=Color(255, 100, 50),
            text=":taco: HI",
        )
        assert advance > 0

    def test_hires_font_per_char_provider_with_emoji(self):
        """Tripwire: HiresFont + per-char provider + emoji slugs
        must route through draw_with_emoji's per-char branch and use
        the shared `draw_text_per_char` helper, which tracks the
        cursor in real pixels for HiresFont (avoids per-char
        ceil-divide drift inside text segments separated by sprites).

        Verifies the provider is called once per text character,
        sprites still render, and char_index advances continuously
        across emoji boundaries — same contract as the BDF path but
        on the HiresFont render code-path."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        from rgbmatrix.graphics import Color

        from led_ticker.fonts import resolve_font
        from led_ticker.pixel_emoji import draw_with_emoji
        from led_ticker.scaled_canvas import ScaledCanvas

        font = resolve_font("Inter-Regular", 24)
        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        canvas = ScaledCanvas(real, scale=4)

        calls: list[tuple[int, int, int]] = []

        class _SpyProvider:
            per_char = True

            def color_for(self, frame, char_index, total_chars):
                calls.append((frame, char_index, total_chars))
                return Color(255, 255, 255)

        advance = draw_with_emoji(
            canvas,
            font,
            cursor_pos=0,
            y=10,
            color=_SpyProvider(),
            text=":taco: HI :taco:",
            frame=3,
        )

        # 4 text chars (" HI ") get individual color_for calls; sprites don't.
        assert len(calls) == 4
        assert all(f == 3 for f, _, _ in calls)
        # char_index advances continuously across the second emoji.
        assert [idx for _, idx, _ in calls] == [0, 1, 2, 3]
        # total_chars equals the count of text chars (no emoji slugs counted).
        assert all(t == 4 for _, _, t in calls)
        # The full draw produces non-zero advance (emoji + text rendered).
        assert advance > 0


def test_partly_cloudy_in_both_registries():
    """partly_cloudy is a weather slug; it must be in both lowres and
    hires registries so the icon renders crisply on bigsign and falls
    back to a working sprite on the small sign. The hires variant
    composes a half-size sun in the top-right with the full cloud
    silhouette anchored bottom (cloud overrides sun on overlap).

    After `_auto_trim_hires`, `physical_width` reflects the lit-pixel
    bbox (27 cols) — not None — so the layout footprint matches the
    sprite's actual visible content rather than the full 32×32 canvas.
    """
    from led_ticker.pixel_emoji import HIRES_REGISTRY, _get_registry

    registry = _get_registry()
    assert "partly_cloudy" in registry
    assert "partly_cloudy" in HIRES_REGISTRY
    h = HIRES_REGISTRY["partly_cloudy"]
    assert h.physical_size == 32
    # Auto-trim: lit pixels span 27 cols → logical_width(4) = ceil(27/4) = 7.
    assert h.physical_width == 27
    assert h.logical_width(scale=4) == 7


class TestDrawEmojiAt:
    """Single-slug helper that picks hires on ScaledCanvas, lowres elsewhere."""

    def test_lowres_on_plain_canvas_returns_advance(self):
        """On a non-ScaledCanvas, lowres path is used. Returns
        sprite_width + EMOJI_PADDING."""
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import EMOJI_PADDING, draw_emoji_at

        canvas = _StubCanvas(width=160, height=16)
        advance = draw_emoji_at(canvas, "sun", x=0, y=4)
        # SUN is 8 wide
        assert advance == 8 + EMOJI_PADDING
        assert canvas.count_nonzero() > 0

    def test_hires_on_scaled_canvas_routes_through_hires_path(self, monkeypatch):
        """On a ScaledCanvas, draw_emoji_at routes through _draw_hires_emoji.
        Asserted by hooking the private helper — proves the hires gate
        actually fires rather than counting pixels (the lowres-via-wrapper
        path also produces a non-empty real canvas, so a pixel-count
        comparison can't reliably prove the hires path was taken).
        """
        from led_ticker import pixel_emoji
        from led_ticker.pixel_emoji import draw_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=4)

        calls: list[str] = []
        original = pixel_emoji._draw_hires_emoji

        def spy(canvas, hires, ix, iy):
            calls.append("hires")
            return original(canvas, hires, ix, iy)

        monkeypatch.setattr(pixel_emoji, "_draw_hires_emoji", spy)

        draw_emoji_at(sc, "sun", x=0, y=0)

        assert calls == ["hires"], (
            "Expected _draw_hires_emoji to fire exactly once on a "
            "ScaledCanvas for a slug with a HIRES_REGISTRY entry. The "
            "hires gate isn't firing."
        )

    def test_hires_falls_back_when_max_height_too_small(self):
        """A two-row caller passes max_emoji_height=4 (canvas.height // 2
        on a 16-tall logical canvas wrapped at scale=2). Hires sprite is
        32 // 2 = 16 logical tall, which exceeds 4 — must fall back to
        lowres so it doesn't overflow the row band."""
        from led_ticker.pixel_emoji import EMOJI_PADDING, draw_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=2)
        advance = draw_emoji_at(sc, "sun", x=0, y=0, max_emoji_height=4)
        # Lowres advance is 8 + EMOJI_PADDING; hires would be different
        # (16 logical at scale=2 etc.). We just assert the lowres value.
        assert advance == 8 + EMOJI_PADDING

    def test_unknown_slug_raises(self):
        """Drop-it-loud behavior: a typo'd slug raises KeyError instead
        of silently drawing nothing."""
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import draw_emoji_at

        canvas = _StubCanvas(width=160, height=16)
        with pytest.raises(KeyError):
            draw_emoji_at(canvas, "definitely_not_a_slug", x=0, y=0)

    def test_partly_cloudy_resolves_via_hires_on_scaled_canvas(self):
        """partly_cloudy has a hires variant — `draw_emoji_at` picks it
        on a ScaledCanvas. After auto-trim, lit_w=27 → logical_width(4)
        = ceil(27/4) = 7, so advance = 7 + EMOJI_PADDING.
        """
        from led_ticker.pixel_emoji import EMOJI_PADDING, draw_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=4)
        advance = draw_emoji_at(sc, "partly_cloudy", x=0, y=0)
        assert advance == 7 + EMOJI_PADDING


_WEATHER_SLUGS = ["sun", "cloud", "rain", "snow", "thunder", "fog", "partly_cloudy"]


class TestMeasureEmojiAtMatchesDrawEmojiAt:
    """`measure_emoji_at` must return the same advance `draw_emoji_at`
    returns — they share the hires/lowres gate, and a layout/draw
    mismatch produces overlap or gap. Exhaustively check across every
    weather slug × every relevant canvas type (plain canvas, scale=2,
    scale=4) so a future gate divergence is caught at any scale.
    """

    @pytest.mark.parametrize("slug", _WEATHER_SLUGS)
    def test_agrees_on_plain_canvas(self, slug):
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import draw_emoji_at, measure_emoji_at

        canvas = _StubCanvas(width=160, height=16)
        measured = measure_emoji_at(canvas, slug)
        # Use a fresh canvas for the draw so the measure isn't perturbed.
        drawn_advance = draw_emoji_at(_StubCanvas(width=160, height=16), slug, 0, 4)
        assert measured == drawn_advance, (
            f"measure_emoji_at({slug}) returned {measured} but "
            f"draw_emoji_at returned {drawn_advance} — gate divergence "
            f"on plain canvas would mean weather's layout math drifts "
            f"from where the icon actually lands."
        )

    @pytest.mark.parametrize("slug", _WEATHER_SLUGS)
    @pytest.mark.parametrize("scale", [2, 4])
    def test_agrees_on_scaled_canvas(self, slug, scale):
        from led_ticker.pixel_emoji import draw_emoji_at, measure_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=scale)
        measured = measure_emoji_at(sc, slug)
        # Fresh wrapper so the draw doesn't see the previous frame.
        drawn_advance = draw_emoji_at(
            ScaledCanvas(_bigsign_real_canvas(), scale=scale), slug, 0, 4
        )
        assert measured == drawn_advance, (
            f"measure_emoji_at({slug!r}, scale={scale}) returned "
            f"{measured} but draw_emoji_at returned {drawn_advance} — "
            f"gate divergence on bigsign would put the temperature "
            f"text on top of the icon (scale=2) or with a visible gap."
        )

    def test_max_emoji_height_fallback_agrees(self):
        """When max_emoji_height forces hires→lowres fallback, both
        helpers must agree on the lowres advance."""
        from led_ticker.pixel_emoji import draw_emoji_at, measure_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=2)
        # Hires sun at scale=2 is 16 logical tall — max=4 forces lowres.
        measured = measure_emoji_at(sc, "sun", max_emoji_height=4)
        drawn_advance = draw_emoji_at(
            ScaledCanvas(_bigsign_real_canvas(), scale=2),
            "sun",
            0,
            4,
            max_emoji_height=4,
        )
        assert measured == drawn_advance


class TestMeasureEmojiAt:
    """Direct contract tests for measure_emoji_at — the spec is that
    returned width equals sprite_width + EMOJI_PADDING, with the
    sprite chosen by the same gate as draw_emoji_at."""

    def test_lowres_on_plain_canvas(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import EMOJI_PADDING, measure_emoji_at

        # SUN lowres is 8 wide.
        assert (
            measure_emoji_at(_StubCanvas(width=160, height=16), "sun")
            == 8 + EMOJI_PADDING
        )

    def test_hires_on_bigsign_scale_4(self):
        from led_ticker.pixel_emoji import EMOJI_PADDING, measure_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        # SUN_HIRES is physical_size=32; at scale=4 logical_width=8.
        sc = ScaledCanvas(_bigsign_real_canvas(), scale=4)
        assert measure_emoji_at(sc, "sun") == 8 + EMOJI_PADDING

    def test_hires_on_bigsign_scale_2(self):
        """At scale=2 the hires sun fills more logical cols than at
        scale=4 — ensures the weather widget's layout math reads
        the canvas-scale-aware footprint rather than a hardcoded
        constant. After auto-trim sun has lit_w=30 → logical_width(2)
        = ceil(30/2) = 15.
        """
        from led_ticker.pixel_emoji import EMOJI_PADDING, measure_emoji_at
        from led_ticker.scaled_canvas import ScaledCanvas

        sc = ScaledCanvas(_bigsign_real_canvas(), scale=2)
        assert measure_emoji_at(sc, "sun") == 15 + EMOJI_PADDING

    def test_unknown_slug_raises(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import measure_emoji_at

        with pytest.raises(KeyError):
            measure_emoji_at(_StubCanvas(width=160, height=16), "no_such_slug")


class TestHiresAutoTrim:
    """Hi-res sprites in `HIRES_REGISTRY` are auto-trimmed at assembly:
    pixels are shifted left so `min_x == 0`, and `physical_width` is
    set to `max_x - min_x + 1`. Generalizes the manual moon override
    so internal sprite whitespace doesn't create asymmetric gaps when
    an emoji is bordered by text (`:bunny: HI :heart_pink:`).

    `logical_width()` uses ceiling division so unaligned widths (e.g.
    cat's lit_w=22 at scale=4) don't truncate and overdraw the next
    element's first column.
    """

    def test_bunny_pixels_shifted_to_left_edge(self):
        """Bunny's lit pixels originally span cols 4-27 inside the 32-wide
        sprite. After trim the leftmost lit pixel is at col 0."""
        from led_ticker.pixel_emoji import HIRES_REGISTRY

        bunny = HIRES_REGISTRY["bunny"]
        xs = [px for px, _, _, _, _ in bunny.pixels]
        assert min(xs) == 0, (
            f"bunny min_x={min(xs)} — expected 0 after auto-trim. "
            "Internal-left whitespace is still in the sprite, which "
            "creates an asymmetric gap to the previous text segment."
        )

    def test_bunny_physical_width_matches_lit_extent(self):
        """Bunny lit pixels span 24 cols after shift → physical_width=24."""
        from led_ticker.pixel_emoji import HIRES_REGISTRY

        bunny = HIRES_REGISTRY["bunny"]
        xs = [px for px, _, _, _, _ in bunny.pixels]
        lit_w = max(xs) - min(xs) + 1
        assert bunny.physical_width == lit_w
        assert bunny.physical_width == 24

    def test_pride_unchanged_already_edge_to_edge(self):
        """Pride fills cols 0..31 — already edge-to-edge, no trim needed.
        physical_width stays 32 (or None) so logical footprint is
        unchanged."""
        from led_ticker.pixel_emoji import HIRES_REGISTRY

        pride = HIRES_REGISTRY["pride"]
        xs = [px for px, _, _, _, _ in pride.pixels]
        assert min(xs) == 0
        assert max(xs) == 31
        # Width covers the full 32 either way (None or 32 are equivalent).
        effective_w = (
            pride.physical_width
            if pride.physical_width is not None
            else pride.physical_size
        )
        assert effective_w == 32

    def test_trim_preserves_pixel_colors_and_y(self):
        """Trim shifts x by min_x but must preserve y and color tuples
        for every pixel — otherwise the sprite's silhouette breaks.
        Compare directly against the source `BUNNY_HIRES` constant:
        the registered sprite must equal each source pixel shifted
        left by 4 (bunny's pre-trim min_x).
        """
        from led_ticker.pixel_emoji import BUNNY_HIRES, HIRES_REGISTRY

        bunny_trimmed = HIRES_REGISTRY["bunny"]
        # Pre-trim bunny pixels start at x=4 (the empty-left margin).
        source_min_x = min(px for px, _, _, _, _ in BUNNY_HIRES.pixels)
        assert source_min_x == 4
        # Every trimmed pixel must equal `(source_x - 4, source_y, r, g, b)`.
        expected = tuple(
            (px - source_min_x, py, r, g, b) for (px, py, r, g, b) in BUNNY_HIRES.pixels
        )
        assert bunny_trimmed.pixels == expected, (
            "Trim mutated y or color values, or shifted x by the wrong "
            "amount. The registered sprite no longer matches the source "
            "constant shifted by min_x."
        )

    def test_logical_width_uses_ceiling_division(self):
        """Auto-trim can produce unaligned physical_widths (e.g. cat's
        lit_w=22 at scale=4 → 22/4 = 5.5). Floor division would return
        5 logical cols, but the sprite's lit content extends 22 real px
        — the next element drawn at logical 5 would overdraw the
        sprite's last 2 lit pixels. Ceiling rounds UP to 6 logical cols,
        leaving the sprite intact.
        """
        from led_ticker.pixel_emoji import HiResEmoji

        # Synthetic sprite with lit_w=22 (matching cat after trim).
        sprite = HiResEmoji(
            pixels=tuple((x, 0, 255, 255, 255) for x in range(22)),
            physical_size=32,
            physical_width=22,
        )
        assert sprite.logical_width(scale=4) == 6  # ceil(22/4) = 6
        assert sprite.logical_width(scale=2) == 11  # ceil(22/2) = 11
        assert sprite.logical_width(scale=1) == 22

    def test_cat_logical_footprint_shrinks_after_trim(self):
        """Concrete: cat lit_w=22 → at scale=4, footprint is 6 logical
        cols (not 8). Two-col reduction in inline-text width.
        """
        from led_ticker.pixel_emoji import HIRES_REGISTRY

        cat = HIRES_REGISTRY["cat"]
        assert cat.logical_width(scale=4) == 6

    def test_heart_logical_width_unchanged_at_scale_4(self):
        """heart lit_w=30 → ceil(30/4) = 8, same as the un-trimmed
        physical_size=32 footprint. Auto-trim shifts the sprite but
        doesn't shrink its footprint at scale=4."""
        from led_ticker.pixel_emoji import HIRES_REGISTRY

        heart = HIRES_REGISTRY["heart"]
        assert heart.logical_width(scale=4) == 8

    def test_all_hires_sprites_start_at_left_edge(self):
        """Every entry in HIRES_REGISTRY has min_x == 0 after auto-trim.
        A sprite with internal-left whitespace creates an asymmetric
        gap to the preceding text segment in `:emoji: word :emoji:`
        rows."""
        from led_ticker.pixel_emoji import HIRES_REGISTRY

        for slug, hires in HIRES_REGISTRY.items():
            xs = [px for px, _, _, _, _ in hires.pixels]
            assert min(xs) == 0, (
                f"{slug} has internal-left whitespace (min_x={min(xs)}). "
                "Auto-trim should have shifted it to the left edge."
            )


class TestEmojiPaddingSymmetric:
    """`EMOJI_PADDING` is applied on BOTH sides of an emoji adjacent to
    text. Previously it was only applied AFTER an emoji, which created
    a permanent asymmetric gap around emojis bordered by text on both
    sides (e.g. `:pride: LOVE :pride:` showed a wider gap on the right
    of the first emoji than on the left of the second).

    Rules:
      - Pad BEFORE an emoji whose previous segment was text.
      - Pad AFTER every emoji (existing behavior, unchanged).
      - No leading pad if emoji is first segment (or after another emoji).

    `draw_emoji_at` and `measure_emoji_at` are single-icon helpers
    used by widgets that explicitly position one icon — they don't
    parse `:slug:` sequences and keep their `sprite_w + EMOJI_PADDING`
    contract unchanged.
    """

    def test_leading_emoji_no_pre_pad(self):
        """`:taco:hello` — taco is the FIRST segment, no leading pad.
        Width = taco_w + EMOJI_PADDING + text_w(hello, padding=0).
        """
        from led_ticker.drawing import get_text_width
        from led_ticker.pixel_emoji import (
            EMOJI_PADDING,
            _emoji_width,
            _get_registry,
            measure_width,
        )

        taco_w = _emoji_width(_get_registry()["taco"])
        hello_w = get_text_width(FONT_SMALL, "hello", padding=0)
        # No canvas → low-res; just text + low-res taco.
        assert measure_width(FONT_SMALL, ":taco:hello") == (
            taco_w + EMOJI_PADDING + hello_w
        )

    def test_text_then_emoji_gets_pre_pad(self):
        """`hi:taco:` — taco is preceded by text, so pre-pad fires.
        Width = text_w(hi) + EMOJI_PADDING + taco_w + EMOJI_PADDING.
        Without the pre-pad fix, width would be:
            text_w(hi) + taco_w + EMOJI_PADDING.
        """
        from led_ticker.drawing import get_text_width
        from led_ticker.pixel_emoji import (
            EMOJI_PADDING,
            _emoji_width,
            _get_registry,
            measure_width,
        )

        taco_w = _emoji_width(_get_registry()["taco"])
        hi_w = get_text_width(FONT_SMALL, "hi", padding=0)
        assert measure_width(FONT_SMALL, "hi:taco:") == (
            hi_w + EMOJI_PADDING + taco_w + EMOJI_PADDING
        )

    def test_back_to_back_emojis_no_double_pad(self):
        """`:taco::taco:` — two adjacent emojis, no text between. The
        second taco's previous segment is an emoji (not text) → no
        leading pad. Each emoji contributes only its trailing pad.
        Width = 2 * (taco_w + EMOJI_PADDING).
        """
        from led_ticker.pixel_emoji import (
            EMOJI_PADDING,
            _emoji_width,
            _get_registry,
            measure_width,
        )

        taco_w = _emoji_width(_get_registry()["taco"])
        assert measure_width(FONT_SMALL, ":taco::taco:") == (
            2 * (taco_w + EMOJI_PADDING)
        )

    def test_emoji_text_emoji_balanced(self):
        """`:taco: hi :taco:` — second taco gets pre-pad because the
        " hi " text segment is its previous segment. The visible gaps
        around "hi" are now symmetric:
            after first taco: EMOJI_PADDING + space char
            before second taco: space char + EMOJI_PADDING
        Width = taco_w + PAD + text_w(' hi ') + PAD + taco_w + PAD.
        """
        from led_ticker.drawing import get_text_width
        from led_ticker.pixel_emoji import (
            EMOJI_PADDING,
            _emoji_width,
            _get_registry,
            measure_width,
        )

        taco_w = _emoji_width(_get_registry()["taco"])
        text_w = get_text_width(FONT_SMALL, " hi ", padding=0)
        assert measure_width(FONT_SMALL, ":taco: hi :taco:") == (
            taco_w + EMOJI_PADDING + text_w + EMOJI_PADDING + taco_w + EMOJI_PADDING
        )

    def test_draw_advance_matches_measured_width(self):
        """`draw_with_emoji` returns the same advance `measure_width`
        predicts. Drift between the two would put text at a different x
        than the layout math expects.
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import draw_with_emoji, measure_width

        canvas = _StubCanvas(width=160, height=16)
        text = "hi:taco: there:taco:"
        measured = measure_width(FONT_SMALL, text)
        advance = draw_with_emoji(
            canvas, FONT_SMALL, cursor_pos=0, y=8, color=(255, 255, 255), text=text
        )
        assert advance == measured

    def test_draw_emoji_at_unchanged_single_icon(self):
        """`draw_emoji_at` is the single-icon helper for widgets that
        position one icon at a known (x, y). It does NOT parse text
        and keeps the simple `sprite_w + EMOJI_PADDING` contract — no
        leading pad applies.
        """
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import EMOJI_PADDING, draw_emoji_at

        canvas = _StubCanvas(width=160, height=16)
        advance = draw_emoji_at(canvas, "taco", x=0, y=4)
        # Low-res taco is 14 wide.
        assert advance == 14 + EMOJI_PADDING

    def test_measure_emoji_at_unchanged_single_icon(self):
        """Mirror: `measure_emoji_at` keeps its single-icon contract."""
        from rgbmatrix import _StubCanvas

        from led_ticker.pixel_emoji import EMOJI_PADDING, measure_emoji_at

        canvas = _StubCanvas(width=160, height=16)
        assert measure_emoji_at(canvas, "taco") == 14 + EMOJI_PADDING

    def test_per_char_provider_advance_matches_measure(self):
        """The pre-pad must apply on the per-char ColorProvider path
        too. If a refactor moved the pre-pad inside `if not per_char:`,
        a per-char rainbow rendering of `:taco: HI :taco:` would
        return the wrong advance and `measure_width` would predict
        a different layout than `draw_with_emoji` paints. Tripwire
        for that drift.
        """
        from rgbmatrix import _StubCanvas
        from rgbmatrix.graphics import Color

        from led_ticker.pixel_emoji import draw_with_emoji, measure_width

        class _PerCharProvider:
            per_char = True

            def color_for(self, frame, char_index, total_chars):
                return Color(255, 255, 255)

        canvas = _StubCanvas(width=160, height=16)
        text = ":taco: HI :taco:"
        measured = measure_width(FONT_SMALL, text)
        advance = draw_with_emoji(
            canvas,
            FONT_SMALL,
            cursor_pos=0,
            y=8,
            color=_PerCharProvider(),
            text=text,
        )
        assert advance == measured

    def test_pride_love_pride_total_width_matches_symmetric_formula(self):
        """`:pride: LOVE :pride:` on a bigsign-equivalent ScaledCanvas:
        `measure_width` must return the symmetric-padded total
        `pride_w + PAD + text_w(' LOVE ') + PAD + pride_w + PAD`.

        Without the symmetric-pad fix, this would return
        `pride_w + PAD + text_w + pride_w + PAD` (one PAD short on
        the second emoji's left side) and the rendered LOVE would sit
        2 logical px closer to the trailing pride than to the leading
        pride.
        """
        from led_ticker.drawing import get_text_width
        from led_ticker.pixel_emoji import EMOJI_PADDING, HIRES_REGISTRY, measure_width
        from led_ticker.scaled_canvas import ScaledCanvas

        real = _bigsign_real_canvas()
        sc = ScaledCanvas(real, scale=4)
        text = ":pride: LOVE :pride:"
        pride_w = HIRES_REGISTRY["pride"].logical_width(scale=sc.scale)
        text_w = get_text_width(FONT_SMALL, " LOVE ", padding=0, canvas=sc)
        expected = (
            pride_w + EMOJI_PADDING + text_w + EMOJI_PADDING + pride_w + EMOJI_PADDING
        )
        assert measure_width(FONT_SMALL, text, canvas=sc) == expected


class TestHiresEmojiAtScale1Wrapper:
    """Documents behavior when _maybe_wrap produces a scale=1 ScaledCanvas.

    After the _maybe_wrap fix, ``_maybe_wrap(real, scale=1,
    content_height=16)`` wraps the canvas in a ScaledCanvas (instead of
    returning it unwrapped) when ``content_height < real.height``.  Because
    ``draw_emoji_at`` gates hi-res on ``isinstance(canvas, ScaledCanvas)``,
    this makes the hi-res path reachable at scale=1.

    **Documented behavior (not a bug):** ``_draw_hires_emoji`` paints at
    physical resolution, anchoring via ``iy_logical * scale +
    wrapper._y_offset``.  At scale=1, ``ix_logical * 1 + y_offset`` equals
    ``real_y_offset``.  A 32×32 sprite at logical y=0 therefore occupies
    real rows ``_y_offset .. _y_offset + 31``.  With a 64-px-tall panel and
    content_height=16, ``_y_offset = (64 - 16) // 2 = 24``, so the sprite
    lands at real rows 24..55.  The content-height band is rows 24..39 (16
    rows), meaning the bottom 16 rows of the sprite (real 40..55) sit BELOW
    the content band but still WITHIN the physical panel.  This is the
    same trade-off that exists at scale > 1; ``draw_with_emoji``'s
    ``max_emoji_height`` / ``sprite_logical_height`` cap in ``_row_layout``
    is the correct protection.  Calling ``draw_emoji_at`` directly bypasses
    that cap.
    """

    def _make_wrapped_scale1(self):
        """Build a 256×64 real canvas and wrap it at scale=1, content_height=16."""
        from rgbmatrix import _StubCanvas

        from led_ticker.scaled_canvas import ScaledCanvas

        real = _StubCanvas(width=256, height=64)
        # content_height=16 < real.height=64  →  _maybe_wrap would wrap
        wrapped = ScaledCanvas(real, scale=1, content_height=16)
        return real, wrapped

    def test_wrapper_properties(self):
        """Sanity: scale=1 wrapper with content_height=16 on a 64-px panel."""
        from led_ticker.scaled_canvas import ScaledCanvas

        real, wrapped = self._make_wrapped_scale1()

        assert isinstance(wrapped, ScaledCanvas)
        assert wrapped.scale == 1
        assert wrapped.content_height == 16
        # y_offset_real = (64 - 16 * 1) // 2 = 24
        assert wrapped.y_offset_real == 24
        # logical canvas height is content_height
        assert wrapped.height == 16

    def test_hires_path_fires_at_scale1(self):
        """draw_emoji_at takes the hi-res branch when canvas is a ScaledCanvas,
        even at scale=1.  The hi-res sprite's lit pixels span ~32 real rows,
        not the ~8 rows of the lo-res fallback.
        """
        from led_ticker.pixel_emoji import draw_emoji_at

        real, wrapped = self._make_wrapped_scale1()

        draw_emoji_at(wrapped, "instagram", 0, 0)

        ys = {y for (x, y), rgb in real._pixels.items() if rgb != (0, 0, 0)}
        assert len(ys) > 0, "no pixels were painted"

        y_span = max(ys) - min(ys) + 1
        # hi-res 32×32 sprite ⇒ span ≈ 32; lo-res 8×8 ⇒ span ≈ 8
        assert y_span > 8, (
            f"y_span={y_span} is too small to be a 32×32 hires sprite; "
            "the hi-res path may not have fired"
        )

    def test_hires_y_placement_documents_overflow(self):
        """Documents the y-coordinate placement of the sprite and the fact
        that it overflows the content_height=16 band.

        With _y_offset=24 and scale=1, a 32×32 sprite at logical y=0
        occupies real rows 24..55.  The content band is rows 24..39.
        Rows 40..55 are on-panel but outside the content region.
        """
        from led_ticker.pixel_emoji import draw_emoji_at

        real, wrapped = self._make_wrapped_scale1()
        # _y_offset == 24 (asserted in test_wrapper_properties)

        draw_emoji_at(wrapped, "instagram", 0, 0)

        lit_ys = {y for (x, y), rgb in real._pixels.items() if rgb != (0, 0, 0)}

        # Sprite should start at or near row 24 (the _y_offset)
        assert (
            min(lit_ys) >= 24
        ), f"Sprite painted above _y_offset: min real y={min(lit_ys)}, expected >= 24"
        # Sprite should extend to around row 55 (24 + 32 - 1)
        assert max(lit_ys) >= 40, (
            f"Sprite top row={max(lit_ys)} expected >= 40; "
            "it should overflow the content_height=16 band (rows 24..39)"
        )
        # The sprite stays within the physical panel (rows 0..63)
        assert (
            max(lit_ys) < 64
        ), f"Sprite painted off-panel: max real y={max(lit_ys)} >= 64"

    def test_hires_advance_at_scale1(self):
        """draw_emoji_at returns the expected logical advance at scale=1.

        At scale=1 the logical_width equals the physical_width (32 for
        instagram) and the advance is logical_width + EMOJI_PADDING.
        """
        from led_ticker.pixel_emoji import EMOJI_PADDING, HIRES_REGISTRY, draw_emoji_at

        _, wrapped = self._make_wrapped_scale1()
        advance = draw_emoji_at(wrapped, "instagram", 0, 0)

        expected_logical_w = HIRES_REGISTRY["instagram"].logical_width(scale=1)
        assert advance == expected_logical_w + EMOJI_PADDING

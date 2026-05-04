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
    from led_ticker.pixel_emoji import HIRES_REGISTRY, MOON_HIRES

    assert "moon" in HIRES_REGISTRY
    assert HIRES_REGISTRY["moon"] is MOON_HIRES
    assert MOON_HIRES.physical_size == 32


def test_hires_moon_logical_width_matches_lowres():
    """The crescent moon's lit pixels only span 19 of 32 cols, so its
    `physical_width` is set to 20 (matching the low-res's 5-col
    footprint at scale=4) — otherwise the empty cols 20-31 would
    consume logical-width and create a visible gap to the next emoji
    in inline rows.
    """
    from led_ticker.pixel_emoji import MOON_HIRES

    assert MOON_HIRES.logical_width(scale=4) == 5
    assert MOON_HIRES.logical_width(scale=2) == 10
    assert MOON_HIRES.physical_size == 32  # full canvas height preserved


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

    draw_with_emoji(
        sc, FONT_SMALL, cursor_pos=0, y=8, color=(255, 255, 255), text=":moon:"
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

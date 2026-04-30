"""Smoke tests for pixel_emoji rendering on ScaledCanvas.

Ensures the bigsign path renders inline emoji + text correctly: emoji
SetPixel calls and text draw_text calls both work through the wrapper.
"""

from __future__ import annotations

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

"""Tests for the StillImage widget — single-image counterpart to GifPlayer.

Mirrors test_gif.py's structure: load + decode + draw + paint helpers,
plus full coverage of the text-overlay variants (left/right/scroll/
scroll_over), text_valign, scroll_direction, validation, and the
hold_seconds duration path.
"""

from __future__ import annotations

import pytest
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color

from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.widgets.still import StillImage


def _make_png(tmp_path, color=(200, 30, 40), size=(32, 32), name="img.png", alpha=None):
    """Build a tiny PNG. If `alpha` (int 0..255) is given, the image is
    saved as RGBA with that alpha value everywhere."""
    if alpha is not None:
        img = Image.new("RGBA", size, color=(*color, alpha))
    else:
        img = Image.new("RGB", size, color=color)
    p = tmp_path / name
    img.save(p, format="PNG")
    return p


def _make_jpg(tmp_path, color=(140, 90, 60), size=(64, 32), name="img.jpg"):
    img = Image.new("RGB", size, color=color)
    p = tmp_path / name
    img.save(p, format="JPEG")
    return p


def _bigsign_real_canvas():
    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


# ---------------------------------------------------------------------------
# Decode + draw basics
# ---------------------------------------------------------------------------


def test_load_decodes_lazily(tmp_path):
    path = _make_png(tmp_path)
    widget = StillImage(path=str(path), fit="stretch")
    assert widget._pixels == b""  # not loaded yet
    widget._load(panel_w=256, panel_h=64)
    assert len(widget._pixels) == 256 * 64 * 3
    # Idempotent
    widget._load(panel_w=256, panel_h=64)
    assert len(widget._pixels) == 256 * 64 * 3


def test_draw_paints_to_real_canvas(tmp_path):
    path = _make_png(tmp_path, color=(200, 30, 40))
    widget = StillImage(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()

    canvas, advance = widget.draw(real, cursor_pos=0)

    assert advance == real.width
    assert real.get_pixel(0, 0) == (200, 30, 40)
    assert real.get_pixel(real.width - 1, real.height - 1) == (200, 30, 40)


def test_draw_unwraps_scaled_canvas(tmp_path):
    """ScaledCanvas wrapper must be bypassed so the image paints at
    native physical resolution, not as scale×scale blocks."""
    path = _make_png(tmp_path, color=(255, 255, 0))
    widget = StillImage(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)

    canvas, advance = widget.draw(sc, cursor_pos=0)

    assert advance == sc.width
    # Pixel at col 1 (NOT divisible by scale=4) should be lit, proving
    # the wrapper was bypassed.
    assert real.get_pixel(1, 1) != (0, 0, 0)


def test_jpg_loads(tmp_path):
    path = _make_jpg(tmp_path, color=(140, 90, 60))
    widget = StillImage(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    widget.draw(real, cursor_pos=0)
    # JPEG compression tweaks colors slightly; just assert non-black
    r, g, b = real.get_pixel(128, 32)
    assert (r, g, b) != (0, 0, 0)


def test_missing_file_raises(tmp_path):
    widget = StillImage(path=str(tmp_path / "nope.png"), fit="stretch")
    with pytest.raises(FileNotFoundError):
        widget._load(panel_w=256, panel_h=64)


# ---------------------------------------------------------------------------
# Transparent PNG handling
# ---------------------------------------------------------------------------


def test_alpha_zero_pixels_become_black(tmp_path):
    """Fully-transparent RGBA pixels (alpha=0) must composite onto
    black so the existing skip-black scroll path treats them as
    skip-zones."""
    # 32×32 image with alpha=0 — rgb values are red but alpha makes
    # them transparent; the decoder should emit black at every pixel.
    path = _make_png(tmp_path, color=(255, 0, 0), alpha=0)
    widget = StillImage(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    widget.draw(real, cursor_pos=0)
    # Every pixel should be black (transparent areas)
    for x in (0, 64, 128, 200, 255):
        for y in (0, 16, 32, 48, 63):
            assert real.get_pixel(x, y) == (0, 0, 0)


def test_alpha_full_pixels_paint_normally(tmp_path):
    """Fully-opaque RGBA pixels (alpha=255) paint at their RGB color."""
    path = _make_png(tmp_path, color=(0, 200, 100), alpha=255)
    widget = StillImage(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    widget.draw(real, cursor_pos=0)
    assert real.get_pixel(128, 32) == (0, 200, 100)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_text_align_raises(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_align"):
        StillImage(path=str(path), text="hi", text_align="bogus")


def test_invalid_gif_align_raises(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="gif_align"):
        StillImage(path=str(path), gif_align="bogus")


def test_invalid_text_valign_raises(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_valign"):
        StillImage(path=str(path), text_valign="middle")


def test_invalid_scroll_direction_raises(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="scroll_direction"):
        StillImage(path=str(path), scroll_direction="up")


def test_negative_numerics_raise(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_scale"):
        StillImage(path=str(path), text_scale=0)
    with pytest.raises(ValueError, match="text_loops"):
        StillImage(path=str(path), text_loops=-1)
    with pytest.raises(ValueError, match="scroll_speed_ms"):
        StillImage(path=str(path), scroll_speed_ms=10)
    with pytest.raises(ValueError, match="hold_seconds"):
        StillImage(path=str(path), hold_seconds=-1.0)


def test_text_loops_with_static_text_raises(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_loops"):
        StillImage(path=str(path), text="X", text_align="right", text_loops=10)


# ---------------------------------------------------------------------------
# text_align "auto" resolution
# ---------------------------------------------------------------------------


def test_text_align_auto_resolves_from_gif_align(tmp_path):
    path = _make_png(tmp_path)
    assert StillImage(path=str(path), text="HI").text_align == "scroll_over"
    assert StillImage(path=str(path), text="HI", gif_align="left").text_align == "right"
    assert StillImage(path=str(path), text="HI", gif_align="right").text_align == "left"


# ---------------------------------------------------------------------------
# play() — no text vs with text
# ---------------------------------------------------------------------------


async def test_play_no_text_holds_for_hold_seconds(tmp_path, mocker):
    """Without text: paint once, swap, then sleep for hold_seconds."""
    path = _make_png(tmp_path, color=(50, 100, 150))
    widget = StillImage(path=str(path), fit="stretch", hold_seconds=2.0)
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame)

    # One swap (paint + display)
    assert frame.matrix.SwapOnVSync.call_count == 1
    # One sleep call for hold_seconds
    sleeps = [c.args[0] for c in sleep_mock.await_args_list]
    assert sleeps == [2.0]
    # Image was painted
    assert real.get_pixel(128, 32) == (50, 100, 150)


async def test_play_with_text_runs_scroll_loop(tmp_path, mocker):
    """With text scrolling: per-tick loop for hold_seconds duration."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
        hold_seconds=1.0,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame)

    # 1.0s / 50ms tick = 20 ticks → 20 swaps
    assert frame.matrix.SwapOnVSync.call_count == 20


async def test_play_with_text_text_loops_extends_duration(tmp_path, mocker):
    """text_loops floor extends the section past hold_seconds when needed."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll",
        scroll_speed_ms=50,
        hold_seconds=0.5,  # 10 ticks; would dominate without text_loops
        text_loops=2,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame)

    # text_w=256, text_width("X")=6 → traversal = 262 ticks; ×2 = 524
    # Tight bound (524..525) catches both undercounting and overcounting.
    assert 524 <= frame.matrix.SwapOnVSync.call_count <= 525


async def test_scroll_direction_right_advances_positively(tmp_path, mocker):
    """scroll_direction="right" mirrors the default — text starts off
    the LEFT edge and moves rightward."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll",
        scroll_speed_ms=50,
        hold_seconds=0.5,
        scroll_direction="right",
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    real_draw = __import__("led_ticker.widgets.still", fromlist=["draw_text"]).draw_text
    mocker.patch(
        "led_ticker.widgets.still.draw_text",
        side_effect=lambda c, f, x, y, col, t: (
            seen_x.append(x) or real_draw(c, f, x, y, col, t)
        ),
    )

    await widget.play(real, frame)

    assert seen_x[0] < 0  # starts off the left edge
    assert seen_x[1] == seen_x[0] + 1


@pytest.mark.parametrize(
    "valign,h,expected_baseline",
    [
        ("top", 64, 10),
        ("center", 64, 36),
        ("bottom", 64, 62),
        ("center", 16, 12),
        ("top", 16, 10),
        ("bottom", 16, 14),
    ],
)
def test_baseline_y_honors_text_valign(tmp_path, valign, h, expected_baseline):
    path = _make_png(tmp_path)
    widget = StillImage(path=str(path), text_valign=valign)
    assert widget._baseline_y(h) == expected_baseline


@pytest.mark.parametrize(
    "valign,offset,h,expected",
    [
        ("top", -3, 64, 7),  # shift caps up by 3 logical pixels
        ("top", 4, 64, 14),  # shift down 4
        ("center", 0, 64, 36),  # no-op
        ("bottom", -10, 64, 52),  # nudge up from bottom edge
    ],
)
def test_text_y_offset_shifts_baseline(tmp_path, valign, offset, h, expected):
    path = _make_png(tmp_path)
    widget = StillImage(path=str(path), text_valign=valign, text_y_offset=offset)
    assert widget._baseline_y(h) == expected


async def test_top_valign_paints_at_panel_top_with_text_scale_2(tmp_path, mocker):
    """At text_scale=2 with text_valign='top', the wrapper now uses
    content_height = panel_h // scale (so it spans the full panel) —
    text paints at the panel's TOP edge, not 16 rows down where a
    letterboxed sub-region used to start."""
    from led_ticker.scaled_canvas import ScaledCanvas

    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="right",
        text_valign="top",
        text_scale=2,
        hold_seconds=0.05,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_canvases: list[object] = []
    seen_y: list[int] = []
    mocker.patch(
        "led_ticker.widgets.still.draw_text",
        side_effect=lambda c, f, x, y, col, t: (
            seen_canvases.append(c) or seen_y.append(y) or 12
        ),
    )

    await widget.play(real, frame)

    # Wrapper spans the full panel: content_height = 64 // 2 = 32
    assert seen_canvases
    assert isinstance(seen_canvases[0], ScaledCanvas)
    assert seen_canvases[0].height == 32  # logical, was 16 (letterboxed) before
    # Top valign at h=32 → baseline = 10 (logical) → physical row 20.
    # Cell top at logical y=0 → physical y=0 (panel top edge).
    assert seen_y[0] == 10


async def test_emoji_routes_through_emoji_painter(tmp_path, mocker):
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text=":sun: hot",
        text_align="right",
        font_color=Color(255, 220, 50),
        hold_seconds=0.1,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    spy = mocker.patch(
        "led_ticker.pixel_emoji.draw_with_emoji",
        side_effect=lambda c, *a, **kw: 16,
    )

    await widget.play(real, frame)
    assert spy.called


async def test_text_scale_uses_scaled_canvas(tmp_path, mocker):
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="HI",
        text_align="right",
        text_scale=2,
        hold_seconds=0.1,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_canvases: list[object] = []
    mocker.patch(
        "led_ticker.widgets.still.draw_text",
        side_effect=lambda c, *a, **kw: seen_canvases.append(c) or 12,
    )

    await widget.play(real, frame)

    assert seen_canvases
    assert all(isinstance(c, ScaledCanvas) and c.scale == 2 for c in seen_canvases)


async def test_text_canvas_follows_back_buffer(tmp_path, mocker):
    """Regression: with text_scale=1 (no wrapper) the text canvas
    reference must follow each SwapOnVSync return — otherwise text
    paints to the front buffer every other tick → pulsing flicker.
    Same bug pattern that bit GifPlayer."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="right",
        scroll_speed_ms=50,
        hold_seconds=0.15,  # ~3 ticks
    )
    real = _bigsign_real_canvas()

    swap_returns: list[object] = []

    def fake_swap(c):
        new = type(real)(width=real.width, height=real.height)
        swap_returns.append(new)
        return new

    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = fake_swap
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen: list[object] = []
    mocker.patch(
        "led_ticker.widgets.still.draw_text",
        side_effect=lambda c, *a, **kw: seen.append(c) or 6,
    )

    await widget.play(real, frame)

    assert len(seen) >= 3
    assert seen[0] is real
    for i, c in enumerate(seen[1:], start=1):
        assert c is swap_returns[i - 1]


# ---------------------------------------------------------------------------
# Real test asset smoke tests (uses the actual files in config/assets/)
# ---------------------------------------------------------------------------


def test_transparent_test_asset_decodes_to_black_corners():
    """moon-transparent.png has alpha=0 corners. After decode, those
    corners should be (0, 0, 0)."""
    from pathlib import Path

    asset = Path("config/assets/moon-transparent.png")
    if not asset.exists():
        pytest.skip("test asset missing")

    widget = StillImage(path=str(asset), fit="pillarbox")
    real = _bigsign_real_canvas()
    widget.draw(real, cursor_pos=0)

    # Top-left and bottom-right corners are well outside the moon
    assert real.get_pixel(0, 0) == (0, 0, 0)
    assert real.get_pixel(255, 63) == (0, 0, 0)


def test_opaque_jpg_test_asset_fills_panel():
    """heart-tunnel-opaque.jpg has no transparency; stretch fills the
    panel with non-black pixels."""
    from pathlib import Path

    asset = Path("config/assets/heart-tunnel-opaque.jpg")
    if not asset.exists():
        pytest.skip("test asset missing")

    widget = StillImage(path=str(asset), fit="stretch")
    real = _bigsign_real_canvas()
    widget.draw(real, cursor_pos=0)

    # Sample a handful — none should be pure black
    for x, y in [(0, 0), (128, 32), (255, 63), (50, 50)]:
        assert real.get_pixel(x, y) != (0, 0, 0), f"({x},{y}) was black"

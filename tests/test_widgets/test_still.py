"""Tests for the StillImage widget — single-image counterpart to GifPlayer.

Mirrors test_gif.py's structure: load + decode + draw + paint helpers,
plus full coverage of the text-overlay variants (left/right/scroll/
scroll_over), text_valign, scroll_direction, validation, and the
hold_time duration path.
"""

from __future__ import annotations

import pytest
from PIL import Image
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


def test_draw_paints_to_real_canvas(tmp_path, bigsign_canvas):
    path = _make_png(tmp_path, color=(200, 30, 40))
    widget = StillImage(path=str(path), fit="stretch")
    real = bigsign_canvas

    canvas, advance = widget.draw(real, cursor_pos=0)

    assert advance == real.width
    assert real.get_pixel(0, 0) == (200, 30, 40)
    assert real.get_pixel(real.width - 1, real.height - 1) == (200, 30, 40)


def test_draw_unwraps_scaled_canvas(tmp_path, bigsign_canvas):
    """ScaledCanvas wrapper must be bypassed so the image paints at
    native physical resolution, not as scale×scale blocks."""
    path = _make_png(tmp_path, color=(255, 255, 0))
    widget = StillImage(path=str(path), fit="stretch")
    real = bigsign_canvas
    sc = ScaledCanvas(real, scale=4)

    canvas, advance = widget.draw(sc, cursor_pos=0)

    assert advance == sc.width
    # Pixel at col 1 (NOT divisible by scale=4) should be lit, proving
    # the wrapper was bypassed.
    assert real.get_pixel(1, 1) != (0, 0, 0)


def test_jpg_loads(tmp_path, bigsign_canvas):
    path = _make_jpg(tmp_path, color=(140, 90, 60))
    widget = StillImage(path=str(path), fit="stretch")
    real = bigsign_canvas
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


def test_alpha_zero_pixels_become_black(tmp_path, bigsign_canvas):
    """Fully-transparent RGBA pixels (alpha=0) must composite onto
    black so the existing skip-black scroll path treats them as
    skip-zones."""
    # 32×32 image with alpha=0 — rgb values are red but alpha makes
    # them transparent; the decoder should emit black at every pixel.
    path = _make_png(tmp_path, color=(255, 0, 0), alpha=0)
    widget = StillImage(path=str(path), fit="stretch")
    real = bigsign_canvas
    widget.draw(real, cursor_pos=0)
    # Every pixel should be black (transparent areas)
    for x in (0, 64, 128, 200, 255):
        for y in (0, 16, 32, 48, 63):
            assert real.get_pixel(x, y) == (0, 0, 0)


def test_alpha_full_pixels_paint_normally(tmp_path, bigsign_canvas):
    """Fully-opaque RGBA pixels (alpha=255) paint at their RGB color."""
    path = _make_png(tmp_path, color=(0, 200, 100), alpha=255)
    widget = StillImage(path=str(path), fit="stretch")
    real = bigsign_canvas
    widget.draw(real, cursor_pos=0)
    assert real.get_pixel(128, 32) == (0, 200, 100)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_text_align_raises(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_align"):
        StillImage(path=str(path), text="hi", text_align="bogus")


def test_invalid_image_align_raises(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="image_align"):
        StillImage(path=str(path), image_align="bogus")


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
    with pytest.raises(ValueError, match="text_loops"):
        StillImage(path=str(path), text_loops=-1)
    with pytest.raises(ValueError, match="scroll_speed_ms"):
        StillImage(path=str(path), scroll_speed_ms=10)
    with pytest.raises(ValueError, match="hold_time"):
        StillImage(path=str(path), hold_time=-1.0)


def test_text_loops_with_static_text_raises(tmp_path):
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_loops"):
        StillImage(path=str(path), text="X", text_align="right", text_loops=10)


# ---------------------------------------------------------------------------
# text_align "auto" resolution
# ---------------------------------------------------------------------------


def test_text_align_auto_resolves_from_image_align(tmp_path):
    path = _make_png(tmp_path)
    assert StillImage(path=str(path), text="HI").text_align == "scroll_over"
    assert (
        StillImage(path=str(path), text="HI", image_align="left").text_align == "right"
    )
    assert (
        StillImage(path=str(path), text="HI", image_align="right").text_align == "left"
    )


# ---------------------------------------------------------------------------
# play() — no text vs with text
# ---------------------------------------------------------------------------


async def test_play_no_text_holds_for_hold_time(tmp_path, mocker, bigsign_canvas):
    """Without text: paint once, swap, then sleep for hold_time."""
    path = _make_png(tmp_path, color=(50, 100, 150))
    widget = StillImage(path=str(path), fit="stretch", hold_time=2.0)
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame)

    # One swap (paint + display)
    assert frame.swap.call_count == 1
    # One sleep call for hold_time
    sleeps = [c.args[0] for c in sleep_mock.await_args_list]
    assert sleeps == [2.0]
    # Image was painted
    assert real.get_pixel(128, 32) == (50, 100, 150)


async def test_play_with_text_runs_scroll_loop(tmp_path, mocker, bigsign_canvas):
    """With text scrolling: per-tick loop for at least one full marquee
    traversal. hold_time sets a minimum, but the auto-floor (for
    text_loops=0) ensures the marquee doesn't get truncated mid-pass.
    """
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
        hold_time=1.0,
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame)

    # 1.0s / 50ms tick = 20 ticks natural — but the auto-floor extends
    # to at least one full marquee pass: text_w (256) + text_width
    # (~6 for "X") = 262 ticks.
    one_traversal = 256 + 6
    count = frame.swap.call_count
    assert one_traversal <= count < 2 * one_traversal


async def test_play_with_text_text_loops_extends_duration(
    tmp_path, mocker, bigsign_canvas
):
    """text_loops floor extends the section past hold_time when needed."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
        hold_time=0.5,  # 10 ticks; would dominate without text_loops
        text_loops=2,
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame)

    # text_w=256, text_width("X")=6 → 1 traversal ≈ 262 ticks. With
    # text_loops=2 the floor is ≥ 2 traversals, < 3. Bounds avoid
    # pinning the exact formula (lets implementation tweak the
    # traversal definition if needed).
    one_traversal = 256 + 6
    count = frame.swap.call_count
    assert 2 * one_traversal <= count < 3 * one_traversal


async def test_scroll_direction_right_advances_positively(
    tmp_path, mocker, bigsign_canvas
):
    """scroll_direction="right" mirrors the default — text starts off
    the LEFT edge and moves rightward."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
        hold_time=0.5,
        scroll_direction="right",
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    real_draw = __import__(
        "led_ticker.widgets._image_base", fromlist=["draw_text"]
    ).draw_text
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
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
    from types import SimpleNamespace

    path = _make_png(tmp_path)
    widget = StillImage(path=str(path), text_valign=valign)
    canvas = SimpleNamespace(height=h, scale=1)
    assert widget._baseline_y(canvas) == expected_baseline


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
    from types import SimpleNamespace

    path = _make_png(tmp_path)
    widget = StillImage(path=str(path), text_valign=valign, text_y_offset=offset)
    canvas = SimpleNamespace(height=h, scale=1)
    assert widget._baseline_y(canvas) == expected


@pytest.mark.parametrize(
    "align,offset,expected_x",
    [
        ("left", 0, 2),  # default: 2-px gap from left edge
        ("left", 10, 12),  # shifted right by 10
        ("left", -2, 0),  # shifted hard against left edge
        ("right", 0, 256 - 6 - 2),  # 256 - text_width(6) - 2
        ("right", -10, 256 - 6 - 2 - 10),  # shifted left from right edge
        ("right", 5, 256 - 6 - 2 + 5),  # shifted past default into edge
    ],
)
async def test_text_x_offset_shifts_static_text(
    tmp_path, mocker, align, offset, expected_x, bigsign_canvas
):
    """text_x_offset adds to whatever text_align computes — extends the
    valign-style adjustment to the horizontal axis. No-op for scrolling
    text (covered separately)."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",  # 6-px wide in stub font
        text_align=align,
        text_x_offset=offset,
        hold_time=0.05,
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen_x.append(x) or 6,
    )

    await widget.play(real, frame)

    assert seen_x[0] == expected_x


def test_text_x_offset_with_scroll_raises(tmp_path):
    """text_x_offset is a static-text knob — using it with scrolling
    raises so the user notices their offset isn't being honored."""
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_x_offset"):
        StillImage(
            path=str(path),
            fit="stretch",
            text="X",
            text_align="scroll_over",
            text_x_offset=99,
        )


async def test_top_valign_paints_at_panel_top_when_wrapped(
    tmp_path, mocker, bigsign_canvas
):
    """With text_valign='top' (and smart-default wrap scale on bigsign),
    the wrapper uses content_height = panel_h // scale so it spans the
    full panel — text paints at the panel's TOP edge, not letterboxed."""
    from led_ticker.scaled_canvas import ScaledCanvas

    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="right",
        text_valign="top",
        hold_time=0.05,
    )
    widget._logical_scale = 4  # Simulate bigsign
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_canvases: list[object] = []
    seen_y: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: (
            seen_canvases.append(c) or seen_y.append(y) or 12
        ),
    )

    await widget.play(real, frame)

    # Behavioral assertion (decoupled from the exact content_height
    # implementation): the wrapper spans the FULL panel height — no
    # letterbox sub-region — so the top of the logical canvas IS the
    # top of the physical panel.
    assert seen_canvases
    assert isinstance(seen_canvases[0], ScaledCanvas)
    assert seen_canvases[0].height * seen_canvases[0].scale == real.height
    # Top valign at top of canvas → baseline 10 (BDF ascent) → cell top
    # at logical y=0 → physical y=0 (panel top edge).
    assert seen_y[0] == 10


async def test_emoji_routes_through_emoji_painter(tmp_path, mocker, bigsign_canvas):
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text=":sun: hot",
        text_align="right",
        font_color=Color(255, 220, 50),
        hold_time=0.1,
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    spy = mocker.patch(
        "led_ticker.pixel_emoji.draw_with_emoji",
        side_effect=lambda c, *a, **kw: 16,
    )

    await widget.play(real, frame)
    assert spy.called


async def test_wrap_uses_scaled_canvas(tmp_path, mocker, bigsign_canvas):
    """Text wraps at smart default _logical_scale on bigsign (no
    explicit font_size). Ensures emoji gate fires for hires sprites."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="HI",
        text_align="right",
        hold_time=0.1,
    )
    widget._logical_scale = 4  # Simulate bigsign
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_canvases: list[object] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, *a, **kw: seen_canvases.append(c) or 12,
    )

    await widget.play(real, frame)

    assert seen_canvases
    assert all(isinstance(c, ScaledCanvas) and c.scale == 4 for c in seen_canvases)


async def test_text_canvas_follows_back_buffer(tmp_path, mocker, bigsign_canvas):
    """Regression: with text_scale=1 (no wrapper) the text canvas
    reference must follow each SwapOnVSync return — otherwise text
    paints to the front buffer every other tick → pulsing flicker.
    Same bug pattern that bit GifPlayer."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        # scroll_over keeps the per-tick loop active so the rebind
        # path is exercised. Static text fast-paths to a single paint.
        text_align="scroll_over",
        scroll_speed_ms=50,
        hold_time=0.15,  # ~3 ticks
    )
    real = bigsign_canvas

    swap_returns: list[object] = []

    def fake_swap(c):
        new = type(real)(width=real.width, height=real.height)
        swap_returns.append(new)
        return new

    frame = mocker.MagicMock()
    frame.swap.side_effect = fake_swap
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen: list[object] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
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


def _real_asset(name: str):
    """Return path to a real config/assets/ file. Fails the test loudly
    if missing — these assets are committed to the repo, so absence
    means a regression in repository state, not a "skip" condition.
    Set ``LED_TICKER_SKIP_REAL_ASSETS=1`` to skip in environments
    that genuinely don't ship assets (rare)."""
    import os
    from pathlib import Path

    asset = Path("config/assets") / name
    if asset.exists():
        return asset
    if os.environ.get("LED_TICKER_SKIP_REAL_ASSETS"):
        pytest.skip(f"asset {name} missing and skip env set")
    pytest.fail(
        f"real test asset config/assets/{name} is missing; commit it "
        f"or set LED_TICKER_SKIP_REAL_ASSETS=1 to skip these checks"
    )


def test_transparent_test_asset_decodes_to_black_corners(bigsign_canvas):
    """moon-transparent.png has alpha=0 corners. After decode, those
    corners should be (0, 0, 0)."""
    asset = _real_asset("moon-transparent.png")

    widget = StillImage(path=str(asset), fit="pillarbox")
    real = bigsign_canvas
    widget.draw(real, cursor_pos=0)

    # Top-left and bottom-right corners are well outside the moon
    assert real.get_pixel(0, 0) == (0, 0, 0)
    assert real.get_pixel(255, 63) == (0, 0, 0)


def test_opaque_jpg_test_asset_fills_panel(bigsign_canvas):
    """heart-tunnel-opaque.jpg has no transparency; stretch fills the
    panel with non-black pixels."""
    asset = _real_asset("heart-tunnel-opaque.jpg")

    widget = StillImage(path=str(asset), fit="stretch")
    real = bigsign_canvas
    widget.draw(real, cursor_pos=0)

    # Sample a handful — none should be pure black
    for x, y in [(0, 0), (128, 32), (255, 63), (50, 50)]:
        assert real.get_pixel(x, y) != (0, 0, 0), f"({x},{y}) was black"


# ---------------------------------------------------------------------------
# Review-driven additions: missing test coverage from the still-image
# pre-merge audit (docs/superpowers/plans/2026-05-02-still-image-review-findings.md)
# ---------------------------------------------------------------------------


async def test_play_no_text_captures_swap_return(tmp_path, mocker, bigsign_canvas):
    """Hardware constraint #1: SwapOnVSync return must be captured.
    Uses a fresh-canvas-per-swap fake so a regression that drops the
    capture (e.g. `frame.swap(canvas)` without the
    assignment) would surface — the returned canvas wouldn't match
    the latest swap return."""
    path = _make_png(tmp_path, color=(50, 100, 150))
    widget = StillImage(path=str(path), fit="stretch", hold_time=0.05)
    real = bigsign_canvas

    swap_returns: list[object] = []

    def fake_swap(c):
        new = type(real)(width=real.width, height=real.height)
        swap_returns.append(new)
        return new

    frame = mocker.MagicMock()
    frame.swap.side_effect = fake_swap
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    result = await widget.play(real, frame)

    # play() returned the canvas the swap gave back, not the original
    assert result is swap_returns[-1]
    assert result is not real


def test_load_re_decodes_when_panel_size_changes(tmp_path):
    """A widget reused across sections of different panel sizes
    re-decodes on size change. Without this, the second size silently
    serves stale bytes from the first decode."""
    path = _make_png(tmp_path, color=(100, 50, 200))
    widget = StillImage(path=str(path), fit="stretch")

    widget._load(panel_w=256, panel_h=64)
    first = widget._pixels
    assert len(first) == 256 * 64 * 3

    # Same dims → no-op (idempotent)
    widget._load(panel_w=256, panel_h=64)
    assert widget._pixels is first

    # Different dims → re-decode
    widget._load(panel_w=160, panel_h=16)
    assert len(widget._pixels) == 160 * 16 * 3
    assert widget._pixels is not first


async def test_hold_time_zero_raises(tmp_path):
    """hold_time < 0.05 (the floor) should raise; semantics of
    instant flash are surprising."""
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="hold_time"):
        StillImage(path=str(path), hold_time=0.0)
    with pytest.raises(ValueError, match="hold_time"):
        StillImage(path=str(path), hold_time=0.04)
    # Exactly the floor is fine
    StillImage(path=str(path), hold_time=0.05)


async def test_scroll_direction_left_initial_position(tmp_path, mocker, bigsign_canvas):
    """Default scroll_direction='left' starts text at scroll_pos=text_w
    (off-right edge) — symmetric counterpart to the right-direction test."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",  # avoid scroll+stretch validator
        scroll_speed_ms=50,
        hold_time=0.15,
        # scroll_direction defaults to "left"
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen_x.append(x) or 6,
    )

    await widget.play(real, frame)

    # First tick: scroll_pos = panel width (256) — off the right edge
    assert seen_x[0] == 256
    # Each tick decrements by 1
    assert seen_x[1] == 255


async def test_scroll_wrap_around_left_direction(tmp_path, mocker, bigsign_canvas):
    """When text fully exits left, scroll_pos resets to text_w. Off-by-one
    in the wrap condition (`<=` vs `<`) ships green without this test."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="pillarbox",  # avoid scroll+stretch validator (use scroll mode)
        text="X",
        text_align="scroll",
        scroll_speed_ms=50,
        hold_time=0.05,
        text_loops=2,  # forces enough ticks to see a wrap
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen_x.append(x) or 6,
    )

    await widget.play(real, frame)

    # Sequence must contain at least one upward jump (the wrap reset).
    increases = [i for i in range(1, len(seen_x)) if seen_x[i] > seen_x[i - 1]]
    assert increases, (
        f"scroll_pos never wrapped back to text_w; saw {len(seen_x)} ticks "
        f"with min={min(seen_x)} max={max(seen_x)}"
    )
    # On the wrap, scroll_pos resets to exactly text_w (256)
    assert seen_x[increases[0]] == 256


async def test_scroll_wrap_around_right_direction(tmp_path, mocker, bigsign_canvas):
    """Mirror of the left-direction wrap test for scroll_direction='right'."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="pillarbox",
        text="X",
        text_align="scroll",
        scroll_direction="right",
        scroll_speed_ms=50,
        hold_time=0.05,
        text_loops=2,
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen_x.append(x) or 6,
    )

    await widget.play(real, frame)

    # For "right" direction, the wrap is a downward jump (back to -text_width).
    decreases = [i for i in range(1, len(seen_x)) if seen_x[i] < seen_x[i - 1]]
    assert decreases, "scroll_pos never wrapped"
    # On the wrap, scroll_pos resets to -text_width (-6 for "X")
    assert seen_x[decreases[0]] == -6


def test_image_align_noop_on_full_width_fits(tmp_path):
    """For stretch / crop, the scaled image always fills the panel
    width — image_align has no slack to act on, so the output bytes
    must be identical across left/center/right values. Pinned via
    direct byte comparison so a regression that wires image_align
    into stretch/crop incorrectly would fail loudly."""
    from led_ticker.widgets.still import _decode_still

    path = _make_png(tmp_path, color=(180, 100, 50), size=(64, 32))
    for fit in ("stretch", "crop"):
        a = _decode_still(path, 256, 64, fit, image_align="left")
        b = _decode_still(path, 256, 64, fit, image_align="center")
        c = _decode_still(path, 256, 64, fit, image_align="right")
        assert a == b == c, f"image_align affected {fit} output"


async def test_text_x_offset_combined_with_text_y_offset(
    tmp_path, mocker, bigsign_canvas
):
    """text_x_offset and text_y_offset must be orthogonal — applying
    one shouldn't affect the other."""
    path = _make_png(tmp_path)
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="right",
        text_valign="top",
        text_x_offset=10,
        text_y_offset=-3,
        hold_time=0.05,
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen: list[tuple[int, int]] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen.append((x, y)) or 6,
    )

    await widget.play(real, frame)

    # text_align="right", text_w=256, text_width=6 → base_x = 248; +10 → 258
    # text_valign="top" → baseline = 10; text_y_offset=-3 → 7
    assert seen[0] == (258, 7)


def test_decode_still_uses_frame_zero_of_animated_source(tmp_path):
    """For multi-frame sources, decode_still should return frame 0.
    (PIL's default is also frame 0, so this is a behavioral check —
    if a regression replaced `seek(0)` with `seek(1)` or removed the
    n_frames guard wrongly, the output would differ.)"""
    import io

    from led_ticker.widgets.still import _decode_still

    img1 = Image.new("RGB", (32, 32), color=(220, 30, 30))  # red
    img2 = Image.new("RGB", (32, 32), color=(30, 200, 30))  # green
    buf = io.BytesIO()
    img1.save(buf, format="GIF", save_all=True, append_images=[img2], duration=100)
    p = tmp_path / "anim.gif"
    p.write_bytes(buf.getvalue())

    pixels = _decode_still(
        p, panel_w=256, panel_h=64, fit="stretch", image_align="center"
    )
    # First pixel should be red (frame 0), not green (frame 1)
    r, g, b = pixels[0], pixels[1], pixels[2]
    assert r > 200 and g < 100, f"expected red frame-0, got ({r},{g},{b})"


async def test_font_too_large_raises_at_first_paint(tmp_path, mocker, bigsign_canvas):
    """font_size that resolves to a wrap scale leaving the text_canvas
    too short for the BDF cell height — raise loudly at first paint
    instead of silently clipping."""
    path = _make_png(tmp_path)
    # On 64-tall panel with bigsign scale=4: smart default wraps at 4,
    # giving text_canvas.height = 64//4 = 16 (adequate). To trigger the
    # error, use explicit font_size that wraps higher (e.g., 72px BDF →
    # 72//12=6 → canvas=64//6=10 < 12).
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="HI",
        text_align="scroll_over",
        font_size=72,  # BDF: 72//12=6 scale → 64//6=10 rows < 12
        hold_time=0.05,
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    with pytest.raises(ValueError, match="font_size"):
        await widget.play(real, frame)


def test_invalid_text_align_raises_with_empty_text(tmp_path):
    """Validation does NOT skip when text="". A bogus alignment should
    surface at construction even before any text is added."""
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_align"):
        StillImage(path=str(path), text_align="bogus")


def test_text_align_scroll_with_stretch_raises(tmp_path):
    """Cross-field pitfall: scroll mode + stretch = invisible text. Raise."""
    path = _make_png(tmp_path)
    with pytest.raises(ValueError, match="text_align='scroll'"):
        StillImage(
            path=str(path),
            fit="stretch",
            text="HELLO",
            text_align="scroll",
        )


async def test_static_fast_path_captures_swap_return(tmp_path, mocker, bigsign_canvas):
    """The static-text fast path also calls SwapOnVSync — it must capture
    the return per CLAUDE.md hardware constraint #1. Uses fresh-canvas-
    per-swap so a regression dropping the assignment fails."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="left",  # static — triggers fast path
        hold_time=0.1,
    )
    real = bigsign_canvas

    swap_returns: list[object] = []

    def fake_swap(c):
        new = type(real)(width=real.width, height=real.height)
        swap_returns.append(new)
        return new

    frame = mocker.MagicMock()
    frame.swap.side_effect = fake_swap
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    result = await widget.play(real, frame)
    # Fast path swaps once; result must be the swap return, not the original
    assert result is swap_returns[-1]
    assert result is not real


async def test_text_canvas_follows_back_buffer_when_wrapped(
    tmp_path, mocker, bigsign_canvas
):
    """On bigsign (smart-default wrap at _logical_scale) the text canvas
    is a ScaledCanvas wrapper — its `.real` attribute must be re-anchored
    to the new back-buffer after each swap (CLAUDE.md #10). Test runs the
    per-tick loop and asserts the wrapper points at the latest swap return
    each tick."""
    from led_ticker.scaled_canvas import ScaledCanvas

    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",  # per-tick loop runs
        scroll_speed_ms=50,
        hold_time=0.15,
    )
    widget._logical_scale = 4  # Simulate bigsign
    real = bigsign_canvas

    swap_returns: list[object] = []

    def fake_swap(c):
        new = type(real)(width=real.width, height=real.height)
        swap_returns.append(new)
        return new

    frame = mocker.MagicMock()
    frame.swap.side_effect = fake_swap
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_wrapped_real: list[object] = []
    real_draw = __import__(
        "led_ticker.widgets._image_base", fromlist=["draw_text"]
    ).draw_text

    def spy(canvas, font, x, y, color, text):
        # If canvas is ScaledCanvas, capture its .real to verify rebind
        if isinstance(canvas, ScaledCanvas):
            seen_wrapped_real.append(canvas.real)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets._image_base.draw_text", side_effect=spy)

    await widget.play(real, frame)

    # Tick 0: wrapper wraps `real`. Tick i (i>=1): wrapper.real is the
    # canvas that came back from swap i-1.
    assert len(seen_wrapped_real) >= 3
    assert seen_wrapped_real[0] is real
    for i, wrapped_real in enumerate(seen_wrapped_real[1:], start=1):
        assert wrapped_real is swap_returns[i - 1]


async def test_text_loops_when_wrapped(tmp_path, mocker, bigsign_canvas):
    """`ticks_per_text_loop = text_w + text_width` uses LOGICAL widths.
    On bigsign (smart-default wrap at scale=4), test that text_loops=2
    runs exactly 2 full traversals without regression to physical widths."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
        hold_time=0.05,
        text_loops=2,
    )
    widget._logical_scale = 4  # Simulate bigsign
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame)

    # At wrap_scale=4: text_w = 256 // 4 = 64 logical;
    # text_width("X") ≈ 6 logical. 1 traversal ≈ 70 ticks; ×2 ≈ 140.
    # If regression used physical widths (256 + 6 = 262 per traversal),
    # the count would be ≥ 524 — way outside our window.
    one_traversal = 64 + 6
    count = frame.swap.call_count
    assert 2 * one_traversal <= count < 3 * one_traversal


async def test_wrap_around_fires_at_correct_tick(tmp_path, mocker, bigsign_canvas):
    """Wrap condition uses `<= 0`. A regression to `< 0` would fire one
    tick later. Pin which tick fires the wrap by asserting BOTH the
    pre-wrap tick had value -text_width AND the wrap tick reset to
    text_w."""
    path = _make_png(tmp_path, color=(0, 0, 0))
    widget = StillImage(
        path=str(path),
        fit="pillarbox",  # avoid the scroll+stretch validator
        text="X",
        text_align="scroll",
        scroll_speed_ms=50,
        hold_time=0.05,
        text_loops=2,
    )
    real = bigsign_canvas
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen_x.append(x) or 6,
    )

    await widget.play(real, frame)

    # Wrap condition is `<= 0` (checked AFTER each per-tick increment):
    #   tick N-1: paint at scroll_pos=-5, increment → -6, wrap fires
    #   tick N:   paint at scroll_pos=256 (post-wrap reset)
    # So pre-wrap drawn value is -text_width + 1 = -5. A regression to
    # `< 0` would let -6 paint first (pre-wrap = -6).
    wraps = [i for i in range(1, len(seen_x)) if seen_x[i] > seen_x[i - 1]]
    assert wraps, "no wrap observed"
    pre_wrap = wraps[0] - 1
    assert seen_x[pre_wrap] == -5, (
        f"pre-wrap tick should have scroll_pos = -text_width + 1 = -5 "
        f"(off-by-one regression in wrap condition would give -6); "
        f"got {seen_x[pre_wrap]}"
    )
    assert seen_x[wraps[0]] == 256


@pytest.mark.parametrize("panel_h,scale", [(64, 6), (32, 3), (16, 2)])
def test_font_too_large_raises_on_various_panels(tmp_path, mocker, panel_h, scale):
    """font_size upper bound: panel_h // wrap_scale must be >= 12 (the
    BDF cell height). Parametrized over panel sizes so a regression
    that hardcodes panel_h would break on small sign / scale=2.
    Trigger error with font_size that results in wrap_scale too large."""
    from rgbmatrix import _StubCanvas

    path = _make_png(tmp_path)
    # Use font_size = 12 * scale so block_scale = scale,
    # and with _logical_scale=1 (small panels), wrap_scale=max(scale,1)=scale.
    # If scale*12 > panel_h, we get panel_h//scale < 12 → error.
    widget = StillImage(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        font_size=12 * scale,
        hold_time=0.05,
    )
    canvas = _StubCanvas(width=panel_h * 4, height=panel_h)
    frame = mocker.MagicMock()
    frame.swap.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    import asyncio as _asyncio

    with pytest.raises(ValueError, match="font_size"):
        _asyncio.get_event_loop().run_until_complete(widget.play(canvas, frame))


def test_real_asset_helper_fails_loudly_on_missing(tmp_path, monkeypatch):
    """Meta-test: `_real_asset()` MUST fail (not skip) when an asset is
    missing and the skip env var is not set. A regression turning
    pytest.fail into pytest.skip would otherwise hide regressions."""
    monkeypatch.delenv("LED_TICKER_SKIP_REAL_ASSETS", raising=False)
    with pytest.raises((pytest.fail.Exception, BaseException)) as exc:
        _real_asset("nonexistent-file-zzz.png")
    # Must be a Failed (pytest.fail) — not a skip
    msg = str(exc.value)
    assert "missing" in msg.lower() or "fail" in msg.lower()


# ---------------------------------------------------------------------------
# bg_color support in _play_no_text
# ---------------------------------------------------------------------------


class TestStillBgColor:
    def test_default_bg_is_none(self, tmp_path):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(path)
        s = StillImage(path=str(path))
        assert s.bg_color is None

    @pytest.mark.asyncio
    async def test_bg_color_set_uses_fill_in_play(self, tmp_path, mocker, monkeypatch):
        from PIL import Image
        from rgbmatrix.graphics import Color

        from led_ticker.widgets.still import StillImage

        async def _instant(_):
            pass

        monkeypatch.setattr("led_ticker.widgets.still.asyncio.sleep", _instant)

        path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(path)
        s = StillImage(path=str(path), bg_color=Color(11, 22, 33))

        canvas = mocker.MagicMock()
        canvas.width = 4
        canvas.height = 4
        # Bypass decode; pre-populate panel dims and pixels.
        s._pixels = b"\x00" * (4 * 4 * 3)
        s._panel_w = 4
        s._panel_h = 4

        frame_obj = mocker.MagicMock()
        frame_obj.swap.side_effect = lambda c: c
        await s._play_no_text(canvas, frame_obj)

        canvas.Clear.assert_not_called()
        canvas.Fill.assert_called_once_with(11, 22, 33)


# ---------------------------------------------------------------------------
# Two-mode _play_no_text: fast path vs per-tick loop based on border type
# ---------------------------------------------------------------------------


class TestStillPlayNoTextBorder:
    """`StillImage._play_no_text` two-mode pattern: fast path
    (paint once + sleep) when border is None or frame-invariant;
    per-tick loop when border is animated."""

    @pytest.fixture
    def still(self, tmp_path):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(path=img_path, hold_time=0.5)

    async def test_no_border_takes_fast_path(self, still, mock_frame, mocker):
        """Single SwapOnVSync, single sleep covering the full hold."""
        sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        await still._play_no_text(mock_frame.swap.return_value, mock_frame)
        # Fast path: ONE swap, ONE sleep.
        assert mock_frame.swap.call_count == 1
        assert sleep_mock.call_count == 1

    async def test_constant_border_takes_fast_path(self, still, mock_frame, mocker):
        from led_ticker.borders import ConstantBorder

        still.border = ConstantBorder([0, 255, 0])

        sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        await still._play_no_text(mock_frame.swap.return_value, mock_frame)
        assert mock_frame.swap.call_count == 1
        assert sleep_mock.call_count == 1

    async def test_animated_border_runs_per_tick_loop(self, still, mock_frame, mocker):
        """RainbowChaseBorder(speed=4) → per-tick loop for hold_time=0.5.
        Border.paint fires per tick with increasing frame_count."""
        from led_ticker.borders import RainbowChaseBorder
        from led_ticker.ticker import ENGINE_TICK_MS

        still.border = RainbowChaseBorder(speed=4)

        sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        await still._play_no_text(mock_frame.swap.return_value, mock_frame)
        expected_ticks = max(1, int(0.5 * 1000) // ENGINE_TICK_MS)
        assert mock_frame.swap.call_count == expected_ticks
        assert sleep_mock.call_count == expected_ticks
        # Frame counter advanced ~expected_ticks×
        assert (
            still._frame_count >= expected_ticks - 1
        ), f"_frame_count should advance per tick; got {still._frame_count}"


class TestStillPlayNoTextBorderPerEffectCounter:
    """Regression for the §4 fix in commit 6ccda4d: both
    `_play_no_text` branches (fast-path constant border + slow-path
    animated border) must read the per-effect counter via
    `frame_for("border")`. A continuous-phase border that opted out
    of visit-reset (`restart_on_visit = False`) would silently
    restart its chase across visits if the call site read
    `_frame_count` directly, since `_frame_count` always resets
    per visit. This was the hardware-observed bug in §4 of the
    rainbow-border smoke config before the fix.
    """

    @pytest.fixture
    def still(self, tmp_path):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(path=img_path, hold_time=0.1)

    async def test_animated_border_reads_per_effect_counter(
        self, still, mock_frame, mocker
    ):
        """Slow path (animated border): pre-populate the per-effect
        counter to simulate carry-over from prior visits, set
        `_frame_count = 0` to simulate a fresh engine reset, then
        verify `border.paint` receives values that ramp up from
        the carried counter — not from the freshly-zeroed
        `_frame_count`.
        """
        from led_ticker.borders import RainbowChaseBorder

        # `RainbowChaseBorder.restart_on_visit = False` (continuous phase).
        # Spy on paint to capture per-call frame_count.
        border = RainbowChaseBorder(speed=4)
        captured: list[int] = []
        original_paint = border.paint

        def _spy(canvas, frame_count):
            captured.append(frame_count)
            return original_paint(canvas, frame_count)

        border.paint = _spy  # type: ignore[method-assign]
        still.border = border

        # Simulate: rainbow border ran for 100 ticks across prior visits.
        # Engine just reset _frame_count for the new visit but the
        # per-effect counter persisted (restart_on_visit = False).
        still._effect_frames["border"] = 100
        still._frame_count = 0

        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        await still._play_no_text(mock_frame.swap.return_value, mock_frame)

        # First paint: advance_frame ran first (both counters +1),
        # so border counter is 101 at the first paint call. Bug-state
        # would have given 1 (reading _frame_count after advance).
        assert captured, "border.paint should have fired at least once"
        assert captured[0] == 101, (
            f"first border.paint should see persisted counter (101); "
            f"got {captured[0]} — _frame_count was being read directly"
        )

    async def test_constant_border_fast_path_reads_per_effect_counter(
        self, still, mock_frame, mocker
    ):
        """Fast path (constant border): the single paint call still
        reads `frame_for("border")`, not `_frame_count`. Constant
        border has `restart_on_visit = True` (default) so the
        per-effect counter is never seeded high in practice — but
        the SOURCE of the value must still be the per-effect entry
        so future continuous-phase + frame_invariant subclasses
        (hypothetical) get the right reading.
        """
        from led_ticker.borders import ConstantBorder

        border = ConstantBorder([0, 255, 0])
        captured: list[int] = []
        original_paint = border.paint

        def _spy(canvas, frame_count):
            captured.append(frame_count)
            return original_paint(canvas, frame_count)

        border.paint = _spy  # type: ignore[method-assign]
        still.border = border

        # Pre-populate per-effect counter to a distinguishable value;
        # _frame_count stays at 0 (the fast path does NOT advance).
        still._effect_frames["border"] = 42
        still._frame_count = 0

        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        await still._play_no_text(mock_frame.swap.return_value, mock_frame)

        # Single paint, value comes from the per-effect counter.
        assert captured == [42], (
            f"fast-path paint should read per-effect counter (42); "
            f"got {captured} — bug-state would yield [0]"
        )

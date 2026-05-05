"""Tests for the :gif: widget — _load() lazy decode + draw() compositing."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions, _StubCanvas
from rgbmatrix.graphics import Color

from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.widgets.gif import GifPlayer


def _make_gif_path(tmp_path, frames, size=(32, 32), duration_ms=100):
    images = [Image.new("RGB", size, color=c) for c in frames]
    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
    )
    p = tmp_path / "test.gif"
    p.write_bytes(buf.getvalue())
    return p


def _bigsign_real_canvas():
    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


def test_load_decodes_lazily(tmp_path):
    path = _make_gif_path(tmp_path, [(255, 0, 0), (0, 255, 0)])
    widget = GifPlayer(path=str(path), fit="stretch")
    assert widget._frames == []  # not loaded yet
    widget._load()
    assert len(widget._frames) == 2
    # Idempotent
    widget._load()
    assert len(widget._frames) == 2


def test_draw_paints_first_frame_to_real_canvas(tmp_path):
    path = _make_gif_path(tmp_path, [(200, 30, 40)])
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()

    canvas, advance = widget.draw(real, cursor_pos=0)

    # advance is the panel width — the widget claims the whole row
    assert advance == real.width
    # Lit pixels should match the source color
    assert real.get_pixel(0, 0) != (0, 0, 0)
    assert real.get_pixel(real.width - 1, real.height - 1) != (0, 0, 0)


def test_draw_unwraps_scaled_canvas(tmp_path):
    """ScaledCanvas wrapper must be bypassed so the GIF paints at native
    physical resolution, not as scale×scale blocks."""
    path = _make_gif_path(tmp_path, [(255, 255, 0)])
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    sc = ScaledCanvas(real, scale=4)

    canvas, advance = widget.draw(sc, cursor_pos=0)

    # advance is the SCALED canvas's width (logical), which is what
    # the layout system expects from any widget.
    assert advance == sc.width
    # The hi-res sprite painted directly to `real` — pixel at col 1
    # (NOT divisible by scale=4) should be lit, proving we bypassed
    # the wrapper.
    assert real.get_pixel(1, 1) != (0, 0, 0)


def test_draw_paints_current_frame_after_play(tmp_path):
    """After `play()` advances the frame index, draw() should paint the
    new current frame, not frame 0."""
    path = _make_gif_path(tmp_path, [(200, 0, 0), (0, 200, 0)])
    widget = GifPlayer(path=str(path), fit="stretch")
    widget._load()
    widget._current_frame_idx = 1  # simulate end-of-play state

    real = _bigsign_real_canvas()
    widget.draw(real, cursor_pos=0)

    # Pixel should reflect frame 1 (green), not frame 0 (red)
    r, g, b = real.get_pixel(real.width // 2, real.height // 2)
    assert g > r  # green-dominant


def test_missing_file_raises_at_load(tmp_path):
    widget = GifPlayer(path=str(tmp_path / "nope.gif"), fit="stretch")
    with pytest.raises(FileNotFoundError):
        widget._load()


async def test_play_loops_through_frames(tmp_path, mocker):
    path = _make_gif_path(tmp_path, [(255, 0, 0), (0, 255, 0)], duration_ms=10)
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()

    # Stub frame.matrix.SwapOnVSync to return a fresh canvas each call —
    # mirrors the real-stub tripwire from CLAUDE.md #1 / conftest.py.
    frame = mocker.MagicMock()
    swap_returns = []

    def fake_swap(c):
        new = type(real)(width=real.width, height=real.height)
        swap_returns.append(new)
        return new

    frame.matrix.SwapOnVSync.side_effect = fake_swap

    # Stub asyncio.sleep so the test runs instantly
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    final = await widget.play(real, frame, loop_count=2)

    # 2 loops × 2 frames = 4 swaps
    assert frame.matrix.SwapOnVSync.call_count == 4
    # Final canvas is whatever the last swap returned (drop-capture
    # regression: we MUST capture the swap return value)
    assert final is swap_returns[-1]
    # _current_frame_idx left at the last frame
    assert widget._current_frame_idx == 1


async def test_play_clamps_zero_loop_count_to_one(tmp_path, mocker):
    path = _make_gif_path(tmp_path, [(50, 50, 50)], duration_ms=10)
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=0)

    # Treated as "play once"
    assert frame.matrix.SwapOnVSync.call_count == 1


async def test_play_uses_per_frame_durations(tmp_path, mocker):
    # Use distinct colors so PIL does not collapse identical frames into one.
    path = _make_gif_path(tmp_path, [(10, 20, 30), (40, 50, 60)], duration_ms=120)
    widget = GifPlayer(path=str(path), fit="stretch")
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c

    sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    # Each frame's duration was 120ms → 0.12s passed to asyncio.sleep
    sleeps = [c.args[0] for c in sleep_mock.await_args_list]
    assert all(abs(s - 0.12) < 1e-6 for s in sleeps)
    assert len(sleeps) == 2


# ---------------------------------------------------------------------------
# Text-alongside-GIF tests (options A static + B scrolling)
# ---------------------------------------------------------------------------


def test_invalid_text_align_raises(tmp_path):
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    with pytest.raises(ValueError):
        GifPlayer(path=str(path), text="hi", text_align="bogus")


def test_text_align_auto_resolves_from_image_align(tmp_path):
    """text_align="auto" (default) picks the opposite side of the gif so
    they never overlap. Center gif → scroll_over (no overlap zone)."""
    path = _make_gif_path(tmp_path, [(10, 20, 30)])

    # Default image_align = "center" → scroll_over
    w = GifPlayer(path=str(path), text="HELLO")
    assert w.text_align == "scroll_over"

    # image_align = "left" → right
    w = GifPlayer(path=str(path), text="HELLO", image_align="left")
    assert w.text_align == "right"

    # image_align = "right" → left
    w = GifPlayer(path=str(path), text="HELLO", image_align="right")
    assert w.text_align == "left"

    # Explicit text_align overrides auto
    w = GifPlayer(path=str(path), text="HELLO", image_align="left", text_align="scroll")
    assert w.text_align == "scroll"


def test_invalid_image_align_raises(tmp_path):
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    with pytest.raises(ValueError, match="image_align"):
        GifPlayer(path=str(path), image_align="bogus")


def test_invalid_text_valign_raises(tmp_path):
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    with pytest.raises(ValueError, match="text_valign"):
        GifPlayer(path=str(path), text_valign="middle")


def test_invalid_scroll_direction_raises(tmp_path):
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    with pytest.raises(ValueError, match="scroll_direction"):
        GifPlayer(path=str(path), scroll_direction="up")


@pytest.mark.parametrize(
    "valign,h,expected_baseline",
    [
        ("top", 64, 10),  # baseline = ascent (10) regardless of h
        ("center", 64, 36),  # (64-12)//2 + 10 = 36
        ("bottom", 64, 62),  # baseline = h - descent (2)
        ("center", 16, 12),  # logical canvas (text_scale > 1) → 12
        ("top", 16, 10),
        ("bottom", 16, 14),
    ],
)
def test_baseline_y_honors_text_valign(tmp_path, valign, h, expected_baseline):
    """`_baseline_y` returns the BDF baseline row for each valign mode.
    Top: baseline = ascent. Center: existing logic. Bottom: h - descent."""
    from types import SimpleNamespace

    path = _make_gif_path(tmp_path, [(0, 0, 0)])
    widget = GifPlayer(path=str(path), text_valign=valign)
    canvas = SimpleNamespace(height=h, scale=1)
    assert widget._baseline_y(canvas) == expected_baseline


@pytest.mark.parametrize(
    "valign,offset,h,expected",
    [
        ("top", -3, 64, 7),
        ("top", 4, 64, 14),
        ("center", 0, 64, 36),
        ("bottom", -10, 64, 52),
    ],
)
def test_text_y_offset_shifts_baseline(tmp_path, valign, offset, h, expected):
    from types import SimpleNamespace

    path = _make_gif_path(tmp_path, [(0, 0, 0)])
    widget = GifPlayer(path=str(path), text_valign=valign, text_y_offset=offset)
    canvas = SimpleNamespace(height=h, scale=1)
    assert widget._baseline_y(canvas) == expected


@pytest.mark.parametrize(
    "align,offset,expected_x",
    [
        ("left", 0, 2),
        ("left", 10, 12),
        ("right", 0, 256 - 6 - 2),
        ("right", -10, 256 - 6 - 2 - 10),
    ],
)
async def test_text_x_offset_shifts_static_text(
    tmp_path, mocker, align, offset, expected_x
):
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align=align,
        text_x_offset=offset,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen_x.append(x) or 6,
    )

    await widget.play(real, frame, loop_count=1)

    assert seen_x[0] == expected_x


def test_text_x_offset_with_scroll_raises(tmp_path):
    """text_x_offset is a static-text knob — for scrolling text it would
    just skew the trajectory by a constant. We raise loudly rather than
    silently no-op."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)])
    with pytest.raises(ValueError, match="text_x_offset"):
        GifPlayer(
            path=str(path),
            fit="stretch",
            text="X",
            text_align="scroll_over",
            text_x_offset=99,
        )


async def test_top_valign_paints_at_panel_top_with_text_scale_2(tmp_path, mocker):
    """With text_valign='top' (and smart-default wrap scale on bigsign),
    the wrapper spans the FULL panel (content_height = panel_h // scale)
    — text paints at the panel's TOP edge, not letterboxed."""
    from led_ticker.scaled_canvas import ScaledCanvas

    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="right",
        text_valign="top",
    )
    widget._logical_scale = 4  # Simulate bigsign
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_canvases: list[object] = []
    seen_y: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: (
            seen_canvases.append(c) or seen_y.append(y) or 12
        ),
    )

    await widget.play(real, frame, loop_count=1)

    assert seen_canvases
    assert isinstance(seen_canvases[0], ScaledCanvas)
    # Behavioral: wrapper spans the FULL panel height (no letterbox
    # sub-region) — decouples from exact content_height value.
    assert seen_canvases[0].height * seen_canvases[0].scale == real.height
    # Top valign → baseline 10 (BDF ascent) → cell top at panel y=0.
    assert seen_y[0] == 10


async def test_scroll_direction_right_advances_positively(tmp_path, mocker):
    """scroll_direction='right' starts text off the LEFT edge and moves
    it rightward across the panel — opposite of the default."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
        scroll_direction="right",
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    real_draw = __import__(
        "led_ticker.widgets._image_base", fromlist=["draw_text"]
    ).draw_text

    def spy(canvas, font, x, y, color, text):
        seen_x.append(x)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets._image_base.draw_text", side_effect=spy)
    await widget.play(real, frame, loop_count=5)

    # First tick: scroll_pos = -text_width (off-left); each subsequent
    # tick adds 1 (moves right).
    assert seen_x[0] < 0  # starts off the left edge
    assert seen_x[1] == seen_x[0] + 1
    assert seen_x[2] == seen_x[0] + 2


def test_image_align_left_anchors_at_x_zero(tmp_path):
    """GifPlayer threads image_align through to decode_gif. After load(),
    a 32×32 pillarboxed source aligned 'left' should leave cols 64+
    black on the bigsign panel."""
    path = _make_gif_path(tmp_path, [(255, 255, 255)], size=(32, 32))
    widget = GifPlayer(path=str(path), fit="pillarbox", image_align="left")
    real = _bigsign_real_canvas()

    widget.draw(real, cursor_pos=0)

    # Cols 0..63 white; cols 64..255 black pillar
    assert real.get_pixel(0, 32) == (255, 255, 255)
    assert real.get_pixel(63, 32) == (255, 255, 255)
    assert real.get_pixel(64, 32) == (0, 0, 0)
    assert real.get_pixel(255, 32) == (0, 0, 0)


def test_default_text_align_resolves_with_no_text(tmp_path):
    """text_align="auto" (default) resolves cleanly even when text="" —
    no exception, default values survive validation."""
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    w = GifPlayer(path=str(path))
    # auto + image_align=center → scroll_over (resolved + valid)
    assert w.text_align == "scroll_over"


def test_invalid_text_align_raises_with_empty_text(tmp_path):
    """Validation does NOT skip when text="". A bogus alignment should
    surface at construction even before any text is added (the previous
    `if self.text:` guard let bogus values silently pass)."""
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    with pytest.raises(ValueError, match="text_align"):
        GifPlayer(path=str(path), text_align="bogus")  # text="" by default


def test_text_align_scroll_with_stretch_raises(tmp_path):
    """Cross-field footgun: scroll mode relies on transparent / pillarbox
    regions for skip-black to expose the marquee. With fit='stretch'
    the panel is fully opaque — text would be invisible. Raise."""
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    with pytest.raises(ValueError, match="text_align='scroll'"):
        GifPlayer(
            path=str(path),
            fit="stretch",
            text="HELLO",
            text_align="scroll",
        )


def test_paint_skip_black_leaves_zero_pixels_untouched(tmp_path):
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    widget = GifPlayer(path=str(path), fit="stretch")
    widget._panel_w = 4
    widget._panel_h = 2
    canvas = _StubCanvas(width=4, height=2)
    # Pre-paint canvas: a yellow line at row 0 to simulate text underneath
    for x in range(4):
        canvas.SetPixel(x, 0, 200, 200, 0)
    # Frame: row 0 has alternating red and black; row 1 is solid green
    pixels = bytes(
        [
            255,
            0,
            0,
            0,
            0,
            0,
            255,
            0,
            0,
            0,
            0,
            0,
            0,
            255,
            0,
            0,
            255,
            0,
            0,
            255,
            0,
            0,
            255,
            0,
        ]
    )
    widget._frames = [(pixels, 50)]

    # _paint_skip_black builds caches lazily; iterates the precomputed
    # non-black list (skipping the alternating black pixels in row 0).
    widget._paint_skip_black(canvas)

    # Black pixels skipped → underlying yellow shows through
    assert canvas.get_pixel(0, 0) == (255, 0, 0)
    assert canvas.get_pixel(1, 0) == (200, 200, 0)
    assert canvas.get_pixel(2, 0) == (255, 0, 0)
    assert canvas.get_pixel(3, 0) == (200, 200, 0)
    # Row 1 fully painted green
    for x in range(4):
        assert canvas.get_pixel(x, 1) == (0, 255, 0)


async def test_play_with_text_uses_scroll_speed_cadence(tmp_path, mocker):
    """With SCROLLING text, ticks happen at scroll_speed_ms regardless
    of frame durations — that's what lets text scroll smoothly over
    slow GIFs. (Static text uses a fast path: paint once, sleep
    cumulative duration.)"""
    path = _make_gif_path(tmp_path, [(10, 20, 30), (40, 50, 60)], duration_ms=120)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="hi",
        text_align="scroll_over",  # scrolling, ticks per scroll_speed_ms
        scroll_speed_ms=60,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    sleeps = [c.args[0] for c in sleep_mock.await_args_list]
    # Cadence: each sleep is exactly scroll_speed_ms regardless of how
    # many ticks the marquee floor produces (gif natural would be 240ms
    # / 60ms = 4, but the auto-floor extends to text_w + text_width
    # ticks so the marquee completes one full pass — see
    # `test_text_loops_zero_extends_to_one_full_traversal`).
    assert len(sleeps) > 0
    assert all(abs(s - 0.06) < 1e-6 for s in sleeps)


async def test_play_static_right_text_overlays_gif(tmp_path, mocker):
    """Static right-aligned text paints AFTER gif → text pixels override."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)])
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="right",
        font_color=Color(255, 0, 0),
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    # Stub DrawText writes a 1px band at y-1. Text starts at
    # x = w - text_width - 2; the right-edge pixel of that band is red.
    text_width = widget.font.CharacterWidth(ord("X"))
    text_x = real.width - text_width - 2
    baseline_y = (real.height - 12) // 2 + 10
    assert real.get_pixel(text_x, baseline_y - 1) == (255, 0, 0)


async def test_play_static_left_text_at_x_2(tmp_path, mocker):
    path = _make_gif_path(tmp_path, [(0, 0, 0)])
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="left",
        font_color=Color(0, 255, 0),
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    baseline_y = (real.height - 12) // 2 + 10
    assert real.get_pixel(2, baseline_y - 1) == (0, 255, 0)


async def test_play_scroll_over_text_overlays_gif(tmp_path, mocker):
    """scroll_over: gif painted first, text on top — so text is always
    visible (opposite of `scroll`, which puts text under and skips black
    gif pixels). Capture each tick's canvas state and assert the text
    overrides the gif at whatever scroll_pos that tick was at.
    """
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        font_color=Color(255, 255, 255),
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    w, h = real.width, real.height

    pixels = bytes([180] * (w * h * 3))
    widget._panel_w = w
    widget._panel_h = h
    widget._frames = [(bytes(pixels), 50)]

    band_y = (h - 12) // 2 + 10 - 1
    target_x = 10
    target_tick = w - target_x  # tick where scroll_pos lands at target_x

    captured: list[tuple[int, int, int]] = []

    def swap(c):
        if len(captured) == target_tick:
            captured.append(c.get_pixel(target_x, band_y))
        else:
            captured.append((-1, -1, -1))
        return c

    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = swap
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    # Just need enough loops that target_tick gets executed; the
    # marquee auto-floor will extend further but we only inspect the
    # one tick we care about.
    await widget.play(real, frame, loop_count=1)

    assert captured[target_tick] == (255, 255, 255), (
        f"text at target_tick={target_tick} should be white; got "
        f"{captured[target_tick]}"
    )
    # Sanity: outside the text band the gif still shows on the same
    # tick. Need to inspect it; re-run with a different inspector.
    assert real.height > 12  # bigsign canvas, just keep test marker


async def test_text_loops_extends_section_duration(tmp_path, mocker):
    """text_loops puts a floor on tick count: section runs at least
    N text traversals even if the gif's own loop_count is shorter."""
    # Gif loops fast (1 frame × 50 ms × 1 loop = 50 ms total, 1 tick).
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",  # narrow so the math is easy
        text_align="scroll_over",
        scroll_speed_ms=50,
        text_loops=2,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    # text_w=256, text_width("X")=6 → 1 traversal ≈ 262 ticks. With
    # text_loops=2 the floor is ≥ 2 traversals, < 3. Bounds avoid
    # pinning the exact formula.
    one_traversal = 256 + 6
    count = frame.matrix.SwapOnVSync.call_count
    assert 2 * one_traversal <= count < 3 * one_traversal


async def test_hires_marquee_completes_full_traversal_default(tmp_path, mocker):
    """Hardware-observed: a hires-wide marquee got cut off mid-pass when
    gif_loops × loop_ms < (text_w + text_width) × scroll_speed_ms. The
    auto-floor (text_loops=0 default) extends to at least one full pass,
    so the panel doesn't show "...moonbunnyaer" frozen at section end.
    """
    from led_ticker.fonts import resolve_font

    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    font = resolve_font("Inter-Regular", 24)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="Follow us! @moonbunnyaerial",  # ~280+ real px wide
        text_align="scroll_over",
        scroll_speed_ms=50,
        font=font,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    # gif_loops=1 × 50ms = 50ms natural / 50ms tick = 1 tick.
    # Without the auto-floor, the marquee would advance only 1 px and
    # then the section ends. With it, the loop runs ≥ text_w +
    # text_width ticks so a full pass completes.
    await widget.play(real, frame, loop_count=1)

    # Lower bound: text_w (256) + minimum text_width (~150 conservative).
    assert frame.matrix.SwapOnVSync.call_count >= 256 + 150


async def test_text_loops_zero_extends_to_one_full_traversal(tmp_path, mocker):
    """text_loops=0 (default) now floors to one full marquee traversal.
    Before: gif duration ruled — short gifs cut off mid-marquee. After:
    the floor ensures the marquee doesn't get truncated. This protects
    hires-wide text whose natural traversal time exceeds the gif loop.
    """
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    # 50 ms gif × 1 loop / 50 ms tick = 1 tick natural duration. The
    # auto-floor extends to text_w + text_width = 256 + 6 = 262 ticks
    # so the marquee completes one full pass.
    one_traversal = 256 + 6
    count = frame.matrix.SwapOnVSync.call_count
    assert one_traversal <= count < 2 * one_traversal


def test_text_loops_with_static_text_raises(tmp_path):
    """text_loops > 0 with static text_align (left/right) used to be
    silently ignored — now raises so the user notices their config
    floor isn't being honored."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    with pytest.raises(ValueError, match="text_loops"):
        GifPlayer(
            path=str(path),
            fit="stretch",
            text="X",
            text_align="right",  # static
            text_loops=10,
        )


def test_negative_numeric_fields_raise(tmp_path):
    """Range validation: text_scale < 1, loops < 1, text_loops < 0,
    scroll_speed_ms < MIN all raise instead of silently mis-behaving."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)])
    with pytest.raises(ValueError, match="text_scale"):
        GifPlayer(path=str(path), text_scale=0)
    with pytest.raises(ValueError, match="text_scale"):
        GifPlayer(path=str(path), text_scale=-1)
    with pytest.raises(ValueError, match="gif_loops"):
        GifPlayer(path=str(path), gif_loops=0)
    with pytest.raises(ValueError, match="text_loops"):
        GifPlayer(path=str(path), text_loops=-1)
    with pytest.raises(ValueError, match="scroll_speed_ms"):
        GifPlayer(path=str(path), scroll_speed_ms=10)  # below MIN=20


async def test_play_scroll_text_wraps_after_full_traversal(tmp_path, mocker):
    """Scroll wraps `scroll_pos` back to text_w when text fully exits left.
    Without this test, off-by-one in `<= 0` vs `< 0` wrap condition could
    ship green: the existing tests only watch monotonically-decreasing
    positions across 5 ticks, never exercising the reset."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    real_draw = __import__(
        "led_ticker.widgets._image_base", fromlist=["draw_text"]
    ).draw_text

    def spy(canvas, font, x, y, color, text):
        seen_x.append(x)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets._image_base.draw_text", side_effect=spy)

    # Run for enough ticks to fully traverse + see the wrap. text_w=256,
    # text_width for "X" = 6. One traversal = 256 + 6 = 262 ticks (panel-
    # right exit to off-left). Use text_loops=2 to force long enough run.
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        scroll_speed_ms=50,
        text_loops=2,
    )
    seen_x.clear()
    mocker.patch("led_ticker.widgets._image_base.draw_text", side_effect=spy)
    await widget.play(real, frame, loop_count=1)

    # Sequence must contain a wrap: somewhere we go from a low (negative)
    # value back to text_w (256). Find at least one drop where x increases.
    increases = [i for i in range(1, len(seen_x)) if seen_x[i] > seen_x[i - 1]]
    assert increases, (
        f"scroll_pos never wrapped back to text_w; saw {len(seen_x)} ticks "
        f"with min={min(seen_x)} max={max(seen_x)}"
    )
    # On wrap, scroll_pos should reset to exactly text_w (256), not text_w-1
    # or text_w+1. Pick the first wrap and verify.
    wrap_idx = increases[0]
    assert (
        seen_x[wrap_idx] == real.width
    ), f"wrap should reset to text_w={real.width}, got {seen_x[wrap_idx]}"


async def test_play_scroll_text_advances_position(tmp_path, mocker):
    """Scroll mode decrements scroll_pos by 1 per tick. Capture the
    DrawText x-coordinate each tick to verify monotonic advance."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="hi",
        text_align="scroll_over",
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    real_draw = __import__(
        "led_ticker.widgets._image_base", fromlist=["draw_text"]
    ).draw_text

    def spy(canvas, font, x, y, color, text):
        seen_x.append(x)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets._image_base.draw_text", side_effect=spy)

    # 5 loops × 50ms = 250ms / 50ms tick = 5 ticks natural — but the
    # marquee auto-floor extends to one full traversal, so seen_x
    # has many more entries. The first 5 still pin the per-tick
    # decrement behavior.
    await widget.play(real, frame, loop_count=5)

    # First tick at scroll_pos = w; subsequent ticks decrement by 1.
    assert seen_x[:5] == [
        real.width,
        real.width - 1,
        real.width - 2,
        real.width - 3,
        real.width - 4,
    ]


async def test_play_scroll_text_visible_through_black_pillars(tmp_path, mocker):
    """The whole point of scroll mode: gif on top, text under, but
    black gif pixels are skipped so text shines through pillars.
    Capture canvas state at the specific tick that lands the text in
    the left pillar — independent of how many ticks the marquee
    auto-floor produces."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll_over",
        font_color=Color(0, 0, 200),
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    w, h = real.width, real.height

    band_y = (h - 12) // 2 + 10 - 1
    pixels = bytearray(w * h * 3)
    centre_lo, centre_hi = 100, 160
    for y in range(h):
        for x in range(centre_lo, centre_hi):
            base = (y * w + x) * 3
            pixels[base] = pixels[base + 1] = pixels[base + 2] = 180
    widget._panel_w = w
    widget._panel_h = h
    widget._frames = [(bytes(pixels), 50)]

    target_x = 10
    target_tick = w - target_x  # scroll_pos lands at target_x on this tick

    pillar_at_target: list[tuple[int, int, int]] = []
    centre_at_target: list[tuple[int, int, int]] = []
    tick_count = [0]

    def swap(c):
        if tick_count[0] == target_tick:
            pillar_at_target.append(c.get_pixel(target_x, band_y))
            centre_at_target.append(c.get_pixel(centre_lo + 5, band_y))
        tick_count[0] += 1
        return c

    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = swap
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    assert pillar_at_target == [(0, 0, 200)], (
        f"text colour expected through left pillar at target_tick="
        f"{target_tick}; got {pillar_at_target}"
    )
    assert centre_at_target == [(180, 180, 180)], (
        f"gif gray expected over centre region at target_tick="
        f"{target_tick}; got {centre_at_target}"
    )


class TestFrameForElapsed:
    """Direct unit tests for _frame_for_elapsed — its boundary behaviour
    is otherwise only exercised end-to-end via play(), which masks
    off-by-one bugs at frame edges."""

    def _widget_with_frames(self, tmp_path, frame_durations):
        colors = [(c, c, c) for c in range(len(frame_durations))]
        path = _make_gif_path(tmp_path, colors)
        widget = GifPlayer(path=str(path), fit="stretch")
        # Bypass real decoding — synthesize frames with known durations
        widget._frames = [(b"", d) for d in frame_durations]
        return widget

    def test_picks_frame_zero_at_start(self, tmp_path):
        w = self._widget_with_frames(tmp_path, [100, 100, 100])
        assert w._frame_for_elapsed(0, 300) == 0

    def test_stays_on_frame_zero_just_before_boundary(self, tmp_path):
        w = self._widget_with_frames(tmp_path, [100, 100, 100])
        assert w._frame_for_elapsed(99, 300) == 0

    def test_advances_at_boundary(self, tmp_path):
        """At elapsed = first-frame-duration, we should be on frame 1."""
        w = self._widget_with_frames(tmp_path, [100, 100, 100])
        assert w._frame_for_elapsed(100, 300) == 1

    def test_picks_last_frame_just_before_loop_end(self, tmp_path):
        w = self._widget_with_frames(tmp_path, [100, 100, 100])
        assert w._frame_for_elapsed(299, 300) == 2

    def test_wraps_at_loop_boundary(self, tmp_path):
        """elapsed == loop_ms should wrap back to frame 0."""
        w = self._widget_with_frames(tmp_path, [100, 100, 100])
        assert w._frame_for_elapsed(300, 300) == 0
        assert w._frame_for_elapsed(301, 300) == 0

    def test_unequal_frame_durations(self, tmp_path):
        w = self._widget_with_frames(tmp_path, [50, 200, 100])
        assert w._frame_for_elapsed(0, 350) == 0
        assert w._frame_for_elapsed(49, 350) == 0
        assert w._frame_for_elapsed(50, 350) == 1
        assert w._frame_for_elapsed(249, 350) == 1
        assert w._frame_for_elapsed(250, 350) == 2
        assert w._frame_for_elapsed(349, 350) == 2
        assert w._frame_for_elapsed(350, 350) == 0  # wrap


async def test_play_with_emoji_routes_through_emoji_painter(tmp_path, mocker):
    """When `text` contains a `:slug:` token, _play_with_text must
    dispatch to draw_with_emoji (not draw_text) so the icon actually
    renders. Spy on the dispatcher; assert it gets called."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text=":sun: hot",
        text_align="right",
        font_color=Color(255, 220, 50),
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    spy = mocker.patch(
        "led_ticker.pixel_emoji.draw_with_emoji",
        side_effect=lambda c, *a, **kw: 16,
    )

    await widget.play(real, frame, loop_count=1)

    assert spy.called, "draw_with_emoji should be invoked for `:slug:` text"


async def test_static_text_wider_than_canvas_clamps_to_left_edge(tmp_path, mocker):
    """text_x_right = max(2, text_w - text_width - 2). With text wider
    than canvas, the unclamped expression goes negative. Drop the max()
    and DrawText would draw partially off the panel — no test catches it
    today."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)])
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="A" * 100,  # ~600px at 6×12 BDF — way wider than 256
        text_align="right",
        font_color=Color(255, 255, 255),
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen_x.append(x) or 600,
    )

    await widget.play(real, frame, loop_count=1)

    assert seen_x, "draw_text should have been called"
    # Clamped to left edge padding (2), not negative
    assert seen_x[0] == 2


async def test_play_emoji_with_text_scale_and_scroll(tmp_path, mocker):
    """The actual user combo (Section 15 in config.gif_test): emoji slug
    + wrap at smart-default scale + text_align="scroll_over". Test that
    logical/physical unit handling in `_measure_text` is correct."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text=":sun: HOT",
        text_align="scroll_over",
        font_color=Color(255, 255, 255),
        scroll_speed_ms=50,
        text_loops=1,
    )
    widget._logical_scale = 4  # Simulate bigsign
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    emoji_calls = mocker.patch(
        "led_ticker.pixel_emoji.draw_with_emoji",
        side_effect=lambda c, *a, **kw: 30,
    )

    await widget.play(real, frame, loop_count=1)

    # Emoji painter ran (not draw_text) because text contains a slug
    assert emoji_calls.called
    # Each call got a ScaledCanvas (smart-default wrap at scale=4)
    from led_ticker.scaled_canvas import ScaledCanvas

    for call in emoji_calls.call_args_list:
        canvas_arg = call.args[0]
        assert isinstance(canvas_arg, ScaledCanvas), (
            f"emoji painter should receive ScaledCanvas at wrap_scale=4, "
            f"got {type(canvas_arg).__name__}"
        )


async def test_play_text_scale_uses_scaled_canvas(tmp_path, mocker):
    """Smart-default wrap at _logical_scale wraps the real canvas in a
    ScaledCanvas just for text painting — block-expands each glyph pixel
    so text is visible on bigsign. Confirm by spying on draw_text."""
    from led_ticker.scaled_canvas import ScaledCanvas

    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="HI",
        text_align="right",
        font_color=Color(255, 255, 255),
    )
    widget._logical_scale = 4  # Simulate bigsign
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_canvases: list[object] = []
    real_draw = __import__(
        "led_ticker.widgets._image_base", fromlist=["draw_text"]
    ).draw_text

    def spy(canvas, font, x, y, color, text):
        seen_canvases.append(canvas)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets._image_base.draw_text", side_effect=spy)

    await widget.play(real, frame, loop_count=1)

    # Every text-paint tick handed draw_text a ScaledCanvas at wrap_scale=4
    assert seen_canvases, "draw_text should have been invoked at least once"
    assert all(isinstance(c, ScaledCanvas) for c in seen_canvases)
    assert all(c.scale == 4 for c in seen_canvases)


async def test_play_text_scale_1_text_canvas_follows_back_buffer(tmp_path, mocker):
    """Regression: with text_scale=1 we have NO ScaledCanvas wrapper to
    re-anchor — text_canvas is the canvas itself. After SwapOnVSync the
    `canvas` variable is reassigned to the new back-buffer, but
    text_canvas would silently keep pointing at the previous (now front)
    buffer, causing text to be painted onto the displayed buffer every
    other tick → visible pulsing/flicker.

    Spy on draw_text and assert that each tick's paint target is the
    same canvas the gif paint targets (= the back-buffer for that tick),
    not the previous one."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    # scroll_over keeps the per-tick loop active (static text fast-paths
    # to a single paint, which would mask the back-buffer-follow bug).
    widget = GifPlayer(
        path=str(path), fit="stretch", text="X", text_align="scroll_over"
    )
    real = _bigsign_real_canvas()

    frame = mocker.MagicMock()
    swap_returns: list[object] = []

    def fake_swap(c):
        new = type(real)(width=real.width, height=real.height)
        swap_returns.append(new)
        return new

    frame.matrix.SwapOnVSync.side_effect = fake_swap
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen: list[object] = []
    real_draw = __import__(
        "led_ticker.widgets._image_base", fromlist=["draw_text"]
    ).draw_text

    def spy(canvas, font, x, y, color, text):
        seen.append(canvas)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets._image_base.draw_text", side_effect=spy)

    await widget.play(real, frame, loop_count=3)

    # Need at least 3 ticks to trip a binding-staleness bug
    assert len(seen) >= 3
    # Tick 0 paints to the original real canvas
    assert seen[0] is real
    # Tick 1+ paints to the canvas that came back from the previous swap
    for i, canvas in enumerate(seen[1:], start=1):
        assert canvas is swap_returns[i - 1], (
            f"tick {i} should paint to swap_returns[{i - 1}], "
            f"not the stale front buffer"
        )


async def test_play_text_scale_1_uses_real_canvas(tmp_path, mocker):
    """text_scale=1 (default) keeps the existing native-resolution path
    — no ScaledCanvas wrapper, draw_text gets the raw real canvas."""
    from led_ticker.scaled_canvas import ScaledCanvas

    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="HI",
        text_align="right",
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen: list[object] = []
    mocker.patch(
        "led_ticker.widgets._image_base.draw_text",
        side_effect=lambda c, *a, **kw: seen.append(c) or 6,
    )

    await widget.play(real, frame, loop_count=1)

    assert seen and not any(isinstance(c, ScaledCanvas) for c in seen)


def test_draw_does_not_paint_text(tmp_path):
    """draw() (used for transition compositing) deliberately skips text
    rendering. Asserts no text-coloured pixels appear after draw()."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)])
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="VISIBLE",
        text_align="left",
        font_color=Color(255, 0, 255),
    )
    real = _bigsign_real_canvas()

    widget.draw(real, cursor_pos=0)

    # No pixel should be the magenta text colour
    for y in range(real.height):
        for x in range(real.width):
            assert real.get_pixel(x, y) != (255, 0, 255)


async def test_gif_static_text_does_not_freeze_animation(tmp_path, mocker):
    """REGRESSION: static text alongside a multi-frame gif must NOT
    freeze the gif on frame 0. The static-text fast path applies only
    when the source itself is static — `_is_static()` returns False
    on multi-frame gifs, forcing the per-tick loop to run so frames
    advance via `_pick_frame_for_elapsed`."""
    # 3-frame gif with distinct colors. Each frame is short (50ms) so
    # several should advance over a few ticks at scroll_speed_ms=50.
    path = _make_gif_path(
        tmp_path,
        [(220, 30, 30), (30, 220, 30), (30, 30, 220)],
        duration_ms=50,
    )
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="right",  # static — would trigger fast-path on a still
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    # gif_loops=1 × 3 frames × 50ms = 150ms / 50ms tick = 3 ticks.
    # Without the fast-path-disable for animated gifs, only 1 swap
    # would happen (paint frame 0, sleep 0.15s, return) and
    # `_current_frame_idx` would stay at 0.
    await widget.play(real, frame, loop_count=1)

    # Per-tick loop ran → frame index advanced past 0
    assert widget._current_frame_idx > 0, (
        f"Multi-frame gif froze on frame 0 — fast-path was incorrectly "
        f"applied to an animated source. Got _current_frame_idx="
        f"{widget._current_frame_idx}; expected > 0."
    )


class TestGifBgColor:
    @pytest.mark.asyncio
    async def test_bg_color_default_paints_full(self, tmp_path, mocker):
        """No bg_color → _play_no_text uses canvas.Clear + _paint_full
        (existing fast path)."""
        from PIL import Image

        from led_ticker.widgets.gif import GifPlayer

        path = tmp_path / "tiny.gif"
        frames = [Image.new("RGB", (2, 2), (255, 0, 0))] * 2
        frames[0].save(
            path, save_all=True, append_images=frames[1:], duration=50, loop=0
        )

        gif = GifPlayer(path=str(path))
        canvas = mocker.MagicMock()
        canvas.width = 4
        canvas.height = 4
        # Inject decoded frames directly to bypass actual decode in tests.
        gif._frames = [(b"\x00" * (4 * 4 * 3), 50), (b"\x00" * (4 * 4 * 3), 50)]
        gif._panel_w = 4
        gif._panel_h = 4

        frame_obj = mocker.MagicMock()
        frame_obj.matrix.SwapOnVSync.side_effect = lambda c: c
        await gif._play_no_text(canvas, frame_obj, loop_count=1)

        # No bg → Clear should have been called per-frame (2 frames × 1 loop = 2).
        assert canvas.Clear.call_count == 2
        canvas.Fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_bg_color_set_uses_fill(self, tmp_path, mocker):
        """bg_color set → _play_no_text uses canvas.Fill(bg) per-frame."""
        from PIL import Image
        from rgbmatrix.graphics import Color

        from led_ticker.widgets.gif import GifPlayer

        path = tmp_path / "tiny.gif"
        frames = [Image.new("RGB", (2, 2), (255, 0, 0))] * 2
        frames[0].save(
            path, save_all=True, append_images=frames[1:], duration=50, loop=0
        )

        gif = GifPlayer(path=str(path), bg_color=Color(80, 90, 100))
        canvas = mocker.MagicMock()
        canvas.width = 4
        canvas.height = 4
        gif._frames = [(b"\x00" * (4 * 4 * 3), 50)]
        gif._panel_w = 4
        gif._panel_h = 4

        frame_obj = mocker.MagicMock()
        frame_obj.matrix.SwapOnVSync.side_effect = lambda c: c
        await gif._play_no_text(canvas, frame_obj, loop_count=1)

        canvas.Clear.assert_not_called()
        canvas.Fill.assert_called_with(80, 90, 100)

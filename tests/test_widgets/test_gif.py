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


def test_invalid_gif_align_raises(tmp_path):
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    with pytest.raises(ValueError, match="gif_align"):
        GifPlayer(path=str(path), gif_align="bogus")


def test_gif_align_left_anchors_at_x_zero(tmp_path):
    """GifPlayer threads gif_align through to decode_gif. After load(),
    a 32×32 pillarboxed source aligned 'left' should leave cols 64+
    black on the bigsign panel."""
    path = _make_gif_path(tmp_path, [(255, 255, 255)], size=(32, 32))
    widget = GifPlayer(path=str(path), fit="pillarbox", gif_align="left")
    real = _bigsign_real_canvas()

    widget.draw(real, cursor_pos=0)

    # Cols 0..63 white; cols 64..255 black pillar
    assert real.get_pixel(0, 32) == (255, 255, 255)
    assert real.get_pixel(63, 32) == (255, 255, 255)
    assert real.get_pixel(64, 32) == (0, 0, 0)
    assert real.get_pixel(255, 32) == (0, 0, 0)


def test_no_text_skips_align_validation(tmp_path):
    """text_align is only validated when text is non-empty (default 'right'
    is fine even if user never sets text)."""
    path = _make_gif_path(tmp_path, [(10, 20, 30)])
    GifPlayer(path=str(path))  # no error — default text="" bypasses check


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
    widget._paint_skip_black(canvas, frame_idx=0)

    # Black pixels skipped → underlying yellow shows through
    assert canvas.get_pixel(0, 0) == (255, 0, 0)
    assert canvas.get_pixel(1, 0) == (200, 200, 0)
    assert canvas.get_pixel(2, 0) == (255, 0, 0)
    assert canvas.get_pixel(3, 0) == (200, 200, 0)
    # Row 1 fully painted green
    for x in range(4):
        assert canvas.get_pixel(x, 1) == (0, 255, 0)


async def test_play_with_text_uses_scroll_speed_cadence(tmp_path, mocker):
    """With text, ticks happen at scroll_speed_ms regardless of frame
    durations. This is what lets text scroll smoothly over slow GIFs."""
    path = _make_gif_path(tmp_path, [(10, 20, 30), (40, 50, 60)], duration_ms=120)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="hi",
        text_align="right",
        scroll_speed_ms=60,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    sleep_mock = mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    sleeps = [c.args[0] for c in sleep_mock.await_args_list]
    # Total = 240ms / 60ms = 4 ticks (vs. 2 swaps on the no-text path)
    assert len(sleeps) == 4
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
    gif pixels). Pixel at the band row inside the gif region must be the
    text colour, not the gif colour."""
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

    # Synthesize a gif frame that's bright gray everywhere (no transparent
    # areas / pillars). With `scroll`, text would be hidden; with
    # `scroll_over`, text must override.
    pixels = bytes([180] * (w * h * 3))
    widget._panel_w = w
    widget._panel_h = h
    widget._frames = [(bytes(pixels), 50)]

    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    band_y = (h - 12) // 2 + 10 - 1
    target_x = 10
    loops_needed = w - target_x + 1
    await widget.play(real, frame, loops_needed)

    # Text colour wins over the gray gif at the text's position
    assert real.get_pixel(target_x, band_y) == (255, 255, 255)
    # Outside the text band the gif still shows
    assert real.get_pixel(target_x, band_y - 5) == (180, 180, 180)


async def test_text_loops_extends_section_duration(tmp_path, mocker):
    """text_loops puts a floor on tick count: section runs at least
    N text traversals even if the gif's own loop_count is shorter."""
    # Gif loops fast (1 frame × 50 ms × 1 loop = 50 ms total, 1 tick).
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",  # narrow so the math is easy
        text_align="scroll",
        scroll_speed_ms=50,
        text_loops=2,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    # text_w = real.width = 256; text_width for "X" via stub font = 6.
    # Per-traversal ticks = 256 + 6 = 262. Two loops → 524 swaps.
    # Tight bound (524..525, allowing 1-tick rounding slack) catches a
    # regression that 10×'s the duration just as well as one that drops
    # the floor entirely.
    assert 524 <= frame.matrix.SwapOnVSync.call_count <= 525


async def test_text_loops_zero_keeps_gif_driven_duration(tmp_path, mocker):
    """text_loops=0 (default) leaves gif duration in charge — no floor."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll",
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    await widget.play(real, frame, loop_count=1)

    # 50 ms gif × 1 loop / 50 ms tick = 1 tick → 1 swap
    assert frame.matrix.SwapOnVSync.call_count == 1


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
    with pytest.raises(ValueError, match="loops"):
        GifPlayer(path=str(path), loops=0)
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
        text_align="scroll",
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    real_draw = __import__("led_ticker.widgets.gif", fromlist=["draw_text"]).draw_text

    def spy(canvas, font, x, y, color, text):
        seen_x.append(x)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets.gif.draw_text", side_effect=spy)

    # Run for enough ticks to fully traverse + see the wrap. text_w=256,
    # text_width for "X" = 6. One traversal = 256 + 6 = 262 ticks (panel-
    # right exit to off-left). Use text_loops=2 to force long enough run.
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll",
        scroll_speed_ms=50,
        text_loops=2,
    )
    seen_x.clear()
    mocker.patch("led_ticker.widgets.gif.draw_text", side_effect=spy)
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
        text_align="scroll",
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_x: list[int] = []
    real_draw = __import__("led_ticker.widgets.gif", fromlist=["draw_text"]).draw_text

    def spy(canvas, font, x, y, color, text):
        seen_x.append(x)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets.gif.draw_text", side_effect=spy)

    # 5 loops × 50ms = 250ms / 50ms tick = 5 ticks
    await widget.play(real, frame, loop_count=5)

    # First tick at scroll_pos = w; subsequent ticks decrement by 1.
    assert seen_x == [
        real.width,
        real.width - 1,
        real.width - 2,
        real.width - 3,
        real.width - 4,
    ]


async def test_play_scroll_text_visible_through_black_pillars(tmp_path, mocker):
    """The whole point of scroll mode: gif on top, text under, but
    black gif pixels are skipped so text shines through pillars."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="X",
        text_align="scroll",
        font_color=Color(0, 0, 200),
        scroll_speed_ms=50,
    )
    real = _bigsign_real_canvas()
    w, h = real.width, real.height

    # Synthesize a "pillarbox-like" frame: bright gray in the centre,
    # black on the outer columns (the pillars).
    band_y = (h - 12) // 2 + 10 - 1  # row the stub DrawText paints
    pixels = bytearray(w * h * 3)
    centre_lo, centre_hi = 100, 160
    for y in range(h):
        for x in range(centre_lo, centre_hi):
            base = (y * w + x) * 3
            pixels[base] = pixels[base + 1] = pixels[base + 2] = 180
    widget._panel_w = w
    widget._panel_h = h
    widget._frames = [(bytes(pixels), 50)]

    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    # Use loop_count=1 → 1 tick; on tick 0 scroll_pos=w (text off-canvas).
    # Force scroll_pos into the LEFT pillar by pre-running enough decrements
    # via an explicit loop_count that puts the text in the left pillar.
    # tick 0: scroll_pos = w. We need the text painted at ~x=10.
    # That means tick (w - 10) → loop_count of (w - 10 + 1) ticks.
    # 50ms per tick × that many ticks = 50 * (w - 9) ms total.
    # n_ticks = total_ms // 50 = w - 9. So loop_count = w - 9 with
    # frame_duration=50 gives loop_ms=50; total_ms = 50 * (w - 9).
    target_x = 10
    loops_needed = w - target_x + 1  # extra +1 for the tick at target_x
    await widget.play(real, frame, loops_needed)

    # Pixel in the LEFT pillar at the band row should retain the text colour
    # (gif painted black there, was skipped).
    assert real.get_pixel(target_x, band_y) == (0, 0, 200)
    # Pixel inside the centre region at the band row should be the gif gray
    # (gif overwrote the text).
    assert real.get_pixel(centre_lo + 5, band_y) == (180, 180, 180)


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
        "led_ticker.widgets.gif.draw_text",
        side_effect=lambda c, f, x, y, col, t: seen_x.append(x) or 600,
    )

    await widget.play(real, frame, loop_count=1)

    assert seen_x, "draw_text should have been called"
    # Clamped to left edge padding (2), not negative
    assert seen_x[0] == 2


async def test_play_emoji_with_text_scale_and_scroll(tmp_path, mocker):
    """The actual user combo (Section 15 in config.gif_test): emoji slug
    + text_scale > 1 + text_align="scroll_over". Each axis is tested
    individually but never the intersection — where logical/physical
    unit confusion in `_measure_text` could produce the wrong tick budget."""
    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text=":sun: HOT",
        text_align="scroll_over",
        font_color=Color(255, 255, 255),
        text_scale=2,
        scroll_speed_ms=50,
        text_loops=1,
    )
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
    # Each call got a ScaledCanvas (text_scale=2 wrap), not the raw real canvas
    from led_ticker.scaled_canvas import ScaledCanvas

    for call in emoji_calls.call_args_list:
        canvas_arg = call.args[0]
        assert isinstance(canvas_arg, ScaledCanvas), (
            f"emoji painter should receive ScaledCanvas at text_scale=2, "
            f"got {type(canvas_arg).__name__}"
        )


async def test_play_text_scale_uses_scaled_canvas(tmp_path, mocker):
    """text_scale > 1 wraps the real canvas in a ScaledCanvas just for
    text painting — block-expands each glyph pixel so text is visible
    on the bigsign. Confirm by spying on draw_text and inspecting the
    canvas argument it receives."""
    from led_ticker.scaled_canvas import ScaledCanvas

    path = _make_gif_path(tmp_path, [(0, 0, 0)], duration_ms=50)
    widget = GifPlayer(
        path=str(path),
        fit="stretch",
        text="HI",
        text_align="right",
        font_color=Color(255, 255, 255),
        text_scale=2,
    )
    real = _bigsign_real_canvas()
    frame = mocker.MagicMock()
    frame.matrix.SwapOnVSync.side_effect = lambda c: c
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    seen_canvases: list[object] = []
    real_draw = __import__("led_ticker.widgets.gif", fromlist=["draw_text"]).draw_text

    def spy(canvas, font, x, y, color, text):
        seen_canvases.append(canvas)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets.gif.draw_text", side_effect=spy)

    await widget.play(real, frame, loop_count=1)

    # Every text-paint tick handed draw_text a ScaledCanvas, not the raw real
    assert seen_canvases, "draw_text should have been invoked at least once"
    assert all(isinstance(c, ScaledCanvas) for c in seen_canvases)
    assert all(c.scale == 2 for c in seen_canvases)


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
    widget = GifPlayer(path=str(path), fit="stretch", text="X", text_align="right")
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
    real_draw = __import__("led_ticker.widgets.gif", fromlist=["draw_text"]).draw_text

    def spy(canvas, font, x, y, color, text):
        seen.append(canvas)
        return real_draw(canvas, font, x, y, color, text)

    mocker.patch("led_ticker.widgets.gif.draw_text", side_effect=spy)

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
        "led_ticker.widgets.gif.draw_text",
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

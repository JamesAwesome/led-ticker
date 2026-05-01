"""Tests for the :gif: widget — _load() lazy decode + draw() compositing."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions

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

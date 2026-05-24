"""Smoke test for Ticker.run_gif() — pulls a GifPlayer from the queue
and calls its play() method on the underlying real canvas."""

from __future__ import annotations

import asyncio
import io
from unittest import mock

from PIL import Image

from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.ticker import Ticker
from led_ticker.widgets.gif import GifPlayer


def _make_gif(tmp_path, n_frames=2, size=(32, 32), duration_ms=10):
    imgs = [Image.new("RGB", size, color=(50 * (i + 1), 0, 0)) for i in range(n_frames)]
    buf = io.BytesIO()
    imgs[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=imgs[1:],
        duration=duration_ms,
        loop=0,
    )
    p = tmp_path / "anim.gif"
    p.write_bytes(buf.getvalue())
    return p


async def test_run_gif_invokes_widget_play(tmp_path, mocker, bigsign_canvas):
    real = bigsign_canvas
    frame = mock.Mock()
    frame.get_clean_canvas.return_value = real
    frame.matrix.SwapOnVSync.side_effect = lambda c: c

    mocker.patch("asyncio.sleep", new=mock.AsyncMock())

    queue: asyncio.Queue = asyncio.Queue()
    widget = GifPlayer(path=str(_make_gif(tmp_path)), fit="stretch")

    ticker = Ticker(
        monitors=[widget],
        frame=frame,
        notif_queue=queue,
        scale=1,
    )

    await ticker.run_gif(loop_count=2)

    # 2 loops × 2 frames = 4 swaps issued by play()
    assert frame.matrix.SwapOnVSync.call_count == 4
    # And widget ended on the last frame
    assert widget._current_frame_idx == 1


async def test_run_gif_unwraps_scaled_canvas(tmp_path, mocker, bigsign_canvas):
    """When the section's scale > 1, the orchestrator must paint to the
    underlying real canvas, not the wrapper."""
    real = bigsign_canvas
    sc = ScaledCanvas(real, scale=4)
    frame = mock.Mock()
    frame.get_clean_canvas.return_value = sc
    frame.matrix.SwapOnVSync.side_effect = lambda c: c

    mocker.patch("asyncio.sleep", new=mock.AsyncMock())

    queue: asyncio.Queue = asyncio.Queue()
    widget = GifPlayer(path=str(_make_gif(tmp_path)), fit="stretch")

    ticker = Ticker(
        monitors=[widget],
        frame=frame,
        notif_queue=queue,
        scale=4,
    )

    await ticker.run_gif(loop_count=1)

    # Pixel at col 1 (mod 4 = 1, NOT block-aligned) lit on the real
    # canvas → proves we bypassed the wrapper.
    real_after = frame.matrix.SwapOnVSync.call_args.args[0]
    # Some non-zero pixel exists at a non-block-aligned col
    assert real_after.get_pixel(1, 1) != (0, 0, 0)


async def test_run_gif_enqueues_monitors_when_queue_empty(
    tmp_path, mocker, bigsign_canvas
):
    """Regression: run_gif must enqueue from self.monitors, not assume
    the queue is pre-populated. (The previous implementation skipped
    _build_then_enqueue and would deadlock in production.)"""
    real = bigsign_canvas
    frame = mock.Mock()
    frame.get_clean_canvas.return_value = real
    frame.matrix.SwapOnVSync.side_effect = lambda c: c

    mocker.patch("asyncio.sleep", new=mock.AsyncMock())

    queue: asyncio.Queue = asyncio.Queue()  # NOTE: NOT pre-populated
    widget = GifPlayer(path=str(_make_gif(tmp_path)), fit="stretch")

    ticker = Ticker(
        monitors=[widget],
        frame=frame,
        notif_queue=queue,
        scale=1,
    )

    await ticker.run_gif(loop_count=1)

    # 1 loop × 2 frames = 2 swaps — would be 0 if monitors weren't enqueued
    assert frame.matrix.SwapOnVSync.call_count == 2

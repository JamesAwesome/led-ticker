"""Tests for led_ticker.ticker."""

import asyncio
import contextlib
import itertools
import unittest.mock as mock
from unittest.mock import MagicMock

import pytest

from led_ticker.colors import RGB_WHITE
from led_ticker.frame import LedFrame
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.ticker import (
    _build_ticker_iter,
    _draw_hires_circle,
    _enqueue_ticker_objects,
    _has_index,
    _maybe_wrap,
    _scroll_one_by_one,
    _scroll_side_by_side,
    _swap,
)


def test_maybe_wrap_skips_wrap_when_canvas_fits():
    # Smallsign: panel_h == content_height == 16, scale=1 → no wrap needed.
    frame = LedFrame(led_cols=32, led_chain=5)
    canvas = frame.get_clean_canvas()
    # The stub canvas height is 32; use content_height=canvas.height so it fits.
    result = _maybe_wrap(canvas, scale=1, content_height=canvas.height)
    assert result is canvas
    assert not isinstance(result, ScaledCanvas)


def test_maybe_wrap_engages_when_content_height_smaller_than_panel():
    # Bigsign running at scale=1: panel_h=64, content_height=16 → must wrap
    # so widgets see canvas.height == 16 and content is vertically centered.
    frame = LedFrame(led_rows=32, led_cols=64, led_chain=8, led_pixel_mapper="U-mapper")
    canvas = frame.get_clean_canvas()
    assert canvas.height == 64  # sanity-check the test fixture
    result = _maybe_wrap(canvas, scale=1, content_height=16)
    assert isinstance(result, ScaledCanvas)
    assert result.scale == 1
    assert result.real is canvas
    assert result.height == 16


def test_maybe_wrap_returns_scaled_canvas_at_scale_4():
    frame = LedFrame(led_rows=32, led_cols=64, led_chain=8, led_pixel_mapper="U-mapper")
    canvas = frame.get_clean_canvas()
    result = _maybe_wrap(canvas, scale=4)
    assert isinstance(result, ScaledCanvas)
    assert result.scale == 4
    assert result.real is canvas


def test_swap_handles_real_canvas():
    frame = LedFrame(led_cols=32, led_chain=5)
    canvas = frame.get_clean_canvas()
    new_canvas = _swap(canvas, frame)
    # Stub returns a different canvas object on swap
    assert new_canvas is not None


def test_swap_handles_scaled_canvas_in_place():
    frame = LedFrame(led_rows=32, led_cols=64, led_chain=8, led_pixel_mapper="U-mapper")
    canvas = frame.get_clean_canvas()
    wrapper = ScaledCanvas(canvas, scale=4)
    original_real = wrapper.real
    result = _swap(wrapper, frame)
    # Returns the same wrapper object, but its `.real` was swapped
    assert result is wrapper
    assert wrapper.real is not original_real


def test_has_index_true():
    assert _has_index(0, [1, 2, 3]) is True
    assert _has_index(2, [1, 2, 3]) is True


def test_has_index_false():
    assert _has_index(5, [1, 2, 3]) is False
    assert _has_index(0, []) is False


class TestBuildTickerIter:
    def test_loop_count_1(self):
        items = [1, 2, 3]
        result = list(_build_ticker_iter(items, loop_count=1))
        assert result == [1, 2, 3]

    def test_loop_count_2(self):
        items = [1, 2, 3]
        result = list(_build_ticker_iter(items, loop_count=2))
        assert result == [1, 2, 3, 1, 2, 3]

    def test_loop_count_0_cycles(self):
        items = [1, 2, 3]
        it = _build_ticker_iter(items, loop_count=0)
        result = list(itertools.islice(it, 9))
        assert result == [1, 2, 3, 1, 2, 3, 1, 2, 3]

    def test_with_title(self):
        items = [1, 2]
        result = list(_build_ticker_iter(items, title="title", loop_count=1))
        assert result == ["title", 1, 2]

    def test_with_title_and_cycle(self):
        items = [1, 2]
        it = _build_ticker_iter(items, title="title", loop_count=0)
        result = list(itertools.islice(it, 5))
        assert result == ["title", 1, 2, 1, 2]


class TestEnqueueTickerObjects:
    async def test_enqueues_all(self):
        queue = asyncio.Queue()
        items = [1, 2, 3]
        it = iter(items)

        asyncio.create_task(_enqueue_ticker_objects(it, queue))
        results = []
        results.append(await queue.get())

        while not queue.empty():
            results.append(await queue.get())
            await asyncio.sleep(0.01)

        assert results == items

    async def test_enqueues_with_title(self):
        queue = asyncio.Queue()
        it = _build_ticker_iter([1, 2], title="T", loop_count=1)

        asyncio.create_task(_enqueue_ticker_objects(it, queue))
        results = []
        results.append(await queue.get())

        while not queue.empty():
            results.append(await queue.get())
            await asyncio.sleep(0.01)

        assert results == ["T", 1, 2]


@pytest.fixture
def no_sleep(monkeypatch):
    _real_sleep = asyncio.sleep

    async def _fast(seconds):
        await _real_sleep(0)

    monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _fast)


def _make_widget(content_width: int = 40, end_padding: int = 6):
    """Mock widget that mimics TickerMessage's draw return contract:
    cursor_pos returned = pos + content_width + end_padding.
    """
    w = mock.Mock()
    w.draw.side_effect = lambda c, cursor_pos=0, **kw: (
        c,
        cursor_pos + content_width + end_padding,
    )
    return w


class TestScrollSideBySideBufferDrawn:
    """Regression test: when the queue serves a new monitor, the
    buffer_message must NOT be skipped on the first frame after the pull.

    Previously the inner loop's `mon_index += 1` jumped past the
    just-appended buffer's index, so the next_monitor was drawn at the
    title's end (no spacing) for one frame — visible as a single-column
    yellow bar at the right edge of the panel.
    """

    async def test_buffer_drawn_on_first_pull_frame(self, no_sleep):
        # Title that, after one decrement, leaves room for next widget.
        title = _make_widget(content_width=40)  # returns pos + 46
        next_monitor = _make_widget(content_width=20)
        buffer_msg = _make_widget(content_width=10)

        canvas = mock.Mock()
        canvas.width = 64
        canvas.Clear = mock.Mock()

        frame = mock.Mock()
        frame.matrix.SwapOnVSync = mock.Mock(return_value=canvas)

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put(title)
        await queue.put(next_monitor)

        # Run a few iterations then cancel
        async def runner():
            await _scroll_side_by_side(
                canvas,
                frame,
                queue,
                buffer_message=buffer_msg,
                cursor_pos=18,  # title at pos=18, end at 64; next iter end at 63
                scroll_speed=0,
                hold_at_end=0,
            )

        task = asyncio.create_task(runner())
        # let a few iterations run
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # The buffer_message MUST have been drawn at least once.
        assert buffer_msg.draw.called, (
            "buffer_message was never drawn — the inner loop is skipping "
            "the just-appended buffer index, causing the 'yellow flash' bug."
        )


def test_draw_hires_circle_paints_filled_disk_on_scaled_canvas():
    """The disk fills a 32x32 physical bounding box centered in the
    content band, with the documented row-half-widths."""
    real = MagicMock()
    real.width = 256
    real.height = 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    # canvas._y_offset = (64 - 16*4) // 2 = 0

    out_canvas, cursor = _draw_hires_circle(canvas, cursor_pos=0, color=RGB_WHITE)

    assert out_canvas is canvas
    assert cursor == 10  # logical advance width

    # All SetPixel calls landed on the underlying real canvas
    # (constraint #11 — paint at physical resolution).
    assert real.SetPixel.called
    assert canvas is not None

    # Pixel set lives in a 32x32 physical bounding box. Cursor=0 puts
    # the circle at x=0 logical → x=4..36 physical (1px pad + 32px disk;
    # the disk extends from center-radius to center+radius, which is
    # (1*4)+16=20 ± 16 = [4,36]). y in [16, 48] physical (center at
    # 0 + (16*4)//2 = 32 ± 16 = [16,48]).
    coords = {(c.args[0], c.args[1]) for c in real.SetPixel.call_args_list}
    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    assert min(xs) >= 4 and max(xs) <= 36, f"x out of [4,36]: {min(xs)}..{max(xs)}"
    assert min(ys) >= 16 and max(ys) <= 48, f"y out of [16,48]: {min(ys)}..{max(ys)}"

    # Disk count is ~π * 16² ≈ 804. Allow ±5% for integer-math rounding.
    assert 760 <= len(coords) <= 850, f"disk pixel count {len(coords)} out of range"


def test_draw_hires_circle_color_applied_uniformly():
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    _draw_hires_circle(canvas, cursor_pos=0, color=(225, 48, 108))

    for call in real.SetPixel.call_args_list:
        _, _, r, g, b = call.args
        assert (r, g, b) == (225, 48, 108)


@pytest.mark.parametrize("scale", [1, 4])
def test_draw_hires_circle_advance_is_ten_at_any_scale(scale):
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=scale, content_height=16)
    _, cursor = _draw_hires_circle(canvas, cursor_pos=42, color=RGB_WHITE)
    assert cursor == 42 + 10


class TestScrollOneByOneReturnsLastPos:
    """Regression: `_scroll_one_by_one` must return the position at which
    the last widget was drawn, so `Ticker.last_scroll_pos` reflects reality
    instead of staying at its 0 default. Without this, the inter-section
    dissolve in app.py renders the outgoing widget at pos=0 (a one-frame
    flash-back of the widget reappearing center-canvas before the dissolve
    begins).
    """

    async def test_returns_negative_pos_after_widget_exits_left(self, no_sleep):
        widget = _make_widget(content_width=20)
        canvas = mock.Mock()
        canvas.width = 64
        canvas.Clear = mock.Mock()
        frame = mock.Mock()
        frame.matrix.SwapOnVSync = mock.Mock(return_value=canvas)

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put(widget)

        result = await _scroll_one_by_one(
            canvas,
            frame,
            queue,
            cursor_pos=0,
            scroll_speed=0,
        )
        # Widget exits left -> last_drawn_pos should be heavily negative
        # (specifically, at most -content_width so the widget is fully
        # off-canvas left).
        assert result < 0, (
            "Expected last_drawn_pos < 0 once the widget scrolls off the "
            f"left edge; got {result}. The dissolve will draw the outgoing "
            "widget at pos=0 (flash-back bug) instead of off-screen."
        )

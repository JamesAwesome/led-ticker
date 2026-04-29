"""Tests for led_ticker.ticker."""

import asyncio
import itertools

from led_ticker.frame import LedFrame
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.ticker import (
    _build_ticker_iter,
    _enqueue_ticker_objects,
    _has_index,
    _maybe_wrap,
    _swap,
)


def test_maybe_wrap_returns_real_canvas_at_scale_1():
    frame = LedFrame(led_cols=32, led_chain=5)
    canvas = frame.get_clean_canvas()
    result = _maybe_wrap(canvas, scale=1)
    assert result is canvas
    assert not isinstance(result, ScaledCanvas)


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

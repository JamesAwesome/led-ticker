"""Tests for led_ticker.ticker."""

import asyncio
import itertools

from led_ticker.ticker import (
    _build_ticker_iter,
    _enqueue_ticker_objects,
    _has_index,
)


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

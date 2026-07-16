"""Producer backpressure (#394): the notif queue is bounded so gate
evaluation in _build_ticker_iter's per-pass expansion tracks DISPLAY time
instead of running unboundedly ahead at enqueue time."""

import asyncio
import itertools

import pytest

from led_ticker.ticker import (
    TICKER_QUEUE_MAXSIZE,
    _enqueue_ticker_objects,
)


def test_maxsize_constant():
    assert TICKER_QUEUE_MAXSIZE == 2


def test_run_loop_constructs_bounded_queue():
    """Source tripwire (house AST-tripwire style): the run loop's queue
    construction must pass maxsize=TICKER_QUEUE_MAXSIZE — the behavior
    tests below build their own queues, so this is the pin that the REAL
    wiring is bounded. A bare `asyncio.Queue()` reintroduces #394."""
    import inspect

    from led_ticker.app import run as run_mod

    src = inspect.getsource(run_mod)
    assert "maxsize=TICKER_QUEUE_MAXSIZE" in src
    assert "notif_queue: asyncio.Queue[Any] = asyncio.Queue()" not in src


async def _drain_n(queue, n, per_item_delay=0.01):
    got = []
    for _ in range(n):
        item = await queue.get()
        got.append(item)
        await asyncio.sleep(per_item_delay)
    return got


@pytest.mark.asyncio
async def test_queue_depth_never_exceeds_maxsize():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(
        _enqueue_ticker_objects(itertools.count(), queue)  # infinite iterator
    )
    try:
        max_seen = 0
        for _ in range(20):
            await asyncio.sleep(0.005)
            max_seen = max(max_seen, queue.qsize())
            if not queue.empty():
                queue.get_nowait()
        assert max_seen <= TICKER_QUEUE_MAXSIZE
    finally:
        producer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await producer


@pytest.mark.asyncio
async def test_sentinel_arrives_last_on_finite_iterator():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(
        _enqueue_ticker_objects(iter([1, 2, 3, 4, 5]), queue)
    )
    got = await _drain_n(queue, 6)
    await producer
    assert got == [1, 2, 3, 4, 5, None]


@pytest.mark.asyncio
async def test_cancel_while_parked_in_put_unwinds_cleanly():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(itertools.count(), queue))
    await asyncio.sleep(0.01)  # producer fills the queue and parks in put()
    assert queue.full()
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(producer, timeout=1.0)  # no hang


@pytest.mark.asyncio
async def test_gating_tracks_display_time():
    """The #394 headline: a visibility flip mid-'section' reaches the
    consumer within maxsize+1 items, instead of being buried behind an
    unbounded backlog of pre-gated items."""

    class _FlippingWidget:
        def __init__(self):
            self.visible = True

        def should_display(self):
            return self.visible

    w = _FlippingWidget()

    def passes():
        # Mimics _build_ticker_iter's cycle_with_refresh: re-evaluate the
        # gate every pass, stop yielding when it goes false.
        from led_ticker.ticker import _expand_sources

        while True:
            widgets = _expand_sources([w])
            if not widgets:
                return
            yield from widgets

    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(passes(), queue))
    # Consume 3 items, then flip the widget invisible.
    await _drain_n(queue, 3)
    w.visible = False
    # The sentinel must arrive within maxsize+2 further gets. asyncio.Queue's
    # put() only suspends once the queue is actually full — it never yields
    # when space exists — so the producer is always one item further ahead
    # than what's queued: up to `maxsize` items sitting in the queue plus
    # exactly one more already gated and blocked in an in-flight put(). That
    # whole backlog (maxsize + 1 stale items, all gated before the flip)
    # must drain before the *next* evaluation — the first one to see the
    # flip — can even run, let alone be retrieved.
    tail = await asyncio.wait_for(
        _drain_n(queue, TICKER_QUEUE_MAXSIZE + 2), timeout=2.0
    )
    await producer
    assert None in tail

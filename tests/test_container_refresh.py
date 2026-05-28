"""Tripwire tests for the live container refresh contract.

The engine MUST re-expand `Container` widgets on every pass through a
section. Snapshotting at section-build time produces the stale-display
bug fixed in 2026-05-28.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib

import pytest

from led_ticker.ticker import _build_ticker_iter, _expand_sources

APP_RUN_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "led_ticker"
    / "app"
    / "run.py"
)


class FakeContainer:
    """Minimal Container Protocol implementer for engine tests."""

    def __init__(self, stories: list[str]) -> None:
        self.feed_stories: list[str] = list(stories)


def test_expand_sources_passes_statics_through() -> None:
    """Non-Container items appear in output unchanged."""
    static_a = object()
    static_b = object()
    result = _expand_sources([static_a, static_b])
    assert result == [static_a, static_b]


def test_expand_sources_expands_containers() -> None:
    """Container items are replaced by their current feed_stories."""
    container = FakeContainer(["a", "b", "c"])
    result = _expand_sources([container])
    assert result == ["a", "b", "c"]


def test_expand_sources_mixed_order_preserved() -> None:
    static = object()
    container = FakeContainer(["x", "y"])
    result = _expand_sources([static, container, static])
    assert result == [static, "x", "y", static]


def test_expand_sources_reflects_mutation() -> None:
    """Mutating feed_stories AFTER the first expand changes the next expand."""
    container = FakeContainer(["v1"])
    first = _expand_sources([container])
    assert first == ["v1"]

    container.feed_stories = ["v2", "v2b"]
    second = _expand_sources([container])
    assert second == ["v2", "v2b"]


def test_expand_sources_empty_container_yields_nothing() -> None:
    container = FakeContainer([])
    result = _expand_sources([container])
    assert result == []


def test_build_ticker_iter_loop_zero_refreshes_each_cycle() -> None:
    """loop_count=0 must re-expand container on every pass — this is the
    fix for the longboi stale-display bug (2026-05-28). Snapshotting on
    first cycle would yield 'v1' forever.
    """
    container = FakeContainer(["v1"])
    ticker_iter = _build_ticker_iter([container], title=None, loop_count=0)

    # First pull: original story
    assert next(ticker_iter) == "v1"

    # Mutate container — simulates update() reassigning feed_stories
    container.feed_stories = ["v2"]

    # Next pull: new story, NOT a cached snapshot of "v1"
    assert next(ticker_iter) == "v2"


def test_build_ticker_iter_loop_zero_empty_container_terminates() -> None:
    """Empty container must terminate the iterator, not hot-loop.
    The outer section loop will then cycle to the next section.
    """
    container = FakeContainer([])
    ticker_iter = _build_ticker_iter([container], title=None, loop_count=0)
    assert list(ticker_iter) == []


def test_build_ticker_iter_loop_n_refreshes_between_passes() -> None:
    """loop_count=N expands once per pass — pass 2 sees mutations from pass 1."""
    container = FakeContainer(["a"])
    ticker_iter = _build_ticker_iter([container], title=None, loop_count=3)

    # Pass 1
    assert next(ticker_iter) == "a"
    # Mutate before pass 2
    container.feed_stories = ["b"]
    assert next(ticker_iter) == "b"
    # Mutate before pass 3
    container.feed_stories = ["c"]
    assert next(ticker_iter) == "c"
    # Exhausted after 3 passes
    with pytest.raises(StopIteration):
        next(ticker_iter)


def test_build_ticker_iter_title_prepended_once() -> None:
    """Title leads the iterator and does NOT repeat each cycle."""
    container = FakeContainer(["a", "b"])
    title = object()
    ticker_iter = _build_ticker_iter([container], title=title, loop_count=2)

    items = list(ticker_iter)
    assert items[0] is title
    assert items[1:] == ["a", "b", "a", "b"]


def test_build_ticker_iter_loop_zero_no_title_cycles_widgets() -> None:
    """Sanity: cycle continues with static widgets across passes."""
    ticker_iter = _build_ticker_iter(["x", "y"], title=None, loop_count=0)
    pulled = [next(ticker_iter) for _ in range(5)]
    assert pulled == ["x", "y", "x", "y", "x"]


def test_app_run_passes_containers_to_ticker_unexpanded() -> None:
    """app/run.py must push containers as-is into Ticker.monitors so the
    engine can re-expand them per cycle. Pre-expanding here defeats the
    refresh — see _build_ticker_iter.

    This is a source-level tripwire: it scans app/run.py to ensure the
    pre-expansion stanza removed in 2026-05-28 doesn't come back.
    """
    src = APP_RUN_PATH.read_text()
    tree = ast.parse(src)

    # Walk for any `widgets.extend(<x>.feed_stories)` call
    class ExtendVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found = False

        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "extend"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "widgets"
                and node.args
                and isinstance(node.args[0], ast.Attribute)
                and node.args[0].attr == "feed_stories"
            ):
                self.found = True
            self.generic_visit(node)

    visitor = ExtendVisitor()
    visitor.visit(tree)
    assert not visitor.found, (
        "app/run.py must not pre-expand widget.feed_stories — "
        "the engine re-expands containers per cycle via _expand_sources. "
        "See docs/superpowers/plans/2026-05-28-live-container-refresh.md."
    )


async def test_enqueue_ticker_objects_handles_empty_iterator() -> None:
    """An immediately-empty iterator (empty container + loop_count=0)
    must terminate cleanly AND put a `None` sentinel on the queue so
    blocking consumers (`await notif_queue.get()` in `_run_swap` etc.)
    wake up and return instead of hanging forever.
    """
    from led_ticker.ticker import _enqueue_ticker_objects

    queue: asyncio.Queue[object] = asyncio.Queue()
    empty_iter = iter([])

    # Should return without raising
    await _enqueue_ticker_objects(empty_iter, queue)

    # Sentinel must be on the queue so consumers wake up.
    assert queue.qsize() == 1
    assert queue.get_nowait() is None


async def test_enqueue_ticker_objects_puts_sentinel_after_exhaustion() -> None:
    """A non-empty iterator must still emit a `None` sentinel after the
    final real item so consumers know the producer is done.
    """
    from led_ticker.ticker import _enqueue_ticker_objects

    queue: asyncio.Queue[object] = asyncio.Queue()
    items_iter = iter(["a", "b"])

    await _enqueue_ticker_objects(items_iter, queue)

    assert queue.get_nowait() == "a"
    assert queue.get_nowait() == "b"
    assert queue.get_nowait() is None
    assert queue.empty()


async def test_run_swap_terminates_on_empty_source_list() -> None:
    """Empty section (no widgets, no title) must not hang the engine —
    the enqueue sentinel + consumer-side guard cleanly end the section.

    Regression test for the live-container-refresh hang: pre-fix, the
    producer's StopIteration guard returned silently and the consumer
    blocked forever on `await notif_queue.get()`.
    """
    import asyncio as _asyncio

    from led_ticker.ticker import Ticker, _build_then_enqueue

    # Build a Ticker with no monitors and no title.
    queue: _asyncio.Queue[object] = _asyncio.Queue()
    ticker = Ticker(
        monitors=[],
        frame=None,  # _run_swap doesn't dispatch through frame on empty
        title=None,
        notif_queue=queue,
    )

    # Spawn the producer (will immediately put a None sentinel).
    producer = _asyncio.create_task(
        _build_then_enqueue([], queue, title=None, loop_count=1)
    )

    # _run_swap should observe the sentinel on its first get() and
    # return 0 immediately — wrap in wait_for to fail loud on hang.
    result = await _asyncio.wait_for(
        ticker._run_swap(canvas=None, delay=0, hold_time=0, continuous_scroll=False),
        timeout=2.0,
    )
    assert result == 0
    await producer

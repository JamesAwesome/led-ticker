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
    must terminate cleanly — without the StopIteration guard, PEP 479
    promotes it to RuntimeError inside this async function.
    """
    from led_ticker.ticker import _enqueue_ticker_objects

    queue: asyncio.Queue[object] = asyncio.Queue()
    empty_iter = iter([])

    # Should return without raising
    await _enqueue_ticker_objects(empty_iter, queue)

    assert queue.empty()

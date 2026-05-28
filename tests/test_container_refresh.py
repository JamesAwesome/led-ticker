"""Tripwire tests for the live container refresh contract.

The engine MUST re-expand `Container` widgets on every pass through a
section. Snapshotting at section-build time produces the stale-display
bug fixed in 2026-05-28.
"""

from __future__ import annotations

from led_ticker.ticker import _expand_sources


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

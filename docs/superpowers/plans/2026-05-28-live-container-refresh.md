# Live Container Refresh — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix stale-display bug where `MLBScoreMonitor` / `MLBStandingsMonitor` / `RSSFeedMonitor` data freezes at section-build time when `loop_count = 0`. Make container widgets a first-class engine concept, and add INFO/DEBUG logging that proves whether updates are reaching the panel.

**Architecture:** Today `app/run.py` pre-expands `widget.feed_stories` into the engine's `widgets` list, and `_build_ticker_iter` calls `itertools.cycle(widgets)` for `loop_count = 0`. The cycle permanently snapshots — even though `update()` rebuilds `feed_stories` every ~5 min in the background, the engine never sees it. Refactor: define a `Container` Protocol, push containers (not their stories) into the engine, and have the engine re-expand sources on every pass through the section. Symmetric for finite `loop_count = N`. No widget-side logic changes; the fix lives at the engine boundary.

**Tech Stack:** Python asyncio, attrs, pytest, `typing.Protocol`, `runtime_checkable`.

---

## Background

Symptom: longboi MLB scoreboard frozen on last night's live half-inning for 11+ hours. Logs show only the three startup `MLB <TEAM>: N stories` lines, then silence. Container has been running, schedule API is reachable, `update()` is firing on its 5-min timer (silent because it only logs on errors).

Root cause: `src/led_ticker/ticker.py:1012`:
```python
if loop_count:
    ticker_iter = itertools.chain(ticker_objects * loop_count)
else:
    ticker_iter = itertools.cycle(ticker_objects)
```
plus `src/led_ticker/app/run.py:94-103`:
```python
if isinstance(widget, RSSFeedMonitor | MLBScoreMonitor | MLBStandingsMonitor):
    widgets.extend(widget.feed_stories)
else:
    widgets.append(widget)
```

`widgets.extend(feed_stories)` copies references at section build. `itertools.cycle` snapshots that list on first iteration and yields from the snapshot forever. Background `update()` reassigns `self.feed_stories = stories` — new objects, but neither `widgets` nor cycle's internal cache sees them. With `loop_count = 0` the section never returns control to the outer loop, so the snapshot is permanent.

Same bug, smaller impact, with `loop_count > 0`: the section refreshes on cycle-back, so staleness ≤ section playtime + update interval. With `loop_count = 0` staleness is unbounded.

Affects three widgets that share the `feed_stories: list[Widget]` pattern: `MLBScoreMonitor`, `MLBStandingsMonitor`, `RSSFeedMonitor`.

## Design

### `Container` Protocol

Add to `src/led_ticker/widget.py` alongside `Updatable`, `Playable`, `FrameAwareWidget`:

```python
@runtime_checkable
class Container(Protocol):
    """Widget that expands into a live, mutable list of child widgets.

    The engine re-reads `feed_stories` on every pass through the section,
    so updates from the container's `update()` task are picked up without
    requiring the outer section loop to cycle.
    """
    feed_stories: list[Widget]
```

The three existing containers already have this field — they satisfy the Protocol structurally, no changes needed in widget code.

### Engine: `_expand_sources`

Add to `src/led_ticker/ticker.py` (module level, near `_build_ticker_iter`):

```python
def _expand_sources(sources: list[Any]) -> list[Any]:
    """Expand `Container` widgets into their current `feed_stories`;
    pass non-containers through unchanged. Called once per pass through
    a section — re-reading `feed_stories` here is what keeps the displayed
    content in sync with each container's background `update()` task.
    """
    from led_ticker.widget import Container

    out: list[Any] = []
    for s in sources:
        if isinstance(s, Container):
            out.extend(s.feed_stories)
        else:
            out.append(s)
    return out
```

### `_build_ticker_iter` — re-expand per pass

Replace `itertools.cycle` / `itertools.chain` with explicit per-pass expansion:

```python
def _build_ticker_iter(
    ticker_objects: list[Any],
    title: Any = None,
    loop_count: int = 0,
) -> Iterator[Any]:
    n_sources = len(ticker_objects)

    if loop_count:
        def passes() -> Iterator[Any]:
            for pass_idx in range(loop_count):
                widgets = _expand_sources(ticker_objects)
                logger.debug(
                    "section pass %d/%d: %d sources → %d widgets",
                    pass_idx + 1, loop_count, n_sources, len(widgets),
                )
                yield from widgets
        ticker_iter: Iterator[Any] = passes()
    else:
        def cycle_with_refresh() -> Iterator[Any]:
            pass_idx = 0
            while True:
                widgets = _expand_sources(ticker_objects)
                logger.debug(
                    "section cycle %d: %d sources → %d widgets",
                    pass_idx, n_sources, len(widgets),
                )
                if not widgets:
                    return  # avoid hot loop; section ends, outer loop cycles
                yield from widgets
                pass_idx += 1
        ticker_iter = cycle_with_refresh()

    if title:
        ticker_iter = itertools.chain([title], ticker_iter)

    return ticker_iter
```

### `app/run.py` — stop pre-expanding

Replace the isinstance/extend stanza at `src/led_ticker/app/run.py:94-103` with:

```python
widgets.append(widget)
```

Containers and statics both go through unchanged. `_expand_sources` handles the difference inside the engine.

### Logging plan

Two log points, two levels.

**INFO — per `update()` success.** Already present in `start()`; mirror it at the end of every `update()` so the timer fires get logged. Format: `MLB <TEAM> updated: N stories (live: M)` for MLB scores, `MLB standings updated: N stories` for standings, `RSS <feed_url> updated: N stories` for RSS. INFO so users see it without `--debug`. Cadence: once per `update_interval` per container (~5 min for MLB). Cheap.

**DEBUG — per cycle pass.** Already specified above in `_build_ticker_iter`. Format: `section cycle N: M sources → K widgets`. DEBUG because it fires every hold (~6s) which is too chatty for INFO. Users debugging "is the engine actually re-reading?" enable DEBUG.

Diagnostic flow for "is data refreshing?":
- No INFO logs after startup → `run_monitor_loop` isn't running OR `update()` is erroring (errors already log via `logger.exception`)
- INFO logs firing but panel stale → engine snapshot bug back (this refactor's regression)
- DEBUG cycle logs firing AND widget counts changing → working correctly

### Concurrency / asyncio analysis

`_expand_sources` does no I/O and no `await`. It runs synchronously between event-loop yields. `update()` ends with `self.feed_stories = stories` — a single atomic Python attribute write. Race-free.

The producer (`update()` in background task) and the consumer (`_expand_sources` in main coroutine) communicate via attribute reassignment. No queue, no lock, no `asyncio.Event` needed. Either side may run between the other's `await` points; the reader always sees a complete list (old or new), never half-written.

Max staleness becomes `update_interval + one_section_pass`. For longboi (hold_time=6s, ~4 widgets per container, 2 containers): ~50s + ~5min = ~6 min worst case. Vs. infinite today.

### Files touched

- Create: `tests/test_container_refresh.py` — behavioral tripwire tests for the engine refresh contract
- Modify: `src/led_ticker/widget.py` — add `Container` Protocol
- Modify: `src/led_ticker/ticker.py` — add `_expand_sources`; rewrite `_build_ticker_iter`; add DEBUG log
- Modify: `src/led_ticker/app/run.py` — stop pre-expanding containers
- Modify: `src/led_ticker/widgets/mlb.py` — add INFO log at end of `update()`
- Modify: `src/led_ticker/widgets/mlb_standings.py` — add INFO log at end of `update()`
- Modify: `src/led_ticker/widgets/rss_feed.py` — add INFO log at end of `update()`
- Modify: `CLAUDE.md` — document the live-container-refresh invariant under a new "Container widgets" subsection

### Out of scope

- Renaming `feed_stories` — name's fine; rename is churn.
- Converting containers to `Playable` widgets that own internal transitions — much larger blast radius, loses section-level transition control.
- Updating `Ticker.from_rss_feed` (only used by tests; production goes through `app/run.py`). Tests using it can be updated case-by-case if they hit the new path; not required for the bug fix.
- Adding `feed_stories_updated_at: datetime` timestamps for staleness UI. Goldplating.

---

### Task 1: Add `Container` Protocol

**Files:**
- Modify: `src/led_ticker/widget.py`
- Test: `tests/test_widget_protocol.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_widget_protocol.py`:

```python
def test_container_protocol_recognizes_mlb_monitor() -> None:
    """MLBScoreMonitor exposes feed_stories — must satisfy Container."""
    from unittest.mock import MagicMock

    from led_ticker.widget import Container
    from led_ticker.widgets.mlb import MLBScoreMonitor

    # Build with attrs.define defaults — feed_stories factory=list satisfies the field
    monitor = MLBScoreMonitor(session=MagicMock(), team="NYM")
    assert isinstance(monitor, Container)


def test_container_protocol_recognizes_rss_monitor() -> None:
    from unittest.mock import MagicMock

    from led_ticker.widget import Container
    from led_ticker.widgets.rss_feed import RSSFeedMonitor

    monitor = RSSFeedMonitor(session=MagicMock(), feed_url="http://example.com/feed")
    assert isinstance(monitor, Container)


def test_container_protocol_recognizes_standings_monitor() -> None:
    from unittest.mock import MagicMock

    from led_ticker.widget import Container
    from led_ticker.widgets.mlb_standings import MLBStandingsMonitor

    monitor = MLBStandingsMonitor(session=MagicMock(), teams=["NYM"])
    assert isinstance(monitor, Container)


def test_container_protocol_rejects_plain_widget() -> None:
    """TickerMessage has no feed_stories — must NOT satisfy Container."""
    from led_ticker.widget import Container
    from led_ticker.widgets.message import TickerMessage

    msg = TickerMessage("hello")
    assert not isinstance(msg, Container)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test ARGS="tests/test_widget_protocol.py -v -k container"`
Expected: `ImportError: cannot import name 'Container'` on all four tests.

- [ ] **Step 3: Add the Protocol**

Edit `src/led_ticker/widget.py`. Add after the `FrameAwareWidget` Protocol:

```python
@runtime_checkable
class Container(Protocol):
    """Widget that expands into a live, mutable list of child widgets.

    The engine re-reads `feed_stories` on every pass through the section,
    so updates from the container's background `update()` task are picked
    up without requiring the outer section loop to cycle. Without this,
    a `loop_count = 0` section would snapshot stories at section-build
    time and never refresh.
    """

    feed_stories: list[Widget]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make test ARGS="tests/test_widget_protocol.py -v -k container"`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widget.py tests/test_widget_protocol.py
git commit -m "$(cat <<'EOF'
feat: add Container Protocol for live-refresh widgets

Defines `Container` Protocol for widgets that expose a mutable
`feed_stories: list[Widget]` rebuilt by a background `update()` task.
The engine will use this to re-expand containers on every pass through
a section, fixing the stale-display bug where loop_count=0 sections
froze on section-build-time snapshots.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add `_expand_sources` engine helper

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Test: `tests/test_container_refresh.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_container_refresh.py`:

```python
"""Tripwire tests for the live container refresh contract.

The engine MUST re-expand `Container` widgets on every pass through a
section. Snapshotting at section-build time produces the stale-display
bug fixed in 2026-05-28.
"""
from __future__ import annotations

import asyncio
import pytest

from led_ticker.ticker import _build_ticker_iter, _expand_sources


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test ARGS="tests/test_container_refresh.py -v"`
Expected: `ImportError: cannot import name '_expand_sources'` on all five.

- [ ] **Step 3: Implement `_expand_sources`**

In `src/led_ticker/ticker.py`, add ABOVE `_build_ticker_iter` (around line 1005):

```python
def _expand_sources(sources: list[Any]) -> list[Any]:
    """Expand `Container` widgets into their current `feed_stories`;
    pass non-containers through unchanged. Called once per pass through
    a section — re-reading `feed_stories` here is what keeps the displayed
    content in sync with each container's background `update()` task.
    """
    from led_ticker.widget import Container

    out: list[Any] = []
    for s in sources:
        if isinstance(s, Container):
            out.extend(s.feed_stories)
        else:
            out.append(s)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make test ARGS="tests/test_container_refresh.py -v"`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_container_refresh.py
git commit -m "$(cat <<'EOF'
feat: add _expand_sources engine helper for live containers

Centralizes the container→stories expansion in one place so it can be
called once per pass through a section. Containers identified by
isinstance(s, Container) Protocol; non-containers pass through.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Rewrite `_build_ticker_iter` to re-expand per pass

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Test: `tests/test_container_refresh.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_container_refresh.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify the new ones fail (refresh tests fail; static cycle test may pass)**

Run: `make test ARGS="tests/test_container_refresh.py -v"`
Expected: `test_build_ticker_iter_loop_zero_refreshes_each_cycle` FAILS (today returns "v1" twice because of `itertools.cycle` snapshot); `test_build_ticker_iter_loop_n_refreshes_between_passes` FAILS likewise.

- [ ] **Step 3: Rewrite `_build_ticker_iter`**

Replace `_build_ticker_iter` in `src/led_ticker/ticker.py` (around line 1007). Current:

```python
def _build_ticker_iter(
    ticker_objects: list[Any],
    title: Any = None,
    loop_count: int = 0,
) -> Any:
    if loop_count:
        ticker_iter = itertools.chain(ticker_objects * loop_count)
    else:
        ticker_iter = itertools.cycle(ticker_objects)

    if title:
        ticker_iter = itertools.chain([title], ticker_iter)

    return ticker_iter
```

New:

```python
def _build_ticker_iter(
    ticker_objects: list[Any],
    title: Any = None,
    loop_count: int = 0,
) -> Iterator[Any]:
    """Build the engine's per-tick iterator over a section's widgets.

    `ticker_objects` may contain `Container` widgets — they are
    expanded into their current `feed_stories` on EVERY pass through
    the section. Snapshotting at first pass would freeze the displayed
    content even though container `update()` tasks keep running (the
    longboi stale-display bug, 2026-05-28).

    `loop_count=0` cycles forever; `loop_count=N` makes exactly N passes.
    Either way, each pass calls `_expand_sources` so live updates land
    on the panel within at most one cycle of latency.

    `title` is prepended ONCE (not repeated per pass).
    """
    n_sources = len(ticker_objects)

    if loop_count:
        def passes() -> Iterator[Any]:
            for pass_idx in range(loop_count):
                widgets = _expand_sources(ticker_objects)
                logger.debug(
                    "section pass %d/%d: %d sources → %d widgets",
                    pass_idx + 1, loop_count, n_sources, len(widgets),
                )
                yield from widgets
        ticker_iter: Iterator[Any] = passes()
    else:
        def cycle_with_refresh() -> Iterator[Any]:
            pass_idx = 0
            while True:
                widgets = _expand_sources(ticker_objects)
                logger.debug(
                    "section cycle %d: %d sources → %d widgets",
                    pass_idx, n_sources, len(widgets),
                )
                if not widgets:
                    return
                yield from widgets
                pass_idx += 1
        ticker_iter = cycle_with_refresh()

    if title:
        ticker_iter = itertools.chain([title], ticker_iter)

    return ticker_iter
```

If `Iterator` isn't already imported, add at the top of `ticker.py`:

```python
from collections.abc import Iterator
```

Verify `logger` is already defined in `ticker.py`; if not, add near the top:

```python
import logging
logger: logging.Logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `make test ARGS="tests/test_container_refresh.py -v"`
Expected: All 10 PASS.

- [ ] **Step 5: Run the broader engine tests to confirm no regression**

Run: `make test ARGS="tests/test_ticker_display.py tests/test_ticker.py tests/test_ticker_wraps_forever.py tests/test_engine_redraw_contract.py -v"`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_container_refresh.py
git commit -m "$(cat <<'EOF'
fix: re-expand containers per cycle in _build_ticker_iter

Replaces itertools.cycle/itertools.chain with explicit per-pass
expansion via _expand_sources. Containers (mlb, mlb_standings,
rss_feed) now refresh their stories on every pass through the
section, so live updates from background update() tasks reach the
panel within one cycle.

Previously, loop_count=0 snapshotted ticker_objects on first cycle
and yielded from that snapshot forever — even though feed_stories
was being rebuilt every 5 min. On longboi this froze MLB scores on
last night's live half-inning for 11+ hours.

DEBUG-level log added per pass: "section cycle N: M sources → K widgets".

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Stop pre-expanding containers in `app/run.py`

**Files:**
- Modify: `src/led_ticker/app/run.py`
- Test: `tests/test_container_refresh.py`

- [ ] **Step 1: Add failing integration test**

Append to `tests/test_container_refresh.py`:

```python
def test_app_run_passes_containers_to_ticker_unexpanded() -> None:
    """app/run.py must push containers as-is into Ticker.monitors so the
    engine can re-expand them per cycle. Pre-expanding here defeats the
    refresh — see _build_ticker_iter.

    This is a source-level tripwire: it scans app/run.py to ensure the
    pre-expansion stanza removed in 2026-05-28 doesn't come back.
    """
    import ast
    import pathlib

    src = pathlib.Path("src/led_ticker/app/run.py").read_text()
    tree = ast.parse(src)

    # Walk for any `widgets.extend(<x>.feed_stories)` call
    class ExtendVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found = False

        def visit_Call(self, node: ast.Call) -> None:
            # widgets.extend(...) pattern
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "extend"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "widgets"
            ):
                # Inspect arg: <x>.feed_stories
                if (
                    node.args
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_container_refresh.py::test_app_run_passes_containers_to_ticker_unexpanded -v"`
Expected: FAIL — `app/run.py` currently has `widgets.extend(widget.feed_stories)`.

- [ ] **Step 3: Remove pre-expansion in `app/run.py`**

Edit `src/led_ticker/app/run.py`. Find the block at lines ~93-105:

```python
                    # Container widgets expand into stories
                    if isinstance(
                        widget,
                        RSSFeedMonitor | MLBScoreMonitor | MLBStandingsMonitor,
                    ):
                        logging.debug(
                            "Expanding %s: %d stories",
                            type(widget).__name__,
                            len(widget.feed_stories),
                        )
                        widgets.extend(widget.feed_stories)
                    else:
                        widgets.append(widget)
```

Replace with:

```python
                    # Containers are expanded by the engine on every
                    # cycle pass via _expand_sources — pushing the
                    # container itself (not its current feed_stories)
                    # keeps the displayed content in sync with the
                    # container's background update() task.
                    widgets.append(widget)
```

Then remove the now-unused imports near the top of `src/led_ticker/app/run.py`:

```python
from led_ticker.widgets.mlb import MLBScoreMonitor
from led_ticker.widgets.mlb_standings import MLBStandingsMonitor
from led_ticker.widgets.rss_feed import RSSFeedMonitor
```

(Verify with grep that no other code in `run.py` references these names. If they're still used elsewhere in the file, keep the imports.)

- [ ] **Step 4: Run tests to verify the tripwire passes**

Run: `make test ARGS="tests/test_container_refresh.py -v"`
Expected: All PASS.

- [ ] **Step 5: Run full app/integration tests**

Run: `make test ARGS="tests/test_ticker.py tests/test_ticker_display.py tests/test_engine_redraw_contract.py -v"`
Expected: All PASS.

- [ ] **Step 6: Lint**

Run: `make lint`
Expected: clean (no unused-import errors from the removed imports).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app/run.py tests/test_container_refresh.py
git commit -m "$(cat <<'EOF'
fix: stop pre-expanding container widgets in app/run.py

Pushes container widgets (mlb, mlb_standings, rss_feed) into
Ticker.monitors as-is rather than copying their current
feed_stories into a static list. The engine now re-expands
containers per cycle via _expand_sources, so live updates land
on the panel within ~one cycle instead of being permanently
snapshotted at section-build time.

Adds AST-level tripwire test to prevent the pre-expansion
pattern from coming back.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Add INFO log on MLB update success

**Files:**
- Modify: `src/led_ticker/widgets/mlb.py`
- Test: `tests/test_mlb_scoreboard.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_mlb_scoreboard.py` (use existing test fixtures + patterns):

```python
class TestMLBUpdateLogging:
    """Periodic update() must log INFO so users can tell the background
    task is firing. Without these logs there is no diagnostic signal
    that update() ran successfully — silent success looks like silent
    failure when the panel goes stale.
    """

    @pytest.mark.asyncio
    async def test_update_logs_info_with_story_count(
        self, monkeypatch, caplog
    ) -> None:
        import logging
        from unittest.mock import AsyncMock, MagicMock

        from led_ticker.widgets.mlb import MLBScoreMonitor

        # Mock session that returns an empty schedule (no games)
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json = AsyncMock(return_value={"dates": []})
        session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        widget = MLBScoreMonitor(session=session, team="NYM")
        widget._team_id = 121  # NYM, skip the team-id resolve
        from zoneinfo import ZoneInfo
        widget._tz = ZoneInfo("America/New_York")

        with caplog.at_level(logging.INFO, logger="led_ticker.widgets.mlb"):
            await widget.update()

        # Find an INFO record matching the expected pattern
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        matching = [r for r in info_records if "updated" in r.message and "NYM" in r.message]
        assert matching, (
            f"expected INFO log mentioning 'updated' and team 'NYM'; "
            f"got: {[r.message for r in info_records]}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test ARGS="tests/test_mlb_scoreboard.py::TestMLBUpdateLogging -v"`
Expected: FAIL — no INFO log emitted from `update()` today (only from `start()`).

- [ ] **Step 3: Add the INFO log**

Edit `src/led_ticker/widgets/mlb.py`. At the end of `update()` (after `self._has_live_game = any(...)` at line ~1015 in the success branch, AND after the no-games / no-series branches), add a single log call.

Concretely, the cleanest place is to compute live game count in update() and log right before each `return`. The simplest path is to add a helper and call it from one spot at the end of update().

Refactor approach: extract the "set state and return" into a helper. Or just add the log line at the bottom of `update()`, after all branches. Since `update()` has early returns on errors, easiest is to log at every `self.feed_stories = ...` assignment site.

Implementation: at the END of `update()` (last line, after `self._has_live_game = ...`), add:

```python
        n_live = sum(1 for g in current.games if g.state == "live") if current else 0
        logger.info(
            "MLB %s updated: %d stories (live: %d)",
            self.team, len(self.feed_stories), n_live,
        )
```

For the error/no-data branches (where `feed_stories = [title, "No Data"]`), prefix each early-return branch with a similar log (the "No Data" state is still a real update result):

In each branch where `self.feed_stories = [title, TickerMessage("No Data", ...)]` is set, immediately before `return`, add:

```python
            logger.info("MLB %s updated: %d stories (no data)", self.team, len(self.feed_stories))
            return
```

For the no-current-series + next-game branch (around line ~958), add:

```python
            logger.info(
                "MLB %s updated: %d stories (next: %s)",
                self.team, len(self.feed_stories), opp_name if next_game else "season over",
            )
            return
```

(Use the existing local `opp_name` already in scope; check the surrounding code for the variable name.)

For the success path at the bottom (after `self._has_live_game = ...`), add the n_live variant shown above.

- [ ] **Step 4: Run tests to verify pass**

Run: `make test ARGS="tests/test_mlb_scoreboard.py::TestMLBUpdateLogging -v"`
Expected: PASS.

Run the full MLB test suite to confirm no regression:

Run: `make test ARGS="tests/test_mlb_scoreboard.py -v"`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/mlb.py tests/test_mlb_scoreboard.py
git commit -m "$(cat <<'EOF'
feat: log INFO at end of MLBScoreMonitor.update()

Adds one INFO log per successful update() with story count and live
game count: "MLB NYM updated: 5 stories (live: 1)". Mirrors the
startup log from start() so the periodic update timer fires also
emit a visible signal. Without this, silent success looks identical
to silent failure when the panel is stale.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add INFO log on MLB standings + RSS update success

**Files:**
- Modify: `src/led_ticker/widgets/mlb_standings.py`
- Modify: `src/led_ticker/widgets/rss_feed.py`
- Test: extend existing test files

- [ ] **Step 1: Add failing tests**

For `tests/test_mlb_scoreboard.py` (the standings tests may live in a separate file — check `tests/` for `test_mlb_standings.py`; if it exists, append there, otherwise append in `tests/test_mlb_scoreboard.py` under a new class):

```python
class TestMLBStandingsUpdateLogging:
    @pytest.mark.asyncio
    async def test_standings_update_logs_info(self, caplog) -> None:
        import logging
        from unittest.mock import AsyncMock, MagicMock

        from led_ticker.widgets.mlb_standings import MLBStandingsMonitor

        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json = AsyncMock(return_value={"records": []})
        session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        widget = MLBStandingsMonitor(session=session, teams=["NYM"])
        from zoneinfo import ZoneInfo
        widget._tz = ZoneInfo("America/New_York")

        with caplog.at_level(logging.INFO, logger="led_ticker.widgets.mlb_standings"):
            await widget.update()

        matching = [
            r for r in caplog.records
            if r.levelno == logging.INFO and "standings" in r.message.lower()
        ]
        assert matching, f"expected INFO log; got {[r.message for r in caplog.records]}"
```

For `tests/test_rss_feed.py` (check filename; if missing, create or extend `tests/test_widgets/test_rss_feed.py`):

```python
class TestRSSFeedUpdateLogging:
    @pytest.mark.asyncio
    async def test_rss_update_logs_info(self, caplog) -> None:
        import logging
        from unittest.mock import AsyncMock, MagicMock

        from led_ticker.widgets.rss_feed import RSSFeedMonitor

        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = AsyncMock(return_value="<rss><channel></channel></rss>")
        session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        widget = RSSFeedMonitor(session=session, feed_url="http://example.com/feed")

        with caplog.at_level(logging.INFO, logger="led_ticker.widgets.rss_feed"):
            await widget.update()

        matching = [
            r for r in caplog.records
            if r.levelno == logging.INFO and "rss" in r.message.lower() or "updated" in r.message
        ]
        assert matching, f"expected INFO log; got {[r.message for r in caplog.records]}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test ARGS="-v -k 'TestMLBStandingsUpdateLogging or TestRSSFeedUpdateLogging'"`
Expected: FAIL for both.

- [ ] **Step 3: Add INFO log to `mlb_standings.py`**

In `src/led_ticker/widgets/mlb_standings.py`, at the END of `update()` (after `self.feed_stories = stories` at line ~181), add:

```python
        logger.info("MLB standings updated: %d stories", len(self.feed_stories))
```

And at the early-return error/offseason branches where `self.feed_stories = [...]` is set (search for `self.feed_stories =` in the file), add the same log immediately before `return`:

```python
        logger.info(
            "MLB standings updated: %d stories (no data)",
            len(self.feed_stories),
        )
        return
```

(For the offseason branch, use `(offseason)` instead of `(no data)` for clarity.)

- [ ] **Step 4: Add INFO log to `rss_feed.py`**

In `src/led_ticker/widgets/rss_feed.py`, find every `self.feed_stories = ...` assignment in `update()`. After each, before the function returns to the caller (i.e., at end of update or before early returns), add:

```python
        logger.info(
            "RSS %s updated: %d stories",
            self.feed_url, len(self.feed_stories),
        )
```

Verify `logger` is defined near the top of the file; if not, add:

```python
import logging
logger: logging.Logger = logging.getLogger(__name__)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `make test ARGS="-v -k 'TestMLBStandingsUpdateLogging or TestRSSFeedUpdateLogging'"`
Expected: All PASS.

Run the full widget suites:

Run: `make test ARGS="tests/test_mlb_scoreboard.py tests/test_widgets -v"`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/mlb_standings.py src/led_ticker/widgets/rss_feed.py tests/
git commit -m "$(cat <<'EOF'
feat: log INFO at end of standings + RSS update()

Adds one INFO log per successful update() for MLBStandingsMonitor
and RSSFeedMonitor, matching the pattern added for MLBScoreMonitor.
Format: "MLB standings updated: N stories" / "RSS <url> updated: N
stories". Gives users a visible signal that the background timer is
firing — silent success is indistinguishable from silent failure
when the panel goes stale.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Document the invariant in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a "Container widgets" subsection under "Load-bearing invariants by subsystem"**

In `CLAUDE.md`, find the "Load-bearing invariants by subsystem" section. Add a new bullet at an appropriate location (after the "Two-row widget" bullet feels right since both are widget-shape rules):

```markdown
**Container widgets** (`Container` Protocol in `widget.py`) — Widgets whose `feed_stories: list[Widget]` is rebuilt by a background `update()` task are first-class to the engine. `app/run.py` pushes them into `Ticker.monitors` AS THEMSELVES (not pre-expanded); `_build_ticker_iter` re-reads `feed_stories` via `_expand_sources` on every pass through the section, so live updates surface within at most one cycle. NEVER use `itertools.cycle(snapshot)` or `widgets.extend(container.feed_stories)` at section build — that was the longboi stale-display bug (2026-05-28): containers updated correctly in the background but the cycle iterator yielded the original snapshot forever, freezing the panel on whatever state was current when the container booted. Each `update()` emits one INFO log per call ("MLB NYM updated: 5 stories (live: 1)") so a silent log stream after startup is a diagnostic signal that the background task died. The engine emits a DEBUG log per pass ("section cycle N: M sources → K widgets") so users debugging "is the engine re-reading?" can flip to DEBUG. Tripwires: `tests/test_container_refresh.py` (behavioral: mutate `feed_stories`, verify next pull yields new content; AST: assert `app/run.py` never re-introduces `widgets.extend(.feed_stories)`).
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document Container widget refresh invariant in CLAUDE.md

Locks in the engine-side contract (containers re-expanded per cycle
via _expand_sources, never pre-snapshotted at section build) and the
logging convention (INFO per update, DEBUG per cycle) so future edits
to the engine can't silently re-introduce the longboi stale-display
bug.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Manual verification on hardware-style config

**Files:**
- None (manual verification step)

- [ ] **Step 1: Validate a representative config**

Run: `make validate CONFIG=config/config.mlb_forever.toml`
Expected: clean validation (no errors / no new warnings beyond pre-existing).

- [ ] **Step 2: Run the full test suite end-to-end**

Run: `make test`
Expected: All ~1438+ tests PASS (with ~12 new in this branch).

- [ ] **Step 3: Run lint and format**

Run: `make lint && make format`
Expected: clean.

- [ ] **Step 4: Final commit if anything cleanup-worthy emerged**

Only if step 3 modified files:

```bash
git add -p  # review changes
git commit -m "$(cat <<'EOF'
chore: lint/format cleanup for live-container-refresh

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and open PR (after user confirms)**

```bash
git push -u origin <branch-name>
```

PR description should include:
- The bug symptom (longboi stale 11h)
- Root cause one-liner
- The refactor summary
- The new INFO/DEBUG log format
- A test plan checklist with a hardware verification item for the user

---

## Self-Review

**Spec coverage:**
- `Container` Protocol → Task 1 ✓
- `_expand_sources` helper → Task 2 ✓
- `_build_ticker_iter` re-expansion → Task 3 ✓
- `app/run.py` cleanup → Task 4 ✓
- MLB INFO log → Task 5 ✓
- Standings + RSS INFO logs → Task 6 ✓
- DEBUG cycle log → Task 3 (folded into rewrite) ✓
- CLAUDE.md invariant → Task 7 ✓
- Tests for refresh contract → Task 2, 3, 4 ✓
- Verification → Task 8 ✓

**Placeholder scan:** None found. Every code step shows actual code; every commit step shows actual commit message; every command step shows actual command + expected output.

**Type consistency:**
- `Container` Protocol defined in Task 1, used in Task 2 (`isinstance(s, Container)`) ✓
- `_expand_sources(sources: list[Any]) -> list[Any]` defined in Task 2, called in Task 3 ✓
- `_build_ticker_iter(ticker_objects, title, loop_count)` signature unchanged from existing — Task 3 only changes return-type annotation from `Any` to `Iterator[Any]`. Callers in `_build_then_enqueue` already use `next()`-style consumption; no caller change needed ✓
- `feed_stories: list[Widget]` field already present on all three container classes; Protocol declaration in Task 1 matches existing field annotations ✓

No gaps. Plan is internally consistent.

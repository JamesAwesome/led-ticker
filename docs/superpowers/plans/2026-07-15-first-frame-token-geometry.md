# First-frame token geometry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the "scrolling message with a polled-source token only scrolls to the first letter on first display" bug via the measure-at-lock invariant in the scroll engine plus a bounded startup prime for polled sources.

**Architecture:** Two independent changes. (1) `ticker.py:_swap_and_scroll` restructured so the geometry a locked scroll consumes is measured at the instant of locking (hold first, then decide/measure), never across the pre-scroll hold `await`. (2) `PolledDataSource` gains a `first_value` event; `run()` awaits all polled sources' first values with a bounded timeout before the display loop.

**Tech Stack:** Python 3.14, asyncio, attrs, pytest (headless — no hardware/Docker).

## Global Constraints

- Never work on `main`; this runs in worktree `led-ticker--first-frame-tokens` on branch `fix/first-frame-token-geometry`. Verify with `git branch --show-current` before editing.
- Constraints #6/#7 (no mid-scroll re-measure — `stop_pos` captured once) MUST be preserved: the fix moves the measurement to the lock boundary, it does NOT re-measure per scroll tick.
- Constraint #1 (capture the swap return) and #12 (advance_frame per tick) are inherited via `_hold_ticks` and the existing scroll loop — do not add a new draw site that bypasses them.
- The `forces_offscreen_scroll` and `wraps_forever` branches of `_swap_and_scroll` already measure-at-lock (resolve-then-lock, no hold between) — do NOT touch them.
- `continuous=True` (scroll-transition seamless mode) behavior must be byte-for-byte preserved: no pre-scroll hold, entry-measure `stop_pos`, and continuous+fits still holds (the original else-branch behavior).
- Lint/format/pyright must be clean: `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev ruff format --check src/ tests/`, `uv run --extra dev pyright src/led_ticker/ticker.py src/led_ticker/sources.py`. No `# type: ignore`.
- Run tests with `uv run --extra dev pytest` (no `PYTHONPATH` prefix).

---

### Task 1: Engine measure-at-lock in `_swap_and_scroll`

**Files:**
- Modify: `src/led_ticker/ticker.py` (the generic-overflow/fits region, currently ~L647-686)
- Test: `tests/test_ticker_display.py`

**Interfaces:**
- Consumes: `self._hold_ticks(canvas, widget, n_ticks, pos, bg_color) -> (canvas, cursor_pos)` where the returned `cursor_pos` is the LAST tick's fresh `_safe_draw` measurement; `get_widget_padding(widget, default=0)`; `ENGINE_TICK_MS = 50`; `self.scroll_speed`.
- Produces: no signature change to `_swap_and_scroll`; it still returns `(canvas, cursor_pos, pos)`.

**Current code to replace (verify against the file — line numbers drift):**

```python
        if cursor_pos > canvas.width:
            if not continuous:
                n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
                canvas, _ = await self._hold_ticks(
                    canvas, ticker_obj, n_ticks, pos, bg_color
                )

            padding = get_widget_padding(ticker_obj, default=0)
            # Freeze inline-token resolution for the scroll loop: `stop_pos`
            # is captured once from the entry width, and the loop discards
            # the per-tick cursor_pos. A mid-scroll re-measure would strand
            # the scroll and clip the tail (constraints #6/#7). A version
            # that bumped mid-scroll applies on the next held tick / visit.
            self._lock_resolution_if_supported(ticker_obj, True)
            try:
                stop_pos = -(cursor_pos - canvas.width) + padding
                while pos > stop_pos:
                    self._maybe_restart()
                    t0 = loop.time()
                    pos -= 1
                    self._advance_frame_if_supported(ticker_obj)
                    reset_canvas(canvas, bg_color)
                    canvas, _ = self._safe_draw(ticker_obj, canvas, pos)
                    canvas = _swap(canvas, self.frame)
                    await asyncio.sleep(
                        max(0.0, self.scroll_speed - (loop.time() - t0))
                    )
            finally:
                self._lock_resolution_if_supported(ticker_obj, False)

            if not continuous:
                n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
                canvas, _ = await self._hold_ticks(
                    canvas, ticker_obj, n_ticks, pos, bg_color
                )
        else:
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            canvas, _ = await self._hold_ticks(
                canvas, ticker_obj, n_ticks, pos, bg_color
            )
```

- [ ] **Step 1: Write the two failing tests + a no-regression test**

Add to `tests/test_ticker_display.py`:

```python
class TestSwapAndScrollMeasureAtLock:
    """Measure-at-lock: the geometry a locked scroll consumes is measured at
    the instant of locking, so a token that resolves from its placeholder
    during the pre-scroll hold drives the scroll distance. Regression: a
    scrolling message with a polled-source token 'only scrolled to the first
    letter' on first display."""

    @staticmethod
    def _growing_widget(narrow: int, wide: int):
        """Mock widget whose draw() reports `narrow` on the FIRST call (entry
        measure, placeholder) and `wide` thereafter (resolved during the hold).
        Width is `cursor_pos + content_width`, matching conftest.make_widget."""
        w = mock.Mock()
        w.hold_time = 0.0
        w.forces_offscreen_scroll = False
        w.wraps_forever = False
        w.bg_color = None
        calls = {"n": 0}

        def _draw(c, cursor_pos=0, **kw):
            calls["n"] += 1
            width = narrow if calls["n"] == 1 else wide
            return c, cursor_pos + width

        w.draw.side_effect = _draw
        return w

    async def test_overflow_scroll_uses_post_hold_width(
        self, canvas, mock_frame, no_sleep
    ):
        # placeholder overflows narrowly (200), resolves wider (400) during hold.
        widget = self._growing_widget(narrow=200, wide=400)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, _, scroll_pos = await ticker._swap_and_scroll(
            canvas, widget, hold_time=0.05
        )
        # canvas.width=160, padding=0 -> stop from the RESOLVED width 400.
        assert scroll_pos == -(400 - 160)  # == -240, NOT -(200-160) == -40

    async def test_placeholder_fits_but_value_overflows_scrolls(
        self, canvas, mock_frame, no_sleep
    ):
        # placeholder fits (40), resolves to overflow (400) during the hold.
        widget = self._growing_widget(narrow=40, wide=400)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, _, scroll_pos = await ticker._swap_and_scroll(
            canvas, widget, hold_time=0.05
        )
        # Old behavior: fits -> never scrolls -> scroll_pos == 0. Now it scrolls.
        assert scroll_pos == -(400 - 160)  # == -240

    async def test_static_overflow_unchanged(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        # A constant-width overflowing widget still stops at the same place.
        widget = make_widget(content_width=300)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, _, scroll_pos = await ticker._swap_and_scroll(
            canvas, widget, hold_time=0.05
        )
        assert scroll_pos == -(300 - 160)  # == -140, unchanged

    async def test_static_fits_does_not_scroll(
        self, canvas, mock_frame, make_widget, no_sleep
    ):
        widget = make_widget(content_width=40)
        ticker = Ticker(monitors=[], frame=mock_frame)
        _, _, scroll_pos = await ticker._swap_and_scroll(
            canvas, widget, hold_time=0.05
        )
        assert scroll_pos == 0  # fits -> held, never scrolls
```

- [ ] **Step 2: Run the tests to verify the two growing-width ones FAIL**

Run: `uv run --extra dev pytest tests/test_ticker_display.py::TestSwapAndScrollMeasureAtLock -v`
Expected: `test_overflow_scroll_uses_post_hold_width` FAILS (gets -40, wants -240); `test_placeholder_fits_but_value_overflows_scrolls` FAILS (gets 0, wants -240); the two static tests PASS.

- [ ] **Step 3: Restructure the overflow/fits region (the fix)**

Replace the current code (shown above) with:

```python
        # Measure-at-lock: the geometry a locked scroll consumes must be
        # measured at the instant of locking, with zero awaits between the
        # measure and the lock. So (non-continuous) we run the initial hold
        # FIRST and re-decide overflow-vs-fits from the POST-hold measurement.
        # A token that resolved from its placeholder during the hold (a polled
        # source's first fetch landing, or a 1 Hz value tick) has by then
        # widened its content, and `_hold_ticks` returns that fresh cursor_pos.
        # Measuring up-front and scrolling to a stale stop_pos was the
        # "first display only scrolls to the first letter" bug.
        if not continuous:
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            canvas, held_cursor = await self._hold_ticks(
                canvas, ticker_obj, n_ticks, pos, bg_color
            )
            if held_cursor > 0:  # 0 == a breaker-tripped draw; keep entry width
                cursor_pos = held_cursor

        if cursor_pos > canvas.width:
            padding = get_widget_padding(ticker_obj, default=0)
            # Freeze inline-token resolution for the scroll loop: `stop_pos` is
            # captured once — now at the lock boundary, measured just above with
            # no await between — and the loop discards the per-tick cursor_pos.
            # A mid-scroll re-measure would strand the scroll and clip the tail
            # (constraints #6/#7). A version that bumps mid-scroll applies on the
            # next held tick / visit.
            self._lock_resolution_if_supported(ticker_obj, True)
            try:
                stop_pos = -(cursor_pos - canvas.width) + padding
                while pos > stop_pos:
                    self._maybe_restart()
                    t0 = loop.time()
                    pos -= 1
                    self._advance_frame_if_supported(ticker_obj)
                    reset_canvas(canvas, bg_color)
                    canvas, _ = self._safe_draw(ticker_obj, canvas, pos)
                    canvas = _swap(canvas, self.frame)
                    await asyncio.sleep(
                        max(0.0, self.scroll_speed - (loop.time() - t0))
                    )
            finally:
                self._lock_resolution_if_supported(ticker_obj, False)

            if not continuous:
                n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
                canvas, _ = await self._hold_ticks(
                    canvas, ticker_obj, n_ticks, pos, bg_color
                )
        elif continuous:
            # continuous + fits: preserve the original else-branch hold (the
            # non-continuous fits-case already held above). Continuous mode has
            # no pre-scroll hold, so its geometry was never stale.
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            canvas, _ = await self._hold_ticks(
                canvas, ticker_obj, n_ticks, pos, bg_color
            )
```

- [ ] **Step 4: Run the new tests + the whole engine suite**

Run: `uv run --extra dev pytest tests/test_ticker_display.py tests/test_engine_redraw_contract.py -q`
Expected: all PASS (the four new tests + no regressions; the AST redraw-contract meta-test still passes since the scroll/hold loops are unchanged internally).

- [ ] **Step 5: Full suite + lint/format/pyright**

Run: `uv run --extra dev pytest -q` then `uv run --extra dev ruff check src/ tests/` and `uv run --extra dev ruff format --check src/ tests/` and `uv run --extra dev pyright src/led_ticker/ticker.py`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "fix(engine): measure scroll geometry at the lock boundary, not across the hold"
```

---

### Task 2: Bounded boot prime for polled sources

**Files:**
- Modify: `src/led_ticker/sources.py` (add `import logging`; `PolledDataSource.first_value` + `_set_value` override; `PRIME_TIMEOUT` + `prime_polled_sources`)
- Modify: `src/led_ticker/app/run.py` (import `prime_polled_sources`; await it after `spawn_source_refresh`)
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `DataRegistry.sources() -> list[DataSource]`; `DataSource._set_value(new) -> bool` (bumps `version` 0→1 on first value); `spawn_source_refresh(registry)` (unchanged).
- Produces: `PolledDataSource.first_value: asyncio.Event`; `async prime_polled_sources(registry, timeout=PRIME_TIMEOUT) -> None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sources.py`:

```python
import asyncio

from led_ticker.sources import (
    DataRegistry,
    PolledDataSource,
    StaticSource,
    prime_polled_sources,
)


class _FakePolled(PolledDataSource):
    async def update(self) -> None:  # not driven in these tests
        self._set_value("real")


def _polled(source_id: str) -> _FakePolled:
    return _FakePolled(id=source_id)


async def test_first_value_event_set_on_first_real_value():
    s = _polled("p")
    assert not s.first_value.is_set()  # nothing applied yet
    s._set_value("123.45")
    assert s.first_value.is_set() and s.version == 1


async def test_prime_returns_when_all_ready():
    reg = DataRegistry()
    a, b = _polled("a"), _polled("b")
    reg.add(a)
    reg.add(b)
    a._set_value("1")
    b._set_value("2")
    # Both events already set -> returns effectively immediately.
    await asyncio.wait_for(prime_polled_sources(reg, timeout=5.0), timeout=1.0)


async def test_prime_times_out_bounded_when_source_never_resolves():
    reg = DataRegistry()
    reg.add(_polled("slow"))  # never _set_value -> event never set
    # Must return after ~timeout, not hang.
    await asyncio.wait_for(prime_polled_sources(reg, timeout=0.05), timeout=1.0)


async def test_prime_ignores_sync_sources():
    reg = DataRegistry()
    reg.add(StaticSource(id="s", value="x"))  # not polled -> not awaited
    await asyncio.wait_for(prime_polled_sources(reg, timeout=0.05), timeout=1.0)
```

- [ ] **Step 2: Run the tests to verify they FAIL**

Run: `uv run --extra dev pytest tests/test_sources.py -k "first_value or prime" -v`
Expected: FAIL — `ImportError`/`AttributeError` (`prime_polled_sources` / `first_value` don't exist yet).

- [ ] **Step 3: Add `first_value` + `_set_value` override + `prime_polled_sources`**

In `src/led_ticker/sources.py`, add `import logging` to the import block (after `import asyncio`).

Add the field and override inside `class PolledDataSource` (after the `interval` field):

```python
    # Set when the first real value is applied (version 0 -> 1). Startup awaits
    # this (bounded) so token widgets show real data on first display instead
    # of the placeholder. Created per instance; binds to the running loop lazily.
    first_value: asyncio.Event = attrs.field(factory=asyncio.Event, init=False)

    def _set_value(self, new: str) -> bool:
        changed = super()._set_value(new)
        if self.version > 0:
            self.first_value.set()
        return changed
```

Add module-level, after the `DataRegistry` class (or near `spawn_source_refresh`):

```python
PRIME_TIMEOUT: float = 2.5


async def prime_polled_sources(
    registry: DataRegistry, timeout: float = PRIME_TIMEOUT
) -> None:
    """Wait (bounded) for each polled source's first real value so token
    widgets render real data on their first display instead of a placeholder.

    Bounded: a source slower than `timeout` degrades to the placeholder and
    self-corrects on its next tick — the wait never blocks boot indefinitely.
    Sync sources (clock/date/static) are already correct at build time and are
    not awaited.
    """
    polled = [s for s in registry.sources() if isinstance(s, PolledDataSource)]
    if not polled:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*(s.first_value.wait() for s in polled)),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        not_ready = [s.id for s in polled if not s.first_value.is_set()]
        logging.info(
            "source prime: %d/%d polled sources ready within %.1fs; "
            "still waiting: %s",
            len(polled) - len(not_ready),
            len(polled),
            timeout,
            not_ready,
        )
```

- [ ] **Step 4: Run the source tests to verify they PASS**

Run: `uv run --extra dev pytest tests/test_sources.py -k "first_value or prime" -v`
Expected: all 4 PASS.

- [ ] **Step 5: Wire the prime into `run()`**

In `src/led_ticker/app/run.py`, add `prime_polled_sources` to the sources import (line ~42):

```python
from led_ticker.sources import (
    DataRegistry,
    prime_polled_sources,
    set_data_registry,
    spawn_source_refresh,
)
```

Immediately after `source_refresh_task = spawn_source_refresh(_source_registry)` (~L829), add:

```python
            # Give polled sources a brief, bounded head start so token widgets
            # show real data on their first display instead of the placeholder
            # (pairs with the engine measure-at-lock fix). Bounded: a slow or
            # down source degrades to the placeholder and self-corrects next tick.
            await prime_polled_sources(_source_registry)
```

- [ ] **Step 6: Run the integration render test + full suite + lint/format/pyright**

Run: `uv run --extra dev pytest tests/test_integration_render.py tests/test_sources.py -q` then `uv run --extra dev pytest -q` then `uv run --extra dev ruff check src/ tests/` and `uv run --extra dev ruff format --check src/ tests/` and `uv run --extra dev pyright src/led_ticker/sources.py src/led_ticker/app/run.py`
Expected: all green (the integration boot test still passes — its configs either have no polled sources, so the prime is a no-op, or a demo source that sets its value fast).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/sources.py src/led_ticker/app/run.py tests/test_sources.py
git commit -m "feat(sources): bounded boot prime so token widgets show real data on first display"
```

---

## Post-implementation (controller, not a task)

- **Visual GIF validation gate (required before merge):** per `docs/visual-validation.md`, render a scrolling message with a demo-backed stocks token from a cold boot and confirm the FIRST pass scrolls the full resolved text (no first-letter truncation). Use the making-a-gif skill (dev mode).
- Final whole-branch review (opus) over the two-task diff, then open the PR.

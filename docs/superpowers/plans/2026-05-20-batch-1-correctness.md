# Batch 1: Correctness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree. Expected branch: `worktree-fix+batch-1-correctness`.

**Goal:** Fix three correctness bugs from the engine architecture review: C2 (feedparser.parse blocks the asyncio event loop), C3 (engine tick loops accumulate drift), and S15 (get_text_width cache wholesale-clears instead of evicting LRU).

**Architecture:** All three are point fixes with no abstraction changes. C2 is a single-line change. S15 is a one-line eviction change plus a tighter test assertion. C3 is the same three-line pattern applied mechanically to 7 tick-loop sites across two files.

**Tech Stack:** Python asyncio, feedparser, attrs, pytest

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Baseline:** 1770 tests passing, 2 skipped.

---

### Task 1: C2 — feedparser.parse off the event loop

`feedparser.parse` is synchronous CPU-bound XML parsing called directly on the asyncio event loop in `RSSFeedMonitor.update()`. This blocks all other coroutines (widget rendering, data monitors) for the full parse duration — typically 50–200 ms on a large feed. Fix: delegate to a thread via `asyncio.to_thread`.

**Files:**
- Modify: `src/led_ticker/widgets/rss_feed.py:66`
- Test: `tests/test_widgets/test_rss_feed.py`

- [ ] **Step 1: Write the failing test**

Add a new test class to `tests/test_widgets/test_rss_feed.py` after the existing classes:

```python
import feedparser as _feedparser  # noqa: E402  (add to top of file)


class TestFeedparserOffEventLoop:
    """feedparser.parse is CPU-bound XML parsing. Calling it directly on
    the event loop blocks all other coroutines for the full parse duration.
    It must be offloaded via asyncio.to_thread (C2)."""

    async def test_feedparser_called_via_to_thread(self, mock_session, monkeypatch):
        """asyncio.to_thread must be called with feedparser.parse and the
        raw feed text — not feedparser.parse called directly."""
        calls: list[tuple] = []

        async def _fake_to_thread(func, *args, **kwargs):
            calls.append((func, args, kwargs))
            return func(*args, **kwargs)

        monkeypatch.setattr(
            "led_ticker.widgets.rss_feed.asyncio.to_thread", _fake_to_thread
        )

        monitor = RSSFeedMonitor(
            session=mock_session, feed_url="http://example.com/rss"
        )
        await monitor.update()

        assert len(calls) == 1, f"expected 1 to_thread call, got {len(calls)}: {calls}"
        func, args, kwargs = calls[0]
        assert func is _feedparser.parse, (
            f"expected feedparser.parse, got {func}"
        )
        assert args == (SAMPLE_RSS,), f"expected (SAMPLE_RSS,), got {args}"
```

Note: add `import feedparser as _feedparser` near the existing imports at the top of the test file (after the existing imports).

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_rss_feed.py::TestFeedparserOffEventLoop -v
```

Expected: `FAILED` — `AssertionError: expected 1 to_thread call, got 0` (feedparser.parse called directly, to_thread never invoked).

- [ ] **Step 3: Implement the fix**

In `src/led_ticker/widgets/rss_feed.py`, change line 66:

```python
# Before (line 66):
            feed = feedparser.parse(feed_data)

# After:
            feed = await asyncio.to_thread(feedparser.parse, feed_data)
```

The full updated `update()` method:

```python
    async def update(self) -> None:
        logging.info("Updating RSS Feed from: %s", self.feed_url)
        async with self.session.get(self.feed_url) as response:
            feed_data = await response.text()
            feed = await asyncio.to_thread(feedparser.parse, feed_data)
            self.feed_title = TickerMessage(
                feed["channel"]["title"],  # type: ignore[index]
                font_color=self._story_color(),
                bg_color=self.bg_color,
            )
            self.feed_stories = [
                TickerMessage(
                    item["title"],  # type: ignore[index]
                    font_color=self._story_color(),
                    bg_color=self.bg_color,
                )
                for item in itertools.islice(feed["items"], self.max_stories)  # type: ignore[index]
            ]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_rss_feed.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 5: Run the full suite to check for regressions**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: 1771 passed, 2 skipped (1 new test added).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/rss_feed.py tests/test_widgets/test_rss_feed.py
git commit -m "fix: offload feedparser.parse to thread pool in RSSFeedMonitor.update (C2)"
```

---

### Task 2: C3 — Engine tick drift compensation

Each tick loop does `await asyncio.sleep(tick_seconds)` without accounting for the time already spent drawing and swapping. Over many ticks the loop runs slower than `ENGINE_TICK_MS = 50 ms`, causing animated color providers (Rainbow, ColorCycle) to sweep noticeably slower on panels with long hold times. Fix: capture `t0 = loop.time()` at the start of each tick iteration and sleep `max(0.0, tick_seconds - (loop.time() - t0))`.

**7 sites** across two files:

| File | Function | Lines |
|------|----------|-------|
| `ticker.py` | `_swap_and_scroll` — pre-scroll hold | 1123–1128 |
| `ticker.py` | `_swap_and_scroll` — post-scroll hold | 1149–1154 |
| `ticker.py` | `_swap_and_scroll` — held-text | 1158–1163 |
| `ticker.py` | `_scroll_and_delay` | 442–449 |
| `ticker.py` | `_scroll_side_by_side` | 631–639 |
| `_image_base.py` | `_play_with_text` | loop body at ~1389 |
| `_image_base.py` | `_play_with_two_row_text` | loop body at ~1658 |

**Note:** The existing test `TestSwapAndScrollContinuous.test_non_continuous_includes_holds` asserts `tick_s in sleep_calls` using exact float equality. After this fix, sleep is called with `max(0.0, tick_s - ε)` where ε is real elapsed time from unmocked `loop.time()` — even a few microseconds breaks exact equality. That test must also be updated (Step 4 below).

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Modify: `src/led_ticker/widgets/_image_base.py`
- Test: `tests/test_ticker_display.py`, `tests/test_widgets/test_image_base.py`

- [ ] **Step 1: Write failing tests**

**In `tests/test_ticker_display.py`**, add a new test class after `TestSwapAndScrollContinuous`:

```python
class TestTickDriftCompensation:
    """Tick loops must subtract elapsed work time from the sleep so the
    panel animates at a steady ENGINE_TICK_MS cadence even when draw +
    swap take measurable time (C3). Each tick calls loop.time() twice:
    once at t0 = loop.time() and once inside the max() subtraction.
    """

    async def test_swap_and_scroll_held_text_subtracts_work_time(
        self, canvas, mock_frame, make_widget, monkeypatch
    ):
        from led_ticker.ticker import ENGINE_TICK_MS, _swap_and_scroll

        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        # Simulate 30 ms of work per tick: loop.time() returns alternating
        # 0.000 (t0) and 0.030 (after work). Each tick consumes two values.
        tick_times = iter([0.000, 0.030] * 100)
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        widget = make_widget(content_width=40)  # fits canvas → held-text branch
        await _swap_and_scroll(canvas, mock_frame, widget, hold_time=0.05)

        tick_s = ENGINE_TICK_MS / 1000  # 0.05
        expected = tick_s - 0.030       # 0.020
        assert sleep_calls, "no sleep calls recorded"
        assert all(
            abs(s - expected) < 1e-9 for s in sleep_calls
        ), f"expected {expected}s sleeps (drift-compensated), got {sleep_calls}"

    async def test_scroll_and_delay_subtracts_work_time(
        self, canvas, mock_frame, no_sleep, monkeypatch
    ):
        from led_ticker.ticker import ENGINE_TICK_MS, _scroll_and_delay

        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        tick_times = iter([0.000, 0.020] * 100)  # 20 ms work per tick
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        widget = make_widget(content_width=40)
        canvas_result, _ = await _scroll_and_delay(
            canvas, mock_frame, widget, delay=0.1
        )

        tick_s = ENGINE_TICK_MS / 1000  # 0.05
        expected = tick_s - 0.020       # 0.030
        assert sleep_calls, "no sleep calls recorded"
        assert all(
            abs(s - expected) < 1e-9 for s in sleep_calls
        ), f"expected {expected}s sleeps, got {sleep_calls}"
```

**In `tests/test_widgets/test_image_base.py`**, add a new test class after `TestPlayLoopAdvancesFrame`:

```python
class TestPlayWithTextDriftCompensation:
    """_play_with_text and _play_with_two_row_text must subtract elapsed
    work time from each tick's sleep so scroll speed stays accurate (C3).
    Each tick calls loop.time() twice: once at t0 and once inside max().
    """

    async def test_single_row_subtracts_work_time(self, monkeypatch):
        from rgbmatrix import _StubCanvas

        from led_ticker.fonts import FONT_DEFAULT

        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr(
            "led_ticker.widgets._image_base.asyncio.sleep", _record
        )

        tick_times = iter([0.000, 0.025] * 500)  # 25 ms work per tick
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.widgets._image_base.asyncio.get_running_loop",
            lambda: mock_loop,
        )

        frame = mock.Mock()
        frame.matrix.SwapOnVSync.return_value = _StubCanvas(width=160, height=16)

        w = _DummyImage(
            text="hi",
            text_align="scroll_over",
            font=FONT_DEFAULT,
            font_size=None,
            scroll_speed_ms=50,
        )
        w._logical_scale = 1
        real = _StubCanvas(width=160, height=16)

        await w._play_with_text(real, frame, n_ticks=3)

        tick_s = 50 / 1000   # scroll_speed_ms / 1000 = 0.05
        expected = tick_s - 0.025  # 0.025
        assert sleep_calls, "no per-tick sleep calls recorded"
        assert all(
            abs(s - expected) < 1e-9 for s in sleep_calls
        ), f"expected {expected}s sleeps (drift-compensated), got {sleep_calls}"
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestTickDriftCompensation tests/test_widgets/test_image_base.py::TestPlayWithTextDriftCompensation -v
```

Expected: `FAILED` on all three — sleep is called with `tick_s` unchanged (no drift subtraction).

- [ ] **Step 3: Implement the fix in `ticker.py` (5 sites)**

**Site A: `_swap_and_scroll` — add `loop` after `tick_seconds` and patch all 3 inner loops**

At line 1117, `tick_seconds = ENGINE_TICK_MS / 1000`. Add `loop` on the next line:

```python
# Change lines 1117–1118 (before the `if cursor_pos > canvas.width:` block):

    # BEFORE:
    tick_seconds = ENGINE_TICK_MS / 1000

    if cursor_pos > canvas.width:

    # AFTER:
    loop = asyncio.get_running_loop()
    tick_seconds = ENGINE_TICK_MS / 1000

    if cursor_pos > canvas.width:
```

Then apply the drift pattern to the **pre-scroll hold** loop (lines 1123–1128):

```python
        # BEFORE:
        for _ in range(n_ticks):
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(tick_seconds)

        # AFTER:
        for _ in range(n_ticks):
            t0 = loop.time()
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
```

Apply the same drift pattern to the **post-scroll hold** loop (lines 1149–1154):

```python
        # BEFORE:
        for _ in range(n_ticks):
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(tick_seconds)

        # AFTER:
        for _ in range(n_ticks):
            t0 = loop.time()
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
```

Apply the same drift pattern to the **held-text** loop (lines 1158–1163):

```python
    # BEFORE:
    else:
        n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
        for _ in range(n_ticks):
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(tick_seconds)

    # AFTER:
    else:
        n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
        for _ in range(n_ticks):
            t0 = loop.time()
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
```

**Site B: `_scroll_and_delay` — add `loop` after `tick_seconds` (lines 442–449)**

```python
    # BEFORE:
    n_ticks = max(1, int(delay * 1000) // ENGINE_TICK_MS)
    tick_seconds = ENGINE_TICK_MS / 1000
    for _ in range(n_ticks):
        _advance_frame_if_supported(ticker_obj)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)
        canvas = _swap(canvas, frame)
        await asyncio.sleep(tick_seconds)
    return canvas, cursor_pos

    # AFTER:
    n_ticks = max(1, int(delay * 1000) // ENGINE_TICK_MS)
    tick_seconds = ENGINE_TICK_MS / 1000
    loop = asyncio.get_running_loop()
    for _ in range(n_ticks):
        t0 = loop.time()
        _advance_frame_if_supported(ticker_obj)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)
        canvas = _swap(canvas, frame)
        await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
    return canvas, cursor_pos
```

**Site C: `_scroll_side_by_side` — add `loop` after `tick_seconds` (lines 631–639)**

```python
        # BEFORE:
        n_hold_ticks = max(1, int(hold_at_end * 1000) // ENGINE_TICK_MS)
        tick_seconds = ENGINE_TICK_MS / 1000
        for _ in range(n_hold_ticks):
            _advance_frame_if_supported(buffered_objects[0])
            bg_hold = getattr(buffered_objects[0], "bg_color", None)
            reset_canvas(canvas, bg_hold)
            canvas, _ = buffered_objects[0].draw(canvas, cursor_pos=held_pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(tick_seconds)
        return held_pos

        # AFTER:
        n_hold_ticks = max(1, int(hold_at_end * 1000) // ENGINE_TICK_MS)
        tick_seconds = ENGINE_TICK_MS / 1000
        loop = asyncio.get_running_loop()
        for _ in range(n_hold_ticks):
            t0 = loop.time()
            _advance_frame_if_supported(buffered_objects[0])
            bg_hold = getattr(buffered_objects[0], "bg_color", None)
            reset_canvas(canvas, bg_hold)
            canvas, _ = buffered_objects[0].draw(canvas, cursor_pos=held_pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
        return held_pos
```

- [ ] **Step 4: Update the existing `test_non_continuous_includes_holds` test**

The test at `tests/test_ticker_display.py::TestSwapAndScrollContinuous::test_non_continuous_includes_holds` asserts `tick_s in sleep_calls` (exact float equality). After C3, sleep is called with `max(0.0, tick_s - ε)` where ε comes from the real event loop — even 1 µs breaks equality. Add a mock loop that reports 0 elapsed work time so the sleep equals `tick_s` exactly.

Find the test (around line 233) and add two lines for the loop mock:

```python
    async def test_non_continuous_includes_holds(
        self, canvas, mock_frame, make_widget, monkeypatch
    ):
        from led_ticker.ticker import ENGINE_TICK_MS

        sleep_calls: list[float] = []
        _real_sleep = asyncio.sleep

        async def _record(seconds):
            sleep_calls.append(seconds)
            await _real_sleep(0)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        # ADD THESE TWO LINES: zero elapsed work time → sleep == tick_s exactly.
        mock_loop = mock.Mock()
        mock_loop.time.return_value = 0.0
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        widget = make_widget(content_width=200)
        await _swap_and_scroll(
            canvas, mock_frame, widget, hold_time=0.1, continuous=False
        )
        tick_s = ENGINE_TICK_MS / 1000
        assert (
            tick_s in sleep_calls
        ), f"Expected tick-sized sleeps ({tick_s}s) in sleep_calls; got {sleep_calls}"
        assert (
            0.1 not in sleep_calls
        ), f"hold_time bare sleep must not appear; sleep_calls={sleep_calls}"
```

- [ ] **Step 5: Run ticker tests to verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py -v
```

Expected: all tests pass, including the two new ones and the updated existing test.

- [ ] **Step 6: Implement the fix in `_image_base.py` (2 sites)**

**Site D: `_play_with_text` — add `loop` before the for loop and apply drift pattern**

Locate the for loop at line 1354 (`for tick in range(n_ticks):`). Add `loop` on the line before it and add `t0 = loop.time()` as the first statement inside the loop body. Change the sleep at line 1389.

```python
    # BEFORE (lines 1354–1389):
        for tick in range(n_ticks):
            self._pick_frame_for_elapsed(tick * tick_ms)
            self.advance_frame()
            if wrap_mode:
                self._render_wrap_tick(
                    canvas,
                    text_canvas,
                    scroll_pos,
                    baseline_y,
                    text_width,
                    sep_width,
                    cycle_width,
                )
            else:
                self._render_tick(
                    canvas,
                    text_canvas,
                    scroll_pos,
                    baseline_y,
                    text_x_left,
                    text_x_right,
                )
            canvas = frame.matrix.SwapOnVSync(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(tick_seconds)

    # AFTER:
        loop = asyncio.get_running_loop()
        for tick in range(n_ticks):
            t0 = loop.time()
            self._pick_frame_for_elapsed(tick * tick_ms)
            self.advance_frame()
            if wrap_mode:
                self._render_wrap_tick(
                    canvas,
                    text_canvas,
                    scroll_pos,
                    baseline_y,
                    text_width,
                    sep_width,
                    cycle_width,
                )
            else:
                self._render_tick(
                    canvas,
                    text_canvas,
                    scroll_pos,
                    baseline_y,
                    text_x_left,
                    text_x_right,
                )
            canvas = frame.matrix.SwapOnVSync(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
```

**Site E: `_play_with_two_row_text` — same pattern before the for loop at line 1614**

```python
    # BEFORE (line 1614 onward):
        for tick in range(n_ticks):
            self._pick_frame_for_elapsed(tick * tick_ms)
            self.advance_frame()
            if wrap_mode:
                self._render_two_row_wrap_tick(...)
            else:
                ...
            self._render_two_row_tick(...)
            canvas = frame.matrix.SwapOnVSync(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(tick_seconds)

    # AFTER:
        loop = asyncio.get_running_loop()
        for tick in range(n_ticks):
            t0 = loop.time()
            self._pick_frame_for_elapsed(tick * tick_ms)
            self.advance_frame()
            if wrap_mode:
                self._render_two_row_wrap_tick(...)
            else:
                ...
            self._render_two_row_tick(...)
            canvas = frame.matrix.SwapOnVSync(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
```

The `...` placeholders in the two-row snippet above represent the existing render arguments — do NOT omit them. Only add `loop = asyncio.get_running_loop()` before the for and `t0 = loop.time()` + updated sleep inside; leave all other lines unchanged.

- [ ] **Step 7: Run the image_base test**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_image_base.py::TestPlayWithTextDriftCompensation -v
```

Expected: all tests pass.

- [ ] **Step 8: Run the full suite to check for regressions**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: 1774 passed, 2 skipped (3 new tests added: 2 in ticker, 1 in image_base).

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/ticker.py src/led_ticker/widgets/_image_base.py \
        tests/test_ticker_display.py tests/test_widgets/test_image_base.py
git commit -m "fix: compensate tick-loop drift with loop.time() subtraction (C3, 7 sites)"
```

---

### Task 3: S15 — get_text_width LRU eviction

`get_text_width` caps its cache at 256 entries but evicts via `.clear()` — a thundering-herd: the very next call after eviction is a cache miss even for the most recently used key. Fix: pop only the oldest entry so the cache stays at maxsize instead of dropping to 1.

**Why not `functools.lru_cache`:** Tests in `test_drawing.py` import `_TEXT_WIDTH_CACHE` and `_TEXT_WIDTH_CACHE_MAXSIZE` directly. Switching to `lru_cache` would change the public test interface; pop-oldest preserves it.

**Files:**
- Modify: `src/led_ticker/drawing.py:122–124`
- Test: `tests/test_drawing.py`

- [ ] **Step 1: Write the failing tests**

**Update the existing `test_cache_evicts_at_maxsize` test** in `tests/test_drawing.py` to assert the cache stays at exactly `_TEXT_WIDTH_CACHE_MAXSIZE` after overflow (currently asserts `<= maxsize`, which passes even when wholesale-clear drops it to 6):

```python
    def test_cache_evicts_at_maxsize(self):
        """Cache evicts at maxsize so memory stays bounded even if a
        config spawns many unique strings. After eviction the cache
        must contain exactly maxsize entries — pop-one-oldest, not
        wholesale-clear."""
        from led_ticker.drawing import (
            _TEXT_WIDTH_CACHE,
            _TEXT_WIDTH_CACHE_MAXSIZE,
        )

        _TEXT_WIDTH_CACHE.clear()
        canvas = SimpleNamespace(scale=1, width=160)
        for i in range(_TEXT_WIDTH_CACHE_MAXSIZE + 5):
            get_text_width(FONT_DEFAULT, f"text_{i}", padding=0, canvas=canvas)
        # Pop-oldest keeps exactly maxsize entries; wholesale-clear would leave ~6.
        assert len(_TEXT_WIDTH_CACHE) == _TEXT_WIDTH_CACHE_MAXSIZE
```

**Add a new test** in the same `TestGetTextWidthMemoization` class, after `test_cache_evicts_at_maxsize`:

```python
    def test_cache_retains_most_recent_entry_after_overflow(self):
        """The entry that triggered eviction must survive. Wholesale-clear
        would also evict the triggering entry (cache drops from maxsize
        to 1 right after clear), leaving the very next call a miss too.
        """
        from led_ticker.drawing import (
            _TEXT_WIDTH_CACHE,
            _TEXT_WIDTH_CACHE_MAXSIZE,
        )

        _TEXT_WIDTH_CACHE.clear()
        canvas = SimpleNamespace(scale=1, width=160)

        # Fill to exactly maxsize.
        for i in range(_TEXT_WIDTH_CACHE_MAXSIZE):
            get_text_width(FONT_DEFAULT, f"old_{i}", padding=0, canvas=canvas)

        assert len(_TEXT_WIDTH_CACHE) == _TEXT_WIDTH_CACHE_MAXSIZE

        # This call triggers eviction (len >= maxsize), then inserts the new key.
        result = get_text_width(FONT_DEFAULT, "the_new_entry", padding=0, canvas=canvas)

        # Cache must stay at maxsize (evict-1 + insert-1).
        assert len(_TEXT_WIDTH_CACHE) == _TEXT_WIDTH_CACHE_MAXSIZE

        # The new entry survives — calling again hits the cache, no new entries.
        result2 = get_text_width(FONT_DEFAULT, "the_new_entry", padding=0, canvas=canvas)
        assert result == result2
        assert len(_TEXT_WIDTH_CACHE) == _TEXT_WIDTH_CACHE_MAXSIZE
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_drawing.py::TestGetTextWidthMemoization -v
```

Expected:
- `test_cache_evicts_at_maxsize` — `FAILED` (`AssertionError: assert 6 == 256` with wholesale-clear)
- `test_cache_retains_most_recent_entry_after_overflow` — `FAILED` (`assert 1 == 256` after clear)

- [ ] **Step 3: Implement the fix**

In `src/led_ticker/drawing.py`, change lines 122–124:

```python
    # BEFORE (lines 122–124):
    if len(_TEXT_WIDTH_CACHE) >= _TEXT_WIDTH_CACHE_MAXSIZE:
        _TEXT_WIDTH_CACHE.clear()
    _TEXT_WIDTH_CACHE[key] = width

    # AFTER:
    if len(_TEXT_WIDTH_CACHE) >= _TEXT_WIDTH_CACHE_MAXSIZE:
        _TEXT_WIDTH_CACHE.pop(next(iter(_TEXT_WIDTH_CACHE)))
    _TEXT_WIDTH_CACHE[key] = width
```

`next(iter(dict))` returns the oldest key in insertion order (Python 3.7+ dicts are ordered). `pop` removes exactly that one entry. The new entry is then inserted — cache stays at exactly `_TEXT_WIDTH_CACHE_MAXSIZE`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_drawing.py::TestGetTextWidthMemoization -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Run the full suite to check for regressions**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: 1775 passed, 2 skipped (1 new test added; the updated test already existed).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/drawing.py tests/test_drawing.py
git commit -m "fix: replace wholesale cache.clear() with pop-oldest in get_text_width (S15)"
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Status |
|---------|------|--------|
| C2 — feedparser blocks event loop | Task 1 | ✅ |
| C3 — tick drift in ticker.py (5 sites) | Task 2 | ✅ |
| C3 — tick drift in _image_base.py (2 sites) | Task 2 | ✅ |
| S15 — cache wholesale-clear | Task 3 | ✅ |

**Placeholder scan:** No TBD, TODO, or "similar to" references. All code blocks are complete.

**Type consistency:** `loop.time()` returns `float`. `max(0.0, float)` returns `float`. `asyncio.sleep(float)` accepted. No type mismatches.

**Existing test update:** `test_non_continuous_includes_holds` mock-loop addition is documented in Step 4 of Task 2 with complete updated test code.

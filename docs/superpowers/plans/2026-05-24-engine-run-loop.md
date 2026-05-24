# Batch 5 (DR2): Engine Run Loop Correctness

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before doing ANY work, run `git branch --show-current`. If it prints `main`, stop immediately and ask for a worktree.

**Goal:** Close the silent-failure cluster in the engine run loop: drift-compensate all 8 scroll-phase sleep calls, create per-section queues, move `transition_obj` off shared config state, store `create_task` handles for clean teardown, and wrap the config file I/O in `asyncio.to_thread`.

**Architecture:** Five separate concerns, each with its own commit. No task depends on another within this batch — they can land in any order. The S3 (per-section queue) change is the most structurally risky; read the run loop carefully before applying it. S2 (drift compensation) has the most sites but each is a mechanical 3-line pattern.

**Tech Stack:** Python asyncio, attrs

**Run tests with:** `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Baseline:** Run `make test` before starting; note the count. New tests should push the count up; existing tests must stay green.

---

### Task 1: S2 — Drift-compensate all 8 scroll-phase `asyncio.sleep` calls

All 8 `await asyncio.sleep(self.scroll_speed)` calls in `ticker.py` and `transitions/__init__.py` sleep a fixed duration regardless of draw+swap time. `_hold_ticks` was already fixed (line 391 has the `max(0.0, ...)` pattern); the scroll paths are not. The actual cadence at `scroll_speed=0.05s` is ~0.07s on hardware due to SwapOnVSync and widget draw time — 40% slower than configured.

The 8 sites are:
| File | Line | Function |
|------|------|----------|
| `ticker.py` | 478 | `_scroll_between` |
| `ticker.py` | 531 | `_swap_and_scroll` (forces_offscreen_scroll branch) |
| `ticker.py` | 548 | `_swap_and_scroll` (wraps_forever branch) |
| `ticker.py` | 567 | `_swap_and_scroll` (main overflow branch) |
| `ticker.py` | 715 | `_scroll_and_delay` (scroll-in loop) |
| `ticker.py` | 779 | `_scroll_one_by_one` (main loop) |
| `ticker.py` | 916 | `_scroll_side_by_side` (main loop) |
| `transitions/__init__.py` | 288 | `run_transition` (frame loop) |

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Modify: `src/led_ticker/transitions/__init__.py`
- Test: `tests/test_ticker_display.py`, `tests/test_transitions.py`

- [ ] **Step 1: Write failing tests**

**In `tests/test_ticker_display.py`**, add a new class after the existing scroll tests:

```python
class TestScrollDriftCompensation:
    """Scroll loops must subtract elapsed draw+swap time from each sleep
    so the actual cadence matches scroll_speed regardless of frame work (S2).
    """

    async def test_scroll_one_by_one_compensates_work_time(
        self, canvas, mock_frame, no_sleep, monkeypatch
    ):
        import asyncio as _asyncio
        from led_ticker.ticker import Ticker

        sleep_calls: list[float] = []

        async def _record(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("led_ticker.ticker.asyncio.sleep", _record)

        # Simulate 20ms of work per tick
        tick_times = iter([0.000, 0.020] * 200)
        mock_loop = mock.Mock()
        mock_loop.time.side_effect = lambda: next(tick_times)
        monkeypatch.setattr(
            "led_ticker.ticker.asyncio.get_running_loop", lambda: mock_loop
        )

        widget = _make_scrolling_widget(text="Hello World", canvas_width=canvas.width)
        ticker = Ticker(monitors=[widget], frame=mock_frame, scroll_speed=0.05)
        ticker.notif_queue = _asyncio.Queue()
        await ticker.notif_queue.put(widget)

        await ticker.run_infini_scroll(loop_count=1)

        scroll_speed = 0.05
        expected = scroll_speed - 0.020  # = 0.030
        assert sleep_calls, "no sleep calls recorded in scroll loop"
        assert all(
            abs(s - expected) < 1e-9 for s in sleep_calls
        ), f"expected drift-compensated {expected}s, got {sleep_calls[:5]}"
```

Note: `_make_scrolling_widget` is a helper that creates a simple `TickerMessage` with text wide enough to trigger scrolling. Use an existing fixture or `make_widget` if available.

- [ ] **Step 2: Run the test to confirm it fails**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestScrollDriftCompensation -v
```

Expected: `FAILED` — sleep is called with `self.scroll_speed` unchanged.

- [ ] **Step 3: Apply the drift pattern to all 8 sites in `ticker.py`**

The pattern is:
```python
# Before (bare sleep):
await asyncio.sleep(self.scroll_speed)

# After (drift-compensated):
await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
```

Where `loop = asyncio.get_running_loop()` is declared once per method before the loop, and `t0 = loop.time()` is the first statement inside each loop iteration.

**Site 1: `_scroll_between` (line 478)**

This is in `for offset in range(total_travel + 1):` starting around line 462. Add `loop` before the loop and `t0` as first line of the loop body:

```python
# Add before the for loop:
loop = asyncio.get_running_loop()
for offset in range(total_travel + 1):
    t0 = loop.time()
    canvas.Clear()
    # ... existing body ...
    canvas = _swap(canvas, self.frame)
    await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
```

**Site 2: `_swap_and_scroll` forces_offscreen_scroll branch (line 531)**

In the `while pos > stop:` loop around line 524:

```python
# Add before while loop:
loop = asyncio.get_running_loop()
while pos > stop:
    t0 = loop.time()
    pos -= 1
    # ... existing draw/swap ...
    await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
```

**Site 3: `_swap_and_scroll` wraps_forever branch (line 548)**

In the `while tick < n_ticks:` loop around line 540:

```python
# Add before while loop:
loop = asyncio.get_running_loop()
while tick < n_ticks:
    t0 = loop.time()
    # ... existing advance/draw/swap ...
    await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
    tick += 1
```

**Site 4: `_swap_and_scroll` main overflow branch (line 567)**

In the `while pos > stop_pos:` loop around line 561:

```python
# Add before while loop (or reuse `loop` if already declared in the method):
if not hasattr(loop_ref := None, "x"):  # just declare loop once
    pass
loop = asyncio.get_running_loop()
while pos > stop_pos:
    t0 = loop.time()
    pos -= 1
    # ... advance/draw/swap ...
    await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
```

Note: if `loop` is already declared for Site 2/3 in the same method, reuse it — don't redeclare.

**Site 5: `_scroll_and_delay` (line 715)**

In the `while pos > 0:` loop around line 703:

```python
loop = asyncio.get_running_loop()
while pos > 0:
    t0 = loop.time()
    self._advance_frame_if_supported(ticker_obj)
    # ... draw/swap ...
    await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
```

**Site 6: `_scroll_one_by_one` (line 779)**

In the `while True:` loop around line 759:

```python
loop = asyncio.get_running_loop()
while True:
    t0 = loop.time()
    self._advance_frame_if_supported(ticker_object)
    # ... draw, pos decrement, queue check ...
    canvas = _swap(canvas, self.frame)
    await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
```

**Site 7: `_scroll_side_by_side` (line 916)**

In the main `while True:` loop around line 823:

```python
loop = asyncio.get_running_loop()
while True:
    t0 = loop.time()
    # ... advance, draw, queue management ...
    canvas = _swap(canvas, self.frame)
    await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
```

Note: this method has a `_hold_ticks` branch that returns early — the `loop.time()` call before the while loop is fine; `loop` is in scope if the while loop body reaches the sleep.

- [ ] **Step 4: Apply the drift pattern to `run_transition` in `transitions/__init__.py`**

**Site 8: `run_transition` frame loop (line 288)**

In `transitions/__init__.py`, the loop is `for i in range(frame_count + 1):` starting around line 237. Add `loop` before the loop and `t0` at the top of the loop body:

```python
# Add before the for loop (after the _pause_presenter calls):
loop = asyncio.get_running_loop()
try:
    for i in range(frame_count + 1):
        t0 = loop.time()
        t = ease_fn(i / max(1, frame_count))
        # ... existing body ...
        await asyncio.sleep(max(0.0, scroll_speed - (loop.time() - t0)))
```

Note: `scroll_speed` here is the function parameter, not `self.scroll_speed`.

- [ ] **Step 5: Run the new drift test**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestScrollDriftCompensation -v
```

Expected: PASS.

- [ ] **Step 6: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: same count or higher (new tests added); all existing pass.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/ticker.py src/led_ticker/transitions/__init__.py tests/test_ticker_display.py
git commit -m "fix: drift-compensate all 8 scroll-phase asyncio.sleep calls (S2, 8 sites)"
```

---

### Task 2: S3 — Create per-section `asyncio.Queue` instead of sharing across sections

`src/led_ticker/app/run.py:62` creates one `asyncio.Queue` before the `while True:` section loop and passes it to every `Ticker` instance. With `loop_count=0` (cycle mode), a fast section can leave pre-filled items from the next iteration in the shared queue, which are consumed by the next section's `Ticker` (wrong data). A one-line fix: create a fresh queue per section.

**Files:**
- Modify: `src/led_ticker/app/run.py`
- Test: `tests/test_app.py` (or write a new test file)

- [ ] **Step 1: Write a failing test**

The easiest way to test this is to verify the `Ticker` constructor receives a fresh queue on each section visit. Add to `tests/test_app.py` or a new `tests/test_run.py`:

```python
class TestPerSectionQueue:
    """A fresh asyncio.Queue must be created per section, not shared
    across all sections. Sharing queues in loop_count=0 (cycle mode)
    can leave pre-filled items from a fast section in the queue, which
    are then consumed by the next section's Ticker — wrong data. (S3)
    """

    async def test_fresh_queue_per_section(self, monkeypatch, tmp_path):
        """Each section's Ticker receives a queue that was newly created
        for that section visit."""
        from led_ticker.app.run import run
        from led_ticker.config import load_config

        received_queues: list[object] = []

        OriginalTicker = Ticker

        class _SpyTicker(OriginalTicker):
            def __init__(self, *args, **kwargs):
                received_queues.append(kwargs.get("notif_queue"))
                super().__init__(*args, **kwargs)

        monkeypatch.setattr("led_ticker.app.run.Ticker", _SpyTicker)
        # ... set up a minimal two-section config and run for 2 iterations ...
        # Then assert:
        assert len(set(id(q) for q in received_queues)) == len(received_queues), (
            "Each section visit must receive a DISTINCT queue object — "
            "not the same queue reused across sections."
        )
```

Note: writing the full test requires a minimal in-memory config. Look at how other `test_app.py` tests set up config (using `tmp_path` and `write_text`). If this is too complex to write in isolation, skip the failing-test step and proceed directly to Step 2 — the change is a one-liner with an obvious correct behavior.

- [ ] **Step 2: Apply the fix**

In `src/led_ticker/app/run.py`, move the queue creation from before the section loop to inside it:

```python
# Before (around line 62):
    async with aiohttp.ClientSession() as session:
        notif_queue: asyncio.Queue[Any] = asyncio.Queue()
        last_widget: Any = None
        # ...
        while True:
            for section in config.sections:
                # ... uses notif_queue ...

# After:
    async with aiohttp.ClientSession() as session:
        last_widget: Any = None
        # ...
        while True:
            for section in config.sections:
                notif_queue: asyncio.Queue[Any] = asyncio.Queue()  # fresh per section
                # ... uses notif_queue ...
```

- [ ] **Step 3: Verify the queue is still passed to Ticker**

Read lines 204–225 of `run.py` to confirm `notif_queue` is in `ticker_kwargs`. The key `"notif_queue": notif_queue` must still be present.

- [ ] **Step 4: Run the test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: same count or higher; all pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/run.py
git commit -m "fix: create fresh asyncio.Queue per section to prevent cross-section bleed (S3)"
```

---

### Task 3: S4 — Move `transition_obj` from `TransitionConfig` to a local variable

`src/led_ticker/app/run.py:199` mutates `widget_trans_cfg.transition_obj` directly on a `TransitionConfig` dataclass that lives in the shared `config.sections` list. `TransitionConfig` carries a `transition_obj: Any = None` field specifically for this runtime assignment. This couples the config layer and the run loop.

**Files:**
- Modify: `src/led_ticker/app/run.py`
- Modify: `src/led_ticker/config.py` (remove `transition_obj` field from `TransitionConfig`)

- [ ] **Step 1: Read `TransitionConfig` in `config.py`**

```bash
grep -n "transition_obj\|TransitionConfig" src/led_ticker/config.py | head -10
```

Find the field definition. It should be something like `transition_obj: Any = None`.

- [ ] **Step 2: Read the mutation site in `run.py`**

```python
# Current code around line 195-202:
widget_trans_cfg = section.widget_transition or (
    section.transition if section.transition_specified else None
)
if widget_trans_cfg is not None and widget_trans_cfg.type != "cut":
    widget_trans_cfg.transition_obj = _build_trans_obj(widget_trans_cfg)
    transition_config = widget_trans_cfg
else:
    transition_config = None
```

- [ ] **Step 3: Determine how `transition_config.transition_obj` is used**

```bash
grep -n "transition_config\|transition_obj" src/led_ticker/app/run.py src/led_ticker/ticker.py | grep -v "^.*:#"
```

Find where `transition_obj` is read. It's likely read by the `Ticker` or `_run_swap` to dispatch the actual transition.

- [ ] **Step 4: Write a failing test verifying no mutation on the config object**

```python
class TestTransitionObjNotMutated:
    """transition_obj must NOT be stored on the shared TransitionConfig
    dataclass. TransitionConfig lives in config.sections which is reused
    on every iteration of the while True run loop. Mutating it couples the
    config layer to the run loop. (S4)
    """

    def test_transition_config_has_no_transition_obj_field(self):
        from led_ticker.config import TransitionConfig
        import dataclasses, attrs
        # After the fix: TransitionConfig should have no transition_obj field
        if hasattr(TransitionConfig, "__attrs_attrs__"):
            fields = {f.name for f in attrs.fields(TransitionConfig)}
        else:
            fields = {f.name for f in dataclasses.fields(TransitionConfig)}
        assert "transition_obj" not in fields, (
            "transition_obj must be a local variable in run.py, "
            "not a field on the shared TransitionConfig dataclass."
        )
```

- [ ] **Step 5: Run the test to confirm it fails**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestTransitionObjNotMutated" -v
```

Expected: FAILED (the field still exists).

- [ ] **Step 6: Apply the fix**

**In `src/led_ticker/app/run.py`**, replace the mutation with a local variable:

```python
# Before:
if widget_trans_cfg is not None and widget_trans_cfg.type != "cut":
    widget_trans_cfg.transition_obj = _build_trans_obj(widget_trans_cfg)
    transition_config = widget_trans_cfg
else:
    transition_config = None

# After:
if widget_trans_cfg is not None and widget_trans_cfg.type != "cut":
    transition_obj = _build_trans_obj(widget_trans_cfg)
    transition_config = (widget_trans_cfg, transition_obj)
else:
    transition_config = None
```

Note: `transition_config` is a `dict` passed to `Ticker` via `ticker_kwargs["transition_config"]`. The tuple approach above is one option; alternatively pass the transition_obj separately as a distinct key. Check how `transition_config` is consumed in `ticker.py` to pick the cleanest approach.

**In `src/led_ticker/ticker.py`**, update any code that reads `transition_config.transition_obj` to read from the local variable instead. Find all reads:

```bash
grep -n "transition_obj\|transition_config\." src/led_ticker/ticker.py | head -15
```

**In `src/led_ticker/config.py`**, remove the `transition_obj` field from `TransitionConfig`:

```python
# Before (approximate):
@attrs.define
class TransitionConfig:
    type: str = "cut"
    duration: float = 0.5
    # ... other fields ...
    transition_obj: Any = None  # REMOVE THIS LINE

# After:
@attrs.define
class TransitionConfig:
    type: str = "cut"
    duration: float = 0.5
    # ... other fields (no transition_obj)
```

- [ ] **Step 7: Run the test**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestTransitionObjNotMutated" -v
```

Expected: PASS.

- [ ] **Step 8: Run the full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: same count or higher; all pass.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/app/run.py src/led_ticker/config.py src/led_ticker/ticker.py
git commit -m "fix: move transition_obj from TransitionConfig field to local run.py variable (S4)"
```

---

### Task 4: S5 + M2 — Store `create_task` handles and add cancellation handling

Four `asyncio.create_task(...)` calls in `ticker.py` (lines 215, 258, 284, 311) discard the returned `Task` object. Uncaught exceptions silently disappear; on `SIGINT` orphaned tasks produce teardown noise. `run()` in `run.py` has no `try/finally` for task cleanup.

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Modify: `src/led_ticker/app/run.py`
- Test: `tests/test_ticker.py` or `tests/test_ticker_display.py`

- [ ] **Step 1: Write a failing test**

```python
class TestCreateTaskHandlesStored:
    """asyncio.create_task results must be stored so exceptions are not
    silently swallowed and orphaned tasks don't persist on cancellation (S5).
    """

    async def test_run_swap_stores_task_handle(self, canvas, mock_frame, monkeypatch):
        from led_ticker.ticker import Ticker
        import asyncio

        created_tasks: list[asyncio.Task] = []
        _original_create_task = asyncio.create_task

        def _spy_create_task(coro, **kwargs):
            task = _original_create_task(coro, **kwargs)
            created_tasks.append(task)
            return task

        monkeypatch.setattr("led_ticker.ticker.asyncio.create_task", _spy_create_task)

        widget = _make_simple_widget()
        ticker = Ticker(monitors=[widget], frame=mock_frame)
        ticker.notif_queue = asyncio.Queue()
        await ticker.notif_queue.put(widget)

        # The ticker itself must store task handles — check after run_swap
        await ticker.run_swap(loop_count=1)

        assert hasattr(ticker, "_bg_task") or hasattr(ticker, "_fetch_task"), (
            "Ticker must store the create_task handle as an instance attribute "
            "so it can be cancelled on teardown."
        )
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestCreateTaskHandlesStored" -v
```

Expected: FAILED.

- [ ] **Step 3: Store task handles in `ticker.py`**

The four `create_task` calls are in `run_swap`, `run_gif`, `run_forever_scroll`, and `run_infini_scroll` (all call `_build_then_enqueue`). Each method launches exactly one background task. Store it on the Ticker instance:

```python
# Before (in run_swap, run_gif, run_forever_scroll, run_infini_scroll):
asyncio.create_task(
    _build_then_enqueue(
        self.monitors,
        self.notif_queue,
        title=title,
        loop_count=loop_count,
    )
)

# After:
self._enqueue_task = asyncio.create_task(
    _build_then_enqueue(
        self.monitors,
        self.notif_queue,
        title=title,
        loop_count=loop_count,
    )
)
self._enqueue_task.add_done_callback(
    lambda t: logging.error("enqueue task failed: %s", t.exception())
    if not t.cancelled() and t.exception() is not None
    else None
)
```

Add `_enqueue_task: asyncio.Task | None = None` to the `Ticker` attrs definition (or initialize it in `__attrs_post_init__`).

- [ ] **Step 4: Add cancellation handling in `run.py`**

In `src/led_ticker/app/run.py`, wrap the section loop with task cleanup:

```python
# Find the while True: section loop and add try/finally:
    while True:
        for section in config.sections:
            ticker = Ticker(**ticker_kwargs)
            try:
                await getattr(ticker, run_method)(**run_kwargs)
            except asyncio.CancelledError:
                raise  # propagate cancellation; finally still runs
            finally:
                if ticker._enqueue_task is not None and not ticker._enqueue_task.done():
                    ticker._enqueue_task.cancel()
                    try:
                        await ticker._enqueue_task
                    except (asyncio.CancelledError, Exception):
                        pass  # expected on cancellation
```

Note: the exact location in `run.py` depends on where `ticker = Ticker(...)` and the run method call are made. Read the current code before applying.

- [ ] **Step 5: Run the test and full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestCreateTaskHandlesStored" -v
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py src/led_ticker/app/run.py
git commit -m "fix: store create_task handles, add done callbacks and cancellation teardown (S5, M2)"
```

---

### Task 5: S21 — Wrap `load_config` in `asyncio.to_thread`

`src/led_ticker/app/run.py:38` calls `load_config(path)` synchronously on the event loop. `load_config` uses `open()` + `tomllib.load()` — blocking I/O that can stall the loop on a slow SD card.

**Files:**
- Modify: `src/led_ticker/app/run.py:38`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write a failing test**

```python
class TestLoadConfigOffEventLoop:
    """load_config() uses blocking file I/O (open + tomllib.load).
    Calling it directly on the event loop stalls all coroutines for the
    duration of the disk read. It must be wrapped in asyncio.to_thread. (S21)
    """

    async def test_load_config_called_via_to_thread(self, monkeypatch, tmp_path):
        import led_ticker.app.run as run_module

        to_thread_calls: list[tuple] = []

        async def _fake_to_thread(func, *args, **kwargs):
            to_thread_calls.append((func, args))
            return func(*args, **kwargs)

        monkeypatch.setattr("led_ticker.app.run.asyncio.to_thread", _fake_to_thread)

        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[display]\n")

        # Trigger just the config-load portion of run() without running the full loop
        # (monkeypatch the rest of run() to return early)
        # ... see existing test_app.py for how to do this ...

        assert any(func.__name__ == "load_config" for func, _ in to_thread_calls), (
            "load_config must be called via asyncio.to_thread in run.py"
        )
```

Note: writing this test cleanly requires either patching the `run()` function to stop after config load or testing the `run_config_load` path specifically. Look at existing `test_app.py` patterns for calling `run()` with a mock config — use the same approach.

- [ ] **Step 2: Apply the fix**

In `src/led_ticker/app/run.py`, change the `load_config` call:

```python
# Before (around line 38):
config = load_config(config_path)

# After:
config = await asyncio.to_thread(load_config, config_path)
```

- [ ] **Step 3: Run the test and full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -k "TestLoadConfigOffEventLoop" -v
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/app/run.py
git commit -m "fix: wrap load_config in asyncio.to_thread to unblock event loop at startup (S21)"
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Status |
|---------|------|--------|
| S2 — scroll sleep drift (8 sites) | Task 1 | ✅ |
| S3 — shared notif_queue cross-section bleed | Task 2 | ✅ |
| S4 — transition_obj mutated on shared config | Task 3 | ✅ |
| S5 — create_task fire-and-forget | Task 4 | ✅ |
| M2 — no cancellation handling in run() | Task 4 | ✅ |
| S21 — blocking load_config on event loop | Task 5 | ✅ |

**Placeholder scan:** Tasks 3 and 4 have "read the current code before applying" notes — the exact integration depends on how `transition_config` and `ticker_kwargs` are structured, which requires a live read. The pattern is fully specified; the exact wiring is left to the implementer who has the code in front of them.

**Order note:** Tasks 1–5 are independent. Task 4 is the most structurally invasive (adds instance state to `Ticker`); read `Ticker.__init__` and the attrs definition before starting.

# Large #2 + #4: Ticker Methods & Visit Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull nine module-level engine functions onto `Ticker` as methods (eliminating repetitive parameter threading), extract a `_hold_ticks` helper to collapse five duplicated tick-loop bodies, and add visit-ownership tracking to `_FrameAware` so aliased widget-in-two-concurrent-visits is a loud runtime error rather than silent data corruption.

**Architecture:** Large #2 is a behaviour-preserving refactor — the same logic, just as `self.method()` instead of `free_function(self.field, ...)`. Large #4 adds an `_visit_owner` field to `_FrameAware` and a `_current_visit` counter to `Ticker`; `advance_frame(visit_id=…)` raises if a second owner claims the counter before `reset_frame()` clears it. Tasks are ordered so each commit leaves `pytest` green: Task 1 patches the AST scanner first so it passes throughout the migration.

**Tech Stack:** Python 3.13, attrs, asyncio, pytest, `ast` module (AST scanner in test suite).

---

## Important Context

### What is being migrated and why

`ticker.py` has nine module-level async functions that thread `canvas`, `frame`, `notif_queue`, and `scroll_speed` through their signatures even though **every caller is a `Ticker.run_*` method** that already owns these as instance fields. The functions are:

| Function | Will become |
|---|---|
| `_has_play` | `Ticker._has_play` (`@staticmethod`) |
| `_advance_frame_if_supported` | `Ticker._advance_frame_if_supported` (instance method after Task 5) |
| `_set_logical_scale` | `Ticker._set_logical_scale` (`@staticmethod`) |
| `_play_widget` | `Ticker._play_widget` (drops `frame` param → `self.frame`) |
| `_scroll_between` | `Ticker._scroll_between` (drops `frame`, `scroll_speed`) |
| `_swap_and_scroll` | `Ticker._swap_and_scroll` (drops `frame`, `scroll_speed`) |
| `_scroll_and_delay` | `Ticker._scroll_and_delay` (drops `frame`, `scroll_speed`) |
| `_show_one` | `Ticker._show_one` (drops `frame`, `scroll_speed`) |
| `_run_swap` | `Ticker._run_swap` (drops `frame`, `notif_queue`, `transition`, `scroll_speed`) |
| `_run_gif` | `Ticker._run_gif` (drops `frame`, `notif_queue`) |
| `_scroll_one_by_one` | `Ticker._scroll_one_by_one` (drops `frame`, `notif_queue`, `scroll_speed`) |
| `_scroll_side_by_side` | `Ticker._scroll_side_by_side` (drops `frame`, `notif_queue`, `scroll_speed`, `buffer_message`) |

Functions that do NOT move (pure utilities with no Ticker state): `_build_circle_offsets`, `_draw_hires_circle`, `_has_index`, `_swap`, `_maybe_wrap`, `_draw_bullet`, `_draw_scroll_frame`, `scroll_separator_width`.

### The `_hold_ticks` extraction

Five places in the engine share identical "run N ticks at drift-compensated rate" logic:
- `_swap_and_scroll`: pre-scroll hold (line ~1148), post-scroll hold (line ~1175), held-text path (line ~1185)
- `_scroll_and_delay`: post-scroll delay hold (line ~1451)
- `_scroll_side_by_side`: end-of-queue hold (line ~1645)

All five do:
```python
n_ticks = max(1, int(duration * 1000) // ENGINE_TICK_MS)
tick_seconds = ENGINE_TICK_MS / 1000
loop = asyncio.get_running_loop()
for _ in range(n_ticks):
    t0 = loop.time()
    _advance_frame_if_supported(widget)
    reset_canvas(canvas, bg_color)
    canvas, cursor_pos = widget.draw(canvas, cursor_pos=pos)
    canvas = _swap(canvas, frame)
    await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
```

The extracted helper:
```python
async def _hold_ticks(
    self,
    canvas: Canvas,
    widget: Any,
    n_ticks: int,
    pos: int,
    bg_color: Any,
) -> tuple[Canvas, int]:
    """Run `n_ticks` drift-compensated ticks: advance → draw → swap → sleep."""
    tick_seconds = ENGINE_TICK_MS / 1000
    loop = asyncio.get_running_loop()
    cursor_pos = 0
    for _ in range(n_ticks):
        t0 = loop.time()
        self._advance_frame_if_supported(widget)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = widget.draw(canvas, cursor_pos=pos)
        canvas = _swap(canvas, self.frame)
        await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
    return canvas, cursor_pos
```

### AST scanner impact

`tests/test_engine_redraw_contract.py` scans `ticker.py` and asserts every loop with a `_swap(…)` call also calls `_advance_frame_if_supported`. Its `_has_advance_call` currently matches only bare function calls (`ast.Name`). After migration the calls become `self._advance_frame_if_supported(…)` (an `ast.Attribute` node). **Task 1 must update `_has_advance_call` before any migration happens**, so the scanner continues to pass after each commit.

### Call graph inside the engine

The functions call each other in this order (deepest first):
```
_swap_and_scroll  ←  _show_one  ←  _run_swap
_scroll_between   ←  _run_swap
_play_widget      ←  _show_one
_scroll_and_delay ←  _scroll_one_by_one, _scroll_side_by_side
```
Migrate deepest first so each caller already uses `self.*` when the callee is moved.

### Ticker `@attrs.define` — adding fields

`Ticker` is decorated `@attrs.define`. New `init=False` fields go just inside the class body with `attrs.field(init=False, ...)`:

```python
_visit_counter: int = attrs.field(init=False, default=0)
_current_visit: int = attrs.field(init=False, default=0)
```

---

## File Map

| File | Change |
|---|---|
| `src/led_ticker/ticker.py` | Move 12 free functions to Ticker; add `_hold_ticks`; add `_visit_counter`/`_current_visit` |
| `src/led_ticker/widgets/_frame_aware.py` | Add `_visit_owner`; update `advance_frame(*, visit_id)`; update `reset_frame` |
| `tests/test_engine_redraw_contract.py` | Update `_has_advance_call` to match attribute form |
| `tests/test_frame_aware.py` | New file: visit-ownership tests |
| `tests/test_ticker.py` | Extend with method-form call assertions |

---

## Task 1: Update the AST scanner before migrating anything

**Files:**
- Modify: `tests/test_engine_redraw_contract.py`

The AST scanner's `_has_advance_call` only matches bare function calls (`ast.Name`). After Task 2 begins, every loop will call `self._advance_frame_if_supported(...)` (an `ast.Attribute` node). Update the helper now so the scanner stays green throughout the migration.

- [ ] **Step 1: Read the current `_has_advance_call` function**

```bash
grep -n "_has_advance_call\|ast.Name\|ast.Attribute" tests/test_engine_redraw_contract.py
```

Expected output: lines 59-66, showing the function currently only checks `ast.Name`.

- [ ] **Step 2: Write the failing test** (verify the scanner would fail on the attribute form)

Add this test to `tests/test_engine_redraw_contract.py` temporarily to confirm the existing code misses attribute calls:

```python
def test_has_advance_call_detects_attribute_form():
    """_has_advance_call must match self._advance_frame_if_supported(...)."""
    code = "async def f(self): self._advance_frame_if_supported(w)"
    tree = ast.parse(code)
    func = tree.body[0]
    # Before fix this fails
    assert _has_advance_call(func)
```

Run: `uv run pytest tests/test_engine_redraw_contract.py::test_has_advance_call_detects_attribute_form -v`
Expected: FAIL (the function returns False for attribute calls).

- [ ] **Step 3: Update `_has_advance_call` in `tests/test_engine_redraw_contract.py`**

Replace the existing function:

```python
def _has_advance_call(node: ast.AST) -> bool:
    """Whether `node`'s subtree calls `_advance_frame_if_supported(...)`.

    Matches both the free-function form (`_advance_frame_if_supported(w)`)
    and the instance-method form (`self._advance_frame_if_supported(w)`)
    so the scanner stays green before and after the method migration.
    """
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        # Free function: _advance_frame_if_supported(...)
        if isinstance(n.func, ast.Name) and n.func.id == "_advance_frame_if_supported":
            return True
        # Instance method: self._advance_frame_if_supported(...)
        if (
            isinstance(n.func, ast.Attribute)
            and n.func.attr == "_advance_frame_if_supported"
        ):
            return True
    return False
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `uv run pytest tests/test_engine_redraw_contract.py -v`
Expected: all tests pass including `test_has_advance_call_detects_attribute_form`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_engine_redraw_contract.py
git commit -m "test: update AST scanner to detect self._advance_frame_if_supported() method calls"
```

---

## Task 2: Move deepest helpers + extract `_hold_ticks`

**Files:**
- Modify: `src/led_ticker/ticker.py`

Move `_has_play`, `_set_logical_scale`, `_play_widget`, `_scroll_between`, and `_swap_and_scroll` onto `Ticker`. At the same time, extract `_hold_ticks` from the three repeated tick-loop bodies in `_swap_and_scroll`.

The migration is mechanical: paste the function body into the class, add `self` as the first param, replace `frame` → `self.frame`, `scroll_speed` → `self.scroll_speed`.

- [ ] **Step 1: Confirm the full test suite passes before touching anything**

Run: `uv run pytest --tb=no -q`
Expected: all tests pass (baseline).

- [ ] **Step 2: Write tests that will fail until the methods exist**

Add to `tests/test_ticker.py`:

```python
from led_ticker.ticker import Ticker

class TestTickerMethodsMigrated:
    """Verify that the engine operations are now Ticker instance/static methods."""

    def _make_ticker(self, frame):
        from unittest.mock import MagicMock
        import asyncio
        return Ticker(monitors=[], frame=frame)

    def test_has_play_is_static_method(self):
        from unittest.mock import MagicMock
        frame = MagicMock()
        ticker = Ticker(monitors=[], frame=frame)
        # _has_play must be callable as a staticmethod on the class
        assert callable(Ticker._has_play)

    def test_set_logical_scale_is_static_method(self):
        from unittest.mock import MagicMock
        frame = MagicMock()
        ticker = Ticker(monitors=[], frame=frame)
        assert callable(Ticker._set_logical_scale)

    def test_hold_ticks_method_exists(self):
        from unittest.mock import MagicMock
        frame = MagicMock()
        ticker = Ticker(monitors=[], frame=frame)
        assert callable(ticker._hold_ticks)

    def test_swap_and_scroll_is_instance_method(self):
        from unittest.mock import MagicMock
        frame = MagicMock()
        ticker = Ticker(monitors=[], frame=frame)
        assert callable(ticker._swap_and_scroll)

    def test_scroll_between_is_instance_method(self):
        from unittest.mock import MagicMock
        frame = MagicMock()
        ticker = Ticker(monitors=[], frame=frame)
        assert callable(ticker._scroll_between)

    def test_play_widget_is_instance_method(self):
        from unittest.mock import MagicMock
        frame = MagicMock()
        ticker = Ticker(monitors=[], frame=frame)
        assert callable(ticker._play_widget)
```

Run: `uv run pytest tests/test_ticker.py::TestTickerMethodsMigrated -v`
Expected: FAIL with `AttributeError` (methods don't exist yet).

- [ ] **Step 3: Move `_has_play` and `_set_logical_scale` to `Ticker` as `@staticmethod`**

Inside the `Ticker` class (after `run_infini_scroll`, before the `# --- Queue builders ---` comment), add:

```python
@staticmethod
def _has_play(widget: Any) -> bool:
    """True iff ``widget``'s class declares an async ``play`` method.

    Looks at the class (not the instance) so Mocks — which auto-create
    a callable ``.play`` attribute on access — don't false-positive.

    Raises ``RuntimeError`` if the class has a ``play`` attribute that is
    NOT a coroutinefunction: that is almost certainly a missing ``async``
    keyword and would silently route the widget to the ``draw()`` path.
    """
    method = getattr(type(widget), "play", None)
    if method is None:
        return False
    if not inspect.iscoroutinefunction(method):
        raise RuntimeError(
            f"{type(widget).__name__}.play exists but is not a coroutine function. "
            "Did you forget 'async def play'?"
        )
    return True

@staticmethod
def _set_logical_scale(widget: Any, scale: int) -> None:
    """Stash the section's logical canvas scale on a play()-style widget."""
    if hasattr(widget, "_logical_scale"):
        widget._logical_scale = scale
```

Update the remaining module-level `_has_play` and `_set_logical_scale` to call through (keep them temporarily for the callers that haven't been migrated yet):

```python
def _has_play(widget: Any) -> bool:
    return Ticker._has_play(widget)

def _set_logical_scale(widget: Any, scale: int) -> None:
    return Ticker._set_logical_scale(widget, scale)
```

- [ ] **Step 4: Add `_hold_ticks` to `Ticker`**

```python
async def _hold_ticks(
    self,
    canvas: Canvas,
    widget: Any,
    n_ticks: int,
    pos: int,
    bg_color: Any,
) -> tuple[Canvas, int]:
    """Run `n_ticks` drift-compensated ticks: advance → draw → swap → sleep."""
    tick_seconds = ENGINE_TICK_MS / 1000
    loop = asyncio.get_running_loop()
    cursor_pos = 0
    for _ in range(n_ticks):
        t0 = loop.time()
        self._advance_frame_if_supported(widget)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = widget.draw(canvas, cursor_pos=pos)
        canvas = _swap(canvas, self.frame)
        await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
    return canvas, cursor_pos
```

(Note: this calls `self._advance_frame_if_supported` — which is the module-level shim until Task 5 converts it. That's fine: `Ticker._advance_frame_if_supported` doesn't exist yet, so use the module-level function for now by calling it directly in the loop body: `_advance_frame_if_supported(widget)`. We'll update to `self.` in Task 5.)

Rewrite `_hold_ticks` body to use module-level for now:

```python
async def _hold_ticks(
    self,
    canvas: Canvas,
    widget: Any,
    n_ticks: int,
    pos: int,
    bg_color: Any,
) -> tuple[Canvas, int]:
    """Run `n_ticks` drift-compensated ticks: advance → draw → swap → sleep."""
    tick_seconds = ENGINE_TICK_MS / 1000
    loop = asyncio.get_running_loop()
    cursor_pos = 0
    for _ in range(n_ticks):
        t0 = loop.time()
        _advance_frame_if_supported(widget)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = widget.draw(canvas, cursor_pos=pos)
        canvas = _swap(canvas, self.frame)
        await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
    return canvas, cursor_pos
```

- [ ] **Step 5: Move `_play_widget` to `Ticker` as an instance method**

Add to `Ticker` class:

```python
async def _play_widget(
    self, canvas: Any, widget: Any, *, section_hold_time: float = 3.0
) -> Any:
    """Hand the canvas off to a widget's `play()` method."""
    gif_loops = getattr(widget, "gif_loops", None)
    loops = gif_loops if gif_loops is not None else (getattr(widget, "loops", 1) or 1)
    if isinstance(canvas, ScaledCanvas):
        innermost = canvas
        while isinstance(innermost.real, ScaledCanvas):
            innermost = innermost.real
        Ticker._set_logical_scale(widget, canvas.scale)
        new_real = await widget.play(
            innermost.real, self.frame, loop_count=loops, hold_time=section_hold_time
        )
        innermost.real = new_real
        return canvas
    Ticker._set_logical_scale(widget, 1)
    return await widget.play(
        canvas, self.frame, loop_count=loops, hold_time=section_hold_time
    )
```

Update the module-level `_play_widget` to delegate:
```python
async def _play_widget(
    canvas: Any, frame: Any, widget: Any, *, section_hold_time: float = 3.0
) -> Any:
    # Callers not yet migrated to use self._play_widget call this shim.
    # frame arg is ignored — the Ticker instance method uses self.frame.
    # This shim will be removed when all callers are on Ticker.
    raise RuntimeError(
        "_play_widget module-level shim called unexpectedly — "
        "all callers should go through Ticker._play_widget"
    )
```

Actually, don't do that yet since `_show_one` (not yet migrated) calls `_play_widget`. Instead update `_show_one`'s call site immediately (it's in the same file). Or keep the shim alive. The cleanest approach: update `_show_one` to call `self._play_widget` at the same time. But `_show_one` isn't a method yet. 

**Simplest approach:** Don't convert the module-level shims yet. Move `_play_widget` to Ticker AND keep the module-level version calling through:

```python
async def _play_widget(
    canvas: Any, frame: Any, widget: Any, *, section_hold_time: float = 3.0
) -> Any:
    # Temporary shim while _show_one hasn't been migrated yet.
    # Uses a singleton pattern keyed by frame to find the Ticker.
    # TODO: remove when _show_one becomes a Ticker method (Task 3).
    pass
```

Actually, this is getting complicated. **Better approach**: migrate the entire call chain in one step. Let's do `_play_widget`, `_scroll_between`, `_swap_and_scroll`, AND `_show_one` together in Task 2. Then update `_run_swap` to call `self._show_one` when it's migrated in Task 3.

Revise Task 2 to include `_show_one` and update Task 3 to cover `_run_swap`, `_run_gif`, `_scroll_one_by_one`, `_scroll_side_by_side`.

- [ ] **Step 5 (revised): Move `_play_widget` to `Ticker`**

See full body above. Keep module-level version as a shim that raises (callers migrated below in step 6).

- [ ] **Step 6: Move `_scroll_between` to `Ticker`**

```python
async def _scroll_between(
    self,
    canvas: Canvas,
    outgoing: Any,
    incoming: Any,
    outgoing_scroll_pos: int = 0,
) -> tuple[Canvas, int]:
    """Seamlessly scroll from outgoing to incoming at constant 1px/frame."""
    if hasattr(outgoing, "pause_frame"):
        outgoing.pause_frame()
    if hasattr(incoming, "pause_frame"):
        incoming.pause_frame()
    if hasattr(incoming, "reset_frame"):
        incoming.reset_frame()
    try:
        w = canvas.width
        sep_w = scroll_separator_width()
        total_travel = w + sep_w
        for offset in range(total_travel + 1):
            canvas.Clear()
            outgoing_pos = outgoing_scroll_pos - offset
            clear_start = max(0, w - offset)
            bullet_x = w + SCROLL_GAP - offset
            incoming_pos = w + sep_w - offset
            _draw_scroll_frame(
                canvas, outgoing, incoming,
                outgoing_pos, bullet_x, incoming_pos, clear_start,
            )
            canvas = _swap(canvas, self.frame)
            await asyncio.sleep(self.scroll_speed)
        return canvas, 0
    finally:
        if hasattr(outgoing, "resume_frame"):
            outgoing.resume_frame()
        if hasattr(incoming, "resume_frame"):
            incoming.resume_frame()
```

- [ ] **Step 7: Move `_swap_and_scroll` to `Ticker`, using `self._hold_ticks`**

```python
async def _swap_and_scroll(
    self,
    canvas: Canvas,
    ticker_obj: Any,
    hold_time: float = 3,
    skip_initial_draw: bool = False,
    continuous: bool = False,
) -> tuple[Canvas, int, int]:
    """Display a widget. If it overflows, hold then scroll the full text."""
    pos = 0
    bg_color = getattr(ticker_obj, "bg_color", None)
    reset_canvas(canvas, bg_color)
    canvas, cursor_pos = ticker_obj.draw(canvas, pos)

    if not skip_initial_draw:
        canvas = _swap(canvas, self.frame)

    if getattr(ticker_obj, "forces_offscreen_scroll", False) is True:
        bottom_width = getattr(ticker_obj, "_bottom_width", 0)
        cycle_width = canvas.width + bottom_width
        hold_time_ticks = int(hold_time / self.scroll_speed) if self.scroll_speed > 0 else 0
        loops_floor = getattr(ticker_obj, "bottom_text_loops", 0)
        if isinstance(loops_floor, bool) or not isinstance(loops_floor, int):
            loops_floor = 0
        loops_floor = loops_floor or 1
        n_passes = (
            max(loops_floor, math.ceil(hold_time_ticks / cycle_width))
            if cycle_width > 0
            else loops_floor
        )
        stop = -(n_passes * cycle_width)
        while pos > stop:
            pos -= 1
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, self.frame)
            await asyncio.sleep(self.scroll_speed)
        return canvas, cursor_pos, pos

    if getattr(ticker_obj, "wraps_forever", False) is True:
        n_ticks = max(1, int(hold_time / self.scroll_speed))
        loops_floor = getattr(ticker_obj, "bottom_text_loops", 0)
        if isinstance(loops_floor, bool) or not isinstance(loops_floor, int):
            loops_floor = 0
        tick = 0
        while tick < n_ticks:
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, cycle_width = ticker_obj.draw(canvas, cursor_pos=pos)
            if tick == 0 and loops_floor > 0 and cycle_width > 0:
                n_ticks = max(n_ticks, loops_floor * cycle_width)
            canvas = _swap(canvas, self.frame)
            pos -= 1
            await asyncio.sleep(self.scroll_speed)
            tick += 1
        return canvas, cursor_pos, pos

    if cursor_pos > canvas.width:
        if not continuous:
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            canvas, _ = await self._hold_ticks(canvas, ticker_obj, n_ticks, pos, bg_color)

        padding = get_widget_padding(ticker_obj, default=0)
        stop_pos = -(cursor_pos - canvas.width) + padding
        while pos > stop_pos:
            pos -= 1
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, self.frame)
            await asyncio.sleep(self.scroll_speed)

        if not continuous:
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            canvas, _ = await self._hold_ticks(canvas, ticker_obj, n_ticks, pos, bg_color)
    else:
        n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
        canvas, _ = await self._hold_ticks(canvas, ticker_obj, n_ticks, pos, bg_color)

    return canvas, cursor_pos, pos
```

- [ ] **Step 8: Move `_show_one` to `Ticker`**

```python
async def _show_one(
    self,
    canvas: Canvas,
    widget: Any,
    hold_time: float,
    skip_initial_draw: bool = False,
    continuous: bool = False,
) -> tuple[Canvas, int]:
    """Display one widget for its full visit."""
    if hasattr(widget, "reset_frame"):
        widget.reset_frame()
    if Ticker._has_play(widget):
        canvas = await self._play_widget(canvas, widget, section_hold_time=hold_time)
        return canvas, 0
    canvas, _, prev_pos = await self._swap_and_scroll(
        canvas, widget,
        hold_time=hold_time,
        skip_initial_draw=skip_initial_draw,
        continuous=continuous,
    )
    return canvas, prev_pos
```

Delete the module-level `_show_one` (it is only called from `_run_swap` which will be migrated in Task 3 — update that call in Step 8 here to `self._show_one`... but `_run_swap` is still module-level. So keep a thin shim or update `_run_swap` now).

**Cleanest approach:** In `_run_swap` (still module-level), replace calls to `_show_one(canvas, frame, widget, ...)` with a self-less call. But `_run_swap` doesn't have `self`. 

**Resolution:** Move `_run_swap` to Ticker in this same task. Add it to Task 2 step 9 below.

- [ ] **Step 9: Move `_run_swap` to `Ticker`**

```python
async def _run_swap(
    self,
    canvas: Canvas,
    delay: float = 5,
    hold_time: float = 3.0,
    continuous_scroll: bool = False,
) -> int:
    """Run swap display mode with optional transitions."""
    from led_ticker.transitions import Scroll, run_transition

    transition = self.transition_config
    is_scroll = transition is not None and isinstance(transition.transition_obj, Scroll)
    ticker_object = await self.notif_queue.get()
    canvas, prev_scroll_pos = await self._show_one(
        canvas, ticker_object, hold_time=hold_time
    )

    prev_object = ticker_object
    while not self.notif_queue.empty():
        ticker_object = self.notif_queue.get_nowait()

        if is_scroll:
            canvas, prev_scroll_pos = await self._scroll_between(
                canvas, prev_object, ticker_object,
                outgoing_scroll_pos=prev_scroll_pos,
            )
            canvas, prev_scroll_pos = await self._show_one(
                canvas, ticker_object,
                hold_time=hold_time,
                skip_initial_draw=True,
                continuous=continuous_scroll,
            )
        elif transition is not None:
            canvas = await run_transition(
                canvas, self.frame,
                prev_object, ticker_object,
                transition=transition.transition_obj,
                duration=transition.duration,
                easing=transition.easing,
                outgoing_scroll_pos=prev_scroll_pos,
                outgoing_bg_color=getattr(prev_object, "bg_color", None),
                incoming_bg_color=getattr(ticker_object, "bg_color", None),
            )
            canvas, prev_scroll_pos = await self._show_one(
                canvas, ticker_object,
                hold_time=hold_time,
                skip_initial_draw=True,
            )
        else:
            canvas, prev_scroll_pos = await self._show_one(
                canvas, ticker_object, hold_time=hold_time
            )

        prev_object = ticker_object

    return prev_scroll_pos
```

Update `Ticker.run_swap` to call `self._run_swap`:
```python
async def run_swap(self, loop_count: int = 0) -> None:
    """Swap between all running monitors."""
    logging.info("Running Swap with loop count %s...", loop_count)
    canvas = _maybe_wrap(self.frame.get_clean_canvas(), self.scale, self.content_height)
    title = self.title if self.title else None
    assert self.notif_queue is not None
    asyncio.create_task(
        _build_then_enqueue(
            self.monitors, self.notif_queue,
            title=title, loop_count=loop_count,
        )
    )
    self.last_scroll_pos = await self._run_swap(
        canvas,
        delay=self.title_delay,
        hold_time=self.hold_time,
        continuous_scroll=self.continuous_scroll,
    )
```

Delete the module-level `_run_swap`.

- [ ] **Step 10: Run the full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "refactor: move _play_widget, _scroll_between, _swap_and_scroll, _show_one, _run_swap to Ticker; extract _hold_ticks"
```

---

## Task 3: Move the remaining run functions + update public run_* methods

**Files:**
- Modify: `src/led_ticker/ticker.py`

Move `_run_gif`, `_scroll_and_delay`, `_scroll_one_by_one`, `_scroll_side_by_side` to Ticker. Update `run_gif`, `run_forever_scroll`, `run_infini_scroll` to call `self.*`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_ticker.py::TestTickerMethodsMigrated`:

```python
def test_run_gif_is_instance_method(self):
    from unittest.mock import MagicMock
    ticker = Ticker(monitors=[], frame=MagicMock())
    assert callable(ticker._run_gif)

def test_scroll_and_delay_is_instance_method(self):
    from unittest.mock import MagicMock
    ticker = Ticker(monitors=[], frame=MagicMock())
    assert callable(ticker._scroll_and_delay)

def test_scroll_one_by_one_is_instance_method(self):
    from unittest.mock import MagicMock
    ticker = Ticker(monitors=[], frame=MagicMock())
    assert callable(ticker._scroll_one_by_one)

def test_scroll_side_by_side_is_instance_method(self):
    from unittest.mock import MagicMock
    ticker = Ticker(monitors=[], frame=MagicMock())
    assert callable(ticker._scroll_side_by_side)
```

Run: `uv run pytest tests/test_ticker.py::TestTickerMethodsMigrated -v`
Expected: the four new tests FAIL.

- [ ] **Step 2: Move `_run_gif` to `Ticker`**

```python
async def _run_gif(
    self,
    canvas: Canvas,
    loop_count: int = 0,
) -> None:
    """Pull GifPlayer widgets from the queue and play() each in turn."""
    # Import preserved from module-level original — GifPlayer is
    # checked via _has_play dispatch only; no direct isinstance needed.
    assert self.notif_queue is not None
    ticker_object = await self.notif_queue.get()
    if not Ticker._has_play(ticker_object):
        return
    canvas = await self._play_widget(canvas, ticker_object)
    while not self.notif_queue.empty():
        ticker_object = self.notif_queue.get_nowait()
        if not Ticker._has_play(ticker_object):
            continue
        canvas = await self._play_widget(canvas, ticker_object)
```

(Copy the full body from the module-level `_run_gif`, substituting `self.frame` → used in `_play_widget` already, `self.notif_queue` → explicit. Match the original exactly.)

Read the full original body at lines 980–1016 before writing:

```bash
sed -n '980,1016p' src/led_ticker/ticker.py
```

Replace `frame` with `self.frame` and `notif_queue` with `self.notif_queue` throughout.

Update `Ticker.run_gif`:
```python
async def run_gif(self, loop_count: int = 0) -> None:
    logging.info("Running GIF playback with loop count %s...", loop_count)
    canvas = _maybe_wrap(self.frame.get_clean_canvas(), self.scale, self.content_height)
    assert self.notif_queue is not None
    asyncio.create_task(
        _build_then_enqueue(self.monitors, self.notif_queue, title=None, loop_count=1)
    )
    await self._run_gif(canvas, loop_count=loop_count)
```

Delete module-level `_run_gif`.

- [ ] **Step 3: Move `_scroll_and_delay` to `Ticker`, using `self._hold_ticks`**

```python
async def _scroll_and_delay(
    self,
    canvas: Canvas,
    ticker_obj: Any,
    delay: float,
    cursor_pos: int = 0,
) -> tuple[Canvas, int]:
    """Scroll ticker_obj in from off-canvas, then hold for `delay` seconds."""
    bg_color = getattr(ticker_obj, "bg_color", None)
    reset_canvas(canvas, bg_color)
    pos = cursor_pos

    canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)

    if pos <= 0:
        canvas = _swap(canvas, self.frame)

    while pos > 0:
        _advance_frame_if_supported(ticker_obj)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)
        pos -= 1
        canvas = _swap(canvas, self.frame)
        await asyncio.sleep(self.scroll_speed)

    n_ticks = max(1, int(delay * 1000) // ENGINE_TICK_MS)
    canvas, cursor_pos = await self._hold_ticks(canvas, ticker_obj, n_ticks, pos, bg_color)
    return canvas, cursor_pos
```

Delete module-level `_scroll_and_delay`.

- [ ] **Step 4: Move `_scroll_one_by_one` to `Ticker`**

```python
async def _scroll_one_by_one(
    self,
    canvas: Canvas,
    delay: float = 0,
    cursor_pos: int = 0,
) -> int:
    """Scroll widgets one-by-one, each fully scrolling off before the next."""
    assert self.notif_queue is not None
    ticker_object = await self.notif_queue.get()
    pos = cursor_pos
    last_drawn_pos = pos

    if delay:
        canvas, cursor_pos = await self._scroll_and_delay(
            canvas, ticker_object, delay, cursor_pos=pos,
        )
        logging.info("Returned to _scroll_one_by_one ...")
        pos = 0
        last_drawn_pos = pos

    while True:
        _advance_frame_if_supported(ticker_object)
        reset_canvas(canvas, getattr(ticker_object, "bg_color", None))
        canvas, final_pos = ticker_object.draw(canvas, cursor_pos=pos)
        last_drawn_pos = pos
        pos -= 1

        if final_pos < 0:
            pos = canvas.width
            try:
                ticker_object = self.notif_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        canvas = _swap(canvas, self.frame)
        await asyncio.sleep(self.scroll_speed)

    canvas.Clear()
    canvas = _swap(canvas, self.frame)
    return last_drawn_pos
```

Update `Ticker.run_infini_scroll`:
```python
async def run_infini_scroll(self, loop_count: int = 0, start_pos: int | None = None) -> None:
    logging.info("Running Infini Scroll with loop count %s...", loop_count)
    canvas = _maybe_wrap(self.frame.get_clean_canvas(), self.scale, self.content_height)
    title = self.title if self.title else None
    assert self.notif_queue is not None
    asyncio.create_task(
        _build_then_enqueue(self.monitors, self.notif_queue, title=title, loop_count=loop_count)
    )
    cursor_pos = start_pos if start_pos is not None else canvas.width
    self.last_scroll_pos = await self._scroll_one_by_one(
        canvas, cursor_pos=cursor_pos, delay=self.title_delay,
    )
```

Delete module-level `_scroll_one_by_one`.

- [ ] **Step 5: Move `_scroll_side_by_side` to `Ticker`, using `self._hold_ticks`**

```python
async def _scroll_side_by_side(
    self,
    canvas: Canvas,
    delay: float = 0,
    cursor_pos: int = 0,
    hold_at_end: float = 2.0,
) -> int:
    """Scroll widgets side-by-side. Returns the final scroll position."""
    assert self.notif_queue is not None
    logging.info("Running _scroll_side_by_side ...")
    buffered_objects: list[Any] = []
    next_monitor = await self.notif_queue.get()
    buffered_objects.append(next_monitor)
    pos = cursor_pos
    queue_empty = False

    if delay:
        canvas, cursor_pos = await self._scroll_and_delay(
            canvas, next_monitor, delay, cursor_pos=pos,
        )
        logging.info("Returned to _scroll_side_by_side ...")
        pos = 0

    while True:
        seen: set[int] = set()
        for buf_w in buffered_objects:
            if id(buf_w) not in seen:
                _advance_frame_if_supported(buf_w)
                seen.add(id(buf_w))

        first_widget = buffered_objects[0] if buffered_objects else None
        bg = getattr(first_widget, "bg_color", None) if first_widget else None
        reset_canvas(canvas, bg)

        mon_index = 0
        canvas, cursor_pos = buffered_objects[mon_index].draw(canvas, cursor_pos=pos)
        mon_0_end_pos = cursor_pos

        pos -= 1

        while cursor_pos < canvas.width:
            mon_index += 1
            if _has_index(mon_index, buffered_objects):
                canvas, cursor_pos = buffered_objects[mon_index].draw(
                    canvas, cursor_pos=cursor_pos,
                )
            elif not queue_empty:
                if self.notif_queue.empty():
                    queue_empty = True
                    break
                next_monitor = self.notif_queue.get_nowait()
                if self.buffer_msg:
                    buffered_objects.append(self.buffer_msg)
                buffered_objects.append(next_monitor)
                mon_index -= 1
            else:
                break

        if len(buffered_objects) == 1 and queue_empty and mon_0_end_pos <= canvas.width:
            held_pos = pos + 1
            canvas = _swap(canvas, self.frame)
            n_hold_ticks = max(1, int(hold_at_end * 1000) // ENGINE_TICK_MS)
            canvas, _ = await self._hold_ticks(
                canvas, buffered_objects[0], n_hold_ticks, held_pos,
                getattr(buffered_objects[0], "bg_color", None),
            )
            return held_pos

        if mon_0_end_pos < 0:
            buffered_objects.pop(0)
            pos = mon_0_end_pos - 1

        canvas = _swap(canvas, self.frame)
        await asyncio.sleep(self.scroll_speed)

        if not len(buffered_objects):
            return pos
```

Update `Ticker.run_forever_scroll`:
```python
async def run_forever_scroll(self, loop_count: int = 0, start_pos: int | None = None) -> None:
    logging.info("Running Forever Scroll with loop count %s...", loop_count)
    canvas = _maybe_wrap(self.frame.get_clean_canvas(), self.scale, self.content_height)
    title = self.title if self.title else None
    cursor_pos = start_pos if start_pos is not None else canvas.width
    assert self.notif_queue is not None
    asyncio.create_task(
        _build_then_enqueue(self.monitors, self.notif_queue, title=title, loop_count=loop_count)
    )
    self.last_scroll_pos = await self._scroll_side_by_side(
        canvas,
        delay=self.title_delay,
        cursor_pos=cursor_pos,
        hold_at_end=self.hold_time,
    )
```

Delete module-level `_scroll_side_by_side`.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all tests pass including `test_every_redraw_loop_advances_frame`.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "refactor: move _run_gif, _scroll_and_delay, _scroll_one_by_one, _scroll_side_by_side to Ticker"
```

---

## Task 4: Convert `_advance_frame_if_supported` to an instance method

**Files:**
- Modify: `src/led_ticker/ticker.py`

Now that all callers are Ticker methods, `_advance_frame_if_supported` can become an instance method. This also unblocks Task 5 (which needs `self._current_visit` to be accessible from this method).

- [ ] **Step 1: Write a failing test**

Add to `tests/test_ticker.py::TestTickerMethodsMigrated`:

```python
def test_advance_frame_if_supported_is_instance_method(self):
    from unittest.mock import MagicMock
    ticker = Ticker(monitors=[], frame=MagicMock())
    # Must be an instance method (not @staticmethod and not module-level only)
    assert hasattr(ticker, "_advance_frame_if_supported")
    assert callable(ticker._advance_frame_if_supported)
```

Run: `uv run pytest tests/test_ticker.py::TestTickerMethodsMigrated::test_advance_frame_if_supported_is_instance_method -v`
Expected: FAIL.

- [ ] **Step 2: Add `_advance_frame_if_supported` as an instance method on `Ticker`**

```python
def _advance_frame_if_supported(self, widget: Any) -> None:
    """Call `widget.advance_frame()` if the widget exposes it.

    Quietly no-ops on widgets without the _FrameAware mixin.
    After Task 5, this will pass `visit_id=self._current_visit`.
    """
    if hasattr(widget, "advance_frame"):
        widget.advance_frame()
```

- [ ] **Step 3: Update all callers in `Ticker` to use `self._advance_frame_if_supported`**

Find every `_advance_frame_if_supported(` call in the Ticker class body (the calls that were left as module-level calls in Tasks 2 and 3) and replace them with `self._advance_frame_if_supported(`.

```bash
grep -n "_advance_frame_if_supported" src/led_ticker/ticker.py
```

Replace each occurrence inside a Ticker method body from `_advance_frame_if_supported(widget)` to `self._advance_frame_if_supported(widget)`.

Also update `self._hold_ticks` body to use `self._advance_frame_if_supported`.

- [ ] **Step 4: Delete the module-level `_advance_frame_if_supported` function**

The module-level function is no longer needed. Delete it.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all tests pass. The AST scanner will now find `self._advance_frame_if_supported` via the attribute-form check added in Task 1.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker.py
git commit -m "refactor: convert _advance_frame_if_supported to Ticker instance method"
```

---

## Task 5: Visit ownership tracking (Large #4)

**Files:**
- Modify: `src/led_ticker/widgets/_frame_aware.py`
- Modify: `src/led_ticker/ticker.py`
- Create: `tests/test_frame_aware.py`

Add `_visit_owner: int | None` to `_FrameAware`. `advance_frame(*, visit_id=None)` records the first caller's `visit_id` and raises if a different `visit_id` tries to advance the same counter before `reset_frame()` clears it. Ticker tracks `_current_visit` and passes it through `_advance_frame_if_supported`.

This surfaces widget-aliasing bugs (same widget instance appearing in two concurrent section visits) as an immediate `RuntimeError` instead of silent data corruption.

- [ ] **Step 1: Write failing tests in new file `tests/test_frame_aware.py`**

```python
"""Tests for _FrameAware visit-ownership tracking (Large #4)."""
from __future__ import annotations

import pytest
import attrs
from led_ticker.widgets._frame_aware import _FrameAware


@attrs.define
class _SimpleWidget(_FrameAware):
    pass


class TestVisitOwnership:
    def test_advance_frame_no_visit_id_is_unchecked(self):
        """Calling advance_frame() without visit_id works as before."""
        w = _SimpleWidget()
        w.advance_frame()
        assert w._frame_count == 1

    def test_advance_frame_same_visit_id_allowed(self):
        """Multiple advance_frame calls with the same visit_id are fine."""
        w = _SimpleWidget()
        w.advance_frame(visit_id=1)
        w.advance_frame(visit_id=1)
        assert w._frame_count == 2

    def test_advance_frame_different_visit_id_raises(self):
        """advance_frame with a new visit_id when one is already claimed raises."""
        w = _SimpleWidget()
        w.advance_frame(visit_id=1)
        with pytest.raises(RuntimeError, match="claimed by visit_id"):
            w.advance_frame(visit_id=2)

    def test_reset_frame_clears_visit_owner(self):
        """reset_frame() releases the visit claim so a new visit_id can take over."""
        w = _SimpleWidget()
        w.advance_frame(visit_id=1)
        w.reset_frame()
        # New visit_id must work after reset
        w.advance_frame(visit_id=2)
        assert w._frame_count == 1  # reset + 1 advance

    def test_advance_frame_no_visit_id_after_claimed_does_not_raise(self):
        """Callers that don't pass visit_id bypass the ownership check."""
        w = _SimpleWidget()
        w.advance_frame(visit_id=1)
        # Module-level callers don't pass visit_id — must not raise.
        w.advance_frame()
        assert w._frame_count == 2

    def test_visit_owner_is_none_initially(self):
        w = _SimpleWidget()
        assert w._visit_owner is None


class TestTickerVisitCounter:
    def test_current_visit_increments_per_show_one(self, no_sleep):
        """_show_one increments _current_visit before each widget visit."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from led_ticker.ticker import Ticker

        frame = MagicMock()
        frame.get_clean_canvas.return_value = MagicMock(width=256, height=64)

        ticker = Ticker(monitors=[], frame=frame)
        assert ticker._current_visit == 0

        widget = MagicMock()
        widget.draw.return_value = (MagicMock(width=256, height=64), 0)
        widget.forces_offscreen_scroll = False
        widget.wraps_forever = False

        canvas = MagicMock(width=256, height=64)

        async def run():
            await ticker._show_one(canvas, widget, hold_time=0.05)

        asyncio.run(run())
        assert ticker._current_visit == 1
```

Run: `uv run pytest tests/test_frame_aware.py -v`
Expected: FAIL (fields and signature don't exist yet).

- [ ] **Step 2: Add `_visit_owner` to `_FrameAware` and update `advance_frame`**

In `src/led_ticker/widgets/_frame_aware.py`, add the `_visit_owner` field after `_effect_frames`:

```python
_visit_owner: int | None = attrs.field(init=False, default=None)
```

Update `advance_frame`:

```python
def advance_frame(self, *, visit_id: int | None = None) -> None:
    """Increment the primary counter AND all per-effect counters.
    No-op if paused.

    When *visit_id* is given, records the first caller as the owner
    and raises ``RuntimeError`` if a different ``visit_id`` calls before
    ``reset_frame()`` clears the claim. This surfaces widget-aliasing
    bugs (same instance in two concurrent section visits) immediately
    rather than silently corrupting animation state.

    Callers that omit *visit_id* bypass the ownership check — backward
    compatible with code that doesn't track visits.
    """
    if self._frame_paused:
        return
    if visit_id is not None:
        if self._visit_owner is not None and self._visit_owner != visit_id:
            raise RuntimeError(
                f"{type(self).__name__} frame counter is claimed by visit_id "
                f"{self._visit_owner!r}, but advance_frame called with "
                f"{visit_id!r}. The same widget instance appears to be "
                "advancing in two concurrent section visits."
            )
        self._visit_owner = visit_id
    self._frame_count += 1
    for attr_name, _ in self._iter_effects():
        self._effect_frames[attr_name] = self._effect_frames.get(attr_name, 0) + 1
```

Update `reset_frame` to clear `_visit_owner`:

```python
def reset_frame(self) -> None:
    """Visit-entry reset. Clears the visit ownership claim."""
    self._frame_count = 0
    self._visit_owner = None
    for attr_name, effect in self._iter_effects():
        if getattr(effect, "restart_on_visit", True):
            self._effect_frames[attr_name] = 0
```

- [ ] **Step 3: Run `_FrameAware` tests to verify the ownership logic**

Run: `uv run pytest tests/test_frame_aware.py::TestVisitOwnership -v`
Expected: all 6 tests PASS.

- [ ] **Step 4: Add `_visit_counter` and `_current_visit` to `Ticker`**

In `src/led_ticker/ticker.py`, inside the `Ticker` `@attrs.define` class body, add after `last_scroll_pos`:

```python
_visit_counter: int = attrs.field(init=False, default=0)
_current_visit: int = attrs.field(init=False, default=0)
```

- [ ] **Step 5: Update `Ticker._show_one` to increment `_current_visit` at visit start**

At the top of `_show_one`, before `reset_frame()`:

```python
async def _show_one(
    self,
    canvas: Canvas,
    widget: Any,
    hold_time: float,
    skip_initial_draw: bool = False,
    continuous: bool = False,
) -> tuple[Canvas, int]:
    """Display one widget for its full visit."""
    self._visit_counter += 1
    self._current_visit = self._visit_counter
    if hasattr(widget, "reset_frame"):
        widget.reset_frame()
    if Ticker._has_play(widget):
        canvas = await self._play_widget(canvas, widget, section_hold_time=hold_time)
        return canvas, 0
    canvas, _, prev_pos = await self._swap_and_scroll(
        canvas, widget,
        hold_time=hold_time,
        skip_initial_draw=skip_initial_draw,
        continuous=continuous,
    )
    return canvas, prev_pos
```

- [ ] **Step 6: Update `Ticker._advance_frame_if_supported` to pass `visit_id`**

```python
def _advance_frame_if_supported(self, widget: Any) -> None:
    """Call `widget.advance_frame(visit_id=self._current_visit)` if supported.

    Passing the current visit_id enables aliasing detection in
    _FrameAware: if the same widget instance is advanced by two
    concurrent callers with different visit_ids, it raises immediately.
    """
    if hasattr(widget, "advance_frame"):
        widget.advance_frame(visit_id=self._current_visit)
```

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/widgets/_frame_aware.py src/led_ticker/ticker.py tests/test_frame_aware.py tests/test_ticker.py
git commit -m "feat: add visit ownership tracking to _FrameAware and Ticker (Large #4)"
```

---

## Self-Review

### Spec coverage

- ✅ Large #2 (S2): `_scroll_and_delay`, `_scroll_one_by_one`, `_scroll_side_by_side`, `_scroll_between`, `_run_swap`, `_run_gif`, `_show_one`, `_swap_and_scroll` all become Ticker methods
- ✅ Large #2 (S3): `_hold_ticks` extracted; collapses 5 duplicate tick-loop bodies
- ✅ Large #4 (S14): `_visit_owner` + `_current_visit` + visit_id threading
- ✅ AST scanner updated before migration begins (Task 1)
- ✅ Module-level utility functions preserved (`_swap`, `_draw_scroll_frame`, etc.)
- ✅ Public `Ticker.run_*` API unchanged (no callers broken)

### Notes for implementer

1. **Read before editing.** `ticker.py` is 1193 lines. Before modifying any function, run `grep -n "def _function_name"` to get the exact line number and read that range with `sed`.

2. **One function at a time.** Convert each function, run `pytest --tb=short -q`, fix any failure before moving to the next.

3. **The AST scanner test name.** `test_every_redraw_loop_advances_frame` — run it explicitly after each function is moved to catch missed `_advance_frame_if_supported` calls.

4. **`_has_play` and `_set_logical_scale` are still referenced at module level** in the `Scroll` transition import inside `_run_swap`. The `Ticker._has_play` staticmethod is accessible as both `Ticker._has_play(w)` and `self._has_play(w)` — use the class form in `_run_swap` for clarity.

5. **`buffer_msg` field.** `_scroll_side_by_side` previously received `buffer_message` as a parameter. On `Ticker`, it reads `self.buffer_msg` (the existing field). Verify the field name:
   ```bash
   grep "buffer_msg" src/led_ticker/ticker.py | head -5
   ```

6. **`_scroll_and_delay` return.** After `_hold_ticks`, the function returns `(canvas, cursor_pos)` — `cursor_pos` comes from `_hold_ticks`'s return value, which is the last `widget.draw()` cursor_pos. This matches the original behaviour.

7. **The `_enqueue_*` queue-builder functions** (`_build_ticker_iter`, `_enqueue_ticker_objects`, `_build_then_enqueue`, `_enqueue_from_rss_feed`) are NOT migrated in this plan — they use `asyncio.create_task` and don't hold Ticker state in the same way. Leave them module-level.

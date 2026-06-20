# Widget Render Circuit Breaker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A widget whose `draw()`/`play()` raises at render time is caught, disabled, logged once, dropped from rotation, and surfaced in the web status — never freezing or crashing the panel.

**Architecture:** A run-scoped `RenderBreaker` (keyed by `id(widget)`) injected into every `Ticker`. A fixed-signature `_safe_draw` helper guards each draw site; the play path is guarded at the method level (`_play_widget` body, `_run_gif` site). `_expand_sources` filters disabled widgets from rotation. Disabled widgets are recorded in the status-board snapshot.

**Tech Stack:** Python 3.14, attrs, asyncio, pytest. (No new dependencies.)

## Global Constraints

- Worktree: `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/widget-circuit-breaker`, branch `feat/widget-circuit-breaker` (based on `origin/main` @ 13a2b09). **Run `git branch --show-current` before editing; abort if it prints `main`.**
- Run `make dev` (or `uv sync --extra dev`) once before the first commit. Tests: `PYTHONPATH=tests/stubs uv run pytest`.
- Lint/format: `uv run --extra dev ruff check src/ tests/` + `ruff format src/ tests/` (line length 88). Types: `uv run --extra dev pyright src/`.
- **No `from __future__ import annotations` in `src/`** (PEP 649 / project rule). `asyncio_mode = "auto"` — async tests are bare `async def test_…` (no decorator).
- **Render constraints (CLAUDE.md):** #1 every code path must end with a captured `SwapOnVSync` — the breaker fallback MUST return a valid canvas so the swap still happens. #12 `advance_frame` per tick is unaffected.
- **Status instrumentation must NEVER raise into the engine** (wrap in try/except, return on error) — same rule as `record_widget_visit`/`record_swap`.
- Trip on FIRST failure; permanent for the run; no retry/cooldown; no on-panel placeholder; transitions out of scope.
- `git add` new files (check `git status` for `??`). Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh`.

---

### Task 1: Status board — `disabled_widgets` + `record_disabled_widget` + schema bump

**Files:**
- Modify: `src/led_ticker/status_board.py`
- Test: `tests/test_status_board.py`

**Interfaces:**
- Produces: `record_disabled_widget(widget: Any, error: str) -> None`; `StatusBoard.disabled_widgets: list[dict[str, str]]`; `snapshot()["disabled_widgets"]`; `SCHEMA_VERSION == 4`.

- [ ] **Step 1: Update the schema tripwire + add a recording test (failing)**

In `tests/test_status_board.py`, change the existing assertion at ~line 42:

```python
    assert snap["schema"] == SCHEMA_VERSION == 4
    assert "disabled_widgets" in snap
```

Add a new test:

```python
def test_record_disabled_widget_appears_in_snapshot():
    from types import SimpleNamespace

    from led_ticker import status_board

    board = StatusBoard(path="/tmp/led-ticker-test-status.json")
    status_board.set_active_board(board)
    try:
        status_board.record_disabled_widget(
            SimpleNamespace(text="hi"), "ValueError: boom"
        )
    finally:
        status_board.set_active_board(None)
    snap = board.snapshot()
    assert snap["disabled_widgets"], "expected a disabled widget entry"
    entry = snap["disabled_widgets"][0]
    assert entry["error"] == "ValueError: boom"
    assert entry["widget"]  # a non-empty label


def test_record_disabled_widget_dedups_by_label_and_error():
    from types import SimpleNamespace

    from led_ticker import status_board

    board = StatusBoard(path="/tmp/led-ticker-test-status2.json")
    status_board.set_active_board(board)
    try:
        w = SimpleNamespace(text="hi")
        status_board.record_disabled_widget(w, "ValueError: boom")
        status_board.record_disabled_widget(w, "ValueError: boom")
    finally:
        status_board.set_active_board(None)
    assert len(board.snapshot()["disabled_widgets"]) == 1
```

(Match `set_active_board`'s actual name — it's defined in status_board.py; confirm by reading it.)

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: FAIL — `SCHEMA_VERSION` is 3 / `record_disabled_widget` missing.

- [ ] **Step 3: Implement**

In `src/led_ticker/status_board.py`:

(a) Bump the constant:

```python
SCHEMA_VERSION = 4
```

(b) Add the field to `StatusBoard` (next to `failed_plugins`):

```python
    disabled_widgets: list[dict[str, str]] = attrs.field(factory=list)
```

(c) Add it to `snapshot()` (next to `"failed_plugins"`):

```python
            "disabled_widgets": self.disabled_widgets,
```

(d) Add the recorder near `record_widget_visit` (instrumentation-safe — never raises into the engine; deduped):

```python
def record_disabled_widget(widget: Any, error: str) -> None:
    """Record a widget disabled by the render circuit breaker. Instrumentation
    only — must never raise into the engine."""
    if _ACTIVE is None:
        return
    try:
        label = type(widget).__name__
        entry = {"widget": label, "error": error}
        if entry not in _ACTIVE.disabled_widgets:
            _ACTIVE.disabled_widgets.append(entry)
            _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return
```

(Uses the widget's class name as the label — stable and matches what the breaker logs. `_widget_summary` is available if richer naming is wanted later; class name keeps the entry a clean `dict[str, str]`.)

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: PASS.

- [ ] **Step 5: Check no other test pins SCHEMA_VERSION==3**

Run: `grep -rn "SCHEMA_VERSION == 3\|\"schema\": 3\|schema.*== 3" tests/`
Expected: no matches (if any, update them to 4). Then `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py tests/test_webui_app.py tests/test_status_instrumentation.py -q` → PASS.

- [ ] **Step 6: Lint + typecheck + commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/status_board.py tests/test_status_board.py
git commit -m "feat(status): disabled_widgets snapshot + record_disabled_widget (schema 4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 2: `RenderBreaker` (`render_breaker.py`)

**Files:**
- Create: `src/led_ticker/render_breaker.py`
- Test: `tests/test_render_breaker.py`

**Interfaces:**
- Consumes: `status_board.record_disabled_widget` (Task 1).
- Produces: `RenderBreaker` with `disabled: dict[int, str]`, `is_disabled(widget) -> bool`, `trip(widget, exc) -> None`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_render_breaker.py`:

```python
import logging
from types import SimpleNamespace

from led_ticker.render_breaker import RenderBreaker


def test_trip_disables_and_records_summary():
    b = RenderBreaker()
    w = SimpleNamespace()
    assert b.is_disabled(w) is False
    b.trip(w, ValueError("boom"))
    assert b.is_disabled(w) is True
    assert b.disabled[id(w)] == "ValueError: boom"


def test_trip_logs_error_once(caplog):
    b = RenderBreaker()
    w = SimpleNamespace()
    with caplog.at_level(logging.ERROR):
        b.trip(w, ValueError("boom"))
        b.trip(w, ValueError("again"))  # second trip is a no-op
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1  # logged once, not per-call
    assert b.disabled[id(w)] == "ValueError: boom"  # first summary kept


def test_distinct_widgets_tracked_independently():
    b = RenderBreaker()
    w1, w2 = SimpleNamespace(), SimpleNamespace()
    b.trip(w1, KeyError("x"))
    assert b.is_disabled(w1) is True
    assert b.is_disabled(w2) is False
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.render_breaker'`.

- [ ] **Step 3: Implement**

Create `src/led_ticker/render_breaker.py`:

```python
"""Run-scoped widget render circuit breaker.

A widget whose draw()/play() raises at render time is disabled (skipped) rather
than crashing or freezing the panel — extending plugin load-time isolation to
render time. State is keyed by id(widget): engine widgets are built once at
startup and persist for the run, so ids are stable and never reused.
"""

import logging
from typing import Any

from led_ticker import status_board


class RenderBreaker:
    def __init__(self) -> None:
        self.disabled: dict[int, str] = {}  # id(widget) -> "TypeName: message"

    def is_disabled(self, widget: Any) -> bool:
        return id(widget) in self.disabled

    def trip(self, widget: Any, exc: BaseException) -> None:
        """Disable a widget after a render error. First trip only: logs ERROR
        with traceback once and records to the status board; later calls for the
        same widget are no-ops (so a widget tripped mid-visit doesn't re-log)."""
        if id(widget) in self.disabled:
            return
        summary = f"{type(exc).__name__}: {exc}"
        self.disabled[id(widget)] = summary
        logging.error(
            "widget %s disabled after a render error: %s",
            type(widget).__name__,
            summary,
            exc_info=exc,
        )
        status_board.record_disabled_widget(widget, summary)
```

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + typecheck + commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/render_breaker.py tests/test_render_breaker.py
git commit -m "feat(engine): RenderBreaker — run-scoped render-time widget isolation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 3: Ticker draw path — breaker field, `_safe_draw`, draw sites, rotation filter

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Test: `tests/test_render_breaker_engine.py`

**Interfaces:**
- Consumes: `RenderBreaker` (Task 2).
- Produces: `Ticker.breaker: RenderBreaker`; `Ticker._safe_draw(widget, canvas, cursor_pos=0) -> (canvas, cursor_pos)`; `_expand_sources(sources, breaker=None)`; `_build_ticker_iter(ticker_objects, title=None, loop_count=0, breaker=None)`.

- [ ] **Step 1: Write the failing draw-path engine test**

Create `tests/test_render_breaker_engine.py`. (Construct the `Ticker` the way `tests/test_ticker_display.py` does — read it for the exact fixture/kwargs; mirror that construction. `swapping_frame` rotates canvases so a dropped swap capture is caught.)

```python
from led_ticker.render_breaker import RenderBreaker
from led_ticker.ticker import Ticker, _expand_sources


class FaultyDrawWidget:
    """A widget whose draw() always raises (no play())."""

    bg_color = None

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        raise ValueError("boom-draw")


def test_expand_sources_filters_disabled():
    b = RenderBreaker()
    good, bad = object(), object()
    b.trip(bad, ValueError("x"))
    assert _expand_sources([good, bad], breaker=b) == [good]


async def test_swap_mode_survives_faulty_draw(swapping_frame):
    # A faulty widget + a good one; the loop must not raise, the swap is still
    # captured (>=2 distinct canvases), and the faulty widget is tripped.
    good = _make_message_widget("hello")  # see helper below / mirror test_ticker_display
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    await ticker.run_swap(loop_count=1)
    assert breaker.is_disabled(bad) is True
    # next pass would drop it:
    assert _expand_sources([bad, good], breaker=breaker) == [good]
```

Add the SAME no-propagation + trip assertions for the other two modes, so all
three render paths are covered (the spec requires per-mode coverage):

```python
async def test_forever_scroll_survives_faulty_draw(swapping_frame):
    good = _make_message_widget("hello")
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    await ticker.run_forever_scroll(loop_count=1)   # _scroll_side_by_side path
    assert breaker.is_disabled(bad) is True


async def test_infini_scroll_survives_faulty_draw(swapping_frame):
    good = _make_message_widget("hello")
    bad = FaultyDrawWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad, good], frame=swapping_frame, breaker=breaker)
    await ticker.run_infini_scroll(loop_count=1)    # _scroll_one_by_one path
    assert breaker.is_disabled(bad) is True
```

(Provide `_make_ticker` / `_make_message_widget` helpers by **reading
`tests/test_ticker_display.py` and reusing its exact Ticker construction +
fixtures** — the key point is `Ticker(..., breaker=breaker)` and the
`swapping_frame` fixture; assert each `run_*` call does NOT raise and
`breaker.is_disabled(bad)`. Confirm the `run_forever_scroll`/`run_infini_scroll`
signatures from `ticker.py` — pass `loop_count` so the run terminates.)

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker_engine.py -q`
Expected: FAIL — `Ticker.__init__` has no `breaker` / `_expand_sources` takes 1 arg / the run raises `ValueError`.

- [ ] **Step 3: Add the breaker field + `_safe_draw`**

In `src/led_ticker/ticker.py`:

(a) Import near the top: `from led_ticker.render_breaker import RenderBreaker`.

(b) Add the field to the `@attrs.define class Ticker` (among the defaulted fields, e.g. after `scroll_speed`):

```python
    breaker: RenderBreaker = attrs.field(factory=RenderBreaker)
```

(c) Add the helper method (near `_advance_frame_if_supported`):

```python
    def _safe_draw(self, widget, canvas, cursor_pos=0):
        """Guard one draw() call. On a render error: trip the widget and return
        the canvas unchanged (no advance) so the swap still captures a valid
        canvas (constraint #1). Already-disabled -> short-circuit before draw().
        Fallback leaves the canvas as-is; the per-tick reset_canvas already wipes
        any partial frame on the next tick (no Clear here)."""
        if self.breaker.is_disabled(widget):
            return canvas, cursor_pos
        try:
            return widget.draw(canvas, cursor_pos=cursor_pos)
        except Exception as exc:
            self.breaker.trip(widget, exc)
            return canvas, cursor_pos
```

- [ ] **Step 4: Replace the draw sites**

Replace each of these `…​.draw(canvas, cursor_pos=pos)` calls with `self._safe_draw(<obj>, canvas, pos)`, keeping the same unpack target. Sites (match by context; line numbers vs 13a2b09):

- `:421` `_hold_ticks`: `canvas, cursor_pos = self._safe_draw(widget, canvas, pos)`
- `:535` `_swap_and_scroll` (positional): `canvas, cursor_pos = self._safe_draw(ticker_obj, canvas, pos)`
- `:563` `canvas, _ = self._safe_draw(ticker_obj, canvas, pos)`
- `:578` `canvas, cycle_width = self._safe_draw(ticker_obj, canvas, pos)`
- `:601` `canvas, _ = self._safe_draw(ticker_obj, canvas, pos)`
- `:750` `_scroll_and_delay`: `canvas, cursor_pos = self._safe_draw(ticker_obj, canvas, pos)`
- `:769` `canvas, cursor_pos = self._safe_draw(ticker_obj, canvas, pos)`
- `:831` `_scroll_one_by_one`: `canvas, final_pos = self._safe_draw(ticker_object, canvas, pos)`
- `:921`, `:932` `_scroll_side_by_side`: `canvas, cursor_pos = self._safe_draw(buffered_objects[mon_index], canvas, pos)` (preserve each call's exact `pos`/cursor argument)

Do NOT touch `:1205`/`:1213` (transitions) or `:112` (`_HiresCircle.draw`).

- [ ] **Step 5: Add the rotation filter**

Change `_expand_sources` and `_build_ticker_iter`:

```python
def _expand_sources(sources, breaker=None):
    from led_ticker.widget import Container

    out = []
    for s in sources:
        if breaker is not None and breaker.is_disabled(s):
            continue
        if isinstance(s, Container):
            for story in s.feed_stories:
                if breaker is None or not breaker.is_disabled(story):
                    out.append(story)
        else:
            out.append(s)
    return out
```

Add `breaker=None` to `_build_ticker_iter(ticker_objects, title=None, loop_count=0, breaker=None)` and pass it to BOTH `_expand_sources(ticker_objects)` calls inside it (→ `_expand_sources(ticker_objects, breaker)`). At the call site (`:1168`), pass the ticker's breaker: `_build_ticker_iter(self.monitors, title=…, loop_count=…, breaker=self.breaker)` (match the existing call's args).

- [ ] **Step 6: Run draw-path tests + the relevant existing engine tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker_engine.py tests/test_ticker_display.py tests/test_engine_redraw_contract.py -q`
Expected: PASS. (The redraw-contract AST test must still pass — `_safe_draw` is the new draw call; if that test scans for literal `widget.draw(`, confirm it still recognizes the advance_frame pairing. If it greps for `.draw(`, `_safe_draw`/`widget.draw` inside it still matches; if it breaks, update the contract test to recognize `_safe_draw` as the draw call.)

- [ ] **Step 7: Full suite + lint + typecheck + commit**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/ticker.py tests/test_render_breaker_engine.py
git commit -m "feat(engine): guard widget draws with the circuit breaker + rotation filter

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 4: Ticker play path — `_play_widget` body + `_run_gif` site

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_play_widget`, `_run_gif`)
- Test: `tests/test_render_breaker_engine.py` (extend)

**Interfaces:**
- Consumes: `Ticker.breaker` (Task 3).

- [ ] **Step 1: Write the failing play-path test**

Append to `tests/test_render_breaker_engine.py`:

```python
class FaultyPlayWidget:
    """A play()-style widget whose play() always raises."""

    bg_color = None
    play_count = 1

    async def play(self, canvas, frame, loop_count=1, hold_time=3.0):
        raise ValueError("boom-play")


async def test_play_widget_survives_faulty_play(mock_frame):
    bad = FaultyPlayWidget()
    breaker = RenderBreaker()
    ticker = _make_ticker(monitors=[bad], frame=mock_frame, breaker=breaker)
    canvas = mock_frame.matrix.CreateFrameCanvas()
    # _play_widget must not raise and must return a valid canvas
    out = await ticker._play_widget(canvas, bad, section_hold_time=0.05)
    assert out is not None
    assert breaker.is_disabled(bad) is True


async def test_disabled_play_widget_short_circuits(mock_frame):
    bad = FaultyPlayWidget()
    breaker = RenderBreaker()
    breaker.trip(bad, ValueError("pre"))  # already disabled
    ticker = _make_ticker(monitors=[bad], frame=mock_frame, breaker=breaker)
    canvas = mock_frame.matrix.CreateFrameCanvas()
    # play() must NOT be called for an already-disabled widget (no raise either)
    out = await ticker._play_widget(canvas, bad, section_hold_time=0.05)
    assert out is canvas  # returned unchanged, play() skipped
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker_engine.py -q -k play`
Expected: FAIL — `_play_widget` propagates `ValueError`.

- [ ] **Step 3: Guard `_play_widget`**

Replace `_play_widget`'s body with the guarded version (entry short-circuit + try/except covering BOTH branches; on trip return the input `canvas` WITHOUT the rebind):

```python
    async def _play_widget(
        self, canvas: Any, widget: Any, *, section_hold_time: float = 3.0
    ) -> Any:
        # ... keep the existing docstring ...
        if self.breaker.is_disabled(widget):
            return canvas
        loops = getattr(widget, "play_count", 1) or 1
        try:
            if isinstance(canvas, ScaledCanvas):
                Ticker._set_logical_scale(widget, canvas.scale)
                new_real = await widget.play(
                    unwrap_to_real(canvas),
                    self.frame,
                    loop_count=loops,
                    hold_time=section_hold_time,
                )
                canvas.rebind_innermost(new_real)
                return canvas
            Ticker._set_logical_scale(widget, 1)
            return await widget.play(
                canvas, self.frame, loop_count=loops, hold_time=section_hold_time
            )
        except Exception as exc:
            self.breaker.trip(widget, exc)
            return canvas
```

- [ ] **Step 4: Guard the `_run_gif` play site (`:1044`)**

In the `_run_gif` loop, replace:

```python
            Ticker._set_logical_scale(widget, wrapper_scale)
            real = await widget.play(real, self.frame, loop_count=loop_count)
```

with:

```python
            if self.breaker.is_disabled(widget):
                continue
            Ticker._set_logical_scale(widget, wrapper_scale)
            try:
                real = await widget.play(real, self.frame, loop_count=loop_count)
            except Exception as exc:
                self.breaker.trip(widget, exc)
                continue
```

- [ ] **Step 5: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker_engine.py -q`
Expected: PASS (all draw + play tests).

- [ ] **Step 6: Full suite + lint + typecheck + commit**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/ticker.py tests/test_render_breaker_engine.py
git commit -m "feat(engine): guard play() widgets with the circuit breaker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 5: Inject one `RenderBreaker` per run (`app/run.py`)

**Files:**
- Modify: `src/led_ticker/app/run.py`
- Test: `tests/test_render_breaker_engine.py` (shared-state test) + a wiring tripwire

**Interfaces:**
- Consumes: `RenderBreaker` (Task 2), `Ticker.breaker` (Task 3).

- [ ] **Step 1: Write the failing shared-state + wiring tests**

Append to `tests/test_render_breaker_engine.py`:

```python
def test_shared_breaker_disables_across_tickers(mock_frame):
    # The whole point of injecting ONE breaker: a widget tripped while one
    # Ticker (section) renders stays disabled for the next Ticker.
    breaker = RenderBreaker()
    bad = FaultyDrawWidget()
    t1 = _make_ticker(monitors=[bad], frame=mock_frame, breaker=breaker)
    t2 = _make_ticker(monitors=[bad], frame=mock_frame, breaker=breaker)
    breaker.trip(bad, ValueError("x"))  # tripped during t1's run
    assert t2.breaker.is_disabled(bad) is True  # t2 sees it (same breaker)


def test_run_injects_a_shared_breaker():
    import inspect

    from led_ticker.app import run as run_mod

    src = inspect.getsource(run_mod.run)
    assert "RenderBreaker(" in src  # created in run()
    assert '"breaker"' in src or "breaker=" in src  # threaded into ticker_kwargs
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker_engine.py -q -k breaker`
Expected: `test_run_injects_a_shared_breaker` FAILS (run() doesn't create one yet).

- [ ] **Step 3: Wire it in**

In `src/led_ticker/app/run.py`, inside `run()`'s `try:` block AFTER `led_frame = build_frame_from_config(...)` and BEFORE the `while True:` section loop, create the run-scoped breaker:

```python
        from led_ticker.render_breaker import RenderBreaker  # noqa: PLC0415

        render_breaker = RenderBreaker()
```

Then add it to the per-section `ticker_kwargs` dict (where the other kwargs are assembled, ~`:589`):

```python
                            "breaker": render_breaker,
```

(So every `Ticker(**ticker_kwargs)` shares the one breaker.)

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker_engine.py -q -k breaker`
Expected: PASS.

- [ ] **Step 5: Full suite + lint + typecheck + commit**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/app/run.py tests/test_render_breaker_engine.py
git commit -m "feat(engine): inject one run-scoped RenderBreaker into every Ticker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 6: Docs — `disabled_widgets` in the web-status reference

**Files:**
- Modify: `docs/site/src/content/docs/concepts/web-status-ui.mdx`

**Interfaces:** none (docs).

- [ ] **Step 1: Find where the status snapshot fields are documented**

Run: `grep -n "failed_plugins\|swap_count\|snapshot\|schema" docs/site/src/content/docs/concepts/web-status-ui.mdx`
Expected: locate the section that lists snapshot fields (e.g. near `failed_plugins`).

- [ ] **Step 2: Add the `disabled_widgets` documentation**

Next to the `failed_plugins` description, add a short paragraph/row:

> **`disabled_widgets`** — widgets the render circuit breaker has disabled this run. If a widget's `draw()`/`play()` raises at render time, it is caught, dropped from the rotation, and listed here as `{ "widget": "<class>", "error": "<exception>" }` — the panel keeps running. This is the render-time counterpart of `failed_plugins` (load-time). Restart to retry a disabled widget.

(If the page documents the schema version, note it's now `4`.)

- [ ] **Step 3: Docs lint + commit**

```bash
cd docs/site && pnpm install >/dev/null 2>&1; pnpm run format && pnpm run lint && cd "$(git rev-parse --show-toplevel)"
git add docs/site/src/content/docs/concepts/web-status-ui.mdx
git commit -m "docs(status): document disabled_widgets (render circuit breaker)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

## Final verification (after all tasks)

- [ ] `PYTHONPATH=tests/stubs uv run pytest -q` — full suite green.
- [ ] `uv run --extra dev ruff check src/ tests/` + `ruff format --check src/ tests/` — clean.
- [ ] `uv run --extra dev pyright src/` — 0 errors.
- [ ] `cd docs/site && pnpm run lint` — clean.
- [ ] `git status` shows no untracked (`??`) files.
- [ ] Push and open a PR against `main`; wait for CI green before requesting merge.

## Notes / gotchas

- The breaker fallback returns a VALID canvas (unchanged) so `SwapOnVSync` is always captured (constraint #1). Do not add a `Clear()` in the fallback — the per-tick `reset_canvas` already wipes any partial frame next tick.
- A widget tripped mid-visit short-circuits on subsequent `_safe_draw` calls that same visit (no hot-loop spin); it's filtered out of rotation on the next pass.
- `record_disabled_widget` and all status calls must never raise into the engine (wrap + return).
- Catch `Exception` only — `CancelledError`/`KeyboardInterrupt`/`SystemExit` (BaseException) must propagate.
- If `tests/test_engine_redraw_contract.py` (the advance_frame AST tripwire) trips on `_safe_draw`, update it to recognize `_safe_draw` as a draw call paired with `_advance_frame_if_supported` — do NOT weaken the contract.
- Do not touch transitions (`:1205`/`:1213`) or `_HiresCircle.draw` (`:112`) — out of scope.

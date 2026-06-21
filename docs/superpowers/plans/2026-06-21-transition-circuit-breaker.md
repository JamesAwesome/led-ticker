# Transition Circuit Breaker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the #6 widget render circuit breaker to cover transition compositing — the last unguarded `widget.draw()` in the render loop — so a widget that raises during a transition is caught, tripped, and dropped instead of freezing the panel.

**Architecture:** A per-widget `_TransitionDrawGuard` (mirrors `Ticker._safe_draw`) wraps `outgoing`/`incoming` for the draw calls inside the two compositor paths (`run_transition` and `_scroll_between`/`_draw_scroll_frame`). The wrapper is allocated ONCE per transition and used ONLY as the `frame_at`/`_draw_scroll_frame` argument; pause/reset/resume/trip stay on the real widget. On a raise it trips the widget via the run-scoped `RenderBreaker` and returns the canvas unchanged so the swap still captures.

**Tech Stack:** Python 3.14, asyncio, attrs, pytest. No new dependencies.

## Global Constraints

- Worktree `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/transition-breaker`, branch `feat/transition-circuit-breaker` (base `origin/main` @ ed6b809). **Run `git branch --show-current` before editing; abort if it prints `main`.**
- Run `make dev` (or `uv sync --extra dev`) once before the first commit. Tests: `PYTHONPATH=tests/stubs uv run pytest`.
- Lint/format: `uv run --extra dev ruff check src/ tests/` + `ruff format src/ tests/` (line length 88). Types: `uv run --extra dev pyright src/`.
- **No `from __future__ import annotations` in `src/`** (PEP 649). `asyncio_mode = "auto"` — async tests are bare `async def test_…` (no decorator).
- **Render constraints:** #1 — the wrapper fallback MUST return a valid canvas (the swap always runs). #12 — `run_transition` already pauses frame counters; the guard does NOT touch advance/pause. #13 — unaffected.
- **Catch `Exception` only** (not `BaseException`) — `CancelledError`/`KeyboardInterrupt`/`SystemExit` propagate.
- Status instrumentation (`breaker.trip` → `record_disabled_widget`) never raises into the loop (already true).
- The wrapper is used ONLY as the `frame_at`/`_draw_scroll_frame` argument; `_pause_presenter`/`_reset_presenter`/`_resume_presenter` and `breaker.trip` use the REAL widget.
- `git add` new files (check `git status` for `??`). Commit trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh`

## Verified facts (from the spec + code @ ed6b809)

- `render_breaker.py`: `RenderBreaker.is_disabled(widget) -> bool`, `trip(widget, exc) -> None` (content-keyed, logs once, calls `status_board.record_disabled_widget`), `reset()`. `_key(widget)` keys on `(type, text/top_text/path)` or `id()`.
- `Ticker._safe_draw` (ticker.py:411) is the pattern to mirror: `if breaker.is_disabled(widget): return canvas, cursor_pos` else `try: return widget.draw(canvas, cursor_pos=cursor_pos)` `except Exception as exc: self.breaker.trip(widget, exc); return canvas, cursor_pos`. `Ticker.breaker` field is at ticker.py:184.
- `run_transition` (transitions/__init__.py): signature ends `..., outgoing_bg_color: Any = None, incoming_bg_color: Any = None,) -> Canvas:`. It calls `_pause_presenter(outgoing)`, `_pause_presenter(incoming)`, `_reset_presenter(incoming)`, then `loop = asyncio.get_running_loop()`, then `try:` with the `for i in range(frame_count + 1):` loop that calls `transition.frame_at(t, active, outgoing, incoming, outgoing_scroll_pos=..., duration_ms=..., incoming_bg_color=...)` then `new_canvas = _swap(active, frame)`; `finally:` resumes both. Returns `incoming_canvas if incoming_canvas is not None else canvas`.
- `_scroll_between` (ticker.py:484, a `Ticker` method): pauses/resets via `hasattr`, then `for offset in range(total_travel + 1):` calls `_draw_scroll_frame(canvas, outgoing, incoming, outgoing_pos, bullet_x, incoming_pos, clear_start)` then `_swap`. `finally:` resumes.
- `_draw_scroll_frame` (ticker.py:1242) calls `outgoing.draw(canvas, cursor_pos=outgoing_pos)` (:1255) and `incoming.draw(canvas, cursor_pos=incoming_pos)` (:1263) — UNCHANGED in this plan (it just calls `.draw()` on whatever it's given).
- The `run_transition(...)` call site is at ticker.py ~:738 (inside `_run_swap`, in the `elif self.transition_config is not None:` branch).
- No transition isinstance-checks a widget (verified) → the `__getattr__`-delegating wrapper is safe.

---

### Task 1: `_TransitionDrawGuard` + `guard_for_transition`

**Files:**
- Modify: `src/led_ticker/render_breaker.py`
- Test: `tests/test_render_breaker.py`

**Interfaces:**
- Consumes: `RenderBreaker.is_disabled`, `RenderBreaker.trip` (existing).
- Produces: `guard_for_transition(widget, breaker) -> Any` (returns `widget` when `breaker is None`, else a `_TransitionDrawGuard`); `_TransitionDrawGuard(widget, breaker)` with `.draw(canvas, *args, **kwargs) -> (canvas, int)` and `__getattr__` delegation.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_breaker.py`:

```python
def test_guard_for_transition_passthrough_without_breaker():
    from types import SimpleNamespace

    from led_ticker.render_breaker import guard_for_transition

    w = SimpleNamespace(text="hi")
    assert guard_for_transition(w, None) is w  # no breaker -> raw widget


def test_guard_draws_through_on_success():
    from led_ticker.render_breaker import RenderBreaker, guard_for_transition

    class W:
        text = "ok"
        def draw(self, canvas, cursor_pos=0, **kw):
            return ("DREW", cursor_pos)

    g = guard_for_transition(W(), RenderBreaker())
    assert g.draw("CANVAS", cursor_pos=7) == ("DREW", 7)


def test_guard_traps_raise_trips_and_returns_canvas():
    from led_ticker.render_breaker import RenderBreaker, guard_for_transition

    class Boom:
        text = "boom"
        def draw(self, canvas, cursor_pos=0, **kw):
            raise ValueError("kaboom")

    b = RenderBreaker()
    w = Boom()
    g = guard_for_transition(w, b)
    out = g.draw("CANVAS", cursor_pos=3)  # must NOT raise
    assert out == ("CANVAS", 0)           # canvas unchanged, pos 0
    assert b.is_disabled(w) is True       # tripped


def test_guard_short_circuits_disabled_without_calling_draw():
    from led_ticker.render_breaker import RenderBreaker, guard_for_transition

    class Counting:
        text = "x"
        def __init__(self):
            self.calls = 0
        def draw(self, canvas, cursor_pos=0, **kw):
            self.calls += 1
            return ("DREW", cursor_pos)

    b = RenderBreaker()
    w = Counting()
    b.trip(w, ValueError("pre"))          # already disabled
    g = guard_for_transition(w, b)
    out = g.draw("CANVAS", cursor_pos=5)
    assert out == ("CANVAS", 0)
    assert w.calls == 0                    # draw NOT called


def test_guard_delegates_other_attrs():
    from types import SimpleNamespace

    from led_ticker.render_breaker import RenderBreaker, guard_for_transition

    w = SimpleNamespace(text="hi", bg_color=(1, 2, 3))
    g = guard_for_transition(w, RenderBreaker())
    assert g.bg_color == (1, 2, 3)         # __getattr__ delegates
    assert g.text == "hi"
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker.py -q -k guard`
Expected: FAIL — `cannot import name 'guard_for_transition'`.

- [ ] **Step 3: Implement**

In `src/led_ticker/render_breaker.py`, add after the `RenderBreaker` class:

```python
class _TransitionDrawGuard:
    """Wraps a widget so its draw() is guarded by the breaker during transition
    compositing. Used ONLY as the outgoing/incoming argument to a transition's
    frame_at / _draw_scroll_frame. Mirrors Ticker._safe_draw: a disabled widget
    renders nothing; a raising draw trips the widget and leaves the canvas
    unchanged (the per-frame reset + the next tick's reset_canvas wipe any partial
    frame). __getattr__ delegates every other attribute to the real widget."""

    __slots__ = ("_widget", "_breaker")

    def __init__(self, widget: Any, breaker: "RenderBreaker") -> None:
        object.__setattr__(self, "_widget", widget)
        object.__setattr__(self, "_breaker", breaker)

    def draw(self, canvas: Any, *args: Any, **kwargs: Any) -> Any:
        widget = object.__getattribute__(self, "_widget")
        breaker = object.__getattribute__(self, "_breaker")
        if breaker.is_disabled(widget):
            return canvas, 0
        try:
            return widget.draw(canvas, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a transition draw must not freeze the panel
            breaker.trip(widget, exc)
            return canvas, 0

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_widget"), name)


def guard_for_transition(widget: Any, breaker: "RenderBreaker | None") -> Any:
    """Return a draw-guarded view of `widget` for transition compositing, or the
    widget unchanged when there is no breaker (programmatic/test callers)."""
    if breaker is None:
        return widget
    return _TransitionDrawGuard(widget, breaker)
```

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker.py -q` → PASS.

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/render_breaker.py tests/test_render_breaker.py
git commit -m "feat(engine): _TransitionDrawGuard + guard_for_transition (transition breaker)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 2: Guard `run_transition`

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py`
- Test: `tests/test_transitions.py`

**Interfaces:**
- Consumes: `guard_for_transition` (Task 1).
- Produces: `run_transition(..., breaker=None)` — new optional last param; wraps `outgoing`/`incoming` for the `frame_at` calls.

- [ ] **Step 1: Write the failing tests**

Read the existing `tests/test_transitions.py` to reuse its imports, the `swapping_frame` fixture (in `tests/conftest.py`), and how it constructs a transition + canvas. Pick a CORE transition whose `frame_at` draws BOTH sides — `WipeLeft` (`from led_ticker.transitions.wipe import WipeLeft`) or `PushLeft` (`from led_ticker.transitions.push import PushLeft`); confirm by reading its `frame_at`. Add:

```python
class _FaultyDraw:
    """A widget whose draw() always raises."""
    text = "faulty"
    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        raise ValueError("boom-in-transition")


class _GoodDraw:
    """A widget that records the canvases it was handed."""
    text = "good"
    def __init__(self):
        self.seen = []
    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        self.seen.append(id(canvas))
        return canvas, 0


async def test_run_transition_survives_faulty_incoming(swapping_frame):
    from led_ticker.render_breaker import RenderBreaker
    from led_ticker.transitions import run_transition
    from led_ticker.transitions.wipe import WipeLeft  # or PushLeft — draws both sides

    breaker = RenderBreaker()
    good, bad = _GoodDraw(), _FaultyDraw()
    canvas = swapping_frame.matrix.CreateFrameCanvas()
    out = await run_transition(
        canvas, swapping_frame, good, bad, transition=WipeLeft(),
        duration=0.05, scroll_speed=0.01, breaker=breaker,
    )
    assert out is not None                    # valid canvas (constraint #1)
    assert breaker.is_disabled(bad) is True   # faulty incoming tripped
    assert len(set(good.seen)) >= 2           # swap kept capturing; healthy side drawn


async def test_run_transition_survives_faulty_outgoing(swapping_frame):
    from led_ticker.render_breaker import RenderBreaker
    from led_ticker.transitions import run_transition
    from led_ticker.transitions.wipe import WipeLeft

    breaker = RenderBreaker()
    bad, good = _FaultyDraw(), _GoodDraw()
    canvas = swapping_frame.matrix.CreateFrameCanvas()
    out = await run_transition(
        canvas, swapping_frame, bad, good, transition=WipeLeft(),
        duration=0.05, scroll_speed=0.01, breaker=breaker,
    )
    assert out is not None
    assert breaker.is_disabled(bad) is True


async def test_run_transition_disabled_widget_not_drawn(swapping_frame):
    from led_ticker.render_breaker import RenderBreaker
    from led_ticker.transitions import run_transition
    from led_ticker.transitions.wipe import WipeLeft

    breaker = RenderBreaker()
    good, pre = _GoodDraw(), _GoodDraw()
    breaker.trip(pre, ValueError("pre"))      # already disabled
    canvas = swapping_frame.matrix.CreateFrameCanvas()
    await run_transition(
        canvas, swapping_frame, good, pre, transition=WipeLeft(),
        duration=0.05, scroll_speed=0.01, breaker=breaker,
    )
    assert pre.seen == []                      # disabled widget never drawn


async def test_run_transition_allocates_guard_once(swapping_frame, monkeypatch):
    # the wrapper must be built once per transition, not per frame
    import led_ticker.transitions as T
    from led_ticker.render_breaker import RenderBreaker
    from led_ticker.transitions.wipe import WipeLeft

    calls = {"n": 0}
    real = T.guard_for_transition
    def counting(widget, breaker):
        calls["n"] += 1
        return real(widget, breaker)
    monkeypatch.setattr(T, "guard_for_transition", counting)

    canvas = swapping_frame.matrix.CreateFrameCanvas()
    await T.run_transition(
        canvas, swapping_frame, _GoodDraw(), _GoodDraw(), transition=WipeLeft(),
        duration=0.2, scroll_speed=0.01, breaker=RenderBreaker(),
    )
    assert calls["n"] == 2  # exactly one guard per widget, regardless of frame_count
```

(If `run_transition` imports `guard_for_transition` with `from led_ticker.render_breaker import guard_for_transition`, the monkeypatch target is `led_ticker.transitions.guard_for_transition` — adjust the `monkeypatch.setattr` target to wherever the name is looked up. Confirm by how you write the import in Step 3.)

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_transitions.py -q -k "faulty or disabled_widget_not_drawn or allocates_guard"`
Expected: FAIL — `run_transition() got an unexpected keyword argument 'breaker'`.

- [ ] **Step 3: Implement**

In `src/led_ticker/transitions/__init__.py`:

(a) Import at the top (module scope), so the monkeypatch target is `led_ticker.transitions.guard_for_transition`:

```python
from led_ticker.render_breaker import guard_for_transition
```

(b) Add the param to `run_transition`'s signature (after `incoming_bg_color`):

```python
    incoming_bg_color: Any = None,
    breaker: Any = None,
) -> Canvas:
```

(c) Allocate the wrappers ONCE, immediately after `_reset_presenter(incoming)` and before `loop = asyncio.get_running_loop()`:

```python
    _reset_presenter(incoming)
    # Guard the draws so a widget that raises during compositing is tripped +
    # skipped instead of freezing the panel (mirrors Ticker._safe_draw). Built
    # ONCE here, not per-frame. pause/reset/resume + trip use the REAL widgets.
    outgoing_draw = guard_for_transition(outgoing, breaker)
    incoming_draw = guard_for_transition(incoming, breaker)
    loop = asyncio.get_running_loop()
```

(d) In the loop, pass the wrappers to `frame_at` (replace `outgoing, incoming` with `outgoing_draw, incoming_draw`):

```python
            transition.frame_at(
                t,
                active,
                outgoing_draw,
                incoming_draw,
                outgoing_scroll_pos=outgoing_scroll_pos,
                duration_ms=int(duration * 1000),
                incoming_bg_color=incoming_bg_color,
            )
```

Leave everything else (`_pause_presenter`/`_reset_presenter`/`_resume_presenter` on the real `outgoing`/`incoming`, the `incoming_scale` rewrap, the per-frame `Fill/Clear`, `_swap`, the `finally`) UNCHANGED.

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_transitions.py -q`
Expected: PASS (new tests + the existing transition suite unaffected — `breaker` defaults to `None`, so non-breaker callers are byte-for-byte unchanged).

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/transitions/__init__.py tests/test_transitions.py
git commit -m "feat(engine): guard run_transition draws with the circuit breaker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 3: Guard `_scroll_between` + pass the breaker at the `run_transition` call site

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Test: `tests/test_ticker_display.py`

**Interfaces:**
- Consumes: `guard_for_transition` (Task 1), `run_transition(..., breaker=)` (Task 2), `Ticker.breaker` (existing, ticker.py:184).

- [ ] **Step 1: Write the failing test**

In `tests/test_ticker_display.py`, mirror the existing Ticker construction there (read it). Add (a `_FaultyDraw`/`_GoodDraw` like Task 2 — define locally or import from a shared spot):

```python
async def test_scroll_between_survives_faulty_widget(swapping_frame):
    from led_ticker.render_breaker import RenderBreaker
    from led_ticker.ticker import _expand_sources

    breaker = RenderBreaker()
    good, bad = _GoodDraw(), _FaultyDraw()       # as in Task 2
    ticker = _make_ticker(monitors=[good, bad], frame=swapping_frame, breaker=breaker)
    canvas = swapping_frame.matrix.CreateFrameCanvas()
    out, _pos = await ticker._scroll_between(canvas, good, bad, outgoing_scroll_pos=0)
    assert out is not None                        # valid canvas, no propagation
    assert breaker.is_disabled(bad) is True       # faulty side tripped
    # tripped widget is dropped from the next pass:
    assert _expand_sources([bad, good], breaker) == [good]
```

(Use the same `_make_ticker` helper / fixture the other `test_ticker_display.py` tests use, passing `breaker=breaker`. `_scroll_between` reads `self.scroll_speed` + `self.frame`; a default Ticker is fine. If `_scroll_between`'s pacing makes the test slow, set the ticker's `scroll_speed` low.)

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py -q -k scroll_between_survives`
Expected: FAIL — `_scroll_between` propagates `ValueError` (currently unguarded).

- [ ] **Step 3: Implement**

In `src/led_ticker/ticker.py`:

(a) Ensure `guard_for_transition` is imported (the file already imports `RenderBreaker` from `led_ticker.render_breaker`; extend that import to include `guard_for_transition`).

(b) In `_scroll_between`, after the pause/reset block and before `loop = asyncio.get_running_loop()`, allocate the guards ONCE, and pass them to `_draw_scroll_frame`:

```python
        if hasattr(incoming, "reset_frame"):
            incoming.reset_frame()
        # Guard the per-frame draws so a widget that raises during the scroll
        # transition is tripped + skipped, not fatal. Built once; pause/resume
        # above operate on the real widgets.
        outgoing_draw = guard_for_transition(outgoing, self.breaker)
        incoming_draw = guard_for_transition(incoming, self.breaker)
        loop = asyncio.get_running_loop()
```

Then in the `for offset` loop, pass the wrappers to `_draw_scroll_frame`:

```python
                _draw_scroll_frame(
                    canvas,
                    outgoing_draw,
                    incoming_draw,
                    outgoing_pos,
                    bullet_x,
                    incoming_pos,
                    clear_start,
                )
```

Leave `_draw_scroll_frame` itself unchanged (it just calls `.draw()` on its args) and keep the `finally` resume on the real `outgoing`/`incoming` (the `hasattr(outgoing, "resume_frame")` calls).

(c) At the `run_transition(...)` call site (~ticker.py:738, the `elif self.transition_config is not None:` branch), add `breaker=self.breaker` to the call:

```python
                canvas = await run_transition(
                    canvas,
                    self.frame,
                    prev_object,
                    ticker_object,
                    transition=self.transition_fn,
                    duration=self.transition_config.duration,
                    easing=self.transition_config.easing,
                    scroll_speed=(1.0 / _fps) if _fps is not None else 0.05,
                    outgoing_scroll_pos=prev_scroll_pos,
                    outgoing_bg_color=getattr(prev_object, "bg_color", None),
                    incoming_bg_color=getattr(ticker_object, "bg_color", None),
                    breaker=self.breaker,
                )
```

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py -q`
Expected: PASS. Then the full suite (engine-wide change):
Run: `PYTHONPATH=tests/stubs uv run pytest -q` → green (existing transition/ticker tests unaffected).

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "feat(engine): guard _scroll_between + pass breaker to run_transition

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 4: Docs — flip the "transitions unguarded" note

**Files:**
- Modify: `CLAUDE.md`
- Modify (if present): `docs/site/src/content/docs/concepts/web-status-ui.mdx` (the `disabled_widgets` note)

**Interfaces:** none (docs).

- [ ] **Step 1: Find the stale notes**

Run: `grep -n "transition" CLAUDE.md | grep -i "unguarded\|non-goal\|freeze\|breaker"` and `grep -n "disabled_widgets\|circuit breaker\|render breaker" CLAUDE.md`
Expected: locate the #6 circuit-breaker invariant + the "transitions are intentionally unguarded / the one remaining freeze surface" wording (in the breaker invariant and/or the transitions section).

- [ ] **Step 2: Update CLAUDE.md**

Edit the relevant bullet(s) so they state transitions are now guarded. Replace the "transitions are a non-goal / the one remaining freeze surface / intentionally unguarded" wording with, e.g.:

> Transition compositing is guarded too: `run_transition` (via its `breaker=` param) and `_scroll_between` wrap `outgoing`/`incoming` in `render_breaker.guard_for_transition(...)` for the `frame_at`/`_draw_scroll_frame` draws, so a widget that raises during a transition is tripped + dropped (same breaker, same content-keyed `disabled_widgets` surfacing) and the transition completes with the bad widget blank — no remaining unguarded `widget.draw()` in the render loop.

Keep it consistent with the existing #6 invariant wording. If CLAUDE.md's transitions section separately lists the unguarded-draw caveat, update that too.

- [ ] **Step 3: Update the docs-site note (only if it claims transitions are unguarded)**

If `web-status-ui.mdx` (or a circuit-breaker page) says transitions aren't covered, soften it to note transition-time trips surface the same way. If no such claim exists, skip (no new page required by this plan).

- [ ] **Step 4: Docs lint (only if a docs/site .mdx changed) + commit**

```bash
# only if you edited a docs/site/**.mdx:
cd docs/site && pnpm install >/dev/null 2>&1; pnpm run format && pnpm run lint && cd "$(git rev-parse --show-toplevel)"
git add CLAUDE.md docs/site/src/content/docs/concepts/web-status-ui.mdx 2>/dev/null; git add CLAUDE.md
git commit -m "docs: transitions are now circuit-breaker-guarded

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

## Final verification (after all tasks)

- [ ] `PYTHONPATH=tests/stubs uv run pytest -q` — full suite green.
- [ ] `uv run --extra dev ruff check src/ tests/` + `ruff format --check src/ tests/` — clean.
- [ ] `uv run --extra dev pyright src/` — 0 errors.
- [ ] `git status` — no untracked (`??`) files.
- [ ] Push, open a PR against `main`, wait for CI green before requesting merge.

## Notes / gotchas

- `breaker=None` keeps `run_transition` byte-for-byte unchanged for programmatic/test callers — the existing transition suite must stay green.
- The wrapper is allocated ONCE per transition (after `_reset_presenter(incoming)` / before the loop); never per-frame (would churn allocations + the allocate-once test catches it).
- pause/reset/resume + `breaker.trip` operate on the REAL widget — the wrapper is only the `frame_at`/`_draw_scroll_frame` argument. Do not wrap before `_pause_presenter`.
- Wrapper fallback returns `(canvas, 0)` (a valid 2-tuple) so the compositor finishes the frame and `_swap` captures (constraint #1); partial pixels are wiped by the next per-frame reset.
- Catch `Exception` only.
- The sprite-trail transitions are plugins now, but they still flow through `run_transition` with the breaker, so they're guarded too — no plugin change needed.
- After merge (controller action, outside the repo): close the `project_circuit_breaker_transitions_followup` memory and update the `project_ledmatrix_steal_list` #6 note.

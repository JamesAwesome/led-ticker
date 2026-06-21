# Transition circuit breaker (close the last render-freeze surface)

**Date:** 2026-06-21
**Status:** approved (design) — design reviewed by a no-context performance engineer
**Goal:** Extend the #6 widget render circuit breaker to cover **transition compositing**, the
one remaining unguarded `widget.draw()` in the render loop. A widget that draws fine in its
hold but raises *during* a transition (or raises for the first time there) must not freeze the
panel — it must be caught, tripped via the same run-scoped `RenderBreaker` (dropped from
rotation, surfaced in the web-status `disabled_widgets`), with the transition completing on the
healthy side.

## Background / why

The #6 circuit breaker (`src/led_ticker/render_breaker.py` + `_safe_draw` in `ticker.py`)
guards every normal widget render: a `draw()` that raises is caught, the widget is tripped
(disabled, keyed by content signature), dropped from rotation via `_expand_sources(sources,
breaker)`, and surfaced. But the **transition compositors are unguarded** — the panel-review
audit (§4a) and the tracked follow-up both flagged this as the single remaining freeze surface:

1. `run_transition(...)` (`src/led_ticker/transitions/__init__.py`) loops calling
   `transition.frame_at(t, canvas, outgoing, incoming, ...)`, which internally calls
   `outgoing.draw(...)` / `incoming.draw(...)` with no try/except, then `_swap(...)`.
2. `_scroll_between(...)` → `_draw_scroll_frame(...)` (`ticker.py`, draws at ~`:1255`/`:1263`) —
   the seamless-scroll path that bypasses `run_transition`.

A raise in either path propagates out of the loop → `SwapOnVSync` is never reached → the panel
freezes (render constraint #1). This is a hole in an already-shipped safety contract.

**This is a correctness/safety fix, not an optimization.** A no-context performance review
confirmed the added per-frame guard cost is negligible — the *identical* `_safe_draw` guard
already runs on the much hotter hold path (~20×/second for seconds per widget); the transition
path runs it ~22×/transition (~10 frames × 2 widgets), ~100× cooler. Non-raising `try/except` is
zero-cost on CPython 3.11+.

## Decisions (from brainstorming + perf review)

1. **Per-widget draw-guard wrapper, not a whole-`frame_at` guard.** Wrap `outgoing`/`incoming`
   in a tiny guard whose only override is `draw()` (mirrors `_safe_draw`); pass the wrappers as
   the `frame_at` / `_draw_scroll_frame` arguments. The draws are scattered across ~30 transition
   sites, so intercepting at the object boundary touches **2 call sites + 0 transition
   implementations** (minimal blast radius) and gives **precise** trip attribution (each wrapper
   wraps exactly one widget). The simpler "one try/except around the whole `frame_at` call +
   abort" was rejected: it cannot tell which widget raised (mis-attributes the content-keyed
   trip) and produces a worse abort-and-snap visual, for no meaningful cost saving on a 10-frame
   path.
2. **Graceful-blank fallback.** On a raise the wrapper trips the widget on the first frame and
   short-circuits its draw for the remaining frames (`is_disabled` → return canvas unchanged).
   The transition **completes** with the bad widget blank; the healthy side animates normally.
   No abort/cut. Consistent with `_safe_draw`'s "render nothing for the bad widget." An
   already-disabled widget entering a transition is short-circuited the same way.
3. **Allocate each wrapper ONCE, before the frame loop** (perf refinement). Never per-frame
   (that churns ~22 throwaway objects per transition and would break `id()`/identity used by
   pause/reset and by trip's content keying). The same two wrapper instances are passed into
   every `frame_at` call of the transition.
4. **Wrapper is used ONLY as the `frame_at` argument.** `_pause_presenter` / `_reset_presenter`
   / `_resume_presenter` and `breaker.trip(...)` operate on the **real** widgets (they need the
   real object's identity + content). This keeps `__getattr__` off the per-frame path — the only
   wrapper attribute a transition touches is `draw()` (a real method, so `__getattr__` is never
   hit for it).
5. **Reuse `RenderBreaker.trip` semantics unchanged** — trip-on-first, content-signature key,
   `status_board.record_disabled_widget` surfacing. No new disable mechanism.
6. **Back-compat:** `run_transition` gains an optional `breaker=None` param; `None` = today's
   behavior (no wrapping) for programmatic/test callers. `_scroll_between` is a `Ticker` method,
   so it uses `self.breaker` directly.

## Components

### `src/led_ticker/render_breaker.py` — the guard wrapper

A small wrapper next to `RenderBreaker`, reused by both compositor paths:

```python
class _TransitionDrawGuard:
    """Wraps a widget so its draw() is guarded by the breaker during transition
    compositing. Used ONLY as the outgoing/incoming argument to a transition's
    frame_at / _draw_scroll_frame. Mirrors Ticker._safe_draw: a disabled widget
    renders nothing; a raising draw trips the widget and leaves the canvas
    unchanged (the per-frame reset + the next tick's reset_canvas wipe any partial
    frame). __getattr__ delegates every other attribute to the real widget."""

    __slots__ = ("_widget", "_breaker")

    def __init__(self, widget: Any, breaker: Any) -> None:
        object.__setattr__(self, "_widget", widget)
        object.__setattr__(self, "_breaker", breaker)

    def draw(self, canvas: Any, *args: Any, **kwargs: Any) -> Any:
        w = self._widget
        if self._breaker.is_disabled(w):
            return canvas, 0
        try:
            return w.draw(canvas, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a transition draw must not freeze the panel
            self._breaker.trip(w, exc)
            return canvas, 0

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_widget"), name)


def guard_for_transition(widget: Any, breaker: Any) -> Any:
    """Return a draw-guarded view of `widget` for transition compositing, or the
    widget unchanged when there is no breaker (programmatic/test callers)."""
    if breaker is None:
        return widget
    return _TransitionDrawGuard(widget, breaker)
```

Notes:
- `draw(self, canvas, *args, **kwargs)` passthrough handles every transition's call shape
  (`cursor_pos=`, `y_offset=`, positional — see push.py/wipe.py/effects.py). On success it
  returns exactly what the real `draw` returns (some transitions use the `(canvas, pos)` return);
  on the disabled/raise path it returns `(canvas, 0)` (a valid 2-tuple, matching `_safe_draw`).
- `__slots__` + `object.__setattr__` keep the wrapper cheap and keep `__getattr__` correct (no
  accidental recursion). `is_disabled`/`trip` re-key off the real widget every frame, same as the
  hold path (left uncached for parity).

### `src/led_ticker/transitions/__init__.py` — `run_transition`

- New signature param: `run_transition(..., breaker: Any = None)`.
- After `_reset_presenter(incoming)` (just before the frame loop), allocate the two wrappers
  **once**:
  ```python
  outgoing_draw = guard_for_transition(outgoing, breaker)
  incoming_draw = guard_for_transition(incoming, breaker)
  ```
- In the loop, pass the wrappers to `frame_at` instead of the raw widgets:
  ```python
  transition.frame_at(t, active, outgoing_draw, incoming_draw, ...)
  ```
- Everything else unchanged: `_pause_presenter`/`_reset_presenter`/`_resume_presenter` stay on
  the **real** `outgoing`/`incoming`; the cross-scale `incoming_scale` rewrap, the per-frame
  `Fill/Clear` reset, `_swap`, and the `finally` resume are untouched. The swap still always runs
  (constraint #1).

### `src/led_ticker/ticker.py` — `_scroll_between` + call sites

- `_scroll_between` (a `Ticker` method): allocate `guard_for_transition(outgoing, self.breaker)`
  / `guard_for_transition(incoming, self.breaker)` **once** before its `for offset` loop, and
  pass the wrappers to `_draw_scroll_frame(...)`. (`_draw_scroll_frame` itself is unchanged — it
  just calls `.draw()` on whatever it's given.) Pause/reset/resume stay on the real widgets.
- The `run_transition(...)` call site (~`:738`) passes `breaker=self.breaker`.

### Docs / invariants

- `CLAUDE.md`: flip the #6 / transitions notes from "transitions are intentionally unguarded"
  to "transitions are guarded via `guard_for_transition` (same breaker, same trip semantics)";
  the `_scroll_between`/`run_transition` draws are no longer a freeze surface.
- Update the docs-site circuit-breaker page (if it exists by then; the panel review proposed
  creating one) / `web-status-ui.mdx` to note transition-time trips surface the same way.
- Close the `project_circuit_breaker_transitions_followup` memory.

## Data flow (a transition where `incoming` raises)

```
run_transition(..., breaker=self.breaker)
  _pause_presenter(outgoing); _pause_presenter(incoming); _reset_presenter(incoming)   # real widgets
  outgoing_draw = guard(outgoing); incoming_draw = guard(incoming)                     # once
  loop frame 0..N:
    reset active (Fill/Clear)
    frame_at(t, active, outgoing_draw, incoming_draw, ...)
        -> outgoing_draw.draw(...)  -> real draw OK
        -> incoming_draw.draw(...)  -> raises
              -> breaker.trip(incoming, exc)   # first frame only; content-keyed; status surfaced
              -> returns (active, 0)           # canvas unchanged; incoming renders blank
    _swap(active, frame)                        # always runs -> constraint #1 honored
  finally: _resume_presenter(outgoing); _resume_presenter(incoming)
# next pass: _expand_sources(sources, breaker) drops `incoming` from rotation
```

Frames 1..N: `incoming_draw.draw` sees `is_disabled` → returns immediately (no draw, no re-log).

## Error handling

- A transition draw raise never propagates: caught in the wrapper, trips, returns a valid
  `(canvas, pos)`. The compositor finishes the frame and `_swap` captures (constraint #1). Any
  partial pixels from a mid-draw raise are wiped by the next per-frame reset / the next tick's
  `reset_canvas`.
- Only `Exception` is caught — `CancelledError`/`KeyboardInterrupt`/`SystemExit` (BaseException)
  propagate, same as `_safe_draw`.
- `breaker.trip` already routes through `status_board.record_disabled_widget`, which never raises
  into the loop (instrumentation-safe).
- `breaker=None` (programmatic/test callers) → `guard_for_transition` returns the raw widget →
  byte-for-byte current behavior.

## Non-goals

- No retry/cooldown/auto-re-enable and no on-panel placeholder for a tripped widget (same as #6
  — recovery is a config reload, which clears the breaker).
- No change to transition *implementations* (`frame_at` bodies) or the `Transition` protocol.
- No abort/cut behavior — transitions complete with the bad widget blank (decision 2).

## Testing

- **Wrapper unit (`tests/test_render_breaker.py`)**: `guard_for_transition(w, None) is w`;
  a guarded faulty widget's `draw()` returns `(canvas, 0)` + trips it (no raise); a disabled
  widget's `draw()` is NOT called (call-counter) and returns `(canvas, 0)`; `__getattr__`
  delegates a sample attribute (e.g. `bg_color`).
- **`run_transition` (`tests/test_transitions.py`)** with `swapping_frame`: a `FaultyDrawWidget`
  as `incoming` (and a second test as `outgoing`) through a real transition → the call does NOT
  raise, returns a valid canvas, captured ≥2 distinct canvases (swap honored), the faulty widget
  is `breaker.is_disabled(...)` afterward, the healthy side still rendered. An already-disabled
  widget → its `draw` not called.
- **`_scroll_between` (`tests/test_ticker_display.py`)**: same shape via the scroll path
  (faulty outgoing/incoming → no raise, trip, healthy side rendered).
- **Filter integration**: after a transition trips a widget, `_expand_sources([bad, good],
  breaker)` returns `[good]` (dropped next pass).
- **Allocate-once tripwire**: assert (e.g. via a spy/`__getattr__` counter or an AST check) the
  wrapper is constructed once per transition, not per frame.

## Verification gates

- `PYTHONPATH=tests/stubs uv run pytest` green (new wrapper + compositor tests + the existing
  transition/ticker suites unaffected).
- `uv run --extra dev ruff check src/ tests/` + `ruff format`.
- `uv run --extra dev pyright src/` clean.

## Key constraints (carried into the plan)

- No `from __future__ import annotations` in `src/` (PEP 649).
- `asyncio_mode = "auto"` — async tests are bare `async def`.
- Render constraints: #1 the wrapper fallback returns a valid canvas so `_swap` always captures;
  #12 `run_transition` already pauses frame counters for the duration (the guard doesn't touch
  advance/pause); #13 unaffected.
- Status instrumentation never raises into the loop.
- The wrapper is used ONLY as the `frame_at`/`_draw_scroll_frame` argument; pause/reset/resume/
  trip use the real widget.

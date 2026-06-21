# Widget-level render circuit breaker (adoption item #6)

**Date:** 2026-06-20
**Status:** approved (design), pre-implementation
**Goal:** A widget whose `draw()` / `play()` raises at render time must not freeze
or crash the panel — catch it, disable that widget, log it once, drop it from the
rotation, and surface it in the web status. Extends the existing plugin
*load-time* error isolation to *render time*.

## Background / why

Plugin load is already isolated: a plugin that fails to import is skipped, logged,
and recorded in `LoadedPlugins.failed` / the status board's `failed_plugins` — it
never crashes the app. But at **render** time there is no such net: an exception
in a widget's `draw()` / `play()` inside the engine loop (`ticker.py`) propagates
and can break the display loop (the panel freezes — render constraint #1). This
feature applies the same isolation philosophy to render time.

The render engine recreates a `Ticker` per section/widget inside the main loop
(`app/run.py`), and widgets are slotted `@attrs.define` instances (can't stash a
flag on them). So the breaker state lives in a **run-scoped object injected into
every Ticker**, not on the Ticker or the widget.

A performance review (perf engineer, no-context) validated the hot-path cost as
negligible (~single-digit µs/s at the ~60–160 draws/s worst case in side-by-side
mode; `try/except` with no raise is ~free on CPython 3.11+) and drove two design
choices below: **no per-call closure** (use fixed-signature helpers) and **per-draw
granularity** (a widget can draw fine for 100 ticks then raise on tick 101).

## Decisions (from brainstorming + perf review)

Superseded: keying changed from id() to a content-signature (type+text/path) with id() fallback, to handle container stories rebuilt each refresh — see `render_breaker._key()`.

1. **Coverage: all widget render modes** — swap+gif (`_show_one` → its draw/play
   seams), forever-scroll (`_scroll_side_by_side`), infini-scroll
   (`_scroll_one_by_one`), and the shared draw/play seams. Transitions deferred.
2. **Trip on first failure** — mirror load-time isolation: a render raise disables
   the widget immediately (no retry/cooldown), permanent for the run.
3. **Skip renders nothing** — the failing call returns the canvas unchanged (no
   advance); the widget is then filtered from rotation. No on-panel placeholder.
4. **Surface in web status** — a new `disabled_widgets` snapshot field, mirroring
   `failed_plugins`.
5. **Run-scoped `RenderBreaker` injected into each Ticker** (not Ticker-state, not
   a widget attr, not a module global).
6. **Per-draw helpers, no closures** — `_safe_draw` / `_safe_play` taking real
   args; inline at each site.

## Component: `RenderBreaker` (`src/led_ticker/render_breaker.py`)

```python
import logging
from typing import Any

from led_ticker import status_board


class RenderBreaker:
    """Run-scoped render-time isolation. Keyed by id(widget); widgets are built
    once at startup and persist for the run, so ids are stable and never reused
    (no GC churn for engine widgets)."""

    def __init__(self) -> None:
        self.disabled: dict[int, str] = {}  # id(widget) -> "TypeName: message"

    def is_disabled(self, widget: Any) -> bool:
        return id(widget) in self.disabled

    def trip(self, widget: Any, exc: BaseException) -> None:
        """Disable a widget after a render error. First trip only: logs ERROR
        with traceback ONCE and records to the status board; subsequent calls are
        no-ops (so a widget tripped mid-visit doesn't re-log)."""
        if id(widget) in self.disabled:
            return
        summary = f"{type(exc).__name__}: {exc}"
        self.disabled[id(widget)] = summary
        logging.error(
            "widget %s disabled after a render error: %s",
            type(widget).__name__, summary, exc_info=exc,
        )
        status_board.record_disabled_widget(widget, summary)
```

Created **once** in `app/run.py:run()` and passed into every `Ticker(...)` via
`ticker_kwargs` (run-scoped → fresh per run, hermetic in tests). The `Ticker`
gains a `breaker: RenderBreaker = attrs.field(factory=RenderBreaker)` field so a
directly-constructed Ticker (tests) always has one, while `run()` injects the
shared instance.

## Engine integration (`src/led_ticker/ticker.py`)

### Draw path — `_safe_draw` (fixed-signature helper, no per-call lambda)

```python
def _safe_draw(self, widget, canvas, cursor_pos=0):
    """Guard one draw() call. On a render error: trip the widget and return the
    canvas unchanged (no advance) so the swap still captures a valid canvas
    (constraint #1). Already-disabled -> short-circuit before draw()."""
    if self.breaker.is_disabled(widget):
        return canvas, cursor_pos
    try:
        return widget.draw(canvas, cursor_pos=cursor_pos)
    except Exception as exc:
        self.breaker.trip(widget, exc)
        return canvas, cursor_pos
```

Replace these draw sites with `self._safe_draw(...)` (line numbers vs origin/main
@ 13a2b09; the implementer matches by context):

| site | function |
|------|----------|
| `:421` | `_hold_ticks` |
| `:535`, `:563`, `:578`, `:601` | `_swap_and_scroll` |
| `:750`, `:769` | `_scroll_and_delay` |
| `:831` | `_scroll_one_by_one` |
| `:921`, `:932` | `_scroll_side_by_side` |

`:535` passes `cursor_pos` positionally (`ticker_obj.draw(canvas, pos)`) — normalize
to `self._safe_draw(ticker_obj, canvas, pos)`.

### Play path — guard at the METHOD level (NOT a generic `_safe_play(*args)`)

Researched against the code: the two play call sites differ — `_play_widget`
passes `hold_time=…`, `_run_gif` (`:1044`) does not — and `_play_widget`'s
ScaledCanvas branch does post-play `canvas.rebind_innermost(new_real)` that **must
be skipped on failure**. A generic wrapper around the raw `widget.play()` call
would return the wrong object or still attempt the rebind. play is **per-visit**
(its frame loop is inside the widget), so there is no hot-path/closure concern.
Guard at the per-play-call unit:

- **`_play_widget` (`:443`/`:452`)** — wrap the method body in one try/except
  covering BOTH the scaled and unscaled branches. On a render error: trip the
  widget and `return canvas` (the input wrapper) unchanged, **without** the
  `rebind_innermost`. Already-disabled (checked at method entry) → return `canvas`
  without calling `play()`.
- **`_run_gif` play (`:1044`)** — guard the single `widget.play(...)` there: on a
  render error trip the widget and continue with `real` unchanged (the loop moves
  to the next widget).

**Out of scope:** the transition draws at `:1205`/`:1213` and the
`_HiresCircle.draw` override at `:112`.

**Trip-once semantics + fallback (researched):** a widget that raises every tick
hits the expensive `try/except`+`trip` path on its FIRST draw of the visit; every
later `_safe_draw` in that visit short-circuits on `is_disabled` and returns the
canvas unchanged — no hot-loop spin (perf-verified). The fallback **leaves the
canvas unchanged (no `Clear()` in the breaker)** because every scroll/held tick
already runs `reset_canvas(canvas, bg_color)` BEFORE the draw
(`advance_frame → reset_canvas → draw → swap`, ticker.py ~`:563/578/601`, and
`_swap_and_scroll` entry `:535`). So the sequence is: the trip tick shows a ≤1-tick
(~50 ms) partial frame; the NEXT tick's existing `reset_canvas` wipes it and
`_safe_draw` short-circuits → a clean blank/bg canvas for the rest of the visit;
then the filter (below) removes the widget from the next pass. A breaker-side
`Clear()` would be redundant with the per-tick reset (it could only affect that one
~50 ms frame) and is therefore **not** added.

## Rotation filter (`_expand_sources`)

`_expand_sources(sources, breaker=None)` drops any widget the breaker has disabled
(and skips a disabled story inside an expanded container). Every mode builds its
render list through `_build_ticker_iter` → `_expand_sources`, so one filter makes a
tripped widget vanish from rotation in all modes on the next pass.
`_build_ticker_iter` threads the breaker through.

## Status surfacing (`src/led_ticker/status_board.py`)

- Add `record_disabled_widget(widget, error)` (mirrors `record_widget_visit`,
  reusing `_widget_summary(widget)` for the human name; appends
  `{"widget": <summary>, "error": <error>}` to a board-held list if not already
  present; instrumentation-safe — never raises into the engine).
- Add `disabled_widgets: list[dict[str, str]]` to the `StatusBoard` snapshot,
  alongside `failed_plugins`.
- **Bump `SCHEMA_VERSION` 3 → 4** (the top-level key set changed) and update the
  schema tripwire test that guards the key set.
- Docs: add `disabled_widgets` to the web-status docs
  (`concepts/web-status-ui.mdx`) and (if it documents the snapshot shape)
  `reference/config-options.mdx` / the status-board reference.

## Render-constraint safety

- `_safe_draw` / `_safe_play` always return a **valid canvas**, so `SwapOnVSync`
  capture (#1) and the swap cadence are never skipped — the engine swaps a real
  canvas every tick regardless of a widget raising.
- `advance_frame` (#12) calls that already ran before a raise are harmless (the
  tick is just skipped for that widget).
- The breaker never touches the swap path or `LedFrame`.
- `status_board.record_disabled_widget` follows the existing instrumentation rule:
  it must never raise into the engine.

## Testing

- `tests/test_render_breaker.py`: `RenderBreaker` unit — trip records id + summary,
  logs once (second trip of same widget is a no-op), `is_disabled` reflects it.
- Engine tests (`tests/test_ticker*.py`): a `FaultyDrawWidget` (draw raises) and a
  `FaultyPlayWidget` (play raises) — for EACH mode (swap, forever, infini):
  - the run loop does not propagate the exception;
  - a sibling good widget still renders;
  - the swap is still captured (use the `swapping_frame` fixture; assert ≥2 distinct
    canvases seen — constraint #1);
  - the faulty widget is tripped on the FIRST failure and `is_disabled` after;
  - it's dropped from the next `_expand_sources`/`_build_ticker_iter` pass;
  - `_safe_draw` short-circuits once disabled (the widget's `draw` isn't called again).
- `tests/test_status_board.py`: `record_disabled_widget` appends to the snapshot;
  the schema tripwire updated for `SCHEMA_VERSION == 4` + the new key.
- `_expand_sources` filter unit: a disabled widget (and a disabled container story)
  is removed.

## Non-goals

- Transitions (`run_transition` / `_scroll_between` draws) — deferred (compositor
  code with pause/resume + capture subtleties; rarer surface).
- Per-widget retry / cooldown / auto-re-enable — trip is permanent for the run.
- An on-panel error placeholder — a disabled widget renders nothing.
- Catching non-`Exception` (KeyboardInterrupt/SystemExit/CancelledError propagate).

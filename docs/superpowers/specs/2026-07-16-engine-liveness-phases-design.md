# Engine Canvas-Lifecycle & Liveness — Phased Design (#394, #395, #396, #302)

**Date:** 2026-07-16
**Status:** Approved (brainstorming complete)

## Problem

Four open issues, three of them mechanically overlapping engine-seam problems
surfaced by PR #391's adversarial review loop:

- **#395** — entry transitions call `get_clean_canvas()` → `create_canvas()`
  → C++ `CreateFrameCanvas()` per section change; the C++ pool never frees, so
  busy playlists accumulate native framebuffers for the process lifetime.
- **#396** — the empty-playlist (not-dark) idle never swaps: busy-light
  overlays freeze and the status board's `swap_count` liveness counter stalls,
  reading as a wedged loop.
- **#394** — the ticker's enqueue producer runs unboundedly ahead of the
  display consumer (unbounded `asyncio.Queue`, only a `qsize() > 10`
  cooperative yield; measured ~30k items in 0.5 s). In `loop_count = 0`
  sections all time-based gating (widget `schedule`, `should_display`) is
  decided at enqueue time — window boundaries never reach the panel — plus
  unbounded memory and a spinning producer. PR #391 shipped honest
  enqueue-time docs and validate warnings as a stopgap.
- **#302** — the hot-reload path runs `validate_config` + a second
  `load_config` synchronously on the event loop; big configs hitch the render
  loop during a reload. (Low priority; "maybe" by its own filing.)

## Decisions (settled during brainstorming)

1. **Scope:** all four issues.
2. **Delivery:** one PR per phase; each lands green (and merged, on James's
   per-PR consent) before the next starts. Worktree + branch per phase.
3. **Phasing (Approach A — foundation first):**
   - Phase 1: #395 + #396 as one "canvas & liveness foundation" PR.
   - Phase 2: #394 alone.
   - Phase 3: #302 alone.
   Rationale: Phase 1 lands the allocation/liveness tripwires that then guard
   Phase 2's deep engine change.
4. **Validation depth:** Phase 2 gets the full antagonistic review loop
   (fresh adversarial reviewer per cycle, exit on two consecutive
   zero-finding cycles, hard cap, flag James if not converged) plus a longboi
   hardware smoke. Phases 1 and 3 get standard per-task review plus one
   adversarial pass.
5. **Behavior change (approved):** a zero-section playlist BLANKS the panel
   (with keepalive swaps) instead of freezing the last frame.

## Phase 1 — Canvas & liveness foundation (#395 + #396)

### The `LedFrame` recycling seam

`LedFrame.swap()` is the single choke point every render path goes through,
and its return value is by definition the buffer that just went off-screen.
Changes in `src/led_ticker/frame.py`:

- `swap()` records its return value internally (e.g. `self._last_back`)
  before returning it.
- `get_clean_canvas()` returns `Clear()`-ed `_last_back` when available;
  only when no swap has happened yet (boot) does it fall back to
  `backend.create_canvas()`.

Result: total framebuffer creation is **O(1) per process** across every
path — entry transitions (#395), the dark loop, boot — with zero call-site
changes. The preview tee continues to wrap whatever canvas is returned
(its `_hw` rebinding already handles buffer rotation).

**Simplification rider:** the dark path's bespoke retention
(`_dark_canvas` threading through `_idle_when_all_scheduled_out` and
`run()`, plus the `is None` fetch gate) becomes unnecessary — it reverts to
calling `get_clean_canvas()` per iteration, now allocation-free. The
`dark_streak` debounce stays (it is a flicker guard, not a leak guard).
The existing O(1)-allocation tripwire tests are retargeted at the seam.

**Required audits (plan-level):**
- *Aliasing:* no call site may hold a previous `get_clean_canvas()` result
  while fetching another (the second fetch Clears the first). Enumerate all
  callers of `get_clean_canvas` and verify.
- *Returned-canvas identity:* callers that compare canvas identity in tests
  (swapping_frame-style) must still see distinct front/back objects.
- *Backend conformance:* `backends/conformance.py` gains a case pinning the
  recycling contract (`get_clean_canvas` after a swap returns the
  just-swapped-out buffer, cleared; `create_canvas` not called again).

### #396 — empty playlist blanks, with keepalive

`_idle_on_empty_playlist`'s callers change so that a zero-section playlist:
- logs its existing warning once (unchanged),
- **blanks the panel** and keepalive-cycles (`Clear()` + captured `swap()`)
  once per idle second — reusing the same cycle helper as the dark path
  (`_cycle_dark_canvas` or its renamed generalization),
- keeps busy-light compositing and `swap_count` advancing,
- recovers instantly when a valid config lands (hot-reload checks unchanged).

The `_display_dark` / empty-playlist interaction simplifies: both idles use
the same keepalive; the special-case added for "empty playlist while dark"
in PR #391 folds into the general path.

Visible behavior change (approved): previously the panel froze on the last
frame during a zero-section interlude; now it goes dark. Docs note in the
hot-reload page if one exists, plus the CLAUDE.md invariant below.

### New CLAUDE.md invariant

Add to the hardware-constraints-adjacent invariants: *idle paths must keep
swapping (overlay hooks and the status board's `swap_count` liveness both
depend on every-swap compositing); steady-state paths must never call
`backend.create_canvas` (the C++ pool never frees) — `get_clean_canvas`
recycles the swap-returned buffer, and tripwires pin O(1) allocation.*

### Phase 1 testing

- Conformance-suite case for the recycling contract (all backends).
- Tripwire: `create_canvas` call count O(1) across N entry transitions + N
  dark iterations + N empty-playlist idle iterations.
- Keepalive tests for the empty-playlist idle (swap called per idle
  iteration, blank content, log once).
- Retargeted dark-path tests (retention machinery removed, behavior
  identical).
- Full suite + docs build; both scheduling smoketest configs still validate.

## Phase 2 — Bound the producer/consumer queue (#394)

### Engine change

- The per-section notification queue becomes `asyncio.Queue(maxsize=2)`.
- Delete the producer's `qsize() > 10` `await asyncio.sleep(0)` yield; the
  producer now parks in `await queue.put(...)` — backpressure ties gate
  evaluation (`_expand_sources`: widget `schedule`, `should_display`,
  container re-reads) to display time within ~2 items.

**Edge-case checklist (plan-level, each needs a test):**
- Sentinel delivery when the producer is blocked in `put()` at pass end.
- Section-`finally` cancellation of a producer parked in `put()`
  (CancelledError unwinds cleanly; no orphaned task, no lost queue slot).
- Every `get_nowait` consumer's `QueueEmpty` handling under a 2-deep queue
  (startup and steady state).
- Side-by-side (`ticker` mode) buffer fill: the display buffer fills from a
  2-deep queue without stutter; the producer must never become the
  frame-rate limiter (it is pure expansion — pin with a pacing test).
- Reload/restart checks still land at their documented latencies.
- Memory: queue depth bounded (regression test using the run()-spy pattern);
  producer no longer spins (no busy-loop when the consumer is slow).

### Restoring the truth (docs + validate)

With gating now display-time:
- `scheduling.mdx` and the CLAUDE.md visibility-scheduling bullet revert
  the cycle-5 enqueue-time wording to per-pass semantics (bounded by ~2
  queued items plus the currently-displaying widget).
- The **widget-level** forever-section validate warning (added as the
  cycle-5 stopgap) is removed — it becomes false.
- The **section-level** forever-section warnings stay: the strong variant
  (widget windows jointly cover 24/7 → the rotation never empties →
  `cycle_with_refresh` never exits → section schedule never re-checked)
  remains true under a bounded queue; the softened variant becomes accurate
  as written.
- The container-freshness claim ("live updates surface within at most one
  cycle") becomes true again for forever sections — restore any wording
  that was hedged.
- Issue #394's "restore per-pass wording" note is satisfied; close the issue
  with a comment linking the PR.

### Phase 2 validation

- Full antagonistic review loop (per the saved protocol: fresh reviewer per
  cycle, mechanism-first, two consecutive clean cycles to exit, hard cap 5,
  flag James if not converged).
- Longboi hardware smoke: both existing scheduling smoketest configs, plus a
  new forever-section (`loop_count = 0`) scenario in the smoketest watching a
  widget-window boundary flip on the panel near wall-clock time.

## Phase 3 — Reload validate off the event loop (#302)

As the issue prescribes:
- Extract `validate_config`'s synchronous core in `validate.py`; the async
  wrapper `await asyncio.to_thread(...)`s it.
- Reload path (`reload.load_and_validate`) uses the offloaded form; also
  offload the duplicate `load_config` in `reload.py`.
- Boot and webui `/api/validate` callers stay correct (plugin loading is
  idempotent per the issue's de-risk note — verify with a test).
- The apply path (`_apply_reload`, engine mutation) stays on the loop.
- Tests: `tests/test_reload.py` + `tests/test_run_reload_helpers.py` green;
  a new test pinning that reload validate runs off-loop (e.g. asserting the
  thread via the extracted core, or that the event loop isn't blocked —
  whichever the plan finds testable without flakiness).

## Process (all phases)

Per phase: fresh worktree + branch from origin/main → SDD build
(brief/report files, per-task review) → adversarial pass (Phase 2: full
loop) → draft PR in James's style → CI watch → James's explicit merge →
next phase. `uv run pyright` on touched files before every push. Issues
closed with PR links as each phase merges (#395+#396 by Phase 1, #394 by
Phase 2, #302 by Phase 3).

## Out of scope

- Reworking the C++ backend's `created_frames_` retention (upstream
  behavior; we design around it).
- Any scheduling-feature surface changes beyond the Phase-2 docs/validate
  restoration.
- Status-board UI concept of "dark" (noted in review as cosmetic).

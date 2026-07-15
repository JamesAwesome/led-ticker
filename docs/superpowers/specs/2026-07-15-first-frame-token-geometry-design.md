# First-frame token geometry — design spec

**Date:** 2026-07-15
**Status:** approved (brainstorm; Fable architectural review) — pending user review before planning
**Repo:** `led-ticker` core, worktree `led-ticker--first-frame-tokens`, branch `fix/first-frame-token-geometry`

---

## 1. Summary

A scrolling text message containing an inline value token backed by a **polled** data
source (stock price `:stocks.aapl:`, weather, etc.) renders wrong on its FIRST display:
it "only scrolls to the first letter," then self-corrects on the next cycle. Fix it with
two complementary changes:

1. **Engine — the "measure-at-lock" invariant** (`ticker.py:_swap_and_scroll`): the scroll
   geometry consumed by a locked scroll must be measured at the instant of locking, never
   across an `await`. Today the generic-overflow branch measures `cursor_pos` up front,
   `await`s a multi-second pre-scroll hold during which the token is *allowed* to re-resolve,
   then computes `stop_pos` from the stale pre-hold `cursor_pos`. This is a stale-snapshot
   bug; the corrected fetch value is already being computed by `_hold_ticks` and discarded.
2. **Startup — bounded boot prime** (`sources.py` + `app/run.py`): before the display loop,
   await each polled source's first real value with a short bounded timeout, so ALL widgets
   (not just scrolling messages) see real data on their first display.

## 2. Root cause (verified against the code)

Two deliberate mechanisms collide:

- **Polled sources fetch their first value in a concurrently-spawned task that never blocks
  startup or the render loop.** `sources.py` `spawn_source_refresh()` does
  `spawn_tracked(run_monitor_loop(source, source.interval, immediate=True))` per
  `PolledDataSource`; the comment states the fetch "runs concurrently — it never blocks
  startup or the render loop." So the display loop can reach a widget's first draw before
  the first fetch lands; the token resolves to its placeholder (`…`).
- **The generic overflow branch of `_swap_and_scroll` snapshots geometry across the hold.**
  `_resolve_now_if_supported` + `_safe_draw` measure `cursor_pos` at entry (`ticker.py:563-565`).
  The overflow decision `if cursor_pos > canvas.width:` (`ticker.py:647`) and the pre-scroll
  hold `canvas, _ = await self._hold_ticks(...)` (`ticker.py:650`, **return value discarded**)
  run, then resolution is locked (`ticker.py:660`, constraints #6/#7) and
  `stop_pos = -(cursor_pos - canvas.width) + padding` (`ticker.py:662`) is computed from the
  pre-hold `cursor_pos`. During the hold the widget re-resolves and re-measures its own
  `_content_width` every tick (`message.py:_resolve_into_full_text` → `_content_width = -1`
  on change) — the panel already shows the real value at its real width — but the engine's
  `cursor_pos`/`stop_pos` locals are stale, so the scroll runs to the placeholder-width stop.

`_hold_ticks` returns `(canvas, cursor_pos)` where `cursor_pos` is the LAST tick's fresh
`_safe_draw` measurement (`ticker.py:_hold_ticks`). The correct value already exists; the
overflow branch throws it away.

The `forces_offscreen_scroll` (`ticker.py:572`) and `wraps_forever` (`ticker.py:615`)
branches already resolve-then-lock with **no hold in between**, so they honor measure-at-lock
today. Only the generic overflow branch (`ticker.py:647`) and its fits-else (`ticker.py:682`)
are affected.

## 3. Non-goals (explicitly out of scope)

- **No new "data readiness" engine concept.** `frames_to_transition_ready` is frame-bounded,
  widget-scoped, single-seam (hold→transition), and does not generalize to unbounded,
  source-scoped network readiness; bending it would rot a clean contract. The existing
  `should_display()` seam already expresses "hide me until data" in a few opt-in lines if a
  user ever asks — but default-hiding token widgets would blank the panel, which is worse
  than a placeholder. We keep the codebase philosophy: **degrade visibly, never block or hide.**
- **No mid-scroll re-measure / lazy geometry during the scroll.** Constraints #6/#7 are
  correct: moving `stop_pos` mid-scroll strands the scroll or clips the tail, and width
  jitter makes centered/held text jump. The fix is measure-*at*-lock, not measure-*per-tick*.
- **No change to the concurrent poll loops themselves** — the ongoing `run_monitor_loop`
  cadence, backoff, and never-block-render contract are unchanged.

## 4. Change 1 — measure-at-lock in `_swap_and_scroll`

**File:** `src/led_ticker/ticker.py`, the region from the generic-overflow decision
(`~L647`) through the fits-else hold (`~L686`). The offscreen/wraps branches above are
untouched.

**Restructure to "hold first, then decide from the post-hold measure":**

- Run the initial hold BEFORE deciding overflow-vs-fits (non-`continuous` only; `continuous`
  keeps its no-hold path). Capture the returned `cursor_pos` — call it `held_cursor`.
- Decide from `held_cursor`: if `held_cursor > canvas.width`, lock resolution and compute
  `stop_pos = -(held_cursor - canvas.width) + padding` **inside** the measure→lock pairing,
  then scroll, then run the trailing hold. Otherwise the initial hold already displayed the
  fits-case; proceed.
- `continuous` mode (scroll transition) has no hold, so its entry measure is already fresh —
  its path is preserved unchanged.

This fixes BOTH directions with one invariant:
- placeholder overflows → real value present after the hold → `stop_pos` from the real width
  (the reported symptom);
- placeholder fits but real value overflows → post-hold measure overflows → it now scrolls
  (today it holds clipped and never scrolls — the "uglier sibling" case).

**Invariant to encode in a comment** (so the next editor preserves it): *the geometry a
locked scroll consumes is measured at the instant of locking, with zero awaits between the
measure and the lock.*

**Preserved:** constraint #1 (swap capture) and #12 (advance-frame per tick) are inherited
via `_hold_ticks` and the existing scroll loop; the settle-to-rest pass (`~L688-700`) is
unchanged; a breaker-tripped widget (whose draw yields the passed-in `pos`, not an overflow
width) must not be pushed into a scroll — guard on the post-hold measure exactly as the
pre-hold decision did.

**Observable behavior change (changelog line):** a routine value change *during* the hold
(not just the boot placeholder) now updates the scroll distance. This is correct — the panel
already shows the new text during the hold — but it is observable.

## 5. Change 2 — bounded boot prime

**Files:** `src/led_ticker/sources.py`, `src/led_ticker/app/run.py`.

- `PolledDataSource` exposes a `first_value: asyncio.Event`, set when it first applies a real
  value (the `version` goes `0 → 1` via `_set_value`). Sync sources (clock/date/static) are
  unaffected — they are already correct at build time and are not primed.
- Startup awaits all polled sources' `first_value` events with a bounded timeout
  (`PRIME_TIMEOUT ≈ 2.5s`) AFTER `spawn_source_refresh` spawns the loops (no second fetch —
  we wait on the event the `immediate=True` fetch already drives) and BEFORE the display loop
  starts. Log any source that misses the deadline (mirrors the status-board "waiting"
  vocabulary). A slow/down API degrades to exactly today's behavior after the timeout and
  never wedges boot.
- This is where first-frame correctness already lives in this codebase: `run.py` builds the
  source registry before widgets "so TokenizedField instances can resolve against an
  already-populated registry"; `_start_busy_light` does `await busy.update()  # correct on
  frame 1`; data widgets eager-fetch in `start()` before spawning their loop. Polled sources
  are the one first-frame-visible data path missing this treatment.
- **Hot-reload:** `_apply_reload` rebuilds the registry with fresh sources, so a reload that
  adds a token has the same race. A short (or zero) prime timeout there is acceptable —
  Change 1 covers the scroll symptom regardless, which is why the two changes are
  complementary rather than alternatives.

## 6. Testing

- **Change 1 tripwires** (engine, headless — the load-bearing regression):
  - First draw yields a short placeholder width; the source bumps mid-hold to a wide value;
    assert the scroll runs to the resolved-width `stop_pos` (not the placeholder-width one).
  - Inverse: placeholder fits, value overflows during the hold → assert it scrolls.
  - No-regression: a static (non-token) overflowing message still scrolls to the same
    `stop_pos` as before; a fits-case static message still just holds; `continuous` mode
    unchanged; breaker-tripped widget is not pushed into a scroll.
- **Change 2 tripwires:** a polled source sets `first_value` on its first real value; the
  prime awaits and returns once all set; the prime returns after the timeout when a source
  never sets it (bounded, no hang); sync sources are not awaited.
- **Visual GIF validation gate (required before merge):** render a scrolling message with a
  demo-backed stocks token from a cold boot and confirm the FIRST pass scrolls the full
  resolved text (no first-letter truncation). Per `docs/visual-validation.md` — this is a
  render-path change, the class the GIF gate exists for.

## 7. Risks

- Change 1 is in the most constraint-laden function in the repo. Mitigations: it touches only
  the generic overflow/fits region (offscreen/wraps/continuous paths untouched); it reuses
  `_hold_ticks` (inheriting constraints #1/#12) rather than adding a new draw site; the
  measure-at-lock invariant is encoded in a comment and guarded by the tripwires above; the
  GIF gate is mandatory.
- Change 2 risk is bounded startup latency (worst case: full `PRIME_TIMEOUT` on a boot with a
  down API) and the asyncio requirement to await tasks/events, not bare coroutines. Both are
  small and bounded.

## 8. Phasing (for the plan)

1. **Change 1** — engine measure-at-lock restructure + engine tripwires (headless). Ships the
   durable fix on its own; the GIF gate validates it.
2. **Change 2** — `PolledDataSource.first_value` + bounded startup prime + prime tripwires.
   Complements Change 1 for non-scrolling widgets.

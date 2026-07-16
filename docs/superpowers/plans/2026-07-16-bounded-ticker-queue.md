# Bounded Ticker Queue (Phase 2: #394) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The ticker's enqueue producer is backpressured by a `maxsize=2` queue so gate evaluation (widget `schedule`, `should_display`, container re-reads) tracks display time — closing #394's enqueue-time gating, unbounded memory, and producer spin — and the docs/validate wording that PR #391 walked back is restored to per-pass semantics.

**Architecture:** `asyncio.Queue(maxsize=2)` at the queue's single construction site; the producer's `qsize() > 10` cooperative-yield hack deletes (a blocking `put()` yields inherently). The consumers already handle the `None` sentinel and `QueueEmpty`; the section-teardown cancellation already awaits the producer task, and a producer parked in `put()` unwinds via CancelledError. The behavioral headline gets a display-time-gating test that fails against the unbounded queue.

**Tech Stack:** Python 3.14, asyncio, attrs, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-16-engine-liveness-phases-design.md` (Phase 2). Issue: #394.

## Global Constraints

- Work in `/Users/james/projects/github/jamesawesome/led-ticker-bounded-queue` on branch `bounded-ticker-queue`. Verify `pwd` and `git branch --show-current` before git operations.
- Commands via `uv run ...`; `make test` full suite; `make lint` ruff; pyright 0 new errors on touched files before push (pre-existing baselines verified per-file against main when needed).
- No `from __future__ import annotations`. Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- QUEUE_MAXSIZE is exactly **2** and appears as a named module constant, not a bare literal.
- This is the display loop: swap-then-sleep ordering and sentinel semantics must not change; the only behavior change is WHEN gate evaluation happens (display time, bounded by ~2 queued items + the currently-showing widget).
- Validation depth (spec): after tasks complete, the branch gets the FULL antagonistic review loop (fresh reviewer per cycle, two consecutive zero-finding cycles to exit, hard cap 5, flag James if not converged) — controller-run, plus James's longboi hardware smoke before merge.

---

### Task 1: Bound the queue + producer behavior tests

**Files:**
- Modify: `src/led_ticker/ticker.py` (module constant near the top constants; `_enqueue_ticker_objects` — the `qsize() > 10` block)
- Modify: `src/led_ticker/app/run.py:1127` (queue construction)
- Test: `tests/test_ticker_queue_bounding.py` (new)

**Interfaces:**
- Produces: `TICKER_QUEUE_MAXSIZE = 2` (module constant in `ticker.py`, imported by `run.py` for the construction site). `_enqueue_ticker_objects` unchanged in signature; its `qsize() > 10` yield block DELETED (docstring updated: backpressure via bounded `put()` replaces the cooperative yield; the sentinel contract is unchanged).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ticker_queue_bounding.py`:

```python
"""Producer backpressure (#394): the notif queue is bounded so gate
evaluation in _build_ticker_iter's per-pass expansion tracks DISPLAY time
instead of running unboundedly ahead at enqueue time."""

import asyncio
import itertools

import pytest

from led_ticker.ticker import (
    TICKER_QUEUE_MAXSIZE,
    _enqueue_ticker_objects,
)


def test_maxsize_constant():
    assert TICKER_QUEUE_MAXSIZE == 2


def test_run_loop_constructs_bounded_queue():
    """Source tripwire (house AST-tripwire style): the run loop's queue
    construction must pass maxsize=TICKER_QUEUE_MAXSIZE — the behavior
    tests below build their own queues, so this is the pin that the REAL
    wiring is bounded. A bare `asyncio.Queue()` reintroduces #394."""
    import inspect

    from led_ticker.app import run as run_mod

    src = inspect.getsource(run_mod)
    assert "maxsize=TICKER_QUEUE_MAXSIZE" in src
    assert "notif_queue: asyncio.Queue[Any] = asyncio.Queue()" not in src


async def _drain_n(queue, n, per_item_delay=0.01):
    got = []
    for _ in range(n):
        item = await queue.get()
        got.append(item)
        await asyncio.sleep(per_item_delay)
    return got


@pytest.mark.asyncio
async def test_queue_depth_never_exceeds_maxsize():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(
        _enqueue_ticker_objects(itertools.count(), queue)  # infinite iterator
    )
    try:
        max_seen = 0
        for _ in range(20):
            await asyncio.sleep(0.005)
            max_seen = max(max_seen, queue.qsize())
            if not queue.empty():
                queue.get_nowait()
        assert max_seen <= TICKER_QUEUE_MAXSIZE
    finally:
        producer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await producer


@pytest.mark.asyncio
async def test_sentinel_arrives_last_on_finite_iterator():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(iter([1, 2, 3, 4, 5]), queue))
    got = await _drain_n(queue, 6)
    await producer
    assert got == [1, 2, 3, 4, 5, None]


@pytest.mark.asyncio
async def test_cancel_while_parked_in_put_unwinds_cleanly():
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(itertools.count(), queue))
    await asyncio.sleep(0.01)  # producer fills the queue and parks in put()
    assert queue.full()
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(producer, timeout=1.0)  # no hang


@pytest.mark.asyncio
async def test_gating_tracks_display_time():
    """The #394 headline: a visibility flip mid-'section' reaches the
    consumer within maxsize+1 items, instead of being buried behind an
    unbounded backlog of pre-gated items."""

    class _FlippingWidget:
        def __init__(self):
            self.visible = True

        def should_display(self):
            return self.visible

    w = _FlippingWidget()

    def passes():
        # Mimics _build_ticker_iter's cycle_with_refresh: re-evaluate the
        # gate every pass, stop yielding when it goes false.
        from led_ticker.ticker import _expand_sources

        while True:
            widgets = _expand_sources([w])
            if not widgets:
                return
            yield from widgets

    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(passes(), queue))
    # Consume 3 items, then flip the widget invisible.
    await _drain_n(queue, 3)
    w.visible = False
    # The sentinel must arrive within maxsize+1 further gets: the items
    # already buffered (<= maxsize) were gated before the flip; everything
    # after re-evaluates and exhausts.
    tail = await asyncio.wait_for(
        _drain_n(queue, TICKER_QUEUE_MAXSIZE + 1), timeout=2.0
    )
    await producer
    assert None in tail
```

Note on the harness: check how existing async tests in this repo are marked (`grep -rn "pytest.mark.asyncio\|anyio" tests/test_container_refresh.py tests/test_ticker_display.py | head`) and match — if the repo uses a different async plugin/fixture convention, adapt the decorators, not the test bodies.

- [ ] **Step 2: Run tests to verify the meaningful failures**

Run: `uv run pytest tests/test_ticker_queue_bounding.py -v`
Expected: `test_maxsize_constant` FAILS (ImportError — constant doesn't exist). After adding just the constant (not the queue changes), `test_queue_depth_never_exceeds_maxsize` and `test_gating_tracks_display_time` FAIL against the current producer if pointed at an UNBOUNDED queue — but note these tests construct their own bounded queue, so they exercise the producer against bounding directly; the repo-level wiring is pinned in Step 3's run.py change plus Task 2's consumer tests. Record which tests failed and why in the report.

- [ ] **Step 3: Implement**

(a) `src/led_ticker/ticker.py` — near the module's other constants (grep `ENGINE_TICK_MS` for the neighborhood):

```python
# Producer/consumer backpressure (#394). The enqueue producer used to run
# unboundedly ahead of the display consumer (~30k items in 0.5s measured),
# which made every gate decision (_expand_sources: widget `schedule`,
# should_display, container re-reads) an ENQUEUE-time decision — a widget
# whose window closed hours ago kept displaying because the consumer sat
# behind a backlog of pre-gated items. maxsize=2 keeps evaluation within
# ~2 queued items + the currently-showing widget of display time, caps the
# queue's memory, and stops the producer from spinning a core.
TICKER_QUEUE_MAXSIZE = 2
```

(b) `_enqueue_ticker_objects` — delete the yield block:

```python
    while True:
        try:
            await notif_queue.put(next(ticker_iter))
        except StopIteration:
            await notif_queue.put(None)
            break
```

and update its docstring: remove the starvation note about unbounded queues; add "The queue is bounded (TICKER_QUEUE_MAXSIZE); `put()` blocks when full, which both paces this producer to display speed and yields the event loop — the old `qsize() > 10` cooperative-yield hack is gone."

(c) `src/led_ticker/app/run.py:1127`:

```python
                        notif_queue: asyncio.Queue[Any] = asyncio.Queue(
                            maxsize=TICKER_QUEUE_MAXSIZE
                        )
```

with `TICKER_QUEUE_MAXSIZE` added to run.py's existing `from led_ticker.ticker import ...` block (grep for it; if run.py imports the module instead, use the module path — match the file's convention).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_ticker_queue_bounding.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Blast radius**

Run: `uv run pytest tests/test_ticker_display.py tests/test_container_refresh.py tests/test_run_section_schedule.py tests/test_run_reload_helpers.py tests/test_app.py -q`
Expected: ALL PASS. A hang here (pytest timeout / no output) means a consumer or teardown path deadlocked against the bounded queue — STOP, capture which test hangs, report NEEDS_CONTEXT. Do not add timeouts to make it pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py src/led_ticker/app/run.py tests/test_ticker_queue_bounding.py
git commit -m "feat(ticker): bound the notif queue (maxsize=2) — gate evaluation tracks display time (#394)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Consumer behavior under the bounded queue

**Files:**
- Test: `tests/test_ticker_queue_bounding.py` (append)

**Interfaces:**
- Consumes: `TICKER_QUEUE_MAXSIZE`, the bounded wiring from Task 1. No production code changes expected — this task PINS that the three consumers' patterns hold under bounding; if any test exposes a real defect, report it (don't patch consumers without flagging).

- [ ] **Step 1: Write the tests**

Append:

```python
@pytest.mark.asyncio
async def test_run_swap_drain_loop_terminates_with_parked_producer():
    """_run_swap's catch-up drain (`while not queue.empty(): get_nowait()`)
    is synchronous — a producer parked in put() CANNOT refill mid-drain
    (its waiter only resolves at the next event-loop yield), so the drain
    terminates. Pin that event-loop fact directly."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(itertools.count(), queue))
    await asyncio.sleep(0.01)  # queue full, producer parked
    drained = []
    while not queue.empty():
        drained.append(queue.get_nowait())
    # Terminated with exactly the buffered items — the parked producer
    # could not sneak refills in synchronously.
    assert len(drained) == TICKER_QUEUE_MAXSIZE
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await producer


@pytest.mark.asyncio
async def test_consumer_never_starves_when_producer_is_fast():
    """With a fast producer, every consumer get() should find an item
    already buffered (the producer keeps the 2-slot queue topped up) —
    the producer must not become the frame-rate limiter."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=TICKER_QUEUE_MAXSIZE)
    producer = asyncio.create_task(_enqueue_ticker_objects(itertools.count(), queue))
    await asyncio.sleep(0.01)
    empty_at_get = 0
    for _ in range(50):
        if queue.empty():
            empty_at_get += 1
        await queue.get()
        await asyncio.sleep(0.001)  # consumer tick
    assert empty_at_get == 0
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await producer
```

Then the integration-level pins, using the existing Ticker-mode test harnesses: find the tests that drive `run_slideshow` / `_scroll_one_by_one` / `_scroll_side_by_side` end-to-end (grep `notif_queue` in `tests/test_ticker_display.py` and `tests/test_app.py`) and confirm they construct their queues via... read how they build them. If any test constructs an UNBOUNDED queue and feeds it manually, that's fine (consumer-side tests). Add ONE integration test that drives `Ticker.run_slideshow` with the real `_build_then_enqueue` over a 3-widget section and a bounded queue, asserting all three widgets display and the mode returns cleanly on the sentinel — mirror the closest existing `run_slideshow` test's fixture setup (mock frame etc.) rather than inventing a new harness; name it `test_run_slideshow_completes_over_bounded_queue`.

- [ ] **Step 2: Run**

Run: `uv run pytest tests/test_ticker_queue_bounding.py -v`
Expected: ALL PASS (these pin existing-correct behavior). A failure = real consumer defect under bounding: STOP and report NEEDS_CONTEXT with the failure.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ticker_queue_bounding.py
git commit -m "test(ticker): pin consumer behavior under the bounded queue

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Validate restoration — retire the enqueue-time warnings

**Files:**
- Modify: `src/led_ticker/validate.py` (the forever-section check family — grep `_check_forever_section_schedule` / `_forever_never_rechecks_issue` / "queued")
- Test: `tests/test_validate_visibility_schedule.py`

**Interfaces:**
- Consumes: display-time gating from Task 1 (the factual basis for the wording).
- Produces: the validate warning matrix for `loop_count = 0` sections becomes:
  - **REMOVED:** the widget-level warning (loop_count=0 + widget-schedules-only, "evaluated when content is queued") — false under bounding.
  - **KEPT (reworded):** section-level schedule + widget windows jointly covering 24/7 → STRONG warning: the rotation never empties, so `cycle_with_refresh` never exits and the section-level schedule is never re-checked after entry. (Still true — bounding doesn't change it.) Keep the "blank-interval sweep assumes the section closes" clause.
  - **KEPT (simplified):** section-level schedule + gapped widget windows → softened warning, now WITHOUT the "already-queued content drains" temper — re-check happens when all widget windows close, and delivery is within ~2 queued items (say exactly that).
  - Title-only skip and `loop_count >= 1` exemptions unchanged.

- [ ] **Step 1: Update the tests first**

In `tests/test_validate_visibility_schedule.py`:
- DELETE the widget-level forever-warning tests (grep "queued" / the fixture for loop_count=0 + widget-schedules-only) and REPLACE with an explicit negative: that config now produces NO warning (bounded queue makes it correct) — keep the fixture, invert the assertion, with a comment citing #394.
- Update the softened-message substring assertions to the new wording (no "already-queued content drains" temper; presence of the "~2 queued items" bound phrasing — pin a distinctive substring, e.g. `"within a couple of queued items"`).
- Strong-warning tests: keep; update substrings only if the rewording touches them.

Run: `uv run pytest tests/test_validate_visibility_schedule.py -v` — expected: the edited tests FAIL against current validate.py (warning still fires / old wording).

- [ ] **Step 2: Implement**

In `validate.py`: delete the widget-level warning branch (and its helper text); reword the softened message per the Produces block; keep strong + title-only + loop_count>=1 logic untouched. Keep `_widget_windows_have_gap` (still drives strong vs softened).

Run the file's tests — ALL PASS.

- [ ] **Step 3: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate_visibility_schedule.py
git commit -m "fix(validate): retire enqueue-time forever-section warnings — gating is display-time now (#394)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Docs restoration + smoketest forever-section scenario

**Files:**
- Modify: `docs/site/src/content/docs/concepts/scheduling.mdx` (the forever-section behavior note — grep "queued"/"loop_count")
- Modify: `CLAUDE.md` (Visibility-scheduling bullet's enqueue-time caveat; the container bullet if it was hedged — grep "queued" and "run-ahead")
- Modify: `config/config.scheduling_smoketest.longboi.toml` + `config/config.scheduling_smoketest.bigsign.toml` (append the forever-section scenario as a commented block)

**Interfaces:** prose + config comments only. Every claim must be true of the post-Task-1 engine.

- [ ] **Step 1: Restore the docs**

- `scheduling.mdx`: replace the enqueue-time paragraph with per-pass semantics: in a `loop_count = 0` section, widget schedules and `should_display` are re-evaluated every pass and reach the panel within a couple of queued items plus the currently-showing widget; a SECTION-level schedule on a forever section is still only checked at entry (validate warns). Grep "queued" to catch every clause.
- `CLAUDE.md`: remove the enqueue-time caveat from the Visibility-scheduling bullet (restore per-pass wording with the ~2-item bound); check the Container bullet's "within at most one cycle" claim is unhedged (it's true again).
- Consistency grep across the repo: `grep -rn "enqueue-time\|run-ahead\|content is queued" CLAUDE.md docs/site/src/content/ config/*.toml src/` — every remaining hit must be either deleted, reworded, or justified in your report (validate.py hits should be gone after Task 3).

- [ ] **Step 2: Smoketest scenario (spec requirement)**

Append to BOTH smoketest configs a commented block:

```toml
# --- FOREVER-SECTION boundary check (#394, manual) ---
# Uncomment this section (and comment out sections 1-4 above) to verify
# display-time gating in a loop_count = 0 section on hardware: the AM/PM
# pair below never leaves this section (loop_count = 0 cycles forever), so
# the ONLY thing that can flip the panel at noon/midnight is the per-pass
# widget gate. THE CHECK: at a 12:00 boundary the displayed widget must
# flip within a few seconds (one widget hold + ~2 queued items) — if it
# keeps showing the pre-boundary widget for minutes, producer run-ahead
# has regressed.
#
# [[playlist.section]]
# mode = "slideshow"
# content_height = 16
# hold_time = 5
# loop_count = 0
#
# [[playlist.section.widget]]
# type = "message"
# text = "FOREVER AM 00:00-12:00"
# font = "Inter-Regular"
# font_size = 24
# font_threshold = 80
# font_color = [0, 255, 0]
# schedule = { start = "00:00", end = "12:00" }
#
# [[playlist.section.widget]]
# type = "message"
# text = "FOREVER PM 12:00-00:00"
# font = "Inter-Regular"
# font_size = 24
# font_threshold = 80
# font_color = [255, 120, 0]
# schedule = { start = "12:00", end = "00:00" }
```

Verify both configs still validate clean (`uv run led-ticker validate <each>` — commented blocks are inert).

- [ ] **Step 3: Docs build + commit**

`source ~/.nvm/nvm.sh && nvm use && make docs-build && make docs-lint` — green. Then:

```bash
git add docs/ CLAUDE.md config/
git commit -m "docs: restore per-pass gating semantics; forever-section smoketest scenario (#394)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Full gate

- [ ] **Step 1:**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-bounded-queue
make test          # full suite green — watch for hangs (a deadlock shows as a stall, not a failure)
make lint
git diff --name-only main...HEAD | grep '\.py$' | tr '\n' ' ' | xargs uv run pyright
source ~/.nvm/nvm.sh && nvm use && make docs-build && make docs-lint
uv run led-ticker validate config/config.scheduling_smoketest.longboi.toml
uv run led-ticker validate config/config.scheduling_smoketest.bigsign.toml
```

Expected: all green, 0 new pyright errors, both smoketests "No issues found".

- [ ] **Step 2: Commit anything the gate surfaced** (or nothing) and report.

---

### Task 6: Antagonistic review loop + hardware handoff + draft PR (controller-run)

Per the spec's Phase-2 validation depth — this is controller work, not an implementer dispatch:

- [ ] **Step 1:** Run the FULL antagonistic loop (per the saved protocol): fresh adversarial correctness reviewer per cycle (mechanism-first, no padding), fix wave per cycle, exit on two consecutive zero-in-scope-finding cycles, hard cap 5 cycles, flag James if not converged. Cycle-1 attack surfaces to seed: producer park/cancel interleavings with section teardown and hot-reload; sentinel-under-full ordering; the `_run_swap` drain-loop event-loop reasoning; side-by-side buffering fill; slow-widget-expansion pacing (can the producer ever limit frame rate now); memory bound claims; the validate matrix truth table against `cycle_with_refresh` under bounding; docs-claim accuracy.
- [ ] **Step 2:** Draft PR via open-pr: title `feat(ticker): bound the producer queue — display-time gating (#394)` shape; body calls out the semantics change (gate decisions now display-time, ~2-item bound), the restored docs/validate wording, and the REQUIRED pre-merge hardware check (the new forever-section smoketest scenario on the longboi at a window boundary). `Closes #394`. Watch CI. No merge without James.

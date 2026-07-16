# Canvas & Liveness Foundation (Phase 1: #395 + #396) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Framebuffer allocation becomes O(1) per process across every render path (`LedFrame` recycles the swap-returned buffer), and every idle path keeps swapping (empty playlist now blanks with keepalive instead of freezing).

**Architecture:** `LedFrame.swap()` is the single choke point and always knows which buffer just went off-screen; it records that buffer and `get_clean_canvas()` recycles it instead of calling `backend.create_canvas()` (whose C++ `CreateFrameCanvas()` retains every allocation until process exit). The dark path's bespoke retention threading then deletes; the cross-scale transition re-wrap reuses the current back buffer; the empty-playlist idle adopts the same blank-keepalive as the dark path.

**Tech Stack:** Python 3.14, attrs, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-16-engine-liveness-phases-design.md` (approved; this plan is Phase 1).

## Global Constraints

- Work in the worktree `/Users/james/projects/github/jamesawesome/led-ticker-canvas-liveness` on branch `canvas-liveness-foundation`. Verify `pwd` and `git branch --show-current` before any git operation.
- All commands via `uv run ...`; `make test` = full suite; `make lint` = ruff.
- No `from __future__ import annotations` (project rule, PEP 649). PEP 758 bare `except A, B:` syntax is allowed (Python 3.14 target).
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- `uv run pyright` must pass (0 errors) on every touched file before push.
- Hardware constraint #1 everywhere: every `frame.swap(canvas)` / `led_frame.swap(canvas)` return value must be captured.
- Approved behavior change (spec): a zero-section playlist BLANKS the panel (keepalive swaps) instead of freezing the last frame.
- Do not change `LedFrame.create_canvas()` (the raw method) — the preview-tee setup (`run.py:756`) legitimately allocates once at boot.

---

### Task 1: `LedFrame` recycling seam

**Files:**
- Modify: `src/led_ticker/frame.py` (get_clean_canvas lines 58-69, swap lines 71-85, new field)
- Test: `tests/test_frame.py` (append)

**Interfaces:**
- Produces: `LedFrame` gains private `_last_back` (attrs `init=False, default=None`). `swap()` records its return value in `_last_back` before returning. `get_clean_canvas()` returns `Clear()`-ed `_last_back` when set; only calls `backend.create_canvas()` when `_last_back is None` (i.e. before the first swap). Public signatures unchanged — later tasks rely on: after ANY `frame.swap(...)`, the next `frame.get_clean_canvas()` allocates nothing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_frame.py` (match its existing stub/fixture style — read the file's head first; if it builds `LedFrame` around a fake backend, reuse that helper):

```python
class _CountingBackend:
    """Minimal Backend double that counts create_canvas calls and models
    double-buffering (swap returns the previous back buffer)."""

    def __init__(self):
        self.create_calls = 0
        self._back = None
        self.brightness = 100

    def setup(self):
        pass

    def create_canvas(self):
        self.create_calls += 1
        return Mock(name=f"canvas{self.create_calls}")

    def swap(self, canvas):
        old_back = self._back if self._back is not None else Mock(name="back0")
        self._back = canvas
        return old_back


def _frame():
    from led_ticker.frame import LedFrame

    backend = _CountingBackend()
    frame = LedFrame(backend=backend)
    frame.setup()
    return frame, backend


class TestGetCleanCanvasRecycling:
    def test_first_fetch_allocates(self):
        frame, backend = _frame()
        c = frame.get_clean_canvas()
        assert backend.create_calls == 1
        c.Clear.assert_called_once()

    def test_fetch_after_swap_recycles_the_returned_buffer(self):
        frame, backend = _frame()
        c1 = frame.get_clean_canvas()
        back = frame.swap(c1)  # constraint #1: capture
        c2 = frame.get_clean_canvas()
        assert c2 is back  # the just-swapped-out buffer, recycled
        assert backend.create_calls == 1  # no new allocation
        back.Clear.assert_called()  # recycled buffer is cleared

    def test_steady_state_allocation_is_constant(self):
        frame, backend = _frame()
        c = frame.get_clean_canvas()
        for _ in range(50):
            c = frame.swap(c)
            c = frame.get_clean_canvas()
        assert backend.create_calls == 1

    def test_double_fetch_before_any_swap_allocates_twice(self):
        # Documented bound: with no swap yet there is nothing to recycle.
        frame, backend = _frame()
        frame.get_clean_canvas()
        frame.get_clean_canvas()
        assert backend.create_calls == 2

    def test_tee_path_recycles_hw_buffer(self):
        frame, backend = _frame()
        tee = Mock()
        tee.mirror = False
        frame.install_preview(tee)
        c1 = frame.get_clean_canvas()
        assert c1 is tee
        hw1 = tee._hw
        result = frame.swap(tee)
        assert result is tee
        c2 = frame.get_clean_canvas()
        assert c2 is tee
        assert tee._hw is not hw1  # rebound to the swap-returned buffer
        assert backend.create_calls == 1
```

Add `from unittest.mock import Mock` to the file's imports if absent.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_frame.py -k Recycling -v`
Expected: `test_fetch_after_swap_recycles_the_returned_buffer`, `test_steady_state_allocation_is_constant`, `test_tee_path_recycles_hw_buffer` FAIL (create_calls grows per fetch); first-fetch and double-fetch tests may already pass.

- [ ] **Step 3: Implement**

In `src/led_ticker/frame.py`, add the field after `_ready` (line 22):

```python
    # The buffer the most recent swap() returned — by definition off-screen.
    # get_clean_canvas() recycles it instead of allocating: on the real
    # backend every backend.create_canvas() is a C++ CreateFrameCanvas()
    # retained until process exit (never freed), so steady-state paths must
    # never allocate. None until the first swap of the process.
    _last_back: Any = attrs.field(init=False, default=None)
```

Replace `get_clean_canvas` (lines 58-69):

```python
    def get_clean_canvas(self) -> Canvas:
        """A cleared canvas ready for rendering (tee-aware).

        Recycles the buffer the most recent swap() returned instead of
        allocating (see _last_back). Only before the first swap of the
        process does this fall back to backend.create_canvas().

        Aliasing contract: a call site must not hold a previous
        get_clean_canvas() result while fetching another — the second fetch
        Clears (and hands out) the same recycled buffer.
        """
        self._require_ready()
        canvas = self._last_back
        if canvas is None:
            canvas = self.backend.create_canvas()
        canvas.Clear()
        tee = self._preview_tee
        if tee is not None:
            tee._hw = canvas
            if tee.mirror:
                tee.Clear()
            return tee
        return canvas
```

In `swap` (lines 71-85), record the off-screen buffer on both branches:

```python
        tee = self._preview_tee
        if tee is not None and canvas is tee:
            new_hw = self.backend.swap(tee._hw)
            self._last_back = new_hw
            tee.maybe_capture()
            tee._hw = new_hw
            return tee
        new_back = self.backend.swap(canvas)
        self._last_back = new_back
        return new_back
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_frame.py -v`
Expected: ALL PASS (new + pre-existing). If a pre-existing test asserts two consecutive `get_clean_canvas()` calls return DIFFERENT objects across a swap, read it carefully — under recycling that expectation inverts; update the test only if its intent was "allocation happens" rather than a behavioral contract, and say so in your report.

- [ ] **Step 5: Run the wider blast radius**

Run: `uv run pytest tests/test_frame.py tests/test_backends tests/test_integration_render.py tests/test_ticker_display.py -q`
Expected: ALL PASS. These exercise real-LedFrame render paths; failures here mean an aliasing assumption broke — STOP and report NEEDS_CONTEXT with the failing test names rather than patching tests to fit.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/frame.py tests/test_frame.py
git commit -m "feat(frame): recycle the swap-returned buffer in get_clean_canvas

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Backend conformance — swap return must be reusable

**Files:**
- Modify: `src/led_ticker/backends/conformance.py` (new check + registration)
- Test: the existing conformance runner tests (find via `grep -rln run_backend_conformance tests/`)

**Interfaces:**
- Consumes: nothing from Task 1 (backend-level contract, not frame-level).
- Produces: `run_backend_conformance` additionally verifies the recycling precondition every backend must satisfy.

- [ ] **Step 1: Write the check**

Add to `src/led_ticker/backends/conformance.py` after `_check_swap_returns_new_buffer` (line ~33), matching the file's function-per-check style:

```python
def _check_swap_return_is_reusable(factory: Callable[[], Backend]) -> None:
    # LedFrame.get_clean_canvas recycles the buffer swap() returned (the
    # process-lifetime allocation invariant). That is only sound if a
    # swap-returned canvas is a live, drawable back buffer: Clear/SetPixel
    # must not raise, and re-swapping it must keep the double-buffer
    # alternation going (each swap returns a different object than it was
    # handed).
    b = factory()
    b.setup()
    c = b.create_canvas()
    for _ in range(3):
        returned = b.swap(c)
        assert returned is not c, "swap() must not return the canvas it was handed"
        returned.Clear()  # must not raise
        returned.SetPixel(0, 0, 9, 9, 9)  # must not raise
        c = returned
```

Register it wherever the suite enumerates its checks (find the list/loop in `run_backend_conformance` and add `_check_swap_return_is_reusable` alongside `_check_swap_returns_new_buffer`).

- [ ] **Step 2: Run the conformance tests**

Run: `grep -rln run_backend_conformance tests/` then `uv run pytest <those files> -v`
Expected: ALL PASS (headless + stub backends satisfy the contract already; this pins it for external backend authors).

- [ ] **Step 3: Commit**

```bash
git add src/led_ticker/backends/conformance.py
git commit -m "feat(conformance): pin that swap-returned canvases are reusable back buffers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Dark-path simplification — delete the retention threading

**Files:**
- Modify: `src/led_ticker/app/run.py` (`_cycle_dark_canvas` lines 249-261, `_idle_when_all_scheduled_out` lines 264-344, run() init line 1036-1037, `_idled` branch lines 1080-1090, idle call site lines 1093-1098)
- Test: `tests/test_run_section_schedule.py` (retarget)

**Interfaces:**
- Consumes: Task 1's recycling (`get_clean_canvas` after a swap allocates nothing).
- Produces: `_blank_swap(led_frame: Any) -> None` — one keepalive blank: `canvas = led_frame.get_clean_canvas(); canvas = led_frame.swap(canvas)` (capture per constraint #1; nothing retained — the frame remembers). `_idle_when_all_scheduled_out(led_frame, any_section_ran, was_dark, dark_streak) -> tuple[bool, int]` — `dark_canvas` parameter and return slot REMOVED. Task 4 reuses `_blank_swap`.

- [ ] **Step 1: Retarget the tests (write them failing first)**

In `tests/test_run_section_schedule.py`: the dark-path tests currently thread `dark_canvas` and assert fetch-once retention. Rewrite to the new contract:
- All `_idle_when_all_scheduled_out(...)` calls drop the `dark_canvas` argument and unpack `(dark, streak)` (2-tuple).
- Retention assertions (`get_clean_canvas.assert_called_once()` across episodes, `is existing_canvas` reuse) are REPLACED by: every committed dark iteration calls `get_clean_canvas()` once and `swap()` once with its result (`frame.swap.assert_called_with(frame.get_clean_canvas.return_value)`); allocation is now pinned at frame level by Task 1's tests, not here.
- Keep unchanged in intent: debounce (first all-out cycle = no fetch/blank/log, sleeps 1.0), transition-only logging, wake resets streak to 0, `slept == [1.0]` assertions, `_on_display_dark_transition` cases.
- Add:

```python
def test_blank_swap_captures_and_discards(monkeypatch):
    from led_ticker.app.run import _blank_swap

    frame = Mock()
    _blank_swap(frame)
    frame.get_clean_canvas.assert_called_once()
    frame.swap.assert_called_once_with(frame.get_clean_canvas.return_value)
```

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/test_run_section_schedule.py -v`
Expected: FAIL — `_blank_swap` missing; signature mismatches on `_idle_when_all_scheduled_out`.

- [ ] **Step 3: Implement**

Replace `_cycle_dark_canvas` (run.py:249-261) with:

```python
def _blank_swap(led_frame: Any) -> None:
    """One keepalive blank: fetch the (recycled — see LedFrame.get_clean_canvas)
    clean canvas and swap it. Shared by the all-scheduled-out dark idle and the
    empty-playlist idle: every idle path must keep swapping, or overlay hooks
    (busy_light composites inside frame.swap()) and the status board's
    swap_count liveness counter stall for the duration. Allocation-free after
    the process's first swap; the frame remembers its own back buffer, so
    callers thread nothing."""
    canvas = led_frame.get_clean_canvas()
    canvas = led_frame.swap(canvas)  # constraint #1: capture the swap return
    del canvas  # the frame recycles it on the next fetch
```

Rewrite `_idle_when_all_scheduled_out` — signature `(led_frame, any_section_ran, was_dark, dark_streak) -> tuple[bool, int]`; body identical control flow minus all `dark_canvas` handling: wake returns `(False, 0)`; debounce returns `(False, 1)`; committed dark logs on transition, calls `_blank_swap(led_frame)`, sleeps 1.0, returns `(True, dark_streak + 1)`. Docstring: KEEP the flicker-debounce paragraph and the liveness rationale; REPLACE the whole leak-guard/retention paragraph with two sentences pointing at the frame seam ("Allocation is not this function's concern anymore: LedFrame.get_clean_canvas recycles the swap-returned buffer, so per-iteration fetches are allocation-free — the process-lifetime O(1) invariant is pinned in tests/test_frame.py.").

In `run()`: delete `_dark_canvas: Any = None` (line 1036, keep `_dark_streak = 0`); the idle call site becomes:

```python
                    _display_dark, _dark_streak = await _idle_when_all_scheduled_out(
                        led_frame, _any_section_ran, _display_dark, _dark_streak
                    )
```

In the `_idled` branch (lines 1080-1090), leave the guard AS-IS for this task (`if _display_dark:` — drop only the `_dark_canvas is not None` clause and call `_blank_swap(led_frame)`); Task 4 makes it unconditional.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_run_section_schedule.py tests/test_run_reload_helpers.py tests/test_reload.py -q`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/run.py tests/test_run_section_schedule.py
git commit -m "refactor(run): dark idle rides the frame recycling seam — retention threading deleted

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Empty playlist blanks with keepalive (#396)

**Files:**
- Modify: `src/led_ticker/app/run.py` (`_idle_on_empty_playlist` lines 210-231 docstring + `_idled` branch)
- Modify: whichever docs page documents the empty-playlist behavior (`grep -rn "no sections" docs/site/src/content/ CLAUDE.md`)
- Test: `tests/test_run_section_schedule.py` or `tests/test_run_reload_helpers.py` (wherever the existing `_idle_on_empty_playlist` tests live — find with grep)

**Interfaces:**
- Consumes: `_blank_swap` from Task 3.
- Produces: behavior — a zero-section playlist blanks the panel and keeps swapping at ~1 Hz until a valid config lands.

- [ ] **Step 1: Write the failing test**

Next to the existing empty-playlist tests (grep `test_idle_on_empty_playlist`):

```python
def test_empty_playlist_blanks_and_keeps_swapping(monkeypatch):
    """Approved behavior change (#396): a zero-section playlist blanks the
    panel (instead of freezing the last frame) and keepalive-swaps every
    idle iteration, dark or not — overlay hooks and swap_count liveness
    must not stall during the interlude."""
    from led_ticker.app import run as run_mod

    frame = Mock()
    calls = []
    monkeypatch.setattr(run_mod, "_blank_swap", lambda f: calls.append(f))
    # Simulate three idled iterations of the run() branch: the branch body
    # is `if _idled: _blank_swap(led_frame); continue` — assert via the
    # extracted branch helper if one exists, else via the run()-spy pattern
    # used by test_per_section_reload_swaps_config_and_restarts_cycle.
```

Implementation note for this test: prefer driving the REAL `run()` loop with the existing spy scaffolding (a config double with `sections=[]`, a stop sentinel after ~3 outer iterations) and assert `_blank_swap` (or `frame.swap`) was called once per idled iteration and the panel-blank happened regardless of `_display_dark`. Follow `test_per_section_reload_swaps_config_and_restarts_cycle`'s harness; if the harness genuinely can't run with zero sections, extract the `_idled` branch body into a tiny helper and unit-test that instead — state which route you took in your report.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest <the test file> -k empty_playlist -v`
Expected: the new test FAILS (blank only happens while `_display_dark` today).

- [ ] **Step 3: Implement**

In the `_idled` branch, make the keepalive unconditional:

```python
                    if _idled:
                        # Approved behavior change (#396): zero sections =
                        # nothing to display = blank, same semantics as the
                        # all-scheduled-out dark path — NOT a frozen last
                        # frame. The keepalive swap keeps overlay hooks
                        # compositing and swap_count advancing throughout.
                        _blank_swap(led_frame)
                        continue
```

Extend `_idle_on_empty_playlist`'s docstring: the caller now blanks per idled iteration (behavior change vs the historical frozen frame); the 1 s sleep here paces the keepalive.

- [ ] **Step 4: Docs**

`grep -rn "no sections" docs/site/src/content/ CLAUDE.md` — wherever the empty-playlist behavior is described (hot-reload page and/or the warning's doc home), update: the panel goes dark during a zero-section interlude and recovers on the next valid config. If no docs page mentions it, add one sentence to the hot-reload concepts page.

- [ ] **Step 5: Run tests + commit**

Run: `uv run pytest tests/test_run_section_schedule.py tests/test_run_reload_helpers.py -q` — ALL PASS.

```bash
git add src/led_ticker/app/run.py tests/ docs/
git commit -m "feat(run): empty playlist blanks with keepalive swaps (#396)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Cross-scale transitions stop allocating (#395 tail)

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py:308-316` and `:350-360`
- Test: `tests/test_transitions.py` (find the cross-scale tests: `grep -n "incoming_scale" tests/test_transitions.py`)

**Interfaces:**
- Consumes: `unwrap_to_real` from `led_ticker.scaled_canvas` (add the import if the module lacks it — check existing imports first).
- Produces: `run_transition` performs zero `frame.create_canvas()` calls; the cross-scale re-wrap reuses the current back buffer.

- [ ] **Step 1: Write the failing test**

```python
class TestCrossScaleNoAllocation:
    async def test_run_transition_never_calls_create_canvas(self):
        # Reuse the file's existing cross-scale fixture (grep incoming_scale
        # for the canonical setup — outgoing at scale 1, incoming_scale=2).
        # Assert after the transition completes:
        frame.create_canvas.assert_not_called()
```

Write it against the file's existing cross-scale test harness (same widgets/frame mocks); the only new assertion is `create_canvas.assert_not_called()`. Cover BOTH switch paths: default `scale_switch_at=0.5` (in-loop switch) and a transition stub with `scale_switch_at = 0.0` (pre-loop switch).

- [ ] **Step 2: Run to verify both fail**

Run: `uv run pytest tests/test_transitions.py -k NoAllocation -v`
Expected: FAIL — `create_canvas` called once per cross-scale transition today.

- [ ] **Step 3: Implement**

Both sites re-wrap the CURRENT back buffer instead of allocating. Site 1 (pre-loop, lines 308-316):

```python
    if needs_switch and scale_switch_at <= 0.0:
        # Switch immediately: re-wrap the current back buffer at the
        # incoming scale. No allocation — after the switch the old-scale
        # `canvas` wrapper is never drawn or swapped again (`active` is
        # always incoming_canvas from here), so sharing its real buffer is
        # safe, and the per-frame Fill/Clear below erases its old content.
        assert incoming_scale is not None  # guaranteed by needs_switch
        incoming_canvas = _maybe_wrap(
            unwrap_to_real(canvas),
            incoming_scale,
            incoming_content_height,
        )
        needs_switch = False  # already switched — skip in-loop check
```

Site 2 (in-loop, lines 350-360): same substitution — `unwrap_to_real(canvas)` replaces `frame.create_canvas()`, with a one-line comment pointing at the site-1 rationale. Add `unwrap_to_real` to the module's `scaled_canvas` import.

- [ ] **Step 4: Run the transition suite**

Run: `uv run pytest tests/test_transitions.py -q`
Expected: ALL PASS — the pre-existing cross-scale tests (dissolve-in at native size, `_OutgoingScaleSweep` late switch, bg cut-over at `scale_switch_at`) are the behavioral net; a failure means the shared-real assumption broke somewhere — STOP and report NEEDS_CONTEXT with the failing test, do not force it.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/__init__.py tests/test_transitions.py
git commit -m "fix(transitions): cross-scale re-wrap reuses the back buffer — no per-transition allocation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: End-to-end allocation tripwire

**Files:**
- Create: `tests/test_frame_allocation.py`

**Interfaces:**
- Consumes: everything above; `HeadlessBackend` from `led_ticker.backends.headless`.
- Produces: the O(1)-allocation invariant pinned end-to-end (spec: "create_canvas call count O(1) across N entry transitions + N dark iterations + N empty-playlist idle iterations").

- [ ] **Step 1: Write the test**

```python
"""Process-lifetime allocation tripwire (spec: engine-liveness Phase 1).

Steady-state render paths must never call backend.create_canvas — on the
real backend each call is a C++ CreateFrameCanvas() retained until process
exit. LedFrame recycles the swap-returned buffer; this test drives the real
LedFrame + HeadlessBackend through the three paths that historically
allocated (entry-transition seeds, dark idle, empty-playlist idle) and pins
the total."""

import asyncio

from led_ticker.backends.headless import HeadlessBackend
from led_ticker.frame import LedFrame


class _CountingHeadless(HeadlessBackend):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.create_calls = 0

    def create_canvas(self):
        self.create_calls += 1
        return super().create_canvas()


def _live_frame():
    backend = _CountingHeadless(width=64, height=16)
    frame = LedFrame(backend=backend)
    frame.setup()
    return frame, backend


def test_allocation_is_constant_across_steady_state_paths():
    from led_ticker.app.run import _blank_swap

    frame, backend = _live_frame()
    # Boot-ish first fetch + swap.
    c = frame.get_clean_canvas()
    c = frame.swap(c)
    baseline = backend.create_calls
    # N "entry transition seed + section run" fetch/swap cycles.
    for _ in range(10):
        c = frame.get_clean_canvas()
        c = frame.swap(c)
    # N dark/empty-idle keepalives.
    for _ in range(10):
        _blank_swap(frame)
    assert backend.create_calls == baseline
    assert baseline <= 2  # first-fetch bound (nothing recycled before swap #1)
```

Check `HeadlessBackend`'s actual constructor signature (`grep -n "def __init__" src/led_ticker/backends/headless.py`) and adapt `_CountingHeadless`'s super call — do not guess.

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_frame_allocation.py -v`
Expected: PASS (Tasks 1+3 already landed). If it fails, a steady-state path still allocates — find it before proceeding.

- [ ] **Step 3: Commit**

```bash
git add tests/test_frame_allocation.py
git commit -m "test(frame): end-to-end O(1) allocation tripwire across steady-state paths

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Invariant docs, wording sync, full gate

**Files:**
- Modify: `CLAUDE.md` (new invariant bullet; touch up the "Visibility scheduling" bullet's dark-path sentence)
- Modify: `docs/site/src/content/docs/concepts/scheduling.mdx` (dark-path allocation wording, if it claims "at most one framebuffer allocated by the dark path")

**Interfaces:** prose only.

- [ ] **Step 1: CLAUDE.md invariant**

Add to the load-bearing invariants (near the hardware constraints), one bullet:

```markdown
**Idle keepalive & framebuffer recycling** — Two paired invariants. (1) IDLE PATHS MUST KEEP SWAPPING: overlay hooks (busy_light) composite inside `LedFrame.swap()` and the status board's `swap_count` liveness verdict rides on it — an idle loop that sleeps without swapping freezes the busy dot and reads as a wedged render loop. Both idles (all-scheduled-out dark, empty playlist) call `_blank_swap` per ~1s iteration; a zero-section playlist BLANKS the panel (behavior change, #396) rather than freezing the last frame. (2) STEADY-STATE PATHS MUST NEVER CALL `backend.create_canvas`: the real backend's C++ `CreateFrameCanvas()` retains every allocation until process exit. `LedFrame.get_clean_canvas` recycles the buffer the most recent `swap()` returned (`_last_back`); cross-scale transitions re-wrap `unwrap_to_real(canvas)` instead of allocating. Aliasing contract: never hold a previous `get_clean_canvas()` result while fetching another. Tripwires: `TestGetCleanCanvasRecycling` (`tests/test_frame.py`), `tests/test_frame_allocation.py`, `_check_swap_return_is_reusable` (`backends/conformance.py`).
```

Then fix the "Visibility scheduling" bullet: its dark-path sentence still describes per-process `dark_canvas` retention — reword to point at the frame seam ("dark idle rides `LedFrame`'s recycling; the debounce remains as the flicker guard").

- [ ] **Step 2: scheduling.mdx**

`grep -n "framebuffer\|allocat" docs/site/src/content/docs/concepts/scheduling.mdx` — if the dark-path note claims the retention lives in the dark path, generalize it ("the engine recycles its framebuffers; a dark panel allocates nothing"). Keep it to a clause; this is a user page, not an internals doc.

- [ ] **Step 3: Full gate**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-canvas-liveness
make test          # full suite green
make lint
git diff --name-only main...HEAD | grep '\.py$' | tr '\n' ' ' | xargs uv run pyright   # 0 errors on touched files
source ~/.nvm/nvm.sh && nvm use && make docs-build && make docs-lint
uv run led-ticker validate config/config.scheduling_smoketest.longboi.toml
uv run led-ticker validate config/config.scheduling_smoketest.bigsign.toml
```

Expected: all green; both smoketests "No issues found".

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/
git commit -m "docs: idle-keepalive + framebuffer-recycling invariant; sync dark-path wording

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Adversarial pass + draft PR

Per the spec's validation depth for Phase 1 (standard review already happened per-task; ONE adversarial pass, not the full loop):

- [ ] **Step 1:** Controller dispatches one adversarial correctness reviewer (mechanism-first, whole-branch diff, focus: the recycling seam's aliasing surface, tee interaction, cross-scale shared-real trace, empty-playlist behavior change) — handled at execution time by the controller, not by a task implementer.
- [ ] **Step 2:** Fix anything found; re-verify.
- [ ] **Step 3:** Open a draft PR via the open-pr skill: body covers the seam, the behavior change (empty playlist blanks — call it out explicitly for the reviewer), closes #395 and #396, notes Phase 1-of-3 with the spec link. Watch CI. Do NOT merge — James's per-PR consent required.

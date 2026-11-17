# Center Wipes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Superseded in part by antagonist review cycles 1–3** (ledger:
> `docs/superpowers/reviews/2026-11-17-center-wipes-antagonist.md`). As shipped:
> `progress_to_b(t, n, inward)` is three-arg and capped by `front_cap(n, inward)`
> (`(n - 1) // 2` inward, `n // 2 - 1` outward) instead of `half`; frame 0 paints the
> sweep lines where the fronts start (not empty at `b == 0`); sweep lines are one
> `SubFill` per span, not per-pixel `SetPixel`; `transitions/__init__.py` gained the
> four re-exports. The task text below is the pre-review record.

**Goal:** Four new erase-style wipe transitions whose sweep fronts start or end at the panel center: `wipe_in`, `wipe_out`, `wipe_in_vertical`, `wipe_out_vertical`.

**Architecture:** One new auto-discovered module `src/led_ticker/transitions/center_wipe.py` holding pure span geometry (`progress_to_b`, `center_spans`, `sweep_line_spans`), a private `_CenterWipe(_BaseWipe)` parametrized by `axis` and `inward`, and four thin registered subclasses. Geometry is computed in physical pixels via `_phys` so letterbox bands are erased, same as the existing wipes. No existing transition file changes.

**Tech Stack:** Python 3.14, attrs-free plain classes, pytest, ruff, pyright. Repo: core (`/Users/james/projects/github/jamesawesome/led-ticker`), worktree branch `center-wipes`.

**Spec:** `docs/superpowers/specs/2026-11-17-center-wipes-design.md` (gate: `docs/superpowers/specs/2026-11-17-center-sweeps-gate.md`).

## Global Constraints

- `wipe.py`, `push.py`, `effects.py`, `transitions/__init__.py` are NOT modified. `wipe_random` / `wipe_alternating` pools are untouched.
- No `from __future__ import annotations` (PEP 649 rule in CLAUDE.md).
- Transition contract: `t = 0` renders outgoing only (plus sweep lines), `t >= 1.0` renders incoming only; the runner clears the canvas, the transition never does.
- All blackout/line geometry in PHYSICAL pixels from `_phys(canvas)`; inherit `_OutgoingScaleSweep` (via `_BaseWipe`) so `scale_switch_at = 1.0`.
- Sweep line thickness `2 * scale`, painted on the KEPT side of each front, clamped to the kept span (matches `wipe_left`/`wipe_right`).
- Defaults from the spec: `wipe_in` / `wipe_in_vertical` color `(255, 255, 0)`, `wipe_out` / `wipe_out_vertical` color `(255, 0, 0)`; `min_frames` 20 horizontal, 16 vertical.
- Center math from the spec: `half = (n + 1) // 2`; `b = min(int(t * (half + 1)), half)`; `b == 0` erases nothing; inward erased `[0, b)` ∪ `[n - b, n)`; outward erased `[n // 2 - b, n // 2 + b + n % 2)` clamped to `[0, n)`.
- Work in a worktree (`git worktree add ../led-ticker-center-wipes -b center-wipes`), never the main checkout. Verify `pwd` and branch before any git op.
- Commands: tests `uv run --no-sync python -m pytest <path> -q`; lint `make lint`; format `make format`; types `uv run pyright src/led_ticker/transitions/center_wipe.py`; docs prose follows `docs/DOCS-STYLE.md`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. Odd physical extents (`n = 15`, `159`): the two fronts must meet with no 1-px gap or overlap. Pinned in Task 1.
2. `t` slightly below 1.0 (e.g. `0.999`) must be fully erased, not show a sliver of outgoing. Pinned in Task 1 (`progress_to_b` reaches `half`) and Task 2.
3. Banded scale-2 wrapper on a 256×64 panel: letterbox rows 0..15 and 48..63 must be blacked out inside the erased spans. Pinned in Task 3.
4. `outgoing_scroll_pos` must reach `outgoing.draw` so a scrolled message does not jump at transition start. Pinned in Task 2.
5. Sweep lines at the panel edge at `t = 0` for inward variants: thickness clamp must not write off-panel or onto the erased side. Pinned in Task 1 (`sweep_line_spans` within kept) and Task 2.

---

### Task 1: Pure span geometry

**Files:**
- Create: `src/led_ticker/transitions/center_wipe.py`
- Test: `tests/test_center_wipe.py`

**Interfaces:**
- Produces:
  - `progress_to_b(t: float, n: int) -> int`
  - `center_spans(n: int, b: int, inward: bool) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]` returning `(erased, kept)` half-open spans, each list sorted, non-overlapping, all within `[0, n)`.
  - `sweep_line_spans(n: int, b: int, inward: bool, thick: int) -> list[tuple[int, int]]` half-open spans on the kept side adjacent to each erased edge, each at most `thick` wide, never overlapping an erased span, empty when nothing is erased (`b == 0`) or nothing is kept.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from led_ticker.transitions.center_wipe import center_spans, progress_to_b, sweep_line_spans

EXTENTS = (15, 16, 159, 160, 256)

def _cover(spans):
    s = set()
    for lo, hi in spans:
        s.update(range(lo, hi))
    return s

@pytest.mark.parametrize("n", EXTENTS)
@pytest.mark.parametrize("inward", [True, False])
def test_spans_partition_every_b(n, inward):
    half = (n + 1) // 2
    for b in range(half + 1):
        erased, kept = center_spans(n, b, inward)
        e, k = _cover(erased), _cover(kept)
        assert e | k == set(range(n)), (n, b, inward)
        assert not (e & k), (n, b, inward)

@pytest.mark.parametrize("n", EXTENTS)
@pytest.mark.parametrize("inward", [True, False])
def test_b_zero_erases_nothing_and_half_erases_all(n, inward):
    assert center_spans(n, 0, inward)[0] == []
    half = (n + 1) // 2
    assert _cover(center_spans(n, half, inward)[0]) == set(range(n))

@pytest.mark.parametrize("n", EXTENTS)
def test_progress_to_b_endpoints(n):
    half = (n + 1) // 2
    assert progress_to_b(0.0, n) == 0
    assert progress_to_b(0.999, n) == half
    assert progress_to_b(1.0, n) == half
    assert all(0 <= progress_to_b(t / 100, n) <= half for t in range(101))

def test_inward_spans_shape_even():
    erased, kept = center_spans(160, 10, True)
    assert erased == [(0, 10), (150, 160)]
    assert kept == [(10, 150)]

def test_outward_spans_shape_odd_keeps_center_in_band():
    erased, kept = center_spans(15, 1, False)
    assert erased == [(6, 9)]
    assert kept == [(0, 6), (9, 15)]

@pytest.mark.parametrize("n", EXTENTS)
@pytest.mark.parametrize("inward", [True, False])
def test_sweep_lines_sit_on_kept_side(n, inward):
    half = (n + 1) // 2
    for b in range(half + 1):
        erased, kept = center_spans(n, b, inward)
        lines = _cover(sweep_line_spans(n, b, inward, thick=2))
        assert lines <= _cover(kept), (n, b, inward)
        assert not (lines & _cover(erased))
        if b == 0 or not kept:
            assert lines == set()

def test_sweep_lines_inward_even_example():
    assert sweep_line_spans(160, 10, True, thick=2) == [(10, 12), (148, 150)]

def test_sweep_lines_outward_even_example():
    assert sweep_line_spans(160, 10, False, thick=2) == [(68, 70), (90, 92)]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_center_wipe.py -q`
Expected: FAIL, `ModuleNotFoundError: led_ticker.transitions.center_wipe`.

- [ ] **Step 3: Implement the three functions in `center_wipe.py`**

Module docstring states the erase-style semantics and the odd-center rule. `center_spans` merges the two inward spans into `[(0, n)]` when `2 * b >= n`. Outward clamps `lo = max(0, n // 2 - b)`, `hi = min(n, n // 2 + b + n % 2)` and returns `erased=[(lo, hi)]`, `kept` from the two remainders dropping empties. `sweep_line_spans`: for each erased span edge that borders a kept span, take `thick` pixels of the kept span starting at that edge, clamped to the kept span.

- [ ] **Step 4: Run to verify pass**

Run: `uv run --no-sync python -m pytest tests/test_center_wipe.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/center_wipe.py tests/test_center_wipe.py
git commit -m "feat(transitions): center-wipe span geometry (pure, partition-tested)"
```

---

### Task 2: `_CenterWipe` and the four registered transitions

**Files:**
- Modify: `src/led_ticker/transitions/center_wipe.py`
- Modify: `tests/test_center_wipe.py`
- Modify: `tests/test_transitions_registry.py:12-15`

**Interfaces:**
- Consumes: Task 1 functions; `_BaseWipe` from `led_ticker.transitions.wipe`; `_phys`, `register_transition` from `led_ticker.transitions`.
- Produces: classes `WipeIn`, `WipeOut`, `WipeInVertical`, `WipeOutVertical`, registered as `wipe_in`, `wipe_out`, `wipe_in_vertical`, `wipe_out_vertical`. Class attrs: `AXIS: str` (`"x"` | `"y"`), `INWARD: bool`, `DEFAULT_COLOR`, `min_frames`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_center_wipe.py`; use a `HeadlessCanvas(160, 16)` and the `make_widget` mock factory shape from `tests/test_transitions.py::TestBandedCanvasFullPanel`)

```python
from unittest import mock
from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.transitions import get_transition_class
from led_ticker.transitions.center_wipe import WipeIn, WipeInVertical, WipeOut, WipeOutVertical

ALL = [WipeIn, WipeOut, WipeInVertical, WipeOutVertical]
NAMES = ["wipe_in", "wipe_out", "wipe_in_vertical", "wipe_out_vertical"]

def _widget():
    w = mock.Mock(); w.hold_time = 0.0
    w.draw.side_effect = lambda c, cursor_pos=0, **kw: (c, cursor_pos + 40)
    return w

@pytest.mark.parametrize("name,cls", zip(NAMES, ALL))
def test_registered(name, cls):
    assert get_transition_class(name) is cls

@pytest.mark.parametrize("cls", ALL)
def test_t0_draws_outgoing_only_t1_incoming_only(cls):
    canvas = HeadlessCanvas(160, 16); out, inc = _widget(), _widget()
    cls().frame_at(0.0, canvas, out, inc)
    assert out.draw.called and not inc.draw.called
    out.reset_mock(); inc.reset_mock()
    cls().frame_at(1.0, canvas, out, inc)
    assert inc.draw.called and not out.draw.called

@pytest.mark.parametrize("cls", ALL)
def test_outgoing_scroll_pos_forwarded(cls):
    canvas = HeadlessCanvas(160, 16); out = _widget()
    cls().frame_at(0.3, canvas, out, _widget(), outgoing_scroll_pos=-37)
    assert out.draw.call_args.kwargs["cursor_pos"] == -37

def test_defaults():
    assert WipeIn.DEFAULT_COLOR == (255, 255, 0) and WipeOut.DEFAULT_COLOR == (255, 0, 0)
    assert WipeIn.min_frames == 20 and WipeOut.min_frames == 20
    assert WipeInVertical.min_frames == 16 and WipeOutVertical.min_frames == 16
    assert WipeIn(color=(1, 2, 3)).color == (1, 2, 3)

def test_wipe_in_midway_erases_edges_and_paints_lines():
    canvas = HeadlessCanvas(160, 16)
    out = mock.Mock(); out.hold_time = 0.0
    def paint(c, cursor_pos=0, **kw):
        for x in range(160):
            for y in range(16): c.SetPixel(x, y, 9, 9, 9)
        return c, 160
    out.draw.side_effect = paint
    WipeIn().frame_at(0.5, canvas, out, _widget())
    b = progress_to_b(0.5, 160)
    assert canvas.get_pixel(0, 8) == (0, 0, 0) and canvas.get_pixel(159, 8) == (0, 0, 0)
    assert canvas.get_pixel(b, 8) == (255, 255, 0)          # line on kept side
    assert canvas.get_pixel(159 - b, 8) == (255, 255, 0)
    assert canvas.get_pixel(80, 8) == (9, 9, 9)              # center still outgoing

def test_wipe_out_vertical_just_before_end_is_fully_black():
    canvas = HeadlessCanvas(160, 16)
    out = mock.Mock(); out.hold_time = 0.0
    def paint(c, cursor_pos=0, **kw):
        for x in range(160):
            for y in range(16): c.SetPixel(x, y, 9, 9, 9)
        return c, 160
    out.draw.side_effect = paint
    WipeOutVertical().frame_at(0.999, canvas, out, _widget())
    assert all(canvas.get_pixel(x, y) == (0, 0, 0) for x in (0, 80, 159) for y in range(16))
```

And in `tests/test_transitions_registry.py::test_list_transition_names_includes_core_transitions` extend the tuple with `"wipe_in", "wipe_out", "wipe_in_vertical", "wipe_out_vertical"`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_center_wipe.py tests/test_transitions_registry.py -q`
Expected: FAIL with `ImportError` on the class names.

- [ ] **Step 3: Implement `_CenterWipe(_BaseWipe)` and subclasses**

`frame_at(self, t, canvas, outgoing, incoming, **kwargs) -> Canvas`: `real, rw, rh, scale, _yo = _phys(canvas)`; `n = rw if self.AXIS == "x" else rh`; if `t >= 1.0` draw incoming at `cursor_pos=0` and return; draw outgoing at `kwargs.get("outgoing_scroll_pos", 0)`; `b = progress_to_b(t, n)`; for each erased span `SubFill` the full cross extent black (`real.SubFill(lo, 0, hi - lo, rh, 0, 0, 0)` for x, `real.SubFill(0, lo, rw, hi - lo, 0, 0, 0)` for y); for each span in `sweep_line_spans(n, b, self.INWARD, 2 * scale)` `SetPixel` every pixel of the cross extent in `self.color`. Subclasses: `WipeIn(AXIS="x", INWARD=True, DEFAULT_COLOR=(255,255,0), min_frames=20)`, `WipeOut(AXIS="x", INWARD=False, DEFAULT_COLOR=(255,0,0), min_frames=20)`, `WipeInVertical(AXIS="y", INWARD=True, yellow, 16)`, `WipeOutVertical(AXIS="y", INWARD=False, red, 16)`. Each gets a one-line docstring naming the Alpha / Huidu mode it mirrors.

- [ ] **Step 4: Run to verify pass, then the whole transitions suite**

Run: `uv run --no-sync python -m pytest tests/test_center_wipe.py tests/test_transitions_registry.py tests/test_transitions.py -q`
Expected: all PASS (existing suite proves nothing else changed).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/center_wipe.py tests/test_center_wipe.py tests/test_transitions_registry.py
git commit -m "feat(transitions): wipe_in / wipe_out and vertical twins (erase-style center wipes)"
```

---

### Task 3: Banded and scaled canvas coverage

**Files:**
- Modify: `tests/test_center_wipe.py`

**Interfaces:**
- Consumes: Task 2 classes; `ScaledCanvas` from `led_ticker.scaled_canvas`.

- [ ] **Step 1: Write the failing tests** (mirror `TestBandedCanvasFullPanel`: real `HeadlessCanvas(256, 64)`, `ScaledCanvas(real, scale=2, content_height=16)`, top band rows 0..15 pre-filled with `(100, 100, 100)`)

```python
def test_wipe_in_blackout_covers_top_band_on_banded_wrapper():
    # at t=0.5, n=256 -> b=progress_to_b(0.5, 256); columns [0,b) and [256-b,256) black in rows 0..15
def test_wipe_out_vertical_blackout_covers_letterbox_rows_when_band_reaches_them():
    # at t=0.999 every physical row 0..63 is black across x in (0, 128, 255)
def test_sweep_line_is_two_times_scale_thick_on_scale4():
    # ScaledCanvas(HeadlessCanvas(256, 64), scale=4, content_height=16); WipeOut at t=0.5;
    # count consecutive line-colored columns at y=32 on each side of the band == 8
```

- [ ] **Step 2: Run to verify failure or pass**

Run: `uv run --no-sync python -m pytest tests/test_center_wipe.py -q`
Expected: PASS if Task 2 used `_phys` correctly; any FAIL points at a logical-vs-physical mistake to fix in `center_wipe.py`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_center_wipe.py
git commit -m "test(transitions): center wipes cover letterbox bands and scale line thickness"
```

---

### Task 4: Docs

**Files:**
- Modify: `docs/content-source/transitions/wipe.md` (table + one `split` sentence)
- Modify: `docs/site/src/content/docs/transitions/wipe.mdx:14` (caption)
- Modify: `docs/site/src/content/docs/tutorial/05-polish.mdx:130`

**Interfaces:** none.

- [ ] **Step 1: Add four table rows** after `wipe_down`, columns `Name | Sweep direction | Default color | Best for`:
  `wipe_in` | both edges → center | yellow | Closing curtain feel; `wipe_out` | center → both edges | red | Opening reveal; `wipe_in_vertical` | top and bottom → center row | yellow | Vertical close; `wipe_out_vertical` | center row → top and bottom | red | Vertical open. Add after the table: "`split` is the magenta-edged twin of `wipe_out`: same geometry, fixed edge lines, no color knob."

- [ ] **Step 2: Update the caption** to "wipe family — left, right, up, down, and random; center variants `wipe_in` / `wipe_out` share the same look" and add the four names to the tutorial's Wipe line.

- [ ] **Step 3: Verify the docs build**

Run: `cd docs/site && pnpm exec prettier --check src/content/docs/transitions/wipe.mdx src/content/docs/tutorial/05-polish.mdx && pnpm run build` (source nvm first if `pnpm` is missing).
Expected: prettier clean, build succeeds.

- [ ] **Step 4: Commit**

```bash
git add docs/content-source/transitions/wipe.md docs/site/src/content/docs/transitions/wipe.mdx docs/site/src/content/docs/tutorial/05-polish.mdx
git commit -m "docs(transitions): document wipe_in / wipe_out and vertical twins"
```

---

### Task 5: Validate, lint, types, full suite, spec files

**Files:**
- Add: `docs/superpowers/specs/2026-11-17-center-sweeps-gate.md`, `docs/superpowers/specs/2026-11-17-center-wipes-design.md`, `docs/superpowers/plans/2026-11-17-center-wipes.md` (already written, untracked)

- [ ] **Step 1: Config preflight with the new names**

Write a scratch TOML in the scratchpad with four sections each using one new `transition`, then `uv run --no-sync led-ticker validate CONFIG=<path>` (or `make validate CONFIG=...`). Expected: no "unknown transition" error.

- [ ] **Step 2: Lint, format, types, full tests**

Run: `make lint && make format && uv run pyright src/led_ticker/transitions/center_wipe.py && make test`
Expected: clean; coverage not below the pre-branch number.

- [ ] **Step 3: Commit the spec, gate, and plan**

```bash
git add docs/superpowers/specs/2026-11-17-center-sweeps-gate.md docs/superpowers/specs/2026-11-17-center-wipes-design.md docs/superpowers/plans/2026-11-17-center-wipes.md
git commit -m "docs(superpowers): center wipes gate, design, and plan"
```

Then the antagonist loop (roadmap §1.4), hardware check (gate §9), and ready-and-ask.

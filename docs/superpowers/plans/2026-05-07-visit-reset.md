# Visit-Reset / Continuous-Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop animated chases (`RainbowChaseBorder`, `Rainbow`, `ColorCycle`) from snapping their phase to 0 at every `loop_count > 1` iteration of a single-widget section, while preserving today's "retype each loop" behavior for `Typewriter`.

**Architecture:** Add a `_should_reset_frame()` gate in `ticker.py`. The gate inspects the widget's effects (`font_color`, `top_color`, `bottom_color`, `border`, `animation`) and returns False if ANY effect opts out of `restart_on_visit`. Effects that want continuous phase set `restart_on_visit: bool = False` as a class attribute (`Rainbow`, `ColorCycle`, `RainbowChaseBorder`). Default `True` via `getattr` fallback preserves today's behavior for unknown effects. Section entry is unchanged — `run_transition._reset_presenter` already resets at every section boundary.

**Tech Stack:** Python 3.13, asyncio, attrs, pytest, ruff. No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-05-07-visit-reset-design.md`](../specs/2026-05-07-visit-reset-design.md)

**Worktree:** `.claude/worktrees/visit-reset` (branch `feat/visit-reset`)

---

## File Inventory

**Modified:**
- `src/led_ticker/ticker.py` — add `_should_reset_frame()` helper near `_show_one`; wire it into the reset path at `_show_one:729-730`.
- `src/led_ticker/color_providers.py` — `Rainbow.restart_on_visit = False`, `ColorCycle.restart_on_visit = False`. Add module docstring note about the convention.
- `src/led_ticker/borders.py` — `RainbowChaseBorder.restart_on_visit = False`. Add module docstring note.
- `tests/test_ticker_display.py` — augment existing `TestShowOneResetsFrame` class with new tests for the gate; add `TestShouldResetFrame` (4 tests on the helper) and `TestShouldResetFrameComposition` (1 test).
- `tests/test_color_providers.py` — add 2 attribute-pin tests.
- `tests/test_borders.py` — add 1 attribute-pin test.
- `CLAUDE.md` — replace the visit-reset hedge in the Rainbow border section with the new behavior.
- `config/config.rainbow_border_test.example.toml` — revert §4/§5/§7 to `loop_count = 3 × gif_loops = 3`; remove §5's workaround comment.

**Not modified (referenced):**
- `src/led_ticker/transitions/__init__.py:184` — `_reset_presenter(incoming)` runs at every transition entry. Confirms section-entry reset is preserved without code changes.
- `src/led_ticker/widgets/_frame_aware.py` — `_FrameAware._frame_count` mixin. Default 0 at construction. No changes needed.

---

## Implementation Conventions

**TDD discipline:** every task writes the failing test first, runs it to confirm it fails, then implements minimal code, runs the tests to confirm pass, then commits.

**Test commands** (from worktree root):
- One file: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py -v`
- One test: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestShouldResetFrame::test_no_effects_resets -v`
- Full suite: `PYTHONPATH=tests/stubs uv run pytest -x -q`

**Lint:** `uv run ruff check src/led_ticker tests` after each task.

**Pre-commit hooks** (auto-run on commit): ruff, ruff-format, pyright, pytest. The full suite must pass for any commit to land.

---

### Task 1: `_should_reset_frame()` helper + unit tests

**Files:**
- Modify: `src/led_ticker/ticker.py:709-742` (add helper above `_show_one`)
- Test: `tests/test_ticker_display.py` (new class `TestShouldResetFrame`)

The helper inspects a widget's effect attributes and returns False if ANY effect has `restart_on_visit` explicitly set to False. Default `True` via `getattr` fallback means unknown classes keep today's behavior.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ticker_display.py` (place AFTER the existing `TestShowOneResetsFrame` class for related-test grouping):

```python
class TestShouldResetFrame:
    """`_should_reset_frame()` returns True iff every effect on the
    widget either has `restart_on_visit = True` (the default) or
    omits the attribute entirely. ANY effect with explicit
    `restart_on_visit = False` blocks the reset — favors continuity
    for animated chases that should advance smoothly across
    loop_count boundaries."""

    def test_no_effects_resets(self):
        """Widget with no effect attributes — falls through every
        check, returns True."""
        from led_ticker.ticker import _should_reset_frame

        class _Widget:
            pass

        assert _should_reset_frame(_Widget()) is True

    def test_continuous_color_provider_blocks_reset(self):
        """font_color with `restart_on_visit = False` → False."""
        from led_ticker.ticker import _should_reset_frame

        class _Provider:
            restart_on_visit = False

        class _Widget:
            font_color = _Provider()

        assert _should_reset_frame(_Widget()) is False

    def test_continuous_border_blocks_reset(self):
        """border with `restart_on_visit = False` → False."""
        from led_ticker.ticker import _should_reset_frame

        class _Border:
            restart_on_visit = False

        class _Widget:
            border = _Border()

        assert _should_reset_frame(_Widget()) is False

    def test_typewriter_alone_resets(self):
        """animation with `restart_on_visit = True` (default
        behavior for Typewriter) and no other effects → True."""
        from led_ticker.ticker import _should_reset_frame

        class _Animation:
            restart_on_visit = True

        class _Widget:
            animation = _Animation()

        assert _should_reset_frame(_Widget()) is True

    def test_unknown_effect_class_keeps_default_true(self):
        """Effect that simply doesn't set restart_on_visit → uses
        getattr default of True. Back-compat path for any third-
        party / unknown effect class."""
        from led_ticker.ticker import _should_reset_frame

        class _CustomEffect:
            pass  # no restart_on_visit attribute

        class _Widget:
            font_color = _CustomEffect()

        assert _should_reset_frame(_Widget()) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestShouldResetFrame -v`

Expected: FAIL with `ImportError: cannot import name '_should_reset_frame' from 'led_ticker.ticker'`.

- [ ] **Step 3: Add the helper to `ticker.py`**

In `src/led_ticker/ticker.py`, immediately above the existing `async def _show_one(` declaration at line 709, insert:

```python
def _should_reset_frame(widget: Any) -> bool:
    """Decide whether `_show_one` should call `reset_frame()` on
    visit entry.

    ANY effect on the widget that opts out of `restart_on_visit`
    blocks the reset. Favors continuity over restart — the safer
    default for animated chases (RainbowChaseBorder, Rainbow,
    ColorCycle) that should advance smoothly across loop_count
    boundaries within a section.

    Default `True` via `getattr` fallback keeps today's behavior
    for unknown effect classes — only effects that explicitly set
    `restart_on_visit = False` opt out.

    Composition tradeoff: a widget with both `Typewriter` (wants
    restart) and `RainbowChaseBorder` (wants continuous) gets the
    continuous semantics — typewriter doesn't retype on inner
    loop iterations. Niche combo; documented in CLAUDE.md.

    Section-entry resets are unaffected — `run_transition` calls
    `_reset_presenter(incoming)` at every transition boundary, so
    the new section's first `_show_one` call sees `_frame_count`
    already reset to 0 regardless of this gate's verdict.
    """
    for attr in ("font_color", "top_color", "bottom_color", "border", "animation"):
        effect = getattr(widget, attr, None)
        if effect is None:
            continue
        if not getattr(effect, "restart_on_visit", True):
            return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestShouldResetFrame -v`

Expected: PASS (5 tests).

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green. The new helper isn't called anywhere yet, so existing tests are unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "visit-reset: add _should_reset_frame() helper + unit tests"
```

---

### Task 2: Wire helper into `_show_one` + integration tests

**Files:**
- Modify: `src/led_ticker/ticker.py:729-730` (the existing `if hasattr(widget, "reset_frame"):` block)
- Test: `tests/test_ticker_display.py` (augment existing `TestShowOneResetsFrame` and add `TestShouldResetFrameComposition`)

Replace the unconditional `widget.reset_frame()` call in `_show_one` with a gated version. Add 2 integration tests verifying behavior across simulated `loop_count` iterations + 1 composition tripwire.

- [ ] **Step 1: Write the failing integration tests**

In `tests/test_ticker_display.py`, append to the END of `class TestShowOneResetsFrame`:

```python
    async def test_show_one_skips_reset_when_border_is_continuous(
        self, swapping_frame, no_sleep
    ):
        """Widget with a RainbowChaseBorder (restart_on_visit=False)
        should NOT have its frame counter reset on entry to
        `_show_one`. Simulates a `loop_count > 1` iteration where
        the chase phase must keep advancing across the boundary."""
        from rgbmatrix import _StubCanvas

        class _ContinuousBorder:
            restart_on_visit = False

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 42  # mid-chase value
                self._frame_paused = False
                self.reset_called = False
                self.border = _ContinuousBorder()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def reset_frame(self):
                self._frame_count = 0
                self.reset_called = True

            def advance_frame(self):
                self._frame_count += 1

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)

        assert not widget.reset_called, (
            "RainbowChaseBorder (restart_on_visit=False) should "
            "block the reset — chase phase must advance across "
            "loop_count boundaries"
        )
        # Frame counter advanced (from advance_frame calls during the
        # hold loop), didn't snap back to 0
        assert widget._frame_count > 42

    async def test_show_one_resets_for_typewriter_widget(
        self, swapping_frame, no_sleep
    ):
        """Widget with only Typewriter (default restart_on_visit=True
        behavior) should still get reset on entry — preserves
        today's retype-each-loop semantics."""
        from rgbmatrix import _StubCanvas

        class _TypewriterAnim:
            restart_on_visit = True  # explicit default

        class _SpyWidget:
            def __init__(self):
                self._frame_count = 99
                self._frame_paused = False
                self.reset_called = False
                self.animation = _TypewriterAnim()

            def draw(self, canvas, cursor_pos=0, **kwargs):
                return canvas, 5

            def reset_frame(self):
                self._frame_count = 0
                self.reset_called = True

            def advance_frame(self):
                self._frame_count += 1

            @property
            def bg_color(self):
                return None

        widget = _SpyWidget()
        canvas = _StubCanvas(width=160, height=16)
        swapping_frame.matrix.SwapOnVSync.return_value = _StubCanvas(
            width=160, height=16
        )

        await _show_one(canvas, swapping_frame, widget, hold_time=0.1)

        assert widget.reset_called, (
            "Typewriter (restart_on_visit=True) must still trigger "
            "the reset — preserves retype-each-loop semantics"
        )
```

Then APPEND a new class at the end of the file:

```python
class TestShouldResetFrameComposition:
    """Composition rule: a widget with both Typewriter (wants
    restart) and RainbowChaseBorder (wants continuous) gets the
    continuous semantics. ANY opt-out wins over restart. Niche
    combo; tradeoff documented in CLAUDE.md."""

    def test_typewriter_plus_continuous_border_skips_reset(self):
        from led_ticker.ticker import _should_reset_frame

        class _Typewriter:
            restart_on_visit = True

        class _ContinuousBorder:
            restart_on_visit = False

        class _Widget:
            animation = _Typewriter()
            border = _ContinuousBorder()

        # Border's opt-out wins; reset is blocked.
        assert _should_reset_frame(_Widget()) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestShowOneResetsFrame::test_show_one_skips_reset_when_border_is_continuous tests/test_ticker_display.py::TestShouldResetFrameComposition -v`

Expected: FAIL — `_show_one` currently calls `reset_frame()` unconditionally, so `test_show_one_skips_reset_when_border_is_continuous` fails on `assert not widget.reset_called`. The composition test passes (it tests the helper, which already works from Task 1).

- [ ] **Step 3: Wire the helper into `_show_one`**

In `src/led_ticker/ticker.py`, lines 729-730 currently read:

```python
    if hasattr(widget, "reset_frame"):
        widget.reset_frame()
```

Replace with:

```python
    if hasattr(widget, "reset_frame") and _should_reset_frame(widget):
        widget.reset_frame()
```

- [ ] **Step 4: Run integration tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py::TestShowOneResetsFrame tests/test_ticker_display.py::TestShouldResetFrameComposition -v`

Expected: PASS — original 2 tests in `TestShowOneResetsFrame` still pass (they don't have continuous-phase effects, so the gate returns True). The 2 new tests pass (continuous border blocks reset; typewriter still triggers reset). Composition test passes.

- [ ] **Step 5: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green. Note: any existing test that builds a widget with a `Rainbow`/`ColorCycle`/`RainbowChaseBorder` instance and expects the frame counter to be reset on `_show_one` entry will now fail — Task 3 has not yet set the `restart_on_visit = False` class attribute. If a test fails here, escalate to the controller; the spec assumed no existing tests depend on that behavior.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "visit-reset: gate _show_one's reset_frame on _should_reset_frame()"
```

---

### Task 3: Per-effect `restart_on_visit` defaults + tripwire pins

**Files:**
- Modify: `src/led_ticker/color_providers.py` (Rainbow class line 83-91, ColorCycle class line 104-111)
- Modify: `src/led_ticker/borders.py` (RainbowChaseBorder class line 120-150, near the `frame_invariant` property)
- Test: `tests/test_color_providers.py` (new attr-pin tests)
- Test: `tests/test_borders.py` (new attr-pin test)

Set `restart_on_visit = False` as a class attribute on the three continuous-phase effects. Add 3 tripwire tests pinning the values — catches a future regression that flips a default silently.

- [ ] **Step 1: Write the failing tripwire tests**

In `tests/test_color_providers.py`, add (placement: near other class-attribute pins on these classes; if no such block exists, append at the end of the file):

```python
class TestContinuousProviderRestartOnVisit:
    """Pin the `restart_on_visit = False` class attribute on
    continuous-phase color providers. Read by `_should_reset_frame`
    in ticker.py. Catches a future change that flips the default."""

    def test_rainbow_restart_on_visit_is_false(self):
        from led_ticker.color_providers import Rainbow

        assert Rainbow.restart_on_visit is False, (
            "Rainbow.restart_on_visit must be False — the chase "
            "phase should advance continuously across loop_count "
            "boundaries within a section"
        )

    def test_color_cycle_restart_on_visit_is_false(self):
        from led_ticker.color_providers import ColorCycle

        assert ColorCycle.restart_on_visit is False, (
            "ColorCycle.restart_on_visit must be False — the cycle "
            "should advance continuously across loop_count boundaries"
        )
```

In `tests/test_borders.py`, add:

```python
class TestRainbowChaseBorderRestartOnVisit:
    """Pin `RainbowChaseBorder.restart_on_visit = False`. Read by
    `_should_reset_frame` in ticker.py. Catches a future change
    that flips the default."""

    def test_rainbow_chase_border_restart_on_visit_is_false(self):
        from led_ticker.borders import RainbowChaseBorder

        assert RainbowChaseBorder.restart_on_visit is False, (
            "RainbowChaseBorder.restart_on_visit must be False — "
            "the perimeter chase should advance continuously across "
            "loop_count boundaries within a section"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_color_providers.py::TestContinuousProviderRestartOnVisit tests/test_borders.py::TestRainbowChaseBorderRestartOnVisit -v`

Expected: FAIL with `AttributeError: type object 'Rainbow' has no attribute 'restart_on_visit'` (and similar for the others).

- [ ] **Step 3: Add the class attribute to Rainbow**

In `src/led_ticker/color_providers.py`, locate the `Rainbow` class (starts at line ~83). Find the existing class-level attributes:

```python
class Rainbow:
    """..."""
    per_char: bool = True
    frame_invariant: bool = False
```

Add `restart_on_visit` directly below `frame_invariant`:

```python
class Rainbow:
    """..."""
    per_char: bool = True
    frame_invariant: bool = False
    restart_on_visit: bool = False  # continuous hue sweep across loop_count boundaries
```

- [ ] **Step 4: Add the class attribute to ColorCycle**

In `src/led_ticker/color_providers.py`, locate the `ColorCycle` class (starts at line ~104). Add `restart_on_visit` directly below the existing `frame_invariant` attribute:

```python
class ColorCycle:
    """..."""
    per_char: bool = False
    frame_invariant: bool = False
    restart_on_visit: bool = False  # continuous cycle across loop_count boundaries
```

- [ ] **Step 5: Add the class attribute to RainbowChaseBorder**

In `src/led_ticker/borders.py`, locate the `RainbowChaseBorder` class (starts at line ~120). The class has a `frame_invariant` defined as a `@property` (line ~157 in the existing file) and constructor-set fields (`speed`, `char_offset`, `thickness`). Add `restart_on_visit` as a class-level attribute (NOT a property) right above `__init__`:

```python
class RainbowChaseBorder:
    """..."""

    # Continuous chase: phase advances across loop_count boundaries
    # within a section. See `_should_reset_frame` in ticker.py.
    restart_on_visit: bool = False

    def __init__(
        self,
        speed: int = 4,
        char_offset: int = 6,
        thickness: int = 1,
    ) -> None:
        ...
```

- [ ] **Step 6: Run the tripwire tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_color_providers.py::TestContinuousProviderRestartOnVisit tests/test_borders.py::TestRainbowChaseBorderRestartOnVisit -v`

Expected: PASS (3 tests).

- [ ] **Step 7: Run full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green. Now `_show_one`'s gate has effects to actually act on — any test that constructs a widget with a `Rainbow` / `ColorCycle` / `RainbowChaseBorder` instance and expects `_frame_count` to be reset on visit entry will now fail. If such a failure surfaces, audit the test: the new behavior is correct; the test's expectation is what needs updating.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/color_providers.py src/led_ticker/borders.py tests/test_color_providers.py tests/test_borders.py
git commit -m "visit-reset: opt out continuous-phase effects (Rainbow / ColorCycle / RainbowChaseBorder)"
```

---

### Task 4: Documentation updates

**Files:**
- Modify: `CLAUDE.md` (the Rainbow border section currently containing the visit-reset hedge)
- Modify: `src/led_ticker/borders.py` (module docstring at top)
- Modify: `src/led_ticker/color_providers.py` (module docstring at top)

Replace the visit-reset hedge in CLAUDE.md with the new behavior. Add short pointers to the convention in the two effect-class modules.

- [ ] **Step 1: Update CLAUDE.md**

In `CLAUDE.md`, locate the paragraph that begins:

```
`_FrameAware`, so transitions freeze the chase via `pause_frame`
and visit-resets restart it cleanly. Visit-reset gotcha: `_show_one`
also calls `reset_frame()` at every `loop_count > 1` iteration of a
single-widget section (correct for typewriter restart semantics, but
visibly snaps the chase phase back to 0 mid-section). Workaround
when configuring an animated border: set `loop_count = 1` and
multiply the inner loop count instead (e.g. `gif_loops = 9` instead
of `loop_count = 3` × `gif_loops = 3`). Smoke config §5 documents
this in-tree.
```

Replace with:

```
`_FrameAware`, so transitions freeze the chase via `pause_frame`
and visit-resets restart it cleanly when needed. Continuous-phase
effects (`Rainbow`, `ColorCycle`, `RainbowChaseBorder`) opt out of
visit-reset by setting `restart_on_visit = False` as a class
attribute — `_show_one._should_reset_frame` checks the widget's
effects and skips the reset if any is opted out. Their phase
advances continuously across `loop_count > 1` iterations within a
section. Section transitions still reset (via `run_transition`'s
`_reset_presenter`), so entry-to-section is always fresh state.
Composition rule: a widget with both a continuous effect and a
restart-on-visit effect (e.g. typewriter + rainbow border) gets
the continuous semantics — typewriter won't retype on inner loop
iterations. Niche combo; if you need typewriter to retype on a
bordered widget, drop the border or use a different framing.
```

- [ ] **Step 2: Update `borders.py` module docstring**

In `src/led_ticker/borders.py`, near the top of the docstring (after the existing `frame_invariant` documentation), add a paragraph:

```
**`restart_on_visit` convention**: effect classes that want
continuous phase across `loop_count > 1` iterations of a section
set `restart_on_visit: bool = False` as a class attribute. Read
by `_should_reset_frame` in `ticker.py`. Default `True` (via
`getattr` fallback) keeps today's "every visit = fresh start"
behavior for unknown effect classes. `RainbowChaseBorder` opts
out (continuous chase); `ConstantBorder` keeps the default
(frame-invariant, so the value is a no-op).
```

- [ ] **Step 3: Update `color_providers.py` module docstring**

In `src/led_ticker/color_providers.py`, near the top of the docstring (after the existing `frame_invariant` documentation), add a paragraph:

```
**`restart_on_visit` convention**: providers that want continuous
phase across `loop_count > 1` iterations of a section set
`restart_on_visit: bool = False` as a class attribute. Read by
`_should_reset_frame` in `ticker.py`. Default `True` (via
`getattr` fallback) keeps today's "every visit = fresh start"
behavior for unknown provider classes. `Rainbow` and `ColorCycle`
opt out (continuous sweep / cycle); the others keep the default
(frame-invariant or visit-driven re-roll).
```

- [ ] **Step 4: Verify docs read correctly**

Run: `grep -n "restart_on_visit" CLAUDE.md src/led_ticker/borders.py src/led_ticker/color_providers.py`

Expected: at least 4 matches across the 3 files (CLAUDE.md, borders.py module docstring, color_providers.py module docstring, and the existing class attribute set in Task 3).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md src/led_ticker/borders.py src/led_ticker/color_providers.py
git commit -m "visit-reset: docs — restart_on_visit convention in CLAUDE.md + module docstrings"
```

---

### Task 5: Smoke config revert

**Files:**
- Modify: `config/config.rainbow_border_test.example.toml` (§4, §5, §7)

Revert the workaround on the three gif sections — they were collapsed to `loop_count = 1 × gif_loops = 9` to dodge the chase-restart artifact. With the fix in place they can go back to `loop_count = 3 × gif_loops = 3`, exercising the actual fix on hardware. Remove §5's inline workaround comment.

- [ ] **Step 1: Revert §4**

In `config/config.rainbow_border_test.example.toml`, locate §4 (search for `# 4. GIF + rainbow border, no text`). The section currently reads:

```toml
[[playlist.section]]
mode = "swap"
hold_time = 7.0
loop_count = 1
transition = "cut"

[[playlist.section.widget]]
type = "gif"
path = "assets/pika_wave_transparent.gif"
fit = "pillarbox"
image_align = "center"
gif_loops = 9
border = "rainbow"
```

Change `loop_count = 1` → `loop_count = 3` and `gif_loops = 9` → `gif_loops = 3`:

```toml
[[playlist.section]]
mode = "swap"
hold_time = 7.0
loop_count = 3
transition = "cut"

[[playlist.section.widget]]
type = "gif"
path = "assets/pika_wave_transparent.gif"
fit = "pillarbox"
image_align = "center"
gif_loops = 3
border = "rainbow"
```

- [ ] **Step 2: Revert §5 + remove the workaround comment**

In `config/config.rainbow_border_test.example.toml`, locate §5 (search for `# 5. GIF + rainbow border + held text`). The section header currently includes the workaround paragraph:

```
# 5. GIF + rainbow border + held text — `_render_tick` non-scroll path
#    on a multi-frame source. Tests the per-tick loop (gif frames
#    advance, border chases, text holds at left). Border paints
#    AFTER image AND BEFORE text — text overlaps border on collision.
#    NB: section uses `loop_count = 1` and `gif_loops = 9` (instead of
#    `loop_count = 3` × `gif_loops = 3`) to avoid `_show_one`'s
#    visit-entry `reset_frame()` mid-section — that reset is correct
#    for typewriter / new-section semantics but visibly snaps the
#    rainbow chase back to phase 0 at every loop_count boundary.
# ---------------------------------------------------------------------------
[[playlist.section]]
mode = "swap"
hold_time = 7.0
loop_count = 1
transition = "cut"

[[playlist.section.widget]]
type = "gif"
path = "assets/pika_wave_transparent.gif"
fit = "pillarbox"
image_align = "left"
text = "PIKA"
text_align = "right"
font = "Inter-Bold"
font_size = 16
font_color = [255, 220, 80]
gif_loops = 9
border = "rainbow"
```

Replace with the workaround paragraph removed and the loop counts reverted:

```
# 5. GIF + rainbow border + held text — `_render_tick` non-scroll path
#    on a multi-frame source. Tests the per-tick loop (gif frames
#    advance, border chases, text holds at left). Border paints
#    AFTER image AND BEFORE text — text overlaps border on collision.
#    `loop_count = 3` × `gif_loops = 3` exercises the visit-reset
#    fix: the rainbow chase phase MUST advance continuously across
#    the 3 inner loop iterations (no snap back to phase 0).
# ---------------------------------------------------------------------------
[[playlist.section]]
mode = "swap"
hold_time = 7.0
loop_count = 3
transition = "cut"

[[playlist.section.widget]]
type = "gif"
path = "assets/pika_wave_transparent.gif"
fit = "pillarbox"
image_align = "left"
text = "PIKA"
text_align = "right"
font = "Inter-Bold"
font_size = 16
font_color = [255, 220, 80]
gif_loops = 3
border = "rainbow"
```

- [ ] **Step 3: Revert §7**

In `config/config.rainbow_border_test.example.toml`, locate §7 (search for `# 7. GIF + rainbow border + COLOR_CYCLE held text`). Change `loop_count = 1` → `loop_count = 3` and `gif_loops = 9` → `gif_loops = 3`:

Find:
```toml
[[playlist.section]]
mode = "swap"
hold_time = 7.0
loop_count = 1
transition = "cut"

[[playlist.section.widget]]
type = "gif"
path = "assets/pika_wave_transparent.gif"
fit = "pillarbox"
image_align = "left"
text = "CYCLE"
text_align = "right"
font = "Inter-Bold"
font_size = 16
font_color = "color_cycle"
gif_loops = 9
border = "rainbow"
```

Replace with:
```toml
[[playlist.section]]
mode = "swap"
hold_time = 7.0
loop_count = 3
transition = "cut"

[[playlist.section.widget]]
type = "gif"
path = "assets/pika_wave_transparent.gif"
fit = "pillarbox"
image_align = "left"
text = "CYCLE"
text_align = "right"
font = "Inter-Bold"
font_size = 16
font_color = "color_cycle"
gif_loops = 3
border = "rainbow"
```

- [ ] **Step 4: Verify the config still parses**

Run: `PYTHONPATH=tests/stubs uv run python -c "
from led_ticker.config import load_config
from pathlib import Path
cfg = load_config(Path('config/config.rainbow_border_test.example.toml'))
for i, s in enumerate(cfg.sections, 1):
    if s.widgets[0]['type'] == 'gif':
        w = s.widgets[0]
        print(f'  §{i}: loop_count={s.loop_count} gif_loops={w.get(\"gif_loops\")} text={w.get(\"text\", \"<none>\")!r}')
"`

Expected output:
```
  §4: loop_count=3 gif_loops=3 text='<none>'
  §5: loop_count=3 gif_loops=3 text='PIKA'
  §7: loop_count=3 gif_loops=3 text='CYCLE'
```

- [ ] **Step 5: Run full suite for regression check**

Run: `PYTHONPATH=tests/stubs uv run pytest -x -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add config/config.rainbow_border_test.example.toml
git commit -m "smoke: revert rainbow-border §4/§5/§7 to loop_count = 3 — exercise the visit-reset fix"
```

---

### Final task: lint + push + open PR

- [ ] **Step 1: Run lint**

```bash
uv run ruff check src/led_ticker tests
```

Expected: All checks passed!

- [ ] **Step 2: Run full test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -x -q
```

Expected: all tests pass (current count + 11 new tests added by this plan: 5 in TestShouldResetFrame + 2 augmenting TestShowOneResetsFrame + 1 in TestShouldResetFrameComposition + 2 in TestContinuousProviderRestartOnVisit + 1 in TestRainbowChaseBorderRestartOnVisit).

- [ ] **Step 3: Push the branch**

```bash
git push -u origin feat/visit-reset
```

- [ ] **Step 4: Open the PR**

```bash
gh pr create --title "visit-reset: continuous-phase effects opt out of loop_count reset" \
  --body "$(cat <<'EOF'
## Summary

Stops animated chases (`RainbowChaseBorder`, `Rainbow`, `ColorCycle`)
from snapping their phase to 0 at every `loop_count > 1` iteration
of a single-widget section. Hardware-observed on §5 of the rainbow
border smoke (PIKA gif). Mitigated in PR #10 via a smoke-config
workaround; this PR is the principled fix.

## Behavior change

`_show_one` in `ticker.py` no longer unconditionally calls
`widget.reset_frame()` on entry. The new `_should_reset_frame()`
gate inspects the widget's effects (`font_color`, `top_color`,
`bottom_color`, `border`, `animation`) and skips the reset if ANY
effect has `restart_on_visit = False` set as a class attribute.

**Continuous-phase effects opt out** (set `restart_on_visit = False`):
- `Rainbow` (color_providers.py)
- `ColorCycle` (color_providers.py)
- `RainbowChaseBorder` (borders.py)

**Restart-on-visit effects keep the default** (no change):
- `Typewriter` — re-types each loop (per spec Q1 answer)
- `Random` — re-rolls on each visit
- All frame-invariant effects (`_ConstantColor`, `Gradient`,
  `ConstantBorder`) — value is a no-op visually

## Section entry is unchanged

`run_transition._reset_presenter` already resets `_frame_count` on
every transition boundary (`transitions/__init__.py:184`). This
PR only affects the inner-loop-iteration path inside `_show_one`.
First section of a fresh playlist run gets `_frame_count = 0`
naturally from `_FrameAware`'s default.

## Composition tradeoff

A widget with both a continuous effect and a restart-on-visit
effect (e.g. typewriter + rainbow border) gets the continuous
semantics — typewriter doesn't retype on inner loop iterations.
Niche combo; documented in CLAUDE.md.

## Test coverage (11 new tests)

- `TestShouldResetFrame` (5) — gate function across no-effects /
  continuous-color-provider / continuous-border / typewriter / unknown-effect
- `TestShowOneResetsFrame` (2 new, augmenting existing class) —
  integration: continuous border blocks reset; typewriter still resets
- `TestShouldResetFrameComposition` (1) — typewriter + continuous border
  → continuous wins
- `TestContinuousProviderRestartOnVisit` (2) — class-attr pins
- `TestRainbowChaseBorderRestartOnVisit` (1) — class-attr pin

## Smoke config revert

`config.rainbow_border_test.example.toml` §4 / §5 / §7 reverted from
the workaround `loop_count = 1 × gif_loops = 9` back to the original
intent `loop_count = 3 × gif_loops = 3`. Hardware verification:
chase phase MUST advance continuously across the 3 inner loops on
each section.

## Spec

[`docs/superpowers/specs/2026-05-07-visit-reset-design.md`](https://github.com/JamesAwesome/led-ticker/blob/feat/visit-reset/docs/superpowers/specs/2026-05-07-visit-reset-design.md)

## Test plan

- [x] Full suite green (existing + 9 new)
- [x] Lint clean
- [x] Pyright clean (no new typing surface)
- [ ] **Hardware verify on bigsign**: §4/§5/§7 of the rainbow border
      smoke now exercise `loop_count = 3` — chase MUST advance
      continuously across all 3 inner loops with no phase snap-back.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL returned.

---

## Summary of files touched

| Path | Change |
|---|---|
| `src/led_ticker/ticker.py` | +`_should_reset_frame` helper, +1 `and` term in `_show_one` |
| `src/led_ticker/color_providers.py` | +1 line on `Rainbow`, +1 line on `ColorCycle`, +module docstring paragraph |
| `src/led_ticker/borders.py` | +1 line on `RainbowChaseBorder`, +module docstring paragraph |
| `tests/test_ticker_display.py` | +`TestShouldResetFrame` (5 tests), +2 tests in `TestShowOneResetsFrame`, +`TestShouldResetFrameComposition` (1 test) |
| `tests/test_color_providers.py` | +`TestContinuousProviderRestartOnVisit` (2 tests) |
| `tests/test_borders.py` | +`TestRainbowChaseBorderRestartOnVisit` (1 test) |
| `CLAUDE.md` | Replaces the visit-reset hedge paragraph |
| `config/config.rainbow_border_test.example.toml` | §4/§5/§7 revert |

Total: 8 files, 11 new tests, single-PR scope.

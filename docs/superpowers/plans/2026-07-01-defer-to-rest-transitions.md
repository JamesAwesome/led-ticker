# Defer-to-Rest Transition Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a widget's hold expires, extend it by up to ~1 s so animated effects (Shimmer sweep, Typewriter reveal) land at a natural rest point before the transition fires, instead of being visually chopped mid-animation (issue #305).

**Architecture:** Compute-once `frames_to_rest(frame, total_chars) -> int` on effects (`ColorProviderBase` default 0; `Shimmer` and `Typewriter` override), aggregated by `FrameAwareBase.frames_to_transition_ready()` (max across effects, per-effect-kind char counts, never raises), consumed by ONE settle site in `ticker.py:_swap_and_scroll` that reuses the existing `_hold_ticks` loop with an all-or-nothing ~1 s cap. Plus validate rule 61 warning when a typewriter's typing duration exceeds its effective hold.

**Tech Stack:** Python 3.14, attrs, pytest (stubs in `tests/stubs` are on the pytest path automatically), ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-07-01-defer-to-rest-transitions-design.md` (read it if a requirement here seems ambiguous — the spec governs).

## Global Constraints

- Work on the feature branch ONLY. Run `git branch --show-current` first; abort if it prints `main`.
- No `from __future__ import annotations` anywhere (project-wide rule, PEP 649).
- Lazy imports inside functions need `# noqa: PLC0415` (existing codebase convention).
- The words "sanity"/"sane" are BANNED repo-wide (`tests/test_no_ableist_language.py` greps the whole tree — it only fails on the FULL suite run, not scoped runs). Use "correctness check" / "quick check". Also avoid "footgun"/gun metaphors — use "Pitfalls" / "Sharp edges".
- `MAX_SETTLE_TICKS = 1000 // ENGINE_TICK_MS` — all-or-nothing: `extra > cap` means NO extension at all.
- Shimmer guard is `pause_frames < 1 -> 0` (NOT `pause == 0`): a sub-frame pause has no landable rest tick.
- Typewriter char count is RAW `len(full_text)` (emoji `:slug:` characters included); color-provider char counts use the draw-path anchor (`count_text_chars` on the emoji path, else `len`). Never share one number across effect kinds.
- Readiness code must NEVER raise into the render loop: `FrameAwareBase.frames_to_transition_ready` catches everything → 0, and the engine call site is defensive again (duck-typed getattr + try/except → 0).
- Before EVERY commit: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/`. Run `uv run --extra dev pyright src/` at least once per task (the pre-push hook enforces it).
- Final verification is the FULL `make test` (meta-tripwires like the AST redraw contract and the ableist-language scan only fire on the full suite).

---

### Task 1: `constants.py` leaf module — relocate `ENGINE_TICK_MS`

`ENGINE_TICK_MS` currently lives at the BOTTOM of `src/led_ticker/ticker.py` (line ~1221: `ENGINE_TICK_MS: int = 50  # 20 fps for held-text frame animation`). Later tasks need it from `animations.py` and `validate.py` without importing the engine. Move it to a new leaf module; `ticker.py` re-exports it so the six existing `from led_ticker.ticker import ENGINE_TICK_MS` importers (`widgets/gif.py`, `widgets/still.py`, `animations.py` docstrings, tests, `tools/gif_plan`) keep working.

**Files:**
- Create: `src/led_ticker/constants.py`
- Modify: `src/led_ticker/ticker.py` (delete the bottom-of-file definition; add a top-of-file import)
- Test: `tests/test_constants.py`

**Interfaces:**
- Produces: `led_ticker.constants.ENGINE_TICK_MS: int` (= 50) — Tasks 3, 5, 6 import it. `from led_ticker.ticker import ENGINE_TICK_MS` must still work (back-compat re-export).

- [ ] **Step 1: Write the failing test**

Create `tests/test_constants.py`:

```python
"""ENGINE_TICK_MS lives in the constants leaf module; ticker.py re-exports
it for back-compat. Guards the defer-to-rest layering: validate.py and
animations.py import the leaf, never the engine."""


def test_constants_module_defines_engine_tick_ms() -> None:
    from led_ticker.constants import ENGINE_TICK_MS

    assert ENGINE_TICK_MS == 50


def test_ticker_reexports_engine_tick_ms() -> None:
    """Back-compat: existing importers use `from led_ticker.ticker import
    ENGINE_TICK_MS` — the re-export must stay."""
    from led_ticker import constants, ticker

    assert ticker.ENGINE_TICK_MS is constants.ENGINE_TICK_MS


def test_constants_is_a_leaf_module() -> None:
    """constants.py must not import anything from led_ticker (leaf-module
    contract — validate.py depends on this staying import-light)."""
    import ast
    from pathlib import Path

    src = Path("src/led_ticker/constants.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom | ast.Import):
            names = (
                [node.module]
                if isinstance(node, ast.ImportFrom)
                else [a.name for a in node.names]
            )
            for name in names:
                assert not (name or "").startswith("led_ticker"), (
                    f"constants.py imports {name} — it must stay a leaf"
                )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_constants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.constants'`

- [ ] **Step 3: Create the constants module and rewire ticker.py**

Create `src/led_ticker/constants.py`:

```python
"""Leaf module for engine-wide constants.

Import-light by contract (no led_ticker imports): `validate.py` (static
config preflight) and `animations.py` import from here without pulling in
the engine. `ticker.py` re-exports ENGINE_TICK_MS for back-compat with
existing `from led_ticker.ticker import ENGINE_TICK_MS` call sites.
"""

ENGINE_TICK_MS: int = 50  # 20 fps for held-text frame animation
```

In `src/led_ticker/ticker.py`:
1. DELETE the bottom-of-file line `ENGINE_TICK_MS: int = 50  # 20 fps for held-text frame animation` (search for it; ~line 1221).
2. ADD to the import block at the top (alphabetical among the `from led_ticker...` imports, i.e. after `from led_ticker.colors import RGB_WHITE`):

```python
from led_ticker.constants import ENGINE_TICK_MS
```

Do NOT touch any other file — the re-export keeps all existing importers working.

- [ ] **Step 4: Run tests to verify pass + no fallout**

Run: `uv run --extra dev pytest tests/test_constants.py tests/test_ticker_display.py tests/test_widgets/test_gif.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint, format, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
git add src/led_ticker/constants.py src/led_ticker/ticker.py tests/test_constants.py
git commit -m "refactor: relocate ENGINE_TICK_MS to a constants leaf module

ticker.py re-exports it for back-compat. Prepares the defer-to-rest
feature (#305): validate.py and animations.py need the tick constant
without importing the engine."
```

---

### Task 2: `frames_to_rest` on `ColorProviderBase` + `Shimmer`

**Files:**
- Modify: `src/led_ticker/color_providers.py` (`ColorProviderBase` ~line 39; `Shimmer` ~line 212)
- Test: `tests/test_frames_to_rest.py` (create)

**Interfaces:**
- Produces: `ColorProviderBase.frames_to_rest(frame: int, total_chars: int) -> int` (default `0`); `Shimmer.frames_to_rest(...)` override; `Shimmer._cycle_geometry(total_chars) -> tuple[float, float]` (private, `(sweep_frames, cycle_frames)`). Task 4 duck-types `frames_to_rest` on effect instances.
- NOTE: `ColorProvider` (line ~64) is a `typing.Protocol` — the default goes on **`ColorProviderBase`** (line ~39), the class every shipped provider actually inherits. Do not add it to the Protocol.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_frames_to_rest.py`:

```python
"""frames_to_rest seam: providers report frames until their next natural
rest point (0 = at rest / no rest concept). Spec:
docs/superpowers/specs/2026-07-01-defer-to-rest-transitions-design.md
"""

import math

import pytest

from led_ticker.color_providers import (
    ColorCycle,
    Gradient,
    Rainbow,
    Random,
    Shimmer,
    _ConstantColor,
    _SHIMMER_FPS,
)
from led_ticker.colors import RGB_WHITE, RGB_BLUE


def _shimmer(pause: float = 0.5, speed: float = 14.0) -> Shimmer:
    return Shimmer(RGB_WHITE, RGB_BLUE, speed=speed, pause=pause)


class TestShimmerFramesToRest:
    def test_mid_sweep_returns_exact_remaining(self) -> None:
        s = _shimmer()
        chars = 20
        sweep = chars / s.speed * _SHIMMER_FPS
        # frame 10 is mid-sweep (sweep ≈ 42.9 frames)
        assert s.frames_to_rest(10, chars) == math.ceil(sweep - 10)

    def test_pause_window_returns_zero(self) -> None:
        s = _shimmer(pause=1.0)
        chars = 20
        sweep = chars / s.speed * _SHIMMER_FPS
        cycle = sweep + 1.0 * _SHIMMER_FPS
        # every integer frame inside [sweep, cycle) is at rest
        for frame in range(math.ceil(sweep), math.floor(cycle)):
            assert s.frames_to_rest(frame, chars) == 0, f"frame {frame}"

    def test_wraparound_beyond_one_cycle(self) -> None:
        s = _shimmer(pause=1.0)
        chars = 20
        sweep = chars / s.speed * _SHIMMER_FPS
        cycle = sweep + 1.0 * _SHIMMER_FPS
        frame = math.floor(cycle) + 10  # 10 frames into the SECOND sweep
        t = float(frame) % cycle
        assert s.frames_to_rest(frame, chars) == math.ceil(sweep - t)

    def test_zero_pause_never_defers(self) -> None:
        s = _shimmer(pause=0.0)
        for frame in range(0, 200, 7):
            assert s.frames_to_rest(frame, 20) == 0

    def test_subframe_pause_never_defers(self) -> None:
        """pause=0.02 -> pause_frames=0.6 < 1: no landable rest tick
        exists; advancing would overshoot into the next sweep."""
        s = _shimmer(pause=0.02)
        for frame in range(0, 200, 7):
            assert s.frames_to_rest(frame, 20) == 0

    @pytest.mark.parametrize("frame", list(range(0, 120, 3)))
    @pytest.mark.parametrize("chars", [5, 20, 61])
    def test_advancing_by_result_lands_in_pause(self, frame: int, chars: int) -> None:
        """Property: advancing by frames_to_rest always lands inside the
        pause window. pause=0.5 -> pause_frames=15 >= 1, so a landable
        rest tick always exists: delta == 0 must mean we're ALREADY in
        the pause, and delta > 0 must land in it."""
        s = _shimmer(pause=0.5)
        delta = s.frames_to_rest(frame, chars)
        sweep = chars / s.speed * _SHIMMER_FPS
        cycle = sweep + 0.5 * _SHIMMER_FPS
        if delta == 0:
            t = float(frame) % cycle
            assert t >= sweep, f"frame={frame}: delta=0 but mid-sweep (t={t})"
        else:
            landed_t = float(frame + delta) % cycle
            assert landed_t >= sweep, (
                f"frame={frame} delta={delta} landed_t={landed_t} sweep={sweep}"
            )

    def test_color_for_and_frames_to_rest_agree_on_geometry(self) -> None:
        """The pause window frames_to_rest reports must be exactly where
        color_for returns base for every char (the flat rest state)."""
        s = _shimmer(pause=1.0)
        chars = 10
        for frame in range(0, 150):
            at_rest = s.frames_to_rest(frame, chars) == 0
            sweep = chars / s.speed * _SHIMMER_FPS
            cycle = sweep + 1.0 * _SHIMMER_FPS
            in_pause = (float(frame) % cycle) >= sweep
            if in_pause:
                assert at_rest, f"frame {frame}: in pause but not at rest"


class TestProviderDefaults:
    @pytest.mark.parametrize(
        "provider",
        [
            _ConstantColor(RGB_WHITE),
            Random(),
            Gradient(RGB_WHITE, RGB_BLUE),
            Rainbow(),
            ColorCycle(),
        ],
        ids=["constant", "random", "gradient", "rainbow", "color_cycle"],
    )
    def test_default_never_defers(self, provider) -> None:
        for frame in (0, 17, 500):
            assert provider.frames_to_rest(frame, 20) == 0
```

NOTE for the implementer: check the actual constructor signatures of `Random`, `Gradient`, `Rainbow`, `ColorCycle` in `src/led_ticker/color_providers.py` before running — adjust the parametrize instantiations to match (e.g. `Gradient` may take colors positionally or by keyword). The assertion body must not change.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_frames_to_rest.py -v`
Expected: FAIL — `AttributeError: 'Shimmer' object has no attribute 'frames_to_rest'` (and same for the defaults).

- [ ] **Step 3: Implement**

In `src/led_ticker/color_providers.py`:

(a) On `ColorProviderBase` (the class at ~line 39 — NOT the `ColorProvider` Protocol), add:

```python
    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        """Frames until this effect reaches a natural rest point.

        0 = at rest now, or no rest concept (never defers a transition).
        The engine consults this at the hold→transition handoff and may
        extend the hold by up to ~1 s (MAX_SETTLE_TICKS) so the
        transition lands on a visually flat state instead of mid-sweep.
        Continuously-cycling providers (Rainbow, ColorCycle) keep this
        default — they have no rest point and must never stall the
        rotation.
        """
        return 0
```

(b) On `Shimmer`, factor the geometry OUT of `color_for` into one helper, and add the override. Replace the three geometry lines inside `color_for` (`sweep_frames = ...`, `pause_frames = ...`, `cycle_frames = ...`) so both methods share one source:

```python
    def _cycle_geometry(self, total_chars: int) -> tuple[float, float]:
        """(sweep_frames, cycle_frames) — the single source of cycle math
        for BOTH color_for and frames_to_rest, so the two can't drift."""
        chars = max(total_chars, 1)
        sweep_frames = chars / self.speed * _SHIMMER_FPS
        cycle_frames = sweep_frames + self.pause * _SHIMMER_FPS
        return sweep_frames, cycle_frames

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        """Frames until the sweep reaches its pause window.

        A sub-frame pause (pause_frames < 1, including pause=0) has no
        landable rest tick — advancing by ceil(sweep - t) would land in
        [sweep, sweep+1), which only sits inside the pause when the pause
        is at least one frame wide. Return 0 in that case (never defer).
        """
        sweep_frames, cycle_frames = self._cycle_geometry(total_chars)
        pause_frames = cycle_frames - sweep_frames
        if pause_frames < 1:
            return 0
        t = float(frame) % cycle_frames
        if t >= sweep_frames:
            return 0
        return math.ceil(sweep_frames - t)
```

And rewrite the top of `color_for` to use the helper (behavior-identical):

```python
    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        from led_ticker._compat import require_graphics  # noqa: PLC0415

        graphics = require_graphics()
        chars = max(total_chars, 1)
        sweep_frames, cycle_frames = self._cycle_geometry(total_chars)

        t = float(frame) % cycle_frames

        if t >= sweep_frames:
            return self._base
        ...  # rest of the method unchanged (center/d/half_width/factor)
```

(`math` is already imported at module top — verify; add if not.)

- [ ] **Step 4: Run tests to verify they pass (plus provider regression)**

Run: `uv run --extra dev pytest tests/test_frames_to_rest.py tests/test_color_providers.py -q`
Expected: all PASS (find the actual color-provider test file name with `ls tests/ | grep -i color` and include it).

- [ ] **Step 5: Lint, format, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
git add src/led_ticker/color_providers.py tests/test_frames_to_rest.py
git commit -m "feat(providers): frames_to_rest seam — ColorProviderBase default + Shimmer

Shimmer geometry factored into _cycle_geometry (single source for
color_for + frames_to_rest). Sub-frame pauses (pause_frames < 1) report
0 — no landable rest tick exists. Part of #305."
```

---

### Task 3: `Typewriter.frames_to_rest` + shared typing-duration helper

**Files:**
- Modify: `src/led_ticker/animations.py`
- Test: `tests/test_frames_to_rest.py` (extend — file exists after Task 2)

**Interfaces:**
- Consumes: `led_ticker.constants.ENGINE_TICK_MS` (Task 1).
- Produces: `Typewriter.frames_to_rest(frame: int, total_chars: int) -> int`; `Typewriter.typing_duration_seconds(total_chars: int) -> float` — Task 6's validate rule calls the latter (the ONLY home of the typing-duration formula; validate must never re-implement it).
- CRITICAL: `total_chars` here is the RAW `len(full_text)` (emoji `:slug:` characters INCLUDED) — `Typewriter.frame_for` slices `full_text[:chars_visible]` against `len(full_text)` (animations.py:73-75), so the rest math must use the same length. This is a DIFFERENT quantity from color providers' `count_text_chars`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_frames_to_rest.py`:

```python
from led_ticker.animations import Typewriter
from led_ticker.constants import ENGINE_TICK_MS


class TestTypewriterFramesToRest:
    def test_mid_type_exact_remaining(self) -> None:
        tw = Typewriter()  # frames_per_char=3, chars_per_frame=1
        total = 10
        # done at frame 3 * (ceil(10/1) - 1) = 27
        assert tw.frames_to_rest(0, total) == 27
        assert tw.frames_to_rest(20, total) == 7
        assert tw.frames_to_rest(27, total) == 0

    def test_done_stays_zero_forever(self) -> None:
        tw = Typewriter()
        for frame in (27, 28, 100, 10_000):
            assert tw.frames_to_rest(frame, 10) == 0

    def test_done_frame_matches_frame_for_reveal(self) -> None:
        """The frame frames_to_rest declares 'done' is exactly the first
        frame at which frame_for reveals the full text — the two formulas
        must agree."""
        tw = Typewriter(frames_per_char=3)
        text = "HELLO WORLD!!"
        total = len(text)
        done = 3 * (math.ceil(total / 1) - 1)
        assert tw.frame_for(done, text, 160, 80).visible_text == text
        assert tw.frame_for(done - 1, text, 160, 80).visible_text != text
        assert tw.frames_to_rest(done - 1, total) == 1
        assert tw.frames_to_rest(done, total) == 0

    def test_chars_per_frame_above_one(self) -> None:
        tw = Typewriter(chars_per_frame=2, frames_per_char=3)
        total = 10
        # done at 3 * (ceil(10/2) - 1) = 12
        assert tw.frames_to_rest(0, total) == 12
        assert tw.frames_to_rest(12, total) == 0

    def test_emoji_text_uses_raw_length(self) -> None:
        """Guard for Critical finding 1: rest math must consume raw
        len(full_text) INCLUDING :slug: characters. With the raw length
        the reveal is still in progress at the frame where the
        emoji-excluded count would claim done."""
        tw = Typewriter()
        text = "GO :sun: GO"  # len = 11 raw; emoji-excluded count = 6
        raw = len(text)
        wrong_done = 3 * (math.ceil(6 / 1) - 1)  # 15 — the WRONG answer
        assert tw.frames_to_rest(wrong_done, raw) > 0
        right_done = 3 * (math.ceil(raw / 1) - 1)  # 30
        assert tw.frames_to_rest(right_done, raw) == 0

    def test_zero_or_negative_chars(self) -> None:
        tw = Typewriter()
        assert tw.frames_to_rest(0, 0) == 0
        assert tw.frames_to_rest(0, -3) == 0


class TestTypingDurationSeconds:
    def test_matches_frames_to_rest_from_zero(self) -> None:
        """Formula-equality tripwire: the duration helper and
        frames_to_rest must be the same math — validate rule 61 depends
        on this staying true."""
        for total in (1, 7, 10, 40):
            for fpc in (1, 3, 6):
                tw = Typewriter(frames_per_char=fpc)
                expected = tw.frames_to_rest(0, total) * ENGINE_TICK_MS / 1000.0
                assert tw.typing_duration_seconds(total) == pytest.approx(expected)

    def test_forty_chars_at_defaults_is_about_six_seconds(self) -> None:
        tw = Typewriter()
        assert tw.typing_duration_seconds(40) == pytest.approx(
            3 * 39 * ENGINE_TICK_MS / 1000.0
        )  # 5.85 s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_frames_to_rest.py -k "Typewriter or TypingDuration" -v`
Expected: FAIL — `AttributeError: 'Typewriter' object has no attribute 'frames_to_rest'`.

- [ ] **Step 3: Implement**

In `src/led_ticker/animations.py`:

(a) Add imports at the top (module currently imports only `dataclass`/`Protocol`):

```python
import math

from led_ticker.constants import ENGINE_TICK_MS
```

(b) Add to the `Typewriter` class:

```python
    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        """Frames until the reveal completes (one-shot rest: 0 forever
        once fully typed).

        total_chars MUST be the raw ``len(full_text)`` — the same length
        ``frame_for`` slices against — INCLUDING any ``:slug:`` emoji
        characters. The emoji-excluded ``count_text_chars`` is a color-
        provider quantity; feeding it here under-counts and reports done
        mid-type.
        """
        if total_chars <= 0:
            return 0
        done_frame = self.frames_per_char * (
            math.ceil(total_chars / self.chars_per_frame) - 1
        )
        return max(0, done_frame - frame)

    def typing_duration_seconds(self, total_chars: int) -> float:
        """Wall-clock seconds to fully reveal ``total_chars`` raw
        characters at engine cadence. The ONLY home of the typing-
        duration formula — validate rule 61 imports and calls this;
        it must never re-implement the math."""
        return self.frames_to_rest(0, total_chars) * ENGINE_TICK_MS / 1000.0
```

(c) In the `Animation` Protocol docstring, append one line to the "Implementing a new animation" paragraph:

```
    Animations MAY also define ``frames_to_rest(frame, total_chars) -> int``
    (0 = at rest / no rest concept): the engine consults it at the
    hold→transition handoff and can extend the hold up to ~1 s so a
    transition doesn't chop the animation mid-flight.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_frames_to_rest.py tests/test_animations.py -q`
Expected: all PASS (find the actual animation test file with `ls tests/ | grep -i anim`; include whatever exists).

- [ ] **Step 5: Lint, format, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/animations.py
git add src/led_ticker/animations.py tests/test_frames_to_rest.py
git commit -m "feat(animations): Typewriter frames_to_rest + typing_duration_seconds

Rest math consumes RAW len(full_text) (emoji slugs included) to match
frame_for's own reveal length. typing_duration_seconds is the single
home of the duration formula for validate rule 61. Part of #305."
```

---

### Task 4: Widget seam — `FrameAwareBase.frames_to_transition_ready`

**Files:**
- Modify: `src/led_ticker/widgets/_frame_aware.py`; `src/led_ticker/widgets/message.py` (`TickerMessage`); `src/led_ticker/widgets/two_row.py` (`TwoRowMessage`)
- Test: `tests/test_widgets/test_frames_to_transition_ready.py` (create)

**Interfaces:**
- Consumes: `frames_to_rest(frame, total_chars)` duck-typed on effects (Tasks 2-3); `FrameAwareBase._iter_effects()` / `frame_for(attr)` (existing).
- Produces: `FrameAwareBase.frames_to_transition_ready() -> int` (never raises; 0 = ready) and overridable hook `FrameAwareBase._effect_total_chars(attr_name: str) -> int`. Task 5's engine settle calls `frames_to_transition_ready` duck-typed.
- Per-effect-kind counts (Critical finding 1): the `"animation"` attr gets RAW `len(full_text)`; color-provider attrs get the draw-path anchor (`count_text_chars(full_text)` when the text contains emoji, else `len(full_text)`).
- NOTE: `FrameAwareBase` is exported via `led_ticker.plugin` — these are additive plugin-visible surface. Docstrings are the contract; write them carefully.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_widgets/test_frames_to_transition_ready.py`:

```python
"""FrameAwareBase.frames_to_transition_ready: max frames_to_rest across a
widget's animated effects, per-effect-kind char counts, never raises."""

import attrs

from led_ticker.colors import RGB_BLUE, RGB_WHITE
from led_ticker.color_providers import Shimmer
from led_ticker.animations import Typewriter
from led_ticker.widgets._frame_aware import FrameAwareBase
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.two_row import TwoRowMessage


class _StubEffect:
    """Effect stub reporting a fixed frames_to_rest."""

    frame_invariant = False
    restart_on_visit = True

    def __init__(self, remaining: int) -> None:
        self.remaining = remaining
        self.seen_chars: list[int] = []

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        self.seen_chars.append(total_chars)
        return self.remaining


class _RaisingEffect:
    frame_invariant = False
    restart_on_visit = True

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        raise RuntimeError("boom")


@attrs.define
class _Widget(FrameAwareBase):
    text: str = "HELLO WORLD"
    font_color: object = None
    border: object = None
    animation: object = None


class TestFramesToTransitionReady:
    def test_no_effects_returns_zero(self) -> None:
        assert _Widget().frames_to_transition_ready() == 0

    def test_takes_max_across_effects(self) -> None:
        w = _Widget(font_color=_StubEffect(5), animation=_StubEffect(11))
        assert w.frames_to_transition_ready() == 11

    def test_effect_without_method_contributes_zero(self) -> None:
        class _NoRest:
            frame_invariant = True
            restart_on_visit = True

        w = _Widget(font_color=_NoRest(), animation=_StubEffect(4))
        assert w.frames_to_transition_ready() == 4

    def test_raising_effect_returns_zero_never_propagates(self) -> None:
        w = _Widget(font_color=_RaisingEffect(), animation=_StubEffect(9))
        assert w.frames_to_transition_ready() == 0

    def test_uses_per_effect_frame_counter(self) -> None:
        w = _Widget(font_color=_StubEffect(0))
        for _ in range(7):
            w.advance_frame()
        seen_frames: list[int] = []
        orig = w.font_color.frames_to_rest

        def spy(frame: int, total_chars: int) -> int:
            seen_frames.append(frame)
            return orig(frame, total_chars)

        w.font_color.frames_to_rest = spy
        w.frames_to_transition_ready()
        assert seen_frames == [7]


class TestEffectTotalChars:
    def test_ticker_message_animation_gets_raw_len(self) -> None:
        """Critical finding 1: the animation attr must see the RAW string
        length including :slug: chars."""
        w = TickerMessage(text="GO :sun: GO", animation=Typewriter())
        assert w._effect_total_chars("animation") == len("GO :sun: GO")  # 11

    def test_ticker_message_color_gets_emoji_excluded_count(self) -> None:
        """Color providers see the draw-path anchor: count_text_chars on
        the emoji path (":sun:" collapses to one emoji, contributing 0
        text chars)."""
        from led_ticker.pixel_emoji import count_text_chars

        w = TickerMessage(
            text="GO :sun: GO",
            font_color=Shimmer(RGB_WHITE, RGB_BLUE),
        )
        assert w._effect_total_chars("font_color") == count_text_chars("GO :sun: GO")

    def test_ticker_message_plain_text_color_gets_len(self) -> None:
        w = TickerMessage(text="HELLO", font_color=Shimmer(RGB_WHITE, RGB_BLUE))
        assert w._effect_total_chars("font_color") == 5

    def test_two_row_per_row_counts(self) -> None:
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="BOTTOM ROW",
            top_color=Shimmer(RGB_WHITE, RGB_BLUE),
            bottom_color=Shimmer(RGB_WHITE, RGB_BLUE),
        )
        assert w._effect_total_chars("top_color") == 3
        assert w._effect_total_chars("bottom_color") == 10

    def test_base_default_falls_back_to_text_attr(self) -> None:
        w = _Widget(text="ABCD")
        assert w._effect_total_chars("font_color") == 4

    def test_base_default_floor_is_one(self) -> None:
        w = _Widget(text="")
        assert w._effect_total_chars("font_color") == 1
```

NOTE for the implementer: check `TickerMessage` and `TwoRowMessage` constructor requirements (fonts etc.) in their attrs definitions and the existing tests (`tests/test_widgets/test_message.py`, `tests/test_widgets/test_two_row.py`) — add whatever minimal required kwargs those tests use for bare construction. The assertions must not change.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_widgets/test_frames_to_transition_ready.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'frames_to_transition_ready'`.

- [ ] **Step 3: Implement**

(a) In `src/led_ticker/widgets/_frame_aware.py`, add to `FrameAwareBase` (after `frame_for`):

```python
    def frames_to_transition_ready(self) -> int:
        """Max frames-to-rest across this widget's animated effects.

        The engine consults this at the hold→transition handoff and may
        extend the hold by up to ~1 s (all-or-nothing) so a transition
        lands on a visually flat state (shimmer pause, typewriter done)
        instead of chopping mid-animation. 0 = ready now.

        Contract (mirrors ``should_display``): this method must NEVER
        raise — a readiness check may never stall or crash the render
        loop. Any exception inside → 0 (ready).

        Effects are duck-typed: anything in ``_EFFECT_ATTRS`` exposing
        ``frames_to_rest(frame, total_chars)`` participates; effects
        without it (e.g. border effects) contribute 0. Char counts come
        from ``_effect_total_chars`` — per effect KIND, see that hook.
        """
        try:
            extra = 0
            for attr, effect in self._iter_effects():
                fn = getattr(effect, "frames_to_rest", None)
                if fn is None:
                    continue
                chars = max(1, int(self._effect_total_chars(attr)))
                extra = max(extra, int(fn(self.frame_for(attr), chars)))
            return extra
        except Exception:
            return 0

    def _effect_total_chars(self, attr_name: str) -> int:
        """Char count fed to ``frames_to_rest`` for the named effect.

        Widgets override this to match what each effect actually
        consumes — the counts differ BY EFFECT KIND and must mirror the
        widget's own draw path:

        - color-provider attrs (``font_color``, ``top_color``, …): the
          same anchor the draw path passes to ``color_for`` —
          ``count_text_chars(full_text)`` when the text contains emoji,
          else ``len(full_text)``.
        - ``"animation"``: RAW ``len(full_text)`` (emoji ``:slug:``
          characters INCLUDED) — Typewriter slices against the raw
          string.

        Default: length of a ``text`` attribute if present (floor 1) —
        safe for simple single-text widgets; wrong counts only make the
        settle window slightly off, never unsafe.
        """
        text = getattr(self, "text", "") or ""
        return max(1, len(str(text)))
```

(b) In `src/led_ticker/widgets/message.py`, add to `TickerMessage`:

```python
    def _effect_total_chars(self, attr_name: str) -> int:
        """Per-effect-kind counts mirroring TickerMessage.draw's anchors:
        animation → raw len (frame_for slices the raw string); color
        providers → count_text_chars on the emoji path (matching the
        draw_with_emoji total_chars anchor), else len."""
        full_text = self._resolve_into_full_text()
        if attr_name == "animation":
            return max(1, len(full_text))
        if self._has_emoji:
            from led_ticker.pixel_emoji import count_text_chars  # noqa: PLC0415

            return max(1, count_text_chars(full_text))
        return max(1, len(full_text))
```

(Verify `_resolve_into_full_text` and `_has_emoji` exist on TickerMessage — both are used in `draw` at message.py ~line 152/165; mirror however `draw` obtains them.)

(c) In `src/led_ticker/widgets/two_row.py`, add to `TwoRowMessage`:

```python
    def _effect_total_chars(self, attr_name: str) -> int:
        """Per-row counts: top_color sees the top row's text, bottom_color
        the bottom row's. Emoji rows use count_text_chars (matching the
        draw_with_emoji anchor in _draw_row_text); plain rows use len."""
        if attr_name == "top_color":
            text = self._resolved_top
        elif attr_name == "bottom_color":
            text = self._resolved_bottom
        else:
            return super()._effect_total_chars(attr_name)
        if EMOJI_PATTERN.search(text):
            from led_ticker.pixel_emoji import count_text_chars  # noqa: PLC0415

            return max(1, count_text_chars(text))
        return max(1, len(text))
```

(Verify `EMOJI_PATTERN` is already imported in two_row.py — it's used at ~line 401; `_resolved_top`/`_resolved_bottom` are set in `__attrs_post_init__` at ~line 207.)

- [ ] **Step 4: Run tests to verify they pass (plus widget regressions)**

Run: `uv run --extra dev pytest tests/test_widgets/test_frames_to_transition_ready.py tests/test_widgets/test_message.py tests/test_widgets/test_two_row.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint, format, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/widgets/
git add src/led_ticker/widgets/_frame_aware.py src/led_ticker/widgets/message.py src/led_ticker/widgets/two_row.py tests/test_widgets/test_frames_to_transition_ready.py
git commit -m "feat(widgets): frames_to_transition_ready seam on FrameAwareBase

Max frames_to_rest across effects, never raises, per-effect-kind char
counts (animation = raw len; color providers = draw-path anchor).
TickerMessage + TwoRowMessage overrides. Part of #305."
```

---

### Task 5: Engine settle site in `_swap_and_scroll`

**Files:**
- Modify: `src/led_ticker/ticker.py`
- Test: `tests/test_ticker_settle.py` (create)

**Interfaces:**
- Consumes: `frames_to_transition_ready()` duck-typed (Task 4); `ENGINE_TICK_MS` (Task 1); existing `_hold_ticks`, `self.breaker.is_disabled`.
- Produces: `MAX_SETTLE_TICKS` module constant; `Ticker._frames_to_settle(widget) -> int` static helper; the settle block. Nothing downstream consumes these — this task completes the runtime feature.
- Placement: `_swap_and_scroll` ends with `return canvas, cursor_pos, pos` (~line 666), reached by the overflow branch (scroll + optional holds) and the else/held-only branch. The `forces_offscreen_scroll` (~line 591) and `wraps_forever` (~line 623) branches return EARLY and are excluded by design (spec §4). The settle goes immediately before the final return, gated on `not continuous` and the breaker.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ticker_settle.py`. Model the harness on `tests/test_ticker_display.py` (read its fixtures first — it builds a `Ticker` with `mock_frame`/`swapping_frame` from `tests/conftest.py` and drives `_swap_and_scroll`). The five behaviors:

```python
"""Settle-to-rest at the hold→transition handoff (#305): after the hold,
the engine extends by frames_to_transition_ready() ticks — all-or-nothing
against MAX_SETTLE_TICKS — so transitions land at animation rest points."""

import attrs
import pytest

from led_ticker.ticker import MAX_SETTLE_TICKS, Ticker
from led_ticker.widgets._frame_aware import FrameAwareBase


@attrs.define
class _SettleWidget(FrameAwareBase):
    """Held-text widget reporting a fixed frames-to-rest. Draw is
    fits-on-screen (cursor_pos < canvas.width) so _swap_and_scroll takes
    the held-only branch."""

    remaining: int = 0
    draw_calls: int = attrs.field(init=False, default=0)
    ready_calls: int = attrs.field(init=False, default=0)

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        self.draw_calls += 1
        return canvas, 10  # fits: 10 < canvas.width

    def frames_to_transition_ready(self) -> int:
        self.ready_calls += 1
        return self.remaining


@attrs.define
class _RaisingReadyWidget(FrameAwareBase):
    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        return canvas, 10

    def frames_to_transition_ready(self) -> int:
        raise RuntimeError("boom")


@attrs.define
class _PlainWidget(FrameAwareBase):
    """No frames_to_transition_ready — must behave byte-identically to
    today (hold ticks only)."""

    draw_calls: int = attrs.field(init=False, default=0)

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        self.draw_calls += 1
        return canvas, 10


# Helper the tests share: build a Ticker + canvas the way
# tests/test_ticker_display.py does (copy its fixture usage), run
# _swap_and_scroll with hold_time such that the base hold is exactly
# N_HOLD ticks, and return the widget's draw_calls.


class TestSettleToRest:
    async def test_settle_extends_by_exactly_remaining(self, ...):
        # widget.remaining = 5; base hold = N ticks
        # assert widget.draw_calls == N + 5
        ...

    async def test_over_cap_extends_zero(self, ...):
        # widget.remaining = MAX_SETTLE_TICKS + 1
        # assert widget.draw_calls == N  (all-or-nothing)
        ...

    async def test_raising_ready_extends_zero_no_crash(self, ...):
        ...

    async def test_breaker_disabled_skips_settle(self, ...):
        # trip the breaker for the widget first (ticker.breaker.trip(...)),
        # widget.remaining = 5 -> draw_calls unchanged by settle
        # AND widget.ready_calls == 0 (settle skipped entirely)
        ...

    async def test_widget_without_method_unchanged(self, ...):
        # _PlainWidget: draw_calls == N exactly
        ...

    async def test_settle_ticks_advance_frames(self, ...):
        # widget.remaining = 3; after the run, widget._frame_count has
        # advanced by N + 3 (the settle reuses _hold_ticks, which calls
        # _advance_frame_if_supported per tick — constraint #12)
        ...
```

The `...` bodies MUST be fully written by the implementer using the concrete harness from `tests/test_ticker_display.py` — copy its Ticker/canvas/frame construction verbatim (this plan cannot inline it because the fixture names live in `tests/conftest.py`; use `mock_frame` where capture-correctness isn't asserted). `MAX_SETTLE_TICKS` import at top doubles as the constant's existence test.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_ticker_settle.py -v`
Expected: FAIL — `ImportError: cannot import name 'MAX_SETTLE_TICKS'`.

- [ ] **Step 3: Implement**

In `src/led_ticker/ticker.py`:

(a) Module-level constant, placed near the top with the other module constants (grep `SCROLL_SPEED` or similar for the right neighborhood):

```python
# Settle-to-rest bound (#305): at the hold→transition handoff the engine
# may extend the hold so animated effects (shimmer sweep, typewriter
# reveal) land at a rest point. All-or-nothing: a remainder above this
# cap gets NO extension (never pay latency without a clean landing).
# ~1 s keeps the slip inside the rotation's existing jitter budget.
MAX_SETTLE_TICKS: int = 1000 // ENGINE_TICK_MS
```

(b) Static helper on `Ticker` (near `_advance_frame_if_supported` / `_safe_draw`):

```python
    @staticmethod
    def _frames_to_settle(widget: Any) -> int:
        """Duck-typed frames_to_transition_ready; any error → 0.

        Defensive on top of the widget-side never-raise contract — a
        readiness check must never stall or crash the render loop."""
        fn = getattr(widget, "frames_to_transition_ready", None)
        if fn is None:
            return 0
        try:
            return int(fn())
        except Exception:
            return 0
```

(c) The settle block, in `_swap_and_scroll`, immediately BEFORE the final `return canvas, cursor_pos, pos` (the one both the overflow and held-only branches reach; NOT the early returns in the `forces_offscreen_scroll` / `wraps_forever` branches):

```python
        # Settle-to-rest (#305): give animated effects up to
        # MAX_SETTLE_TICKS extra hold so the upcoming transition lands
        # at a rest point (shimmer pause / typewriter done) instead of
        # chopping mid-animation. All-or-nothing; reuses _hold_ticks so
        # constraints #1/#12 (swap capture, advance-per-tick) are
        # inherited. Skipped for breaker-tripped widgets — a disabled
        # widget must not buy extra blank-draw time.
        if not continuous and not self.breaker.is_disabled(ticker_obj):
            extra = self._frames_to_settle(ticker_obj)
            if 0 < extra <= MAX_SETTLE_TICKS:
                canvas, _ = await self._hold_ticks(
                    canvas, ticker_obj, extra, pos, bg_color
                )

        return canvas, cursor_pos, pos
```

- [ ] **Step 4: Run tests — new, engine regression, and the AST tripwire**

Run: `uv run --extra dev pytest tests/test_ticker_settle.py tests/test_ticker_display.py tests/test_engine_redraw_contract.py -q`
Expected: all PASS. The AST tripwire passes because the settle reuses `_hold_ticks` (no new per-tick loop, no new `_swap(` call site).

- [ ] **Step 5: Lint, format, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/ticker.py
git add src/led_ticker/ticker.py tests/test_ticker_settle.py
git commit -m "feat(engine): settle-to-rest at the hold→transition handoff

One settle site in _swap_and_scroll: extend the hold by
frames_to_transition_ready() ticks, all-or-nothing vs MAX_SETTLE_TICKS
(~1 s). Reuses _hold_ticks (constraints #1/#12 inherited); skipped for
breaker-tripped widgets. Closes the mid-animation chop from #305."
```

---

### Task 6: Validate rule 61 — typewriter typing duration vs hold_time

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate_typewriter_hold.py` (create; check whether validate tests live in one big `tests/test_validate.py` — if so, append a class there instead, following its conventions)

**Interfaces:**
- Consumes: `Typewriter.typing_duration_seconds(total_chars)` (Task 3 — the ONLY duration source); `led_ticker.app.coercion._coerce_animation` (existing) to build the Typewriter from the raw TOML value.
- Produces: `_check_typewriter_hold(config: AppConfig) -> list[ValidationIssue]`, wired into `validate_config` next to the `warnings.extend(_check_soft(config))` call (~line 2523).
- Hold math (antagonist finding 4): `effective_hold = max(section.hold_time, widget_hold)` where `widget_hold` is the widget cfg's numeric `hold_time` or `0.0`. There is NO display-level hold tier, and the engine uses `max()` (ticker.py: `hold_time = max(hold_time, getattr(widget, "hold_time", 0.0))`) — a widget hold SMALLER than the section's must NOT trigger a false fire.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validate_typewriter_hold.py` (mirror the harness of existing validate tests — find how they build an `AppConfig`/TOML fixture with `grep -rn "rule=30\|rule == 30" tests/ -l` and copy that file's approach; typical shape is writing a TOML to `tmp_path` and running `validate_config`):

```python
"""Rule 61: typewriter typing duration exceeds the effective hold —
the reveal gets chopped mid-type. Warning, not error."""

# Harness: copy the fixture/builder approach from the file that tests
# rule 30 (grep tests/ for "rule=30"). The TOML bodies below are the
# test cases; assertion helper: collect issues, filter rule == 61.

TOML_FIRES = """
[display]
panel_cols = 32
panel_rows = 16
chain_length = 5

[[playlist.section]]
mode = "slideshow"
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "THIS MESSAGE IS WAY TOO LONG TO TYPE IN THREE SECONDS"
animation = "typewriter"
"""
# 54 chars * 3 frames * 50 ms = 7.95 s > 3.0 s -> rule 61 warning


_LONG_TEXT = "THIS MESSAGE IS WAY TOO LONG TO TYPE IN THREE SECONDS"  # 53 chars


def _toml(section_hold: float, widget_lines: str) -> str:
    return f"""
[display]
panel_cols = 32
panel_rows = 16
chain_length = 5

[[playlist.section]]
mode = "slideshow"
hold_time = {section_hold}

[[playlist.section.widget]]
type = "message"
text = "{_LONG_TEXT}"
{widget_lines}
"""


TOML_FIRES = _toml(3.0, 'animation = "typewriter"')
# 3 fpc * (53-1) * 50 ms = 7.8 s > 3.0 s -> rule 61 warning

TOML_SUFFICIENT_HOLD = _toml(10.0, 'animation = "typewriter"')
# 7.8 s < 10 s -> no rule 61

TOML_WIDGET_HOLD_SMALLER = _toml(
    10.0, 'animation = "typewriter"\nhold_time = 1.0'
)
# effective = max(10.0, 1.0) = 10 s -> no rule 61 (max semantics; a
# false fire here means the rule inverted the engine's math)

TOML_WIDGET_HOLD_RESCUES = _toml(
    3.0, 'animation = "typewriter"\nhold_time = 10.0'
)
# effective = max(3.0, 10.0) = 10 s -> no rule 61

TOML_DICT_FORM = _toml(
    3.0, 'animation = {style = "typewriter", frames_per_char = 6}'
)
# 6 fpc * 52 * 50 ms = 15.6 s > 3.0 -> fires; message contains "15.6"

TOML_NO_ANIMATION = _toml(3.0, "")
# same long text, no animation -> no rule 61
```

Recompute the expected durations against `Typewriter.typing_duration_seconds` in the assertions rather than hardcoding, e.g. `Typewriter().typing_duration_seconds(len(_LONG_TEXT))` — the test then can't drift from the formula. Add one more test: **the warning survives the human report** (this is what startup logs via `_log_validation_report`):

```python
def test_rule_61_appears_in_human_report(...) -> None:
    """Startup surfacing: app/run.py logs validate's human report at
    config load — assert rule 61's message text appears in
    _format_human's output for TOML_FIRES (grep validate.py for the
    exact _format_human signature)."""
```

Write each as a real test: run validate on the TOML, assert rule-61 presence/absence, and for `TOML_FIRES` assert the message contains the computed duration (`"8.0"` or `"7.9"` — match the rounding you implement), the configured hold (`"3.0"`), and the word `"hold_time"`, and that `severity == "warning"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_validate_typewriter_hold.py -v`
Expected: FAIL — no rule-61 issues found.

- [ ] **Step 3: Implement**

In `src/led_ticker/validate.py`, add a checker function (place it near `_check_soft`, ~line 1333):

```python
def _check_typewriter_hold(config: AppConfig) -> list[ValidationIssue]:
    """Rule 61: typewriter typing duration exceeds the effective hold.

    The engine's settle-to-rest extension caps at ~1 s, so a reveal
    longer than the hold gets chopped mid-type — the viewer never sees
    the full message. Effective hold mirrors the ENGINE's math:
    max(section.hold_time, widget hold_time or 0.0) — there is no
    display-level hold tier, and a widget hold SMALLER than the
    section's is ignored (max wins), so it must not fire the rule.
    Duration comes from Typewriter.typing_duration_seconds — the single
    home of the formula (never re-implement it here).
    """
    from led_ticker.animations import Typewriter  # noqa: PLC0415
    from led_ticker.app.coercion import _coerce_animation  # noqa: PLC0415

    warnings: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        for j, widget_cfg in enumerate(section.widgets):
            anim_raw = widget_cfg.get("animation")
            if anim_raw is None:
                continue
            try:
                anim = _coerce_animation(anim_raw)
            except (ValueError, TypeError):
                continue  # invalid animation — other rules own that
            if not isinstance(anim, Typewriter):
                continue
            text = str(widget_cfg.get("text", "") or "")
            if not text:
                continue
            duration = anim.typing_duration_seconds(len(text))
            widget_hold = widget_cfg.get("hold_time")
            if not isinstance(widget_hold, (int, float)) or isinstance(
                widget_hold, bool
            ):
                widget_hold = 0.0
            effective_hold = max(float(section.hold_time), float(widget_hold))
            if duration <= effective_hold:
                continue
            warnings.append(
                ValidationIssue(
                    rule=61,
                    location=f"section[{i}].widget[{j}]",
                    severity="warning",
                    message=(
                        f"text takes ~{duration:.1f}s to type but the "
                        f"effective hold_time is {effective_hold:.1f}s — "
                        f"the message will be cut mid-type"
                    ),
                    fix=(
                        f"Raise hold_time to at least {duration:.1f}, or "
                        "shorten the text. (After typing completes, the "
                        "widget holds fully-typed for the remainder of "
                        "the hold.)"
                    ),
                )
            )
    return warnings
```

Wire it in `validate_config`, adjacent to the existing soft checks (~line 2523):

```python
        warnings.extend(_check_typewriter_hold(config))
```

(Match the surrounding indentation/guard structure — if `_check_soft` is inside a conditional block, put this call in the same block.)

Startup surfacing needs NO new code: `app/run.py` already runs `validate_config` at startup and logs the warning summary via `_log_validation_report` (run.py ~lines 411-418) — rule 61 flows through automatically.

- [ ] **Step 4: Run tests to verify they pass (plus validate regression)**

Run: `uv run --extra dev pytest tests/test_validate_typewriter_hold.py tests/ -k "validate" -q`
Expected: all PASS.

- [ ] **Step 5: Lint, format, pyright, commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/led_ticker/validate.py
git add src/led_ticker/validate.py tests/test_validate_typewriter_hold.py
git commit -m "feat(validate): rule 61 — typewriter typing duration vs hold_time

Warns (with the numbers + both fixes) when the reveal outlasts the
effective hold: max(section, widget) mirroring the engine's math.
Duration via Typewriter.typing_duration_seconds (single formula home).
Startup surfacing is free via the existing _log_validation_report.
Part of #305."
```

---

### Task 7: Docs — color-providers, animations, plugin API reference

**Files:**
- Modify: `docs/site/src/content/docs/concepts/color-providers.mdx`; `docs/site/src/content/docs/concepts/animations.mdx`; `docs/site/src/content/docs/plugins/api-reference.mdx`
- Also commit: `docs/superpowers/specs/2026-07-01-defer-to-rest-transitions-design.md` and `docs/superpowers/plans/2026-07-01-defer-to-rest-transitions.md` (they ride along with this branch)

**Interfaces:**
- Consumes: the shipped behavior from Tasks 2-6 (docs must describe what the code does, not the spec's earlier drafts).
- Follow `docs/DOCS-STYLE.md` (read it first — it is the style guide AND per-page review rubric). No "sanity", no gun metaphors.

- [ ] **Step 1: Read the style guide and the three pages**

Read `docs/DOCS-STYLE.md`, then each target page fully before editing (match each page's existing voice, heading depth, and admonition style).

- [ ] **Step 2: Color-providers page — Shimmer note**

In `color-providers.mdx`, find the Shimmer section and add one short paragraph (adapt to the page's voice):

```markdown
When a section transition is due while the shimmer is mid-sweep, the
engine waits up to ~1 second for the sweep to reach its pause before
firing, so the bright spot isn't teleported by the scene change. Sweeps
that need longer than a second (or a `pause` shorter than one frame)
transition immediately, as before.
```

- [ ] **Step 3: Animations page — Typewriter note**

In `animations.mdx`, in the Typewriter section, add (adapt to the page's voice):

```markdown
Typing takes `frames_per_char × 50 ms` per character (~0.15 s each at
the default), so a long message can outlast a short `hold_time` and get
cut mid-type. `led-ticker validate` warns about this (rule 61) with the
computed duration; raise `hold_time` to at least the typing time, or
shorten the text. Transitions also wait up to ~1 second for a reveal
that's nearly done.
```

- [ ] **Step 4: Plugin API reference — FrameAwareBase additions**

In `plugins/api-reference.mdx`, find where `FrameAwareBase` is documented (it is part of the exported surface). OUTSIDE the drift-guarded `<!-- api-methods -->` / exported-names regions (the guard checks `PluginAPI` methods and `__all__` names only — these are inherited methods, not new exports), add to the FrameAwareBase prose:

```markdown
`FrameAwareBase` also provides `frames_to_transition_ready()` — the
engine calls it at the hold→transition handoff and may extend the hold
by up to ~1 second so animated effects finish at a rest point. It
aggregates `frames_to_rest(frame, total_chars)` across the widget's
effects (color providers, animations) and never raises. Widgets with
per-region text override `_effect_total_chars(attr_name)` to hand each
effect the char count it actually renders with; the default uses the
widget's `text` attribute.
```

- [ ] **Step 5: Verify docs build + drift guards, commit**

Run: `uv run --extra dev pytest tests/test_docs_plugin_api_drift.py tests/test_docs_config_options_drift.py -q && make docs-lint`
Expected: all PASS / lint OK. (`make docs-format` first if prettier complains.)

```bash
git add docs/site/src/content/docs/concepts/color-providers.mdx docs/site/src/content/docs/concepts/animations.mdx docs/site/src/content/docs/plugins/api-reference.mdx docs/superpowers/specs/2026-07-01-defer-to-rest-transitions-design.md docs/superpowers/plans/2026-07-01-defer-to-rest-transitions.md
git commit -m "docs: defer-to-rest behavior notes + FrameAwareBase plugin surface

Shimmer/Typewriter settle notes, rule 61 pointer, plugin API reference
prose for frames_to_transition_ready. Ships the #305 spec + plan."
```

---

### Task 8: Full-suite verification

- [ ] **Step 1: Full test suite**

Run: `make test`
Expected: everything passes — including the meta-tripwires that only fire on the full run (`test_engine_redraw_contract.py`, `test_no_ableist_language.py`, docs drift guards).

- [ ] **Step 2: Full lint + typecheck + format check**

Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/ && uv run --extra dev pyright src/`
Expected: clean.

- [ ] **Step 3: Manual smoke (headless render)**

Build a scratch TOML with a shimmer message + `transition = "cut"` + `hold_time = 2.0` and render it headless (`make render-demo CONFIG=<scratch>.toml OUT=<scratch>.gif` — see `tools/render_demo`); confirm the gif shows the cut landing on flat base-color text (no mid-sweep teleport). This is a visual confidence check, not a gate.

- [ ] **Step 4: Fix anything found, commit, report**

Any failure: fix, re-run the failing scope, then re-run `make test`. Report status honestly — failures are findings, not embarrassments.

# Framerate Fraction — Centralized Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `framerate_fraction` through a new `LedFrame.swap()` method to make `SwapOnVSync` timing deterministic on longboi, eliminating scan-seam tearing at the top/bottom rows.

**Architecture:** `LedFrame` gains a private `_framerate_fraction` (computed from `led_limit_refresh_rate_hz / 20`) and a `swap(canvas) -> Canvas` method that passes it to `SwapOnVSync`. The existing `_swap()` shim in `ticker.py` is updated to call `frame.swap()` instead of `frame.matrix.SwapOnVSync()` directly; all other direct call sites in the widget files do the same. An AST tripwire enforces that `frame.py` is the only permitted caller of `SwapOnVSync`.

**Tech Stack:** Python 3.13, attrs, pytest, rgbmatrix C extension (stub in tests)

> **Worktree note:** All implementation work must be done on a feature branch in a git worktree (never on `main`). Create the worktree before starting Task 1, e.g. `git worktree add .worktrees/framerate-fraction -b feat/framerate-fraction`. Run `make dev` inside the worktree before working.

---

## File map

| File | Change |
|---|---|
| `src/led_ticker/frame.py` | Add `_ENGINE_FPS`, `_framerate_fraction` field, `swap()` method |
| `tests/stubs/rgbmatrix/__init__.py` | Add `framerate_fraction=1` param to `SwapOnVSync` |
| `tests/test_frame.py` | Add 5 unit tests |
| `src/led_ticker/ticker.py` | Update `_swap()` to call `frame.swap()` |
| `src/led_ticker/widgets/gif.py` | Migrate 1 call site |
| `src/led_ticker/widgets/still.py` | Migrate 2 call sites |
| `src/led_ticker/widgets/_image_base.py` | Migrate 4 call sites |
| `tests/test_swap_centralization.py` | New: AST tripwire |
| `config/config.longboi.toml` | Add `limit_refresh_rate_hz = 100` |

---

## Task 1: Add `_framerate_fraction` and `swap()` to `LedFrame`

**Files:**
- Modify: `src/led_ticker/frame.py`
- Modify: `tests/stubs/rgbmatrix/__init__.py`
- Modify: `tests/test_frame.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_frame.py`:

```python
from unittest.mock import MagicMock


def test_framerate_fraction_default():
    """limit_refresh_rate_hz=0 → fraction stays at 1 (no change to behaviour)."""
    frame = LedFrame(led_limit_refresh_rate_hz=0)
    assert frame._framerate_fraction == 1


def test_framerate_fraction_computed():
    """100 Hz / 20 fps engine = fraction 5."""
    frame = LedFrame(led_limit_refresh_rate_hz=100)
    assert frame._framerate_fraction == 5


def test_framerate_fraction_rounds():
    """15 Hz / 20 fps rounds to 0.75 → floor-at-1 → 1."""
    frame = LedFrame(led_limit_refresh_rate_hz=15)
    assert frame._framerate_fraction == 1


def test_swap_passes_fraction_to_matrix():
    """frame.swap() must forward _framerate_fraction to SwapOnVSync."""
    frame = LedFrame(led_limit_refresh_rate_hz=100)
    mock_matrix = MagicMock()
    frame.matrix = mock_matrix
    canvas = object()
    frame.swap(canvas)
    mock_matrix.SwapOnVSync.assert_called_once_with(canvas, 5)


def test_swap_returns_new_canvas():
    """frame.swap() returns the back-buffer (new canvas, not the same object)."""
    frame = LedFrame()
    canvas = frame.matrix.CreateFrameCanvas()
    result = frame.swap(canvas)
    assert result is not canvas
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_frame.py::test_framerate_fraction_default tests/test_frame.py::test_framerate_fraction_computed tests/test_frame.py::test_framerate_fraction_rounds tests/test_frame.py::test_swap_passes_fraction_to_matrix tests/test_frame.py::test_swap_returns_new_canvas -v
```

Expected: 5 failures — `AttributeError: 'LedFrame' object has no attribute '_framerate_fraction'` and `AttributeError: 'LedFrame' object has no attribute 'swap'`.

- [ ] **Step 3: Add `framerate_fraction` parameter to the stub's `SwapOnVSync`**

In `tests/stubs/rgbmatrix/__init__.py`, change the `SwapOnVSync` signature from:

```python
    def SwapOnVSync(self, canvas):
        """Simulate double-buffering: return the previous back buffer."""
```

to:

```python
    def SwapOnVSync(self, canvas, framerate_fraction=1):
        """Simulate double-buffering: return the previous back buffer."""
```

The `framerate_fraction` parameter is accepted but ignored — the stub doesn't simulate timing.

- [ ] **Step 4: Add `_ENGINE_FPS`, `_framerate_fraction`, and `swap()` to `LedFrame`**

In `src/led_ticker/frame.py`, add the module-level constant immediately before the `@attrs.define` line:

```python
_ENGINE_FPS: int = 20  # must stay in sync with ENGINE_TICK_MS = 50 in ticker.py
```

Inside the `LedFrame` class, add `_framerate_fraction` as an `attrs` init=False field after `led_limit_refresh_rate_hz`:

```python
    led_limit_refresh_rate_hz: int = 0
    matrix: RGBMatrixType = attrs.field(init=False)
    _framerate_fraction: int = attrs.field(init=False)
```

At the END of `__attrs_post_init__`, after `self.matrix = RGBMatrix(options=options)`, add the fraction computation:

```python
        self.matrix = RGBMatrix(options=options)
        self._framerate_fraction = (
            max(1, round(self.led_limit_refresh_rate_hz / _ENGINE_FPS))
            if self.led_limit_refresh_rate_hz
            else 1
        )
```

After `get_clean_canvas`, add the `swap` method:

```python
    def swap(self, canvas: Canvas) -> Canvas:
        """Swap the back-buffer to the display.

        Single centralized swap point. The framerate_fraction argument
        makes SwapOnVSync land at a fixed position in the hardware scan
        cycle, eliminating the scan-seam tearing visible on long chains.
        Future overlay_hooks will iterate here before the swap.
        """
        return self.matrix.SwapOnVSync(canvas, self._framerate_fraction)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_frame.py -v
```

Expected: all pass including the 5 new tests.

- [ ] **Step 6: Run full test suite**

```bash
make test
```

Expected: green. The stub change is backwards-compatible (parameter is optional).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/frame.py tests/stubs/rgbmatrix/__init__.py tests/test_frame.py
git commit -m "feat: add LedFrame._framerate_fraction and LedFrame.swap()

Centralizes SwapOnVSync behind a single method that passes the hardware
refresh fraction, making swap timing deterministic on longboi at 100 Hz.
Stub gains the optional framerate_fraction param (ignored in tests)."
```

---

## Task 2: Update `_swap()` helper in `ticker.py`

**Files:**
- Modify: `src/led_ticker/ticker.py:129-139`

- [ ] **Step 1: Update `_swap()` to call `frame.swap()`**

In `src/led_ticker/ticker.py`, the `_swap` function currently reads:

```python
def _swap(canvas: Any, frame: Any) -> Any:
    """SwapOnVSync that handles both real canvases and ScaledCanvas wrappers.

    For real canvases: returns the new back-buffer canvas.
    For ScaledCanvas: swaps the underlying real canvas in place and returns
    the same wrapper (now pointing at the new back-buffer).
    """
    if isinstance(canvas, ScaledCanvas):
        canvas.real = frame.matrix.SwapOnVSync(canvas.real)
        return canvas
    return frame.matrix.SwapOnVSync(canvas)
```

Change it to:

```python
def _swap(canvas: Any, frame: Any) -> Any:
    """SwapOnVSync that handles both real canvases and ScaledCanvas wrappers.

    For real canvases: returns the new back-buffer canvas.
    For ScaledCanvas: swaps the underlying real canvas in place and returns
    the same wrapper (now pointing at the new back-buffer).
    """
    if isinstance(canvas, ScaledCanvas):
        canvas.real = frame.swap(canvas.real)
        return canvas
    return frame.swap(canvas)
```

- [ ] **Step 2: Run full test suite**

```bash
make test
```

Expected: green. All existing `_swap`-based tests pass through `frame.swap()` now.

- [ ] **Step 3: Commit**

```bash
git add src/led_ticker/ticker.py
git commit -m "refactor: _swap() routes through frame.swap() instead of matrix directly"
```

---

## Task 3: Migrate widget call sites

**Files:**
- Modify: `src/led_ticker/widgets/gif.py:344`
- Modify: `src/led_ticker/widgets/still.py:299,314`
- Modify: `src/led_ticker/widgets/_image_base.py:1367,1407,1631,1680`

There are 7 direct `frame.matrix.SwapOnVSync(canvas)` calls in widget files. Each is a mechanical one-line substitution: `frame.matrix.SwapOnVSync(canvas)` → `frame.swap(canvas)`. The return-value capture and ScaledCanvas rebind semantics are unchanged.

- [ ] **Step 1: Migrate `gif.py`**

In `src/led_ticker/widgets/gif.py` at line 344, change:

```python
            canvas = frame.matrix.SwapOnVSync(canvas)
```

to:

```python
            canvas = frame.swap(canvas)
```

- [ ] **Step 2: Migrate `still.py`**

In `src/led_ticker/widgets/still.py`, there are two calls. Change both:

```python
            canvas = frame.matrix.SwapOnVSync(canvas)
```

to:

```python
            canvas = frame.swap(canvas)
```

(Both occurrences — one in the fast path around line 299, one in the slow tick loop around line 314.)

- [ ] **Step 3: Migrate `_image_base.py`**

In `src/led_ticker/widgets/_image_base.py`, there are four calls (approximately lines 1367, 1407, 1631, 1680). Change each:

```python
            canvas = frame.matrix.SwapOnVSync(canvas)
```

to:

```python
            canvas = frame.swap(canvas)
```

Use search-and-replace to catch all four — there must be exactly zero remaining after:

```bash
grep -n "frame.matrix.SwapOnVSync" src/led_ticker/widgets/_image_base.py
```

Expected: no output.

- [ ] **Step 4: Verify no `frame.matrix.SwapOnVSync` calls remain in widgets**

```bash
grep -rn "frame.matrix.SwapOnVSync" src/led_ticker/widgets/
```

Expected: no output.

- [ ] **Step 5: Run full test suite**

```bash
make test
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/gif.py src/led_ticker/widgets/still.py src/led_ticker/widgets/_image_base.py
git commit -m "refactor: migrate widget SwapOnVSync calls to frame.swap()"
```

---

## Task 4: AST tripwire

**Files:**
- Create: `tests/test_swap_centralization.py`

- [ ] **Step 1: Write the tripwire test**

Create `tests/test_swap_centralization.py`:

```python
"""AST tripwire: frame.py is the only permitted SwapOnVSync caller.

All other code must go through LedFrame.swap() so framerate_fraction
is always forwarded and future overlay_hooks have a single injection point.
"""

from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "led_ticker"
ALLOWLIST = {"frame.py"}


def test_no_bare_swaponvsync():
    violations = []
    for path in SRC.rglob("*.py"):
        if path.name in ALLOWLIST:
            continue
        if "SwapOnVSync" in path.read_text():
            violations.append(path.relative_to(SRC))
    assert not violations, (
        "Direct SwapOnVSync calls found — use frame.swap() instead:\n"
        + "\n".join(f"  src/led_ticker/{v}" for v in violations)
    )
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
pytest tests/test_swap_centralization.py -v
```

Expected: PASS. If it fails, a widget file still has a bare `SwapOnVSync` — fix it before continuing.

- [ ] **Step 3: Run full test suite**

```bash
make test
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_swap_centralization.py
git commit -m "test: AST tripwire enforcing frame.swap() as sole SwapOnVSync caller"
```

---

## Task 5: Enable `limit_refresh_rate_hz = 100` on longboi

**Files:**
- Modify: `config/config.longboi.toml`

- [ ] **Step 1: Add `limit_refresh_rate_hz` to the longboi display config**

In `config/config.longboi.toml`, add `limit_refresh_rate_hz = 100` to the `[display]` section. Place it next to the other Pi 5 timing tuning fields. The `[display]` section should look like:

```toml
[display]
rows = 64
cols = 128
chain = 4
brightness = 60
default_scale = 4
hardware_mapping = "adafruit-hat"
panel_type = "FM6126A"
# Muen P2 panels wire HUB75 G-pin → Red LED, R-pin → Blue LED, B-pin → Green LED.
led_rgb_sequence = "BRG"

# Pi 5 RP1 RIO backend (faster refresh, slightly more CPU than PIO).
# rp1_rio = 1 requires row_address_type = 0 (default) — do not set row_address_type = 1.
# Raise gpio_slowdown to 4–5 if flicker appears.
gpio_slowdown = 3
rp1_rio = 1
pwm_bits = 8     # 8-bit PWM: faster refresh, slightly less color depth than default 11
show_refresh_rate = true
# Cap refresh at 100 Hz so SwapOnVSync(canvas, framerate_fraction=5) lands
# at the same scan-cycle point every frame at 20 fps — eliminates top/bottom
# motion lag on the 512-column chain (hzeller/rpi-rgb-led-matrix issue #941).
limit_refresh_rate_hz = 100
```

- [ ] **Step 2: Validate the config**

```bash
make validate CONFIG=config/config.longboi.toml
```

Expected: no validation errors.

- [ ] **Step 3: Run full test suite**

```bash
make test
```

Expected: green. (The docs-drift test audits `DisplayConfig` defaults, not this file, so no doc updates required.)

- [ ] **Step 4: Commit**

```bash
git add config/config.longboi.toml
git commit -m "config: enable limit_refresh_rate_hz = 100 on longboi

Combined with framerate_fraction=5 in LedFrame.swap(), swaps now land at
a fixed point in the 100 Hz scan cycle at exactly 20 fps, eliminating
the top/bottom motion lag caused by SwapOnVSync landing near the seam."
```

---

## Task 6: Open PR

- [ ] **Step 1: Push the branch and open a PR**

```bash
git push -u origin feat/framerate-fraction
gh pr create \
  --title "feat: centralize SwapOnVSync via LedFrame.swap() with framerate_fraction" \
  --body "$(cat <<'EOF'
## Summary

- Adds `LedFrame.swap(canvas)` as the single centralized swap point, forwarding `_framerate_fraction` to `SwapOnVSync` so hardware swap timing is deterministic.
- `_framerate_fraction` is auto-computed from `led_limit_refresh_rate_hz / 20`; defaults to 1 (unchanged behaviour when `limit_refresh_rate_hz` is not set).
- Migrates all 9 `SwapOnVSync` call sites (`_swap()` helper + 7 widget sites) to `frame.swap()`.
- Enforces centralization with an AST tripwire (`tests/test_swap_centralization.py`).
- Enables `limit_refresh_rate_hz = 100` on longboi, making swaps land at 20 fps fixed points in the 100 Hz refresh cycle — fixes top/bottom motion lag (hzeller/rpi-rgb-led-matrix issue #941).
- `LedFrame.swap()` signature is future-proof: `overlay_hooks` (busy-light PR) iterate inside `swap()` with no call-site changes.

## Test plan

- [ ] `pytest tests/test_frame.py` — 5 new tests for fraction computation and `swap()` delegation
- [ ] `pytest tests/test_swap_centralization.py` — AST tripwire passes
- [ ] `make test` — full suite green
- [ ] Deploy to longboi and verify motion is smooth with `show_refresh_rate = true` confirming ~100 Hz

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Verify CI is green before merging**

Check PR status:

```bash
gh pr checks
```

Wait for all checks to pass before merging. Do NOT merge without explicit user confirmation.

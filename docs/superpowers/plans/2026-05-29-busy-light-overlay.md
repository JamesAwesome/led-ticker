# Busy-Light Overlay System + MVP Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A generic `LedFrame.overlay_hooks` compositor (paint callbacks run in `swap()` before every `SwapOnVSync`) plus an MVP busy light — a file-driven service that paints a steady corner dot while `~/.busy` exists.

**Architecture:** `LedFrame` gains `overlay_hooks: list[Callable[[Canvas], None]]`; `swap()` runs them on the real canvas before the hardware swap (all render paths already route through `swap()`, so no migration). A `BusyLight` app-scope service polls a file via the existing `run_monitor_loop` and registers a `paint` hook. A `[busy_light]` config block drives it; `run.py` wires it when enabled.

**Tech Stack:** Python 3.13, attrs, pytest, the existing `LedFrame`/`run_monitor_loop`/config-dataclass machinery.

Spec: `docs/superpowers/specs/2026-05-29-busy-light-overlay-design.md`

---

### Task 1: `LedFrame.overlay_hooks` + paint-before-swap

**Files:**
- Modify: `src/led_ticker/frame.py` (imports; attrs field after line 44; `swap()` at lines 97–105)
- Test: `tests/test_frame.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_frame.py` (it already imports `LedFrame` and uses `MagicMock`; add `from unittest.mock import MagicMock` only if not already imported):

```python
def test_overlay_hooks_default_empty():
    frame = LedFrame()
    assert frame.overlay_hooks == []


def test_swap_runs_hooks_before_swap_with_canvas():
    """Each overlay hook is called once with the canvas, BEFORE SwapOnVSync."""
    frame = LedFrame()
    order: list[str] = []
    received: list[object] = []
    canvas = object()

    def hook(c):
        received.append(c)
        order.append("hook")

    mock_matrix = MagicMock()
    mock_matrix.SwapOnVSync.side_effect = lambda c, f: order.append("swap")
    frame.matrix = mock_matrix
    frame.overlay_hooks.append(hook)

    frame.swap(canvas)

    assert received == [canvas]
    assert order == ["hook", "swap"]  # hooks paint before the hardware swap


def test_swap_runs_multiple_hooks_in_registration_order():
    frame = LedFrame()
    calls: list[str] = []
    frame.matrix = MagicMock()
    frame.overlay_hooks.extend(
        [lambda c: calls.append("a"), lambda c: calls.append("b")]
    )
    frame.swap(object())
    assert calls == ["a", "b"]


def test_swap_no_hooks_unchanged():
    """Empty overlay_hooks: swap forwards (canvas, fraction) and returns the result."""
    frame = LedFrame(led_limit_refresh_rate_hz=100)
    mock_matrix = MagicMock()
    mock_matrix.SwapOnVSync.return_value = "backbuffer"
    frame.matrix = mock_matrix
    canvas = object()
    result = frame.swap(canvas)
    mock_matrix.SwapOnVSync.assert_called_once_with(canvas, 5)
    assert result == "backbuffer"
```

- [ ] **Step 2: Run the tests — confirm they fail**

Run: `uv run pytest tests/test_frame.py -k "overlay or hooks" -v`
Expected: FAIL — `LedFrame` has no `overlay_hooks` attribute.

- [ ] **Step 3: Add the import + field + paint loop**

In `src/led_ticker/frame.py`, add to the top imports (after `from __future__ import annotations`):

```python
from collections.abc import Callable
```

Add the field to the `LedFrame` attrs body — place it right after the `matrix` field (line 44):

```python
    matrix: RGBMatrixType = attrs.field(init=False)
    overlay_hooks: list[Callable[[Canvas], None]] = attrs.field(factory=list)
```

Replace `swap()` (lines 97–105) with:

```python
    def swap(self, canvas: Canvas) -> Canvas:
        """Swap the back-buffer to the display.

        Single centralized swap point. Each registered overlay hook paints
        on the real canvas (physical pixels) immediately before the hardware
        swap, so overlays composite over every render path (engine,
        transitions, play()-style widgets) that routes through here. The
        framerate_fraction argument pins SwapOnVSync to a fixed scan-cycle
        position, eliminating seam tearing on long chains.
        """
        for hook in self.overlay_hooks:
            hook(canvas)
        return self.matrix.SwapOnVSync(canvas, self._framerate_fraction)
```

- [ ] **Step 4: Run the tests — confirm they pass**

Run: `uv run pytest tests/test_frame.py -v`
Expected: all pass (the four new tests plus the existing `test_swap_*` ones).

- [ ] **Step 5: Confirm the swap-centralization tripwire still passes**

Run: `uv run pytest tests/test_swap_centralization.py -v`
Expected: PASS — no new raw `SwapOnVSync` call sites were introduced.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/frame.py tests/test_frame.py
git -c core.hooksPath=/dev/null commit -m "feat: LedFrame.overlay_hooks — paint callbacks run before every swap

Generic overlay mechanism: swap() runs each registered hook on the real
canvas before SwapOnVSync. All render paths already route through swap(),
so overlays composite everywhere with no per-call-site changes. Empty
hooks list is byte-identical to prior behavior. LedFrame stays
mechanism-only (no knowledge of any specific overlay)."
```

---

### Task 2: `BusyLight` service

**Files:**
- Create: `src/led_ticker/busy_light.py`
- Test: `tests/test_busy_light.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_busy_light.py`:

```python
"""Tests for the BusyLight overlay service."""

from pathlib import Path

from rgbmatrix import _StubCanvas  # test stub canvas with SetPixel + get_pixel

from led_ticker.busy_light import BusyLight


def test_file_path_expands_user():
    busy = BusyLight(file_path="~/.busy")
    assert busy.file_path == Path.home() / ".busy"


def test_update_busy_when_file_exists(tmp_path):
    f = tmp_path / ".busy"
    f.write_text("")
    busy = BusyLight(file_path=str(f))
    import asyncio

    asyncio.run(busy.update())
    assert busy.is_busy is True


def test_update_not_busy_when_file_absent(tmp_path):
    busy = BusyLight(file_path=str(tmp_path / ".busy"))
    import asyncio

    asyncio.run(busy.update())
    assert busy.is_busy is False


def _lit(canvas):
    return {
        (x, y)
        for y in range(canvas.height)
        for x in range(canvas.width)
        if canvas.get_pixel(x, y) != (0, 0, 0)
    }


def test_paint_top_right_block_when_busy():
    canvas = _StubCanvas(width=64, height=32)
    busy = BusyLight(file_path="/nonexistent", corner="top_right", color=(255, 0, 0), size=4)
    busy.is_busy = True
    busy.paint(canvas)
    lit = _lit(canvas)
    assert lit == {(x, y) for x in range(60, 64) for y in range(0, 4)}
    assert canvas.get_pixel(63, 0) == (255, 0, 0)


def test_paint_each_corner():
    cases = {
        "top_left": {(x, y) for x in range(0, 4) for y in range(0, 4)},
        "top_right": {(x, y) for x in range(60, 64) for y in range(0, 4)},
        "bottom_left": {(x, y) for x in range(0, 4) for y in range(28, 32)},
        "bottom_right": {(x, y) for x in range(60, 64) for y in range(28, 32)},
    }
    for corner, expected in cases.items():
        canvas = _StubCanvas(width=64, height=32)
        busy = BusyLight(file_path="/x", corner=corner, color=(1, 2, 3), size=4)
        busy.is_busy = True
        busy.paint(canvas)
        assert _lit(canvas) == expected, corner


def test_paint_nothing_when_not_busy():
    canvas = _StubCanvas(width=64, height=32)
    busy = BusyLight(file_path="/x", size=4)
    busy.is_busy = False
    busy.paint(canvas)
    assert _lit(canvas) == set()


def test_size_clamps_to_canvas_bounds():
    canvas = _StubCanvas(width=8, height=8)
    busy = BusyLight(file_path="/x", corner="top_left", size=100)
    busy.is_busy = True
    busy.paint(canvas)  # must not raise / paint out of range
    lit = _lit(canvas)
    assert lit == {(x, y) for x in range(8) for y in range(8)}
```

- [ ] **Step 2: Run the tests — confirm they fail**

Run: `uv run pytest tests/test_busy_light.py -v`
Expected: FAIL — `led_ticker.busy_light` does not exist.

- [ ] **Step 3: Create `src/led_ticker/busy_light.py`**

```python
"""Busy-light overlay service.

Polls a local file for busy state and paints a steady corner dot via a
LedFrame overlay hook. Mechanism is generic; this is the first consumer
of LedFrame.overlay_hooks. Real busy sources (calendar/Slack) are a
follow-up that sets the same is_busy flag behind the same overlay.
"""

from __future__ import annotations

from pathlib import Path

import attrs

from led_ticker._types import Canvas, ColorTuple

_CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")


@attrs.define
class BusyLight:
    """Polls `file_path` for busy state; paints a corner dot while busy."""

    file_path: Path = attrs.field(converter=lambda p: Path(p).expanduser())
    corner: str = "top_right"
    color: ColorTuple = (255, 0, 0)
    size: int = 4
    is_busy: bool = attrs.field(default=False, init=False)

    async def update(self) -> None:
        """Conforms to the Updatable protocol; driven by run_monitor_loop."""
        self.is_busy = self.file_path.exists()

    def paint(self, canvas: Canvas) -> None:
        """Overlay hook: draw a size×size block in the corner while busy."""
        if not self.is_busy:
            return
        w = canvas.width
        h = getattr(canvas, "height", 16)
        s = max(1, min(self.size, w, h))
        x0 = 0 if "left" in self.corner else w - s
        y0 = 0 if "top" in self.corner else h - s
        r, g, b = self.color
        for dy in range(s):
            for dx in range(s):
                canvas.SetPixel(x0 + dx, y0 + dy, r, g, b)
```

- [ ] **Step 4: Run the tests — confirm they pass**

Run: `uv run pytest tests/test_busy_light.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/busy_light.py tests/test_busy_light.py
git -c core.hooksPath=/dev/null commit -m "feat: BusyLight service — file poll + corner-dot overlay hook

update() reads ~/.busy presence (Updatable, run by run_monitor_loop);
paint() draws a size×size block in the configured corner while busy.
file_path expanduser'd via attrs converter; size clamps to canvas bounds.
First consumer of LedFrame.overlay_hooks."
```

---

### Task 3: `[busy_light]` config block

**Files:**
- Modify: `src/led_ticker/config.py` (new `BusyLightConfig` dataclass; `AppConfig.busy_light` field; parse + validate in `load_config`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py` (it has a `config(tmp_path)` fixture writing `SAMPLE_CONFIG`; these tests write their own TOML via `tmp_path` + `load_config`):

```python
def test_busy_light_default_disabled(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    cfg = load_config(p)
    assert cfg.busy_light.enabled is False
    assert cfg.busy_light.file_path == "~/.busy"
    assert cfg.busy_light.corner == "top_right"
    assert cfg.busy_light.color == (255, 0, 0)
    assert cfg.busy_light.size == 4
    assert cfg.busy_light.poll_interval == 5.0


def test_busy_light_parsed(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\nfile_path=\"/tmp/b\"\n"
        "poll_interval=2.0\ncorner=\"bottom_left\"\ncolor=[0,255,0]\nsize=6\n\n"
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    cfg = load_config(p)
    assert cfg.busy_light.enabled is True
    assert cfg.busy_light.file_path == "/tmp/b"
    assert cfg.busy_light.poll_interval == 2.0
    assert cfg.busy_light.corner == "bottom_left"
    assert cfg.busy_light.color == (0, 255, 0)
    assert cfg.busy_light.size == 6


def test_busy_light_invalid_corner_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\ncorner=\"middle\"\n\n"
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="corner"):
        load_config(p)


def test_busy_light_invalid_size_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\nsize=0\n\n"
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="size"):
        load_config(p)
```

- [ ] **Step 2: Run the tests — confirm they fail**

Run: `uv run pytest tests/test_config.py -k busy_light -v`
Expected: FAIL — `AppConfig` has no `busy_light` attribute.

- [ ] **Step 3: Add the dataclass, field, parse, and validation**

In `src/led_ticker/config.py`, add the dataclass just above `AppConfig` (before line 152):

```python
@dataclass
class BusyLightConfig:
    enabled: bool = False
    file_path: str = "~/.busy"
    poll_interval: float = 5.0
    corner: str = "top_right"
    color: tuple[int, int, int] = (255, 0, 0)
    size: int = 4
```

Add the field to `AppConfig` (after `between_sections_specified`, before `_coerce_warnings`):

```python
    busy_light: BusyLightConfig = field(default_factory=BusyLightConfig)
```

In `load_config`, after the `transitions_raw` block (around line 315), parse and validate:

```python
    bl_raw = raw.get("busy_light", {})
    busy_light = BusyLightConfig(
        enabled=bl_raw.get("enabled", False),
        file_path=bl_raw.get("file_path", "~/.busy"),
        poll_interval=bl_raw.get("poll_interval", 5.0),
        corner=bl_raw.get("corner", "top_right"),
        color=tuple(bl_raw.get("color", [255, 0, 0])),
        size=bl_raw.get("size", 4),
    )
    _BUSY_CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")
    if busy_light.corner not in _BUSY_CORNERS:
        raise ValueError(
            f"busy_light.corner={busy_light.corner!r} is not valid; "
            f"choose one of: {', '.join(_BUSY_CORNERS)}."
        )
    if busy_light.size < 1:
        raise ValueError(f"busy_light.size must be >= 1; got {busy_light.size}.")
```

Pass it into the `return AppConfig(...)` call (add the kwarg before `_coerce_warnings=coerce_warnings`):

```python
        busy_light=busy_light,
```

- [ ] **Step 4: Run the tests — confirm they pass**

Run: `uv run pytest tests/test_config.py -k busy_light -v`
Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/config.py tests/test_config.py
git -c core.hooksPath=/dev/null commit -m "feat: [busy_light] config block

BusyLightConfig (enabled/file_path/poll_interval/corner/color/size) on
AppConfig, parsed in load_config with corner-enum + size>=1 validation."
```

---

### Task 4: Wire into `run.py` + example config + docs + integration test

**Files:**
- Modify: `src/led_ticker/app/run.py` (after `led_frame = build_frame_from_config(...)`, line 45)
- Modify: `config/config.example.toml` (commented `[busy_light]` block)
- Modify: `CLAUDE.md` (one invariant bullet)
- Test: `tests/test_busy_light.py` (integration test)

- [ ] **Step 1: Write the contract/integration test**

This locks the end-to-end frame+busy contract (it exercises `LedFrame` + `BusyLight` directly, so it passes once Tasks 1–2 are in — it's a regression guard, not failing-first). The `run.py` startup wiring is app glue that isn't unit-tested in isolation; it's covered by `make test` staying green plus the spec's hardware acceptance check (`touch ~/.busy` lights the dot).

Append to `tests/test_busy_light.py`:

```python
def test_registered_hook_paints_dot_through_frame_swap(tmp_path):
    """End-to-end: a BusyLight.paint hook on a real LedFrame lights the
    corner when busy and clears it when not, through frame.swap()."""
    import asyncio

    from led_ticker.frame import LedFrame

    f = tmp_path / ".busy"
    busy = BusyLight(file_path=str(f), corner="top_right", color=(255, 0, 0), size=4)
    frame = LedFrame(led_cols=64, led_rows=32)
    frame.overlay_hooks.append(busy.paint)

    canvas = frame.get_clean_canvas()
    f.write_text("")  # go busy
    asyncio.run(busy.update())
    swapped = frame.swap(canvas)  # returns the previous back-buffer; we painted `canvas`
    # The painted canvas is the one we passed in; inspect it.
    assert canvas.get_pixel(canvas.width - 1, 0) == (255, 0, 0)

    f.unlink()  # not busy
    asyncio.run(busy.update())
    canvas2 = frame.get_clean_canvas()
    frame.swap(canvas2)
    lit = [
        (x, y)
        for y in range(canvas2.height)
        for x in range(canvas2.width)
        if canvas2.get_pixel(x, y) != (0, 0, 0)
    ]
    assert lit == []
```

- [ ] **Step 2: Run it — confirm it passes (regression guard)**

Run: `uv run pytest tests/test_busy_light.py::test_registered_hook_paints_dot_through_frame_swap -v`
Expected: PASS — it validates the frame+busy contract that Tasks 1–2 already implement. (If it fails, something in Task 1 or 2 regressed — fix before proceeding.)

- [ ] **Step 3: Wire the busy light into `run.py`**

In `src/led_ticker/app/run.py`, add the import near the other `from led_ticker...` imports (after line 30):

```python
from led_ticker.widget import run_monitor_loop
```

(If `run_monitor_loop` is already imported, skip.) Then, immediately after `led_frame = build_frame_from_config(config.display)` (line 45):

```python
    if config.busy_light.enabled:
        from led_ticker.busy_light import BusyLight

        busy = BusyLight(
            file_path=config.busy_light.file_path,
            corner=config.busy_light.corner,
            color=config.busy_light.color,
            size=config.busy_light.size,
        )
        await busy.update()  # fast initial read so the dot is correct on frame 1
        led_frame.overlay_hooks.append(busy.paint)
        asyncio.create_task(
            run_monitor_loop(busy, config.busy_light.poll_interval, splay=False)
        )
```

(`BusyLight.file_path` expanduser's via its attrs converter, so pass the raw config string. `splay=False`: react promptly, no random 0–60s offset.)

- [ ] **Step 4: Add a commented `[busy_light]` block to `config/config.example.toml`**

Append to `config/config.example.toml`:

```toml
# Busy light — a persistent corner dot that lights up while a local file
# exists. Toggle with `touch ~/.busy` / `rm ~/.busy`. The dot composites
# over every section and transition. (Real calendar/Slack sources are a
# future addition behind the same overlay.)
# [busy_light]
# enabled = true
# file_path = "~/.busy"
# poll_interval = 5.0
# corner = "top_right"       # top_left | top_right | bottom_left | bottom_right
# color = [255, 0, 0]
# size = 4                    # dot side length in physical pixels
```

- [ ] **Step 5: Add the CLAUDE.md invariant bullet**

In `CLAUDE.md`, under the load-bearing-invariants section (near the `frame.py` / rendering constraints), add:

```
**Overlay hooks** (`frame.py`) — `LedFrame.overlay_hooks: list[Callable[[Canvas], None]]` run inside `swap()` on the real canvas before every `SwapOnVSync`, so an overlay composites over every render path (engine, transitions, play-widgets) with no per-call-site change. `LedFrame` stays mechanism-only. First consumer: `busy_light.BusyLight` (file-driven corner dot via `[busy_light]` config); real calendar/Slack sources are a future swap-in behind the same hook.
```

- [ ] **Step 6: Run the full verification gate**

```bash
uv run pytest tests/test_busy_light.py tests/test_frame.py tests/test_config.py tests/test_swap_centralization.py -v
make test
make lint
make typecheck
```
Expected: all green (~2350+ passed, lint clean, 0 typecheck errors).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app/run.py config/config.example.toml CLAUDE.md tests/test_busy_light.py
git -c core.hooksPath=/dev/null commit -m "feat: wire busy light into run.py + example config + docs

When [busy_light].enabled, build BusyLight, register its paint hook on the
shared led_frame, and start its file-poll loop (splay=False). Commented
[busy_light] block in config.example.toml; CLAUDE.md overlay-hooks
invariant. Integration test: paint hook lights/clears the corner through
frame.swap()."
```

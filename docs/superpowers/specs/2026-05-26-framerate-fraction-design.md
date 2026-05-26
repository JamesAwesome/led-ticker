# Design: Centralized swap + `framerate_fraction` support

**Date:** 2026-05-26
**Status:** Approved
**Branch:** to be created from main

## Problem

On longboi (4× 128×64 FM6126A panels, 512-column chain, Pi 5 RIO mode) a
visible lag appears at the top and bottom rows during motion. Research confirmed
this matches [hzeller/rpi-rgb-led-matrix issue #941][941] — an unresolved known
issue where `SwapOnVSync` lands near the scan-cycle seam, causing both boundary
row groups to show the previous frame during transitions.

The rgbmatrix Python binding exposes a `framerate_fraction` parameter on
`SwapOnVSync(canvas, framerate_fraction=1)` that, combined with
`limit_refresh_rate_hz`, makes swap timing deterministic: at 100 Hz with
`framerate_fraction=5`, every swap lands at the same point in the hardware scan
cycle at exactly 20 fps — the engine's target rate.

Currently `framerate_fraction` is never passed; all call sites use the default
of 1.

[941]: https://github.com/hzeller/rpi-rgb-led-matrix/issues/941

## Goals

1. Wire `framerate_fraction` through every `SwapOnVSync` call site.
2. Centralize all swaps behind `LedFrame.swap()` — the agreed foundation for
   the future busy-light overlay system (see memory: `project-busy-light-widget`).
3. Enforce the centralization with an AST tripwire so no future code can bypass it.
4. Enable `limit_refresh_rate_hz = 100` on longboi as the test case.

## Non-goals

- `overlay_hooks` / busy-light implementation (separate PR).
- Fixing non-default `scroll_step_ms` sections (known limitation, see below).

## Architecture

```
DisplayConfig.limit_refresh_rate_hz   (already exists)
        ↓
LedFrame._framerate_fraction          (new: computed at init, stored privately)
LedFrame.swap(canvas) → Canvas        (new: single centralized swap point)
        ↓
_swap() helper in ticker.py           (updated: ScaledCanvas routing shim → frame.swap())
transitions/__init__.py               (unchanged: already calls _swap())
        ↓
gif.py / still.py / _image_base.py   (migrated: 8 direct SwapOnVSync calls → frame.swap())
        ↓
AST tripwire                          (new: no bare .SwapOnVSync( in src/)
```

`LedFrame.swap()` always receives a real canvas. ScaledCanvas routing stays in
`_swap()`. This matches the busy-light design requirement that overlay callbacks
operate at physical-pixel coordinates with no unwrapping needed.

## Component details

### `frame.py` — `LedFrame`

```python
_ENGINE_FPS: int = 20  # must stay in sync with ENGINE_TICK_MS = 50 in ticker.py

@attrs.define
class LedFrame:
    led_limit_refresh_rate_hz: int = 0  # already exists
    _framerate_fraction: int = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        # ... existing options wiring unchanged ...
        self.matrix = RGBMatrix(options=options)
        self._framerate_fraction = (
            max(1, round(self.led_limit_refresh_rate_hz / _ENGINE_FPS))
            if self.led_limit_refresh_rate_hz
            else 1
        )

    def swap(self, canvas: Canvas) -> Canvas:
        # Future overlay_hooks iterate here before the swap.
        # Signature takes no extra args so call sites need no update when hooks land.
        return self.matrix.SwapOnVSync(canvas, self._framerate_fraction)
```

`_framerate_fraction` examples:
- `limit_refresh_rate_hz = 0` → `1` (default, unchanged behaviour)
- `limit_refresh_rate_hz = 100` → `5`
- `limit_refresh_rate_hz = 15` → `1` (rounds, floors at 1)

### `ticker.py` — `_swap()` helper

```python
def _swap(canvas: Any, frame: Any) -> Any:
    if isinstance(canvas, ScaledCanvas):
        canvas.real = frame.swap(canvas.real)
        return canvas
    return frame.swap(canvas)
```

`transitions/__init__.py` already imports and calls `_swap()` — no change there.

### Call site migration (8 sites, all mechanical)

| File | Call count | Change |
|---|---|---|
| `ticker.py` (`_swap`) | 2 internal | `SwapOnVSync` → `frame.swap()` |
| `widgets/gif.py` | 1 | `frame.matrix.SwapOnVSync(canvas)` → `frame.swap(canvas)` |
| `widgets/still.py` | 2 | same |
| `widgets/_image_base.py` | 4 | same |

Return-value capture and ScaledCanvas rebind semantics are unchanged.

### Stub (`tests/stubs/rgbmatrix/__init__.py`)

`SwapOnVSync` gains an optional `framerate_fraction=1` parameter (ignored in the
stub — test double-buffering behaviour is unaffected).

### AST tripwire (`tests/test_swap_centralization.py`)

```python
SRC = Path(__file__).parent.parent / "src" / "led_ticker"
ALLOWLIST = {"frame.py"}  # LedFrame.swap() is the one permitted SwapOnVSync caller

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

### Config

`config/config.longboi.toml` — add `limit_refresh_rate_hz = 100`.

No changes to `DisplayConfig` or `factories.py`; those already carry the field
from the previous PR.

## Tests

| Test | Location | Asserts |
|---|---|---|
| `test_framerate_fraction_default` | `tests/test_frame.py` | `limit_refresh_rate_hz=0` → fraction=1 |
| `test_framerate_fraction_computed` | `tests/test_frame.py` | `limit_refresh_rate_hz=100` → fraction=5 |
| `test_framerate_fraction_rounds` | `tests/test_frame.py` | `limit_refresh_rate_hz=15` → fraction=1 |
| `test_swap_passes_fraction_to_matrix` | `tests/test_frame.py` | `frame.swap()` calls `SwapOnVSync(canvas, 5)` |
| `test_swap_returns_new_canvas` | `tests/test_frame.py` | return value is the back-buffer |
| `test_no_bare_swaponvsync` | `tests/test_swap_centralization.py` | AST tripwire |

## Known limitation

Sections with a non-default `scroll_step_ms` (e.g. 30 ms → ~33 fps) will have
their effective swap rate capped to 20 fps when `limit_refresh_rate_hz` is set,
because `_framerate_fraction` is computed against the fixed engine rate of 20 fps.
Acceptable since `limit_refresh_rate_hz` requires explicit opt-in and most
sections use the default scroll speed.

## Build order

1. `LedFrame._framerate_fraction` + `LedFrame.swap()` + stub update + unit tests
2. `_swap()` helper update + `transitions/__init__.py` (already uses `_swap()`, verify no change)
3. Migrate 7 direct call sites in `gif.py`, `still.py`, `_image_base.py`
4. AST tripwire
5. `config.longboi.toml` — add `limit_refresh_rate_hz = 100`

## Future: overlay_hooks

When the busy-light PR lands, step 1 inside `LedFrame.swap()` becomes:

```python
def swap(self, canvas: Canvas) -> Canvas:
    for hook in self.overlay_hooks:
        hook(canvas)
    return self.matrix.SwapOnVSync(canvas, self._framerate_fraction)
```

No call sites change. The `overlay_hooks: list[Callable[[Canvas], None]]` field
is added to `LedFrame`; the busy-light poller registers/deregisters its paint
callback there.

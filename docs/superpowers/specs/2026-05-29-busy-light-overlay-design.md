# Busy-Light Overlay System + MVP Validator — Design Spec

**Date:** 2026-05-29
**Status:** Draft — pending implementation plan.
**Author:** James + Claude (brainstorming session)

## Summary

Add a persistent on-panel indicator that lights up when the user is "busy." The design splits cleanly into two pieces:

1. **Overlay system** — a generic, mechanism-only compositor: `LedFrame` gains `overlay_hooks: list[Callable[[Canvas], None]]` that `swap()` paints onto the real canvas before every `SwapOnVSync`. Reusable for any future overlay; knows nothing about "busy."
2. **MVP busy light** — the consumer that validates the system: a global service that polls a local file (`~/.busy`) for busy state and registers a paint hook that draws a steady solid corner dot while busy.

The MVP busy light **is** the validation artifact for the overlay system — the simplest no-auth source (file presence) exercising the overlay end-to-end on hardware. Real calendar/Slack/Teams sources are a deliberate follow-up that swaps the source behind the same overlay.

## Why this is small now (compositor already exists)

The prior design (memory `project-busy-light-widget`) called for adding a centralized `LedFrame.swap()`, migrating every `SwapOnVSync` call site to it, and an AST tripwire. **All of that already shipped.** Current state (verified against `frame.py`, `ticker.py`, `transitions/__init__.py`, `widgets/`):

- `LedFrame.swap(canvas) -> Canvas` exists (`frame.py` ~line 97) and is the single hardware-swap point; its docstring already says *"Future overlay_hooks will iterate here before the swap."*
- All ~23 swap sites (engine `ticker._swap`, `run_transition`, `play()`-style gif/still/image widgets) route through `frame.swap()`. The `ticker._swap` helper unwraps `ScaledCanvas` so `frame.swap()` always receives the **real** physical-pixel canvas.
- `tests/test_swap_centralization.py` already AST-forbids raw `*.SwapOnVSync` outside `frame.py`.

So this spec only adds the `overlay_hooks` field + the paint-before-swap loop, plus the busy-light consumer. No migration.

## Goals

- A generic overlay mechanism on `LedFrame` that paints on every render path (engine, transitions, play-widgets) with zero per-call-site changes.
- An MVP busy light: file-driven busy state + a steady corner dot, configurable via `[busy_light]`.
- `LedFrame` stays mechanism-only — it never imports or references "busy."
- Validatable on hardware by `touch ~/.busy` / `rm ~/.busy`.

## Non-goals (deferred)

- **Real busy sources** (Google Calendar, Slack/Teams status). A follow-up adds a source that sets the same `is_busy` flag behind the same overlay; no overlay/compositor change needed.
- **Animation** (blink/pulse/fade). The MVP dot is steady, so the paint hook stays stateless.
- **Multiple-overlay z-ordering policy** beyond list order (hooks paint in registration order).
- **Per-section overlay control** (show/hide per playlist section). The busy light is global by design.
- **`.env` loading.** The MVP needs no secrets; file path comes from config.

## Architecture

```
LedFrame (mechanism)                     BusyLight (consumer, app-scope service)
  overlay_hooks: list[Callable]            is_busy: bool
  swap(canvas):                            update(): is_busy = file_path.exists()
    for h in overlay_hooks: h(canvas)      paint(canvas): if is_busy: draw corner dot
    return matrix.SwapOnVSync(...)

app/run.py wiring (if config.busy_light.enabled):
  busy = BusyLight(...from config...)
  frame.overlay_hooks.append(busy.paint)
  asyncio.create_task(run_monitor_loop(busy, poll_interval, splay=False))
```

Data flow: the background poll task flips `busy.is_busy` from the file; every `frame.swap()` (any render path) calls `busy.paint(canvas)`, which paints the dot iff `is_busy`. This is a single-threaded asyncio app — the poll coroutine (writer) and the render coroutines that call `frame.swap()` (reader) run in the **same event loop**, never interleaving mid-statement, so the shared `is_busy` bool needs no lock.

## Component details

### 1. `LedFrame.overlay_hooks` + `swap()` (`src/led_ticker/frame.py`)

Add the field (empty by default) and the paint loop:

```python
from collections.abc import Callable

    # In the attrs class body:
    overlay_hooks: list[Callable[[Canvas], None]] = attrs.field(factory=list)

    def swap(self, canvas: Canvas) -> Canvas:
        """Swap the back-buffer to the display.

        Runs each overlay hook against the real canvas (physical pixels)
        immediately before the hardware swap, so overlays composite over
        every render path (engine, transitions, play()-style widgets) that
        routes through this single swap point. framerate_fraction pins the
        swap to a fixed scan position to avoid seam tearing.
        """
        for hook in self.overlay_hooks:
            hook(canvas)
        return self.matrix.SwapOnVSync(canvas, self._framerate_fraction)
```

Invariants:
- Hooks receive the **real** canvas (physical px). At scale>1 the `ScaledCanvas` unwrap already happens in `ticker._swap` before `frame.swap(canvas.real)`, so a hook reading `canvas.width`/`height` sees physical dimensions and can place a corner dot correctly.
- Empty `overlay_hooks` ⇒ behavior byte-identical to today.
- Hooks paint via `canvas.SetPixel` (works on real canvas and the test stub). They must not call `SwapOnVSync` or read pixels.
- `LedFrame` imports no widget/busy code — `overlay_hooks` is `list[Callable]` only.

### 2. `BusyLight` service (`src/led_ticker/busy_light.py`, new)

A global service (not a `@register`ed playlist widget — it composites over all sections, so it lives at app scope, not in the playlist):

```python
@attrs.define
class BusyLight:
    file_path: Path
    corner: str = "top_right"           # top_left|top_right|bottom_left|bottom_right
    color: ColorTuple = (255, 0, 0)
    size: int = 4                        # px, square block side
    is_busy: bool = attrs.field(default=False, init=False)

    async def update(self) -> None:
        """Conforms to the Updatable protocol; run by run_monitor_loop."""
        self.is_busy = self.file_path.exists()

    def paint(self, canvas: Canvas) -> None:
        """Overlay hook: draw a size×size block in the corner while busy."""
        if not self.is_busy:
            return
        w, h = canvas.width, getattr(canvas, "height", 16)
        s = max(1, min(self.size, w, h))
        x0 = 0 if "left" in self.corner else w - s
        y0 = 0 if "top" in self.corner else h - s
        r, g, b = self.color
        for dy in range(s):
            for dx in range(s):
                canvas.SetPixel(x0 + dx, y0 + dy, r, g, b)
```

- `file_path` is `Path(...).expanduser()` (resolved at construction).
- A missing file ⇒ `is_busy = False` (no error; `Path.exists()` is false for missing).
- `paint` is the callback appended to `frame.overlay_hooks`.

### 3. Config `[busy_light]` (`src/led_ticker/config.py`)

New dataclass + `AppConfig` field + parse, mirroring `DisplayConfig`/`TransitionConfig`:

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

`AppConfig` gains `busy_light: BusyLightConfig = field(default_factory=BusyLightConfig)`. In `load_config`:

```python
    bl = raw.get("busy_light", {})
    busy_light = BusyLightConfig(
        enabled=bl.get("enabled", False),
        file_path=bl.get("file_path", "~/.busy"),
        poll_interval=bl.get("poll_interval", 5.0),
        corner=bl.get("corner", "top_right"),
        color=tuple(bl.get("color", [255, 0, 0])),
        size=bl.get("size", 4),
    )
```

Validation (inline in `config.py`'s `load_config`, mirroring the existing `coerce_choice(..., valid=...)` pattern used for `[transitions].easing`): `corner` must be one of the four values (raise `ValueError` naming the valid set on a bad value); `size >= 1`.

TOML example:
```toml
[busy_light]
enabled = true
file_path = "~/.busy"
poll_interval = 2.0
corner = "top_right"
color = [255, 0, 0]
size = 4
```

### 4. Wiring (`src/led_ticker/app/run.py`)

The frame is built at `run.py:45` (`led_frame = build_frame_from_config(config.display)`), before the section loop. Add the wiring right after it (file-based busy needs no `aiohttp` session, so it does not need to be inside the `async with ClientSession` block; it does run inside `async def run`, so the event loop is available for `create_task`):

```python
    led_frame = build_frame_from_config(config.display)

    if config.busy_light.enabled:
        from led_ticker.busy_light import BusyLight

        busy = BusyLight(
            file_path=Path(config.busy_light.file_path).expanduser(),
            corner=config.busy_light.corner,
            color=config.busy_light.color,
            size=config.busy_light.size,
        )
        await busy.update()  # fast initial read
        led_frame.overlay_hooks.append(busy.paint)
        asyncio.create_task(
            run_monitor_loop(busy, config.busy_light.poll_interval, splay=False)
        )
```

`splay=False` so it reacts promptly (no random 0–60s offset — this isn't a network source needing splay). `led_frame` is the same instance threaded into `Ticker` (`"frame": led_frame` in the ticker kwargs), so the hook reaches every swap on every render path.

## Testing

### `tests/test_frame.py`
- `swap()` calls each overlay hook exactly once with the canvas, in registration order, BEFORE `matrix.SwapOnVSync` (use a hook that records call order / the canvas it received).
- `swap()` still returns the matrix's back-buffer and forwards `_framerate_fraction` (existing tests stay green).
- Empty `overlay_hooks` ⇒ `swap()` behaves exactly as before (no hook calls).

### `tests/test_busy_light.py` (new)
- `update()` sets `is_busy=True` when `file_path` exists, `False` when absent (use `tmp_path`; create/remove the file between calls).
- `paint()` while busy lights a `size×size` block at the correct origin for each of the four corners on a known-size stub canvas (assert the lit `SetPixel` coords; check both the lit block and that pixels outside it are untouched).
- `paint()` while not busy lights nothing.
- `size` clamps to `>=1` and to the canvas bounds (e.g. `size` larger than the panel doesn't paint out of range).
- `file_path` with `~` expands.

### `tests/test_config.py` (or wherever config parsing is tested)
- `[busy_light]` absent ⇒ `AppConfig.busy_light` is the default (disabled).
- A populated `[busy_light]` parses each field; `color` list → tuple.
- Invalid `corner` raises `ValueError` naming the valid set; `size < 1` raises.

### Integration (`tests/test_busy_light.py` or `test_frame.py`)
- Construct a `LedFrame` (stub matrix), append `BusyLight.paint`, set busy, call `frame.swap(canvas)`; assert the corner block is lit on the swapped canvas. Set not-busy, swap, assert clean.

## Files affected

| File | Change |
|---|---|
| `src/led_ticker/frame.py` | Add `overlay_hooks` field; iterate hooks in `swap()` before `SwapOnVSync`. |
| `src/led_ticker/busy_light.py` | **New.** `BusyLight` service: `update()` (file poll) + `paint()` (corner dot). |
| `src/led_ticker/config.py` | `BusyLightConfig` dataclass; `AppConfig.busy_light`; parse `[busy_light]`; corner/size validation. |
| `src/led_ticker/app/run.py` | If enabled: build `BusyLight`, register `paint` on `frame.overlay_hooks`, start `run_monitor_loop`. |
| `tests/test_frame.py` | Overlay-hook swap tests. |
| `tests/test_busy_light.py` | **New.** `update`/`paint`/corner/clamp/integration tests. |
| `tests/test_config.py` | `[busy_light]` parse + validation tests. |
| `config/config.example.toml` (+ bigsign example) | Commented `[busy_light]` block documenting the knobs. |
| `CLAUDE.md` | One bullet: `LedFrame.overlay_hooks` is the generic overlay mechanism; `BusyLight` is the first consumer; real sources are future. |

## Future (out of scope, design-compatible)

A real source (calendar/Slack/Teams) becomes a new poller object whose `update()` sets `is_busy` from an API (using the central `aiohttp.ClientSession`, `os.getenv` secrets, `run_monitor_loop` with `splay=True`). It registers the same kind of `paint` hook — or the corner-dot paint is factored into a shared helper both sources reuse. No change to `LedFrame.overlay_hooks` or `swap()`.

## Acceptance criteria

- `make test`, `make lint`, `make typecheck` clean.
- `LedFrame.swap()` runs overlay hooks before the swap; empty list unchanged; existing `test_swap_centralization.py` and `test_frame.py` stay green.
- With `[busy_light] enabled = true`, `touch ~/.busy` lights the configured corner dot within `poll_interval`; `rm ~/.busy` clears it. The dot stays visible across section transitions (proves the centralized-swap coverage).
- `LedFrame` contains no reference to "busy."

"""LED matrix frame wrapper — backend-agnostic render mechanism."""

from collections.abc import Callable
from typing import Any, TypeIs

import attrs

from led_ticker import pixel_emoji, status_board
from led_ticker._types import Canvas
from led_ticker.backends import Backend, BackendNotReadyError


def _is_int(value: Any) -> TypeIs[int]:
    """True for a real int — bool is an int subclass and must not count."""
    return isinstance(value, int) and not isinstance(value, bool)


def floor_tick_ms(frame: Any, nominal_ms: int) -> int:
    """The wall clock a loop really spends per tick: *nominal_ms* floored
    at the frame's `swap_interval_ms`, when that is a real int.

    Cadence loops pass this (not the nominal) to
    `FrameAwareBase.advance_frame_elapsed` / `_settle_ticks`. The nominal
    tick itself still drives sleep, gif frame pick and traversal length.
    A frame without the property, or a Mock frame (the engine tests), has
    no floor — ``max(int, Mock)`` would raise, so the guard is explicit.
    """
    interval = getattr(frame, "swap_interval_ms", None)
    if _is_int(interval):
        return max(nominal_ms, interval)
    return nominal_ms


@attrs.define
class LedFrame:
    """Backend-agnostic frame: overlay hooks, status-board swap recording, the
    preview tee, and framerate live here. The backend owns the matrix
    lifecycle. Nothing outside LedFrame touches the backend directly."""

    backend: Backend
    overlay_hooks: list[Callable[[Canvas], None]] = attrs.field(factory=list)
    _preview_tee: Any = attrs.field(init=False, default=None)
    _ready: bool = attrs.field(init=False, default=False)
    # The buffer the most recent swap() returned — by definition off-screen.
    # get_clean_canvas() recycles it instead of allocating: on the real
    # backend every backend.create_canvas() is a C++ CreateFrameCanvas()
    # retained until process exit (never freed), so steady-state paths must
    # never allocate. None until the first swap of the process.
    _last_back: Any = attrs.field(init=False, default=None)

    def setup(self) -> None:
        """Build the backend's matrix (privilege-drop boundary, constraint
        #13) and mark the frame ready. Call exactly once, after all pre-drop
        privileged work (prepare_dir, validation) and before any consumer that
        needs a live backend (preview tee, brightness scheduler)."""
        self.backend.setup()
        self._ready = True

    def _require_ready(self) -> None:
        if not self._ready:
            raise BackendNotReadyError(
                "backend not set up — call LedFrame.setup() before drawing"
            )

    @property
    def brightness(self) -> int:
        self._require_ready()
        return self.backend.brightness

    @brightness.setter
    def brightness(self, value: int) -> None:
        self._require_ready()
        self.backend.brightness = value

    @property
    def swap_interval_ms(self) -> int:
        """Minimum wall clock one `swap()` takes on this backend, in ms —
        0 when the backend has no such floor (uncapped, headless, Mock).

        The rgbmatrix backend swaps with ``SwapOnVSync(canvas,
        framerate_fraction)``, which BLOCKS until a refresh where
        ``frame_count % fraction == 0``: on a `limit_refresh_rate_hz`-capped
        sign every swap takes ``fraction / hz`` seconds — INCLUDING
        ``fraction == 1`` (a cap below 30 Hz), where it still waits for the
        next refresh, so 20 Hz swaps every 50 ms and 25 Hz every 40 ms
        (#525 cycle-2 finding 1). A loop whose nominal tick is shorter
        really ticks at this interval; cadence math (`floor_tick_ms`) floors
        the banked tick here so a frame stays 50 ms of wall clock on capped
        signs. Rounded to the nearest ms (30 Hz → 2/30 s → 67, not 66).
        Pre-`setup()` the backend's `framerate_fraction` is still its
        default 1, so a capped backend reads ``1000 / hz`` until setup.

        Read duck-typed off the backend — deliberately NOT part of the
        `Backend` protocol, so third-party backends and the conformance
        suite are untouched. Only real ints count (bool excluded; a Mock
        backend answers every attribute with a Mock → 0).
        """
        backend = self.backend
        fraction = getattr(backend, "framerate_fraction", None)
        hz = getattr(backend, "led_limit_refresh_rate_hz", None)
        if not (_is_int(fraction) and _is_int(hz)):
            return 0
        if hz <= 0:
            return 0
        return round(fraction * 1000 / hz)

    def install_preview(self, tee: Any) -> None:
        """Install the (single, process-lifetime) preview tee."""
        self._preview_tee = tee

    def create_canvas(self) -> Canvas:
        """Raw back-buffer canvas (no Clear, no tee). Used by the preview-tee
        setup and cross-scale transitions."""
        self._require_ready()
        return self.backend.create_canvas()

    def get_clean_canvas(self) -> Canvas:
        """A cleared canvas ready for rendering (tee-aware).

        Recycles the buffer the most recent swap() returned instead of
        allocating (see _last_back). Only before the first swap of the
        process does this fall back to backend.create_canvas().

        Aliasing contract: a call site must never draw through or swap a
        previously fetched canvas after a subsequent fetch — the second
        fetch Clears (and hands out) the same recycled buffer, so drawing
        into or swapping the stale reference corrupts whatever the new
        fetch is building. Merely holding a dead reference (never drawn
        through or swapped again) is harmless.
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

    def swap(self, canvas: Canvas) -> Canvas:
        """Single centralized swap point. Overlay hooks paint on the real
        canvas before the backend swap; status_board records liveness. Hooks
        must be paint-only and not raise (see CLAUDE.md overlay invariant)."""
        self._require_ready()
        pixel_emoji.tick_image_animations()  # advance inline-image frames
        # (guarded internally — never raises into the swap; see the
        # CLAUDE.md swap-responsibilities invariant)
        for hook in self.overlay_hooks:
            hook(canvas)
        status_board.record_swap()
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

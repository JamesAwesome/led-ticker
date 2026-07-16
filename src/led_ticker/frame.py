"""LED matrix frame wrapper — backend-agnostic render mechanism."""

from collections.abc import Callable
from typing import Any

import attrs

from led_ticker import status_board
from led_ticker._types import Canvas
from led_ticker.backends import Backend, BackendNotReadyError


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

    def swap(self, canvas: Canvas) -> Canvas:
        """Single centralized swap point. Overlay hooks paint on the real
        canvas before the backend swap; status_board records liveness. Hooks
        must be paint-only and not raise (see CLAUDE.md overlay invariant)."""
        self._require_ready()
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

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
        """A cleared canvas ready for rendering (tee-aware)."""
        self._require_ready()
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
        ff = self.backend.framerate_fraction
        tee = self._preview_tee
        if tee is not None and canvas is tee:
            new_hw = self.backend.swap(tee._hw, ff)
            tee.maybe_capture()
            tee._hw = new_hw
            return tee
        return self.backend.swap(canvas, ff)

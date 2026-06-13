"""Busy-light overlay service.

Polls a local file for busy state and paints a steady corner dot via a
LedFrame overlay hook. The mechanism (LedFrame.overlay_hooks) is generic;
this is its first consumer. Real busy sources (calendar/Slack) are a
follow-up that sets the same is_busy flag behind the same overlay.
"""

import time
from pathlib import Path

import attrs

from led_ticker._types import Canvas, ColorTuple


@attrs.define
class BusyLight:
    """Polls `file_path` for busy state; paints a corner dot while busy."""

    file_path: Path = attrs.field(converter=lambda p: Path(p).expanduser())
    corner: str = "top_right"
    color: ColorTuple = (255, 0, 0)
    size: int = 4
    ttl_seconds: float = 0.0
    is_busy: bool = attrs.field(default=False, init=False)
    _busy_until: float | None = attrs.field(default=None, init=False)

    async def update(self) -> None:
        """Conforms to the Updatable protocol; driven by run_monitor_loop."""
        self.is_busy = self.file_path.exists()

    def set_busy(
        self, state: bool, now: float | None = None, ttl: float | None = None
    ) -> None:
        """Set busy state from a push source. When `state` is True, arms the
        TTL deadline using `ttl` (a per-request override) when given, else the
        configured `ttl_seconds`. A non-positive effective TTL means "stay on
        until an explicit off" and clears any prior deadline. `state=False`
        clears immediately."""
        if state:
            self.is_busy = True
            effective_ttl = self.ttl_seconds if ttl is None else ttl
            if effective_ttl > 0:
                t = time.monotonic() if now is None else now
                self._busy_until = t + effective_ttl
            else:
                self._busy_until = None
        else:
            self.is_busy = False
            self._busy_until = None

    def tick_ttl(self, now: float | None = None) -> None:
        """Clear busy state once the TTL deadline passes. No-op when no
        deadline is armed. Kept off the paint path so paint() stays
        paint-only."""
        if self._busy_until is None:
            return
        t = time.monotonic() if now is None else now
        if t >= self._busy_until:
            self.is_busy = False
            self._busy_until = None

    def ttl_remaining(self, now: float | None = None) -> float | None:
        """Seconds-from-now until the armed deadline clears the busy state,
        clamped at 0.0; None when no deadline is armed. Read-only — does NOT
        mutate state (unlike tick_ttl). Lets a reader (the web status
        heartbeat) report the remaining time without reaching into the
        private _busy_until, keeping busy_light import-free of the web stack."""
        if self._busy_until is None:
            return None
        t = time.monotonic() if now is None else now
        return max(0.0, self._busy_until - t)

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

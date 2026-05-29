"""Busy-light overlay service.

Polls a local file for busy state and paints a steady corner dot via a
LedFrame overlay hook. The mechanism (LedFrame.overlay_hooks) is generic;
this is its first consumer. Real busy sources (calendar/Slack) are a
follow-up that sets the same is_busy flag behind the same overlay.
"""

from __future__ import annotations

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

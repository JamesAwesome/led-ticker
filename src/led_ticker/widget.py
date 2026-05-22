"""Widget protocols and shared lifecycle helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

from led_ticker._types import Canvas, DrawResult

logger: logging.Logger = logging.getLogger(__name__)

# Backoff limits for run_monitor_loop
_MIN_BACKOFF: int = 60  # 1 minute minimum on error
_MAX_BACKOFF: int = 3600  # 1 hour maximum backoff


@runtime_checkable
class Widget(Protocol):
    """Any object that can draw itself to an LED canvas."""

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        """Render to canvas starting at cursor_pos.

        ``y_offset``: vertical offset from the widget's natural baseline.
        ``font_color``: override the widget's own font color (Color or ColorProvider).

        ``scale`` is **not** a param. If ``canvas`` is a ``ScaledCanvas``,
        scaling is transparent. Widgets that need to read scale can use
        ``getattr(canvas, "scale", 1)``.

        Returns (canvas, new_cursor_pos).
        """
        ...


@runtime_checkable
class Updatable(Protocol):
    """Any object that can update itself asynchronously."""

    async def update(self) -> None:
        """Fetch fresh data from an external source."""
        ...


@runtime_checkable
class Playable(Protocol):
    """Any widget that runs its own async display loop via ``play()``."""

    async def play(
        self,
        real_canvas: Canvas,
        frame: Any,
        loop_count: int = 1,
        *,
        hold_time: float | None = None,
    ) -> Canvas:
        """Drive the display until cancelled."""
        ...


@runtime_checkable
class FrameAwareWidget(Protocol):
    """Widget that tracks per-effect frame counters for animated ColorProviders,
    BorderEffects, and Animations. Implement by inheriting ``_FrameAware`` from
    ``widgets/_frame_aware.py`` — do not implement these methods manually."""

    def advance_frame(self) -> None: ...
    def pause_frame(self) -> None: ...
    def resume_frame(self) -> None: ...
    def reset_frame(self) -> None: ...
    def frame_for(self, effect_name: str) -> int: ...


async def run_monitor_loop(
    widget: Updatable,
    interval: float,
    splay: bool = True,
) -> None:
    """Generic monitor loop with exponential backoff on errors.

    On success, waits `interval` seconds before the next update.
    On error, backs off exponentially from 60s to 1 hour, then
    resets to `interval` on the next successful update.
    """
    if splay:
        from random import randint

        interval += randint(0, 60)

    consecutive_errors: int = 0

    while True:
        if consecutive_errors > 0:
            backoff = min(
                _MAX_BACKOFF,
                _MIN_BACKOFF * (2 ** (consecutive_errors - 1)),
            )
            logger.warning(
                "%s: backing off %ds after %d consecutive errors",
                type(widget).__name__,
                backoff,
                consecutive_errors,
            )
            await asyncio.sleep(backoff)
        else:
            await asyncio.sleep(interval)

        try:
            await widget.update()
            consecutive_errors = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_errors += 1
            logger.exception(
                "Error updating %s (attempt %d), will back off",
                type(widget).__name__,
                consecutive_errors,
            )

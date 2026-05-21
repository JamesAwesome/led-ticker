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
        **kwargs: Any,
    ) -> DrawResult:
        """Render to canvas starting at cursor_pos.

        Recognized kwargs:
        - ``y_offset`` (int): vertical offset from natural baseline
        - ``font_color`` (Color): override the widget's own font color

        ``scale`` is **not** a kwarg. If ``canvas`` is a ``ScaledCanvas``,
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
class AsyncWidget(Widget, Protocol):
    """A widget that fetches data asynchronously and updates itself."""

    async def update(self) -> None:
        """Fetch fresh data from an external source."""
        ...


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

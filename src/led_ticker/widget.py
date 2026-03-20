"""Widget protocols and shared lifecycle helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Widget(Protocol):
    """Any object that can draw itself to an LED canvas."""

    def draw(self, canvas: Any, cursor_pos: int = 0, **kwargs) -> tuple[Any, int]:
        """Render to canvas starting at cursor_pos.

        Returns (canvas, new_cursor_pos).
        """
        ...


@runtime_checkable
class AsyncWidget(Widget, Protocol):
    """A widget that fetches data asynchronously and updates itself."""

    async def update(self) -> None:
        """Fetch fresh data from an external source."""
        ...


async def run_monitor_loop(
    widget: AsyncWidget,
    interval: float,
    splay: bool = True,
) -> None:
    """Generic monitor loop with error handling.

    Call after the widget's initial update(). Runs forever, calling
    widget.update() every `interval` seconds.
    """
    if splay:
        from random import randint

        interval += randint(0, 60)

    while True:
        await asyncio.sleep(interval)
        try:
            await widget.update()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Error updating %s, will retry in %s seconds",
                type(widget).__name__,
                interval,
            )

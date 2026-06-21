"""Widget protocols and shared lifecycle helpers."""

import asyncio
import contextvars
import logging
from typing import Any, Protocol, runtime_checkable

from led_ticker import status_board
from led_ticker._types import Canvas, DrawResult

logger: logging.Logger = logging.getLogger(__name__)

# Backoff limits for run_monitor_loop
_MIN_BACKOFF: int = 60  # 1 minute minimum on error
_MAX_BACKOFF: int = 3600  # 1 hour maximum backoff

# Strong references to fire-and-forget background tasks. The event loop only
# holds WEAK references to tasks, so a task with no strong reference elsewhere
# can be garbage-collected mid-flight ("Task was destroyed but it is pending!").
# Every long-lived background task (data-widget pollers, the busy-light HTTP
# listener and TTL ticker) is spawned through spawn_tracked() so it stays rooted.
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()

# When set (around a single widget build), spawn_tracked also records the task here
# so the caller can cancel exactly that widget's background tasks on a config reload.
# A ContextVar (not a plain global) so concurrent builds can't cross-contaminate.
_build_sink: contextvars.ContextVar[set[asyncio.Task[Any]] | None] = (
    contextvars.ContextVar("led_ticker_build_sink", default=None)
)


def spawn_tracked(coro: Any) -> asyncio.Task[Any]:
    """asyncio.create_task + keep a strong reference until the task completes.

    The event loop only weakly references tasks; without this a task awaiting a
    rootless primitive (e.g. asyncio.Event().wait()) can be GC'd mid-flight.

    If a build sink is active (config-reload widget build), the task is recorded
    there too so it can be cancelled when that widget is evicted.
    """
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    sink = _build_sink.get()
    if sink is not None:
        sink.add(task)
        task.add_done_callback(sink.discard)
    return task


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
    BorderEffects, and Animations. Implement by inheriting ``FrameAwareBase`` from
    ``widgets/_frame_aware.py`` — do not implement these methods manually."""

    def advance_frame(self, *, visit_id: int | None = None) -> None: ...
    def pause_frame(self) -> None: ...
    def resume_frame(self) -> None: ...
    def reset_frame(self) -> None: ...
    def frame_for(self, effect_name: str) -> int: ...


@runtime_checkable
class Container(Protocol):
    """Widget that expands into a live, mutable list of child widgets.

    The engine re-reads `feed_stories` on every pass through the section,
    so updates from the container's background `update()` task are picked
    up without requiring the outer section loop to cycle. Without this,
    a `loop_count = 0` section would snapshot stories at section-build
    time and never refresh.
    """

    feed_stories: list[Widget]


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
            status_board.record_monitor_update(
                getattr(widget, "name", None) or type(widget).__name__
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_errors += 1
            logger.exception(
                "Error updating %s (attempt %d), will back off",
                type(widget).__name__,
                consecutive_errors,
            )

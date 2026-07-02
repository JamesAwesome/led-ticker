"""Widget protocols and shared lifecycle helpers."""

import asyncio
import contextlib
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
    immediate: bool = False,
    *,
    register_monitor: bool = True,
) -> None:
    """Generic monitor loop with exponential backoff on errors.

    On success, waits `interval` seconds before the next update.
    On error, backs off exponentially from 60s to 1 hour, then
    resets to `interval` on the next successful update.

    When ``immediate`` is True, the FIRST ``update()`` runs before the initial
    ``interval`` wait, so a polled source shows real data within one request
    instead of after a full interval (otherwise a 15-30 min blank for weather).
    Data widgets leave it False: they eager-fetch in ``start()`` before spawning
    the loop, so an immediate first cycle here would double-fetch. Only the first
    cycle is affected; the error-backoff path is unchanged.

    ``register_monitor`` (default True) controls whether this rider appears in
    the status-board monitor roster. Set to False only for riders that are NOT
    data monitors (e.g. busy_light — a visual-overlay helper). When False, no
    registration or update/error recording occurs; a DEBUG log marks the opt-out.
    There is no shape allow-list: any Updatable is registered by default.
    No import of ``sources`` (circular).
    """
    # Register in the monitor roster (best-effort). Registration is UNCONDITIONAL
    # when register_monitor=True — no shape check gates it. Kind is derived from
    # the explicit .polled marker (DataSource sets it) vs a plain widget tag.
    # The only opt-out is register_monitor=False (busy_light); that emits a DEBUG
    # log and skips registration entirely (_mon_name stays None).
    _mon_name = None
    if not register_monitor:
        with contextlib.suppress(Exception):
            logger.debug(
                "monitor loop started (unregistered): %s",
                type(widget).__name__,
            )
    else:
        with contextlib.suppress(Exception):
            _name = status_board._monitor_name(widget)
            _mtype = status_board._monitor_type(widget)
            kind = "source" if getattr(widget, "polled", False) else "widget"
            _mon_name = status_board.register_monitor(
                _name, kind, interval, mtype=_mtype
            )
            logger.info(
                "monitor loop started: %s (%s, every %gs)",
                _name,
                kind,
                interval,
            )

    if splay:
        from random import randint

        interval += randint(0, 60)

    consecutive_errors: int = 0
    first: bool = True

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
        elif not (first and immediate):
            await asyncio.sleep(interval)
        first = False

        try:
            await widget.update()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            consecutive_errors += 1
            if _mon_name is not None:
                retry_in = min(
                    _MAX_BACKOFF, _MIN_BACKOFF * (2 ** (consecutive_errors - 1))
                )
                # Belt-and-suspenders: recorder is internally guarded, but wrap
                # the call site too — instrumentation must never reach the loop.
                with contextlib.suppress(Exception):
                    status_board.record_monitor_error(
                        _mon_name, str(exc)[:200], consecutive_errors, retry_in
                    )
            logger.exception(
                "Error updating %s (attempt %d), will back off",
                type(widget).__name__,
                consecutive_errors,
            )
        else:
            # `else` runs only when update() did NOT raise — so a raise in
            # _monitor_value / record_monitor_update cannot be miscounted as
            # an update failure (would have bumped consecutive_errors and
            # logged "Error updating" for a SUCCESSFUL update).
            consecutive_errors = 0
            if _mon_name is not None:
                with contextlib.suppress(Exception):
                    status_board.record_monitor_update(
                        _mon_name, status_board._monitor_value(widget)
                    )

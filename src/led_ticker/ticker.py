"""Display orchestrator for scrolling/swapping widgets on LED panels."""

import asyncio
import inspect
import itertools
import logging
import math
from collections.abc import Callable, Iterator
from typing import Any

import attrs

from led_ticker import status_board
from led_ticker._types import Canvas
from led_ticker.colors import RGB_WHITE
from led_ticker.drawing import get_widget_padding
from led_ticker.render_breaker import RenderBreaker, guard_for_transition
from led_ticker.scaled_canvas import ScaledCanvas, is_scaled, unwrap_to_real
from led_ticker.separator import (
    _CIRCLE_LOGICAL_PAD,
    DEFAULT_CIRCLE_SPEC,
    DEFAULT_DOT_SPEC,
    SCROLL_GAP,
    SeparatorSpec,
    render_separator,
    scroll_separator_width,
)
from led_ticker.widgets._image_fit import reset_canvas
from led_ticker.widgets.message import TickerMessage

logger: logging.Logger = logging.getLogger(__name__)


class RestartRequested(Exception):
    """Raised inside the per-tick display loops when a web-UI restart marker
    is present, so the engine unwinds promptly (within a few seconds) instead
    of waiting for the next full playlist cycle.

    The `restart_check` callback (see `Ticker.restart_check`) is responsible
    for consuming (deleting) the marker BEFORE this is raised — loop-safety:
    the restarted process must not re-read the marker and exit again. The
    app-level loop catches this and calls `sys.exit(0)` for a clean
    supervisor restart.
    """


@attrs.define
class _CircleBufferMsg(TickerMessage):
    """ticker buffer separator. Auto-routes to a hi-res circle
    when the canvas is a ScaledCanvas; falls back to TickerMessage's
    BDF rendering on plain canvases (smallsign / scale=1).

    Not a registered widget \u2014 users never configure this directly.
    Constructed by ticker.DEFAULT_BUFFER_MSG and by app._resolve_buffer_msg
    for color-only sections.

    Continuous-phase color sweep (Rainbow / ColorCycle) is provided
    automatically by the provider's class-level `restart_on_visit =
    False` \u2014 FrameAwareBase reads that attribute via getattr on the
    provider, not on the widget.
    """

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ):
        if is_scaled(canvas):
            advance = render_separator(
                canvas,
                cursor_pos + _CIRCLE_LOGICAL_PAD,
                self.frame_for("font_color"),
                attrs.evolve(DEFAULT_CIRCLE_SPEC, color=self.font_color),
            )
            new_pos = cursor_pos + _CIRCLE_LOGICAL_PAD + advance + _CIRCLE_LOGICAL_PAD
            return canvas, new_pos
        return super().draw(
            canvas, cursor_pos, y_offset=y_offset, font_color=font_color
        )


DEFAULT_BUFFER_MSG: TickerMessage = _CircleBufferMsg(
    text=" \u2022 ", center=False, font_color=RGB_WHITE
)


def _has_index(index: int, items: list[Any]) -> bool:
    """Check if a list has an index."""
    try:
        items[index]
    except IndexError:
        return False
    return True


def _swap(canvas: Any, frame: Any) -> Any:
    """SwapOnVSync that handles both real canvases and ScaledCanvas wrappers.

    For real canvases: returns the new back-buffer canvas.
    For ScaledCanvas: swaps the underlying real canvas in place and returns
    the same wrapper (now pointing at the new back-buffer).
    """
    if is_scaled(canvas):
        canvas.real = frame.swap(canvas.real)
        return canvas
    return frame.swap(canvas)


def _maybe_wrap(canvas: Any, scale: int, content_height: int = 16) -> Any:
    """Wrap canvas in a ScaledCanvas when the logical size differs from physical.

    Wraps when scale > 1 (bigsign) OR when content_height is smaller than the
    raw canvas height (scale=1 bigsign running a narrow content region). In
    both cases the wrapper's y_offset_real centers the content band and widgets
    read canvas.height == content_height instead of the raw panel height.

    `content_height` controls the wrapper's logical height. Default 16 matches
    a single 5x8 / 6x12 row. Sections that need vertical breathing room (e.g.
    the two_row layout) can request a taller logical canvas by passing
    `content_height=20` etc.
    """
    if scale > 1 or content_height < canvas.height:
        return ScaledCanvas(canvas, scale=scale, content_height=content_height)
    return canvas


@attrs.define
class Ticker:
    """Display orchestrator for an LedFrame."""

    monitors: list[Any]
    frame: Any
    title: Any = None
    title_delay: int = 4
    buffer_msg: Any = attrs.Factory(lambda: DEFAULT_BUFFER_MSG)
    notif_queue: asyncio.Queue[Any] | None = None
    transition_config: Any = None
    transition_fn: Any = None
    hold_time: float = 3.0
    continuous_scroll: bool = False
    scale: int = 1
    content_height: int = 16
    # Per-pixel scroll cadence in seconds. Default 0.05 (= 1 logical
    # pixel per engine tick) matches ENGINE_TICK_MS. Sourced from
    # `section.scroll_step_ms / 1000` in app.py — None falls back
    # to this default.
    scroll_speed: float = 0.05
    breaker: RenderBreaker = attrs.field(factory=RenderBreaker)
    # Optional zero-arg predicate polled once per engine tick. When it returns
    # True, the engine raises RestartRequested to unwind promptly for a web-UI
    # restart. The callback MUST consume (delete) the restart marker before
    # returning True — loop-safety, so the restarted process doesn't re-read
    # the marker and exit again. None disables the in-tick check entirely.
    restart_check: Callable[[], bool] | None = None
    last_scroll_pos: int = attrs.field(init=False, default=0)
    _visit_counter: int = attrs.field(init=False, default=0)
    _current_visit: int = attrs.field(init=False, default=0)
    _enqueue_task: asyncio.Task | None = attrs.field(init=False, default=None)

    @classmethod
    def from_rss_feed(
        cls,
        feed_monitor: Any,
        frame: Any,
        custom_title: Any = None,
        title_delay: int = 4,
        buffer_msg: Any = None,
        notif_queue: asyncio.Queue[Any] | None = None,
    ) -> Ticker:
        title = custom_title if custom_title else feed_monitor.feed_title
        if buffer_msg is None:
            buffer_msg = DEFAULT_BUFFER_MSG
        return cls(
            monitors=feed_monitor.feed_stories,
            frame=frame,
            title=title,
            title_delay=title_delay,
            buffer_msg=buffer_msg,
            notif_queue=notif_queue,
        )

    async def run_slideshow(self, loop_count: int = 0) -> None:
        """Swap between all running monitors."""
        logging.info("Running Slideshow with loop count %s...", loop_count)
        canvas = _maybe_wrap(
            self.frame.get_clean_canvas(), self.scale, self.content_height
        )
        title = self.title if self.title else None
        assert self.notif_queue is not None

        self._enqueue_task = asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
                breaker=self.breaker,
            )
        )
        self._enqueue_task.add_done_callback(
            lambda t: (
                logging.error("enqueue task failed: %s", t.exception())
                if not t.cancelled() and t.exception() is not None
                else None
            )
        )

        self.last_scroll_pos = await self._run_swap(
            canvas,
            delay=self.title_delay,
            hold_time=self.hold_time,
            continuous_scroll=self.continuous_scroll,
        )

    async def run_ticker(
        self, loop_count: int = 0, start_pos: int | None = None
    ) -> None:
        """Scroll all monitors side-by-side in a continuous stream."""
        logging.info("Running Ticker with loop count %s...", loop_count)
        canvas = _maybe_wrap(
            self.frame.get_clean_canvas(), self.scale, self.content_height
        )
        title = self.title if self.title else None
        cursor_pos = start_pos if start_pos is not None else canvas.width
        assert self.notif_queue is not None

        self._enqueue_task = asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
                breaker=self.breaker,
            )
        )
        self._enqueue_task.add_done_callback(
            lambda t: (
                logging.error("enqueue task failed: %s", t.exception())
                if not t.cancelled() and t.exception() is not None
                else None
            )
        )

        self.last_scroll_pos = await self._scroll_side_by_side(
            canvas,
            delay=self.title_delay,
            cursor_pos=cursor_pos,
            hold_at_end=self.hold_time,
        )

    async def run_one_at_a_time(
        self, loop_count: int = 0, start_pos: int | None = None
    ) -> None:
        """Scroll monitors one-by-one, each fully scrolling off before the next."""
        logging.info("Running One-at-a-time with loop count %s...", loop_count)
        canvas = _maybe_wrap(
            self.frame.get_clean_canvas(), self.scale, self.content_height
        )
        title = self.title if self.title else None
        assert self.notif_queue is not None

        self._enqueue_task = asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
                breaker=self.breaker,
            )
        )
        self._enqueue_task.add_done_callback(
            lambda t: (
                logging.error("enqueue task failed: %s", t.exception())
                if not t.cancelled() and t.exception() is not None
                else None
            )
        )

        cursor_pos = start_pos if start_pos is not None else canvas.width

        self.last_scroll_pos = await self._scroll_one_by_one(
            canvas,
            cursor_pos=cursor_pos,
            delay=self.title_delay,
        )

    # --- Engine helper methods (migrated from module-level) ---

    @staticmethod
    def _has_play(widget: Any) -> bool:
        """True iff ``widget``'s class declares an async ``play`` method.

        Looks at the class (not the instance) so Mocks — which auto-create
        a callable ``.play`` attribute on access — don't false-positive.

        Raises ``RuntimeError`` if the class has a ``play`` attribute that is
        NOT a coroutinefunction: that is almost certainly a missing ``async``
        keyword and would silently route the widget to the ``draw()`` path.
        """
        method = getattr(type(widget), "play", None)
        if method is None:
            return False
        if not inspect.iscoroutinefunction(method):
            raise RuntimeError(
                f"{type(widget).__name__}.play exists but is not a coroutine function. "
                "Did you forget 'async def play'?"
            )
        return True

    @staticmethod
    def _set_logical_scale(widget: Any, scale: int) -> None:
        """Stash the section's logical canvas scale on a play()-style
        widget BEFORE the ScaledCanvas is unwrapped, so the widget can
        interpret logical-unit knobs (e.g. `top_row_height`) when it
        receives the raw real canvas. Best-effort — silently no-ops on
        widgets that don't declare the `_logical_scale` field (only
        `_BaseImageWidget` does today).
        """
        if hasattr(widget, "_logical_scale"):
            widget._logical_scale = scale

    def _advance_frame_if_supported(self, widget: Any) -> None:
        """Call `widget.advance_frame(visit_id=self._current_visit)` if supported.

        Quietly no-ops on widgets without the FrameAwareBase mixin.
        Passes the current visit ID so FrameAwareBase can detect aliasing bugs
        (same widget instance advancing in two concurrent section visits).
        """
        if hasattr(widget, "advance_frame"):
            widget.advance_frame(visit_id=self._current_visit)

    @staticmethod
    def _resolve_now_if_supported(widget: Any) -> None:
        """Force a widget to resolve its inline value tokens + invalidate
        its width cache, if it supports the hook.

        Called immediately BEFORE a scroll's `stop_pos` is computed so the
        scroll measures the current value; resolution is then locked for
        the loop so a 1 Hz source update can't move the width mid-scroll
        (constraints #6/#7). Quietly no-ops on widgets without tokens."""
        fn = getattr(widget, "resolve_tokens_now", None)
        if callable(fn):
            fn()

    @staticmethod
    def _lock_resolution_if_supported(widget: Any, locked: bool) -> None:
        """Set/clear a widget's `_resolution_locked` freeze flag if present.

        Duck-typed parallel to the `pause_frame`/`resume_frame` freeze —
        used by the scroll branch (where transitions don't run) to freeze
        token re-resolution for the scroll loop and release it after."""
        if hasattr(widget, "_resolution_locked"):
            widget._resolution_locked = locked

    def _maybe_restart(self) -> None:
        """Poll the restart_check callback once. If it returns True, raise
        RestartRequested so the engine unwinds promptly for a web-UI restart.

        Called at the top of every per-tick loop body so a queued restart is
        honoured within ~one engine tick (tens of ms) rather than waiting for
        the next full playlist cycle. The callback consumes (deletes) the
        marker itself before returning True — loop-safety. Cheap: a tmpfs
        `stat` per tick. None disables the check.
        """
        if self.restart_check is not None and self.restart_check():
            raise RestartRequested

    def _safe_draw(
        self, widget: Any, canvas: Any, cursor_pos: int = 0
    ) -> tuple[Any, int]:
        """Guard one draw() call. On a render error: trip the widget and return
        the canvas unchanged (no advance) so the swap still captures a valid
        canvas (constraint #1). Already-disabled -> short-circuit before draw().
        Fallback leaves the canvas as-is; the per-tick reset_canvas already wipes
        any partial frame on the next tick (no Clear here)."""
        if self.breaker.is_disabled(widget):
            return canvas, cursor_pos
        try:
            return widget.draw(canvas, cursor_pos=cursor_pos)
        except Exception as exc:
            self.breaker.trip(widget, exc)
            return canvas, cursor_pos

    async def _hold_ticks(
        self,
        canvas: Canvas,
        widget: Any,
        n_ticks: int,
        pos: int,
        bg_color: Any,
    ) -> tuple[Canvas, int]:
        """Run `n_ticks` drift-compensated ticks: advance → draw → swap → sleep."""
        tick_seconds = ENGINE_TICK_MS / 1000
        loop = asyncio.get_running_loop()
        cursor_pos = 0
        for _ in range(n_ticks):
            self._maybe_restart()
            t0 = loop.time()
            self._advance_frame_if_supported(widget)
            reset_canvas(canvas, bg_color)
            canvas, cursor_pos = self._safe_draw(widget, canvas, pos)
            canvas = _swap(canvas, self.frame)
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
        return canvas, cursor_pos

    async def _play_widget(
        self, canvas: Any, widget: Any, *, section_hold_time: float = 3.0
    ) -> Any:
        """Hand the canvas off to a widget's `play()` method.

        Used by widgets that drive their own animation loop (e.g. GifPlayer).
        Unwraps any ScaledCanvas wrappers so the widget paints at native
        physical resolution; the wrapper is re-anchored to the new
        back-buffer canvas afterward so subsequent draws stay scaled.

        ``section_hold_time`` is forwarded to ``widget.play()`` as ``hold_time``
        so gif widgets with ``play_count = 0`` can compute how many loops fit in
        the section's duration.
        """
        if self.breaker.is_disabled(widget):
            return canvas
        loops = getattr(widget, "play_count", 1) or 1
        try:
            if is_scaled(canvas):
                Ticker._set_logical_scale(widget, canvas.scale)
                new_real = await widget.play(
                    unwrap_to_real(canvas),
                    self.frame,
                    loop_count=loops,
                    hold_time=section_hold_time,
                )
                canvas.rebind_innermost(new_real)
                return canvas
            Ticker._set_logical_scale(widget, 1)
            return await widget.play(
                canvas, self.frame, loop_count=loops, hold_time=section_hold_time
            )
        except Exception as exc:
            self.breaker.trip(widget, exc)
            return canvas

    async def _scroll_between(
        self,
        canvas: Canvas,
        outgoing: Any,
        incoming: Any,
        outgoing_scroll_pos: int = 0,
    ) -> tuple[Canvas, int]:
        """Seamlessly scroll from outgoing to incoming at constant 1px/frame.

        This is a transition compositor — it redraws both widgets per
        tick for compositing, but their frame counters MUST stay frozen
        during the transition (matches `run_transition`'s pause/resume
        contract). Otherwise rainbow / color_cycle widgets drift their
        animation phase by however many compositor ticks ran (~166 on
        the small sign), surfacing as a visible phase jump when the
        transition ends and the held-text loop resumes ticking. We
        pause/resume here explicitly because `_run_swap` dispatches us
        directly, bypassing `run_transition`.
        """
        if hasattr(outgoing, "pause_frame"):
            outgoing.pause_frame()
        if hasattr(incoming, "pause_frame"):
            incoming.pause_frame()
        # Reset the incoming widget's frame counter so frame-aware effects
        # render their visit-initial state during the scroll-in. Mirrors
        # `run_transition`'s same-shape fix; without it, on loop iteration
        # 2+ the incoming widget's _frame_count holds the previous-visit-
        # end value — typewriter shows full text during the bullet scroll,
        # then snaps to frame=0 when the section begins.
        if hasattr(incoming, "reset_frame"):
            incoming.reset_frame()
        # Guard the per-frame draws so a widget that raises during the scroll
        # transition is tripped + skipped, not fatal. Built once; pause/resume
        # above operate on the real widgets.
        outgoing_draw = guard_for_transition(outgoing, self.breaker)
        incoming_draw = guard_for_transition(incoming, self.breaker)
        loop = asyncio.get_running_loop()
        try:
            w = canvas.width
            spec = getattr(self.transition_fn, "_spec", DEFAULT_DOT_SPEC)
            sep_w = scroll_separator_width(spec)
            total_travel = w + sep_w
            for offset in range(total_travel + 1):
                t0 = loop.time()
                canvas.Clear()
                outgoing_pos = outgoing_scroll_pos - offset
                clear_start = max(0, w - offset)
                bullet_x = w + SCROLL_GAP - offset
                incoming_pos = w + sep_w - offset
                _draw_scroll_frame(
                    canvas,
                    outgoing_draw,
                    incoming_draw,
                    outgoing_pos,
                    bullet_x,
                    incoming_pos,
                    clear_start,
                    spec=spec,
                    frame=offset,
                )
                canvas = _swap(canvas, self.frame)
                await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))
            return canvas, 0
        finally:
            if hasattr(outgoing, "resume_frame"):
                outgoing.resume_frame()
            if hasattr(incoming, "resume_frame"):
                incoming.resume_frame()

    async def _swap_and_scroll(
        self,
        canvas: Canvas,
        ticker_obj: Any,
        hold_time: float = 3,
        skip_initial_draw: bool = False,
        continuous: bool = False,
    ) -> tuple[Canvas, int, int]:
        """Display a widget. If it overflows, hold then scroll the full text.

        When *skip_initial_draw* is True, the first SwapOnVSync is skipped
        because the caller (a transition) already put this widget on screen.
        When *continuous* is True, skip holds for overflow text (used by
        scroll transition for seamless continuous scrolling).
        """
        pos = 0
        bg_color = getattr(ticker_obj, "bg_color", None)
        # Resolve inline value tokens against the live registry once, up
        # front, so the initial draw's `cursor_pos` (which decides hold-vs-
        # scroll and feeds `stop_pos`) is measured against the CURRENT
        # value. The scroll-overflow branch below then locks resolution so
        # a mid-scroll 1 Hz update can't move the width and strand the
        # scroll (constraints #6/#7). No-op for non-token widgets.
        self._resolve_now_if_supported(ticker_obj)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = self._safe_draw(ticker_obj, canvas, pos)

        if not skip_initial_draw:
            canvas = _swap(canvas, self.frame)

        loop = asyncio.get_running_loop()

        if getattr(ticker_obj, "forces_offscreen_scroll", False) is True:
            # Token resolution + geometry: the top-of-function
            # `_resolve_now_if_supported` (L635) already resolved against the
            # current value, and the `_safe_draw` call (L637) that followed
            # recomputed `_bottom_width` from the resolved text.  Do NOT
            # resolve again here — `resolve_tokens_now()` unconditionally sets
            # `_bottom_width = -1`, so a second call with no intervening draw
            # leaves `_bottom_width` at -1 and makes `cycle_width` and `stop`
            # wrong (strands the scroll at ~-canvas.width instead of the
            # correct ~-(canvas.width + real_bottom_width)).  The lock below
            # prevents mid-scroll re-resolution (constraints #6/#7).
            bottom_width = getattr(ticker_obj, "_bottom_width", 0)
            cycle_width = canvas.width + bottom_width
            hold_time_ticks = (
                int(hold_time / self.scroll_speed) if self.scroll_speed > 0 else 0
            )
            loops_floor = getattr(ticker_obj, "bottom_text_loops", 0)
            if isinstance(loops_floor, bool) or not isinstance(loops_floor, int):
                loops_floor = 0
            loops_floor = loops_floor or 1
            n_passes = (
                max(loops_floor, math.ceil(hold_time_ticks / cycle_width))
                if cycle_width > 0
                else loops_floor
            )
            stop = -(n_passes * cycle_width)
            self._lock_resolution_if_supported(ticker_obj, True)
            try:
                while pos > stop:
                    self._maybe_restart()
                    t0 = loop.time()
                    pos -= 1
                    self._advance_frame_if_supported(ticker_obj)
                    reset_canvas(canvas, bg_color)
                    canvas, _ = self._safe_draw(ticker_obj, canvas, pos)
                    canvas = _swap(canvas, self.frame)
                    await asyncio.sleep(
                        max(0.0, self.scroll_speed - (loop.time() - t0))
                    )
            finally:
                self._lock_resolution_if_supported(ticker_obj, False)
            return canvas, cursor_pos, pos

        if getattr(ticker_obj, "wraps_forever", False) is True:
            # Same resolution-freeze pattern as the forces_offscreen_scroll and
            # generic overflow branches: resolve first so the entry cycle_width
            # and n_ticks floor are measured against the current value, then
            # lock so a 1 Hz source tick can't change _bottom_width mid-wrap
            # (which would de-sync the seamless tile scroll).
            self._resolve_now_if_supported(ticker_obj)
            n_ticks = max(1, int(hold_time / self.scroll_speed))
            loops_floor = getattr(ticker_obj, "bottom_text_loops", 0)
            if isinstance(loops_floor, bool) or not isinstance(loops_floor, int):
                loops_floor = 0
            tick = 0
            self._lock_resolution_if_supported(ticker_obj, True)
            try:
                while tick < n_ticks:
                    self._maybe_restart()
                    t0 = loop.time()
                    self._advance_frame_if_supported(ticker_obj)
                    reset_canvas(canvas, bg_color)
                    canvas, cycle_width = self._safe_draw(ticker_obj, canvas, pos)
                    if tick == 0 and loops_floor > 0 and cycle_width > 0:
                        n_ticks = max(n_ticks, loops_floor * cycle_width)
                    canvas = _swap(canvas, self.frame)
                    pos -= 1
                    await asyncio.sleep(
                        max(0.0, self.scroll_speed - (loop.time() - t0))
                    )
                    tick += 1
            finally:
                self._lock_resolution_if_supported(ticker_obj, False)
            return canvas, cursor_pos, pos

        if cursor_pos > canvas.width:
            if not continuous:
                n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
                canvas, _ = await self._hold_ticks(
                    canvas, ticker_obj, n_ticks, pos, bg_color
                )

            padding = get_widget_padding(ticker_obj, default=0)
            # Freeze inline-token resolution for the scroll loop: `stop_pos`
            # is captured once from the entry width, and the loop discards
            # the per-tick cursor_pos. A mid-scroll re-measure would strand
            # the scroll and clip the tail (constraints #6/#7). A version
            # that bumped mid-scroll applies on the next held tick / visit.
            self._lock_resolution_if_supported(ticker_obj, True)
            try:
                stop_pos = -(cursor_pos - canvas.width) + padding
                while pos > stop_pos:
                    self._maybe_restart()
                    t0 = loop.time()
                    pos -= 1
                    self._advance_frame_if_supported(ticker_obj)
                    reset_canvas(canvas, bg_color)
                    canvas, _ = self._safe_draw(ticker_obj, canvas, pos)
                    canvas = _swap(canvas, self.frame)
                    await asyncio.sleep(
                        max(0.0, self.scroll_speed - (loop.time() - t0))
                    )
            finally:
                self._lock_resolution_if_supported(ticker_obj, False)

            if not continuous:
                n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
                canvas, _ = await self._hold_ticks(
                    canvas, ticker_obj, n_ticks, pos, bg_color
                )
        else:
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            canvas, _ = await self._hold_ticks(
                canvas, ticker_obj, n_ticks, pos, bg_color
            )

        return canvas, cursor_pos, pos

    async def _show_one(
        self,
        canvas: Canvas,
        widget: Any,
        hold_time: float,
        skip_initial_draw: bool = False,
        continuous: bool = False,
    ) -> tuple[Canvas, int]:
        """Display one widget for its full visit.

        Dispatches: widgets exposing `play()` run their own animation loop;
        everything else uses the standard hold-and-scroll path. Returns
        `(canvas, last_scroll_pos)` — `last_scroll_pos` is 0 for play()
        widgets since they don't have a scroll position.

        Resets the widget's frame counters at the start of each visit
        (via `reset_frame()` if the widget exposes it).
        """
        self._visit_counter += 1
        self._current_visit = self._visit_counter
        if widget is not None:
            # Intentionally at visit-entry (section boundary), not inside the
            # tick loop — keep it here so a refactor of _swap_and_scroll doesn't
            # accidentally pull it into per-tick cadence.
            status_board.record_widget_visit(widget)
        if hasattr(widget, "reset_frame"):
            widget.reset_frame()
        hold_time = max(hold_time, getattr(widget, "hold_time", 0.0))
        if Ticker._has_play(widget):
            canvas = await self._play_widget(
                canvas, widget, section_hold_time=hold_time
            )
            return canvas, 0
        canvas, _, prev_pos = await self._swap_and_scroll(
            canvas,
            widget,
            hold_time=hold_time,
            skip_initial_draw=skip_initial_draw,
            continuous=continuous,
        )
        return canvas, prev_pos

    async def _run_swap(
        self,
        canvas: Canvas,
        delay: float = 5,
        hold_time: float = 3.0,
        continuous_scroll: bool = False,
    ) -> int:
        """Run swap display mode with optional transitions."""
        from led_ticker.transitions import Scroll, run_transition

        assert self.notif_queue is not None
        is_scroll = self.transition_config is not None and isinstance(
            self.transition_fn, Scroll
        )
        ticker_object = await self.notif_queue.get()
        # `None` is the iterator-exhausted sentinel from
        # `_enqueue_ticker_objects`. An empty container (or empty
        # section) produces this on the very first get(); returning
        # here ends the section cleanly instead of crashing on
        # `_show_one(None, ...)`.
        if ticker_object is None:
            return 0
        canvas, prev_scroll_pos = await self._show_one(
            canvas, ticker_object, hold_time=hold_time
        )

        prev_object = ticker_object
        while not self.notif_queue.empty():
            ticker_object = self.notif_queue.get_nowait()
            # Sentinel mid-stream: producer exhausted the iterator.
            # Stop draining the queue and return the current scroll pos.
            if ticker_object is None:
                break

            if is_scroll:
                canvas, prev_scroll_pos = await self._scroll_between(
                    canvas,
                    prev_object,
                    ticker_object,
                    outgoing_scroll_pos=prev_scroll_pos,
                )
                canvas, prev_scroll_pos = await self._show_one(
                    canvas,
                    ticker_object,
                    hold_time=hold_time,
                    skip_initial_draw=True,
                    continuous=continuous_scroll,
                )
            elif self.transition_config is not None:
                _fps = self.transition_config.transition_fps
                canvas = await run_transition(
                    canvas,
                    self.frame,
                    prev_object,
                    ticker_object,
                    transition=self.transition_fn,
                    duration=self.transition_config.duration,
                    easing=self.transition_config.easing,
                    scroll_speed=(1.0 / _fps) if _fps is not None else 0.05,
                    outgoing_scroll_pos=prev_scroll_pos,
                    outgoing_bg_color=getattr(prev_object, "bg_color", None),
                    incoming_bg_color=getattr(ticker_object, "bg_color", None),
                    breaker=self.breaker,
                )
                canvas, prev_scroll_pos = await self._show_one(
                    canvas,
                    ticker_object,
                    hold_time=hold_time,
                    skip_initial_draw=True,
                )
            else:
                canvas, prev_scroll_pos = await self._show_one(
                    canvas, ticker_object, hold_time=hold_time
                )

            prev_object = ticker_object

        return prev_scroll_pos

    async def _scroll_and_delay(
        self,
        canvas: Canvas,
        ticker_obj: Any,
        delay: float,
        cursor_pos: int = 0,
    ) -> tuple[Canvas, int]:
        logging.info("Running _scroll_and_delay ...")
        bg_color = getattr(ticker_obj, "bg_color", None)
        reset_canvas(canvas, bg_color)
        pos = cursor_pos

        canvas, cursor_pos = self._safe_draw(ticker_obj, canvas, pos)

        if pos <= 0:
            # Title is already in its final position — swap once so it's
            # on-screen immediately (no blank frame between transition end
            # and the delay).
            canvas = _swap(canvas, self.frame)

        loop = asyncio.get_running_loop()
        while pos > 0:
            self._maybe_restart()
            # Advance the per-tick frame so animated title providers
            # (rainbow, color_cycle) animate during scroll-in. Without
            # this, the title freezes on its visit-initial hue while it
            # scrolls in from off-canvas, then suddenly animates after
            # landing — visually inconsistent with the post-scroll hold
            # below and with `_swap_and_scroll`'s scroll branch.
            t0 = loop.time()
            self._advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, cursor_pos = self._safe_draw(ticker_obj, canvas, pos)
            pos -= 1
            canvas = _swap(canvas, self.frame)
            await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))

        # Post-scroll hold: tick loop so animated title providers
        # (color_cycle, rainbow) actually animate during the delay.
        # Mirrors the pattern in `_swap_and_scroll`. Without this, an
        # animated title held at pos=0 would freeze on the visit-initial
        # frame for the full delay.
        n_ticks = max(1, int(delay * 1000) // ENGINE_TICK_MS)
        canvas, cursor_pos = await self._hold_ticks(
            canvas, ticker_obj, n_ticks, pos, bg_color
        )
        return canvas, cursor_pos

    async def _scroll_one_by_one(
        self,
        canvas: Canvas,
        delay: float = 0,
        cursor_pos: int = 0,
    ) -> int:
        """Scroll widgets one-by-one, each fully scrolling off before the next.

        Returns the cursor_pos at which the last widget was drawn before exiting.
        The caller stashes this on `Ticker.last_scroll_pos` so the inter-section
        dissolve has a consistent starting point — without this, the dissolve
        would draw the outgoing widget at pos=0 (the field default), causing
        a one-frame "flash-back" of the last widget reappearing center-canvas
        before the dissolve begins.
        """
        assert self.notif_queue is not None
        ticker_object = await self.notif_queue.get()
        # Iterator-exhausted sentinel — empty section, nothing to scroll.
        # Return the input cursor_pos as the "last drawn" position; the
        # caller's inter-section dissolve will treat this as a no-op start.
        if ticker_object is None:
            return cursor_pos
        pos = cursor_pos
        last_drawn_pos = pos

        if delay:
            canvas, cursor_pos = await self._scroll_and_delay(
                canvas,
                ticker_object,
                delay,
                cursor_pos=pos,
            )
            logging.info("Returned to _scroll_one_by_one ...")
            pos = 0
            last_drawn_pos = pos

        loop = asyncio.get_running_loop()
        while True:
            self._maybe_restart()
            # Advance the per-tick frame on the widget currently on-screen
            # so animated providers (rainbow, color_cycle) animate during
            # the scroll. Without this, RSS stories with `font_color =
            # "rainbow"` render as a static gradient that scrolls but
            # doesn't sweep over time.
            t0 = loop.time()
            self._advance_frame_if_supported(ticker_object)
            reset_canvas(canvas, getattr(ticker_object, "bg_color", None))
            canvas, final_pos = self._safe_draw(ticker_object, canvas, pos)
            last_drawn_pos = pos
            pos -= 1

            if final_pos < 0:
                pos = canvas.width
                try:
                    ticker_object = self.notif_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                # Sentinel: producer exhausted the iterator. End this
                # section so the inter-section dissolve can run.
                if ticker_object is None:
                    break

            canvas = _swap(canvas, self.frame)
            await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))

        canvas.Clear()  # final blank — keep as Clear (no specific widget bg here)
        canvas = _swap(canvas, self.frame)
        # last_drawn_pos is heavily negative at this point (the widget exited
        # left), so the inter-section dissolve renders outgoing off-canvas →
        # visually identical to the cleared state we just swapped.
        return last_drawn_pos

    async def _scroll_side_by_side(
        self,
        canvas: Canvas,
        delay: float = 0,
        cursor_pos: int = 0,
        hold_at_end: float = 2.0,
    ) -> int:
        """Scroll widgets side-by-side. Returns the final scroll position so the
        caller can stash it on `Ticker.last_scroll_pos` for inter-section
        transitions.

        When the queue is exhausted and only the last widget remains, scrolling
        stops once the widget's content right edge reaches the canvas right edge
        (last char fully visible). The function holds for `hold_at_end` seconds,
        then returns. This produces a clean readable end-state that an
        inter-section dissolve can fade out from.
        """
        assert self.notif_queue is not None
        logging.info("Running _scroll_side_by_side ...")
        buffered_objects: list[Any] = []
        next_monitor = await self.notif_queue.get()
        # Iterator-exhausted sentinel on the first pull means there's
        # nothing to scroll — return the input cursor_pos so the
        # inter-section dissolve has a sane starting point.
        if next_monitor is None:
            return cursor_pos
        buffered_objects.append(next_monitor)
        pos = cursor_pos
        queue_empty = False

        if delay:
            canvas, cursor_pos = await self._scroll_and_delay(
                canvas,
                next_monitor,
                delay,
                cursor_pos=pos,
            )
            logging.info("Returned to _scroll_side_by_side ...")
            pos = 0

        loop = asyncio.get_running_loop()
        while True:
            self._maybe_restart()
            # Advance the per-tick frame on every UNIQUE widget being
            # drawn this tick so animated providers (rainbow, color_cycle)
            # animate during side-by-side scroll. Dedup by id() because
            # buffered_objects can contain the same widget instance
            # multiple times (e.g. with a buffer_message widget repeated
            # between stories) — calling advance_frame multiple times per
            # tick would over-advance and skew the animation phase.
            t0 = loop.time()
            seen: set[int] = set()
            for buf_w in buffered_objects:
                if id(buf_w) not in seen:
                    self._advance_frame_if_supported(buf_w)
                    seen.add(id(buf_w))

            # Side-by-side scroll uses the FIRST buffered widget's bg_color for
            # the whole canvas. Mixing widgets with different bg_color in this
            # mode is an accepted pitfall (design spec) — the bg flips at the
            # moment the leftmost widget exits and the next one becomes index 0.
            first_widget = buffered_objects[0] if buffered_objects else None
            bg = getattr(first_widget, "bg_color", None) if first_widget else None
            reset_canvas(canvas, bg)

            mon_index = 0
            canvas, cursor_pos = self._safe_draw(
                buffered_objects[mon_index], canvas, pos
            )
            mon_0_end_pos = cursor_pos

            pos -= 1

            while cursor_pos < canvas.width:
                mon_index += 1

                if _has_index(mon_index, buffered_objects):
                    canvas, cursor_pos = self._safe_draw(
                        buffered_objects[mon_index],
                        canvas,
                        cursor_pos,
                    )
                elif not queue_empty:
                    if self.notif_queue.empty():
                        queue_empty = True
                        break
                    next_monitor = self.notif_queue.get_nowait()
                    # Sentinel: producer exhausted the iterator. Mark
                    # the queue drained so the outer loop holds the
                    # last widget at end-of-scroll instead of waiting
                    # for more items that will never come.
                    if next_monitor is None:
                        queue_empty = True
                        break
                    if self.buffer_msg:
                        buffered_objects.append(self.buffer_msg)
                    buffered_objects.append(next_monitor)
                    # `mon_index += 1` already ran for this iteration but the
                    # index we tried (e.g. 1) didn't exist yet, so we appended
                    # instead. Step mon_index back so the next iteration's
                    # increment lands on the just-appended buffer_message
                    # rather than skipping past it to next_monitor — otherwise
                    # the buffer is skipped for one frame and next_monitor is
                    # drawn at the title's end (no spacing), then re-drawn one
                    # frame later with the buffer pushing it off-screen right.
                    # That produces a one-frame "flash" of the next widget's
                    # leftmost column at the right edge of the panel.
                    mon_index -= 1
                else:
                    break

            # Hold the last widget at end-of-scroll instead of letting it
            # scroll fully off the left. mon_0_end_pos is the right edge of
            # the widget's content (including end_padding); when it's at or
            # within the canvas, the last character is fully visible.
            # Tick the frame counter during the hold so animated providers
            # (rainbow, color_cycle) keep sweeping while the text is at
            # rest — without the tick loop, the rainbow freezes the moment
            # the text stops moving (visible as static gradient on §17).
            # `held_pos = pos + 1` recovers the input cursor_pos that
            # produced the just-drawn frame (the outer loop did `pos -= 1`
            # AFTER the draw). The hold loop redraws at exactly `held_pos`
            # so the visual position matches the just-drawn frame — using
            # `held_pos - 1` would snap the text 1px left between the
            # final scroll frame and the first hold tick.
            if (
                len(buffered_objects) == 1
                and queue_empty
                and mon_0_end_pos <= canvas.width
            ):
                held_pos = pos + 1
                canvas = _swap(canvas, self.frame)
                n_hold_ticks = max(1, int(hold_at_end * 1000) // ENGINE_TICK_MS)
                bg_hold = getattr(buffered_objects[0], "bg_color", None)
                canvas, _ = await self._hold_ticks(
                    canvas, buffered_objects[0], n_hold_ticks, held_pos, bg_hold
                )
                return held_pos

            if mon_0_end_pos < 0:
                buffered_objects.pop(0)
                pos = mon_0_end_pos - 1

            canvas = _swap(canvas, self.frame)
            await asyncio.sleep(max(0.0, self.scroll_speed - (loop.time() - t0)))

            if not len(buffered_objects):
                return pos


# --- Queue builders ---


def _displayable(widget: Any) -> bool:
    """A widget may opt out of a rotation pass via `should_display()` (e.g. an
    out-of-range count widget). Duck-typed: widgets without the method always
    show. A check that raises keeps the widget — a visibility check must never
    crash the render loop or silently hide content."""
    check = getattr(widget, "should_display", None)
    if check is None:
        return True
    try:
        return bool(check())
    except Exception:  # noqa: BLE001 - visibility must not crash the render loop
        return True


def _expand_sources(
    sources: list[Any], breaker: RenderBreaker | None = None
) -> list[Any]:
    """Expand `Container` widgets into their current `feed_stories`;
    pass non-containers through unchanged. Called once per pass through
    a section — re-reading `feed_stories` here is what keeps the displayed
    content in sync with each container's background `update()` task.

    If `breaker` is given, disabled widgets (and disabled container
    stories) are filtered from the output so they never re-enter the
    rotation after being tripped.

    Widgets (and container stories) that define `should_display()` are also
    filtered: returning `False` removes the widget from this pass. A check
    that raises keeps the widget — visibility must never crash the render loop.
    """
    from led_ticker.widget import Container

    out: list[Any] = []
    for s in sources:
        if breaker is not None and breaker.is_disabled(s):
            continue
        if isinstance(s, Container):
            for story in s.feed_stories:
                if breaker is not None and breaker.is_disabled(story):
                    continue
                if _displayable(story):
                    out.append(story)
        elif _displayable(s):
            out.append(s)
    return out


def _build_ticker_iter(
    ticker_objects: list[Any],
    title: Any = None,
    loop_count: int = 0,
    breaker: RenderBreaker | None = None,
) -> Iterator[Any]:
    """Build the engine's per-tick iterator over a section's widgets.

    `ticker_objects` may contain `Container` widgets — they are
    expanded into their current `feed_stories` on EVERY pass through
    the section. Snapshotting at first pass would freeze the displayed
    content even though container `update()` tasks keep running (the
    longboi stale-display bug, 2026-05-28).

    `loop_count=0` cycles forever; `loop_count=N` makes exactly N passes.
    Either way, each pass calls `_expand_sources` so live updates land
    on the panel within at most one cycle of latency.

    `title` is prepended ONCE (not repeated per pass).

    If `breaker` is given, disabled widgets are filtered from each pass
    so they never re-enter the rotation after being tripped.
    """
    n_sources = len(ticker_objects)

    if loop_count:

        def passes() -> Iterator[Any]:
            for pass_idx in range(loop_count):
                widgets = _expand_sources(ticker_objects, breaker)
                logger.debug(
                    "section pass %d/%d: %d sources → %d widgets",
                    pass_idx + 1,
                    loop_count,
                    n_sources,
                    len(widgets),
                )
                yield from widgets

        ticker_iter: Iterator[Any] = passes()
    else:

        def cycle_with_refresh() -> Iterator[Any]:
            pass_idx = 0
            while True:
                widgets = _expand_sources(ticker_objects, breaker)
                logger.debug(
                    "section cycle %d: %d sources → %d widgets",
                    pass_idx,
                    n_sources,
                    len(widgets),
                )
                if not widgets:
                    return
                yield from widgets
                pass_idx += 1

        ticker_iter = cycle_with_refresh()

    if title:
        ticker_iter = itertools.chain([title], ticker_iter)

    return ticker_iter


async def _enqueue_ticker_objects(
    ticker_iter: Any, notif_queue: asyncio.Queue[Any]
) -> None:
    """Pull from ticker_iter into notif_queue until exhausted.

    With per-pass container refresh (2026-05-28), an empty container
    can produce an immediately-empty iterator. Guard the first next()
    call so PEP 479 doesn't promote StopIteration to RuntimeError.

    On exhaustion (either initial-empty or mid-iteration StopIteration),
    enqueue a `None` sentinel so blocking consumers (`await
    notif_queue.get()` in `_run_swap` / `_scroll_one_by_one` /
    `_scroll_side_by_side`) see a wake-up and can return
    cleanly instead of hanging forever waiting on an item that will
    never arrive.
    """
    try:
        await notif_queue.put(next(ticker_iter))
    except StopIteration:
        await notif_queue.put(None)
        return
    while True:
        try:
            await notif_queue.put(next(ticker_iter))
            # Yield to let consumer tasks run. Without this,
            # itertools.cycle with unbounded Queue starves the
            # event loop (put() never blocks on unbounded queues).
            if notif_queue.qsize() > 10:
                await asyncio.sleep(0)
        except StopIteration:
            await notif_queue.put(None)
            break


async def _build_then_enqueue(
    ticker_objects: list[Any],
    notif_queue: asyncio.Queue[Any],
    title: Any = None,
    loop_count: int | None = None,
    breaker: RenderBreaker | None = None,
) -> None:
    ticker_iter = _build_ticker_iter(
        ticker_objects, title=title, loop_count=loop_count or 0, breaker=breaker
    )
    await _enqueue_ticker_objects(ticker_iter, notif_queue)


ENGINE_TICK_MS: int = 50  # 20 fps for held-text frame animation


def _draw_scroll_frame(
    canvas: Canvas,
    outgoing: Any,
    incoming: Any,
    outgoing_pos: int,
    bullet_x: int,
    incoming_pos: int,
    clear_start: int,
    spec: SeparatorSpec = DEFAULT_DOT_SPEC,
    frame: int = 0,
) -> None:
    """Draw one frame of scroll transition: outgoing | gap | bullet | gap | incoming."""
    w = canvas.width
    h = getattr(canvas, "height", 16)

    outgoing.draw(canvas, cursor_pos=outgoing_pos)

    if 0 <= clear_start < w:
        canvas.SubFill(clear_start, 0, w - clear_start, h, 0, 0, 0)

    render_separator(canvas, bullet_x, frame, spec)

    if incoming_pos < w:
        incoming.draw(canvas, cursor_pos=incoming_pos)

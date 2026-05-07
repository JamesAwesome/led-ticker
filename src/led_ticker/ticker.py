"""Display orchestrator for scrolling/swapping widgets on LED panels."""

from __future__ import annotations

import asyncio
import inspect
import itertools
import logging
from typing import Any

import attrs

from led_ticker._types import Canvas, ColorTuple
from led_ticker.colors import RGB_WHITE
from led_ticker.drawing import get_widget_padding
from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real
from led_ticker.widgets._image_fit import reset_canvas
from led_ticker.widgets.message import TickerMessage

DEFAULT_BUFFER_MSG: TickerMessage = TickerMessage(
    " \u2022 ", center=False, font_color=RGB_WHITE
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
    if isinstance(canvas, ScaledCanvas):
        canvas.real = frame.matrix.SwapOnVSync(canvas.real)
        return canvas
    return frame.matrix.SwapOnVSync(canvas)


def _maybe_wrap(canvas: Any, scale: int, content_height: int = 16) -> Any:
    """Wrap canvas in a ScaledCanvas when scale > 1; otherwise return as-is.

    `content_height` controls the wrapper's logical height. Default 16 matches
    a single 5x8 / 6x12 row. Sections that need vertical breathing room (e.g.
    the two_row layout) can request a taller logical canvas by passing
    `content_height=20` etc.
    """
    if scale > 1:
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
    hold_time: float = 3.0
    continuous_scroll: bool = False
    scale: int = 1
    content_height: int = 16
    last_scroll_pos: int = attrs.field(init=False, default=0)

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

    async def run_swap(self, loop_count: int = 0) -> None:
        """Swap between all running monitors."""
        logging.info("Running Swap with loop count %s...", loop_count)
        canvas = _maybe_wrap(
            self.frame.get_clean_canvas(), self.scale, self.content_height
        )
        title = self.title if self.title else None
        assert self.notif_queue is not None

        asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
            )
        )

        self.last_scroll_pos = await _run_swap(
            canvas,
            self.frame,
            self.notif_queue,
            delay=self.title_delay,
            transition=self.transition_config,
            hold_time=self.hold_time,
            continuous_scroll=self.continuous_scroll,
        )

    async def run_gif(self, loop_count: int = 0) -> None:
        """Legacy GIF playback mode: panel-takeover, no titles.

        Each widget pulled from the queue is a GifPlayer; play() is
        called with the underlying real canvas so frames render at
        native physical resolution. `loop_count` is the number of
        complete passes through each GIF before the next widget (or
        section transition) takes over. Treats loop_count=0 as 1
        (consistent with other run modes).

        Each monitor is enqueued exactly once; per-gif repetition
        happens inside play() via loop_count, NOT by re-queueing.

        For title + gif behavior, use `mode = "swap"` instead — gif
        rides _show_one's _has_play dispatch alongside the title.
        """
        logging.info("Running GIF playback with loop count %s...", loop_count)
        canvas = _maybe_wrap(
            self.frame.get_clean_canvas(), self.scale, self.content_height
        )
        assert self.notif_queue is not None

        # mode="gif" suppresses section titles entirely — they have no
        # sensible place to render alongside a full-panel GIF takeover.
        # We pass title=None to _build_then_enqueue rather than relying
        # on _run_gif's defensive non-play() skip (which is a tripwire,
        # not the primary suppression mechanism).
        asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=None,
                loop_count=1,
            )
        )

        await _run_gif(
            canvas,
            self.frame,
            self.notif_queue,
            loop_count=loop_count,
        )

    async def run_forever_scroll(
        self, loop_count: int = 0, start_pos: int | None = None
    ) -> None:
        """Scroll all monitors side-by-side in a continuous stream."""
        logging.info("Running Forever Scroll with loop count %s...", loop_count)
        canvas = _maybe_wrap(
            self.frame.get_clean_canvas(), self.scale, self.content_height
        )
        title = self.title if self.title else None
        cursor_pos = start_pos if start_pos is not None else canvas.width
        assert self.notif_queue is not None

        asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
            )
        )

        self.last_scroll_pos = await _scroll_side_by_side(
            canvas,
            self.frame,
            self.notif_queue,
            delay=self.title_delay,
            buffer_message=self.buffer_msg,
            cursor_pos=cursor_pos,
            hold_at_end=self.hold_time,
        )

    async def run_infini_scroll(
        self, loop_count: int = 0, start_pos: int | None = None
    ) -> None:
        """Scroll monitors one-by-one, each fully scrolling off before the next."""
        logging.info("Running Infini Scroll with loop count %s...", loop_count)
        canvas = _maybe_wrap(
            self.frame.get_clean_canvas(), self.scale, self.content_height
        )
        title = self.title if self.title else None
        assert self.notif_queue is not None

        asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
            )
        )

        cursor_pos = start_pos if start_pos is not None else canvas.width

        self.last_scroll_pos = await _scroll_one_by_one(
            canvas,
            self.frame,
            self.notif_queue,
            cursor_pos=cursor_pos,
            delay=self.title_delay,
        )


# --- Queue builders ---


def _build_ticker_iter(
    ticker_objects: list[Any],
    title: Any = None,
    loop_count: int = 0,
) -> Any:
    if loop_count:
        ticker_iter = itertools.chain(ticker_objects * loop_count)
    else:
        ticker_iter = itertools.cycle(ticker_objects)

    if title:
        ticker_iter = itertools.chain([title], ticker_iter)

    return ticker_iter


async def _enqueue_ticker_objects(
    ticker_iter: Any, notif_queue: asyncio.Queue[Any]
) -> None:
    await notif_queue.put(next(ticker_iter))
    while True:
        try:
            await notif_queue.put(next(ticker_iter))
            # Yield to let consumer tasks run. Without this,
            # itertools.cycle with unbounded Queue starves the
            # event loop (put() never blocks on unbounded queues).
            if notif_queue.qsize() > 10:
                await asyncio.sleep(0)
        except StopIteration:
            break


async def _build_then_enqueue(
    ticker_objects: list[Any],
    notif_queue: asyncio.Queue[Any],
    title: Any = None,
    loop_count: int | None = None,
) -> None:
    ticker_iter = _build_ticker_iter(
        ticker_objects, title=title, loop_count=loop_count or 0
    )
    await _enqueue_ticker_objects(ticker_iter, notif_queue)


async def _enqueue_from_rss_feed(
    feed: Any,
    notif_queue: asyncio.Queue[Any],
    custom_title: Any = None,
    loop_count: int | None = None,
) -> None:
    title = custom_title if custom_title else feed.feed_title
    ticker_iter = _build_ticker_iter(
        feed.feed_stories,
        title=title,
        loop_count=loop_count or 0,
    )
    await _enqueue_ticker_objects(ticker_iter, notif_queue)


# --- Display modes ---


async def _scroll_and_delay(
    canvas: Canvas,
    frame: Any,
    ticker_obj: Any,
    delay: float,
    cursor_pos: int = 0,
    scroll_speed: float = 0.05,
) -> tuple[Canvas, int]:
    logging.info("Running _scroll_and_delay ...")
    bg_color = getattr(ticker_obj, "bg_color", None)
    reset_canvas(canvas, bg_color)
    pos = cursor_pos

    canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)

    if pos <= 0:
        # Title is already in its final position — swap once so it's
        # on-screen immediately (no blank frame between transition end
        # and the delay).
        canvas = _swap(canvas, frame)

    while pos > 0:
        # Advance the per-tick frame so animated title providers
        # (rainbow, color_cycle) animate during scroll-in. Without
        # this, the title freezes on its visit-initial hue while it
        # scrolls in from off-canvas, then suddenly animates after
        # landing — visually inconsistent with the post-scroll hold
        # below and with `_swap_and_scroll`'s scroll branch.
        _advance_frame_if_supported(ticker_obj)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)
        pos -= 1
        canvas = _swap(canvas, frame)
        await asyncio.sleep(scroll_speed)

    # Post-scroll hold: tick loop so animated title providers
    # (color_cycle, rainbow) actually animate during the delay.
    # Mirrors the pattern in `_swap_and_scroll`. Without this, an
    # animated title held at pos=0 would freeze on the visit-initial
    # frame for the full delay.
    n_ticks = max(1, int(delay * 1000) // ENGINE_TICK_MS)
    tick_seconds = ENGINE_TICK_MS / 1000
    for _ in range(n_ticks):
        _advance_frame_if_supported(ticker_obj)
        reset_canvas(canvas, bg_color)
        canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)
        canvas = _swap(canvas, frame)
        await asyncio.sleep(tick_seconds)
    return canvas, cursor_pos


async def _scroll_one_by_one(
    canvas: Canvas,
    frame: Any,
    notif_queue: asyncio.Queue[Any],
    delay: float = 0,
    cursor_pos: int = 0,
    scroll_speed: float = 0.05,
) -> int:
    """Scroll widgets one-by-one, each fully scrolling off before the next.

    Returns the cursor_pos at which the last widget was drawn before exiting.
    The caller stashes this on `Ticker.last_scroll_pos` so the inter-section
    dissolve has a consistent starting point — without this, the dissolve
    would draw the outgoing widget at pos=0 (the field default), causing
    a one-frame "flash-back" of the last widget reappearing center-canvas
    before the dissolve begins.
    """
    ticker_object = await notif_queue.get()
    pos = cursor_pos
    last_drawn_pos = pos

    if delay:
        canvas, cursor_pos = await _scroll_and_delay(
            canvas,
            frame,
            ticker_object,
            delay,
            cursor_pos=pos,
        )
        logging.info("Returned to _scroll_one_by_one ...")
        pos = 0
        last_drawn_pos = pos

    while True:
        # Advance the per-tick frame on the widget currently on-screen
        # so animated providers (rainbow, color_cycle) animate during
        # the scroll. Without this, RSS stories with `font_color =
        # "rainbow"` render as a static gradient that scrolls but
        # doesn't sweep over time.
        _advance_frame_if_supported(ticker_object)
        reset_canvas(canvas, getattr(ticker_object, "bg_color", None))
        canvas, final_pos = ticker_object.draw(canvas, cursor_pos=pos)
        last_drawn_pos = pos
        pos -= 1

        if final_pos < 0:
            pos = canvas.width
            try:
                ticker_object = notif_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        canvas = _swap(canvas, frame)
        await asyncio.sleep(scroll_speed)

    canvas.Clear()  # final blank — keep as Clear (no specific widget bg here)
    canvas = _swap(canvas, frame)
    # last_drawn_pos is heavily negative at this point (the widget exited
    # left), so the inter-section dissolve renders outgoing off-canvas →
    # visually identical to the cleared state we just swapped.
    return last_drawn_pos


async def _scroll_side_by_side(
    canvas: Canvas,
    frame: Any,
    notif_queue: asyncio.Queue[Any],
    buffer_message: Any = None,
    delay: float = 0,
    cursor_pos: int = 0,
    scroll_speed: float = 0.05,
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
    logging.info("Running _scroll_side_by_side ...")
    buffered_objects: list[Any] = []
    next_monitor = await notif_queue.get()
    buffered_objects.append(next_monitor)
    pos = cursor_pos
    queue_empty = False

    if delay:
        canvas, cursor_pos = await _scroll_and_delay(
            canvas,
            frame,
            next_monitor,
            delay,
            cursor_pos=pos,
        )
        logging.info("Returned to _scroll_side_by_side ...")
        pos = 0

    while True:
        # Advance the per-tick frame on every UNIQUE widget being
        # drawn this tick so animated providers (rainbow, color_cycle)
        # animate during side-by-side scroll. Dedup by id() because
        # buffered_objects can contain the same widget instance
        # multiple times (e.g. with a buffer_message widget repeated
        # between stories) — calling advance_frame multiple times per
        # tick would over-advance and skew the animation phase.
        seen: set[int] = set()
        for buf_w in buffered_objects:
            if id(buf_w) not in seen:
                _advance_frame_if_supported(buf_w)
                seen.add(id(buf_w))

        # Side-by-side scroll uses the FIRST buffered widget's bg_color for
        # the whole canvas. Mixing widgets with different bg_color in this
        # mode is an accepted footgun (design spec) — the bg flips at the
        # moment the leftmost widget exits and the next one becomes index 0.
        first_widget = buffered_objects[0] if buffered_objects else None
        bg = getattr(first_widget, "bg_color", None) if first_widget else None
        reset_canvas(canvas, bg)

        mon_index = 0
        canvas, cursor_pos = buffered_objects[mon_index].draw(canvas, cursor_pos=pos)
        mon_0_end_pos = cursor_pos

        pos -= 1

        while cursor_pos < canvas.width:
            mon_index += 1

            if _has_index(mon_index, buffered_objects):
                canvas, cursor_pos = buffered_objects[mon_index].draw(
                    canvas,
                    cursor_pos=cursor_pos,
                )
            elif not queue_empty:
                if notif_queue.empty():
                    queue_empty = True
                    break
                next_monitor = notif_queue.get_nowait()
                if buffer_message:
                    buffered_objects.append(buffer_message)
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
        if len(buffered_objects) == 1 and queue_empty and mon_0_end_pos <= canvas.width:
            held_pos = pos + 1
            canvas = _swap(canvas, frame)
            n_hold_ticks = max(1, int(hold_at_end * 1000) // ENGINE_TICK_MS)
            tick_seconds = ENGINE_TICK_MS / 1000
            for _ in range(n_hold_ticks):
                _advance_frame_if_supported(buffered_objects[0])
                bg_hold = getattr(buffered_objects[0], "bg_color", None)
                reset_canvas(canvas, bg_hold)
                canvas, _ = buffered_objects[0].draw(canvas, cursor_pos=held_pos)
                canvas = _swap(canvas, frame)
                await asyncio.sleep(tick_seconds)
            return held_pos

        if mon_0_end_pos < 0:
            buffered_objects.pop(0)
            pos = mon_0_end_pos - 1

        canvas = _swap(canvas, frame)
        await asyncio.sleep(scroll_speed)

        if not len(buffered_objects):
            return pos


BULLET_WIDTH: int = 2  # 2px wide dot
BULLET_COLOR: ColorTuple = (255, 255, 255)
SCROLL_GAP: int = 6  # px of black on each side of bullet
ENGINE_TICK_MS: int = 50  # 20 fps for held-text frame animation


def _draw_bullet(canvas: Canvas, x: int, color: ColorTuple = BULLET_COLOR) -> None:
    """Draw a 2x2 pixel bullet dot centered vertically on the display."""
    h = getattr(canvas, "height", 16)
    y_center = h // 2
    for dy in range(-1, 1):
        for dx in range(BULLET_WIDTH):
            px = x + dx
            py = y_center + dy
            if 0 <= px < canvas.width and 0 <= py < h:
                canvas.SetPixel(px, py, *color)


def _draw_scroll_frame(
    canvas: Canvas,
    outgoing: Any,
    incoming: Any,
    outgoing_pos: int,
    bullet_x: int,
    incoming_pos: int,
    clear_start: int,
) -> None:
    """Draw one frame of scroll transition: outgoing | gap | bullet | gap | incoming."""
    w = canvas.width
    h = getattr(canvas, "height", 16)

    outgoing.draw(canvas, cursor_pos=outgoing_pos)

    if 0 <= clear_start < w:
        x_range = range(clear_start, w)
        for y in range(h):
            for x in x_range:
                canvas.SetPixel(x, y, 0, 0, 0)

    _draw_bullet(canvas, bullet_x)

    if incoming_pos < w:
        incoming.draw(canvas, cursor_pos=incoming_pos)


def scroll_separator_width(gap: int = SCROLL_GAP) -> int:
    """Total pixel width of the scroll separator: gap + bullet + gap."""
    return gap + BULLET_WIDTH + gap


async def _scroll_between(
    canvas: Canvas,
    frame: Any,
    outgoing: Any,
    incoming: Any,
    outgoing_scroll_pos: int = 0,
    scroll_speed: float = 0.05,
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
    try:
        w = canvas.width
        sep_w = scroll_separator_width()

        total_travel = w + sep_w

        for offset in range(total_travel + 1):
            canvas.Clear()

            outgoing_pos = outgoing_scroll_pos - offset
            clear_start = max(0, w - offset)
            bullet_x = w + SCROLL_GAP - offset
            incoming_pos = w + sep_w - offset

            _draw_scroll_frame(
                canvas,
                outgoing,
                incoming,
                outgoing_pos,
                bullet_x,
                incoming_pos,
                clear_start,
            )

            canvas = _swap(canvas, frame)
            await asyncio.sleep(scroll_speed)

        return canvas, 0
    finally:
        if hasattr(outgoing, "resume_frame"):
            outgoing.resume_frame()
        if hasattr(incoming, "resume_frame"):
            incoming.resume_frame()


def _has_play(widget: Any) -> bool:
    """True iff `widget`'s class declares an async `play` method.

    Looks at the class (not the instance) so Mocks — which auto-create
    a callable `.play` attribute on access — don't false-positive.
    """
    method = getattr(type(widget), "play", None)
    return inspect.iscoroutinefunction(method)


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


async def _play_widget(canvas: Any, frame: Any, widget: Any) -> Any:
    """Hand the canvas off to a widget's `play()` method.

    Used by widgets that drive their own animation loop (e.g. GifPlayer).
    Unwraps any ScaledCanvas wrappers so the widget paints at native
    physical resolution; the wrapper is re-anchored to the new
    back-buffer canvas afterward so subsequent draws stay scaled.
    """
    # `gif_loops` is the canonical name on GifPlayer; fall back to `loops`
    # for any future play()-style widget that doesn't follow the same
    # naming. Either way 0/None coerces to 1.
    loops = getattr(widget, "gif_loops", None) or getattr(widget, "loops", 1) or 1
    if isinstance(canvas, ScaledCanvas):
        innermost = canvas
        while isinstance(innermost.real, ScaledCanvas):
            innermost = innermost.real
        _set_logical_scale(widget, canvas.scale)
        new_real = await widget.play(innermost.real, frame, loop_count=loops)
        innermost.real = new_real
        return canvas
    _set_logical_scale(widget, 1)
    return await widget.play(canvas, frame, loop_count=loops)


def _should_reset_frame(widget: Any) -> bool:
    """Decide whether `_show_one` should call `reset_frame()` on
    visit entry.

    ANY effect on the widget that opts out of `restart_on_visit`
    blocks the reset. Favors continuity over restart — the safer
    default for animated chases (RainbowChaseBorder, Rainbow,
    ColorCycle) that should advance smoothly across loop_count
    boundaries within a section.

    Default `True` via `getattr` fallback keeps today's behavior
    for unknown effect classes — only effects that explicitly set
    `restart_on_visit = False` opt out.

    Composition tradeoff: a widget with both `Typewriter` (wants
    restart) and `RainbowChaseBorder` (wants continuous) gets the
    continuous semantics — typewriter doesn't retype on inner
    loop iterations. Niche combo; documented in CLAUDE.md.

    Section-entry resets are unaffected — `run_transition` calls
    `_reset_presenter(incoming)` at every transition boundary, so
    the new section's first `_show_one` call sees `_frame_count`
    already reset to 0 regardless of this gate's verdict.
    """
    for attr in ("font_color", "top_color", "bottom_color", "border", "animation"):
        effect = getattr(widget, attr, None)
        if effect is None:
            continue
        if not getattr(effect, "restart_on_visit", True):
            return False
    return True


async def _show_one(
    canvas: Canvas,
    frame: Any,
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

    Conditionally resets the widget's frame counter at the start of
    each visit (via `reset_frame()` if the widget exposes it).  The
    reset is gated by `_should_reset_frame()`: effects that set
    `restart_on_visit = False` (e.g. `RainbowChaseBorder`) suppress
    it so their animation phase advances smoothly across `loop_count`
    boundaries.  Effects that omit the flag or set it to `True`
    (e.g. `Typewriter`) still trigger the reset.  ANY opt-out on the
    widget wins — see `_should_reset_frame` for the composition rule.
    """
    if hasattr(widget, "reset_frame") and _should_reset_frame(widget):
        widget.reset_frame()
    if _has_play(widget):
        canvas = await _play_widget(canvas, frame, widget)
        return canvas, 0
    canvas, _, prev_pos = await _swap_and_scroll(
        canvas,
        frame,
        widget,
        hold_time=hold_time,
        skip_initial_draw=skip_initial_draw,
        continuous=continuous,
    )
    return canvas, prev_pos


async def _run_swap(
    canvas: Canvas,
    frame: Any,
    notif_queue: asyncio.Queue[Any],
    delay: float = 5,
    transition: Any = None,
    hold_time: float = 3.0,
    continuous_scroll: bool = False,
) -> int:
    """Run swap display mode with optional transitions."""
    from led_ticker.transitions import Scroll, run_transition

    is_scroll = transition is not None and isinstance(transition.transition_obj, Scroll)
    ticker_object = await notif_queue.get()
    canvas, prev_scroll_pos = await _show_one(
        canvas, frame, ticker_object, hold_time=hold_time
    )

    prev_object = ticker_object
    while not notif_queue.empty():
        ticker_object = notif_queue.get_nowait()

        if is_scroll:
            # Scroll transition: seamless scrolling between widgets.
            # continuous_scroll=True skips holds for overflow text.
            canvas, prev_scroll_pos = await _scroll_between(
                canvas,
                frame,
                prev_object,
                ticker_object,
                outgoing_scroll_pos=prev_scroll_pos,
            )
            canvas, prev_scroll_pos = await _show_one(
                canvas,
                frame,
                ticker_object,
                hold_time=hold_time,
                skip_initial_draw=True,
                continuous=continuous_scroll,
            )
        elif transition is not None:
            # Within a section, both prev and incoming widgets share
            # the section's bg_color (set via `default_bg_color` in
            # `_build_widget`). Pass it on both sides so:
            #  - t<0.5 keeps prev_object's bg painted (otherwise the
            #    bg disappears the instant the inter-widget transition
            #    starts, identical to the inter-section symptom).
            #  - t>=0.5 re-establishes incoming's bg before the
            #    held-text loop's first reset_canvas, eliminating
            #    the post-transition flash.
            # `run_transition` accepts either a tuple or a
            # graphics.Color (widgets store the latter post-coercion).
            canvas = await run_transition(
                canvas,
                frame,
                prev_object,
                ticker_object,
                transition=transition.transition_obj,
                duration=transition.duration,
                easing=transition.easing,
                outgoing_scroll_pos=prev_scroll_pos,
                outgoing_bg_color=getattr(prev_object, "bg_color", None),
                incoming_bg_color=getattr(ticker_object, "bg_color", None),
            )
            canvas, prev_scroll_pos = await _show_one(
                canvas,
                frame,
                ticker_object,
                hold_time=hold_time,
                skip_initial_draw=True,
            )
        else:
            canvas, prev_scroll_pos = await _show_one(
                canvas, frame, ticker_object, hold_time=hold_time
            )

        prev_object = ticker_object

    return prev_scroll_pos


async def _run_gif(
    canvas: Canvas,
    frame: Any,
    notif_queue: asyncio.Queue[Any],
    loop_count: int = 0,
) -> None:
    """Pull GifPlayer widgets from the queue and play() each in turn.

    The widget's `play()` method paints to the real canvas (unwrapping
    any ScaledCanvas) and returns the back-buffer canvas after its
    final swap; we feed that back into the next widget's play() so
    swap chaining stays correct.
    """
    # Unwrap ScaledCanvas wrappers so GIF frames paint at native physical
    # resolution. `_play_widget` keeps its own innermost-wrapper pointer
    # for the post-swap rebind step; this site just wants the raw canvas.
    # Capture the wrapper scale before unwrapping so play()-style widgets
    # can interpret logical-unit knobs (e.g. `top_row_height`).
    wrapper_scale = canvas.scale if isinstance(canvas, ScaledCanvas) else 1
    real = unwrap_to_real(canvas)
    while True:
        try:
            widget = notif_queue.get_nowait()
        except asyncio.QueueEmpty:
            try:
                widget = await asyncio.wait_for(notif_queue.get(), timeout=0.1)
            except TimeoutError:
                return
        # Skip non-GIF widgets (e.g. section titles enqueued by
        # _build_then_enqueue). GIF mode takes over the whole panel —
        # titles don't have a sensible place to render here.
        if not _has_play(widget):
            logging.debug("_run_gif skipping non-GIF widget %s", type(widget).__name__)
            continue
        _set_logical_scale(widget, wrapper_scale)
        real = await widget.play(real, frame, loop_count=loop_count)


def _advance_frame_if_supported(widget: Any) -> None:
    """Call `widget.advance_frame()` if the widget exposes it.

    Quietly no-ops on widgets without the _FrameAware mixin so the
    orchestrator works for both old (transitional) and new widgets.
    """
    if hasattr(widget, "advance_frame"):
        widget.advance_frame()


async def _swap_and_scroll(
    canvas: Canvas,
    frame: Any,
    ticker_obj: Any,
    scroll_speed: float = 0.05,
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
    reset_canvas(canvas, bg_color)
    canvas, cursor_pos = ticker_obj.draw(canvas, pos)

    if not skip_initial_draw:
        canvas = _swap(canvas, frame)

    tick_seconds = ENGINE_TICK_MS / 1000

    if cursor_pos > canvas.width:
        if not continuous:
            # Pre-scroll hold: tick loop so frame-aware widgets animate.
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            for _ in range(n_ticks):
                _advance_frame_if_supported(ticker_obj)
                reset_canvas(canvas, bg_color)
                canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
                canvas = _swap(canvas, frame)
                await asyncio.sleep(tick_seconds)

        # cursor_pos from draw() includes end_padding (default 6px),
        # which is spacing for forever_scroll side-by-side layout.
        # Don't remove padding from the widget — it's needed there.
        # Add padding back here to compensate: cursor_pos overshoots
        # by padding, so adding it to stop_pos scrolls less far left,
        # putting the last character flush with the right edge (x=159).
        padding = get_widget_padding(ticker_obj, default=0)
        stop_pos = -(cursor_pos - canvas.width) + padding
        while pos > stop_pos:
            pos -= 1
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(scroll_speed)

        # Post-scroll hold: tick loop so frame-aware widgets animate.
        if not continuous:
            n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
            for _ in range(n_ticks):
                _advance_frame_if_supported(ticker_obj)
                reset_canvas(canvas, bg_color)
                canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
                canvas = _swap(canvas, frame)
                await asyncio.sleep(tick_seconds)
    else:
        # Held text: tick loop so frame-aware widgets animate during hold.
        n_ticks = max(1, int(hold_time * 1000) // ENGINE_TICK_MS)
        for _ in range(n_ticks):
            _advance_frame_if_supported(ticker_obj)
            reset_canvas(canvas, bg_color)
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = _swap(canvas, frame)
            await asyncio.sleep(tick_seconds)

    return canvas, cursor_pos, pos

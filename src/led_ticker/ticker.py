"""Display orchestrator for scrolling/swapping widgets on LED panels."""

import asyncio
import itertools
import logging

import attrs

from led_ticker.colors import RGB_WHITE
from led_ticker.widgets.message import TickerMessage

DEFAULT_BUFFER_MSG = TickerMessage(" * ", center=False, font_color=RGB_WHITE)


def _has_index(index, items):
    """Check if a list has an index."""
    try:
        items[index]
    except IndexError:
        return False
    return True


@attrs.define
class Ticker:
    """Display orchestrator for an LedFrame."""

    monitors: list
    frame: object
    title: object = None
    title_delay: int = 4
    buffer_msg: object = attrs.Factory(lambda: DEFAULT_BUFFER_MSG)
    notif_queue: object = None
    transition_config: object = None
    hold_time: float = 3.0
    last_scroll_pos: int = attrs.field(init=False, default=0)

    @classmethod
    def from_rss_feed(
        cls,
        feed_monitor,
        frame,
        custom_title=None,
        title_delay=4,
        buffer_msg=None,
        notif_queue=None,
    ):
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

    async def run_swap(self, loop_count=0):
        """Swap between all running monitors."""
        logging.info("Running Swap with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.title if self.title else None

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
        )

    async def run_forever_scroll(self, loop_count=0, start_pos=None):
        """Scroll all monitors side-by-side in a continuous stream."""
        logging.info("Running Forever Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.title if self.title else None
        cursor_pos = start_pos if start_pos is not None else canvas.width

        asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
            )
        )

        await _scroll_side_by_side(
            canvas,
            self.frame,
            self.notif_queue,
            delay=self.title_delay,
            buffer_message=self.buffer_msg,
            cursor_pos=cursor_pos,
        )

    async def run_infini_scroll(self, loop_count=0, start_pos=None):
        """Scroll monitors one-by-one, each fully scrolling off before the next."""
        logging.info("Running Infini Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.title if self.title else None

        asyncio.create_task(
            _build_then_enqueue(
                self.monitors,
                self.notif_queue,
                title=title,
                loop_count=loop_count,
            )
        )

        cursor_pos = start_pos if start_pos is not None else canvas.width

        await _scroll_one_by_one(
            canvas,
            self.frame,
            self.notif_queue,
            cursor_pos=cursor_pos,
            delay=self.title_delay,
        )


# --- Queue builders ---


def _build_ticker_iter(ticker_objects, title=None, loop_count=0):
    if loop_count:
        ticker_iter = itertools.chain(ticker_objects * loop_count)
    else:
        ticker_iter = itertools.cycle(ticker_objects)

    if title:
        ticker_iter = itertools.chain([title], ticker_iter)

    return ticker_iter


async def _enqueue_ticker_objects(ticker_iter, notif_queue):
    await notif_queue.put(next(ticker_iter))
    while True:
        try:
            await notif_queue.put(next(ticker_iter))
        except StopIteration:
            break


async def _build_then_enqueue(ticker_objects, notif_queue, title=None, loop_count=None):
    ticker_iter = _build_ticker_iter(ticker_objects, title=title, loop_count=loop_count)
    await _enqueue_ticker_objects(ticker_iter, notif_queue)


async def _enqueue_from_rss_feed(feed, notif_queue, custom_title=None, loop_count=None):
    title = custom_title if custom_title else feed.feed_title
    ticker_iter = _build_ticker_iter(
        feed.feed_stories,
        title=title,
        loop_count=loop_count,
    )
    await _enqueue_ticker_objects(ticker_iter, notif_queue)


# --- Display modes ---


async def _scroll_and_delay(
    canvas,
    frame,
    ticker_obj,
    delay,
    cursor_pos=0,
    scroll_speed=0.05,
):
    logging.info("Running _scroll_and_delay ...")
    canvas.Clear()
    pos = cursor_pos

    canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)

    while pos > 0:
        canvas.Clear()
        canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)
        pos -= 1
        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

    await asyncio.sleep(delay)
    return canvas, cursor_pos


async def _scroll_one_by_one(
    canvas,
    frame,
    notif_queue,
    delay=0,
    cursor_pos=0,
    scroll_speed=0.05,
):
    ticker_object = await notif_queue.get()
    pos = cursor_pos

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

    while True:
        canvas.Clear()
        canvas, final_pos = ticker_object.draw(canvas, cursor_pos=pos)
        pos -= 1

        if final_pos < 0:
            pos = canvas.width
            try:
                ticker_object = notif_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

    canvas.Clear()
    canvas = frame.matrix.SwapOnVSync(canvas)


async def _scroll_side_by_side(
    canvas,
    frame,
    notif_queue,
    buffer_message=None,
    delay=0,
    cursor_pos=0,
    scroll_speed=0.05,
):
    logging.info("Running _scroll_side_by_side ...")
    buffered_objects = []
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
        canvas.Clear()

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
            else:
                break

        if mon_0_end_pos < 0:
            buffered_objects.pop(0)
            pos = mon_0_end_pos - 1

        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

        if not len(buffered_objects):
            return True


async def _scroll_between(
    canvas,
    frame,
    outgoing,
    incoming,
    outgoing_scroll_pos=0,
    scroll_speed=0.05,
):
    """Seamlessly scroll from outgoing to incoming at constant 1px/frame."""
    from led_ticker.drawing import get_text_width
    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.widgets.message import TickerMessage

    w = canvas.width
    h = getattr(canvas, "height", 16)

    # Explicit equal gaps on both sides of bullet: [padding][*][padding]
    # Don't rely on outgoing's end_padding — it's just a cursor_pos
    # number, not visible pixels on screen.
    padding = getattr(outgoing, "padding", None)
    padding = padding if isinstance(padding, int) else 6

    bullet = TickerMessage("*", center=False, padding=0)
    bullet_text_w = get_text_width(FONT_DEFAULT, "*", padding=0)
    separator_width = padding + bullet_text_w + padding

    total_travel = w + separator_width

    for offset in range(total_travel + 1):
        canvas.Clear()

        outgoing_pos = outgoing_scroll_pos - offset
        bullet_pos = w + padding - offset
        incoming_pos = w + separator_width - offset

        # 1. Draw outgoing (may bleed right)
        outgoing.draw(canvas, cursor_pos=outgoing_pos)

        # 2. Blackout from separator start (outgoing end + gap)
        clear_start = max(0, w - offset)
        if clear_start < w:
            x_range = range(clear_start, w)
            for y in range(h):
                for x in x_range:
                    canvas.SetPixel(x, y, 0, 0, 0)

        if bullet_pos < w and bullet_pos + bullet_text_w > 0:
            bullet.draw(canvas, cursor_pos=bullet_pos)

        if incoming_pos < w:
            incoming.draw(canvas, cursor_pos=incoming_pos)

        canvas = frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

    return canvas, 0


async def _run_swap(
    canvas,
    frame,
    notif_queue,
    delay=5,
    transition=None,
    hold_time=3.0,
):
    """Run swap display mode with optional transitions."""
    from led_ticker.transition import Scroll, run_transition

    is_scroll = (
        transition is not None
        and isinstance(transition.transition_obj, Scroll)
    )

    ticker_object = await notif_queue.get()
    canvas, _, prev_scroll_pos = await _swap_and_scroll(
        canvas,
        frame,
        ticker_object,
        hold_time=hold_time,
    )

    prev_object = ticker_object
    while not notif_queue.empty():
        ticker_object = notif_queue.get_nowait()

        if is_scroll:
            # Continuous scroll: no holds between widgets
            canvas, prev_scroll_pos = await _scroll_between(
                canvas,
                frame,
                prev_object,
                ticker_object,
                outgoing_scroll_pos=prev_scroll_pos,
            )
            # Scroll long text through without holding
            canvas, _, prev_scroll_pos = await _swap_and_scroll(
                canvas,
                frame,
                ticker_object,
                skip_initial_draw=True,
                hold_time=0,
            )
        elif transition is not None:
            canvas = await run_transition(
                canvas,
                frame,
                prev_object,
                ticker_object,
                transition=transition.transition_obj,
                duration=transition.duration,
                easing=transition.easing,
                outgoing_scroll_pos=prev_scroll_pos,
            )
            canvas, _, prev_scroll_pos = await _swap_and_scroll(
                canvas,
                frame,
                ticker_object,
                skip_initial_draw=True,
                hold_time=hold_time,
            )
        else:
            canvas, _, prev_scroll_pos = await _swap_and_scroll(
                canvas,
                frame,
                ticker_object,
                hold_time=hold_time,
            )

        prev_object = ticker_object

    return prev_scroll_pos


async def _swap_and_scroll(
    canvas,
    frame,
    ticker_obj,
    scroll_speed=0.05,
    hold_time=3,
    skip_initial_draw=False,
):
    """Display a widget. If it overflows, hold then scroll the full text.

    When *skip_initial_draw* is True, the first SwapOnVSync is skipped
    because the caller (a transition) already put this widget on screen.
    """
    pos = 0
    canvas.Clear()
    canvas, cursor_pos = ticker_obj.draw(canvas, pos)

    if not skip_initial_draw:
        canvas = frame.matrix.SwapOnVSync(canvas)

    if cursor_pos > canvas.width:
        await asyncio.sleep(hold_time)

        # cursor_pos from draw() includes end_padding (default 6px),
        # which is spacing for forever_scroll side-by-side layout.
        # Don't remove padding from the widget — it's needed there.
        # Add padding back here to compensate: cursor_pos overshoots
        # by padding, so adding it to stop_pos scrolls less far left,
        # putting the last character flush with the right edge (x=159).
        padding = getattr(ticker_obj, "padding", None)
        padding = padding if isinstance(padding, int) else 0
        stop_pos = -(cursor_pos - canvas.width) + padding
        while pos > stop_pos:
            pos -= 1
            canvas.Clear()
            canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
            canvas = frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(scroll_speed)

        # Hold with the end of the text visible
        await asyncio.sleep(hold_time)
    else:
        await asyncio.sleep(hold_time)

    return canvas, cursor_pos, pos

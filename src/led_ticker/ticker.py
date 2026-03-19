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

    @classmethod
    def from_rss_feed(cls, feed_monitor, frame, custom_title=None,
                      title_delay=4, buffer_msg=None, notif_queue=None):
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

        asyncio.create_task(_build_then_enqueue(
            self.monitors, self.notif_queue,
            title=title, loop_count=loop_count,
        ))

        await _run_swap(canvas, self.frame, self.notif_queue, delay=self.title_delay)

    async def run_forever_scroll(self, loop_count=0, start_pos=None):
        """Scroll all monitors side-by-side in a continuous stream."""
        logging.info("Running Forever Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.title if self.title else None
        cursor_pos = 0 if start_pos is not None else canvas.width

        asyncio.create_task(_build_then_enqueue(
            self.monitors, self.notif_queue,
            title=title, loop_count=loop_count,
        ))

        await _scroll_side_by_side(
            canvas, self.frame, self.notif_queue,
            delay=self.title_delay,
            buffer_message=self.buffer_msg,
            cursor_pos=cursor_pos,
        )

    async def run_infini_scroll(self, loop_count=0, start_pos=None):
        """Scroll monitors one-by-one, each fully scrolling off before the next."""
        logging.info("Running Infini Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.title if self.title else None

        asyncio.create_task(_build_then_enqueue(
            self.monitors, self.notif_queue,
            title=title, loop_count=loop_count,
        ))

        cursor_pos = 0 if start_pos is not None else canvas.width

        await _scroll_one_by_one(
            canvas, self.frame, self.notif_queue,
            cursor_pos=cursor_pos, delay=self.title_delay,
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
        feed.feed_stories, title=title, loop_count=loop_count,
    )
    await _enqueue_ticker_objects(ticker_iter, notif_queue)


# --- Display modes ---

async def _scroll_and_delay(
    canvas, frame, ticker_obj, delay, cursor_pos=0, scroll_speed=0.05,
):
    logging.info("Running _scroll_and_delay ...")
    canvas.Clear()
    pos = cursor_pos

    canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)

    while pos > 0:
        canvas.Clear()
        canvas, cursor_pos = ticker_obj.draw(canvas, cursor_pos=pos)
        pos -= 1
        frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

    await asyncio.sleep(delay)
    return canvas, cursor_pos


async def _scroll_one_by_one(
    canvas, frame, notif_queue, delay=0, cursor_pos=0, scroll_speed=0.05,
):
    ticker_object = await notif_queue.get()
    pos = cursor_pos

    if delay:
        canvas, cursor_pos = await _scroll_and_delay(
            canvas, frame, ticker_object, delay, cursor_pos=pos,
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

        await asyncio.sleep(scroll_speed)
        frame.matrix.SwapOnVSync(canvas)

    canvas.Clear()
    frame.matrix.SwapOnVSync(canvas)


async def _scroll_side_by_side(canvas, frame, notif_queue, buffer_message=None,
                               delay=0, cursor_pos=0, scroll_speed=0.05):
    logging.info("Running _scroll_side_by_side ...")
    buffered_objects = []
    next_monitor = await notif_queue.get()
    buffered_objects.append(next_monitor)
    pos = cursor_pos
    queue_empty = False

    if delay:
        canvas, cursor_pos = await _scroll_and_delay(
            canvas, frame, next_monitor, delay, cursor_pos=pos,
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
                    canvas, cursor_pos=cursor_pos,
                )
            elif not queue_empty:
                try:
                    next_monitor = notif_queue.get_nowait()
                    if buffer_message:
                        buffered_objects.append(buffer_message)
                    buffered_objects.append(next_monitor)
                except asyncio.QueueEmpty:
                    queue_empty = True
                    break
            else:
                break

        if mon_0_end_pos < 0:
            buffered_objects.pop(0)
            pos = mon_0_end_pos - 1

        await asyncio.sleep(0.05)
        frame.matrix.SwapOnVSync(canvas)

        if not len(buffered_objects):
            return True


async def _run_swap(canvas, frame, notif_queue, ticker_delay=3, delay=5):
    """Run swap display mode."""
    ticker_object = await notif_queue.get()

    await _swap_and_scroll(canvas, frame, ticker_object)
    await asyncio.sleep(delay)

    while True:
        try:
            ticker_object = notif_queue.get_nowait()
            await _swap_and_scroll(canvas, frame, ticker_object)
            await asyncio.sleep(delay)
        except asyncio.QueueEmpty:
            break

    canvas.Clear()
    frame.matrix.SwapOnVSync(canvas)


async def _swap_and_scroll(canvas, frame, ticker_obj, scroll_speed=0.05):
    pos = 0
    canvas.Clear()

    canvas, cursor_pos = ticker_obj.draw(canvas, pos)
    frame.matrix.SwapOnVSync(canvas)

    if cursor_pos > canvas.width:
        await asyncio.sleep(2)
        canvas, cursor_pos = await _scroll_into_frame(canvas, frame, ticker_obj, pos)

    return canvas, cursor_pos


async def _scroll_into_frame(canvas, frame, ticker_obj, cursor_pos, scroll_speed=0.05):
    logging.info("Running _scroll_into_frame ...")
    pos = cursor_pos

    canvas.Clear()
    canvas, cursor_pos = ticker_obj.draw(canvas, pos)
    frame.matrix.SwapOnVSync(canvas)

    while cursor_pos > canvas.width:
        pos -= 1
        canvas.Clear()
        canvas, cursor_pos = ticker_obj.draw(canvas, pos)
        frame.matrix.SwapOnVSync(canvas)
        await asyncio.sleep(scroll_speed)

    return canvas, cursor_pos

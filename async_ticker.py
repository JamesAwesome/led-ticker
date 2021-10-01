#!/usr/bin/env python3
"""Async Ticker
"""
import asyncio
import itertools
import logging

import attr

from async_widgets import TickerMessage
from rgbmatrix import graphics

RGB_WHITE = graphics.Color(255, 255, 255)


def _has_index(index, my_list):
    """check if a list has an index"""
    try:
        my_list[index]
    except IndexError:
        return False

    return True


@attr.s
class AsyncTicker:
    """Async ticker for an LedFrame"""

    monitors = attr.ib(type=list)
    frame = attr.ib()
    title = attr.ib(default=None)
    title_delay = attr.ib(default=4)
    buffer_msg = attr.ib(default=TickerMessage(' * ', center=False, font_color=RGB_WHITE))

    async def run_swap(self, loop_count=0):
        """Swap between all running monitors"""
        logging.info("Running Swap with loop count %s...", loop_count)

        if loop_count:
            monitor_generator = itertools.chain(self.monitors * loop_count)
        else:
            monitor_generator = itertools.cycle(self.monitors)

        if self.title:
            monitor_generator = itertools.chain([self.title], monitor_generator)

        canvas = self.frame.get_clean_canvas()

        for monitor in monitor_generator:
            pos = 0
            canvas, cursor_pos = monitor.draw(canvas, pos)

            # If the image is too big, display at the far left and scroll it
            if cursor_pos > canvas.width:
                self.frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(2)

            while cursor_pos > canvas.width:
                canvas.Clear()
                canvas, cursor_pos = monitor.draw(canvas, pos)
                pos -= 1
                await asyncio.sleep(0.05)

                self.frame.matrix.SwapOnVSync(canvas)

            self.frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(5)
            canvas.Clear()

        self.frame.matrix.SwapOnVSync(canvas)

    async def run_forever_scroll(self, loop_count=0, start_pos=None):
        """Scroll all monitors in order forever"""
        logging.info("Running Forever Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.title if self.title else None

        cursor_pos = 0 if start_pos is not None else canvas.width

        ticker_objects = _chain_ticker_objects(
            self.monitors,
            title=title,
            loop_count=loop_count,
        )

        await _scroll_side_by_side(
            canvas, self.frame, ticker_objects,
            delay=self.title_delay,
            buffer_message=self.buffer_msg,
            cursor_pos=cursor_pos,
        )

    async def run_infini_scroll(self, loop_count=0):
        """Scroll monitors forever one by one"""
        logging.info("Running Infini Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.title if self.title else None

        ticker_objects = _chain_ticker_objects(
            self.monitors,
            title=title,
            loop_count=loop_count,
        )

        cursor_pos = 0 if start_pos is not None else canvas.width

        await _sroll_one_by_one(
            canvas, self.frame, ticker_objects,
            cursor_pos=cursor_pos, delay=self.title_delay
        )


@attr.s
class AsyncRSSFeedTicker:
    """Async ticker for an LedFrame"""

    feed = attr.ib(type=list)
    frame = attr.ib()
    buffer_msg = attr.ib(default=TickerMessage(' * ', center=False, font_color=RGB_WHITE))
    display_title = attr.ib(default=True)
    title_delay = attr.ib(default=5)

    async def run_swap(self, loop_count=0):
        """Swap between all running monitors"""
        logging.info("Running Swap with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.feed.feed_title if self.display_title else None
        cursor_pos = 0 if start_pos is not None else canvas.width

        ticker_objects = _chain_ticker_objects(
            self.feed.feed_stories,
            title=title,
            loop_count=loop_count,
        )

        await _run_swap(canvas, frame, ticker_objects, delay=0)

    async def run_forever_scroll(self, loop_count=0, start_pos=None):
        """Scroll all monitors in order forever"""
        logging.info("Running Forever Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.feed.feed_title if self.display_title else None
        cursor_pos = 0 if start_pos is not None else canvas.width

        ticker_objects = _chain_ticker_objects(
            self.feed.feed_stories,
            title=title,
            loop_count=loop_count,
        )

        await _scroll_side_by_side(
            canvas, self.frame, ticker_objects,
            delay=self.title_delay,
            buffer_message=self.buffer_msg,
            cursor_pos=cursor_pos,
        )

    async def run_infini_scroll(self, loop_count=0, start_pos=None):
        """Scroll monitors forever one by one"""
        logging.info("Running Infini Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        title = self.feed.feed_title if self.display_title else None

        ticker_objects = _chain_ticker_objects(
            self.feed.feed_stories,
            title=title,
            loop_count=loop_count,
        )

        cursor_pos = 0 if start_pos is not None else canvas.width

        await _sroll_one_by_one(
            canvas, self.frame, ticker_objects,
            cursor_pos=cursor_pos, delay=self.title_delay
        )


def _chain_ticker_objects(ticker_objects, title=None, loop_count=0):
    if loop_count:
        ticker_objects = itertools.chain(ticker_objects * loop_count)
    else:
        ticker_objects = itertools.cycle(ticker_objects)

    if title:
        ticker_objects = itertools.chain([title], ticker_objects)

    return ticker_objects


async def _sroll_one_by_one(canvas, frame, ticker_objects, delay=0, cursor_pos=0, scroll_speed=0.05):
    ticker_object = next(ticker_objects)
    pos = cursor_pos

    if delay:
        canvas.Clear()
        canvas, cursor_pos = ticker_object.draw(canvas, cursor_pos=pos)

        while pos > 0:
            canvas.Clear()
            canvas, cursor_pos = ticker_object.draw(canvas, cursor_pos=pos)
            pos -= 1

            frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(scroll_speed)

        await asyncio.sleep(delay)

    while True:
        canvas.Clear()

        canvas, final_pos = ticker_object.draw(canvas, cursor_pos=pos)
        pos -= 1

        if final_pos < 0:
            pos = canvas.width
            try:
                ticker_object = next(ticker_objects)
            except StopIteration:
                break

        await asyncio.sleep(scroll_speed)
        frame.matrix.SwapOnVSync(canvas)

    canvas.Clear()
    frame.matrix.SwapOnVSync(canvas)


async def _scroll_side_by_side(canvas, frame, ticker_objects, buffer_message=None, delay=0, cursor_pos=0, scroll_speed=0.05):

        buffered_objects = []
        buffered_objects.append(next(ticker_objects))
        pos = cursor_pos

        if delay:
            canvas.Clear()
            canvas, cursor_pos = buffered_objects[0].draw(canvas, cursor_pos=pos)

            while pos > 0:
                canvas.Clear()
                canvas, cursor_pos = buffered_objects[0].draw(canvas, cursor_pos=pos)
                pos -= 1
                frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(scroll_speed)

        await asyncio.sleep(delay)

        while True:
            canvas.Clear()

            mon_index = 0
            canvas, cursor_pos = buffered_objects[mon_index].draw(canvas, cursor_pos=pos)
            mon_0_end_pos = cursor_pos

            pos -= 1

            while cursor_pos < canvas.width:
                mon_index += 1

                try:
                    if not _has_index(mon_index, buffered_objects):
                        next_monitor = next(ticker_objects)

                        if buffer_message:
                            buffered_objects.append(buffer_message)

                        buffered_objects.append(next_monitor)

                    canvas, cursor_pos = buffered_objects[mon_index].draw(
                        canvas, cursor_pos=cursor_pos
                    )

                except StopIteration:
                    # We have run out of monitors
                    break

            if mon_0_end_pos < 0:
                buffered_objects.pop(0)
                pos = mon_0_end_pos - 1

            await asyncio.sleep(0.05)
            frame.matrix.SwapOnVSync(canvas)

            if not len(buffered_objects):
                # We have run out of monitors
                return True


async def _run_swap(canvas, frame, ticker_objects, delay=0):
        """Run Swap"""
        pos = 0

        if delay:
            ticker_object = next(ticker_objects)
            canvas.Clear()
            canvas, cursor_pos = ticker_object.draw(canvas, cursor_pos=pos)
            frame.matrix.SwapOnVSync(canvas)

        await asyncio.sleep(delay)

        for monitor in monitor_generator:
            canvas.Clear()
            pos = 0
            canvas, cursor_pos = ticker_object.draw(canvas, pos)

            # If the image is too big, display at the far left and scroll it
            if cursor_pos > canvas.width:
                frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(2)

            while cursor_pos > canvas.width:
                canvas.Clear()
                canvas, cursor_pos = ticker_object.draw(canvas, pos)
                pos -= 1
                await asyncio.sleep(0.05)

                frame.matrix.SwapOnVSync(canvas)

            frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(5)

        canvas.Clear()
        frame.matrix.SwapOnVSync(canvas)

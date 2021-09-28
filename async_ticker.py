#!/usr/bin/env python3
"""Async Ticker
"""
import asyncio
import itertools
import logging

import attr


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
            pos = 3
            canvas, cursor_pos = monitor.draw(canvas, pos, ticker_mode='swap')

            # If the image is too big, display at the far left and scroll it
            if (cursor_pos + 6) > canvas.width:
                self.frame.matrix.SwapOnVSync(canvas)
                await asyncio.sleep(2)

            while (cursor_pos + 6) > canvas.width:
                canvas.Clear()
                canvas, cursor_pos = monitor.draw(canvas, pos, ticker_mode='swap')
                pos -= 1
                await asyncio.sleep(0.05)

                self.frame.matrix.SwapOnVSync(canvas)

            self.frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(5)
            canvas.Clear()

        self.frame.matrix.SwapOnVSync(canvas)

    async def run_forever_scroll(self, loop_count=0):
        """Scroll all monitors in order forever"""
        logging.info("Running Forever Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        pos = canvas.width

        if loop_count:
            monitor_generator = itertools.chain(self.monitors * loop_count)
        else:
            monitor_generator = itertools.cycle(self.monitors)

        buffered_monitors = []
        if self.title:
            buffered_monitors.append(self.title)

        buffered_monitors.append(next(monitor_generator))

        while True:
            canvas.Clear()

            mon_index = 0
            canvas, cursor_pos = buffered_monitors[mon_index].draw(canvas, cursor_pos=pos, ticker_mode='scroll')
            mon_0_end_pos = cursor_pos

            pos -= 1

            while cursor_pos < canvas.width:
                mon_index += 1

                try:
                    if not _has_index(mon_index, buffered_monitors):
                        buffered_monitors.append(next(monitor_generator))

                    canvas, cursor_pos = buffered_monitors[mon_index].draw(
                        canvas, cursor_pos=cursor_pos, ticker_mode='scroll'
                    )

                except StopIteration:
                    # We have run out of monitors
                    break

            if mon_0_end_pos < 0:
                buffered_monitors.pop(0)
                pos = mon_0_end_pos - 1

            await asyncio.sleep(0.05)
            self.frame.matrix.SwapOnVSync(canvas)

            if not len(buffered_monitors):
                # We have run out of monitors
                return True

    async def run_infini_scroll(self, loop_count=0):
        """Scroll monitors forever one by one"""
        logging.info("Running Infini Scroll with loop count %s...", loop_count)
        canvas = self.frame.get_clean_canvas()
        pos = canvas.width

        if loop_count:
            monitor_generator = itertools.chain(self.monitors * loop_count)
        else:
            monitor_generator = itertools.cycle(self.monitors)

        if self.title:
            monitor = self.title

        else:
            monitor = next(monitor_generator)

        while True:
            canvas.Clear()

            canvas, final_pos = monitor.draw(canvas, cursor_pos=pos, ticker_mode='scroll')
            pos -= 1

            if final_pos < 0:
                pos = canvas.width
                try:
                    monitor = next(monitor_generator)
                except StopIteration:
                    break

            await asyncio.sleep(0.05)
            self.frame.matrix.SwapOnVSync(canvas)

        canvas.Clear()
        self.frame.matrix.SwapOnVSync(canvas)

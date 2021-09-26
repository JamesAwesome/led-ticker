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

    async def run_swap(self):
        """Swap between all running monitors"""
        logging.info("Running Swap...")
        while True:
            canvas = self.frame.get_clean_canvas()
            for monitor in itertools.cycle(self.monitors):
                canvas.Clear()
                pos = 3
                canvas, cursor_pos = monitor.draw(canvas)

                while (cursor_pos + 6) > canvas.width:
                    canvas.Clear()
                    canvas, cursor_pos = monitor.draw(canvas, pos)
                    pos -= 1
                    await asyncio.sleep(0.1)

                    self.frame.matrix.SwapOnVSync(canvas)

                await asyncio.sleep(5)
                self.frame.matrix.SwapOnVSync(canvas)

    async def run_forever_scroll(self):
        """Scroll all monitors in order forever"""
        logging.info("Running Forever Scroll...")
        canvas = self.frame.get_clean_canvas()
        pos = 0

        monitor_generator = itertools.cycle(self.monitors)
        monitors = [next(monitor_generator)]

        while True:
            canvas.Clear()

            mon_index = 0
            canvas, cursor_pos = monitors[mon_index].draw(canvas, cursor_pos=pos)
            mon_0_width = cursor_pos

            pos -= 1

            while cursor_pos < canvas.width:
                mon_index += 1

                if not _has_index(mon_index, monitors):
                    monitors.append(next(monitor_generator))

                canvas, cursor_pos = monitors[mon_index].draw(
                    canvas, cursor_pos=cursor_pos
                )

            if mon_0_width + canvas.width < 0:
                monitors.pop(0)
                pos = mon_0_width - 1

            await asyncio.sleep(0.05)
            self.frame.matrix.SwapOnVSync(canvas)

    async def run_infini_scroll(self):
        """Scroll monitors forever one by one"""
        logging.info("Running Infini Scroll...")
        canvas = self.frame.get_clean_canvas()
        pos = canvas.width
        monitor_generator = itertools.cycle(self.monitors)
        monitor = next(monitor_generator)

        while True:
            canvas.Clear()

            canvas, final_pos = monitor.draw(canvas, cursor_pos=pos)
            pos -= 1

            if (final_pos + canvas.width) - canvas.width == 0:
                pos = canvas.width
                monitor = next(monitor_generator)

            await asyncio.sleep(0.05)
            self.frame.matrix.SwapOnVSync(canvas)

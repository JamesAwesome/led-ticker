#!/usr/bin/env python3

import asyncio
import itertools
import logging

import attr


@attr.s
class AsyncTicker(object):
    monitors = attr.ib(type=list)
    frame = attr.ib()

    async def run_swap(self):
        logging.info('Running Swap...')
        while True:
            canvas = self.frame.get_clean_canvas()
            for monitor in itertools.cycle(self.monitors):
                canvas.Clear()
                canvas, _  = monitor.draw(canvas)
                await asyncio.sleep(5)
                self.frame.matrix.SwapOnVSync(canvas)


    def _has_index(self, index, my_list):
        try:
            my_list[index]
        except IndexError:
            return False

        return True

    async def run_forever_scroll(self):
        logging.info('Running Forever Scroll...')
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

                if not self._has_index(mon_index, monitors):
                    monitors.append(next(monitor_generator))

                canvas, cursor_pos = monitors[mon_index].draw(canvas, cursor_pos=cursor_pos)

            if pos + canvas.width < 0:
                monitors.pop(0)
                pos = mon_0_width - 1

            await asyncio.sleep(0.05)
            self.frame.matrix.SwapOnVSync(canvas)

    async def run_infini_scroll(self):
        logging.info('Running Infini Scroll...')
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

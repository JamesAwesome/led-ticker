#!/usr/bin/env python3

import itertools
import os
import time
import logging
import attr
from frame import Frame
from rgbmatrix import graphics
from async_price_apis import AsyncPriceMonitor, logger
import asyncio
import aiohttp
import itertools
from random import randint

from rgbmatrix import RGBMatrix, RGBMatrixOptions

FONT_SYMBOL = graphics.Font()
FONT_SYMBOL.LoadFont('fonts/7x13.bdf')

FONT_PRICE = graphics.Font()
FONT_PRICE.LoadFont('fonts/6x12.bdf')

FONT_PRICE_SMALL = graphics.Font()
FONT_PRICE_SMALL.LoadFont('fonts/5x8.bdf')

FONT_CHANGE = graphics.Font()
FONT_CHANGE.LoadFont('fonts/6x10.bdf')

DEFAULT_COLOR = graphics.Color(255, 255, 0)
UP_TREND_COLOR = graphics.Color(46, 139, 87)
DOWN_TREND_COLOR = graphics.Color(194, 24, 7)

@attr.s
class LedFrame(object):
    led_rows = attr.ib(default=32)
    led_cols = attr.ib(default=64)
    led_chain = attr.ib(default=1)
    led_parallel = attr.ib(default=1)
    led_pwm_bits = attr.ib(default=11)
    led_brightness = attr.ib(default=100)
    led_gpio_mapping = attr.ib(default='adafruit-hat')
    led_scan_mode = attr.ib(default=1)
    led_pwm_lsb_nanoseconds = attr.ib(default=130)
    led_show_refresh = attr.ib(default=False)
    led_slowdown_gpio = attr.ib(default=1)
    led_no_hardware_pulse = attr.ib(default=False)  # double check
    led_rgb_sequence = attr.ib(default='RGB')
    led_pixel_mapper = attr.ib(default='')
    led_row_addr_type = attr.ib(default=0)
    led_multiplexing = attr.ib(default=0)
    led_panel_type = attr.ib(default='')
    matrix = attr.ib(init=False)

    def __attrs_post_init__(self):
        options = RGBMatrixOptions()

        if self.led_gpio_mapping is not None:
            options.hardware_mapping = self.led_gpio_mapping

        options.rows = self.led_rows
        options.cols = self.led_cols
        options.chain_length = self.led_chain
        options.parallel = self.led_parallel
        options.row_address_type = self.led_row_addr_type
        options.multiplexing = self.led_multiplexing
        options.pwm_bits = self.led_pwm_bits
        options.brightness = self.led_brightness
        options.pwm_lsb_nanoseconds = self.led_pwm_lsb_nanoseconds
        options.led_rgb_sequence = self.led_rgb_sequence
        options.pixel_mapper_config = self.led_pixel_mapper
        options.panel_type = self.led_panel_type

        if self.led_show_refresh:
            options.show_refresh_rate = 1

        if self.led_slowdown_gpio is not None:
            options.gpio_slowdown = self.led_slowdown_gpio

        if self.led_no_hardware_pulse:
            options.disable_hardware_pulsing = True

        self.matrix = RGBMatrix(options=options)

    def get_clean_canvas(self):
        canvas = self.matrix.CreateFrameCanvas()
        canvas.Clear()
        return canvas


@attr.s
class AsyncTicker(object):
    monitors = attr.ib(type=list)
    frame = attr.ib()

    async def run_swap(self):
        logger.info('Running Swap...')
        while True:
            canvas = self.frame.get_clean_canvas()
            for monitor in itertools.cycle(self.monitors):
                canvas.Clear()
                canvas, _  = monitor.draw(canvas)
                await asyncio.sleep(5)
                frame.matrix.SwapOnVSync(canvas)


    def _has_index(self, index, my_list):
        try:
            my_list[index]
        except IndexError:
            return False

        return True

    async def run_forever_scroll(self):
        logger.info('Running Forever Scroll...')
        canvas = self.frame.get_clean_canvas()
        pos = 0

        monitor_generator = itertools.cycle(self.monitors)
        monitors = [next(monitor_generator)]

        while True:
            canvas.Clear()

            mon_index = 0
            canvas, cursor_pos = monitors[mon_index].draw(canvas cursor_pos=pos)
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
            frame.matrix.SwapOnVSync(canvas)

    async def run_infini_scroll(self):
        logger.info('Running Infini Scroll...')
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
            frame.matrix.SwapOnVSync(canvas)


async def main(frame):
    async with aiohttp.ClientSession() as session:

        price_monitors = await asyncio.gather(
            AsyncPriceMonitor.start('ETH', 'USD', session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start('BTC', 'USD', session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start('XLM', 'USD', session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start('SOL', 'USD', session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start('ADA', 'USD', session, 300 + randint(0, 60)),
            AsyncPriceMonitor.start('SUSHI', 'USD', session, 300 + randint(0, 60)),
        )

        await AsyncTicker(
            price_monitors,
            frame
        ).run_forever_scroll()

if __name__ == '__main__':
    frame = LedFrame(
        led_rows=16,
        led_cols=32,
        led_chain=5,
        led_slowdown_gpio=2,
        led_brightness=60,
    )

    asyncio.run(main(frame))

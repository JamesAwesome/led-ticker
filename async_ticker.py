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
            for monitor in itertools.cycle(self.monitors):
                canvas, _  = self.draw(monitor)
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
            canvas, cursor_pos = self.draw(monitors[mon_index], start_pos=pos, canvas=canvas)

            mon_0_width = cursor_pos
            pos -= 1

            while cursor_pos < canvas.width:
                mon_index += 1

                if not self._has_index(mon_index, monitors):
                    monitors.append(next(monitor_generator))

                canvas, cursor_pos = self.draw(monitors[mon_index], start_pos=cursor_pos, canvas=canvas)

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

            canvas, final_pos = self.draw(monitor, start_pos=pos, canvas=canvas)
            pos -= 1

            if (final_pos + canvas.width) - canvas.width == 0:
                pos = canvas.width
                monitor = next(monitor_generator)

            await asyncio.sleep(0.05)
            frame.matrix.SwapOnVSync(canvas)

    async def run_scroll(self):
        logger.info('Running Scroll...')
        canvas = self.frame.get_clean_canvas()
        pos = canvas.width

        while True:
            canvas.Clear()
            canvas, final_pos = self.draw_all(canvas, start_pos=pos)
            pos -= 1

            if (final_pos + canvas.width) - canvas.width == 0:
                pos = canvas.width

            await asyncio.sleep(0.05)
            frame.matrix.SwapOnVSync(canvas)


    def _get_change_width(self, font_change, change_word, padding=6):
        change_width = sum(
            [font_change.CharacterWidth(ord(c)) for c in change_word]
        ) + padding

        return change_width

    def _get_change_color(self, change_str):
        if change_str.startswith('-'):
            return DOWN_TREND_COLOR

        return UP_TREND_COLOR

    def _get_price_font(self, price_str):
        if len(price_str) > 10:
            return FONT_PRICE_SMALL

        return FONT_PRICE

    def draw_all(self, canvas, start_pos=3):
        pos = start_pos

        for monitor in self.monitors:
            canvas, pos = self.draw(monitor, start_pos=pos, canvas=canvas)

        return canvas, pos

    def draw(self, monitor, start_pos=3, canvas=None):
        """Build the ticker canvas given an asset

        Returns:
            A canvas object with the symbol, change, and price drawn.
        """
        # Generate a fresh canvas
        if canvas is None:
            canvas = self.frame.get_clean_canvas()

        change_str = f'{monitor.change_24h:.2f}%'
        price_str = f'{monitor.price:.4f}'

        change_color = self._get_change_color(change_str)
        font_price = self._get_price_font(price_str)

        # Draw the elements on the canvas
        graphics.DrawText(canvas, FONT_SYMBOL, start_pos, 12, DEFAULT_COLOR, monitor.symbol)

        price_x = start_pos + self._get_change_width(FONT_SYMBOL, monitor.symbol)

        graphics.DrawText(canvas, font_price, price_x, 12, DEFAULT_COLOR, price_str)

        change_x = price_x + self._get_change_width(font_price, price_str)

        graphics.DrawText(
            canvas, FONT_CHANGE, change_x, 12, change_color, change_str
        )

        final_pos = change_x + self._get_change_width(FONT_CHANGE, change_str)

        return canvas, final_pos


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

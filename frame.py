#!/usr/bin/env python3

import attr
from rgbmatrix import RGBMatrix, RGBMatrixOptions


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

"""Example led-ticker plugin: a custom 'pulse' color provider (the 'Custom color provider' how-to).

Drop `example_colorprovider/` into your `config/plugins/` (local use), or package it
with an `[project.entry-points."led_ticker.plugins"]  example_colorprovider = "example_colorprovider:register"`
entry, then use it as `font_color = {style = "example_colorprovider.pulse"}`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

import math

from led_ticker.plugin import ColorProviderBase, make_color


def register(api):
    @api.color_provider("pulse")
    class Pulse(ColorProviderBase):
        # One color for the whole string (not per-character).
        per_char = False
        # `color_for` depends on `frame`, so the widget must re-render each tick.
        # Declaring this True would freeze the pulse — ColorProviderBase forces
        # you to set it explicitly.
        frame_invariant = False

        # Config fields come from TOML, e.g.
        #   font_color = {style = "example_colorprovider.pulse", color = [0, 200, 255], speed = 6}
        def __init__(self, color=(0, 200, 255), speed=6):
            self.color = color
            self.speed = speed

        def color_for(self, frame, char_index, total_chars):
            # Brightness breathes between ~0.30 and ~1.00 as the frame advances.
            level = 0.65 + 0.35 * math.sin(frame * self.speed * 0.05)
            r, g, b = self.color
            return make_color(int(r * level), int(g * level), int(b * level))

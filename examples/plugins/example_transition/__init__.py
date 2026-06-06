"""Example led-ticker plugin: a custom 'wipe' transition (the 'Writing a transition' how-to).

Drop `example_transition/` into your `config/plugins/` (local use), or package it
with an `[project.entry-points."led_ticker.plugins"]  example_transition = "example_transition:register"`
entry, then use it in TOML as `transition = {type = "example_transition.wipe"}`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""


def register(api):
    @api.transition("wipe")
    class Wipe:
        # Enough frames for a smooth sweep regardless of the configured duration.
        min_frames = 16

        # A config-driven field: `transition = {type = "example_transition.wipe",
        # color = [255, 0, 0]}` passes `color` here. Default: cyan.
        def __init__(self, color=(0, 255, 255)):
            self.color = color

        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            # The engine clears the canvas before each call — don't clear it here.
            # Draw onto `canvas`; the return value is ignored (returning canvas
            # is just a convention).
            w = canvas.width
            h = getattr(canvas, "height", 16)

            if t >= 1.0:
                incoming.draw(canvas, cursor_pos=0)
                return canvas

            edge = int(t * w)  # the sweep edge moves left -> right, 0 .. w

            outgoing.draw(canvas, cursor_pos=0)  # 1. the old frame fills the canvas
            if edge > 0:  # 2. black out everything the sweep has passed
                canvas.SubFill(0, 0, edge, h, 0, 0, 0)
            for dx in range(2):  # 3. a 2px colored sweep line at the edge
                x = edge + dx
                if 0 <= x < w:
                    for y in range(h):
                        canvas.SetPixel(x, y, self.color[0], self.color[1], self.color[2])
            return canvas

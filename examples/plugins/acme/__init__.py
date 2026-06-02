"""Reference led-ticker plugin — exercises every plugin surface + hook.

Drop this directory into your ``config/plugins/`` (or install it as a package
with an ``[project.entry-points."led_ticker.plugins"]`` entry) and reference its
contributions in TOML as ``acme.<name>`` (e.g. ``type = "acme.clock"``).
"""

from led_ticker.plugin import (
    AnimationFrame,
    BorderEffectBase,
    ColorProviderBase,
    HiResEmoji,
    StartupContext,
    make_color,
)

# Shared state a startup poller updates and the overlay paints (the canonical
# "service plugin" pattern).
_STATE = {"tick": 0}


def register(api):
    @api.widget("clock")
    class Clock:
        def __init__(self, **kwargs):
            self.text = kwargs.get("text", "12:00")

        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            return canvas, cursor_pos

    @api.transition("swoosh")
    class Swoosh:
        min_frames = 0

        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            return canvas

    @api.color_provider("fire")
    class Fire(ColorProviderBase):
        per_char = False
        frame_invariant = True

        def color_for(self, frame, char_index, total_chars):
            return make_color(255, 80, 0)

    @api.animation("scramble")
    class Scramble:
        def frame_for(self, frame, full_text, canvas_width, text_width):
            return AnimationFrame(visible_text=full_text)

    @api.border("neon")
    class Neon(BorderEffectBase):
        frame_invariant = False

        def paint(self, canvas, frame_count):
            return None

    api.easing("snap", lambda p: p * p)
    api.emoji("spark", [(x, y, 255, 200, 0) for x in range(8) for y in range(8)])
    api.emoji("glow", [(x, y, 255, 200, 0) for x in range(8) for y in range(8)])
    api.hires_emoji(
        "glow", HiResEmoji(pixels=((0, 0, 255, 200, 0),), physical_size=16)
    )
    api.font("Brand", "fonts/Brand.ttf")

    def paint(canvas):
        canvas.SetPixel(0, 0, 0, 200, 0)

    api.overlay(paint)

    def on_startup(ctx: StartupContext):
        _STATE["tick"] = 1  # a real plugin might spawn_tracked(poller())

    api.on_startup(on_startup)
    api.on_shutdown(lambda: _STATE.update(tick=0))

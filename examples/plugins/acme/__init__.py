"""Reference led-ticker plugin — exercises every plugin surface + hook.

Drop this directory into your ``config/plugins/`` (or install it as a package
with an ``[project.entry-points."led_ticker.plugins"]`` entry) and reference its
contributions in TOML as ``acme.<name>`` (e.g. ``type = "acme.clock"``).

Field-bearing widgets use ``@attrs.define`` (``attrs`` is a standard project
dependency) so that config validation can inspect ``__attrs_attrs__`` and accept
declared fields. Only led-ticker INTERNAL modules (anything under
``led_ticker.*`` that is not ``led_ticker.plugin``) are off-limits; ``attrs``
and stdlib imports are fine.
"""

import attrs

from led_ticker.plugin import (
    AnimationFrame,
    BorderEffectBase,
    ColorProviderBase,
    HiResEmoji,
    StartupContext,
    draw_text,
    make_color,
    resolve_font,
    spawn_tracked,
)

# Shared state a startup poller updates and the overlay paints (the canonical
# "service plugin" pattern).
_STATE = {"tick": 0}


def register(api):
    @api.widget("clock")
    @attrs.define
    class Clock:
        text: str = "12:00"
        # Declare a `font_color` field to accept the standard
        # `font_color = {style = "acme.fire"}` knob — the loader coerces it to a
        # color provider and injects it here. (A plain widget without this field
        # rejects font_color as an unknown field.)
        font_color: object = None

        @classmethod
        def validate_config(cls, cfg):
            # Cross-field example: reject empty text (a Phase-D convention check).
            return ["text must not be empty"] if cfg.get("text") == "" else []

        # `font_color=` is part of the Widget.draw protocol but unused here;
        # this widget reads its injected `self.font_color` field (set at
        # attrs-init) instead.
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            font = resolve_font("6x12")
            color = make_color(255, 255, 255)
            # If a color provider was injected via the `font_color` field, use
            # its first color; otherwise default to white.
            provider = self.font_color
            if provider is not None and hasattr(provider, "color_for"):
                color = provider.color_for(0, 0, len(self.text))
            return canvas, draw_text(canvas, font, self.text, cursor_pos, 10, color)

    @api.transition("swoosh")
    class Swoosh:
        min_frames = 0

        # A config-driven field: reference this transition in TOML as
        #   transition = {type = "acme.swoosh", threshold = 0.3}
        # and the loader passes `threshold` to this constructor (clean ValueError
        # for unknown/missing keys — see _build_plugin_style).
        def __init__(self, threshold=0.5):
            self.threshold = threshold

        def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
            # A transition renders TO `canvas` (the engine ignores the return
            # value). Hard cut at `threshold`: outgoing before it, incoming after.
            frame = incoming if t >= self.threshold else outgoing
            frame.draw(canvas, cursor_pos=0)
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
        "glow",
        HiResEmoji(
            pixels=tuple(
                (x, y, 255, 200, 0)
                for x in range(16)
                for y in range(16)
                if 4 <= x < 12 and 4 <= y < 12
            ),
            physical_size=16,
        ),
    )
    api.font("Brand", "fonts/Brand.ttf")

    def paint(canvas):
        canvas.SetPixel(0, 0, 0, 200, 0)

    api.overlay(paint)

    async def _poll():
        # A real poller would fetch state on an interval with
        # `await asyncio.sleep(...)`. Kept minimal here so tests don't hang.
        _STATE["tick"] += 1

    def on_startup(ctx: StartupContext):
        # Start background work via spawn_tracked (must be a coroutine); the
        # overlay above paints whatever _STATE the poller updates.
        spawn_tracked(_poll())

    api.on_startup(on_startup)
    api.on_shutdown(lambda: _STATE.update(tick=0))

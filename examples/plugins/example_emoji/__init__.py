"""Example led-ticker plugin: a custom inline emoji (the 'Custom emoji' how-to).

Drop `example_emoji/` into your `config/plugins/` (local use), or package it with
an `[project.entry-points."led_ticker.plugins"]  example_emoji = "example_emoji:register"`
entry, then use it inline in any message as `:example_emoji.heart:`.

Imports only `led_ticker.plugin` (the public surface) plus stdlib.
"""

from led_ticker.plugin import HiResEmoji

# An 8x8 heart. "X" = a lit pixel, "." = transparent.
_HEART_ART = [
    ".XX..XX.",
    "XXXXXXXX",
    "XXXXXXXX",
    "XXXXXXXX",
    ".XXXXXX.",
    "..XXXX..",
    "...XX...",
    "........",
]
_RED = (220, 40, 60)

# Low-res sprite: a PixelData = list of (x, y, r, g, b), one tuple per lit pixel.
HEART = [
    (x, y, *_RED)
    for y, row in enumerate(_HEART_ART)
    for x, cell in enumerate(row)
    if cell == "X"
]

# Hi-res sprite: scale the 8x8 up 2x into a 16x16, in physical coordinates.
HEART_HIRES = tuple(
    (x * 2 + dx, y * 2 + dy, r, g, b)
    for (x, y, r, g, b) in HEART
    for dx in (0, 1)
    for dy in (0, 1)
)


def register(api):
    # Low-res: used by inline `:example_emoji.heart:` and small / unscaled signs.
    api.emoji("heart", HEART)
    # Hi-res: used on scaled (big) signs; keep the low-res one for inline use.
    api.hires_emoji("heart", HiResEmoji(pixels=HEART_HIRES, physical_size=16))

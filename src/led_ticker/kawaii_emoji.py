"""Cute / anime emoji — hand-drawn 8×8 lowres sprites for scale-1 signs.

Same shape as ``fall_emoji.py``: the standard-emoji pack ships Noto glyphs
for these (``:cherry_blossom:`` 🌸, ``:steaming_bowl:`` 🍜) but every pack
sprite is hires-only, so on an unscaled sign (smallsign,
``default_scale = 1``) it strips to nothing. Each sprite here is drawn by
hand on the 8×8 grid.

Every slug in this module is a **pack fallback**: it ALSO exists in the
standard-emoji pack. The lowres here is what a scale-1 sign draws; on a
scaled sign the hires resolver finds no curated hires and falls through to
the pack's Noto glyph, so the bigsign renders unchanged. One slug, both
signs. Unicode (🌸 / 🍜) reaches the same sprite via the pack's codepoint
map. Never register a curated hires for one of these slugs — it would
shadow Noto (``tests/test_emoji_pack_asset.py::test_no_curated_collisions``
checks the aggregate ``pixel_emoji.PACK_FALLBACK_SLUGS``).

Slug names follow the pack's CLDR short names so the fallback lines up:
🍜 is ``steaming_bowl`` (not ``ramen``) — a ``ramen`` slug would be
curated-only and block-expand on the bigsign.

Sprite rules (pinned by ``tests/test_kawaii_emoji.py``): every art row is 8
cells and there are 8 rows, no duplicate cells, every lit pixel has
``max(r, g, b) >= 30`` (an unlit LED IS black), and the lowest lit row is
6 or 7 — inline lowres emoji anchor at ``baseline - 8``, so a shorter
sprite floats above the text.

Design notes from the smallsign spike (2026-11-12): a rounded five-petal
blossom reads as a HEART at 8×8 — the petals need real notches between
them, so the blossom below is five distinct lobes (top, two sides, two
bottom) around a yellow center. The bowl is a white body with a red rim
band; a red body with a white rim read as a mouth with teeth.
"""

from led_ticker._types import PixelData

# Palette. One letter per color so the art strings stay legible.
_PALETTE: dict[str, tuple[int, int, int]] = {
    "P": (255, 120, 170),  # sakura pink
    "Y": (255, 220, 60),  # yellow (blossom center, noodles)
    "W": (240, 240, 240),  # white (bowl)
    "R": (220, 40, 30),  # red (bowl rim band + pattern)
    "T": (210, 160, 90),  # tan (chopsticks — brown is too dim on LEDs)
    "S": (110, 110, 120),  # steam gray
}

# "." = transparent. 8 rows × 8 columns, row 0 at the top.
_ART: dict[str, list[str]] = {
    # 🌸 cherry blossom: five distinct lobes around a yellow center.
    "cherry_blossom": [
        "...PP...",
        ".P.PP.P.",
        "PPPPPPPP",
        ".PPYYPP.",
        ".PPYYPP.",
        "PPPPPPPP",
        ".PP..PP.",
        ".PP..PP.",
    ],
    # 🍜 steaming bowl: steam, tan chopsticks lifting yellow noodles out of a
    # white bowl with a red rim band.
    "steaming_bowl": [
        "..S.S.TT",
        ".S.S.TT.",
        ".YYYYTY.",
        "RRRRRRRR",
        "WWWWWWWW",
        "WWRWWRWW",
        ".WWWWWW.",
        "..WWWW..",
    ],
}

# Every slug here ALSO exists in the standard-emoji pack. Their lowres lives
# here; their hires stays the pack's Noto glyph (no curated hires is
# registered).
KAWAII_PACK_FALLBACK_SLUGS: frozenset[str] = frozenset(_ART)


def _pixels(art: list[str]) -> PixelData:
    return [
        (x, y, *_PALETTE[cell])
        for y, row in enumerate(art)
        for x, cell in enumerate(row)
        if cell != "."
    ]


KAWAII_LOWRES: dict[str, PixelData] = {slug: _pixels(art) for slug, art in _ART.items()}

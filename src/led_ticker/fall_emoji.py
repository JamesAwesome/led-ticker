"""Autumn / Halloween emoji — hand-drawn 8×8 lowres sprites for scale-1 signs.

Why this module exists. The standard-emoji pack ships Noto glyphs for the
whole season (``:jack_o_lantern:``, ``:maple_leaf:``, ``:turkey:``, ...) but
every pack sprite is hires-only: on an unscaled sign (smallsign,
``default_scale = 1``) it strips to nothing. Downsampling a 32×32 Noto glyph
to 8×8 was tried first and every candidate lost its silhouette, so each
sprite here is drawn by hand on the 8×8 grid.

Two kinds of slug live here, and ``FALL_PACK_FALLBACK_SLUGS`` tells them
apart:

* **Pack fallbacks** — slugs that ALSO exist in the standard-emoji pack
  (``jack_o_lantern``, ``ghost``, ``bat``, ...). The lowres sprite here is
  what a scale-1 sign draws; on a scaled sign the hires resolver finds no
  curated hires for the slug and falls through to the pack's Noto glyph, so
  the bigsign keeps rendering exactly what it did before. One slug, both
  signs. Unicode (🎃) reaches the same sprite via the pack's codepoint map.
  These are the ONE sanctioned overlap between the curated registry and the
  pack — see ``tests/test_emoji_pack_asset.py::test_no_curated_collisions``.
* **Curated-only** — ``pumpkin``, ``acorn``, ``candy_corn``: no CLDR
  emoji, so no pack glyph. Lowres-only; a scaled sign block-expands them.

Sprite rules (pinned by ``tests/test_fall_emoji.py``): fits 8×8, no
duplicate cells, no pixel darker than ``max(r, g, b) < 30`` (an unlit LED IS
black, so eyes / mouths / pupils use a visible dark gray), and the lowest lit
row is 6 or 7 — inline lowres emoji anchor at ``baseline - 8``, so a shorter
sprite floats above the text.
"""

from led_ticker._types import PixelData

# Palette. One letter per color so the art strings stay legible.
_PALETTE: dict[str, tuple[int, int, int]] = {
    "O": (255, 120, 20),  # pumpkin orange
    "o": (230, 90, 10),  # pumpkin rib (darker orange)
    "R": (220, 40, 30),  # red
    "r": (255, 90, 40),  # red-orange (leaf body)
    "Y": (255, 220, 60),  # yellow
    "y": (255, 240, 170),  # pale yellow (flame core)
    "G": (40, 160, 40),  # green
    "g": (30, 110, 30),  # dark green
    "B": (120, 70, 25),  # brown
    "b": (80, 45, 15),  # dark brown
    "T": (210, 160, 90),  # tan
    "W": (240, 240, 240),  # white
    "w": (150, 150, 160),  # gray (web)
    "K": (30, 30, 30),  # visible-black (eyes, mouths)
    "P": (140, 90, 190),  # purple (bat — a black bat would vanish)
    "S": (110, 110, 120),  # steam gray
    "C": (255, 240, 200),  # cream (mushroom stem)
}

# "." = transparent. 8 rows × 8 columns, row 0 at the top.
_ART: dict[str, list[str]] = {
    # 🍁 maple leaf: five lobes, a lighter center vein, brown stem.
    "maple_leaf": [
        "...R....",
        ".R.R.R..",
        ".RrrrR..",
        "RrrOrrr.",
        ".rrOrr..",
        "..rOr...",
        "...B....",
        "...B....",
    ],
    # 🍂 fallen leaf: tan oval on the diagonal with a dark midrib.
    "fallen_leaf": [
        "......bb",
        "....TTbT",
        "...TTbTT",
        "..TTbTTT",
        "..TbTTT.",
        "..bTTT..",
        ".b......",
        "........",
    ],
    # 🎃 jack-o'-lantern: yellow eyes and a jagged yellow grin.
    "jack_o_lantern": [
        "...g....",
        "..gO....",
        ".OOOOOO.",
        "OOOOOOOO",
        "OYOOOOYO",
        "OOOOOOOO",
        "OYOYYOYO",
        ".OOOOOO.",
    ],
    # plain pumpkin (no CLDR emoji): ribbed orange body, green stem.
    "pumpkin": [
        "...g....",
        "..gg....",
        ".OoOOoO.",
        "OOoOOoOO",
        "OOoOOoOO",
        "OOoOOoOO",
        "OOoOOoOO",
        ".OOOOOO.",
    ],
    # acorn (no CLDR emoji): dark-brown cap over a tan nut.
    "acorn": [
        "...b....",
        "..bbbb..",
        ".bbbbbb.",
        ".bbbbbb.",
        "..TTTT..",
        "..TTTT..",
        "..TTTT..",
        "...TT...",
    ],
    # 🍎 red apple: stem + leaf, dimpled bottom.
    "red_apple": [
        "....B...",
        "...BG...",
        ".RRRRRR.",
        "RRRRRRRR",
        "RRRRRRRR",
        "RRRRRRRR",
        ".RRRRRR.",
        "..RR.RR.",
    ],
    # 🍄 mushroom: red cap with white spots, cream stem.
    "mushroom": [
        "..RRRR..",
        ".RWRRWR.",
        "RRRRRRRR",
        "RWRRRWRR",
        "..CCCC..",
        "..CCCC..",
        "..CCCC..",
        ".CCCCCC.",
    ],
    # 🌽 ear of corn: yellow cob, green husk peeling right and down.
    "ear_of_corn": [
        "...gG...",
        "..YYG...",
        ".YYYYG..",
        ".YYYY.G.",
        ".YYYY...",
        "GYYYYg..",
        "GgYYgG..",
        ".GG.G...",
    ],
    # 🦃 turkey: red/orange fan tail behind a brown body facing right,
    # yellow beak, red wattle, yellow legs.
    "turkey": [
        ".ROROR..",
        "RORORORO",
        "ROROROR.",
        ".bBBBBb.",
        "..BBBBY.",
        "..BBBBr.",
        "..BBBB..",
        "..Y..Y..",
    ],
    # 👻 ghost: white sheet, dark eyes, wavy hem.
    "ghost": [
        "..WWWW..",
        ".WWWWWW.",
        ".WKWWKW.",
        ".WWWWWW.",
        ".WWWWWW.",
        ".WWWWWW.",
        ".WWWWWW.",
        ".W.WW.W.",
    ],
    # 🦇 bat: purple so it reads against an unlit panel.
    "bat": [
        "........",
        "........",
        "P......P",
        "PP.PP.PP",
        "PPPPPPPP",
        ".PPPPPP.",
        "..P..P..",
        "........",
    ],
    # ☕ hot beverage: steam, white mug with a handle on the right.
    "hot_beverage": [
        "..S.S...",
        ".S.S....",
        "........",
        "WWWWW...",
        "WBBBWWW.",
        "WBBBW.W.",
        "WBBBWWW.",
        ".WWW....",
    ],
    # 🕯 candle: yellow flame with a pale core, white pillar, brown base.
    "candle": [
        "...Y....",
        "..YyY...",
        "...o....",
        "..WWW...",
        "..WWW...",
        "..WWW...",
        "..WWW...",
        ".BBBBB..",
    ],
    # 🍬 candy: red wrapped sweet, twisted ends, white highlight.
    "candy": [
        "........",
        "........",
        "........",
        ".R..RR.R",
        "RR.RRRR.",
        ".RRWRWRR",
        "RR.RRRR.",
        ".R..RR.R",
    ],
    # candy corn (no CLDR emoji): white tip, orange middle, yellow base.
    "candy_corn": [
        "........",
        "...W....",
        "..WWW...",
        "..OOO...",
        ".OOOOO..",
        ".OOOOO..",
        ".YYYYY..",
        "YYYYYYY.",
    ],
    # 💀 skull: dark eye sockets, nose, jaw with tooth gaps.
    "skull": [
        "..WWWW..",
        ".WWWWWW.",
        "WWKWWKWW",
        "WWKWWKWW",
        "WWWWWWWW",
        ".WWKKWW.",
        "..WWWW..",
        "..WKWK..",
    ],
    # 🦉 owl: ear tufts, white eyes with pupils, yellow beak, tan belly.
    "owl": [
        ".B....B.",
        ".BBBBBB.",
        "BWKBBKWB",
        "BBBBYBBB",
        ".BTTTTB.",
        ".BTTTTB.",
        ".BBBBBB.",
        "..B..B..",
    ],
    # 🕸 spider web: hung in the top-left corner, spokes + two arcs.
    "spider_web": [
        "wwwwwwww",
        "w..w..w.",
        "w.w..w..",
        "www.w...",
        "w..ww...",
        "w.ww....",
        "ww......",
        "w.......",
    ],
    # 🪾 leafless tree: bare branches over a trunk.
    "leafless_tree": [
        "B.B.B.B.",
        ".B.B.B..",
        "..BBB...",
        "...B....",
        "...B....",
        "...B....",
        "...B....",
        "..BBB...",
    ],
}

# Slugs that ALSO exist in the standard-emoji pack. Their lowres lives here;
# their hires stays the pack's Noto glyph (no curated hires is registered).
FALL_PACK_FALLBACK_SLUGS: frozenset[str] = frozenset(
    {
        "maple_leaf",
        "fallen_leaf",
        "jack_o_lantern",
        "red_apple",
        "mushroom",
        "ear_of_corn",
        "turkey",
        "ghost",
        "bat",
        "hot_beverage",
        "candle",
        "candy",
        "skull",
        "owl",
        "spider_web",
        "leafless_tree",
    }
)


def _pixels(art: list[str]) -> PixelData:
    return [
        (x, y, *_PALETTE[cell])
        for y, row in enumerate(art)
        for x, cell in enumerate(row)
        if cell != "."
    ]


FALL_LOWRES: dict[str, PixelData] = {slug: _pixels(art) for slug, art in _ART.items()}

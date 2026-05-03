# src/led_ticker/transitions/_hires_registry.py
"""Registry of hi-res sprite assets for sprite-based transitions.

When a transition's name appears here AND the canvas is a ScaledCanvas,
the dispatch in `nyancat.py` / `pokeball.py` picks the hi-res render
path. Reverse variants reuse the base sprite file and flip horizontally
at decode time so we ship one asset per family, not two.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SPRITES_DIR = Path(__file__).parent / "sprites"


@dataclass(frozen=True)
class HiresSpec:
    """Describes one hi-res sprite asset.

    `sprite_path` points at the bundled gif/webp inside the package.
    `flip_horizontal=True` mirrors each frame at decode (used for
    `*_reverse` variants so the cat/pikachu faces its travel direction).
    `trail` selects the band painted behind the sprite to erase outgoing
    text: ``"none"`` paints nothing, ``"black"`` fills the band with
    black (e.g. pokeball), ``"rainbow"`` fills it with 6 horizontal RGB
    stripes (e.g. nyancat).
    """

    sprite_path: Path
    flip_horizontal: bool
    trail: str = "none"


HIRES_REGISTRY: dict[str, HiresSpec] = {
    "nyancat": HiresSpec(
        sprite_path=SPRITES_DIR / "nyancat.webp",
        flip_horizontal=False,
        trail="rainbow",
    ),
    "nyancat_reverse": HiresSpec(
        sprite_path=SPRITES_DIR / "nyancat.webp",
        flip_horizontal=True,
        trail="rainbow",
    ),
    "pokeball": HiresSpec(
        sprite_path=SPRITES_DIR / "pikachu-run-transparent.gif",
        flip_horizontal=False,
        trail="black",
    ),
    "pokeball_reverse": HiresSpec(
        sprite_path=SPRITES_DIR / "pikachu-run-transparent.gif",
        flip_horizontal=True,
        trail="black",
    ),
}

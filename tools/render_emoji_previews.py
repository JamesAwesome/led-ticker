"""Generate per-slug PNG previews of every inline emoji.

Writes one lowres + one hires PNG per slug to
`docs/site/public/emoji/`. The docs site embeds these via root-absolute
URLs (`/emoji/<slug>-low.png`, `/emoji/<slug>-hi.png`).

Each PNG is rendered against a panel-black background so what you see
in the docs is what the LED panel will display. Lowres sprites are
nearest-neighbour upscaled so each logical pixel is a clean square.

Re-run after sprite edits:
    uv run python tools/render_emoji_previews.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from PIL import Image  # noqa: E402

from led_ticker.pixel_emoji import HIRES_REGISTRY, _get_registry  # noqa: E402

OUT = REPO / "docs" / "site" / "public" / "emoji"
BG = (0, 0, 0)
TARGET_PX = 96  # both lowres and hires renders end up at this square size


def _render_lowres(slug: str, sprite) -> Image.Image:
    width = max(x for x, _, *_ in sprite) + 1
    height = max(y for _, y, *_ in sprite) + 1
    img = Image.new("RGB", (width, height), BG)
    for x, y, r, g, b in sprite:
        img.putpixel((x, y), (r, g, b))
    scale = max(1, TARGET_PX // max(width, height))
    return img.resize((width * scale, height * scale), Image.NEAREST)


def _render_hires(slug: str, hires) -> Image.Image:
    size = hires.physical_size
    img = Image.new("RGB", (size, size), BG)
    for x, y, r, g, b in hires.pixels:
        if 0 <= x < size and 0 <= y < size:
            img.putpixel((x, y), (r, g, b))
    scale = max(1, TARGET_PX // size)
    return img.resize((size * scale, size * scale), Image.NEAREST)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    low = _get_registry()
    hi = HIRES_REGISTRY

    for slug in sorted(set(low) | set(hi)):
        if slug in low:
            _render_lowres(slug, low[slug]).save(OUT / f"{slug}-low.png")
        if slug in hi:
            _render_hires(slug, hi[slug]).save(OUT / f"{slug}-hi.png")

    print(f"Wrote {len(list(OUT.glob('*.png')))} PNGs to {OUT}")


if __name__ == "__main__":
    main()

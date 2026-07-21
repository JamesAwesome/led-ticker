"""Generate per-slug PNG previews of every inline emoji.

Writes one lowres + one hires PNG per slug to
`docs/site/public/emoji/`. The docs site embeds these via root-absolute
URLs (`/emoji/<slug>-low.png`, `/emoji/<slug>-hi.png`).

Each PNG is rendered against a panel-black background so what you see
in the docs is what the LED panel will display. Lowres sprites are
nearest-neighbour upscaled so each logical pixel is a clean square.

Re-run after sprite edits:
    uv run python tools/render_emoji_previews.py

Re-run after standard-emoji pack edits (`tools/gen_emoji_pack.py`):
    uv run python tools/render_emoji_previews.py --pack-sheets
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from led_ticker import emoji_pack  # noqa: E402
from led_ticker.pixel_emoji import HIRES_REGISTRY, _get_registry  # noqa: E402

OUT = REPO / "docs" / "site" / "public" / "emoji"
BG = (0, 0, 0)
TARGET_PX = 96  # both lowres and hires renders end up at this square size

# Standard-emoji pack contact sheets: slugs are grouped by codepoint into
# a handful of named groups (not one file per slug — ~1,400 pack slugs
# would be unwieldy). Boundaries follow the Unicode emoji block layout;
# every pack slug must fall in exactly one group, so the ranges below
# partition the full codepoint space the pack draws from (checked by
# `_group_for_codepoint`'s fallback branch, which would raise on a gap).
PACK_GROUPS: list[tuple[str, list[tuple[int, int]]]] = [
    ("smileys", [(0x1F600, 0x1F64F)]),
    ("animals-nature", [(0x1F300, 0x1F32C), (0x1F400, 0x1F4FF)]),
    ("food-drink", [(0x1F32D, 0x1F37F)]),
    ("activities-objects", [(0x1F380, 0x1F3FF), (0x1F500, 0x1F7FF)]),
    ("symbols", [(0x0000, 0x1F2FF)]),
    ("misc", [(0x1F900, 0x1FFFF)]),
]


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


def _group_for_codepoint(cp: int) -> str:
    for name, ranges in PACK_GROUPS:
        for lo, hi in ranges:
            if lo <= cp <= hi:
                return name
    raise ValueError(f"codepoint {cp:#x} not covered by any PACK_GROUPS range")


def _pack_slug_codepoints() -> dict[str, int]:
    """slug -> codepoint for every entry in the standard-emoji pack.

    The public API only exposes the reverse lookup (`slug_for_codepoint`)
    since that's what runtime rendering needs. This tool needs the
    forward direction to bucket slugs by codepoint, so it reaches into
    the loader's private reverse index and inverts it (every pack entry
    has exactly one codepoint and `load_index` builds a 1:1 map, verified
    by the count assertion below).
    """
    emoji_pack.load_index()
    cp_to_slug = emoji_pack._cp_to_slug  # noqa: SLF001
    slug_to_cp = {slug: cp for cp, slug in cp_to_slug.items()}
    slugs = emoji_pack.pack_slugs()
    missing = [s for s in slugs if s not in slug_to_cp]
    if missing:
        raise ValueError(
            f"{len(missing)} pack slugs have no known codepoint: {missing[:5]}"
        )
    return slug_to_cp


def _pack_sprite_cell(
    slug: str, cell_w: int, cell_h: int, sprite_px: int, font
) -> Image.Image:
    hires = emoji_pack.get_sprite(slug)
    cell = Image.new("RGB", (cell_w, cell_h), BG)
    if hires is not None:
        sprite_img = _render_hires(slug, hires).resize(
            (sprite_px, sprite_px), Image.NEAREST
        )
        cell.paste(sprite_img, ((cell_w - sprite_px) // 2, 2))
    draw = ImageDraw.Draw(cell)
    label = slug if len(slug) <= 14 else slug[:13] + "…"
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(
        ((cell_w - text_w) // 2, sprite_px + 6),
        label,
        fill=(180, 180, 180),
        font=font,
    )
    return cell


def render_pack_sheets() -> None:
    """Render one labeled contact-sheet PNG per PACK_GROUPS entry to
    `docs/site/public/emoji/pack-<group>.png`."""
    OUT.mkdir(parents=True, exist_ok=True)
    slug_to_cp = _pack_slug_codepoints()

    grouped: dict[str, list[str]] = {name: [] for name, _ in PACK_GROUPS}
    for slug, cp in slug_to_cp.items():
        grouped[_group_for_codepoint(cp)].append(slug)

    font = ImageFont.load_default()
    sprite_px = 64
    cell_w, cell_h = 84, sprite_px + 20

    for name, _ranges in PACK_GROUPS:
        slugs = sorted(grouped[name])
        n = len(slugs)
        cols = min(20, max(8, round(math.sqrt(n) * 1.3))) if n else 1
        rows = math.ceil(n / cols) if n else 1
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), BG)
        for i, slug in enumerate(slugs):
            r, c = divmod(i, cols)
            cell = _pack_sprite_cell(slug, cell_w, cell_h, sprite_px, font)
            sheet.paste(cell, (c * cell_w, r * cell_h))
        out_path = OUT / f"pack-{name}.png"
        sheet.save(out_path)
        print(f"Wrote {out_path} ({n} slugs, {cols}x{rows} grid)")


if __name__ == "__main__":
    if "--pack-sheets" in sys.argv:
        render_pack_sheets()
    else:
        main()

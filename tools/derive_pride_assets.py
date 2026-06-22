"""Generate the CC0 pride sample assets (replaces third-party pride art).

Two assets:
- pride.gif      — 6-stripe rainbow flag (1000×700)
- pride_trans.gif — 5-stripe trans pride flag (498×280)

Both are project-original, animated by scrolling the flag vertically
(ImageChops.offset wraps) for a seamless loop. Reproducible.
Run: `make derive-pride`.
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "config" / "assets"

# Classic 6-stripe rainbow (generic public-domain arrangement).
BANDS = [
    (228, 3, 3),  # red
    (255, 140, 0),  # orange
    (255, 237, 0),  # yellow
    (0, 128, 38),  # green
    (0, 77, 255),  # blue
    (117, 7, 135),  # violet
]

# Trans pride flag — 5 symmetric stripes.
TRANS_BANDS = [
    (91, 206, 250),  # light blue
    (245, 169, 184),  # pink
    (255, 255, 255),  # white
    (245, 169, 184),  # pink
    (91, 206, 250),  # light blue
]

N_FRAMES = 12


def _base(w: int, h: int, bands: list[tuple[int, int, int]]) -> Image.Image:
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    band_h = h / len(bands)
    for i, color in enumerate(bands):
        draw.rectangle([0, round(i * band_h), w, round((i + 1) * band_h)], fill=color)
    return img


def _frames(w: int, h: int, bands: list[tuple[int, int, int]]) -> list[Image.Image]:
    base = _base(w, h, bands)
    # Scroll the whole flag vertically by a full height over N frames (wraps to
    # the start at frame N -> seamless loop).
    return [
        ImageChops.offset(base, 0, round(i * h / N_FRAMES)) for i in range(N_FRAMES)
    ]


def main() -> None:
    configs = [
        ("pride.gif", 1000, 700, BANDS),
        ("pride_trans.gif", 498, 280, TRANS_BANDS),
    ]
    for name, w, h, bands in configs:
        frames = _frames(w, h, bands)
        frames[0].save(
            OUT / name, save_all=True, append_images=frames[1:], duration=80, loop=0
        )


if __name__ == "__main__":
    main()

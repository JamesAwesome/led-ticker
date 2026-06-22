"""Generate the CC0 6-stripe rainbow sample assets (replaces third-party pride art).

Project-original: six solid horizontal color bands, animated by scrolling the
rainbow vertically (ImageChops.offset wraps) so the gif-widget demo moves and
loops seamlessly. Reproducible. Run: `make derive-pride`.
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
N_FRAMES = 12


def _base(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    band_h = h / len(BANDS)
    for i, color in enumerate(BANDS):
        draw.rectangle([0, round(i * band_h), w, round((i + 1) * band_h)], fill=color)
    return img


def _frames(w: int, h: int) -> list[Image.Image]:
    base = _base(w, h)
    # Scroll the whole flag vertically by a full height over N frames (wraps to
    # the start at frame N -> seamless loop).
    return [
        ImageChops.offset(base, 0, round(i * h / N_FRAMES)) for i in range(N_FRAMES)
    ]


def main() -> None:
    for name, (w, h) in {
        "pride.gif": (1000, 700),
        "pride_trans.gif": (498, 280),
    }.items():
        frames = _frames(w, h)
        frames[0].save(
            OUT / name, save_all=True, append_images=frames[1:], duration=80, loop=0
        )


if __name__ == "__main__":
    main()

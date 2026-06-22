"""Generate the CC0 heart-tunnel backdrop (replaces third-party asset).

Project-original procedurally-generated image: concentric trans-pride hearts
receding to a center vanishing point. The palette cycles light-blue → pink →
white → pink (symmetric outward). Reproducible. Run: `make derive-heart-tunnel`.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "config" / "assets" / "heart-tunnel-opaque.jpg"
W, H = 700, 350
# Trans-pride, symmetric outward.
BLUE, PINK, WHITE = (91, 206, 250), (245, 169, 184), (255, 255, 255)
PALETTE = [BLUE, PINK, WHITE, PINK]
N_RINGS = 22


def _heart(cx: float, cy: float, s: float) -> list[tuple[float, float]]:
    """Generate a heart curve at center (cx, cy) with scale s."""
    pts = []
    t = 0.0
    while t < 2 * math.pi:
        x = 16 * math.sin(t) ** 3
        y = (
            13 * math.cos(t)
            - 5 * math.cos(2 * t)
            - 2 * math.cos(3 * t)
            - math.cos(4 * t)
        )
        pts.append((cx + x * s, cy - y * s))
        t += 0.04
    return pts


def main() -> None:
    img = Image.new("RGB", (W, H), PALETTE[0])
    draw = ImageDraw.Draw(img)
    cx, cy = W / 2, H / 2 + 18  # heart curve sits high; nudge down to recenter
    big = H / 22
    for i in range(N_RINGS):
        # ease so rings bunch toward the centre (depth)
        s = big * (1 - i / N_RINGS) ** 1.25
        draw.polygon(_heart(cx, cy, s), fill=PALETTE[i % len(PALETTE)])
    img.save(OUT, "JPEG", quality=92)


if __name__ == "__main__":
    main()

# CC0 heart-tunnel asset (open-source-prep follow-up #1)

**Date:** 2026-06-22
**Status:** approved (design)
**Goal:** Replace the unattributed third-party `config/assets/heart-tunnel-opaque.jpg` with a project-original,
procedurally-generated CC0 image — concentric trans-pride hearts receding to a center (a "heart tunnel").

## Background

`config/assets/heart-tunnel-opaque.jpg` (700×350 RGB JPEG) is an opaque backdrop of unknown provenance — one
of the two `.jpg` test assets flagged in the gate-1 review (the other, `moonscape-opaque.jpg`, stays a tracked
follow-up — out of scope here). It is referenced ONLY by `config/config.image_test.example.toml` (3 `path =`
lines + 2 comments), the StillImage-widget test config (fit-mode cycling + a text "knockout" overlay test). It
is NOT referenced by any docs-site demo, so there is no committed demo GIF to re-render. Mirrors the
just-merged CC0 derives (`tools/derive_pride_assets.py`, `tools/derive_phoenix_assets.py`).

## Decisions (approved with the user)

- **Static** image (not animated): it is the StillImage widget's test backdrop (incl. a JPEG-source decode
  test + a text-knockout test); animating it would change the widget role + the test intent.
- **Same filename + format:** keep `config/assets/heart-tunnel-opaque.jpg` (700×350, RGB **JPEG**) — zero
  repoint, and the image_test config intentionally exercises a JPEG source.
- **Visual:** concentric hearts receding to a center vanishing point; ring colors cycle the trans-pride palette
  **light-blue `[91, 206, 250]` → pink `[245, 169, 184]` → white `[255, 255, 255]` → pink** (symmetric
  outward). The approved prototype is staged at `.superpowers/heart_tunnel_proto.py`.

## Component

### `tools/derive_heart_tunnel.py` (committed, Pillow — sibling to derive_pride/derive_phoenix)

Generates `config/assets/heart-tunnel-opaque.jpg` from code alone (no third-party source), reproducible. The
proven algorithm (from the approved prototype):

```python
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
    pts = []
    t = 0.0
    while t < 2 * math.pi:
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s, cy - y * s))
        t += 0.04
    return pts


def main() -> None:
    img = Image.new("RGB", (W, H), PALETTE[0])
    draw = ImageDraw.Draw(img)
    cx, cy = W / 2, H / 2 + 18          # heart curve sits high; nudge down to recenter
    big = H / 22
    for i in range(N_RINGS):
        s = big * (1 - i / N_RINGS) ** 1.25   # ease so rings bunch toward the centre (depth)
        draw.polygon(_heart(cx, cy, s), fill=PALETTE[i % len(PALETTE)])
    img.save(OUT, "JPEG", quality=92)


if __name__ == "__main__":
    main()
```

(Match the existing derive scripts' module docstring / ROOT-path / `__main__` conventions. Document the CC0
origin + the trans palette in the docstring.)

### `make derive-heart-tunnel` target

Add to `.PHONY` + a target mirroring `derive-pride`:
```makefile
derive-heart-tunnel:  ## Re-generate config/assets/heart-tunnel-opaque.jpg (CC0 trans heart tunnel)
	$(UVRUN) python tools/derive_heart_tunnel.py
```

### ATTRIBUTION

Add an entry to `config/assets/ATTRIBUTION.md`: `heart-tunnel-opaque.jpg` is project-generated CC0 by
`tools/derive_heart_tunnel.py` (concentric trans-pride hearts; the palette RGBs); no third-party source.

### Test

Extend `tests/test_phoenix_assets.py` (or a small new `tests/test_heart_tunnel_asset.py`): the file exists, is
**JPEG**, **700×350**, mode **RGB**.

## Removals / repoint

None — same filename. The 3 `config.image_test.example.toml` references + comments are unchanged (the comment
already reads "700×350 RGB JPEG", which stays accurate). Confirm the config still loads after regeneration.

## Testing / verification

- `make derive-heart-tunnel` regenerates the file; the new test passes (exists / JPEG / 700×350 / RGB).
- Reproducible: re-running the script produces the same image (deterministic — no RNG).
- `git grep -n "heart-tunnel" -- config docs` unchanged (3 refs + comments still valid; no broken path).
- Full suite green; `uv run --extra dev ruff check tools/ tests/` + `ruff format` clean. (No docs-site prose
  changes → docs build unaffected, but run `make docs-build` if any .mdx is touched.)
- The all-asset-paths-resolve audit (from #257) still `none ✓`.

## Non-goals

- `config/assets/moonscape-opaque.jpg` — the sibling unattributed JPEG; separate tracked follow-up (it needs
  its own visual + color decision).
- Animating the asset (it's a StillImage backdrop).
- Restyling the image_test config beyond regenerating the binary.

## Constraints

- Reproducible CC0 derive (Pillow, deterministic — no randomness); no third-party source.
- 700×350 RGB JPEG, same filename (zero repoint).
- The committed binary IS the deliverable (regenerate + commit it alongside the script).

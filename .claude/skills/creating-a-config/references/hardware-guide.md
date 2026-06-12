<!-- Derived from CLAUDE.md sections: "Project Overview", "Hardware", "CRITICAL: Hardware Rendering Constraints", "Per-section `content_height`". Last synced: 2026-05-07. -->

# Hardware Guide: Smallsign vs Bigsign

## At-a-glance comparison

| Dimension | Small sign | Bigsign |
|-----------|------------|---------|
| Pi model | Raspberry Pi 4 Model B | Raspberry Pi 5 |
| Panel layout | 5× chained 32×16 Adafruit | 8× P3 32×64 in 2×4 serpentine |
| Logical canvas | 160×16 | 256×64 |
| `default_scale` | 1 | 4 |
| BDF fonts | ✓ | ✓ |
| Hires TTF/OTF fonts | (overflows vertically; user beware) | ✓ |
| Hires emoji (`:moon:`, `:instagram:`) | (falls back to lowres automatically) | ✓ |
| Hires sprite transitions (nyancat/pokeball) | (uses lowres) | ✓ |
| `content_height` ceiling | 16 | 16 (hard: `content_height × 4 ≤ 64`) |
| Refresh rate | ~20 fps | ~20 fps (tunable) |
| Realistic viewing distance | ≤ 10 ft | up to 50 ft |
| Brightness default | 60 | 60 |

## Choosing scale (bigsign only)

The bigsign at `default_scale = 4` means all widgets draw at a logical 16-row canvas, and the wrapper expands every logical pixel to a 4×4 block on the physical 64-row panel. This centers content vertically and fills the display.

- **`default_scale = 4`** (most common) — headline content (banners, weather, countdown). Logical 16-row content fills the panel vertically.
- **`scale = 2` per-section** — handle layouts with `two_row` widgets (e.g. "@MoonBunnyBakery" top + email bottom). 128 logical px is wide enough for typical handles; logical rows are 32 real px tall.
- **Never `scale = 4` for a `two_row` handle** — text wraps or gets cut. Use the default `scale = 4` for single-row content or scale down to 2.

## Viewing-distance heuristics

| Distance | Sign | Recommended font |
|----------|------|------------------|
| Close (≤6 ft) | small sign | BDF FONT_DEFAULT (6×12) |
| Close (≤6 ft) | bigsign | BDF FONT_DEFAULT (6×12) at scale=4, or hires Inter @ 16px |
| Medium (6–20 ft) | small sign | BDF FONT_DEFAULT |
| Medium (6–20 ft) | bigsign | hires Inter @ 18–22px |
| Far (20 ft+) | small sign | (not realistic; panel too small) |
| Far (20 ft+) | bigsign | hires Inter / Inter-Bold @ 24–32px |

## Refresh tuning (bigsign / Pi 5 only)

The bigsign at default settings achieves ~20 fps. For "info-dense" configs with many sections, these tunings help:

- **`pwm_bits = 8`** (down from default 11) — ~8× faster refresh rate at the cost of minor color fidelity loss
- **RIO backend** — the library default on Pi 5: faster refresh, higher CPU. Set `rp1_pio = 1` to force the lower-CPU PIO backend.
- **`gpio_slowdown = 3`** — paired with the default RIO backend. Raise to 4–5 if flicker persists (typical for chained panels with fast refresh).

Default bigsign config uses `gpio_slowdown = 3` + `pwm_bits = 8`.

## What does NOT work where

- **Hires emoji** (`:moon:` 32×32, `:instagram:` hi-res) on small sign — automatically falls back to 8×8 lowres. Don't promise them on small sign in your design.
- **Hires fonts** (TTF/OTF like Inter) on small sign — text paints to the physical 16 rows, no wrapping. Possible but overflows; user must pick `font_size ≤ 16` manually. Better to stick with BDF (6×12 default).
- **Hires sprite transitions** (nyancat, pokeball hi-res variants — and the `baseball.roll*` transitions from the `led-ticker-baseball` plugin if installed) on small sign — small sign gets lowres 4-frame sprite versions. No error; just silently degrades.
- **`content_height = 20`** on bigsign at scale=4 — clips top and bottom rows. Hard ceiling: `content_height × scale ≤ 64` (i.e., `content_height ≤ 16`).

All of these degrade silently. Configure carefully and test on hardware.

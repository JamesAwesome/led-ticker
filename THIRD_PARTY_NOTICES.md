# Third-party notices

led-ticker is MIT-licensed (see `LICENSE`). It also incorporates a small amount
of third-party material under its own license, listed here as required by that
license. (Sample media used only by example configs / docs demos is CC0 and
recorded separately in `config/assets/ATTRIBUTION.md`.)

## Noto Emoji — the `:fire:` hi-res sprite

The hi-res `:fire:` 🔥 emoji sprite (`_FIRE_HIRES_PIXELS` in
`src/led_ticker/pixel_emoji.py`) is **derived from** the Noto Emoji "fire"
glyph (U+1F525, `emoji_u1f525`): the 512×512 source PNG downsampled to 32×32
and alpha-thresholded into a pixel list (see `tools/gen_fire_hires.py`, which
reproduces the constant from the vendored source at
`tools/assets/noto_emoji_u1f525.png`).

- **Source:** Noto Emoji — https://github.com/googlefonts/noto-emoji
- **Copyright:** © Google LLC
- **License:** Apache License, Version 2.0 —
  https://www.apache.org/licenses/LICENSE-2.0

The low-res 8×8 `:fire:` sprite is project-original (hand-authored) and not
derived from Noto.

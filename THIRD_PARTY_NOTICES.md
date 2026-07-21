# Third-party notices

led-ticker is MIT-licensed (see `LICENSE`). It also incorporates a small amount
of third-party material under its own license, listed here as required by that
license. (Sample media used only by example configs / docs demos is CC0 and
recorded separately in `config/assets/ATTRIBUTION.md`.)

## Noto Emoji — hi-res sprites (`:fire:`, adopted curated icons) and the standard-emoji pack

The hi-res `:fire:` 🔥 sprite (`_FIRE_HIRES_PIXELS` in
`src/led_ticker/pixel_emoji.py`) and the standard-emoji pack
(`src/led_ticker/assets/emoji_pack.bin`, ~1,400 sprites) are **derived from**
Noto Emoji glyphs: 512×512 source PNGs downsampled to 32×32 and
alpha-thresholded into pixel lists (see `tools/gen_fire_hires.py` and
`tools/gen_emoji_pack.py`; the pack's contents are enumerated in
`tools/assets/emoji_manifest.txt`; `gen_fire_hires.py` reproduces the fire
constant from the vendored source at `tools/assets/noto_emoji_u1f525.png`).

- **Source:** Noto Emoji — https://github.com/googlefonts/noto-emoji
- **Copyright:** © Google LLC
- **License:** Apache License, Version 2.0 —
  https://www.apache.org/licenses/LICENSE-2.0

The low-res 8×8 `:fire:` sprite is project-original (hand-authored) and not
derived from Noto.

## DejaVu Sans — the hi-res glyph fallback font

The hi-res glyph resolution ladder (`fonts/hires_loader.py`) falls back to
DejaVu Sans for characters a config's chosen font lacks (arrows, math and
currency symbols, extended punctuation), rasterized at the same pixel size.
Vendored at `src/led_ticker/assets/DejaVuSans.ttf` (from the upstream
`dejavu-sans-ttf-2.37.zip` release asset).

- **Source:** DejaVu Fonts — https://dejavu-fonts.github.io/
- **License:** Bitstream Vera Fonts Copyright, as amended by the DejaVu
  project (permissive, attribution-only; renaming required for modified
  derivatives) — see `src/led_ticker/assets/DejaVuSans-LICENSE.txt`.

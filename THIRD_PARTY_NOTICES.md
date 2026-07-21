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

## Spleen — bundled pixel fonts for small hi-res sizes

Three sizes of the Spleen monospaced pixel-font family ship as hi-res fonts
(`spleen-6x12`, `spleen-8x16`, `spleen-16x32` — native 12, 16, and 32 px).
At their native pixel size (or an integer multiple) they rasterize to exact
1-bit output — crisp on LED panels at sizes where outline fonts blur (e.g.
24 px via `spleen-6x12` at 2×). Vendored at
`src/led_ticker/fonts/hires/spleen-*.otf`.

- **Source:** Spleen 2.2.0 — https://github.com/fcambus/spleen
- **License:** BSD 2-Clause (c) 2018-2026 Frederic Cambus — see
  `src/led_ticker/fonts/hires/SPLEEN-LICENSE.txt`.

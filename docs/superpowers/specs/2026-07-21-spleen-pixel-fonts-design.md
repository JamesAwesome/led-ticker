# Spleen pixel fonts — crisp hi-res text at small sizes

**Date:** 2026-07-21
**Status:** approved (brainstorm with James)

## Problem

Inter (the only bundled hi-res family) smooshes at small sizes: its
antialiased outlines are hard-thresholded to 1-bit, and below ~14 px the
counters (`e a o`) close and adjacent strokes land in the same LED. The
concrete incident surface is the baseball statcast/attendance layouts, which
render Inter at **9–13 px** (stat lines at 9/11, labels at 13) — sizes where
no outline font binarizes cleanly. James chose the crisp pixel-font look over
a small-optimized outline font (B612/Atkinson would still merge at 9–11 px).

## Decision — bundle Spleen (verified empirically)

[Spleen](https://github.com/fcambus/spleen) 2.2.0, BSD-2-Clause (Frederic
Cambus), a monospaced bitmap family shipped upstream as OTF conversions.
Rendered through OUR actual loader (PIL truetype + threshold), a Spleen OTF at
its native pixel size produces **strictly binary output** — every pixel 0 or
255, exact integer advances — and stays binary at integer multiples:

| `font_size` | result (spleen-6x12, measured) |
|---|---|
| 12 (native) | BINARY — advance(M) = 6.0 exactly |
| 24 (2×) | BINARY — advance(M) = 12.0 |
| 11 (off-grid) | antialiased mush (the failure the guardrail catches) |

Monospace is a feature for the target content (tabular stat columns align).
No bold weight exists; the target call sites are predominantly
`bold=False`.

## What ships

Vendor three OTFs into `src/led_ticker/fonts/hires/` (from the upstream
2.2.0 release tarball):

- `spleen-6x12.otf` — native **12 px** (the 9–13 px replacement tier)
- `spleen-8x16.otf` — native **16 px**
- `spleen-16x32.otf` — native **32 px**

**`spleen-12x24` dropped (upstream defect, 2026-07-21):** the 2.2.0 OTF for
that size has `unitsPerEm=1023` (vs 1024 on the others) and its glyph
outlines sit off the pixel grid, so it antialiases at its own native 24 px
instead of rendering 1-bit (verified through our loader). A crisp 24 px is
reached instead via `spleen-6x12` at **2×** (24 px renders strictly binary —
verified), so no native-24 asset is needed. Also excluded: `spleen-32x64`
(64 px on a 64 px panel — YAGNI) and `spleen-5x8` (upstream ships no OTF).
License: vendor Spleen's `LICENSE` alongside (one file for the family) + a
`THIRD_PARTY_NOTICES.md` section — same posture as DejaVu and Noto.

## Architecture

**Loader — no new machinery.** The OTFs are ordinary hi-res fonts resolved by
the existing path: `resolve_font("spleen-6x12", 12)`. Font names follow the
file stem (lowercase `spleen-WxH`), consistent with how bundled hires fonts
are discovered today.

**Pixel-native registry.** `hires_loader` gains a small module-level map:

```python
_PIXEL_NATIVE: dict[str, int] = {
    "spleen-6x12": 12,
    "spleen-8x16": 16,
    "spleen-16x32": 32,
}
```

Valid crisp sizes for a pixel-native font are `native × k` (k ≥ 1). The
registry is the single source of truth consumed by the validate rule and the
docs. (Deliberately name-keyed and core-owned; a plugin-contributed pixel
font can be added to it later via the plugin API if demand appears — not in
this spec.)

**Off-grid guardrail — validate rule 69.** A config widget using a
pixel-native font at a `font_size` that is not an integer multiple of the
native size gets a warning naming the two nearest valid sizes:

> `section[i].widget[j]: spleen-6x12 at 13px renders blurry (pixel font off
> its native grid) — use 12 or 24`

Warning, not error; and NO silent snapping at runtime (a snap would change
layout underneath an existing config). Runtime renders exactly what was
asked, as today. The rule lives beside rule 68 in `validate.py`, keyed off
`_PIXEL_NATIVE`.

**Threshold interplay.** At native sizes every glyph pixel is 0 or 255, so
`font_threshold` is a no-op for Spleen (any value 1–255 yields identical
output). Documented; no code change.

**Glyph-ladder interplay.** Unchanged. Spleen covers Basic Latin, Latin-1,
Latin Extended-A, box-drawing, block elements, Braille. A char outside that
falls through the normal ladder (DejaVu rung 2 → ASCII rung 3 → `?`); a
DejaVu glyph binarized at 12 px will look mushy next to crisp Spleen, which
is honest behavior — rule 68 already surfaces coverage degradation, and the
notdef fingerprint handles Spleen's missing-glyph rendering like any other
font.

## Tests

- **Binary-at-native (the load-bearing pin):** rasterize a text sample in
  `spleen-6x12` at 12 via the real loader; assert the pre-threshold bitmap
  contains no intermediate gray values and `advance("M") == 6`. Repeat at 24
  (2×). This pins the "pixel-perfect through PIL" property the whole feature
  rests on — if a Pillow upgrade breaks grid alignment, this fails loudly.
  (Exact-advance assertions are safe here — integer grid by construction —
  unlike the banned freetype-advance pins for outline fonts.)
- **Off-grid renders non-binary:** size 11 produces intermediate grays
  (guards the rule-69 premise).
- **Rule 69:** warns at 13 (message names 12 and 24); silent at 12 and 24;
  silent for non-pixel fonts (Inter at any size); default-BDF widgets
  unaffected.
- **Resolution:** all four names resolve; `font_line_height`/baseline math
  sane at native sizes.

## Visual gate (James, before PR)

Bigsign render GIF: the same stat-style line (`EV 104.6  LA 28°  DIST 412FT`)
in Inter-Regular @ ~11 px vs `spleen-6x12` @ 12 px side by side, plus one
Spleen line at 24 px. James eyeballs crispness before the PR opens.

## Docs

`concepts/fonts.mdx`: a "Pixel fonts" subsection — what ships, the
native-size rule (native × integer only; validate warns off-grid), threshold
no-op note, when to prefer Spleen over Inter (below ~14 px, tabular stats),
monospace caveat. Decision-tree row for "<14 px on the bigsign →
spleen-6x12 @ 12". Config-skill fact-pack touch-up if the fonts fact-pack
lists bundled hires fonts.

## Non-goals

- No baseball-plugin adoption in this spec (follow-up in the plugins repo:
  its 9/11 px Inter calls migrate to `spleen-6x12` @ 12).
- No BDF-as-hires adapter (considered; separate idea, not needed once Spleen
  ships).
- No bold synthesis, no `spleen-5x8`/`32x64`, no runtime size-snapping, no
  plugin API surface for `_PIXEL_NATIVE`.

## Release shape

Core minor (new bundled assets + validate rule). No plugin changes required.

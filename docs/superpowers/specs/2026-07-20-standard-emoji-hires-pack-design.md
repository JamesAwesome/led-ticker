# Standard emoji in hires — the emoji pack

**Date:** 2026-07-20
**Status:** approved (brainstorm with James)
**Relation:** first of a two-spec sequence. The glyph/tofu-system revisit
(font coverage checks, typographic→ASCII fallbacks, validate flagging) is a
SEPARATE spec that follows this one — emoji-first was chosen because this
shrinks the tofu surface (an emoji rendered as a sprite never reaches the
font) and the Noto pipeline is proven (the `:fire:` work, core #424).

## Goal

Any standard emoji typed in widget text — as real unicode (🚀) or as a
`:slug:` — renders as a 32×32 sprite on hires (scaled) displays. Today only
47 unicode emoji map to ~21 curated base slugs; everything else silently
strips.

## Decisions (from the brainstorm)

1. **Scope: broad, no modifiers (~1,400 sprites).** Every single-codepoint
   standard emoji from Noto Emoji. Skin-tone variants fold to base; ZWJ
   sequences fold to their FIRST base codepoint (👨‍👩‍👧 → 👨); regional-indicator
   letter flags excluded (fold rules below). NOT the full ~3,600 set with
   distinct tone/ZWJ sprites — tone fidelity is illegible at 32px.
2. **All pack emoji get `:slug:` names** (CLDR short names, sanitized).
   `emoji_slugs()` grows to ~1,400+.
3. **flair.stickers goes wild but capped:** random mode samples the full
   drawable set, limited to ≤ 12 DISTINCT slugs per firing (companion flair
   PR — see "Stickers companion" below).
4. **Source: Noto Emoji** (© Google, Apache 2.0) — same source, recipe, and
   attribution posture as `:fire:` (#424). `THIRD_PARTY_NOTICES.md` extends
   from "the fire glyph" to "the emoji pack".

## Architecture

### Asset pipeline (generation-time; no runtime network, ever)

- **`tools/gen_emoji_pack.py`** — the packer/reproducer (the scaled-up
  `tools/gen_fire_hires.py`):
  1. Reads a **vendored codepoint manifest** (`tools/assets/emoji_manifest.txt`:
     one `codepoint<TAB>slug` line per emoji, itself generated once from CLDR
     annotation data + the Noto file listing, then committed — the manifest is
     the reviewable source of truth for WHAT is in the pack and WHAT it's
     named).
  2. For each entry, fetches the Noto per-glyph PNG
     (`png/512/emoji_uXXXX.png` from `github.com/googlefonts/noto-emoji`) into
     a local cache dir (gitignored; only the manifest + pack are committed).
  3. Applies the proven fire recipe: Lanczos downsample to 32×32, alpha
     threshold ≥ 110, RGB kept as-is.
  4. Packs all sprites into **one committed binary asset**:
     `src/led_ticker/assets/emoji_pack.bin`.
- **Pack format** (versioned, magic + format-version header):
  - Header: magic `LTEP`, u16 version, u32 entry count.
  - Index: per entry — slug (len-prefixed ascii), u32 codepoint (every
    entry is a single-codepoint emoji; folds resolve to a base codepoint
    BEFORE lookup, so the index never stores sequences), u32 payload
    offset, u32 payload length.
  - Payloads: per-sprite zlib-compressed run of `(x, y, r, g, b)` u8 quints
    (the exact `HiResEmoji.pixels` tuple content; x/y < 32 fit u8).
  - Expected size: ~1,400 sprites × ~1–2 KB ≈ **2–3 MB** committed to the
    repo and shipped in the wheel. Signs stay offline-capable.
- The packer is **provenance tooling** (run on a dev machine; committed pack
  is what CI/builds consume — hermetic, same posture as the fire PNG).
  Byte-for-byte reproducibility from manifest + pinned Noto ref is a test
  (subset check in CI is enough; full re-fetch is a manual tool run).

### Runtime: lazy two-tier lookup

- **Curated registries always win.** `EMOJI_REGISTRY` / `HIRES_REGISTRY` /
  `_UNICODE_EMOJI_MAP` are consulted first, unchanged. A pack entry whose
  slug or codepoint collides with a curated one is skipped AT PACK TIME
  (packer refuses to emit it; e.g. `fire`, `taco`, `heart`).
- **New module `src/led_ticker/emoji_pack.py`:**
  - `load_index()` — parses header+index only (~50–100 KB of work), eagerly
    at first emoji lookup miss (NOT at import). Exposes
    `pack_slugs() -> tuple[str, ...]`, `slug_for_codepoint(cp) -> str | None`.
  - `get_sprite(slug) -> HiResEmoji | None` — decodes ONE payload on first
    use (zlib + tuple build), caches the `HiResEmoji` in a module dict.
    Decoded cache grows with emoji actually displayed, not pack size — Pi
    memory stays proportional to usage.
  - Corrupt/missing pack: log once, behave as "pack absent" (curated set
    still works; a broken asset must never crash the app).
- **Wiring into `pixel_emoji.py`** (the only consumer-visible seam):
  - Slug resolution (draw + measure + `has_renderable_emoji`): on curated
    miss, try `emoji_pack.get_sprite(slug)`. Hires paths only.
  - Unicode mapping (`_map_uemoji_to_slug`): on curated-map miss, fold the
    char run (rules below) and try `slug_for_codepoint`.
  - `emoji_slugs()`: union grows to include `pack_slugs()` (index-only — no
    sprite decode to enumerate).
- **Fold rules** (extending `_emoji_key`, which already strips VS + tone):
  - Skin-tone modifier (U+1F3FB–1F3FF): strip → base (existing behavior).
  - ZWJ sequence: take the FIRST base codepoint, look that up; if absent →
    strip (today's behavior for unmapped).
  - Regional-indicator pairs (letter flags): always strip (excluded from
    pack).
  - Keycap/other multi-cp sequences: first-base rule, else strip.

### Slug generation (in the manifest, reviewed once)

- CLDR short names, sanitized to the existing slug regex
  (`[a-z_][a-z0-9_.]*`): lowercase, spaces/punctuation → `_`, ascii-folded
  (`piñata` → `pinata`).
- Deterministic collision handling INSIDE the pack: append `_2` etc. —
  expected to be rare; the manifest makes any such case visible in review.
- Curated-name collisions: pack entry dropped (curated wins), asserted by a
  packer check + a runtime test.

### Scale-1 (smallsign) policy — existing semantics, no new class

Pack emoji are **hires-only** (the established "in `HIRES_REGISTRY`-space
but not `EMOJI_REGISTRY`" class; CLAUDE.md already documents that class as
having no low-res fallback):

- Real unicode on a scale-1 canvas: **strips** (today's behavior, unchanged).
- A pack `:slug:` in config on a scale-1 display: renders nothing at draw;
  **`led-ticker validate` gains a warning** — "`:rocket:` is a hires-only
  emoji and this display is scale 1 — it will not render". (Validate knows
  `default_scale` and the widget text fields already.)

### Stickers companion (flair PR, after the core release)

`flair.stickers` random mode currently picks each sticker's slug
independently from the full drawable set. With ~1,400 slugs that stays the
"gone wild" assortment James wants, but each FIRING caps variety:

- Sample ≤ `_RANDOM_VARIETY_CAP = 12` distinct slugs per firing (re-sampled
  every firing — chaos across firings, coherence within one).
- Constant, not a knob (YAGNI; promote to a knob on request).
- Explicit `emoji = [...]` lists are untouched.
- Sequencing: flair PR lands AFTER the core release that ships the pack
  (its tests need `emoji_slugs()` to include pack slugs to be meaningful,
  but the cap logic itself is set-size-agnostic so it can land any time —
  the PR simply pins no new core floor).

### Docs

- `assets/emoji.mdx`: curated table stays as-is; new **"Standard emoji"**
  section — "any standard emoji works as unicode or by `:cldr_short_name:`
  on hires displays" + fold/scale-1 caveats.
- Browsable list: **generated category contact-sheets** (one PNG grid per
  Unicode category, built by extending `tools/render_emoji_previews.py`) —
  NOT a 1,400-row fact-pack table. The fact-pack keeps the curated table
  only, plus a pointer.
- `THIRD_PARTY_NOTICES.md`: fire entry generalizes to the pack (same Noto
  clause, now covering `emoji_pack.bin` + manifest).

### Tests & gates

- Pack round-trip: pack a fixture subset → decode → pixel-identical.
- Header/version: wrong magic/version → clean "pack absent" degradation.
- Fold rules: tone → base; ZWJ → first-base; flags → strip; unmapped → strip.
- Collision policy: packer refuses curated collisions (unit on the packer);
  runtime curated-wins asserted for a known dupe.
- Slug validity: every manifest slug matches the slug regex; no dupes.
- Laziness asserted: importing `pixel_emoji` + drawing a CURATED emoji never
  touches the pack file; drawing one pack emoji decodes exactly one payload.
- `emoji_slugs()` includes pack slugs (size tripwire: > 1,000).
- Scale-1 validate warning: new rule test.
- Perf gates (spec-mandated, lightning-convention): index load < 50 ms on
  dev (one-time), single-sprite decode ms-class, drawing a pack emoji in a
  message renders at the same frame cost as a curated hires emoji after
  first decode.
- Visual gate: render a bigsign GIF with a spread of pack emoji
  (🚀😂🦞🍕⚽💀 etc.) inline in message/two_row text for James before merge.

## Non-goals

- No skin-tone / ZWJ sprite fidelity (folds only).
- No letter flags.
- No lowres (8×8) pack — hand-drawn curated lowres remains the only lowres.
- No runtime network access of any kind.
- No change to the plugin emoji API surface (`api.emoji` etc.) — plugins
  keep registering namespaced emoji exactly as today.
- The glyph/tofu system (font coverage, ASCII fallbacks, validate flagging
  of unrenderable TEXT chars) — next spec, not this one.

## Rough sizing

Core: packer tool + manifest (~1,400 lines) + `emoji_pack.py` (~150 lines) +
`pixel_emoji.py` wiring (3 seams) + validate rule + tests + docs + the
committed 2–3 MB asset. Flair: ~10-line cap change + tests. Release shape:
core minor (new feature), then flair patch.

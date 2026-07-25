# Inline image animation (Phase 2) — animated GIFs as live inline emoji

**Date:** 2026-07-25
**Status:** approved (brainstorm with James; architecture choice: registry
frame-swapping)
**Relation:** Phase 2 of the inline image source
(`2026-07-25-inline-image-source-design.md`, shipped static in core
v4.28.0). That spec's §9 recorded this phase's hard requirements; this
design satisfies their INTENT while deleting the two hardest ones (the
~10-site polymorphic migration and the lowres frame seam) via a different
architecture.

## Problem

Phase 1 renders an animated GIF's first frame. James's original ask was an
animated inline emoji — the party parrot should party, at its native GIF
timing, while the text around it scrolls or holds, on both sign
geometries.

## Decisions carried from Phase 1

- **Native GIF timing** — frames advance per the GIF's own durations.
- **Shared wall-clock epoch** — every instance of the same slug, in any
  widget, is in phase; sprites keep animating through transitions
  (wall-clock is deliberately decoupled from the `pause_frame`
  frame-counter machinery).
- **Smallsign animates too** (8×8 forms per frame) and is in the visual
  gate.

## Architecture — registry frame-swapping (Approach A)

The registries continue to hold **plain static sprites, always**
(`PixelData` lowres, `HiResEmoji` hires). No new registry value type, no
consumption-site changes, no lowres seam. Animation is a producer-side
concern:

### 1. Decode: layout-invariant frame sets

`load_image_sprites` grows an animated path: for a multi-frame file it
decodes EVERY frame (up to the caps, §4) and bakes per-frame lowres+hires
sprites **normalized to identical layout geometry** — the hires
`physical_width` is computed once from the UNION of all frames' lit
bboxes and applied to every frame; all frames share `physical_size=32`.
Any frame therefore measures exactly like any other, so the pure
`measure_width` and a draw at any instant agree BY CONSTRUCTION (the F6
parity requirement) — pinned by a parity tripwire test. Durations come
from the GIF (`frame.info["duration"]`, min-clamped to 20 ms; a missing
duration defaults to 100 ms, Pillow convention).

The decode returns the existing `(lowres, hires)` pair for frame 0 PLUS an
optional animation record: `frames: tuple[(lowres_i, hires_i), ...]`,
`durations_ms`, `total_ms`.

### 2. Registration: an animation table beside the registries

`pixel_emoji` gains a private per-slug table
`_IMAGE_ANIMATIONS: dict[slug, _ImageAnimation]` (frames, durations,
total, last-committed frame index), staged/committed/aborted/suspended by
the SAME two-phase machinery as Phase 1 (`stage_image_emoji` grows an
optional `animation=` argument; `commit/abort/suspend_image_emoji` carry
the table with the slug set — one lifecycle, no second protocol). The
registries hold the CURRENT frame's static sprites; the table is the
source the ticker swaps from.

### 3. The tick: one call at the swap chokepoint

`pixel_emoji.tick_image_animations() -> None`, called once at the top of
`LedFrame.swap()` (frame.py) inside a `try/except` that logs at most once
(the overlay-invariant posture: nothing in swap may raise). Semantics:

- `elapsed = (monotonic() - _ANIM_EPOCH) % total_ms` per slug → frame
  index via the duration walk (the `GifPlayer._pick_frame_for_elapsed`
  algorithm).
- ONLY when the index differs from the last-committed one: write that
  frame's lowres into `EMOJI_REGISTRY[slug]` and hires into
  `HIRES_REGISTRY[slug]`. Dict writes on the render task (single-task
  asyncio) — no races, O(animated slugs) per swap, zero work when nothing
  changed or the table is empty.

Because EVERY pixel that reaches the panel passes through `swap()` (the
documented "single centralized swap point" — engine ticks, play-widgets,
transitions, idle keepalive), the frame table advances everywhere the
panel is alive, at least at the idle-keepalive ~1 Hz and at
`ENGINE_TICK_MS` (50 ms) during holds/scrolls. This adds a NON-paint
responsibility to `swap()` — documented as a new sentence in the
CLAUDE.md overlay/idle invariant block, alongside `record_swap` liveness
(which already set the precedent of swap carrying bookkeeping).

### 4. Fast-path exclusion (the freeze class)

The engine's per-tick redraw loops (constraint #12) make TickerMessage /
TwoRowMessage animate with zero changes — they redraw every 50 ms and pick
up the swapped registry values. The ONLY paint-once-and-sleep paths are
the image-overlay fast paths: `_play_with_text` and
`_play_with_two_row_text` gate on `font_color.frame_invariant` /
`border.frame_invariant` / `_is_static()`. New predicate
`pixel_emoji.has_animated_emoji(text) -> bool` (True when any `:slug:` in
the text is in `_IMAGE_ANIMATIONS`); both gates add
`AND NOT has_animated_emoji(...)` so an animated inline sprite forces the
slow (per-tick) path. Tripwire mirroring
`test_gif_static_text_does_not_freeze_animation`: a still image widget
with an animated inline slug renders DIFFERENT pixels across ticks.

Note: `has_animated_emoji` consults the animation table, which is
config-scoped and committed before widgets are constructed (boot ordering
from Phase 1) — but the image-overlay gates evaluate per play() call, not
at construction, so reload's widget-cache flush (Phase 1) plus per-call
evaluation keep it correct across config changes.

### 5. Lifecycle interplay (all inherited, one addition each)

- **Boot:** stage carries the animation record; the guarded post-loop
  commit lands table + frame-0 sprites together.
- **Reload:** the same commit/abort atomicity covers the table (a failed
  reload keeps the old table AND old sprites; success swaps both).
- **Validate:** `suspend_image_emoji()` also pops the animation table into
  its snapshot and the finally-restore reinstates it — the
  LOAD-BEARING SERIALIZATION INVARIANT (validate inline on the display
  task, never concurrent with a draw) already pinned in Phase 1 covers the
  table's absence during the window. Rule 70's first-frame WARNING is
  REMOVED (animation is now real); its frame caps (§4) take its place.
- **Stickers/capture:** registry values are always static, so
  `capture_sprite` keeps working untouched — it captures whichever frame
  is current at plan time (documented; strictly better than a frozen
  frame 0 and zero code).

### 6. Caps (§9's frames×area budget, concretized)

- frames > 24 → validate WARNING (memory note).
- frames > 60 → validate ERROR + build-time skip-with-log (never darks).
  Worst case at the cap: 60 frames × 32×128 all-opaque ≈ 20 MB of pixel
  tuples for one sprite — bounded on a Pi; the >512×512 source-area
  warning from Phase 1 still applies.
- Total animated-slug budget: no additional cap in this phase (source
  count is small in practice); revisit if real configs prove otherwise.

## Testing

- Frame-pick math: table-driven elapsed→index (pure function).
- Layout invariance: a synthetic GIF whose frames have different lit
  bboxes → all frames' hires share identical `physical_width`; measure ==
  draw advance at several instants (the parity tripwire).
- Tick semantics: monkeypatched clock — index change swaps both registry
  values; no-change ticks write nothing (object identity stable);
  empty-table tick is a no-op.
- Swap integration: a `LedFrame.swap()` call advances a due animation; a
  raising tick is swallowed + logged once (never blocks the hardware
  swap).
- Fast-path exclusion tripwire (still image + animated slug ≠ frozen).
- Lifecycle: reload atomicity + suspend/restore now carry the table
  (extend the Phase-1 tests); rule 70 cap tests; first-frame warning
  removed.
- **Visual gate (James): bigsign AND smallsign** — the animated GIF
  visibly cycling in held and scrolling text on both geometries (two
  time-separated contact-sheet rows proving different frames), static PNG
  unaffected.

## Non-goals

- No `AnimatedSprite` registry type (that was §9's assumption; Approach A
  supersedes it). No per-widget phase offsets or play-once modes (loop
  forever, shared epoch). No animated PLUGIN emoji API (`api.emoji` is
  untouched; the table is config-image-only this phase). No webp/apng
  promises beyond what Pillow's `n_frames` already gives the decode path.
  No change to `docs` beyond updating the emoji page's "first frame"
  sentence to describe animation + caps.

## Release shape

Core minor. No plugin changes.

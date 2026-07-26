# Inline image animation (Phase 2) — animated GIFs as live inline emoji

**Date:** 2026-07-25 (rev 2 after antagonistic ENG review; rev 1 in git
history)
**Status:** approved (brainstorm with James; architecture: registry
frame-swapping; rev-2 findings adjudicated with James — animation is
HIRES-ONLY, smallsign stays static)
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
- **Animation is HIRES-ONLY (rev 2).** The lowres path computes a
  sprite's advance INTRINSICALLY from its pixels (`_emoji_width` =
  max lit x + 1) — there is no width field to normalize, so per-frame
  lowres advances would wobble and jitter the surrounding text (proven
  against the real decode in review). Rather than build a new per-slug
  lowres-advance seam into the ~4 lowres measure/draw sites (exactly the
  consumption-site surgery this architecture exists to avoid), smallsign
  keeps Phase 1's static frame 0; a validate note says so. Smallsign
  animation is a possible Phase 3 behind that seam if ever wanted.

## Architecture — registry frame-swapping (Approach A)

The registries continue to hold **plain static sprites, always**
(`PixelData` lowres, `HiResEmoji` hires). No new registry value type, no
consumption-site changes, no lowres seam. Animation is a producer-side
concern:

### 1. Decode: layout-invariant frame sets

`load_image_sprites` grows an animated path: for a multi-frame file it
decodes EVERY frame (up to the caps, §4) and bakes per-frame HIRES
sprites **normalized to identical layout geometry**. The exact formula
(rev 2, from review): `physical_width = max over frames of
(max_x_f + 1)` — the union EXTENT, not the max bbox width — applied
unchanged to every frame, and pixels are NOT origin-shifted (image
sprites bypass `_auto_trim_hires`; a frame's content keeps its natural
inset). A tripwire asserts no frame's rightmost lit pixel exceeds the
applied `physical_width` (getting extent vs width wrong silently clips
wide frames). All frames share `physical_size=32`. Any frame therefore
measures exactly like any other on the hires path — the F6 parity
requirement — pinned by a parity test. The LOWRES form is baked from
frame 0 only (smallsign is static, see Decisions). Durations come from
the GIF (`frame.info["duration"]`, min-clamped to 20 ms; a missing
duration defaults to 100 ms, Pillow convention; the clamp slightly
stretches pathological <20 ms GIFs — documented, accepted).

The decode returns the existing `(lowres, hires)` pair for frame 0 PLUS an
optional animation record: `hires_frames: tuple[HiResEmoji, ...]`,
`durations_ms`, `total_ms`, and a precomputed CUMULATIVE duration array
for O(log frames) frame lookup.

### 2. Registration: an animation table beside the registries

`pixel_emoji` gains a private per-slug table
`_IMAGE_ANIMATIONS: dict[slug, _ImageAnimation]` (hires frames,
cumulative durations, total, last-committed frame index),
staged/committed/aborted/suspended by the SAME two-phase machinery as
Phase 1 (`stage_image_emoji` grows an optional `animation=` argument;
`commit/abort/suspend_image_emoji` carry the table with the slug set —
one lifecycle, no second protocol). **Commit REBUILDS the table from the
pending set exactly** (rev 2): it first clears every `_CONFIG_IMAGE_SLUGS`
entry from the table, then inserts only the pending animation records —
so an animated→static reload (same id, GIF swapped for a PNG) cannot
leave a dead table entry re-animating stale frames over the new static
sprite (tripwire test). The registries hold the CURRENT frame's static
sprites; the table is the source the ticker swaps from.

### 3. The tick: one call at the swap chokepoint

`pixel_emoji.tick_image_animations() -> None`, called once at the top of
`LedFrame.swap()` (frame.py) inside a `try/except` that logs at most once
(the overlay-invariant posture: nothing in swap may raise). Semantics:

- `now_ms = monotonic() * 1000` hoisted ONCE per tick; per slug,
  `elapsed = (now_ms - _ANIM_EPOCH_MS) % total_ms` → frame index via
  `bisect` on the precomputed cumulative-duration array — O(log frames)
  per slug, so the tick is O(slugs · log frames) per swap (rev 2: rev 1
  claimed O(slugs) with a linear walk, which was wrong twice — corrected
  and improved). The index lookup runs on every swap for a non-empty
  table (that IS the work of discovering nothing changed); only the dict
  write is conditional. Empty table = one len check.
- ONLY when the index differs from the last-committed one: write that
  frame's HiResEmoji into `HIRES_REGISTRY[slug]` (hires-only —
  `EMOJI_REGISTRY` keeps frame 0's lowres permanently). Dict writes on
  the render task (single-task asyncio) — no races.

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
  RESCOPED: gone for scaled sections (animation is real there), retained
  for scale-1 sections ("animates on scaled displays; smallsign shows the
  first frame"). The frame caps (§6) are enforced at validate AND in
  `load_image_sprites` itself (rev 2) — validate alone cannot stop the
  boot/reload build path from decoding an over-cap file; on an over-cap
  file the build path decodes NOTHING beyond the probe, skips the source
  with a log (never darks; its token renders as literal text, matching
  the Phase-1 bad-file posture). Note: enforcing caps means validate
  decodes every frame of every animated source — a transient
  ~24 MB-per-max-sprite spike inside the suspend window; accepted at the
  §6 caps.
- **Stickers/capture:** registry values are always static, so
  `capture_sprite` keeps working untouched — it captures whichever frame
  is current at plan time (documented; strictly better than a frozen
  frame 0 and zero code).

### 6. Caps (§9's frames×area budget, concretized)

- frames > 24 → validate WARNING (memory note).
- frames > 60 → validate ERROR **and** `load_image_sprites` build-time
  refusal (skip-with-log, never darks) — both enforcement points (rev 2).
  Worst case at the cap: measured ~88 B per hires pixel tuple → an
  all-opaque 32×128 frame ≈ 384 KB → 60 frames ≈ **~23 MB per slug**
  (rev 2: rev 1 said 20 — corrected from a real measurement); the
  >512×512 source-area warning from Phase 1 still applies.
- Aggregate: validate WARNS when the summed decoded-frame estimate across
  all animated sources exceeds ~64 MB (three max-cap slugs) — a nudge,
  not a hard cap; revisit if real configs prove otherwise.
- Known cache interaction (documented, accepted): `_downsample_hires` is
  an unbounded `functools.cache` keyed on the HiResEmoji object — an
  animated slug rendered through a downscaling lens caches one entry per
  frame, and reload replaces frame objects, so repeated reloads of
  lens-downscaled animated slugs grow that cache. Pre-existing class
  (static image slugs already leak one entry per reload); animation
  multiplies it by frame count. Mitigation deferred: bound or key that
  cache in a follow-up if lens+animated usage materializes.

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
- Union-extent tripwire: no frame's rightmost lit pixel exceeds the
  applied `physical_width` (synthetic GIF with right-shifted content).
- Animated→static reload tripwire: table entry purged; the new static
  sprite never gets stale frames swapped over it.
- Build-path cap: an over-cap GIF is refused by `load_image_sprites`
  (skip posture), independent of validate.
- **Visual gate (James): bigsign animated, smallsign static-confirmed** —
  bigsign shows the GIF visibly cycling in held and scrolling text (two
  time-separated contact-sheet rows proving different frames); smallsign
  shows the stable frame-0 8×8 with NO jitter in surrounding text; static
  PNG unaffected on both.

## Non-goals

- No smallsign/lowres animation (rev 2 — needs a per-slug lowres-advance
  seam in the lowres measure/draw sites; possible Phase 3). No
  `AnimatedSprite` registry type (that was §9's assumption; Approach A
  supersedes it). No per-widget phase offsets or play-once modes (loop
  forever, shared epoch). No animated PLUGIN emoji API (`api.emoji` is
  untouched; the table is config-image-only this phase). No webp/apng
  promises beyond what Pillow's `n_frames` already gives the decode path.
  No change to `docs` beyond updating the emoji page's "first frame"
  sentence to describe animation + caps.

## Release shape

Core minor. No plugin changes.

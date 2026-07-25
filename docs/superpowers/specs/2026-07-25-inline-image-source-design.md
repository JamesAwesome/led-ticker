# Inline image source — custom emoji from config-declared images

**Date:** 2026-07-25 (rev 2 after antagonistic ENG + PM review; rev 1 is in
git history)
**Status:** approved (brainstorm with James; hostile-review findings
adjudicated with James — static-first phasing, corrected lifecycle)

## Problem

There is no way to use your own image inline in text the way emoji render
inline. The emoji registries are fixed at build time (curated + pack) plus
plugin code (`api.emoji`); a user with a small logo or mascot image cannot
declare it in config and embed it mid-sentence. James's ask: declare an
image through a `[[source]]` and embed it wherever a `:token:` goes — a
custom emoji, config-driven.

## Decisions

- **Local files only** — files under the config dir (`config/assets/`,
  already Docker-mounted + gitignored). No URLs.
- **`[[source]]` declaration surface** (James's pick), implemented as a
  CORE source type (joining `clock`/`date`/`static` in
  `app/factories._SOURCE_TYPES`) — not a plugin. The PM review contested
  discoverability; adjudicated: keep the surface, fix findability through
  docs (see §7).
- **Auto-downscale at scale 1** — every image registers BOTH a 32-px-tall
  hires form and an 8×8 lowres form, so the three-place "renders inline"
  parse gate passes unchanged. Validate warns that machine-downscaled 8×8
  is approximate (see §6).
- **PHASED (rev 2, from review):** Phase 1 ships STATIC inline images —
  PNG, or GIF rendered as its first frame. Phase 2 (separately designed,
  gated on demand) adds native-timing animation. Rationale: the animated
  variant is a polymorphic sprite type touching ~10 resolution sites
  including a lowres path with no frame seam, and carries a measure/draw
  parity hazard — ~70% of the risk for the weaker half of the demand
  (the storefront-logo value case is static). Phase 2's requirements are
  recorded in §9 so the findings aren't lost.

## Config surface

```toml
[[source]]
type = "image"
id = "cart.logo"
path = "assets/cart-logo.png"   # relative to the config dir (gif-widget convention)

[[playlist.section.widget]]
type = "message"
text = "HALAL CART :cart.logo: OPEN LATE"
```

`id` is the token name — bare `:<id>:`, same namespace as `:clock.now:` /
`:wx.cart:`. Docs and the error messages steer users toward DOTTED ids
(`cart.logo`, `me.parrot`): the ~1,400 pack slugs own most bare English
words (`fire`, `taco`, `star`), and a dotted id sidesteps the whole
collision class (matching the plugin-emoji `namespace.name` convention).

## Architecture

### 1. `ImageSource` — a declaration-only core source

A new `DataSource` subclass in `sources.py`, registered as `"image"` in
`app/factories._SOURCE_TYPES`. No polling, no monitor-roster entry
(StaticSource posture). At build it: resolves `path` against the config
dir; decodes (Pillow; GIF via `widgets/_gif_decode.decode_gif`, taking
frame 0 in Phase 1); builds the two sprite forms (hires: 32 px tall,
width proportional capped at 128 px; RGBA alpha ≥ 110 keeps a pixel — the
proven Noto recipe; lowres: 8×8 resize); and hands the prepared sprites to
the registration commit (§2 — the source does NOT mutate global registries
itself).

Once the slug is registered, `is_emoji_slug(id)` is true, so
`TokenizedField` EXCLUDES it from `_candidate_ids` (sources.py:242-245) —
the emoji parser owns the token outright; token resolution never sees it.
**Load-bearing ordering invariant:** image registration must complete
before any `TokenizedField`/widget construction reads the registries. True
at boot (sources build at run.py:980, widgets after); `led-ticker
validate` must register images (via the same decode path) before its
token/widget checks so preflight sees the same world.

### 2. Registration lifecycle — two-phase commit, atomic with the data registry

(Rev 2: redesigned. Rev 1's "register during build, clear at reload" tears
the atomic reload — reload.py builds a TEMP DataRegistry and commits it
via `set_data_registry` only after the whole loop succeeds; a global
emoji-registry mutation mid-loop would partially apply while the data
registry rolls back.)

`pixel_emoji` gains:

- `stage_image_emoji(slug, lowres, hires) -> None` — accumulates into a
  PENDING dict (no global mutation).
- `commit_image_emoji() -> None` — swaps the pending set in: removes all
  previously-committed image slugs from `EMOJI_REGISTRY`/`HIRES_REGISTRY`
  (tracked in `_CONFIG_IMAGE_SLUGS`), inserts the pending set, updates the
  tracking set, clears pending.
- `abort_image_emoji() -> None` — drops the pending set untouched.

Boot and reload both: build sources (staging as they go) → on overall
success, call `commit_image_emoji()` at the SAME point `set_data_registry`
commits → on failure, `abort_image_emoji()` (reload keeps the old
sources AND the old emoji set — never torn). Curated-always-wins is
preserved: commit refuses (skips + logs) any slug already present from a
non-image origin — but in practice collisions never get this far
(validate + build-time check, §6).

**Widget-cache invalidation (rev 2, from review):** widgets cache
`_has_emoji` at construction (message.py:120, _image_base.py:630), and
reload evicts only widgets whose own config changed — so an added or
retargeted image source would never reach an unchanged widget. Fix: the
reload path flushes the ENTIRE widget cache whenever the committed image
slug set (or any image source's path/mtime) changed. Coarse but correct
and rare (image-source edits are infrequent); a keyed invalidation is a
future refinement.

### 3. Failure posture — never dark the panel (rev 2: matches the code)

Rev 1 claimed boot=hard-error / reload=drop-that-source. Both were wrong
against the code (boot's `build_source_registry` try/excepts EACH source
and skips; reload is atomic-or-nothing) and the PM review independently
rejected darking a sign over a decorative image. Corrected posture,
aligned with the existing machinery:

- **Boot:** a bad image source (missing file, undecodable, oversized)
  logs a clear error and is SKIPPED — its token renders as literal text;
  the panel runs. (Existing per-source try/except behavior, inherited.)
- **Reload:** unchanged atomic semantics — a bad new config keeps ALL old
  sources and the old emoji set (finding #1's two-phase commit makes the
  emoji side honor this too).
- **`led-ticker validate` is the fail-loud surface** (see §6) — preflight
  errors there, where loud is safe.

### 4. Sprite data — Phase 1 is static-only

Registered values are the EXISTING types (`PixelData` lowres,
`HiResEmoji` hires) — zero new polymorphism, zero changes to the ~10
resolution/measure/draw sites, no fast-path gate changes, no measure/draw
parity risk. A GIF contributes frame 0 (validate notes it, §6). The
stickers capture path, per-char color flow, fisheye, and both image-overlay
fast paths work unchanged because the sprite types are unchanged.

### 5. Collision rule

An `id` colliding with any existing emoji slug (curated, pack, plugin) is
a VALIDATE ERROR and a build-time skip-with-log. Validate rule 56 already
half-covers this (`is_emoji_slug(src.id)` on source ids); extend it: (a)
an image-source-tailored message that NAMES the conflict origin and
suggests a dotted id ("id 'taco' is a standard-emoji pack slug — use a
dotted id like 'cart.taco'"); (b) also flag an image id colliding with
another same-config source id (today only exact duplicate `[[source]]`
ids are caught).

### 6. Validation (`led-ticker validate` = the loud surface)

- Missing file / undecodable / unsupported extension → ERROR naming the
  path.
- Collision (per §5) → ERROR.
- Animated GIF in Phase 1 → WARNING: "renders as its first frame
  (inline animation is a planned follow-up)".
- Scale-1 sections using an image slug → WARNING: machine-downscaled 8×8
  is approximate; hand-authored art reads better at this size.
- Sanity caps: source frame area > 512×512 → WARNING (decoded anyway).
- Dangling declaration (an image source whose token no widget text
  references) → WARNING (mirror of the silent unknown-token case).
- Validate registers images through the same decode path BEFORE its
  token/widget checks (§1's ordering invariant), so what validate blesses
  is what boot renders.

### 7. Docs + discoverability (rev 2, from PM review)

- The feature docs live on the EMOJI page (docs.ledticker.dev/assets/emoji/
  gains a "Your own images as emoji" section) with a pointer from the
  value-tokens page — users search "custom emoji", not "sources".
- The docs include the file-placement walkthrough (how a PNG actually gets
  to `config/assets/` on a Pi: scp/SMB/USB; the web UI has no asset upload
  today — named explicitly as future work, not implied).
- The halal-cart example config gains a commented-out image-source block
  as living documentation.
- Config-skill fact-packs updated (sources + emoji).

### 8. Testing

- Decode/stage/commit/abort round-trip; reload keeps old set on abort
  (torn-registry regression test — stage 2 sources, fail the 3rd, assert
  registries unchanged).
- Widget-cache flush on image-source change (reload with unchanged widget
  text → new slug renders; the staleness class from review finding #5).
- Boot skip-not-dark: a bad image source boots the panel with the token
  as literal text.
- Collision: pack/curated/plugin/same-config-source-id cases; the dotted-id
  suggestion appears.
- Parse-gate agreement + render in message, two_row, image overlay;
  per-char color char_index continuity across the sprite.
- Validate rules incl. ordering (image slug registered before token
  checks — a config whose only emoji is an image slug validates clean).
- **Visual gate (James): bigsign AND smallsign renders** — logo PNG inline
  in scrolling + held text on both geometries (8×8 approximation visible
  and acknowledged on smallsign).

### 9. Phase 2 — animation (explicitly out of scope; requirements recorded)

Native-GIF-timing inline animation returns as its own spec/plan, carrying
the review findings as hard requirements: an `AnimatedSprite` type must
duck-type BOTH registry value shapes across all ~10 consumption sites
(hires `physical_size`/`logical_width`/`pixels` AND the lowres
`PixelData` iterators — the smallsign path has no frame seam today);
frame geometry must be LAYOUT-INVARIANT across frames so the pure
`measure_width` and the wall-clock draw can never disagree (the F6
measure/draw-parity contract), with a parity tripwire; the real fast-path
gates are the image-overlay ones (`_play_with_text`,
`_play_with_two_row_text` — TickerMessage/two_row redraw per engine tick
already); smallsign animation is in the visual gate; memory budget is
frames×area based (pixel-tuple lists cost ~80 B/px — a 256-frame cap
alone permits ~80 MB sprites); stickers capture unwraps to frame 0
explicitly.

## Non-goals (Phase 1)

- No animation (Phase 2, §9). No URLs. No per-image size knobs (32 px
  hires / 8×8 lowres; a size knob is the expected first enhancement
  request — deliberately deferred, not overlooked). No hand-authored
  lowres override (future). No web-UI asset upload (named as future work
  in docs). No plugin API change. No BDF-path changes.

## Release shape

Core minor (new source type + staged emoji-registration surface +
validate rules + docs). No plugin changes.

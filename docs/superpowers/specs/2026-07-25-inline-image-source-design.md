# Inline image source — custom emoji from config-declared images

**Date:** 2026-07-25
**Status:** approved (brainstorm with James)

## Problem

There is no way to use your own image inline in text the way emoji render
inline. The emoji registries are fixed at build time (curated + pack) plus
plugin code (`api.emoji`); a user with `partyparrot.gif` or a small logo
cannot declare it in config and embed it mid-sentence. James's ask: declare
an animated or static image through a `[[source]]` and embed it wherever a
`:token:` goes — a custom emoji, config-driven.

## Decisions (from brainstorm)

- **Local files only** — PNG (static) and GIF (animated) under the config
  dir (`config/assets/`, already Docker-mounted + gitignored). No URLs.
- **Native GIF timing** — animated sprites advance per the GIF's own frame
  durations (wall-clock), like the gif widget. Not tick-stepped.
- **Auto-downscale at scale 1** — every image registers BOTH a 32-px-tall
  hires form and an 8×8 lowres form (curated-emoji semantics): scaled signs
  get the hires sprite, smallsign gets the tiny approximation, and the
  three-place "renders inline" parse gate passes unchanged because a lowres
  form exists.
- **`[[source]]` declaration surface** (James's pick over a core
  `[emoji.images]` block): familiar block, `:<id>:` token — but implemented
  as a CORE source type (joining `clock`/`date`/`static` in
  `app/factories._SOURCE_TYPES`), not a plugin, because the animation and
  registry seams are core work regardless.

## Config surface

```toml
[[source]]
type = "image"
id = "partyparrot"
path = "assets/partyparrot.gif"   # relative to the config dir (gif-widget convention)

[[playlist.section.widget]]
type = "message"
text = "DEPLOY SHIPPED :partyparrot:"
```

`id` is the token name — bare `:<id>:`, same namespace and UX as
`:clock.now:` / `:wx.cart:`. The user picks any id (dots allowed as in other
source ids); no forced prefix.

## Architecture

### 1. `ImageSource` — a declaration-only core source

A new `DataSource` subclass in `sources.py`, registered in
`app/factories._SOURCE_TYPES` as `"image"`. It does NOT poll and does NOT
join the monitor roster (StaticSource posture). Its job happens once at
config load (and again on hot-reload):

1. Resolve `path` against the config dir; decode with the existing
   primitives (`widgets/_gif_decode.decode_gif` for GIF frames + durations,
   Pillow for PNG; `_image_fit` resizing).
2. Build sprite forms per frame: hires = resized to 32 px tall, width
   scaling proportionally capped at 128 px (a 4-cell-wide banner is the
   max sensible inline footprint; wider input letterboxes down); RGBA
   alpha ≥ 110 keeps a pixel — the proven Noto bake recipe. Lowres = 8×8
   resize (per-frame for animated).
3. Register the id as an emoji slug (see §2).

The source's token never needs text resolution: the emoji parser consumes
`:<id>:` directly once the slug is registered. (TokenizedField still treats
an image-source id as "known", so validate's unknown-token rule stays
quiet; resolution returning the literal token text is fine because the
emoji parse runs on the resolved string.)

### 2. Config-scoped emoji registration

`pixel_emoji` gains a small registration surface for config-declared
sprites, mirroring how plugin slugs commit into the mutable registries
(`EMOJI_REGISTRY[slug] = ...` with built-ins `setdefault`-ed around them):

- `register_image_emoji(slug, lowres, hires_frames) -> None` — inserts into
  `EMOJI_REGISTRY` + `HIRES_REGISTRY`, tracking the slug in a module-level
  `_CONFIG_IMAGE_SLUGS: set[str]`.
- `clear_image_emoji() -> None` — removes all tracked slugs; called by the
  hot-reload path before sources are respawned, so a removed/renamed
  `[[source]]` cleanly disappears.

Collision rule: registering a slug that already exists in the curated
registries, the pack, or a plugin registration is a CONFIG-LOAD ERROR
("id 'fire' collides with an existing emoji slug — pick another id").
Curated-always-wins stays intact because collisions never register.

Because every image registers a lowres form, the parse gate
(`_get_registry() OR emoji_pack.has_slug`) accepts the slug with NO gate
changes — the three-place agreement (`_parse_segments`,
`has_renderable_emoji`, rule 67) is untouched.

### 3. Animated sprites — the one new render seam

The registries hold static sprite data today. They gain an animated
variant:

- A frames container (e.g. `AnimatedSprite`: `frames:
  tuple[PixelData | HiResEmoji, ...]`, `durations_ms: tuple[int, ...]`,
  `total_ms: int`) usable as a registry value in both registries.
- `draw_emoji_at` / the `draw_with_emoji` sprite branch detect the animated
  variant and pick the frame by WALL-CLOCK: `elapsed_ms = (monotonic() -
  _EPOCH) % total_ms`, then the same duration-walk as
  `GifPlayer._pick_frame_for_elapsed`. Static sprites take the existing
  path untouched. All animated sprites share one global epoch (sprites of
  the same gif in different widgets stay in phase — a feature).

**Fast-path exclusion (load-bearing):** a widget whose text contains an
animated slug must not take the static-text fast paths, or the sprite
freezes on held text (the gif-widget freeze class). New predicate
`has_animated_emoji(text) -> bool` in `pixel_emoji`; every fast-path gate
that today checks `font_color.frame_invariant` / `border.frame_invariant`
adds `AND NOT has_animated_emoji(text)`. Known gates: `TickerMessage`'s
held/static branch, `_BaseImageWidget._play_with_text`'s static gate, and
two_row's row paths. The engine's per-tick loops then redraw at
`ENGINE_TICK_MS` cadence and the wall-clock frame-pick animates — no
`advance_frame` coupling needed (wall-clock, not counter, exactly so
transitions' `pause_frame` semantics don't fight it; during a transition
the sprite keeps animating, which matches how bordered/gif content behaves
visually).

### 4. Hot-reload

The reload path (where sources are respawned) calls `clear_image_emoji()`
then re-registers from the new config. Image decode failures at reload log
+ drop THAT source (panel keeps running; its token renders as literal
text) — plugin-error-isolation posture. At first boot, a bad image is a
hard config error (fail loud before the panel is trusted).

### 5. Validation

- Missing file / undecodable image / unsupported extension → config-load
  ERROR naming the path.
- Slug collision (see §2) → ERROR.
- Sanity cap: GIF with > 64 frames or source frame area > 512×512 →
  WARNING (decoded anyway, memory note); hard error above 256 frames.
- Scale-1 sections: no warning needed (lowres form always exists).
- `led-ticker validate` reuses the same decode path so preflight catches
  what boot would.

## Testing

- Decode/register: PNG → static lowres+hires; GIF → animated both forms;
  registry insert/clear round-trip (reload semantics).
- Collision error; missing-file error; cap warning.
- Frame-pick math: synthetic durations, elapsed → expected frame index
  (pure function, table-driven).
- Fast-path exclusion tripwire: a message with an animated slug renders
  DIFFERENT pixels at two engine ticks (the freeze-class guard, mirroring
  `test_gif_static_text_does_not_freeze_animation`).
- Parse-gate agreement: registered image slug parses inline, renders in
  message + two_row + image overlay; unknown token still literal.
- Per-char color flows around the sprite (char_index continuity — existing
  emoji tests extended with an image slug).
- **Visual gate (James):** bigsign render — a static PNG and an animated
  GIF inline in (a) scrolling text, (b) held text; sprite animates at
  native speed in both.

## Non-goals

- No URLs / remote fetch. No per-image size knobs (emoji-cell sizing only:
  32 px hires / 8×8 lowres). No dynamic id→file rebinding between reloads.
- No BDF-path rendering changes (lowres 8×8 rides the existing path).
- No plugin API surface change (`api.emoji` untouched; a future
  `api.animated_emoji` could reuse the AnimatedSprite seam but is not in
  scope).
- No stickers/transition integration work — if `flair.stickers` picks a
  config image slug it renders frame 0 via the existing capture path
  (acceptable; capture is static by design).

## Release shape

Core minor (new source type + emoji-registry surface + animated inline
sprites). No plugin changes.

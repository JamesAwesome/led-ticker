# Colored Value Tokens — Phase 2 (two_row + image overlay) — Design

**Date:** 2026-07-17
**Repo:** led-ticker core (`src/led_ticker`)
**Status:** approved (extends the Phase 1 design, shipped in core 4.14.0)

## Why

Phase 1 (`TickerMessage`, core 4.14.0) let a `:id:` value token render in its
source-declared `color` while the surrounding literal text keeps the widget's
`font_color` — mixed colors in one line. The segment infra was built "shared
to extend." Phase 2 wires the SAME behavior through the two other
token-rendering surfaces: `TwoRowMessage` (per row) and the `_BaseImageWidget`
text overlay (image/gif — single-row all alignments + two-row). Detail note:
[[project_colored_value_tokens]].

## Principle

Identical semantics to Phase 1, in two more widgets. A token's chars render in
its `color`; literal chars keep the field's host color (`top_color` /
`bottom_color` for two_row; `font_color` for image). No new config — a
source's optional `color` already exists on the base `DataSource`. When no
source in a field declares a color, the render path is BYTE-IDENTICAL to
today (the override is `None`, existing branches untouched, zero overhead).

## The Phase 1 pattern being extended (reference: `message.py`)

Each widget already resolves tokens into a flat string per field
(`_resolved_*`) via `TokenizedField.resolve`. Phase 1 added, in `message.py`:
1. A FROZEN `resolve_segments` snapshot taken at the SAME registry read as the
   flat string — typed spans `(text, color|None, is_emoji)`.
2. `_build_token_color_override(segments, visible_text, host_provider,
   has_emoji)` → a per-char list aligned to the DRAW PATH's char space
   (emoji-excluding when `draw_with_emoji` renders sprites; gated on the raw
   `_has_emoji` flag — the M1/M2 lesson: the override char space must match
   the char space the draw path iterates, in all branches).
3. A three-branch draw dispatch, each branch consulting the override:
   - **emoji present:** `draw_with_emoji(..., color_override=callable)` where
     the callable returns `override[i]` (None ⇒ host provider).
   - **per-char host provider (rainbow/gradient), no emoji:**
     `draw_text_per_char` with a callback returning `override[idx]` if set
     else `provider.color_for(...)`.
   - **whole-string/constant host, no emoji:** when an override exists, FORCE
     the per-char path (`draw_text_per_char`) so the override can win on
     individual chars while literals keep the host constant; else the plain
     `draw_text` fast path (unchanged).

`two_row._draw_row_text_at` and `_image_base._draw_text` ALREADY have these
three branches — Phase 2 adds the override into each, it does not restructure
them.

## Changes

### 1. Extract the shared builder (`sources.py`)

Move `_build_token_color_override` from `message.py` to `sources.py` (beside
`TokenizedField`) as `build_token_color_override(segments, visible_text,
host_provider, has_emoji) -> list`. `message.py` imports it and drops its
private copy — no behavior change (a pure move; message tests stay green).
Rationale: `sources.py` owns `TokenizedField` + `resolve_segments`; the
override builder is the consumer-side half of that infra and all three
widgets import from there.

### 2. `TwoRowMessage` (`two_row.py`)

- Add frozen segment snapshots `_resolved_top_segments` /
  `_resolved_bottom_segments`, filled in `_resolve_tokens` /
  `resolve_tokens_now` at the SAME `TokenizedField.resolve` call that sets
  `_resolved_top` / `_resolved_bottom` (mirror message's freeze; snapshot
  taken from the same registry read so text and segments can't disagree).
- `_draw_row_text_at` gains the row's segment snapshot (new param, or read
  the field on `self` keyed by `frame_key`). It builds the override via
  `build_token_color_override(segments, text, provider,
  has_renderable_emoji(text))` and threads it into all three existing
  branches (emoji callable / per_char callback / whole-string-forced).
- Two_row scrolls the bottom row by x-shifting the FULL resolved string
  (verified: `_draw_row_text_at` receives the full `text` and an `x` that may
  be off-canvas — no slicing), so `visible_text == text` (full row) and no
  scroll-window tracking is needed. The builder still slices defensively to
  `len(visible_text)`.
- The separator draw (`_draw_bottom_separator`) is NOT a token field — it
  keeps its current whole-string color (a separator has no `:id:`).

### 3. `_BaseImageWidget` text overlay (`_image_base.py`)

- Add frozen segment snapshots for the three text fields (`text`, `top_text`,
  `bottom_text`) filled at the same resolve calls that set
  `_resolved_text_single` / `_resolved_top_text` / `_resolved_bottom_text`.
- **Single-row `_draw_text`:** build the override from the `text`-field
  segments. `visible_text` is the actual drawn string — the full resolved
  string for static/scroll (scroll is x-shift), or the typewriter prefix
  (`text_override`); the builder already slices to `len(visible_text)`, and
  per-char `total_chars` stays anchored to the full substituted length (the
  existing I3 contract — unchanged). Thread the override into the three
  branches.
- **Two-row overlay helper (the `_draw_row`-style path at ~L1121):** same as
  two_row — per-row segment snapshot + override into its branches.
- Non-token widgets: `_resolved_* == self.<field>` and the segment snapshot
  is all-literal, so the override is all-None ⇒ byte-identical.

### 4. Fast-path / frame-invariant gate (both widgets)

Message forces per-tick redraw when a token's provider is not
`frame_invariant` (e.g. `stocks.trend`, which recolors every tick). Both
two_row and image have static/fast paths; extend each gate so a field whose
frozen segments contain a non-`frame_invariant` token provider takes the
per-tick path. A colored token with a CONSTANT provider stays fast-path
eligible (its color never changes). Predicate: any segment color provider in
any of the widget's fields reports `frame_invariant is False`.

### 5. Scope boundary

Fisheye stays out — the lens path (`flair.fisheye`) re-renders through a
separate transform and does not consume the per-char override; this is the
same boundary Phase 1 documented as M3. All other overlay modes are covered.

## Testing

Per widget (two_row, image single-row, image two-row):
- **Colored token + literal:** a `:id:` with a constant `color` renders that
  color; surrounding literals render the field's host color (pixel assertion
  on a stub canvas, as Phase 1 did).
- **No-color source → byte-identical:** a field with tokens but no source
  `color` produces the exact same pixels as the pre-change path (frozen
  snapshot equality / golden compare).
- **Frame-invariant gate:** a `frame_invariant=False` token provider forces
  the per-tick redraw (the widget's fast path is bypassed); a constant token
  color does NOT bypass it.
- **Emoji-adjacent char-space (M1/M2):** a colored token next to a `:slug:`
  emoji and next to a Unicode emoji colorizes the correct chars (the override
  char space matches the draw path's, gated on `_has_emoji`) — include the
  "`:slug:` inside a token VALUE" case Phase 1's re-review caught.
- **Typewriter prefix (image single-row):** a colored token colorizes
  correctly DURING a typewriter reveal (override slices with the prefix).
- **Scroll (two_row bottom, image scroll):** the colored token stays colored
  as the row x-shifts (full-string override, no drift).
- **Shared-helper move:** `message.py`'s existing colored-token tests still
  pass after `build_token_color_override` moves to `sources.py`.

GIF gate before merge (render-path change): a two_row config with a
`:stocks.*:` colored token (top or bottom row) + a literal label in another
color; an image/gif with a colored-token caption. Confirm mixed colors read
on both signs' geometry.

## Rollout

1. Core PR: shared extraction + two_row + image + tests + GIF gate → core
   release vNext (minor — behavior addition, no new config surface).
2. Small plugins PR (led-ticker-plugins): add a two_row + image colored-token
   line to the stocks smoke configs for hardware validation (mirrors Phase 1
   PR #49). Floors those configs to the core release.

## Out of scope

- New config surface — a source's `color` field is reused as-is.
- `flair.fisheye` overlay colorization (M3 boundary).
- Per-token color on the SEPARATOR (a separator is not a value token).

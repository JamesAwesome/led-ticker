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
   flat string — typed spans `(text, color|None, is_emoji)`. Built ONLY when
   the field's `TokenizedField.has_tokens` is true (a non-token field never
   allocates a snapshot).
2. `_build_token_color_override(segments, visible_text, frame: int,
   has_emoji: bool) -> list | None` (message.py:41; VERIFIED signature — the
   3rd param is the int frame from `self.frame_for("font_color")`, NOT a host
   provider, and it returns `None` when no token in the field declares a
   color). It produces a per-char list of `Color`-or-`None` aligned to the
   DRAW PATH's char space (emoji-excluding when `draw_with_emoji` renders
   sprites). `None` entries mean "defer to the host color"; the host provider
   is applied by the CALLER in each draw branch, never inside the builder.
3. A three-branch draw dispatch, each branch consulting the override:
   - **emoji present:** `draw_with_emoji(..., color_override=callable)` where
     the callable returns `override[i]` (None ⇒ host provider). The override
     is indexed in `draw_with_emoji`'s EMOJI-EXCLUDING char space.
   - **per-char host provider (rainbow/gradient), no emoji:**
     `draw_text_per_char` with a callback returning `override[idx]` if set
     else `provider.color_for(...)`.
   - **whole-string/constant host, no emoji:** when an override exists, FORCE
     the per-char path (`draw_text_per_char`) so the override can win on
     individual chars while literals keep the host constant; else the plain
     `draw_text` fast path (unchanged).

**THE `has_emoji` BASIS RULE (the load-bearing correctness constraint).** The
`has_emoji` argument passed to the builder MUST equal the predicate the draw
site uses to pick its emoji-vs-plain branch — otherwise the override char
space misaligns with the drawn char space and trailing literal chars steal a
token's color (the bug Phase 1's re-review caught). The four draw sites this
project touches gate emoji DIFFERENTLY, so there is NO single recipe:

| Draw site | Emoji-branch predicate (VERIFIED) | Builder `has_emoji` arg |
|---|---|---|
| `message.draw` (Phase 1, reference) | `self._has_emoji` (raw cache) | raw cache |
| two_row top-row direct (`two_row.py:667`) | unconditional `draw_with_emoji` | `has_renderable_emoji(resolved_top)` |
| two_row bottom-row direct (`two_row.py:702`) | unconditional `draw_with_emoji` | `has_renderable_emoji(resolved_bottom)` |
| two_row wrap `_draw_row_text_at` (`:417`) | `has_renderable_emoji(text)` (resolved) | `has_renderable_emoji(text)` |
| image single-row `_draw_text` (`:1028`) | `self._has_emoji()` (raw cache) | raw cache |
| image two-row `_draw_row_text` (`:1118`) | `self._has_emoji() and has_renderable_emoji(text)` | the SAME compound expr |

Each implementation task states its site's basis from this table and has a
test proving alignment when a token VALUE resolves to a string containing an
emoji slug (e.g. a weather source returning `":sun: 72"` — the case that
breaks a raw-vs-resolved mismatch).

**IMPORTANT — the named methods are NOT all uniform.** Only two_row wrap
`_draw_row_text_at` and image single-row `_draw_text` already carry the full
three-branch structure. The two_row DEFAULT path uses two DIRECT
`draw_with_emoji` calls (top `:667`, bottom `:702`) with no per-char/plain
branches — those must gain an override-aware call (and, since a constant/host
color with an override needs the per-char path, may need a small branch added,
not just a threaded kwarg). The image two-row path (`_draw_row_text`) is fed
by pre-built tuples and needs plumbing (see §3). Phase 2 is NOT "thread one
kwarg into three ready methods."

## Changes

### 1. Extract the shared builder (`sources.py`)

Move `_build_token_color_override` from `message.py` to `sources.py` (beside
`TokenizedField`) as `build_token_color_override(segments, visible_text,
frame: int, has_emoji: bool) -> list | None` — signature UNCHANGED from the
current private function (message.py:41), only the location and the leading
underscore. `message.py` imports it and drops its private copy — a pure move;
message's existing colored-token tests stay green (a task step re-runs them).
Rationale: `sources.py` owns `TokenizedField` + `resolve_segments`; the
override builder is the consumer-side half of that infra and all three widgets
import from there. Check for an import cycle: `sources.py` must not import a
widget module; the builder only needs the segment tuple shape + a color
provider's `.color_for` (duck-typed), so no new top-level import of
color-provider classes is required (confirm during the move).

### 2. `TwoRowMessage` (`two_row.py`)

TwoRowMessage draws each row through THREE distinct sites (verified against
the source): the default top row (`:667`, direct `draw_with_emoji`), the
default bottom row (`:702`, direct `draw_with_emoji`), and the wrap-mode rows
(`_draw_row_text_at`, `:397`, only reached when `bottom_text_wrap=True`, call
sites `:623`/`:645`). ALL THREE must apply the override, or the feature
silently no-ops in the default (non-wrap) configuration.

- Add frozen segment snapshots `_top_segments` / `_bottom_segments`, filled in
  `_resolve_tokens` AND `resolve_tokens_now` from the SAME registry read that
  sets `_resolved_top` / `_resolved_bottom`. Placement matters: `_resolve_tokens`
  updates `_resolved_bottom` only inside its `if changed:` block
  (`two_row.py:331`) — refresh the matching snapshot in the SAME block so text
  and segments can't drift under a frozen registry. Snapshot is built only when
  that row's `TokenizedField.has_tokens` (else left `None`, builder returns
  `None`, byte-identical).
- **Top row (`:667`) and bottom row (`:702`):** build the row override
  `build_token_color_override(row_segments, resolved_row_text,
  self.frame_for("<row>_color"), has_renderable_emoji(resolved_row_text))` and
  pass it as `color_override=` to the direct `draw_with_emoji`. Because a
  colored token must win even under a CONSTANT `top_color`/`bottom_color`,
  when the override is non-None and the row has no emoji, route through the
  per-char path (`draw_text_per_char` with an override-aware callback) instead
  of the constant `draw_with_emoji` — the same forced-per-char rule Phase 1
  uses. Factor the "draw one row's text with an optional override" logic into
  a small shared helper so `:667`, `:702`, and `_draw_row_text_at` share one
  implementation of the three-branch dispatch rather than three copies.
- **Wrap rows (`_draw_row_text_at`):** same helper; `text` here is the row's
  visible string.
- Scroll: TwoRowMessage scrolls by x-shifting the FULL resolved row string
  (the `x` passed to the draw may be off-canvas; no slicing), so
  `visible_text == resolved_row_text` and no scroll-window tracking is needed.
- The separator draw (`_draw_bottom_separator`) is NOT a token field — it
  keeps its whole-string color unchanged.

### 3. `_BaseImageWidget` text overlay (`_image_base.py`)

- Add frozen segment snapshots for the three text fields (`text`, `top_text`,
  `bottom_text`), each built (only when that field's `TokenizedField.has_tokens`)
  at the same resolve calls that set `_resolved_text_single` /
  `_resolved_top_text` / `_resolved_bottom_text`.
- **Single-row `_draw_text` (`:988`):** build the override from the
  `text`-field segments with `has_emoji = self._has_emoji()` (RAW cache
  basis — `_draw_text` selects its emoji branch on `self._has_emoji()` at
  `:1028`, NOT on resolved text; passing a resolved basis here reintroduces
  the misalignment bug). `visible_text` is the actual drawn string — the full
  resolved string for static/scroll (scroll is x-shift), or the typewriter
  prefix (`text_override`); the builder slices to `len(visible_text)`, and
  per-char `total_chars` stays anchored to the full substituted length (the
  existing I3 contract — unchanged). Thread the override into the three
  branches.
- **Two-row overlay `_draw_row_text` (`:1090`):** its emoji branch predicate
  is the COMPOUND `self._has_emoji() and has_renderable_emoji(text)` (`:1118`)
  — the builder's `has_emoji` arg must be that exact expression. This method
  is fed by pre-resolved tuples built in `_render_two_row_tick` (`:1428`),
  `_render_two_row_wrap_tick` (`:1474`), and the two-row fast-path tuple
  builders (`:1983`, `:2057`); the tuple has no segment field. Threading a
  per-row override requires: (a) resolving per-row segment snapshots in
  `_play_with_two_row_text` alongside the existing top/bottom text resolves,
  (b) widening the row tuple (or adding a parallel per-row override) through
  each composer AND the fast-path builders, and (c) widening `_draw_row_text`'s
  signature. This is multi-method plumbing, not a one-line thread — the plan
  must budget a dedicated task for it.
- Non-token fields: `has_tokens` is false, no snapshot is built, the override
  is `None` ⇒ byte-identical to today.

### 4. Fast-path / frame-invariant — NO gate change needed (corrected)

The original draft proposed extending a "frame-invariant gate" in both
widgets. That was wrong on the facts (antagonist review, verified):

- **TwoRowMessage has NO static/paint-once fast path** — `draw()` redraws
  every engine tick unconditionally (no `_is_static`, no self-owned swap).
  A trend-colored token already animates via the engine's per-tick
  `advance_frame` + `draw`. There is nothing to gate. Do NOT add one.
- **Image already forces per-tick on ANY token** — the paint-once fast path
  is gated on `and not self._has_overlay_tokens()` (`_image_base.py:1667`,
  `:1981`). Any token field (colored or not) already takes the per-tick
  loop. Do NOT narrow this to "only non-frame-invariant": a constant-color
  token must still force per-tick (its VALUE can change even if its color is
  constant — the reason `_has_overlay_tokens()` exists). Leave the gate as is.

Net: no fast-path change in either widget. A task step ASSERTS this (a
trend-colored token in each widget animates; the image fast path is already
bypassed for token fields) rather than implementing a gate.

### 5. Scope boundary — fisheye differs between message and image (corrected)

In `message.py` the lens uses a SEPARATE paint method that never consults the
override, so Phase 1's M3 "fisheye out" boundary holds there. In `_image_base.py`
the fisheye lens strip adapter calls `self._draw_text(...)` (`:1209`) — the
SAME method §3 modifies — so the override WILL reach the image fisheye path
whether or not we intend it. Decision: **embrace it.** The override is a
per-char color map that is geometry-independent (the lens only remaps x
sampling; each source char keeps its color), so colored tokens through the
image fisheye lens are expected to render correctly. Add a test that a colored
token renders colored under `flair.fisheye` on an image widget. Do NOT claim
image parity with message's M3 boundary — image has no such boundary because
its lens shares `_draw_text`.

## Testing

Per surface — **two_row TOP row (`:667`), two_row BOTTOM row (`:702`),
two_row WRAP rows, image single-row, image two-row** (C1: the two_row default
top/bottom sites are distinct from the wrap helper and each need their own
coverage):
- **Colored token + literal:** a `:id:` with a constant `color` renders that
  color; surrounding literals render the field's host color (pixel assertion
  on a stub canvas, as Phase 1 did). For two_row, assert this on a
  DEFAULT-mode (`bottom_text_wrap=False`) widget so the `:667`/`:702` sites
  are exercised, not just the wrap helper.
- **No-color source → byte-identical:** a field with tokens but no source
  `color` produces the exact same pixels as the pre-change path.
- **has_emoji-basis alignment (C2 / M1/M2) — the key correctness test:** a
  colored token whose VALUE resolves to a string CONTAINING an emoji slug
  (source returns `":sun: 72"`). Assert the token's chars colorize correctly
  and no trailing literal steals the color — run this on each surface, since
  each gates emoji on a different basis (raw cache vs resolved vs compound).
  This is the test that fails if a surface uses the wrong `has_emoji` arg.
- **Colored token adjacent to a `:slug:` and a Unicode emoji** in the field
  text itself (not just in the value).
- **Typewriter prefix (image single-row):** a colored token colorizes
  correctly DURING a typewriter reveal (override slices with the prefix).
- **Scroll (two_row bottom default marquee, image scroll):** the colored token
  stays colored as the row x-shifts (full-string override, no drift).
- **Fisheye on image (I3):** a colored token renders colored under
  `flair.fisheye` on an image widget (the lens shares `_draw_text`).
- **No fast-path regression (I2):** a constant-color token still forces the
  image per-tick loop (`_has_overlay_tokens()` unchanged); a trend-colored
  token animates in both widgets.
- **Shared-helper move:** `message.py`'s existing colored-token tests still
  pass after `build_token_color_override` moves to `sources.py` (import
  update only).

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
- `flair.fisheye` on the MESSAGE widget stays out (M3, its lens uses a
  separate paint method). Image fisheye is IN (§5 — the image lens shares
  `_draw_text`, so colored tokens flow through it by construction).
- Per-token color on the SEPARATOR (a separator is not a value token).

## Revision note

This spec was revised 2026-07-17 after an antagonistic review found five
verified defects in the first draft: (C1) it targeted `_draw_row_text_at`,
which only runs in `bottom_text_wrap` mode — the default two_row path
(`:667`/`:702`) was missed; (C2) it gave one `has_emoji` recipe for four
sites that gate emoji differently; (I1) the builder signature named a
non-existent `host_provider` param (it is `frame: int`); (I2) the
frame-invariant fast-path gate was wrong — two_row has no fast path and image
already gates on any token; (I3) image fisheye shares `_draw_text`, so the
"fisheye out" boundary was false for image. §§1–5 + testing were rewritten
against verified file:line evidence.

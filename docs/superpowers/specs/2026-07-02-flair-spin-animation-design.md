# Flair propeller animation (`flair.propeller`) + core rotation seam — Design

**Date:** 2026-07-02
**Status:** Validated — two rounds. Round 1 (engineer: "implementable as
spec'd" + 2 required edits; PM: "approved with changes") folded in; naming +
default decided by product owner. Round 2 re-review (engineer: "ready for
implementation planning"; PM: "approved with changes") folded in below.
Round-2 adjudication note: the PM's "silent cut zone" finding
(`spin_seconds > 1 s` with a longer hold gets cut) was REJECTED with code
evidence — the spin runs at visit START, during the hold, so
`spin_seconds ≤ hold_time` always completes mid-hold and is never cut; the
only cut zone is `hold < spin`, which rule 62 owns. The §7 wording that
invited the misreading was rewritten.
**Repos:** led-ticker (core seam PR, first) + led-ticker-plugins (flair PR, second)

## Problem / goal

Add a "spinning text" animation to the **flair** plugin wheel: when a message
widget appears, the entire printed text **rapidly spins in-plane like a
propeller** around its own center, decelerates, and settles flat and readable
for the rest of the hold.

Today's `Animation` seam cannot express this: `AnimationFrame` carries only
`visible_text: str` (a text-slice contract built for Typewriter). A spin is a
pixel-space transform, so the feature is two PRs: a small core seam
extension + the flair-side animation.

## Decisions made during brainstorm + validation

- **Geometry: whole-text propeller** (in-plane rotation about the text
  block's center). Chosen over coin-flip / per-char pinwheels / barrel roll,
  understanding that a wide message is mostly clipped near 90° (the mid-spin
  blur-sweep IS the effect).
- **Envelope: spin-in, then rest.** Rapid revolutions on visit entry (~1 s),
  decelerating (ease-out cubic) into flat, then readable for the rest of the
  hold. Restarts each visit.
- **Name: `flair.propeller`** (PM finding: `spin` is the most generic
  possible name and can never be reclaimed after release; `propeller` is
  unambiguous, matches the wheel's compound-name pattern, and leaves
  `flair.spin` free for a future family/alias).
- **Defaults: `revolutions = 2`, `spin_seconds = 1.0`** (product owner chose
  drama over the PM's `revolutions = 1` legibility argument; the short-hold
  risk is covered by validate rule 62 below instead).
- **Seam shape: transform field + core-owned pixel math.** Rejected: a
  duck-typed `render()` override on Animation (plugin would reimplement the
  text pipeline) and a forward-map SetPixel rotation wrapper (non-surjective
  mapping leaves ~30% pixel holes at 45°).
- **Inverse mapping:** per destination pixel, sample the source at `R(−θ)` —
  hole-free at every angle, nearest-neighbor.

## Design — core seam (led-ticker PR)

### 1. `AnimationFrame.rotation`

`src/led_ticker/animations.py`:

```python
@dataclass
class AnimationFrame:
    visible_text: str
    rotation: float = 0.0  # degrees, clockwise-positive; 0.0 = no rotation
```

Back-compat verified by the engineer: all construction sites use keyword
form; image widgets read only `.visible_text` and correctly ignore
`.rotation` (matches the §4 scope-out). `AnimationFrame` is already exported
via `led_ticker.plugin`; the docs-site plugin API reference gains the field
description.

### 2. Public-surface addition — `ENGINE_TICK_MS` (REQUIRED, engineer finding 1)

`ENGINE_TICK_MS` is NOT currently importable from `led_ticker.plugin`, and
flair's import-purity test forbids any other `led_ticker.*` import — so
**adding `ENGINE_TICK_MS` to `led_ticker.plugin` (import + `__all__`) is a
required core-PR item**, an explicit acceptance criterion, and the flair PR
hard-blocks on it. (The Spin class converts `spin_seconds` to frames with it.)

### 3. Rotation engine — new module `src/led_ticker/rotate.py`

Deliberately **resolution-agnostic** (no logical-vs-physical assumptions;
this is what makes the physical-resolution follow-up a plumbing-only change):

- `class PixelBuffer` — minimal owned raster: `width`, `height`,
  `SetPixel(x, y, r, g, b)` (out-of-bounds silently ignored, matching real
  canvas semantics), readable storage. This is OUR object — hardware
  constraint #3 (no GetPixel on real canvases) does not apply to it.
  Attribute surface required by the draw chain (engineer-enumerated):
  `SetPixel`, `width`, `height`; it must return itself from
  `unwrap_to_real()` (passthrough — automatic, no `.real` attr) and be
  `is_scaled() == False`.
- `def rotate_blit(dst, src: PixelBuffer, angle_deg: float, cx: float, cy: float) -> None`
  — for each dst pixel in the axis-aligned bounding box of the rotated src
  extent (clamped to dst bounds), inverse-map through `R(−θ)` about
  `(cx, cy)`, nearest-neighbor sample; **unset src pixels are transparent**
  (skip — never paint black over the background). `dst` is anything with
  `SetPixel`. Angle convention: clockwise-positive, degrees; `rotate_blit`
  doesn't special-case 0 (callers gate).
- No existing rotate/blit code collides (engineer-verified; `panel_map.py`'s
  90° hardware remap is unrelated).

### 4. Widget integration — `TickerMessage.draw`

When `anim_frame.rotation % 360 != 0`:

1. Create `PixelBuffer(canvas.width, canvas.height)` (logical dims, v1).
2. Run the widget's NORMAL text branches (emoji path / per-char path /
   whole-string path) against the buffer instead of the canvas — all three
   thread the canvas param and paint via SetPixel (engineer-verified
   redirectable without refactoring).
3. `rotate_blit(canvas, buffer, rotation, cx, cy)` with
   `cx = start_pos + content_width / 2`, `cy = canvas.height / 2` — the
   text block's own center. `compute_cursor` already folds `center=True` /
   left-align / overflow into `start_pos`, so one formula covers all
   alignments. (No `text_x_offset` interaction — that knob doesn't exist on
   TickerMessage.)
4. Cursor advance: unchanged — the same draw calls compute it against the
   buffer.

**Unrotated on purpose:** the border (`self.border.paint`) frames the PANEL,
not the text — it keeps painting directly to the canvas before the text,
exactly as today.

**Hires-font guard (LOAD-BEARING, engineer finding 2 — not cosmetic):** a
HiresFont routed into a logical buffer renders garbage (`_draw_hires_text`
reads `scale=1` off the buffer and paints real-pixel-sized glyphs into
logical space). If `isinstance(self.font, HiresFont)` and rotation ≠ 0:
skip rotation for that draw (normal unrotated path) + ONE log warning per
widget instance. Never crash, never blank. Additionally surfaced at
config time by validate rule 63 (§6).

**Emoji behavior (v1):** the buffer is not a `ScaledCanvas`, so the
hires-emoji gate doesn't fire — emoji render lo-res 8×8 into the buffer and
**rotate with the text** (correct on smallsign). Known cosmetic edge on
bigsign: emoji POP from lo-res to hi-res at the settle instant. Called out
ON THE DOCS PAGE (PM finding 7 — not buried in CLAUDE.md); erased by the
physical-resolution follow-up.

### 5. `emits_rotation` marker (PM Blocker resolution)

Core validate cannot import flair to detect a rotation-emitting animation,
so the Animation protocol gains an optional class attribute:
`emits_rotation: bool` (absent/False = never rotates; Typewriter untouched).
The `Propeller` class sets `emits_rotation = True`. Core reads it
duck-typed (`getattr(anim, "emits_rotation", False)`).

### 6. Validate rules (core PR)

- **Rule 62 — animation duration vs hold (PM finding 2):** generalize the
  rule-61 mechanism: for a coerced animation that is NOT a Typewriter
  (rule 61 owns that wording) but exposes `frames_to_rest`, compute
  `duration = frames_to_rest(0, len(text)) × ENGINE_TICK_MS / 1000` and
  warn when it exceeds the effective hold
  (`max(section.hold_time, widget hold_time)` — same math as rule 61):
  "animation runs ~X.Xs but the effective hold_time is Y.Ys — it will be
  cut mid-animation." Coherent with the settle seam: all-or-nothing means
  an over-cap remainder gets NO deferral, so a too-short hold really does
  cut mid-spin — exactly what this warns about.
- **Rule 63 — rotation on a hires font (PM Blocker):** animation with
  `emits_rotation` truthy + widget font resolving to a HiresFont → warning:
  "flair.propeller will not spin hires/custom fonts until
  physical-resolution rotation ships; text will display normally. Switch
  this widget to a BDF font to get the spin effect now." (Actionable
  clause per PM round-2 finding 1.) Fires in `led-ticker validate` and
  (via the existing startup report logging) in the startup log. Static
  hires detection is cheap and already exists: `_is_hires_font_name(name)`
  (`coercion.py`) checks membership in `list_available_hires_fonts()` —
  no font construction needed (engineer round-2 verified).
- **Best-effort scope (both round-2 reviews):** rules 62 and 63 coerce the
  animation, so they fire only when the flair plugin is INSTALLED in the
  validating environment. On a machine without flair, `flair.propeller`
  fails coercion and the existing unknown-style error (with its
  install-hint via `_with_plugin_hint`) owns the messaging — the rules
  swallow the coercion error and skip, mirroring rule 53's
  plugin-transition pattern. State this in the rules' docstrings.

### 7. Scope-outs (v1)

- Rotation honored by **TickerMessage only**. Gif/image text overlays ignore
  the `rotation` field — documented in the animations page's
  "Where it works" table (PM finding 8).
- Logical-resolution rotation only (bigsign rotates in 4-px blocks).
- Propeller only: no per-char mode, no continuous mode, no coin-flip.
- Settle interaction, precise model (rewritten after the round-2
  misreading): the spin plays at visit START, during the hold — when
  `hold_time ≥ spin_seconds` the spin completes mid-hold and is NEVER cut,
  regardless of the settle cap. The settle seam only matters when the hold
  expires mid-spin (`hold < spin`): the remainder is finished if ≤
  `MAX_SETTLE_TICKS` (20 ticks ≈ 1 s, all-or-nothing), else cut immediately
  — and every `hold < spin` config already drew a rule 62 warning at load
  time. Numeric note (engineer round 2): the default spin
  (`spin_seconds = 1.0` → 20 frames) sits exactly at the settle ceiling,
  so even a `hold_time` → 0 edge finishes its spin; `spin_seconds > 1.0`
  relies on `hold_time` covering the excess (which rule 62 checks).

## Design — the propeller animation (led-ticker-plugins flair PR)

### 8. Registration

Fifth namespace on the flair wheel (`pyproject.toml` entry point):

```toml
flair = "led_ticker_flair.flair:register"
```

`src/led_ticker_flair/flair/__init__.py` registers
`api.animation("propeller")` → TOML `animation = "flair.propeller"` or
`{style = "flair.propeller", revolutions = 3, spin_seconds = 1.5, direction = "ccw"}`.
Note (engineer finding 5): this breaks the wheel's "namespace = sprite
family" pattern (the fifth namespace is the wheel's own name) — acceptable,
document in flair's CLAUDE.md ("One wheel, five plugin namespaces"). The
import-purity test auto-covers the new module via rglob.

### 9. `Propeller` animation class

Constructor kwargs (dict-form reachable, like Typewriter):
- `revolutions: int = 2` (full 360° turns; ≥ 1, validated in `__init__`)
- `spin_seconds: float = 1.0` (> 0, validated)
- `direction: str = "cw"` (`"cw"` / `"ccw"`, validated; ccw negates the
  angle — PM finding 4, included in v1 as a sign flip)

Class attributes: `restart_on_visit = True` (explicit), `emits_rotation = True`.

```python
total_frames = max(1, int(spin_seconds * 1000) // ENGINE_TICK_MS)

def frame_for(self, frame, full_text, canvas_width, text_width):
    t = min(1.0, frame / self.total_frames)
    eased = 1.0 - (1.0 - t) ** 3          # ease-out cubic
    angle = (360.0 * self.revolutions * eased) % 360.0
    if self.direction == "ccw":
        angle = -angle % 360.0
    return AnimationFrame(visible_text=full_text, rotation=angle)

def frames_to_rest(self, frame, total_chars):
    return max(0, self.total_frames - frame)
```

- `visible_text` is ALWAYS `full_text`; only `rotation` varies.
- Landing exactness (engineer-verified numerically): `eased(1.0) == 1.0`
  exactly and `(360.0 · int_revs) % 360.0 == 0.0` exactly — the rest state
  is a true unrotated draw. Mid-spin, the post-mod angle passes through 0
  once per revolution (flat = correct propeller behavior, not a bug).
- `frames_to_rest` is one-shot and monotone → composes with the #305 settle
  seam with zero wiring (engineer-verified: `animation` ∈ `_EFFECT_ATTRS`,
  duck-typed pickup).
- `ENGINE_TICK_MS` imports from `led_ticker.plugin` (§2 — hard dependency).
- **Version-skew error quality (PM round-2 finding 10):** flair's
  `register()` wraps the `ENGINE_TICK_MS` import and re-raises ImportError
  with an explicit message — "flair.propeller requires led-ticker >= <the
  core release carrying the seam>; update the core image" — so the plugin
  loader's failed-plugin log tells the user the FIX (update core, not
  flair) instead of a generic import failure. The loader's error-isolation
  path already logs and skips; this just makes the logged reason
  actionable.
- Imports ONLY from `led_ticker.plugin`.

## Follow-up (designed-for, not built): physical-resolution rotation

One plumbing change in the §4 branch — when `is_scaled(canvas)`: build
`PixelBuffer(w·scale, h·scale)`, wrap in `ScaledCanvas(buffer, scale)`, run
the draw into the wrapper (hires fonts paint real pixels via
`unwrap_to_real`; the hires-emoji gate fires), then `rotate_blit` onto
`unwrap_to_real(canvas)` at physical coordinates. `PixelBuffer` and
`rotate_blit` need ZERO changes. Delivers: custom/hires fonts in the spin,
hires emoji in the spin, no settle pop, 4× smoother bigsign rotation.
Deletes the v1 hires guard + rule 63. Estimated one-task PR (~50 lines +
tests).

## Testing

**Core (`tests/test_rotate.py` + widget + validate tests):**
- `rotate_blit` 90°/180°/270°: exact pixel permutations.
- 45°: center pixel invariant; all painted pixels in-bounds.
- Transparency: dst pre-seeded with a sentinel color; sentinel survives
  outside the glyph area.
- `AnimationFrame()` back-compat: `rotation` defaults 0.0; Typewriter
  untouched.
- `unwrap_to_real(PixelBuffer(...)) is` the buffer (base-case identity —
  PM round-2 finding 11; verify the function's no-`.real` base case rather
  than assuming).
- Widget: rotation=0 → buffer path NOT taken; rotation=90 via stub
  animation → text pixels rotated, border pixels unrotated, cursor advance
  equals the unrotated advance; hires-font + rotation → unrotated draw +
  one warning (caplog).
- Emoji: `:slug:` text + rotation → lo-res sprite pixels present in the
  rotated output.
- Rule 62: fires for a stub `frames_to_rest` animation exceeding hold;
  not for Typewriter (rule 61 owns it); max-hold semantics.
- Rule 63: fires for `emits_rotation` + hires font; not for BDF; not for
  Typewriter.
- `ENGINE_TICK_MS` importable from `led_ticker.plugin` (acceptance
  criterion test).

**Flair (`plugins/flair/tests/`):**
- Envelope (engineer finding 4 — corrected): the PRE-modulo angle
  `360·revs·eased` is strictly increasing; the post-mod angle lands exactly
  0.0 at `total_frames` and stays 0.0 after.
- `direction="ccw"` mirrors angles (`-angle % 360`); invalid direction raises.
- `frames_to_rest`: `total_frames` at 0, 0 at/after `total_frames`.
- `visible_text == full_text` at every frame; `emits_rotation is True`.
- Registration resolves `flair.propeller`; constructor validation
  (`revolutions < 1`, `spin_seconds <= 0` raise); import purity.

**Visual:** render-demo gif (spin-in → settle → cut) ships ON the docs page
at launch (PM finding 12), not just as a PR artifact.

## Docs (PM findings 7, 8, 11)

- The **flair plugin's docs page owns the feature** (same pattern as the
  sprite-trail transitions); the core animations concept page cross-refs it
  and adds `flair.propeller` to the "Where it works" table.
- Bigsign emoji-pop callout on the docs page.
- Short-message tuning note on the docs page (PM residual concern, decided
  defaults stand): "for short messages, `revolutions = 1` or
  `spin_seconds = 0.8` reads less like flicker."
- Plugin catalog entry for the flair wheel gains the animation in
  `provides`.
- Plugin API reference: `AnimationFrame.rotation` field, `emits_rotation`
  marker, `ENGINE_TICK_MS` export.

## Delivery

1. **led-ticker core PR** — `rotation` field, `ENGINE_TICK_MS` export,
   `rotate.py`, TickerMessage integration, hires guard, rules 62 + 63,
   docs, tests. No flair dependency.
2. **led-ticker-plugins flair PR** — fifth namespace, `Propeller`, tests,
   README/CLAUDE.md/catalog updates. Hard-blocks on a released core
   carrying §1/§2 (pin per the deploy-doc convention).

## Contributor process

Branch + PR in each repo (never main); `make dev` per worktree; ruff +
ruff-format + pyright before push; full `make test` in core (meta-tripwires
fire only on the full suite); monorepo `make lint` + `uv run pytest
plugins/flair` on the flair side. No `from __future__ import annotations`.

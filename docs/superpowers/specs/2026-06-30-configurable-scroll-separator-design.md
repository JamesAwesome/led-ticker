# Configurable scroll-transition separator (unified separator rendering)

**Date:** 2026-06-30
**Branch family:** `feat/configurable-scroll-separator` (ships as **3 staged PRs**)
**Type:** Feature (rendering + config) — built on a behavior-preserving refactor
**Reviewed by:** principal engineer + PM (2026-06-30); their blocking findings (R1–R7) and notes (N1–N5) are folded in below.

## Problem

The `scroll` transition draws a **hardcoded 2×2 white dot** between outgoing and
incoming content. It looks jarring on some displays and — unlike the ticker-mode
separator — can't be recolored, resized, or replaced. The same separator visual
is drawn in **three** places with three implementations:

- `ticker._CircleBufferMsg.draw` / `_draw_hires_circle` — ticker-mode side-by-side
  separator (configurable color/glyph/font; default = hi-res filled circle,
  `_CIRCLE_LOGICAL_RADIUS = 4`; on a **plain** canvas it falls back to the BDF
  "•" glyph via `TickerMessage`, font-driven advance — `ticker.py:129-134`).
- `ticker._draw_bullet` / `_draw_scroll_frame` — the inter-widget `scroll` path
  (hardcoded 2×2 dot; `BULLET_WIDTH = 2`, `BULLET_COLOR = (255,255,255)`,
  `SCROLL_GAP = 6`).
- `transitions/effects.py` `Scroll.frame_at` — the registered `scroll` transition
  (hardcoded 2×2 dot, inline duplicate of the above).

Two gaps fall out: the scroll bullet has **no** config, and the ticker circle has
**no size knob** (can't shrink the big dot).

## Goal

Make the scroll-transition separator **as configurable as the ticker-mode
separator** — color (incl. providers), custom glyph, font, and size — by unifying
the rendering, preserving every current default appearance exactly.

Agreed shape: unify the **renderer + appearance type**, keep **two scoped config
homes**, **per-site defaults**. The `scroll` transition can run section-to-section,
so its separator belongs to the transition, not a section.

Non-goals: changing any current default look; asymmetric gaps; a persistent
frame-aware counter for the separator (it derives its animation frame locally).

## Phasing (3 PRs)

Per the principal-engineer review, the riskiest piece (variable-width scroll
geometry + a derived animated frame inside an otherwise-frozen transition) must
land on a proven, behavior-preserving foundation.

**Phase 1 — behavior-preserving extraction (no new config, no user-facing change).**
Create `separator.py` (`SeparatorSpec`, `render_separator`, `separator_width`);
move the circle helpers; re-express today's circle separator AND the scroll dot
through the shared renderer. **Acceptance: every existing ticker-separator and
scroll tripwire stays green with zero pixel drift.** Implements R1, R3, R4, N1, N3.

**Phase 2 — scroll config + variable-width geometry (load-bearing, riskiest).**
Add `TransitionConfig.separator` / `separator_color` / `separator_font` /
`separator_font_size`; resolve to a `SeparatorSpec`; thread `separator_width(spec)`
through the scroll geometry on **both** consumers; wire the derived frame; add
validation; **ship the docs + drift-test update in this PR** (CI gate). Implements
R2, R5, R6, R7, N2, N4, N5.

**Phase 3 — `separator_size` knob.** `separator_size` (dot/circle filled-shape
pixel size) on both `SectionConfig` (ticker circle — closes the shrink gap) and
`TransitionConfig` (scroll dot). Glyph size already comes from `separator_font_size`
(Phase 2). Positive-int validation; docs + drift-test update.

Each phase is an independently shippable, reviewable PR. This spec describes the
whole feature; each phase gets its own implementation plan.

## Design

### 1. `SeparatorSpec` + renderer (new `src/led_ticker/separator.py`) — Phase 1

A **leaf module** (N3): may import `color_providers`, `fonts`, `scaled_canvas`,
`text_render`, `widgets.message`; must **not** import `ticker` or `transitions`
(so `effects.py` and `ticker.py` both depend on it, no cycle).

```python
@attrs.define
class SeparatorSpec:
    kind: str              # "dot" | "circle" | "glyph"
    color: ColorProvider   # normalized; constants wrap in _ConstantColor
    size: int              # dot/circle: filled-shape pixel size (Phase 3 knob);
                           # ignored for glyph (glyph size = font)
    glyph: str = ""        # kind == "glyph": character(s)
    font: Any = None       # kind == "glyph": resolved BDF/hires font

def render_separator(canvas, x, frame, spec) -> int:
    """Paint the separator at LOGICAL x; return the mark's LOGICAL advance
    (its own width, NO padding — callers add their own). `frame` drives the
    color provider: spec.color.color_for(frame, 0, 1)."""

def separator_width(spec) -> int:
    """The mark's own LOGICAL width (no padding). dot/circle: size-derived;
    glyph: font-driven pixel advance."""
```

**Render kinds (N1 — dot stays a primitive, NOT a 1-char glyph, for byte-identical
back-compat):**
- `dot` — a `size`×`size` filled square via `SetPixel` (default size 2 →
  today's 2×2). Used by the scroll default.
- `circle` — a filled disk at **physical** resolution via `paint_hires` on a
  `ScaledCanvas` (radius = `size // 2`; default size 8 → radius 4, today's look).
  **On a plain canvas (smallsign / scale=1), `circle` renders the BDF "•" glyph
  via the existing `TickerMessage` path (R4)** — font-driven advance, never a 2px
  dot. Used by the ticker default.
- `glyph` — arbitrary character(s) via `text_render.draw_text` directly (N3 — not
  by constructing a `TickerMessage`, to keep the renderer a pure paint function).

**Frame sourcing (R1) — `render_separator` takes an explicit `frame: int`:**
- Ticker path: the separator widget passes `self.frame_for("font_color")`
  (today's `_CircleBufferMsg.draw`, `ticker.py:130`), driven by the engine's
  per-tick `_advance_frame_if_supported`.
- Scroll paths: there is **no** frame counter. Derive one **locally** from
  transition progress — `Scroll.frame_at` uses its integer `scroll_offset`;
  `_scroll_between` uses its loop `offset`. This counter is transition-local and
  transient.

**Width is LOGICAL, paint is physical (N4):** `Scroll.frame_at` works in logical
canvas units and must not switch to physical; `separator_width` returns logical
px and `render_separator` does any physical paint internally via `paint_hires`
(mirroring `_draw_hires_circle`'s `(cursor_pos + pad)*scale` centering,
`ticker.py:92-101`).

### 2. Padding stays at the call sites (R3)

`separator_width(spec)` returns the **mark's own width**. Each site adds its own
padding:
- Ticker advance: `pad + width + pad` with `pad = _CIRCLE_LOGICAL_PAD = 1`
  (default circle → `1 + 8 + 1 = 10`, byte-identical to today's
  `_CIRCLE_LOGICAL_ADVANCE`).
- Scroll geometry: `gap + width + gap` with `gap = SCROLL_GAP = 6` (default dot →
  `6 + 2 + 6 = 14`, today's `scroll_separator_width()`).

`scroll_separator_width` becomes `scroll_separator_width(spec, gap=SCROLL_GAP)`.

### 3. Ticker & scroll consume the renderer — Phase 1

- `_CircleBufferMsg.draw` delegates to `render_separator(canvas, cursor_pos,
  self.frame_for("font_color"), self._spec)` (circle spec, ø8). `DEFAULT_BUFFER_MSG`
  unchanged in appearance.
- `Scroll.frame_at` calls `render_separator(canvas, bullet_x, scroll_offset,
  self._spec)` (dot spec, size 2) instead of the inline dot; positioning uses
  `separator_width(self._spec)`.
- `_draw_scroll_frame` / `_scroll_between` call `render_separator` with the dot
  spec and the loop `offset` as frame. `_draw_bullet`, `BULLET_WIDTH`,
  `BULLET_COLOR` are removed (folded into the `dot` kind).
- The circle helpers (`_build_circle_offsets`, `_draw_hires_circle`) **move** to
  `separator.py`; `effects.py` drops its deferred `from led_ticker.ticker import …`
  (N3) and imports from `separator.py` at top level.

### 4. Variable-width geometry — Phase 2 (the load-bearing change)

The scroll math assumes a constant 2px. Thread `separator_width(spec)` through
`total_travel`, `bullet_x`, and `incoming_pos` in **both** `Scroll.frame_at` and
`_draw_scroll_frame`. **`clear_start` stays `max(0, w - offset)` (N2)** — it blacks
out outgoing's tail bleed and is independent of separator width; do not refactor it
to depend on the spec.

**Two consumers, two spec sources (R5):**
- Section-entry / `run_transition` path → `Scroll.frame_at` → uses `self._spec`
  (set in `Scroll.__init__`).
- Inter-widget slideshow scroll → `_run_swap` special-cases `self._scroll_between`
  (`ticker.py:838-844`), which is a `Ticker` method, not `Scroll`. It reads the spec
  from **`self.transition_fn._spec`** (the `Scroll` instance already lives on the
  Ticker as `transition_fn`, `run.py:1004`). Because the same `TransitionConfig`
  feeds both entry and inter-widget transitions (via `transition_specified`), both
  paths resolve to one consistent spec.

**Animated separator vs the transition-freeze invariant (R2):** constraint #12 /
the transition-freeze contract freezes frame-aware widgets mid-transition
(`pause_frame`/`resume_frame`). A `rainbow` `separator_color` makes the separator
the only animated element during the transition — acceptable **only because** the
separator is not a `FrameAwareBase` widget with a persistent counter to drift; its
frame is the transition-local derived counter (R1), so it can't desync a real
widget's phase. The spec states this as a deliberate carve-out.

### 5. Config — two homes, same field family

- `TransitionConfig` (Phase 2): `separator`, `separator_color`, `separator_font`,
  `separator_font_size`; (Phase 3): `separator_size`. All default `None`. Honored
  only by the `scroll` transition.
- `SectionConfig` (Phase 3): `separator_size` (default `None`), beside the existing
  `separator*` fields; applies to the ticker-mode circle.

All defaults `None` ⇒ today's appearance (ticker circle ø8 / scroll dot 2×2).

### 6. Shared resolver + transition construction (R6) — Phase 2

`app/factories._resolve_separator_spec(*, separator, separator_color,
separator_font, separator_font_size, separator_size, default_kind) -> SeparatorSpec`,
called by both sites. Branching mirrors today's `_resolve_buffer_msg`:
all-unset → `default_kind` spec (white, default size); color-only → `default_kind`
recolored; glyph/font set → `kind="glyph"`.

`_build_trans_obj` builds the spec with `default_kind="dot"` and passes it to
`Scroll`. **Guard the color-provider coercion to `type == "scroll"`** — this
function runs for *every* transition (cut/dissolve/push/…) and must not coerce,
cost, or error for the others. Plugin transitions route through `extra`;
`separator_*` are named dataclass fields, so they never reach a plugin transition
(the validator rejects them there instead of silently dropping).

The ticker path's `_resolve_buffer_msg` is refactored to build a spec with
`default_kind="circle"` and wrap it in the separator widget.

### 7. Validation (R7) — Phase 2 / Phase 3

`TransitionConfig` is used as `between_sections`, per-section `transition`,
`entry_transition`, and `widget_transition` (`config.py:95-118`). The new rule must
inspect **each** home and **reject `separator_*` where the resolved `type !=
"scroll"`** (e.g. `widget_transition = scroll` but `entry_transition = dissolve`),
with a message that points the user at the scroll transition. Resolve
`separator_font` for scroll transitions mirroring `_check_separator_fonts`
(`validate.py:1365-1417`); `separator_size` must be a positive int (Phase 3).
Also clarify the existing section-level rule-26 message: section `separator_*`
affects only `mode = "ticker"`; for the scroll transition, set them in the
transition table.

### 8. Docs + drift gate — Phase 2 (PM: CI gate, not a follow-up)

`tests/test_docs_config_options_drift.py` audits `config-options.mdx` against the
config dataclasses, so new `TransitionConfig`/`SectionConfig` fields **must** be
documented in the same PR or CI fails. Updates: the `[transitions]` table rows in
`reference/config-options.mdx`; a paragraph (+ its OptionsTable source) under the
`scroll` variant in `transitions/special.mdx`; the section-separator note in
`concepts/sections-and-modes.mdx` (Phase 3 size). Any strict unknown-key check on
the transition table must allow-list the new fields.

## Back-compat

Purely additive; no migration. Every existing config renders identically (all new
fields default `None`; per-site defaults reproduce circle ø8 and dot 2×2). The
existing ticker-separator + scroll tripwires are the Phase-1 guardrail.

## Testing

**Phase 1 (refactor safety):** existing ticker-separator + scroll tripwires stay
green, zero pixel drift. Migrate (don't delete) the tripwires that pin the old
internals (N5): `tests/test_transitions.py:849-860` (imports `BULLET_WIDTH`, calls
`scroll_separator_width()` with no args) and `tests/test_ticker.py:353-401` (pins
`cursor == 10` + the smallsign BDF delegation) → spec-driven equivalents. Add the
meta-tripwire: no inline `255, 255, 255` dot loop remains; all separator pixels go
through `render_separator`.

**Phase 2:** scroll default still a 2×2 dot; `separator_color` recolors it;
`separator = "*"` + font renders the glyph; geometry shifts correctly with a wider
separator (assert outgoing/incoming/bullet x at a mid-`t` frame on both
`Scroll.frame_at` and `_scroll_between`); a `rainbow` `separator_color` advances hue
across the derived frame on the bullet; validation rejects `separator_*` on each
non-scroll `TransitionConfig` home; hires `separator_font` without
`separator_font_size` errors; docs drift test passes.

**Phase 3:** `separator_size` resizes the dot (scroll) and the circle (ticker —
radius follows size, advance recomputed, smallsign BDF path unaffected); negative
`separator_size` rejected.

## Files touched (by phase)

- **P1:** create `src/led_ticker/separator.py`; `ticker.py` (consume renderer;
  remove `_draw_bullet`/`BULLET_*`; move circle helpers; `_CircleBufferMsg`
  delegates; `scroll_separator_width(spec)`); `transitions/effects.py` (`Scroll`
  consumes spec, top-level import from `separator.py`); migrate the two tripwire
  sites.
- **P2:** `config.py` (`TransitionConfig` separator fields); `app/factories.py`
  (`_resolve_separator_spec`, wire `_build_trans_obj` scoped to scroll, refactor
  `_resolve_buffer_msg`); `ticker.py`/`effects.py` variable-width geometry +
  `_scroll_between` spec source; `validate.py` (4-home rejection + font resolve);
  docs (`config-options.mdx`, `transitions/special.mdx`) + drift allow-list;
  `tests/test_separator.py` + scroll tests.
- **P3:** `config.py` (`separator_size` on both); `app/factories.py` + `separator.py`
  (size wiring); `validate.py` (size bound); docs; tests.

## Risks / sharp edges

- **Variable-width geometry (P2)** — every offset that assumed `2` must use
  `separator_width(spec)`; a wrong offset is a visible mid-scroll jump/overlap.
- **Derived animated frame inside a frozen transition (P2)** — novel behavior;
  must stay transition-local (R2) so it can't desync a real widget.
- **Circle advance default must stay byte-identical** — size 8 → advance 10, or the
  ticker `_scroll_side_by_side` layout shifts.
- **Two scroll consumers must stay in lockstep (R5)** — both route through the same
  renderer + width helper; the meta-tripwire enforces no inline dot remains.

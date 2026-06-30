# Configurable scroll-transition separator (unified separator rendering)

**Date:** 2026-06-30
**Branch:** `feat/configurable-scroll-separator`
**Type:** Feature (rendering + config) — with a behavior-preserving refactor

## Problem

The `scroll` transition draws a **hardcoded 2×2 white dot** between outgoing and
incoming content. It looks jarring on some displays, and unlike the ticker-mode
separator it can't be recolored, resized, or replaced. Worse, the same separator
visual is currently drawn in **three** places with three implementations:

- `ticker._CircleBufferMsg.draw` / `_draw_hires_circle` — the ticker-mode
  side-by-side separator (configurable: glyph/font/size? no — font/glyph/color
  yes, size no; defaults to a hi-res filled circle, `_CIRCLE_LOGICAL_RADIUS = 4`).
- `ticker._draw_bullet` / `_draw_scroll_frame` — the inter-widget `scroll` path
  (hardcoded 2×2 dot, `BULLET_WIDTH = 2`, `BULLET_COLOR = (255,255,255)`).
- `transitions/effects.py` `Scroll.frame_at` — the registered `scroll`
  transition (hardcoded 2×2 dot, inline duplicate).

Two related gaps fall out of this: the scroll bullet has **no** config at all,
and the ticker-mode circle has **no size knob** (you can't shrink the big dot).

## Goal

Make the scroll-transition separator **as configurable as the ticker-mode
separator** — color (incl. providers like rainbow/gradient), custom glyph,
font, and **size** — by unifying the rendering, while preserving every current
default appearance exactly.

Architectural shape (agreed during brainstorming):
- **Unify the renderer + the appearance type**, not the config homes.
- **Two config homes, scoped:** ticker mode keeps `SectionConfig.separator*`;
  the scroll transition gains the same family on `TransitionConfig`. (The
  `scroll` transition can run section-to-section, so its appearance belongs to
  the transition, not a section.)
- **Per-site defaults:** ticker mode defaults to the hi-res circle; the scroll
  transition defaults to the 2×2 dot. No existing config changes appearance.
- **One real `separator_size` knob** added to both sites (chosen option **b**),
  which also closes the ticker-mode "can't shrink the circle" gap.

Non-goals: changing any current default look; per-side-of-bullet asymmetric
gaps; animating the separator independently of the existing frame counter.

## Design

### 1. `SeparatorSpec` + renderer (new `src/led_ticker/separator.py`)

A small value type describing *how a separator looks* (not where it's drawn):

```python
@attrs.define
class SeparatorSpec:
    kind: str            # "dot" | "circle" | "glyph"
    color: ColorProvider # normalized provider (constant wraps in _ConstantColor)
    size: int            # nominal logical px: dot = square side; circle =
                         # diameter; glyph = font size (hires) / block scale (BDF)
    glyph: str = ""      # kind == "glyph": the character(s) to render
    font: Any = None     # kind == "glyph": resolved font (BDF/hires) or None
```

Renderer + width helper (the single source of separator pixels):

```python
def render_separator(canvas, x, spec) -> int:
    """Paint the separator mark at logical x; return its logical advance
    (width incl. padding). Routes hi-res kinds through unwrap_to_real /
    paint_hires on a ScaledCanvas; plain canvas falls back to dot/BDF glyph."""

def separator_width(spec) -> int:
    """Logical advance of the mark — used by scroll gap geometry."""
```

`render_separator` absorbs `_draw_hires_circle` + `_build_circle_offsets` (moved
from `ticker.py`), the dot paint (from `_draw_bullet`/`Scroll`), and the glyph
path (delegating to `text_render`/`TickerMessage`-style BDF/hires draw). It reads
the color via `spec.color.color_for(frame, 0, 1)` so providers animate.

Circle geometry becomes size-driven: `radius = size // 2`; the logical advance is
`pad + size + pad` (today's `_CIRCLE_LOGICAL_ADVANCE = 10` becomes
`2*pad + size` with `size` defaulting to `8` → unchanged). Dot advance is
`gap-driven` as today.

### 2. Config — two homes, same field family

- `TransitionConfig` gains: `separator`, `separator_color`, `separator_font`,
  `separator_font_size`, `separator_size` (all default `None`). Honored only by
  the `scroll` transition.
- `SectionConfig` gains: `separator_size` (default `None`). Applies to the
  ticker-mode separator (sits beside the existing `separator*` fields).

All defaults `None` ⇒ today's appearance (ticker circle ø8 / scroll dot 2×2).

### 3. Shared resolver (`app/factories.py`)

A single `_resolve_separator_spec(*, separator, separator_color, separator_font,
separator_font_size, separator_size, default_kind) -> SeparatorSpec` that both
sites call. Branching mirrors today's `_resolve_buffer_msg`:

- all separator/font/size/color unset → `default_kind` spec, white, default size.
- color-only → `default_kind` recolored (circle stays circle on bigsign).
- glyph/font set → `kind = "glyph"` with the char + resolved font.
- `separator_size` overrides `size` for any kind.

Call sites:
- Ticker: `_resolve_buffer_msg` builds a spec with `default_kind="circle"` and
  wraps it in the separator widget (a thin `TickerMessage`/`_CircleBufferMsg`
  whose `draw` delegates to `render_separator`), so the ticker rotation still
  gets a Widget.
- Scroll: `_build_trans_obj` builds a spec with `default_kind="dot"` from the
  `TransitionConfig` fields and passes it into the `Scroll` constructor.

### 4. Consume the spec in both scroll paths

- `transitions/effects.py` `Scroll.__init__(spec=...)`; `frame_at` calls
  `render_separator(canvas, bullet_x, self._spec)` instead of the inline dot, and
  uses `separator_width(self._spec)` for `total_travel`/positioning.
- `ticker.py` `_draw_scroll_frame` / `scroll_separator_width` take the spec and
  call `render_separator` / `separator_width`. `_draw_bullet`,
  `BULLET_WIDTH`/`BULLET_COLOR` are removed (folded into the dot kind).

The variable-width separator is the main geometry change: `total_travel`,
`bullet_x`, `incoming_pos`, and the black-out region must use
`separator_width(spec)` rather than the constant `2`.

### 5. Validation (`validate.py`)

- Extend the rule-26-style check: `separator_*` on a transition are honored only
  by `type = "scroll"`; reject (warn) on other transition types, mirroring the
  existing section-mode rejection.
- Resolve `separator_font` for scroll transitions (mirror `_check_separator_fonts`),
  surfacing a clear error on an unknown font / missing `separator_font_size` for
  a hires font.
- `separator_size` must be a positive int (bounded sanity check).

## Back-compat

Purely additive fields; no migration. Every existing config renders identically
because all new fields default `None` and the per-site defaults reproduce the
current circle (ø8) and dot (2×2). The existing ticker-separator tripwires are
the guardrail that the refactor is behavior-preserving.

## Testing

- **Refactor safety:** existing ticker-separator tests stay green (default circle
  unchanged on bigsign; BDF `•` on smallsign).
- **Scroll separator (new):** default is still a 2×2 dot; `separator_color`
  recolors it; `separator = "*"` + font renders the glyph; `separator_size`
  resizes the dot; the gap geometry shifts correctly with a wider separator
  (assert outgoing/incoming/bullet x at a mid-`t` frame).
- **Provider animation:** a `rainbow` `separator_color` advances hue across frames
  on the scroll bullet.
- **Ticker size knob:** `separator_size` shrinks/grows the hi-res circle (radius
  follows size; advance recomputed) and the smallsign BDF path is unaffected.
- **Validation:** `separator_*` on a non-scroll transition is rejected; a hires
  `separator_font` without `separator_font_size` errors; negative `separator_size`
  rejected.
- **Tripwire:** the three former draw sites no longer contain a hardcoded
  `255, 255, 255` dot loop — all separator pixels go through `render_separator`.

## Files touched

- Create: `src/led_ticker/separator.py` (`SeparatorSpec`, `render_separator`,
  `separator_width`, circle helpers moved from `ticker.py`)
- `src/led_ticker/ticker.py` (consume the renderer; remove `_draw_bullet` /
  `BULLET_*`; `_CircleBufferMsg`/`DEFAULT_BUFFER_MSG` delegate to it;
  `scroll_separator_width` takes a spec)
- `src/led_ticker/transitions/effects.py` (`Scroll` consumes the spec)
- `src/led_ticker/config.py` (`TransitionConfig` + `SectionConfig` fields)
- `src/led_ticker/app/factories.py` (`_resolve_separator_spec`; wire ticker +
  `_build_trans_obj`)
- `src/led_ticker/validate.py` (transition separator validation + size bounds)
- `tests/` (new `test_separator.py` + extensions to scroll-transition and
  ticker-separator tests)
- Docs (follow-up, not blocking): `transitions/special`, `concepts/sections-and-modes`,
  `reference/config-options`.

## Risks / sharp edges

- **Variable separator width vs scroll geometry** — the positioning math assumes
  a constant 2px; threading `separator_width(spec)` through every offset is the
  load-bearing change. A wrong offset shows as a visible jump/overlap mid-scroll.
- **Circle advance** — `_CIRCLE_LOGICAL_ADVANCE` is currently a constant baked
  into `_scroll_side_by_side` layout; making it size-driven must keep the default
  (size 8 → advance 10) byte-identical or the ticker layout shifts.
- **Two scroll paths must stay in lockstep** — `Scroll.frame_at` and
  `ticker._draw_scroll_frame` should both route through the same renderer + width
  helper so they can't drift again (a tripwire asserts no inline dot remains).

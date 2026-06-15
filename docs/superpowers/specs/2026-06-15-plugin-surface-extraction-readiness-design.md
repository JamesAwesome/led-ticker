# Extraction-readiness plugin-API audit (P3) — Design

**Date:** 2026-06-15
**Status:** Approved (brainstorm with James)

## Context

P3 is the third and final prerequisite from the plugin-extraction review
(`docs/superpowers/reviews/2026-06-15-plugin-extraction-recommendation.html`),
after P1 (migration hints, #214/#216) and P2 (hi-res transition API, #218).

The review labeled P3 "trivial public-API adds" — export `format_clock` and
`draw_text_per_char`. An audit of every planned-extraction candidate's
`led_ticker.*` imports against the public `led_ticker.plugin.__all__` surface
found **more** internal reaches than those two. P3's real goal: make the public
surface complete enough that the planned extractions (`calendar`, `weather`,
`rss_feed`, the arcade sprite transitions) need **zero re-vendoring** of core
internals — and lock that with a tripwire so the surface can't silently rot.

This work is purely additive surface + one behavior-identical dogfood swap + a
test. It does NOT extract anything.

## Audit results (verified against `plugin.__all__`)

Per candidate, the names imported from `led_ticker.*` that are NOT already on
the public surface:

| Candidate | Internal reaches | Resolution |
|---|---|---|
| `widgets/calendar.py` | `format_clock`, `draw_with_emoji`, `count_text_chars`, `_ConstantColor`, color constants (`DEFAULT_COLOR`), `register` | export first three; `_ConstantColor`→`as_color_provider` (dogfood); constants via public `colors` module; `register`→`api.widget` on extraction |
| `widgets/weather.py` | `draw_text_per_char`, `_ConstantColor`, constants (`DEFAULT_COLOR`,`RGB_WHITE`), `register`, `weather_icons._match_condition` | export `draw_text_per_char`; `_ConstantColor`→`as_color_provider`; constants via `colors`; `register`→`api.widget`; `weather_icons` moves with weather |
| `widgets/weather_icons.py` | (only `PixelData`, public) | none — moves with weather |
| `widgets/rss_feed.py` | constants (`DEFAULT_COLOR`,`GREEN`,`RED`), `register` | constants via `colors`; `register`→`api.widget` |
| `transitions/nyancat.py` | `ColorTuple`, `HIRES_REGISTRY`, `register_transition` | export `ColorTuple`; `HIRES_REGISTRY` is built-in dispatch only (extracted arcade uses the P2 `HiresSpec`+`is_scaled` pattern); `register_transition`→`api.transition` |
| `transitions/{pokeball,pacman,sailor_moon}.py` | `HIRES_REGISTRY` (pokeball only), `register_transition` | as above |

Non-gaps confirmed: the color constants `DEFAULT_COLOR`/`RGB_WHITE`/`GREEN`/`RED`
are all attributes of the already-public `colors` module (a plugin uses
`from led_ticker.plugin import colors; colors.RED`).

## Changes

### 1. Public factory — `color_providers.py`

```python
def as_color_provider(color: Color) -> ColorProvider:
    """Wrap a constant Color as a uniform (non-animated) ColorProvider.

    The public way to get a constant-color provider — e.g. for a widget's
    default font color. `_ConstantColor` stays private; this is the
    supported surface.
    """
    return _ConstantColor(color)
```

### 2. Public surface — `plugin.py` (`__all__` + imports)

Add: `format_clock` (from `widgets.clock`), `draw_text_per_char` (from
`text_render`), `draw_with_emoji` + `count_text_chars` (from `pixel_emoji`),
`ColorTuple` (from `_types`), `as_color_provider` (from `color_providers`).
Six new names. `_ConstantColor` and `HIRES_REGISTRY` stay internal.

### 3. Dogfood the factory in core

Repoint `widgets/calendar.py` and `widgets/weather.py` from constructing
`_ConstantColor(...)` directly to `as_color_provider(...)` (importing
`as_color_provider` from `color_providers`, NOT the plugin facade — core code
imports real modules). Behavior-identical (the factory only calls
`_ConstantColor`). Removes the private reach and exercises the factory through
the existing calendar/weather suites. `clock.py` also uses `_ConstantColor` but
stays in core (not an extraction candidate) — leave it, OR convert for
consistency (optional; behavior-identical either way).

### 4. Extraction-readiness tripwire — new `tests/test_plugin_extraction_readiness.py`

The centerpiece. AST-scans each candidate module's `led_ticker.*` imports and
asserts every imported name is one of:
- **public** — in `plugin.__all__`, or an attribute of the public `colors`
  module;
- **allowlisted** with a documented reason, per candidate:
  - `register` / `register_transition` — replaced by `api.widget` /
    `api.transition` when the plugin registers;
  - a sibling module that moves with the same plugin (e.g. `weather` ↔
    `weather_icons`; a candidate's own intra-module names);
  - `HIRES_REGISTRY` (nyancat/pokeball) — built-in dispatch only; the extracted
    arcade transition uses the P2 `HiresSpec` + `is_scaled` pattern.

Anything else is a **GAP** → fail, naming the module + symbol. After P3 the GAP
set is empty. The allowlist is a small, per-candidate dict whose values are the
*reason* each internal name is acceptable — a new internal reach added later
trips the wire, forcing either a new export or a justified allowlist entry. The
allowlist is the audit, made executable.

### 5. Drift guard + docs

`tests/test_docs_plugin_api_drift.py` pins `__all__` against
`docs/site/.../plugins/api-reference.mdx` — add rows for all six new symbols.
Add a short authoring note (the plugins extending/authoring docs): rich-text
plugin widgets use `draw_with_emoji` / `count_text_chars`; constant colors via
`as_color_provider`; the named color constants via the public `colors` module.

## Testing

- **Readiness tripwire** (new): GAP set empty for all candidates; a synthetic
  "inject a fake unknown internal import" check proves the test actually fails
  on a gap (non-vacuous) — exercised by asserting a deliberately-bogus name in
  a fixture string is classified GAP.
- **Factory**: `as_color_provider(c)` returns a `ColorProvider` whose
  `color_for(...)` yields `c` (uniform); importable from `led_ticker.plugin`.
- **Public imports**: `from led_ticker.plugin import format_clock,
  draw_text_per_char, draw_with_emoji, count_text_chars, ColorTuple,
  as_color_provider` all resolve.
- **Dogfood regression**: existing `tests/test_widgets/test_calendar.py` and
  `test_weather.py` stay green (behavior-identical swap).
- **Drift**: `test_docs_plugin_api_drift.py` green after the api-reference rows.

## Out of scope

- Any actual extraction (calendar / weather / rss / arcade) — P3 unblocks them.
- Rewriting the in-core arcade transitions to the `HiresSpec` pattern — that
  happens in the arcade-extraction PR; here their `HIRES_REGISTRY` reach is an
  allowlisted, P2-resolved case.
- The custom per-widget field-coercion plugin surface and the plugin-registry /
  `led-ticker plugin install` project (separate threads).

## Delivery

Feature branch + PR (worktree `feat/plugin-surface-extraction-readiness`).
Staged commits: factory + exports → dogfood swap → readiness tripwire →
drift/docs.

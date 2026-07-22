# Pixel-font-aware auto-sizing

**Date:** 2026-07-21
**Status:** approved (brainstorm with James)
**Relation:** follow-on to the Spleen pixel fonts (core v4.25.0). Those ship
crisp only at native sizes or integer multiples; this makes DYNAMICALLY-sized
text (a plugin fitting text to a shape) land on that grid too.

## Problem

flair's lottery widget auto-sizes each ball's font to fit the word:
`auto_font_size(word, diameter_px, font_name, scale)` searches sizes from
`int(diameter_px * 0.45)` down to 8 and returns the largest whose rendered
width fits the ball chord — a CONTINUOUS search over every integer. For an
outline font (Inter, the default) that's correct. For a **pixel font**
(Spleen) it lands on off-grid sizes (measured 10–28 px for the halal balls,
mostly NOT multiples of 12/16/32), so Spleen renders antialiased/blurry —
defeating the entire reason to use a pixel font. Any future plugin that
fits pixel-font text to a shape hits the same wall.

## Design

Three units, shipped in dependency order (core → flair → config).

### 1. Core — public `pixel_native_size` helper

Expose the existing private `_PIXEL_NATIVE` registry
(`fonts/hires_loader.py`) through a public function, re-exported on
`led_ticker.plugin` (the ONLY module plugins import):

```python
def pixel_native_size(name: str) -> int | None:
    """Native pixel height of a bundled pixel font (`spleen-6x12` -> 12),
    or None if `name` isn't a pixel-native font. Outline fonts (Inter,
    DejaVu, user TTFs) return None — they render at any size, so callers
    leave them on their existing path. Callers that compute a size
    dynamically snap it onto the grid (native multiples) before resolving,
    so pixel-font text stays crisp."""
    return _PIXEL_NATIVE.get(name)
```

- Lives in `hires_loader.py` beside `_PIXEL_NATIVE`.
- Added to `led_ticker.plugin`'s imports and `__all__`.
- The public contract is just "name -> native px or None". The snapping
  arithmetic is the caller's (keeps the API minimal; the registry stays the
  single source of truth). `API_VERSION` need not bump — this is an additive
  re-export, not a breaking change; but it does widen the plugin surface, so
  the plugin API reference (drift-guarded by
  `tests/test_docs_plugin_api_drift.py`) gets the new name.

### 2. Flair — grid-aware `auto_font_size`

In `led_ticker_flair.flair.lottery.auto_font_size`, when
`pixel_native_size(font_name)` is not None, restrict the candidate sizes to
**native multiples** instead of every integer:

- Outline font (`pixel_native_size(name) is None`) → unchanged continuous
  search (from `int(diameter_px * _MAX_FONT_FACTOR)` down to `_MIN_FONT_SIZE`).
- Pixel font → iterate multiples `k * native` for `k` from the largest with
  `k*native <= int(diameter_px * _MAX_FONT_FACTOR)` down to `k = 1`
  (`native`), returning the first (largest) whose rendered width fits the
  chord (`diameter_px * _CHORD_FACTOR`). If even `native` doesn't fit, return
  `0` — the existing "doesn't fit" sentinel the widget already handles
  (truncate/fallback). Result: a pixel-font ball always resolves at a crisp
  on-grid size (computed-14 → 12; computed-25 → 24).

The fit-measurement, threshold (`_FACE_THRESHOLD`), and `scale`-handling all
stay exactly as they are — only the set of candidate sizes narrows. Draw and
measure already resolve at the same size (the widget's existing contract), so
no parity risk. Bumps the plugin's core floor to the version that ships
`pixel_native_size`.

### 3. Config — the switch

Set `font = "spleen-6x12"` on the halal config's four `flair.lottery`
widgets (`config/config.halal-cart.example.toml`). Crisp only once flair #2
is released + installed, so this lands LAST. The already-made longboi
additions (stocks/baseball/flight/transitions) are independent and ride in
the core PR.

## Architecture / boundaries

- `pixel_native_size` is a pure lookup — no font loading, no I/O. Depends
  only on the module-level `_PIXEL_NATIVE` dict.
- `auto_font_size` keeps its signature (`word, diameter_px, font_name, scale
  -> int`) and its two documented contracts (largest-that-fits; `0` =
  doesn't fit). The change is internal: candidate-size generation.
- Config is data — no code dependency beyond the widget accepting a `font`.

## Sequencing (dependency chain)

1. **Core PR:** `pixel_native_size` + tests + plugin-API-reference entry +
   the longboi config additions. Merge → release core minor.
2. **Flair PR:** grid-aware `auto_font_size` + tests + core-floor bump.
   Merge → release flair minor.
3. **Config:** halal `flair.lottery` → `spleen-6x12` (can be folded into the
   core PR's config changes OR a tiny follow-up; it renders soft until flair
   ships, acceptable for an example config, but PREFER landing it after the
   flair release so the committed example is crisp on current plugins).

## Tests

- **Core:** `pixel_native_size` returns 12/16/32 for the three Spleen names,
  `None` for `Inter-Bold`/`Inter-Regular`/an unknown name; present in
  `led_ticker.plugin.__all__` and importable from it. Docs-drift test stays
  green.
- **Flair:** `auto_font_size` for a pixel font returns only native multiples
  (parametrized across diameters — assert `result % native == 0 or result ==
  0`); returns `0` when even native overflows a tiny ball; outline-font
  behavior byte-identical to today (a pinned before/after on `Inter-Bold`).
  Exact-size assertions are fine here (integer grid, deterministic) — the
  Spleen exception to the no-exact-hires-advance rule.
- **Visual gate (James):** render the halal lottery in `spleen-6x12` and
  confirm the ball faces are crisp (on-grid) vs the current soft off-grid.

## Non-goals

- No snapping in core `resolve_font` itself (stays permissive; validate rule
  69 already warns on static off-grid config sizes — this is the DYNAMIC
  path). No runtime size-mutation of user-specified `font_size`.
- No change to the outline-font path anywhere.
- No new pixel fonts; no auto-sizing added to other widgets (lottery is the
  only auto-sizer today; the helper is available for future ones).
- The API_VERSION does not bump (additive re-export).

## Release shape

Core minor (new public API). Flair minor (new capability, consumes the API).
Config is content (no release of its own).

---

## Addendum (2026-07-21) — the lottery must ACCEPT a config font first

**Discovered mid-implementation:** the original design assumed setting
`font = "spleen-6x12"` on a `flair.lottery` widget was a plain config change.
It is not. Two core/flair mechanisms block it:

1. Core's `app/factories._resolve_fonts` eagerly coerces EVERY widget's
   `font` name → a `Font` OBJECT at config-load, and raises
   "HiresFont requires font_size" for a hires name without `font_size`.
2. The lottery's `_font_is_a_name` validator then REJECTS a config `font`
   outright ("the 'font' config key is reserved by the core loader … ball
   faces are too small for other faces to matter") — it wants only its
   internal `Inter-Bold` default, which it re-resolves at auto-computed
   sizes.

So the grid-aware `auto_font_size` (§2) is necessary but not sufficient:
there is no way to select a pixel font on the lottery via config. James's
decision (2026-07-21): **do the full rework** so the lottery accepts a
config-selected font that it self-sizes.

### Core — `RESOLVES_OWN_FONT` opt-out

A widget class may set the class attribute `RESOLVES_OWN_FONT = True`
(default `False`). When `_resolve_fonts` sees it, the widget's `font` field
is left as the **raw name string**: no resolve-to-`Font`, and NO
"requires font_size" check (the widget sizes the font itself). `font_size`/
`font_threshold` for such a widget are also left untouched (passed through
only if the class declares those attrs fields). Every other widget is
unaffected (marker absent/`False` → today's behavior exactly). This is the
minimal seam and the natural companion to `pixel_native_size` — core already
owns the font-coercion policy; this lets a self-sizing widget opt out of it.
Documented on the plugin surface (a note in the API reference; the marker is
read off the widget class, no `api.*` call).

### Flair — accept the name

Set `RESOLVES_OWN_FONT = True` on the lottery widget and relax
`_font_is_a_name`: now that core leaves `font` a string, the validator
accepts a valid font *name* (still erroring on an unknown font, and keeping
the lottery's existing default when `font` is omitted). Combined with the
grid-aware `auto_font_size` (§2), a config `font = "spleen-6x12"` now loads
AND renders crisp.

### Sequencing (revised)

The original core PR (helper `pixel_native_size` + longboi config) already
SHIPPED as **core v4.26.0**. The rework adds:

1. **Core PR:** `RESOLVES_OWN_FONT` opt-out + tests + API-reference note.
   Merge → release **core v4.27.0**.
2. **Flair PR:** the grid-aware `auto_font_size` (from §2) + the
   `RESOLVES_OWN_FONT` marker + relaxed validator + core-floor bump to
   `>=4.27` + tests + visual gate. Merge → release flair minor.
3. **Config:** halal lottery → `spleen-6x12`. Merge.

### Off-ramp

Ball faces are ~12–24px. If the visual gate (flair PR) shows Spleen isn't a
clear improvement over auto-sized Inter-Bold at that size, stop before the
config switch — the core opt-out + grid-snap remain as correct latent
capability, no harm.

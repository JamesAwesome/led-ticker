# Hi-res sprites for plugin transitions (P2) — Design

**Date:** 2026-06-15
**Status:** Approved (brainstorm with James)

## Context

P2 from the plugin-extraction review
(`docs/superpowers/reviews/2026-06-15-plugin-extraction-recommendation.html`):
the hi-res sprite-transition path is **unreachable by plugins**, so the
`nyancat`/`pokeball`-style sprite transitions can't be extracted to a plugin
(`led-ticker-arcade`) without silently regressing to lo-res on the bigsign.

The cause is a back-edge: `render_hires_frame(..., registry_name)` looks the
sprite up *inside itself* via the core-internal `HIRES_REGISTRY[registry_name]`
dict, and the transition class gates on `self._registry_name in HIRES_REGISTRY`.
Neither `render_hires_frame`, `HiresSpec`, nor `HIRES_REGISTRY` is on the public
`led_ticker.plugin` surface, so an out-of-tree transition has no way to supply
its own sprite to the renderer.

This work removes the back-edge and exposes the hi-res render path to plugins.
It does **not** extract the arcade pack — it unblocks that future PR.

## Decision (from brainstorm)

**Approach (b): pass a `HiresSpec` to `render_hires_frame`.** Chosen over (a) an
`api.hires_transition_sprite(name, spec)` registration surface because (b)
removes the back-edge entirely (rather than blessing it as public API), adds no
second global mutable surface, has no name-pairing footgun, and is lower-risk to
core (built-ins change ~one line each). `HIRES_REGISTRY` survives only as the
built-ins' private catalog.

## Current shape (verified)

- `HiresSpec` — `@dataclass(frozen=True)` in `transitions/_hires_registry.py`:
  `sprite_path: Path`, `flip_horizontal: bool`, `trail: str = "none"`
  (`trail` ∈ {`"none"`, `"black"`, `"rainbow"}`).
- `HIRES_REGISTRY: dict[str, HiresSpec]` — keyed by transition name
  (`nyancat`, `nyancat_reverse`, `pokeball`, `pokeball_reverse`).
- `load_hires(transition_name: str) -> HiresFrames | None` — `@functools.cache`'d
  on the name; does `HIRES_REGISTRY.get(transition_name)` then `_decode(spec)`.
- `render_hires_frame(t, canvas, outgoing, incoming, registry_name, **kwargs)` —
  calls `sprite = load_hires(registry_name)`. `registry_name` is used **only**
  for that lookup; `trail`/`flip` ride on the decoded `HiresFrames`.
- Dispatch gate (`nyancat.py`, `pokeball.py`):
  `isinstance(canvas, ScaledCanvas) and self._registry_name in HIRES_REGISTRY`
  → `render_hires_frame(..., self._registry_name, **kwargs)`.
- Already public in `plugin.__all__`: `ScaledCanvas`, `SNAP_THRESHOLD`,
  `snap_reset`, `paint_hires`, `unwrap_to_real`, `Transition`, `HiResEmoji`,
  `PixelData`. NOT public: `HiresSpec`, `render_hires_frame`, `HIRES_REGISTRY`.

## Changes

### 1. `transitions/_hires_loader.py` — render path becomes a pure function of a spec
- `load_hires(spec: HiresSpec) -> HiresFrames` — change the parameter from
  `transition_name: str` to `spec: HiresSpec`. `@functools.cache` now keys on the
  frozen, hashable `HiresSpec` (all fields — `Path`/`bool`/`str` — are hashable).
  Body becomes `return _decode(spec)`: no registry lookup, no `None` path (the
  caller owns resolution).
- `render_hires_frame(t, canvas, outgoing, incoming, spec: HiresSpec, **kwargs)` —
  change `registry_name` → `spec`; internally `sprite = load_hires(spec)`. No
  other logic changes (`registry_name` had no other use).

### 2. `transitions/nyancat.py` / `pokeball.py` — resolve-then-pass
- `_frame_at_hires`: `spec = HIRES_REGISTRY[self._registry_name]` then
  `render_hires_frame(t, canvas, outgoing, incoming, spec, **kwargs)`.
- Dispatch gate and `_registry_name` unchanged — built-ins keep `HIRES_REGISTRY`
  as their catalog. Behavior is byte-for-byte identical.

### 3. `plugin.py` — public surface
- Import and add `HiresSpec` and `render_hires_frame` to `__all__`.
- `HIRES_REGISTRY` stays internal.

### 4. Docs + drift guard
- `tests/test_docs_plugin_api_drift.py` pins `__all__` against the api-reference
  docs — so add the two new exports to
  `docs/site/src/content/docs/plugins/api-reference.mdx`.
- Add an authoring example (a hi-res plugin transition holding its own `HiresSpec`
  + bundled sprite, with the `ScaledCanvas` gate and a lo-res fallback) to the
  plugins docs, per `docs/DOCS-STYLE.md`.

## Testing

- **Regression:** existing `tests/test_nyancat.py` / `tests/test_pokeball.py`
  hi-res-on-bigsign + lo-res-on-small tests stay green (the refactor preserves
  built-in behavior — same spec resolved, just at the call site).
- **The P2 proof (key test):** simulate an out-of-tree plugin — a tiny transition
  class that holds its own `HiresSpec` pointing at a sprite **generated at test
  time with PIL into `tmp_path`** (a 2-frame gif). The spec's name is NOT in
  `HIRES_REGISTRY`. Assert that on a `ScaledCanvas` `render_hires_frame(..., spec)`
  paints sprite (non-black) pixels — i.e. the hi-res path fires for a sprite the
  core registry never knew about. Also assert `from led_ticker.plugin import
  HiresSpec, render_hires_frame` works.
- **Cache:** `load_hires(spec)` memoizes on the spec (same spec → same object;
  a spec differing only in `flip_horizontal` → a distinct entry, matching today's
  nyancat vs nyancat_reverse).
- The plan greps to confirm no caller other than the two sprite families used the
  old `registry_name` signature.

## Out of scope

- Extracting the arcade sprite pack (separate future PR — this unblocks it).
- Plugin lo-res fallbacks (a plugin writes its own lo-res path, like `nyancat`
  does; P2 only concerns the hi-res path).
- A bespoke (non-horizontal-traversal) hi-res effect API — plugins already have
  `paint_hires` / `unwrap_to_real` / `ScaledCanvas` for that.
- The `api.hires_transition_sprite` registration surface (approach a — rejected).

## Delivery

Feature branch + PR (worktree `feat/hires-transition-plugin-api`). Staged commits
per the project review pattern: loader refactor + built-in call sites (+ their
regression tests) → public export + drift/docs → plugin-simulation proof test →
authoring docs example.

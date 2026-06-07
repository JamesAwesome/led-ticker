# Plugin public-surface hardening (A1–A4) — design

**Date:** 2026-06-07
**Status:** Approved design, pending implementation plan
**Repos:** led-ticker (the surface) + led-ticker-baseball (the only migrating consumer)
**Origin:** the two independent review panels on the baseball extraction flagged four `led_ticker.plugin` API smells. Captured in memory `project_plugin_surface_fastfollows`. This is the first of the deferred baseball fast-follows to be specced (the rest — B–G — are a separate batched effort).

## Goal

Harden the public `led_ticker.plugin` surface so plugins stop (a) subclassing a `_`-private base, (b) copying core internals that encode tested invariants, (c) coupling to an internal wrapper type by `isinstance`, and (d) choosing between two overlapping text-draw entry points. Do it as a **clean break** — no deprecation shims — and migrate the two first-party consumers in lockstep.

## Why clean break is justified

led-ticker has never been publicly released, and the **only** two consumers of the plugin surface are first-party (led-ticker-pool, led-ticker-baseball). pool uses **none** of the four touched symbols; baseball uses three of them. So there is no external contract to preserve and exactly one repo to migrate. Adding deprecation aliases would be pre-1.0 cruft no real consumer needs.

## The four changes

### A1 — `FrameAwareBase` becomes a real public class (not an alias)

Today: `led_ticker.plugin` does `from led_ticker.widgets._frame_aware import _FrameAware as FrameAwareBase`. The public name aliases a `_`-private class whose `_`-named internals (`_effect_frames`, `_frame_count`, `advance_frame`, `pause_frame`, `frame_for`, `restart_on_visit`) are the de-facto contract a plugin subclass inherits — unlike the sibling `ColorProviderBase` / `BorderEffectBase`, which are real public base classes.

Change: **rename** `_FrameAware` → `FrameAwareBase` in `src/led_ticker/widgets/_frame_aware.py`; update its ~8 core inheritors (`widgets/message.py` ×2, `widgets/two_row.py`, `widgets/weather.py`, `widgets/crypto/{coinbase,coingecko,etherscan}.py`, `widgets/_image_base.py`); export it directly from `led_ticker.plugin` (drop the `as`-alias). Document the stable subclass contract (which methods/attrs a plugin may rely on) in the api-reference.

baseball impact: **none.** `scores.py` already imports `FrameAwareBase` from `led_ticker.plugin` — the public name is unchanged. pool: unaffected.

### A2 — public `snap_reset` + `normalize_bg`

Today: the bg-aware transition-snap behavior (a CLAUDE.md load-bearing invariant — `TestHiresSnapRespectsIncomingBg`) lives in `_`-private `_hires_loader._snap_reset` (which calls `transitions._normalize_bg`). A third-party transition that snaps-to-incoming cannot reproduce it without copying internals — which baseball did (`transition.py` carries local `_snap_reset` + `_normalize_bg` copies that WILL drift from core).

Change: promote both to the public surface as `snap_reset(canvas, incoming_bg_color)` and `normalize_bg(c) -> tuple[int,int,int] | None`. Keep the core call sites working (the public names can be the real functions; internal callers import them from their current home or the surface). Add to `__all__` + api-reference.

baseball impact: drop the two local copies, import `snap_reset`/`normalize_bg` from `led_ticker.plugin`. Behavior is byte-identical (the copies were verbatim), so the pixel-identical transition tests stay green.

### A3 — `is_scaled(canvas)` predicate

Today: a plugin that needs the bigsign hi-res path checks `isinstance(canvas, ScaledCanvas)` (baseball does, 2 sites in `transition.py`). That couples plugins to the wrapper's concrete type, blocking core from ever changing it.

Change: add `is_scaled(canvas) -> bool` to the surface (returns whether the canvas is a scaled wrapper — implementation can stay `isinstance(canvas, ScaledCanvas)` internally, but plugins call the predicate). `ScaledCanvas` stays exported (still needed for typing/`unwrap_to_real`), but the documented gate becomes `is_scaled`.

baseball impact: replace the 2 `isinstance(canvas, ScaledCanvas)` checks with `is_scaled(canvas)`.

### A4 — canonicalize text drawing; remove `draw_with_emoji` from the surface

Today: two overlapping public text-draw entry points — `draw_text(canvas, font, text, x, y, color) -> int` (returns the absolute next-x, ergonomic, for overlays/chaining) and `draw_with_emoji(canvas, font, cursor_pos, y, color, text) -> int` (returns the advance width, the low-level primitive). `measure_width(font, text)` already exists for pure width math.

Change: canonicalize on **`draw_text` (draw + next-x) + `measure_width` (width only)**. **Remove `draw_with_emoji` from the public surface** — it stays an internal that `draw_text` wraps. Drop it from `__all__` + api-reference.

baseball impact: migrate the ~10 `draw_with_emoji` call sites in `scores.py` to `draw_text` (`x = draw_text(canvas, font, text, x, y, color)` chains on next-x — strictly nicer than manual advance addition); where a site needs width without drawing, use `measure_width`. The file is NOT split here (that's chore B) — calls migrate in place.

## Cross-repo sequencing (no red CI at any point)

A4's removal of `draw_with_emoji` is the only breaking change; baseball uses it today. Order the three PRs so nothing is ever broken:

1. **Core PR #1 (additive + rename):** A1 (rename `_FrameAware`→`FrameAwareBase`, drop alias), A2 (add `snap_reset`/`normalize_bg`), A3 (add `is_scaled`). All safe — the rename preserves the public name `FrameAwareBase`; A2/A3 are additive; `draw_with_emoji` still present. Merge.
2. **Baseball PR (adopt new forms):** drop the `_snap_reset`/`_normalize_bg` copies → import public; `isinstance(ScaledCanvas)` → `is_scaled`; migrate the `draw_with_emoji` sites → `draw_text`/`measure_width`. After this, baseball no longer references `draw_with_emoji`. Merge.
3. **Core PR #2 (removal):** remove `draw_with_emoji` from the public surface (no consumer remains). Merge.

This ordering keeps every CI run green: baseball always builds against a core that still has what it needs. (Alternative considered — collapse A4's removal into PR #1 and accept baseball CI red between merges — rejected: the staged order is barely more work and never breaks.)

## Testing

**Core:**
- `tests/test_plugin_surface.py`: assert `FrameAwareBase`, `snap_reset`, `normalize_bg`, `is_scaled` are exported (PR #1); update the FrameAwareBase-identity test to the renamed class; assert `draw_with_emoji` is **absent** from `__all__` (PR #2).
- `tests/test_docs_plugin_api_drift.py` / `api-reference.mdx`: add the new symbols (PR #1), remove `draw_with_emoji` (PR #2).
- Full suite green after the ~8-inheritor rename (the rename is mechanical; behavior unchanged).
- `prettier`/`astro check` on the api-reference edits.

**Baseball:**
- All 232 tests green after migration.
- The AST import-purity tripwire (`tests/test_import_purity.py`) still passes — every import is still from `led_ticker.plugin`.
- The pixel-identical hi-res transition behavior is preserved (snap_reset swap + is_scaled are behavior-neutral substitutions).

## Out of scope

- The other deferred chores (B split scores.py, C live-poll, D deploy note, E pool AST test, F color=random verify, G gif re-render) — a separate batched effort.
- **B specifically:** A4 edits the draw call sites in `scores.py`, but does NOT split the file — calls migrate in place.
- Any change to pool (it uses none of the four symbols).
- Wiring or deleting the dead live-poll code (that's chore C).

## Success criteria

- `led_ticker.plugin` exports `FrameAwareBase` (real class), `snap_reset`, `normalize_bg`, `is_scaled`; no longer exports `draw_with_emoji`.
- No plugin subclasses a `_`-private class, copies a core internal, or `isinstance`-checks `ScaledCanvas`.
- baseball builds + all tests pass against the hardened surface; pool untouched; every CI run across the three PRs is green.

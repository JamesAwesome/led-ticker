# Spike: reduce the `tools/gif_plan` ↔ engine hand-mirror burden

**Date:** 2026-05-16
**Status:** Spike complete — recommendation: **Option A (extract-and-share leaf), GO**
**Branch:** `spike/gif-plan-engine-coupling` (contains the proven POC)

## Problem

`tools/gif_plan/` re-derives engine timing/layout facts by hand. The
source-of-truth coupling is *by comment* ("Mirrors src/led_ticker/…"),
not by code, so it drifts whenever the engine changes. PR #66 needed
four review rounds; each found a transcription bug, including a
**critical** one (round 3): the planner re-derived config-relative path
resolution and resolved against the cwd instead of the config dir
(`app.py:652-659`), silently mispredicting every gif demo.

## Hypothesis

The duplicated surface splits into:

- **Pure facts** (constants, one pure function) — shareable if they can
  be imported without dragging the engine's heavy world.
- **Emergent durations** (per-tick `play()` / `_swap_and_scroll`
  outcomes) — genuinely not shareable; stay reimplemented, pinned by
  the dogfood tripwire.

## Q1 — Import-cost evidence (measured, this branch)

`import led_ticker` self-stubs `rgbmatrix` via `_compat` → it does **not**
force `PYTHONPATH=tests/stubs`. Per-module cost (clean env, no stub
path), `+mods` = modules added to `sys.modules`:

| Module | Time | +mods | Heavy deps pulled |
|---|---|---|---|
| `led_ticker._compat` | 5ms | +25 | — |
| `led_ticker.config` | 12ms | +58 | **none** |
| `led_ticker.fonts` | ~225ms | +97 | PIL (+ BDF file I/O at import) |
| `led_ticker.widgets._image_base` | ~300ms–1.2s | **+363** | **PIL, aiohttp, asyncio** |
| `led_ticker.app` | ~325ms | **+383** | **PIL, aiohttp, asyncio** |

So the constants the planner mirrors (`AUTO_TEXT_ALIGN_FOR_IMAGE`,
`MIN_SCROLL_SPEED_MS`, `TEXT_EDGE_PADDING_PX`) are **pure values trapped
in the heaviest modules**, and the path-resolution rule is *inline in
`_build_widget`* (not even importable). Importing those modules to get a
dict is the "pulls in the world" cost the original design avoided —
**correctly**. `config` is the lone clean import.

## Q2 — Leaf-module POC (built & proven on this branch)

Created `src/led_ticker/_planning_contract.py` — **pure stdlib only**
(hard rule, stated in its docstring). It holds:

- `resolve_widget_path(config_dir, raw_path)` — the one definition of
  the round-3 rule, now obeyed by **both** `app._build_widget` and
  `tools/gif_plan/plan._resolve_widget_paths`.
- `AUTO_TEXT_ALIGN_FOR_IMAGE`, `MIN_SCROLL_SPEED_MS`,
  `TEXT_EDGE_PADDING_PX`, `PATH_BACKED_WIDGET_TYPES`,
  `DEFAULT_HOLD_TIME_S`, `DEFAULT_LOOP_COUNT`.

`_image_base.py` now re-exports the three constants from the leaf
(call sites unchanged); `app.py` calls `resolve_widget_path`;
`tools/gif_plan/plan.py` imports `resolve_widget_path` from the leaf.

**Measured outcomes:**

| Check | Result |
|---|---|
| `import led_ticker._planning_contract` (clean env) | **10.8ms, +32 mods, zero heavy deps** (no PIL/aiohttp/asyncio, doesn't even trip the rgb stub) |
| Planner importing leaf (clean env) | **3.88ms, heavy=NONE**, 68 total modules — vs `_image_base`'s +363 w/ aiohttp+asyncio |
| Full engine suite after refactor | **1866 passed, 2 skipped, 13 xfailed — byte-identical to the pre-spike baseline (zero behavior change)** |
| `tools/gif_plan` suite (path resolution now via leaf) | 169 passed, 13 xfailed |
| `make plan-gif` (clean env, no `PYTHONPATH`) | exit 0, correct output (gif-silent → real 1200ms via the shared rule) |
| ruff / format on touched files | clean |

The POC proves Option A end-to-end in miniature: a dependency-free leaf
gives the planner a **compile-time** link to the engine's truth at
~4ms/zero-heavy cost, with the engine completely unchanged.

## Q3 — Contract test for the one derived fact

`_BDF_CELL_WIDTH` (planner) has **no engine constant equivalent** — the
engine's truth is the parsed BDF `FONTBOUNDINGBOX`, not a dict. Sharing
a constant would itself be a mirror. Correct mechanism: a test in the
**led_ticker** suite that, for each alias, asserts the planner's
`_BDF_CELL_WIDTH[name]` equals the engine-parsed advance
(`fonts.get_bdf_for`). It fails in led_ticker's own CI at change time,
naming `gif_plan` as the thing to update. (Follow-up scope.)

## Q4 — Packaging reality (settled)

`led_ticker` is an installed package in the uv env, so
`from led_ticker._planning_contract import …` works from
`tools/gif_plan` with **no `sys.path` hack and no `PYTHONPATH`**. The
leaf is pure stdlib, so it never trips the rgbmatrix shim. `make
plan-gif` verified working clean. No CI/Make wiring changes needed
(the new gif-plan-test job from PR #71 already covers the planner).

## Decision

| Option | Verdict |
|---|---|
| **A. Extract-and-share leaf** | **CHOSEN.** POC-proven: compile-time link, ~4ms/zero-heavy planner cost, engine unchanged, `make plan-gif` clean. |
| B. Import-where-cheap + contract-test rest | Subsumed — only `config` imported cheaply; the high-value items (constants, path rule) had to be *extracted* anyway, which is A. |
| C. Keep mirrored + drift test | Fallback only; A removes the duplication entirely for the pure surface, which C cannot. |

**Scope boundary:** emergent tick-loop math (`gif_loops=0`,
`scroll_through`, marquee floor) stays reimplemented — not shareable —
pinned by the existing dogfood tripwire + the curated ±1s anchors.

## Recommended follow-up (separate implementation PR)

1. Land the leaf + the three re-exports + planner import (this branch's
   POC, already green) as the foundation.
2. Migrate the remaining pure mirrors to the leaf: `config.py` field
   defaults sourced from `DEFAULT_HOLD_TIME_S` / `DEFAULT_LOOP_COUNT`;
   planner reads `AUTO_TEXT_ALIGN_FOR_IMAGE` / `MIN_SCROLL_SPEED_MS`
   from the leaf instead of its local copies.
3. Add the Q3 BDF-cell-width contract test to the led_ticker suite.
4. Update `tools/gif_plan` module docstrings — the design rationale
   ("No led_ticker engine import") is now *narrowed*, not absolute:
   pure facts come from the leaf; only emergent math is reimplemented.

This branch's POC is intentionally minimal (path rule + 3 constants) so
it can ship as the proven foundation; steps 2–4 are mechanical.

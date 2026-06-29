# Design: panel-map — pixel-mapper configuration helper

**Date:** 2026-06-29
**Status:** Approved (brainstorm), pending spec review → implementation plan

## Problem

Building a custom multi-panel sign requires deriving a `pixel_mapper_config`
Remap string by hand:

```
Remap:WIDTH,HEIGHT|x,yORIENT|x,yORIENT|...
```

— one entry per panel **in data-chain order**, each giving the panel's
top-left `(x, y)` on the final logical canvas plus an orientation flag
(`n` normal / `s` 180° / `e` 270° / `w` 90° / `x` discard). To write it
correctly you must know three things that are *not* obvious from looking at
the wall: which physical panel is #1, #2, … in the cable chain; where each
panel lands on the finished canvas; and how each one is rotated.

When we built bigsign we had no tooling for this. We iterated by editing the
string, painting **random text**, photographing the panels, guessing what was
wrong, and editing again — a slow, ambiguous loop because random text doesn't
tell you a panel's chain index or its rotation directly.

Existing tooling covers neighboring layers but not this one:
`led-ticker validate` and `make render-demo` cover the **config/widget layer**;
`scripts/panel_color_test.py` (`make panel-test`) covers the **hardware/driver
layer** (RGB sequence, FM6126A, chain length, slowdown). Nothing covers the
**panel-geometry layer** — the mapper string itself.

## Goal / non-goals

**Goal:** a small, deterministic helper that turns the mapper-derivation loop
from "edit → random text → photograph → guess" into "reveal → photograph →
transcribe → derive → verify", with purpose-built calibration patterns and a
string generator.

**Non-goals:**

- **No LLM, anywhere.** Every step is plain Python: paint loops + grid parsing
  + arithmetic. There is deliberately no "point your camera and let an AI infer
  the layout" feature. Manual transcription of the reveal photo is the
  canonical (and only) input path.
- Not part of the `led-ticker` CLI — it is a standalone script under
  `scripts/`, exactly like `panel_color_test.py`.
- `derive` does not auto-solve 90°/270° (`e`/`w`) layouts where rotation swaps
  a panel's footprint and breaks the uniform grid (see Scope & limitations).
  It emits a best-guess grid and the user finishes in `verify`.
- No GUI, no web surface, no photo storage.

## Design

One script — `scripts/panel_map.py` — with three subcommands. Two of them paint
hardware (`reveal`, `verify`); one is pure logic and runs anywhere (`derive`).
All three reuse the same config-reading + `LedFrame` construction as
`panel_color_test.py`, so every panel knob (`rows`, `cols`, `chain_length`,
`parallel`, `panel_type`, `led_rgb_sequence`, `gpio_slowdown`, `rp1_pio`) is
exactly what the running ticker would see.

```
uv run python scripts/panel_map.py reveal  [--config PATH] [--hold SECONDS]
uv run python scripts/panel_map.py derive  [--config PATH] [--layout FILE]
uv run python scripts/panel_map.py verify  [--config PATH] [--hold SECONDS] [--mapper "Remap:..."]
```

### The loop

1. **`reveal`** — paint the panels with **no mapper applied** so the framebuffer
   maps 1:1 to the raw data chain. Photograph the wall.
2. **Transcribe** the photo into an ASCII grid (one cell per panel).
3. **`derive`** — feed the grid in; get the `Remap:` string printed to stdout.
4. **`verify`** — paste the string back (or drop it in the config) and paint a
   coherent full-canvas pattern. Correct → coherent; wrong → scrambled. Loop
   back to step 2 if needed.

### `reveal` — chain + orientation calibration pattern

Runs with `pixel_mapper_config` forced to **identity** (empty), overriding
whatever the config holds. Without a mapper, the logical canvas is
`cols·chain_length` wide × `rows·parallel` tall, and chain panel `k` (0-based)
occupies logical x in `[k·cols, (k+1)·cols)`. So painting "panel k content"
into that slot lights up the *k-th physical panel in the cable chain* —
directly revealing chain order.

Per panel slot `k`, paint (all via `SetPixel` / `ScaledCanvas.draw_bdf_text`,
no `DrawText` on wrapped canvases):

- The **chain index** `k+1` (1-based) as a large BDF digit, centered in the slot.
- An **up-arrow** glyph pointing toward logical-top — the primary rotation tell.
- A **bright dot** in the logical **top-left** corner of the slot — disambiguates
  90° vs 270° and mirrors.
- A thin **1px border** around the slot so panel boundaries are unmistakable.
- A subtle **per-panel hue** (cycled) as a secondary boundary aid — not
  load-bearing; index + border already suffice.

Paints once and holds (re-painting each `--hold` tick, capturing the swap
return per hardware constraint #1). Ctrl-C paints a final black frame and swaps,
like `panel-test`, so the panel never sticks.

**Orientation legend** — what you observe on a given physical panel → the flag
you transcribe for it:

| What you see on that physical panel       | Flag        |
| ----------------------------------------- | ----------- |
| Arrow up, dot top-left                    | `n` (0°)    |
| Arrow down, dot bottom-right              | `s` (180°)  |
| Arrow right, dot top-right                | `e` or `w`  |
| Arrow left, dot bottom-left               | the other   |

The exact `e` vs `w` mapping (the docs define `e=270°`, `w=90°`, but which
*visual* each produces) is the **one empirical unknown** — it will be pinned
during implementation by running `verify` against the real rgbmatrix library on
hardware, then documented. The common `n`/`s` cases are unambiguous and need no
hardware to reason about.

### `derive` — string generator (no hardware)

Reads the transcribed grid from `--layout FILE` or, if omitted, from **stdin**
(paste then Ctrl-D). Grid format — whitespace-separated cells, one text row per
physical row, each cell `<chain-index><flag>`:

```
3n 4n 5s 6s
1n 2n 7s 8s
```

Algorithm:

- Parse into a `G_rows × G_cols` grid of `(index, flag)` cells.
- `WIDTH = G_cols · cols`, `HEIGHT = G_rows · rows`.
- For each cell at grid `(row, col)`: target `x = col·cols`, `y = row·rows`,
  `ORIENT = flag`.
- Emit entries **in chain-index order** 1..N (not grid reading order):
  `Remap:WIDTH,HEIGHT|x₁,y₁f₁|x₂,y₂f₂|...` to stdout. Diagnostics to stderr.

Validation (clear error messages, non-zero exit on failure):

- Every index `1..N` present exactly once (report missing / duplicate).
- Grid rectangular (every text row same cell count).
- Each flag in `{n, s, e, w, x}`.
- `N == chain_length · parallel` from the config (warn, don't hard-fail, if the
  user is deriving for a layout that differs from the loaded config).

### `verify` — coherent full-canvas pattern

Applies a candidate mapper — `--mapper "Remap:..."` (e.g. paste `derive`'s
output) or, if omitted, the config's `pixel_mapper_config` — and paints **one
coherent image across the whole finished canvas**:

- A **coordinate grid**: faint lines every `cols` / `rows` px so seams should
  fall exactly on physical panel edges.
- **Corner labels**: `0,0` top-left, `W,0` top-right, `0,H` bottom-left —
  instantly exposes flips and axis swaps.
- One **big arrow** spanning the canvas pointing up, plus a short **`TOP`**
  label along the top edge.

Correct mapper → square grid, labels in the right corners, arrow up, seams on
panel edges. Wrong mapper → torn / scrambled / upside-down. Same hold + Ctrl-C
behavior as `reveal`.

## Scope & limitations (documented honestly per DOCS-STYLE)

- `derive` computes **uniform-cell rectangular grids**. `n`/`s` are fully
  supported — 180° doesn't change a panel's footprint. `e`/`w` (90°/270°) swap
  width/height, so a grid mixing rotated and unrotated panels can be physically
  non-rectangular; the simple grid math can't always solve those. For such
  layouts `derive` emits its best grid guess and the docs point the user at
  `verify` to finish by hand. This will be stated plainly on the docs page, not
  papered over.
- `reveal` and `verify` are **hardware** tools (need `/dev/mem`; `sudo` on a
  host Pi or `--privileged` in Docker) — same constraints as `panel-test`. The
  ticker and these diagnostics can't share the matrix; stop the ticker first.

## Surface

Mirrors `panel-test` conventions exactly.

**Make targets:**

- `make panel-map-reveal` / `make panel-map-verify` — hardware, with `CONFIG=`
  and `HOLD=` overrides and `-docker` variants (`--privileged --network host`
  against the existing image), same as `panel-test`.
- `make panel-map-derive` — no hardware; pipes a `--layout` file or stdin grid
  to the generator.

**Docs:** new page `docs/site/src/content/docs/tools/panel-map.mdx` (full
DOCS-STYLE treatment): the reveal→photograph→transcribe→derive→verify
walkthrough, the orientation legend table, the `e`/`w` empirical note, and the
scope-limitation honesty block. No demo GIF (test patterns don't render
meaningfully off-hardware — same call `panel-test` made). Cross-link from
`tools/panel-test.mdx`, `hardware/bigsign.mdx`,
`hardware/building-your-own.mdx`, `reference/cli.mdx`, and the relevant
`RelatedPages` blocks.

## Testing

`derive` is pure logic ⇒ the testing center of gravity:

- **Golden tripwire:** the bigsign grid
  ```
  8n 6n 4n 2n
  7n 5n 3n 1n
  ```
  reproduces the `config.bigsign.example.toml` Remap string
  (`Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n`)
  **character-for-character**. Derivation of this grid from the string: chain
  panel 1 → `(192,32)` = rightmost column, bottom text row; panel 8 → `(0,0)` =
  leftmost column, top text row. This binds the tool to the one known-good
  real-world string and doubles as a worked example for the docs page.
- Single-row-of-4, 2×2 grid, and n/s-rotation cases.
- Error cases: missing index, duplicate index, ragged grid, bad flag,
  count-vs-`chain_length` mismatch.

Paint modes (`reveal` / `verify`) get light tests via the headless backend /
stub canvas — assert that with no mapper the per-panel index pixels land in the
correct chain slots, and that the script captures every `SwapOnVSync` return
(constraint #1) and never calls `DrawText` on a wrapped canvas (constraints #1,
#2). No hardware in CI — same posture as `panel-test`.

**Hardware-rendering constraint compliance (CLAUDE.md):** #1 capture every swap
return; #2 no `DrawText` on non-Canvas (use `ScaledCanvas.draw_bdf_text` /
`SetPixel`); #3 no `GetPixel`; #4 `SetPixel` everywhere; #5 swap-then-sleep.

## Open implementation detail

- Pin `e` vs `w` visual mapping on real hardware and document it.
- Factor the `DisplayConfig → LedFrame` kwargs into the shared helper
  `panel_color_test.py` already wants (or reuse it if that refactor landed), so
  the two scripts can't drift on panel knobs.

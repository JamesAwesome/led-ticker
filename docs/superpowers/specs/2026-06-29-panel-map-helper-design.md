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
- A short **underline directly beneath the index digit** ("this-way-up" bar) so
  a rotated `6`/`9` (and any rotated digit) is never ambiguous — you read the
  digit relative to its underline, not the room. (Persona feedback: a rotated
  digit silently breaks the whole grid; the corner dot fixes rotation but not
  digit legibility.)

Paints once and holds (re-painting each `--hold` tick, capturing the swap
return per hardware constraint #1). Ctrl-C paints a final black frame and swaps,
like `panel-test`, so the panel never sticks.

**Prerequisite — rule out the hardware layer first.** If `reveal` itself looks
garbled (wrong colors, scrambled half-panels), that is a *hardware/driver* fault
(`led_rgb_sequence`, `panel_type`/FM6126A, `gpio_slowdown`), not a mapper
problem — and `panel-map` cannot help with it. The docs page MUST open by
telling the user to run [`panel-test`](/tools/panel-test/) first and only reach
for `panel-map` once solid colors render cleanly. Without this pointer a
first-timer (whose panels are *already* garbled — that's why they're here)
concludes the new tool is broken and bails. (Both personas flagged this; it is
a free cross-link.)

**Photo discipline (one line in docs):** shoot the wall square-on, lights toward
you, so left/right and top/bottom aren't mirrored in the photo.

**Note on double digits:** chain indices ≥ 10 rotated sideways get hard to read.
Fine for the reference builds (≤ 8 panels); the docs note it for larger walls.

**Per-panel hue is explicitly cut.** An earlier draft cycled a subtle per-panel
hue as a secondary boundary aid; index + border already disambiguate, so it was
dropped as gold-plating on the riskiest command (PM feedback).

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
hardware. The common `n`/`s` cases are unambiguous and need no hardware to
reason about.

**Gate (both personas):** the docs page MUST NOT ship with a "`e` or `w`, we're
not sure" legend. Pinning `e`/`w` on hardware is a **release blocker** for the
docs page, not a post-ship cleanup — most hobbyists portrait-mount at least some
panels, so an ambiguous legend leaves the rotated-panel case dead in the water.
The legend table ships with concrete flags filled in.

**Flip-and-retry fallback (documented):** even with the legend pinned, if a
rotated panel comes out wrong in `verify`, the fix is "swap that panel's
`e`↔`w` and re-run." This is stated explicitly so a 90°/270° mistake is a
10-second coin-flip, not a re-derive-from-scratch.

### `derive` — string generator (no hardware)

Reads the transcribed grid from **`--layout FILE`** (the friendly,
re-editable, headline path) or, if omitted, from **stdin** (paste then Ctrl-D —
kept as a convenience, but NOT the headline: over SSH a non-engineer fumbling
Ctrl-D/Ctrl-C is a real failure mode, so the docs lead with the file).

**Transcription instruction (stated, not implied — hobbyist feedback):** *Stand
in front of the wall. Write one `<chain-index><flag>` token per panel — the top
row of the wall first, left to right, exactly as the panels hang.* A panel's
row/column is decided by **where it sits on the wall**, not by how it's rotated.
`derive` re-sorts into cable/chain order internally, so the user never thinks in
chain order — they only describe what they see.

Grid format — whitespace-separated cells, one text row per physical row, each
cell `<chain-index><flag>`:

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

Validation — **plain-language** error messages (hobbyist feedback: cryptic
errors make a first-timer distrust the whole tool), non-zero exit on failure:

- Every index `1..N` present exactly once — e.g. *"You listed panel 4 twice and
  never listed panel 5. Each cable position appears exactly once."*
- Grid rectangular — e.g. *"Row 2 has 3 panels but row 1 has 4. Every wall row
  needs the same number of cells."*
- Each flag in `{n, s, e, w, x}` — name the bad token and the legal set.
- `N == chain_length · parallel` from the config (warn, don't hard-fail, if the
  user is deriving for a layout that differs from the loaded config).

### `verify` — coherent full-canvas pattern

Applies a candidate mapper — `--mapper "Remap:..."` (e.g. paste `derive`'s
output) or, if omitted, the config's `pixel_mapper_config` — and paints a
coherent **and self-diagnosing** image across the whole finished canvas:

- A **coordinate grid**: faint lines every `cols` / `rows` px so seams should
  fall exactly on physical panel edges.
- **Corner labels**: `0,0` top-left, `W,0` top-right, `0,H` bottom-left —
  instantly exposes flips and axis swaps.
- One **big arrow** spanning the canvas pointing up, plus a short **`TOP`**
  label along the top edge.
- **Per-panel diagnostic overlay (key change from persona reviews):** into each
  panel cell, paint its *expected* chain index + a small *expected* orientation
  marker (same glyph vocabulary as `reveal`). So a wrong mapper doesn't just
  look "scrambled" — the offending panel shows the wrong number or a tilted
  marker, telling the user **which** panel is misplaced/misrotated and **how**.
  They fix that one cell of the grid and re-run, instead of re-transcribing
  everything and guessing.

Correct mapper → square grid, labels in the right corners, arrow up, seams on
panel edges, every panel showing the index/orientation it should. Wrong mapper
→ the specific panel that's off is self-identifying. Same hold + Ctrl-C behavior
as `reveal`.

**Why this matters:** without the per-panel overlay, `verify` is only
pass/fail, which merely *relocates* the original "edit → photograph → guess"
loop from the Remap string onto the ASCII grid. The overlay closes the loop —
it's cheap because `verify` already paints the full canvas.

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
DOCS-STYLE treatment). Both personas called the docs page "half the product,"
so it carries specific load:

- **Open with the `panel-test`-first prerequisite** (rule out the hardware
  layer before reaching for the mapper tool).
- **Lead with the bigsign as a worked end-to-end example** — the same grid the
  golden tripwire uses (`1n 3n 5n 7n` / `2n 4n 6n 8n`, hardware-validated) → its
  known string → `verify`. One concrete walkthrough beats abstract prose.
- **A real `reveal` photo** of a panel wall showing the numbers/underlines/
  arrows/dots, sitting next to the typed grid and the string it produced. Unlike
  `panel-test` (whose solid colors don't photograph meaningfully), `reveal` is
  inherently photographable and the picture is the most reassuring artifact on
  the page. **Until bigsign hardware is available to shoot, ship a labeled
  placeholder** (consistent with the project's other pending-photo placeholders)
  and backfill — track it as a TODO, don't block the tool on the photo.
- The orientation legend table (with `e`/`w` **pinned**, not "unsure"), the
  flip-and-retry fallback, the plain-language transcription instruction, photo
  discipline, and the scope-limitation honesty block.
- No demo GIF — test patterns don't animate meaningfully; the still photo is the
  visual.

**Inline intercept (not just a tools-index entry):** `hardware/building-your-own`
must, *at the exact step where it tells a custom builder about
`pixel_mapper_config`*, say "don't hand-write this — run `panel-map`." A
first-timer is stuck at that line, not browsing the tools index. Also cross-link
from `tools/panel-test.mdx`, `hardware/bigsign.mdx`, `reference/cli.mdx`, and the
relevant `RelatedPages` blocks.

## Testing

`derive` is pure logic ⇒ the testing center of gravity:

- **Golden tripwire:** the bigsign grid
  ```
  1n 3n 5n 7n
  2n 4n 6n 8n
  ```
  reproduces the `config.bigsign.example.toml` Remap string
  (`Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n`)
  **character-for-character**. This binds the tool to the one known-good
  real-world string and doubles as a worked example for the docs page.

  > **CORRECTION (2026-06-29, hardware-validated).** The original spec listed
  > this grid as `8n 6n 4n 2n / 7n 5n 3n 1n`, reverse-engineered from the
  > string under the assumption that string entry *k* = the physical position
  > of chain panel *k*. That assumption is wrong: the C `RemapMapper` indexes
  > its entry list by **reversed** chain position (`panel_col = chain - x/pw -
  > 1`), so the first string entry feeds the *last* cable panel. On bigsign's
  > centrally-symmetric 4×2 layout the two conventions yield the identical
  > string, so the circular test passed while `derive` shipped a 180°-inverted
  > result. The real reveal photo shows chain index 1 at the **top-left**
  > (`1n 3n 5n 7n / 2n 4n 6n 8n`); `derive` now emits entries in reverse chain
  > order, turning that grid into the production string. Tripwire:
  > `test_derive_emits_in_reverse_chain_order`.
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

## Success metrics

Qualitative (a build-time, once-per-sign tool), but falsifiable:

- **Primary:** the maintainer re-derives the bigsign Remap string from a cold
  `reveal` in a single pass to a coherent `verify`, never hand-editing a Remap
  string. If the author can't, no one can.
- **Adoption:** a custom builder (not the maintainer) reports deriving their
  string via the tool without hand-writing `Remap:...` — captured via an
  issue/Discussion tag.
- **Negative signal to watch:** repeated `reveal`/`verify` round-trips on one
  build ⇒ orientation transcription is still failing (the central persona risk
  resurfacing); revisit glyphs.
- **Leading proxy:** the golden tripwire stays green — it's both the test and
  the docs' worked example.

## Implementation ordering

1. **Orientation hardware spike FIRST.** Before building the full surface, on
   real hardware: (a) pin the `e`/`w` visual→flag mapping, and (b) confirm the
   `reveal` glyphs (index + underline + arrow + corner dot) are actually legible
   in a room photo at *both* cell sizes — 16×32 (smallsign) and 32×64 (bigsign).
   If the encoding doesn't read clearly, change it (bigger digit, clearer tell)
   *before* the rest is built. This de-risks the one step the whole tool's value
   hinges on.
2. `derive` (pure logic, fully testable, golden tripwire) — buildable without
   hardware, lands the core value early.
3. `reveal` + `verify` paint modes (incl. the per-panel diagnostic overlay).
4. Make targets + docs page (with the spike's pinned `e`/`w` legend + photo
   placeholder).

## Open implementation detail

- Factor the `DisplayConfig → LedFrame` kwargs into the shared helper
  `panel_color_test.py` already wants (or reuse it if that refactor landed), so
  the two scripts can't drift on panel knobs.

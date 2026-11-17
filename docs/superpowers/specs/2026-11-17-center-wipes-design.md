# Design: center wipes (`wipe_in`, `wipe_out`, vertical twins)

Roadmap item 1, approach A (build reduced). Gate: `2026-11-17-center-sweeps-gate.md`.
Status: approved by James 2026-11-17; implemented on `center-wipes`; amended by review cycles 1–3 (see the antagonist ledger). Size: small change.

## Intent

Four new erase-style wipe transitions whose sweep lines start or end at the
panel center, matching Alpha ROLL/WIPE IN/OUT geometry and Huidu's "open from
middle" / "close up and down", in the same visual language as the existing
wipe family. Rolls (two-sided push) are out of scope and in the backlog until a
clipping primitive exists.

## Goals / non-goals / anti-goals

- Goals: `wipe_in`, `wipe_out`, `wipe_in_vertical`, `wipe_out_vertical`;
  byte-identical behavior for every existing transition; docs row per variant.
- Non-goals: true reveal wipes, roll in/out, touching the `wipe_random` /
  `wipe_alternating` pools (item 2), refactoring the existing four wipe classes.
- Anti-goals: a 1-px gap or overlap where the two fronts meet; a visible
  letterbox band on banded scale-2 sections; a mid-sweep resize on cross-scale
  sections.

## Approaches considered

A erase-style center wipes (chosen), B clip proxy then full Alpha set, C defer
to item 3's raster. Reasons recorded in the gate: wanted-evidence is vendor-only,
rolls need a new primitive, the wipe half is small and pure.

## Design

**Semantics.** Outgoing is drawn at `outgoing_scroll_pos`; black `SubFill`
regions grow from the fronts; colored sweep lines `2 * scale` thick mark the
fronts; `t >= 1.0` draws incoming only. Identical pattern to `wipe.py`.

| Name | Fronts | Erased region at `t` | Default color |
|---|---|---|---|
| `wipe_in` | two, start at left and right edges, move toward center column | `[0, b)` and `[rw - b, rw)` | yellow (255, 255, 0) |
| `wipe_out` | two, start at center column, move toward edges | `[c - b, c + b)` clamped to the panel | red (255, 0, 0) |
| `wipe_in_vertical` | top and bottom edges toward center row | rows, same math on `rh` | yellow |
| `wipe_out_vertical` | center row toward top and bottom | rows | red |

**Center math (odd and even sizes).** Let `n` be the swept extent (`rw` or
`rh`). The front travel `b` is linear in `t` and capped at
`front_cap = (n - 1) // 2` inward, `n // 2 - 1` outward, with multiplier
`cap + 1` so `b == cap` for any `t` near 1.0. For `in`, the erased rects are
`[0, b)` and `[n - b, n)`. For `out`, the band is `[n // 2 - b, n // 2 + b + (n % 2))`,
so on an odd extent the center pixel belongs to the band from `b = 1` onward.
At the cap a 1-2 px sliver is still kept and the sweep lines cover all of it,
so the frame before the cut is black plus sweep colour, never a fully black
panel (cycle-1 review: capping at `half` left the vertical variants black for
the last third of an `ease_out` run). Pinned by a test over `n in (15, 16, 159, 160, 256)` that
asserts erased ∪ kept == all pixels and erased ∩ kept == ∅ at every `b`.

**Scale handling.** `_phys(canvas)` for real width/height/scale/y-offset; all
geometry in physical pixels so letterbox bands are erased too (the existing
`test_*_covers_top_band` shape). `_OutgoingScaleSweep` mixin for
`scale_switch_at = 1.0`.

**`min_frames`.** Horizontal 20 (each front travels `rw / 2` ≈ 80 px at scale 1,
one-fourth of the 40 that `wipe_left` uses for a 160-px travel is too few to
see, 20 keeps ~4 px per frame). Vertical 16, same as `wipe_up` / `wipe_down`,
so each front advances one logical row per two frames at scale 1. Hardware
check may raise the vertical value.

**Code shape.** New file `src/led_ticker/transitions/center_wipe.py`
(auto-discovered by `pkgutil`). One private `_CenterWipe(_BaseWipe)` base
parametrized by `axis` ("x" / "y") and `inward: bool`, four thin registered
subclasses setting those plus `DEFAULT_COLOR` and `min_frames`. `_BaseWipe`
stays in `wipe.py` and is imported; nothing in `wipe.py` changes.

**`split`.** Unchanged. Docs note it as the magenta-edged twin of `wipe_out`
with no erase band color knob.

**Config.** `transition_color` works on all four (via `_BaseWipe.__init__`).
Names are picked up by `validate` from the registry; no validate change.

**Docs.** `docs/content-source/transitions/wipe.md` gains four rows and a
sentence on `split`; `wipe.mdx` caption lists the new variants;
`tutorial/05-polish.mdx` wipe list gains the names. Demo GIF unchanged (its
paired TOML stays verbatim); a second GIF for the center set is optional and
not part of the PR.

## Tests

- Registry: four names present and sorted (`test_transitions_registry.py`).
- `t = 0` draws outgoing plus the sweep lines at the fronts' start, `t = 1.0` draws incoming only at `cursor_pos = 0`, for each class.
- Partition test over odd and even extents (above).
- Letterbox band coverage at banded scale 2 and full-height at scale 4 for one
  horizontal and one vertical class.
- Nonzero `outgoing_scroll_pos` is forwarded to `outgoing.draw`.
- Byte-identical guard: `wipe.py`, `effects.py`, `push.py` untouched (diff
  review, no code tripwire needed).

## Process

Worktree branch `center-wipes`. TDD. Antagonist loop capped at 5 cycles per the
roadmap; exit on low/docs only; loop 5 with medium or higher stops and flags.
Ends ready-and-ask, no merge without James. Hardware check on smallsign and
bigsign per the gate's section 9 before the ask.

## Left to the builder

Exact default colors if the two picked here clash with a section `bg_color` in
the test configs; whether `_CenterWipe` reads cleaner as two methods
(`_erase_rects(t)`, `_line_rects(t)`) or one.

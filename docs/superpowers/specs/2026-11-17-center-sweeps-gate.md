# Gate: item 1, center-in/out and vertical roll + wipe variants

Roadmap: `2026-11-15-effects-roadmap.md`, item 1. Status: **closed 2026-11-17, outcome build reduced (approach A), picked by James.**

## 1. What the audit asked for

Alpha ROLL_IN / ROLL_OUT / WIPE_IN / WIPE_OUT and Huidu "Vertically open from
middle" / "Close up and down" have no led-ticker equivalent. `split` is the
only center sweep and it is horizontal center-out only.

## 2. Finding that reshapes the item

Core has no way to clip a widget draw. Every hard-edged transition uses
draw-blackout-draw: draw one widget (it may bleed anywhere), `SubFill` black over
the region the other widget owns, draw the other widget there. That protects
exactly ONE boundary per frame.

- `wipe_*` and `split` do not reveal the incoming at all. They erase the
  outgoing to black behind a moving line and cut to the incoming at `t = 1.0`
  (`wipe.py`, `effects.py:132`). They are "wipe to black", not "wipe over".
- `push_*` move both widgets with `cursor_pos` / `y_offset` and black out the
  single seam between them (`push.py`).

Sketch of `roll_out` at `t = 0.5` on a 160-wide panel: outgoing left half at
x < 40 shifted left, incoming left half on [40, 80), incoming right half on
[80, 120), outgoing right half at x >= 120 shifted right. Four regions, two
clipped draws per widget. Draw-blackout-draw cannot produce it: the second
outgoing draw overwrites the first. `roll_in` has the same shape mirrored.
**Two-sided rolls need a clipping primitive. Center wipes in the existing
erase style do not.**

The clipping primitive that fits this codebase is a write-side proxy, the
pattern `pixel_gain.with_pixel_gain` already uses: a `ClipCanvas` at the bottom
of the wrapper chain that drops `SetPixel` / `SubFill` outside a rectangle and
crops the PIL image on `SetImage` (which the gain proxy passes through untouched;
clipping must not). This is the scissor test from raster graphics: "only pixels
that lie within the scissor box can be modified by drawing commands"
([Khronos glScissor](https://registry.khronos.org/OpenGL-Refpages/gl4/html/glScissor.xhtml),
read 2026-11-17). It would also let the existing wipes become true reveals and
would retire every blackout in `push.py` and `wipe.py`, but that is a behavior
change for every wipe user and belongs in its own gate.

## 3. Should we build: rubric

| Question | Evidence | Verdict |
|---|---|---|
| Wanted? | Vendor lists only. Four of the eleven Alpha modes with no equivalent are these. No open issue, no shipped config asks for a center sweep; `split` appears in 2 user configs and 6 test configs. | **Weak. James to answer: do you want these on a sign?** |
| Good design? | Center wipes fit the existing erase-style family exactly. Vertical variants at scale 1 have 8 rows of travel per side on a 16-row canvas, so a vertical center sweep is a 2-to-3-frame event at `min_frames = 16`; the hardware check must decide if it reads as motion or as a blink. | OK for horizontal; vertical is the open design question. |
| Too hard? | Center wipes: one file (`wipe.py` or `effects.py`), tests, `wipe.mdx`, demo GIF. No API change. Rolls: add the clip proxy (new module, wrapper-chain rebuild, `SetImage` crop, tripwires on scaled + banded canvases). | Wipes: small. Rolls: medium, one new seam. |
| Reviews poor? | None. Wipe/push/split history is bug fixes (cross-scale sweep #325, SubFill perf #100, letterbox bands) and no removals. | Clean. |

## 4. Research and sourcing

Read directly:

- Alpha 215 remote-control programming manual
  (<https://daylight.net/manuals/alpha-215-remote-control.pdf>, text extracted
  2026-11-17): "[RL <>] = Roll a message in from both sides of the sign",
  "[RL ><] = Roll a message out from the middle of the sign". Roll in/out is
  horizontal on this model. Scroll: "moves your message from the bottom to the
  top of the sign".
- Khronos glScissor reference, quoted above.

Search summary only, pages unreachable (403 / DNS): the Alpha 220 protocol table
gives mode `p` as "Previous message is pushed toward the center of the display
by the new message" and `q` as "pushed outward from the center by the new
message", so roll means push. A second Alpha model page describes roll in/out
vertically (top and bottom to the center row). **Axis varies by model**; Huidu
offers both.

Unsourced: what an Alpha WIPE does to the previous message. This does not block
the gate: without a clip primitive the only wipe we can build is the erase
style we already ship, and with one we can choose.

Technique notes for the design:

- Two-front symmetric sweep. The odd-width center pixel must belong to exactly
  one front so the two fronts meet without a 1-px gap or overlap; same rule as
  the odd-dimension Bresenham note in project memory.
- Boundary math in the four wipes is not uniform today (`int(t*rh)` vs
  `int(t*(rh+1))`, `min_frames` 16 vs 40, per-class default colors, sweep
  clamp). A shared base must reproduce each exactly or leave them alone.

## 5. Approaches

**A. Build reduced: erase-style center wipes, rolls deferred.** Add
`wipe_in` / `wipe_out` (horizontal, edges-to-center erase and center-to-edges
erase) and `wipe_in_vertical` / `wipe_out_vertical`; `split` stays as is and is
documented as the magenta-edged twin of `wipe_out`. No new seam. Roll in/out
move to the backlog until a clip or raster primitive exists (item 3's readable
raster could also serve). Smallest change that pilots the roadmap process.

**B. Clip proxy first, then the full set.** Precursor PR: `clip_canvas.py`
with `with_clip(canvas, rect)` modelled on `with_pixel_gain`, `SetImage` crop,
tripwires at scale 1, scale 4, banded scale 2. Feature PR: `wipe_in/out`
(both axes) and `push_in/out` (both axes, Alpha roll semantics) built on clipped
draws, no blackouts. Delivers all four Alpha modes. Opens the question of
migrating the existing wipes to true reveals, which must NOT ride this PR.

**C. Defer the whole item to after item 3.** The readable raster planned for
text styling also enables clipped compositing. Loses the process pilot.

Recommendation: **A**, because "wanted" is weak and the roadmap wants a small
first item. If James wants the rolls on a sign, **B** with the proxy as a
refactor-only precursor; it is the one approach backed by a standard technique.

## 6. Decisions the design must settle

1. `split` vs `wipe_out`: alias, keep both, or rename with a migration hint
   (`_TRANSITION_MIGRATION` already exists for sprite families).
2. Naming per axis. Built-in transitions receive only `color` / `colors`;
   `trans_cfg.extra` reaches plugin types only (`_build_trans_obj`). Either
   name per axis (`wipe_in_vertical`) or widen the built-in config path, which
   is a seam. Name per axis.
3. `wipe_random` / `wipe_alternating` hard-code four classes. Adding members
   changes existing configs. Leave the pools alone; item 2 owns pools.
4. Shared base for the existing four wipes only after golden frames are
   recorded (scale 1, scale 4, banded scale 2, nonzero `outgoing_scroll_pos`)
   and only if no per-direction special case is needed to match them.
5. Vertical sweeps at scale 1: `min_frames` so the two fronts take at least
   8 ticks to meet, or declare vertical variants hires-preferred in docs.

## 7. Campsite and DRY

- Open issues touching these files: none (#525/#526/#527/#535 do not).
- DRY: the direction-parametrized base is conditional on item 6.4. The
  random/alternating pools are item 2's.
- Docs made true or false: `wipe.mdx`, `tutorial/05-polish.mdx` mention the
  wipe set; `transitions-wipe.gif` demo would need a re-render if the page
  shows all variants.

## 8. Seams touched

`transitions/wipe.py` (or a new `center.py`, auto-discovered), `tests/test_transitions.py`
(letterbox-band tripwires like `test_wipe_right_blackout_covers_top_band`),
`validate` picks names up from the registry automatically, `wipe.mdx` + GIF.
Approach B adds `clip_canvas.py` and its tests.

## 9. Hardware check plan

- Smallsign (scale 1): horizontal `wipe_in` / `wipe_out`; vertical variants at
  default duration. Question: does the vertical sweep read as motion?
- Bigsign (scale 4) and a banded `scale = 2, content_height = 32` section:
  letterbox bands fully black during the sweep, no 1-px seam at the center
  column/row, snap at `t = 1.0` matches the plain draw.
- Nonzero `outgoing_scroll_pos` after a scrolled message.

## 10. Proposed outcome

**Build reduced (A)** unless James wants the rolls, then **B**. Recorded reason:
wanted-evidence is vendor-only; the roll half needs a new primitive; the wipe
half is small and pure.

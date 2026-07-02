# Physical-resolution rotation (`RotationSurface`) — Design

**Date:** 2026-07-02
**Status:** Antagonistic-optimization-reviewed (verdict "needs changes" — all
7 findings folded in below, including one latent AttributeError the draft
denied: `ScaledCanvas` writes route through `SubFill`, which `PixelBuffer`
lacked). Pending user review.
**Repo:** led-ticker (core only — no plugin changes; flair.propeller picks this up with zero flair-side edits)
**Predecessors:** the rotation seam (#345) + flair.propeller (plugins#30). The seam's spec
(`2026-07-02-flair-spin-animation-design.md`) designed this follow-up in; `PixelBuffer`
and `rotate_blit` were built resolution-agnostic specifically so this PR is plumbing-only
around them.

## Goal

On the bigsign (`default_scale > 1`), `flair.propeller` (and any future
rotation consumer) rotates at **physical** resolution: hires fonts spin,
hires emoji spin (the lo-res→hi-res settle pop disappears), and rotation
steps are `scale×` finer. Smallsign behavior is byte-identical to today.

## Standing requirements (from the product owner)

1. **Antagonistic optimization-engineer review at every stopping point**
   (spec, plan, each task review, final whole-branch review). Brief: attack
   wasted per-frame work, hidden allocations, complexity that doesn't buy
   speed, and anything blocking transition reuse; simple-and-effective
   beats clever.
2. **Transition reuse kept in mind:** the rotation orchestration must be a
   widget-agnostic primitive a future rotation *transition* can call
   without refactoring — but no transition is built now (YAGNI on the
   feature, not on the seam shape).
3. **Cite the CS fundamentals** grounding each pattern, so correctness is
   checkable against first principles rather than vibes.

## Design

### 1. The reusable primitive — `make_rotation_surface` (in `rotate.py`)

```python
# Construct ONCE per consumer (widget instance / transition instance) —
# NOT per frame. Per-frame construction allocates a fresh 16,384-slot
# list + re-runs ScaledCanvas's post-init every tick (GC churn for zero
# benefit; the antagonist review measured the seam shape, Finding 4).
surface = make_rotation_surface(canvas)

# ... then per frame:
surface.clear()                          # reset the buffer (O(A) slot wipe)
# ... draw anything into surface.target using LOGICAL coordinates ...
surface.blit(angle_deg, cx_logical)      # inverse-rotate onto the real canvas
```

Consumers cache the surface (the widget holds it on the instance, lazily
built and rebuilt if canvas dims change — wrapper identity is stable
across frames per hardware constraint #9, so dims changing mid-run is
defensive only). Clearing and reallocating are the same order (both O(A)
memory touches), but construct-once removes the per-tick attrs
construction, wrapper-peel validation, and allocator/GC pressure — this
also FIXES v1, which allocates a fresh buffer every rotating draw.

- **scale == 1** (`not is_scaled(canvas)`): `target` is a bare
  `PixelBuffer(canvas.width, canvas.height)`; `blit` calls
  `rotate_blit(canvas, buffer, angle, cx, canvas.height / 2)` — byte-for-byte
  today's v1 path, relocated.
- **scaled**: `target` is `ScaledCanvas(PixelBuffer(w_real, h_real), scale,
  content_height)` where `w_real/h_real/scale/content_height` are copied
  from the incoming wrapper. The buffer is **panel-shaped**, so the
  wrapper's cached `y_offset_real` centering math is identical to the real
  canvas's. `blit` calls `rotate_blit(unwrap_to_real(canvas), buffer,
  angle, cx_logical * scale, h_real / 2)`.
  - Pivot-x: the widget's pivot is a CONTINUOUS logical coordinate (the
    visible-extent midpoint, e.g. `5.0` for text spanning logical 0..10),
    and continuous coordinates map to physical space by pure scaling —
    logical `x` ↔ physical `x · scale` (text at logical 0..10 spans
    physical 0..40; midpoint 5.0 → 20.0, the true physical center). No
    half-block adjustment: that would apply only to integer pixel INDICES
    (index `i` occupies `[i·s, (i+1)·s)`, center `i·s + s/2`), and the
    midpoint formula already carries the half-pixel semantics.
  - Pivot-y is the physical panel center: `ScaledCanvas` centers the
    content band vertically, so band-center == panel-center by
    construction.

**Grounding:**
- *Separation of mechanism and policy* (classic systems design, cf.
  Hansen/Wulf): `rotate_blit` stays a pure transform (mechanism);
  `RotationSurface` owns the scale/wrapping decisions (policy). Consumers
  — the widget today, a transition tomorrow — touch neither.
- *Adapter over a duck-typed protocol*: `ScaledCanvas` wrapping a
  `PixelBuffer` works because the entire draw pipeline is written against
  the minimal canvas protocol (`SetPixel`, `width`, `height`) — behavioral
  substitutability (the Liskov principle applied to a structural type).
  The hires font/emoji paths gate on `isinstance(canvas, ScaledCanvas)` +
  `unwrap_to_real`, both of which behave identically over the buffer
  wrapper — so they paint hires pixels into the buffer with ZERO changes.
- *Offscreen composition* (painter's-algorithm staging): render to an
  intermediate surface, transform once, composite. Also the only shape
  compatible with hardware constraint #3 (no read-back from the real
  canvas): the intermediate is OUR memory, so sampling it is legal.

### 1b. Required `PixelBuffer` additions (the draft's "zero changes underneath" was FALSE)

The antagonist review's load-bearing catch: `ScaledCanvas.SetPixel` and
`draw_bdf_text` write through **`self.real.SubFill(rx, ry, s, s, r, g, b)`**
(`scaled_canvas.py`) — not `SetPixel`. A bare `PixelBuffer` wrapped in
`ScaledCanvas` raises `AttributeError` on the first BDF glyph. Required
additions to `PixelBuffer` (small, mechanical, resolution-agnostic):

- `SubFill(x, y, w, h, r, g, b)` — fill the block's slots (bounds-clamped,
  same silent-ignore semantics as `SetPixel`).
- `clear()` — reset all slots to `None` (the per-frame reset for the
  construct-once surface).

`rotate_blit` itself needs zero changes. The Grounding bullet in §1 is
corrected accordingly: the draw pipeline's *logical* paths are
SetPixel-only, but the **scaled wrapper's write path is SubFill** — the
minimal protocol the buffer must satisfy is `SetPixel + SubFill + width +
height` (plus `get` for the blit and `clear` for reuse).

### 2. The transform itself — unchanged, and why it's already correct

`rotate_blit` (shipped in #345) needs zero changes; its correctness at any
resolution rests on:

- *Rotation is an element of SO(2)*: an orthogonal linear map, so its
  inverse is its transpose — which is why the per-pixel inverse sample is
  the sign-flipped matrix, exact and cheap (2 mul + 2 add per axis).
  Screen coordinates (y-down) flip handedness, fixed once in the sign
  convention and pinned by the 90° permutation test.
- *Backward (inverse) mapping* (standard image-warping doctrine, cf.
  Wolberg, *Digital Image Warping*): forward-mapping a discrete grid under
  rotation is not surjective onto the destination grid — adjacent source
  pixels land on non-adjacent destination pixels, leaving ~30% holes at
  45°. Backward mapping evaluates `dst(x) = src(T⁻¹x)` — a total function
  over the destination domain — so every destination pixel is defined
  exactly once. Hole-free by construction, not by tuning.
- *Nearest-neighbor resampling* (zero-order hold): correct for LED
  matrices specifically — the output device is quantized, high-contrast
  discrete emitters; first-order (bilinear) interpolation would synthesize
  intermediate intensities that read as dimming/blur on LEDs and cost 4×
  the samples.
- *Scan-region bounding via convexity*: rotation is affine; affine maps
  preserve convex hulls; therefore the image of the source rectangle is
  contained in the convex hull of its four mapped corners, and the
  axis-aligned bounding box of those corners (clamped to dst) is a
  **sound but not tight** scan region — the rotated rectangle inscribes
  its AABB leaving four empty corner triangles, up to ~40% over-scan at
  45°. Those samples inverse-map outside the source and cheap-reject via
  `src.get(...) is None`. Tightening (per-row span walking) is possible
  but YAGNI at this frame budget; the honest cost model in §5 accounts
  for the loose bound.

### 3. Widget integration — `TickerMessage.draw` gets SMALLER

The v1 inline policy (buffer construction + blit + pivot math) is replaced
by the two `RotationSurface` calls. The visible-extent pivot formula
(`(max(0, start_pos) + min(canvas.width, start_pos + content_width)) / 2`,
in logical coords) stays at the widget — it is text-layout policy, not
rotation policy.

**Hires-font guard:** deleted for scaled canvases (hires fonts now render
into the wrapped buffer correctly). Retained ONLY for `scale == 1` +
`HiresFont` — where the buffer is bare and `_draw_hires_text` would paint
real-pixel-sized glyphs into logical space (garbage). That configuration
is already flagged by validate rule 59 (hires font on a scale-1 display).
The guard's warning text drops the "until physical-resolution rotation
ships" clause.

**Rule 63 becomes scale-aware:** fires only when **`section.scale == 1`**
— the per-section RESOLVED scale (each section's `scale` defaults to
`display.default_scale` but can be overridden; gating on the global would
mis-fire for scale-overriding sections — antagonist Finding 5; the field
is already in scope in rule 63's section loop). Message updated: hires
fonts don't rotate *on scale-1 sections*. On the bigsign the rule is
silent because the feature now works.

### 4. Future transition reuse (kept in mind, not built)

A rotation transition constructs its surface ONCE (in `__init__` or
lazily on first `frame_at`) and per compositing tick does:
`surface.clear()` → draw the outgoing widget into `surface.target` at
pos 0 → `surface.blit(angle(t), canvas.width / 2)` → draw incoming per
its own schedule. The construct-once/clear-per-frame shape (§1) exists
precisely so a transition's 20–60 `frame_at` calls don't pay 20–60
buffer allocations + wrapper constructions (antagonist Finding 4).
Nothing in `RotationSurface` assumes a widget, an animation, or a frame
counter — its inputs are a canvas, draw calls against a target, an
angle, and a pivot. The seam is transition-ready by construction; no
transition code ships in this PR.

### 5. Performance — measured, not assumed

**Model** (*asymptotics + constant factors*): the blit is `O(A)` where `A`
is the clamped AABB area. On the scaled path the buffer is panel-shaped,
so a rotated full-panel rectangle's AABB fills the panel at essentially
every non-axis angle: **~16,384 destination samples per spin frame is the
TYPICAL cost, not a worst case** — the AABB bound buys nothing here
(antagonist Finding 1; it helps only near axis angles). Pure Python
(~0.3–1 µs/iteration of interpreter overhead dominates; the FP math is
negligible): estimated 5–16 ms/frame on desktop, 2–3× that on a Pi 5 —
against the 50 ms tick budget, and ONLY during the ~1 s spin window
(`angle % 360 != 0`); at rest the cached surface sits idle.

The **draw half** must be measured too, not just the blit: at scale 4
every lit logical pixel writes a 4×4 block through the wrapper's
`SubFill` — same per-write shape as a normal scaled draw, but into
list-slot stores instead of the C canvas's block fill, so the buffer draw
can be SLOWER than the real-canvas draw it mirrors. The benchmark times
both halves (draw-into-wrapped-buffer + blit) as one per-frame unit.

**Gate:** the implementation plan includes a micro-benchmark task —
`rotate_blit` at 256×64 across representative angles (0.1°, 45°, 90°,
137°), timed on the dev machine with the Pi factor applied, plus a
headless engine-tick timing via the existing smoke harness at bigsign
dims. **Acceptance: p95 blit ≤ 15 ms on-target-equivalent.** Results are
recorded in the PR description.

**Fallback (documented, only on a failed gate):** rotate at half-physical
resolution — buffer at `(w_real/2, h_real/2)`, and the 2×2 expansion comes
FREE from the existing machinery by passing `ScaledCanvas(real, scale=2)`
as the blit's `dst` (its SetPixel writes 2×2 blocks). Honest accounting
(antagonist Finding 6): this is a constructor branch PLUS halved
pivot/`cy` arguments to `rotate_blit` — `RotationSurface.blit` owns that
arithmetic, so *callers* still see no change, but it is not
"constructor-only." Quarters the scan (4,096 samples), stays 2× finer
than v1. Second-tier fallback (not designed now): per-spin caching of the
rendered buffer (sound only when `font_color.frame_invariant` — per-char
animated colors repaint per tick; *memoization requires referential
transparency*, and a Rainbow mid-spin isn't).

### 6. Out of scope

- Any rotation transition (seam-ready only).
- Interpolation upgrades (bilinear/supersampling) — wrong for LEDs, see §2.
- numpy (transitive dependency only — not a platform we may build on).
- gif/image overlay rotation (unchanged scope-out from the seam spec).
- The propeller docs PR (deferred by the product owner until after this).

## Testing

- **Surface policy:** `make_rotation_surface` at scale 1 returns a bare
  buffer target (and blits identically to v1 — the existing 13 rotation
  tests are the net, they must pass UNCHANGED); at scale N returns a
  wrapped panel-shaped buffer whose `scale`/`content_height`/`y_offset_real`
  match the incoming wrapper.
- **PixelBuffer additions:** `SubFill` fills exactly the clamped block
  (bounds semantics match `SetPixel`); `clear()` resets every slot; a
  wrapped-buffer `draw_bdf_text` succeeds (the AttributeError the draft
  denied — this is the regression pin for §1b).
- **Surface reuse:** two consecutive clear→draw→blit cycles on ONE surface
  produce independent, correct outputs (no bleed-through from frame 1
  into frame 2 — pins the construct-once contract).
- **Physical fidelity:** on a scale-4 stub canvas, a rotated draw's lit
  physical pixels are NOT constant over each 4×4 block at a non-axis angle
  (proves rotation happened at physical granularity, not logical-then-
  expanded). At 0° the output is byte-identical to the unrotated draw.
- **Pivot mapping:** a 180° physical rotation of a known asymmetric
  pattern maps its lit-pixel set exactly through
  `(x, y) → (2·cx_phys − x, 2·cy_phys − y)` with `cx_phys = cx_logical ·
  scale` (catches any half-block pivot bias or scale-map error).
- **Hires paths:** hires emoji sprite pixels present in the rotated
  physical output (the settle-pop eraser); hires font glyphs render
  rotated on a scaled canvas without the guard firing; guard still fires
  at scale 1 + HiresFont (caplog).
- **Rule 63 scale-awareness:** fires at scale 1, silent at scale 4.
- **Perf:** the micro-benchmark (not a CI assert — a plan task with
  recorded numbers).
- **Visual (docs/visual-validation.md matrix):** bigsign-geometry configs —
  propeller + hires font, propeller + emoji (verify NO settle pop:
  no long-frame content change at the settle boundary), overflow at
  scale 4, plus a smallsign regression render.

## Process

Antagonistic optimization-engineer reviews at: this spec (next step), the
plan, each task review (added lens), and the final whole-branch review.
Standard per-task spec/quality reviews continue as usual.

---

## REVISION 2 — snapshot-artifact architecture (supersedes §1's per-frame draw and §5's half-res-draw fallback)

**Origin:** the Task-5 perf gate FAILED for full-resolution per-frame
blitting (measured 16.4 ms desktop ≈ 49 ms on-target; even DDA+extent and
PIL-C-rotate variants fail — the per-pixel canvas WRITE is the interpreter
floor). The half-res-draw fallback passed (2.1 ms) but forced hires emoji
to lo-res mid-spin (fixed-size sprite art is 2× oversized in a half-res
buffer), keeping the settle pop. The PRODUCT OWNER then asked the
right question: why draw per frame at all, instead of snapshotting the
screen-state artifact once and spinning THAT? Answer folded in here.

### R2.1 Architecture

Per spin (not per frame):
1. **Snapshot** — at spin entry, run the widget's normal draw branches ONCE
   into the full-resolution artifact (`surface.target`, exactly §1's
   wrapped panel-shaped buffer — every paint path is correct by
   construction: hires fonts, hires emoji, per-char colors).
2. **Downsample** — `surface.snapshot()` box-downsamples the full-res
   artifact 2× into an owned half-res buffer. **Box any-lit sampling, NOT
   nearest** (*Nyquist/aliasing*: nearest at stride 2 drops 1-px strokes at
   odd coordinates — a decimation without a low-pass step loses
   sub-stride features; the any-lit box is the cheap morphological
   dilation-flavored low-pass that preserves them). Color = first lit of
   the 2×2 block (adjacent pixels share a char's color; exactness is not
   load-bearing on an LED at half detail mid-spin). ~16 K reads ONCE per
   spin — inside one tick's budget.
3. **Per frame** — `blit(canvas, angle, cx_logical)` rotates the HALF-RES
   artifact through a construct-once `ScaledCanvas(real, scale=2,
   content_height=h_real//2)` dst wrapper (y_offset 0 — the artifact
   already contains the panel layout). Pivot in half-space:
   `(cx_logical · scale / 2, h_real / 4)`. Measured: **2.1 ms desktop ≈
   6.4 ms on-target — passes the 15 ms gate 2.4× under.**
4. **Settle** — rotation returns to 0 → the normal live draw resumes at
   full detail (no buffer involved).

Scale-1 canvases take the SAME snapshot-once lifecycle with no downsample
step (the artifact is blitted directly) — uniform semantics across signs.

### R2.2 What this fixes vs the half-res-draw fallback

- **Hires emoji spin correctly sized** (they render into the full-res
  artifact; the downsample scales them like every other pixel). The
  settle "pop" stops being an ART SWAP (lo-res sprite ↔ hi-res sprite)
  and becomes a uniform gentle detail-sharpening at settle — same class
  as the fonts. The spec's third goal is (largely) restored.
- **Per-frame work is minimal by construction**: the draw happens once
  per spin, not 20×. Maximal answer to the antagonist's per-frame brief.
- **One path.** No hybrid, no emoji special-casing, no per-frame draw.

### R2.3 The disclosed trade-off (product-owner ACCEPTED)

Animated color providers (rainbow / color_cycle / shimmer) FREEZE for the
duration of the spin: the artifact is a memoized render, and re-rendering
per frame for animated colors measures ~30 ms on-target (fails the gate).
The sweep freezes mid-spin (~1 s, during a motion blur), and resumes from
its live phase at settle (the frame counter never stops — `frame_for`
advances regardless; only the RENDER is frozen). *Memoization requires
referential transparency* — we deliberately relax it mid-spin because the
observable divergence during rapid rotation is negligible, and restore it
at rest. Applies uniformly at every scale (smallsign spins previously
redrew per frame with live colors; they now freeze too — accepted).

### R2.4 Snapshot lifecycle (widget policy)

`TickerMessage` snapshots at spin ENTRY (first draw with
`rotation % 360 != 0` and no valid artifact) and invalidates on:
`reset_frame()` (visit restart → next spin re-snapshots), a `matches()`
rebuild (geometry change), and rotation returning to 0 (settle). Skip
frames (valid artifact) do NOT run the text branches — the cursor advance
is recomputed from the cached `content_width` exactly as the animation
path already does. Token resolution: already frozen during animation
holds by the `_resolution_locked` machinery; the snapshot adds no new
staleness class.

### R2.5 Perf gate — REVISED NUMBERS (measured)

- One-time (per spin): full-res draw + box-downsample ≈ 0.7–3 ms desktop
  (≤ ~10 ms on-target) — inside a single 50 ms tick.
- Per frame: half-res blit 2.1 ms desktop ≈ 6.4 ms on-target. PASS.
- The Task-5 benchmark is re-pointed at this shape (one-time cost + steady
  per-frame cost, reported separately; the bench's silently-skipped hires
  draw half is also fixed — antagonist finding).

### R2.6 Superseded

- §1's per-frame `clear()` + redraw model (replaced by snapshot-once; the
  construct-once surface + `clear()` primitive remain — `snapshot()` uses
  them).
- §5's half-res-DRAW fallback (the artifact path downsamples a full-res
  render instead of drawing at half-res — emoji sizing stays correct).
- The "no settle pop" descope from the failed-gate deliberation.

---

## REVISION 3 — corrected gate numbers + the optimized blit (antagonist round 3 folded in)

The R2 antagonist review found **both R2.5 benchmark numbers invalid**:
(H1) the per-frame bench's dst wrapper used `content_height=16`, clipping
the blit to HALF the panel — the honest full-panel half-res blit measured
~9.4 ms desktop ≈ 28 ms on-target, FAILING the gate R2 claimed to pass;
(H2) the one-time bench measured the NEAREST downsample (single cold
iteration) instead of the mandated any-lit box — honestly ~11 ms/scan.
(H3) the "invalidate on rotation returning to 0" lifecycle rule can
discard the artifact MID-SPIN (the post-mod angle passes through 0 each
revolution and can land on an integer frame for realistic
revolutions/frame-count pairs).

**Resolutions (all measured, identical-output-verified):**

1. **Optimized blit inner loop** — same inverse-mapping algorithm,
   mechanical speedups only: *forward differencing* (DDA — per-row
   incremental `sx += cosθ, sy −= sinθ` replaces per-pixel matrix
   evaluation; the classic scanline-rasterization transform), `int(x+0.5)`
   truncation instead of two `round()` calls, hoisted method refs +
   direct slot indexing (the per-sample cost was interpreter call
   ceremony, not arithmetic), and a scan region derived from the
   ARTIFACT'S LIT EXTENT (tracked during writes — 4 compares per write)
   instead of the full buffer rect. Output is byte-identical to the
   baseline blit (asserted at arbitrary angles). **0.63 ms desktop ≈
   1.9 ms on-target — passes the 15 ms gate 8× under.** `rotate_blit`
   gains an optional `src_extent` parameter (default = full rect,
   back-compat); `PixelBuffer` tracks `lit_extent`.
2. **Extent-scoped any-lit downsample**: 0.86 ms one-time (vs 11 ms
   full-scan) using the same tracked extent.
3. **Lifecycle (H3)**: artifact invalidation on VISIT BOUNDARY ONLY
   (`reset_frame()` + `matches()` rebuild). `rotation % 360 == 0` gates
   the live-draw-vs-blit OUTPUT decision per frame; it never invalidates
   the artifact.
4. **Bench methodology pinned for Task 5**: full-panel dst geometry
   (`content_height = h_real // 2`), any-lit downsample, C-call-modeled
   dst SubFill (production SubFill is the core.pyx C binding — a Python
   expansion-loop stub overstates the cost), warmed p95.

R2's architecture stands; only its evidence and the two flagged rules
changed. Cleared by the round-3 review: half-space pivot math
(`cx_logical·scale/2, h_real/4` with the `content_height=h_real//2` dst
wrapper), any-lit honesty (dilation-biased — strokes thicken, sub-half-px
gaps may close; disclosed as mid-spin-only cosmetics), memory
(~160 KB/rotating widget), transition reuse (snapshot-once is exactly the
transition shape), scale-1 uniformity.

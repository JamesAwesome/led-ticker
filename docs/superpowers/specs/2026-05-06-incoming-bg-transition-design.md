# `incoming_bg_color` plumbed into `run_transition`

**Status:** Design draft. Awaiting confirmation before implementing.

**Goal:** Eliminate the visual flash when transitioning into a section
with a different `bg_color` than the previous section had on screen.
Today the panel goes black during the transition and snaps to the
incoming section's `bg_color` only once the transition completes —
visible as a stutter on bright-bg sections (showroom §8 yellow being
the worst case, going from black-during-pokeball to bright-yellow
in one tick).

**Branch:** `feat/incoming-bg-transition` off main. Worktree at
`.claude/worktrees/incoming-bg-transition` (already created).
Single PR.

---

## Diagnosis (from user investigation)

User reported a stutter "just as §8 (BUILT TO BE SEEN) appears,
every iteration." Diagnosis ruled out cold-cache, per-tick budget,
and transition compute issues. Root cause: `run_transition`'s
compositor calls `active.Clear()` per frame (line 149,
`transitions/__init__.py`) — explicitly painting black between any
widget content the compositor draws. CLAUDE.md called this an
"accepted footgun per the bg-color design spec":

```python
# Transition compositing intentionally ignores bg_color — between
# two sections with different bgs, the dissolve flashes through
# black rather than coupling transition logic to widget state.
# Accepted footgun per the bg-color design spec.
active.Clear()
```

Frame-by-frame on the §7→§8 boundary:

| Frame | Visual | Avg brightness |
|---|---|---|
| Last pokeball frame (t=1.0 of transition) | Black bg, Pikachu offscreen | ~5% |
| First §8 frame (`reset_canvas` → `Fill(yellow)`) | Yellow bg + black text + rainbow border | ~70% |

That single-tick 14× brightness step reads as a flash. Now that
multiple showroom sections use `bg_color` (§5 wine, §8 yellow), it's
worth fixing the engine instead of working around per-section.

---

## Design

Plumb `incoming_bg_color` into `run_transition` mirroring the
existing `incoming_scale` / `incoming_content_height` pattern (which
already switches the canvas at t ≥ 0.5 to dissolve the incoming
widget at its native size).

### API change

`transitions/__init__.py:run_transition`:

```python
async def run_transition(
    canvas: Canvas,
    frame: Any,
    outgoing: Any,
    incoming: Any,
    transition: Transition,
    duration: float = 0.5,
    easing: str = "linear",
    scroll_speed: float = 0.05,
    outgoing_scroll_pos: int = 0,
    region: Any = None,
    incoming_scale: int | None = None,
    incoming_content_height: int = 16,
    incoming_bg_color: tuple[int, int, int] | None = None,  # NEW
) -> Canvas:
    ...
```

### Compositor change

In the per-frame loop, replace the unconditional `active.Clear()`
with a t-aware reset:

```python
# Before t=0.5 the outgoing section is dominant — Clear (black)
# matches the legacy behavior so we don't change the look of
# transitions between two no-bg sections. After t=0.5 the
# incoming section's bg fades in: any incoming_bg_color paints
# instead of Clear, so the panel ramps to the incoming bg
# brightness over the second half of the transition rather than
# snapping at t=1.0.
if t >= 0.5 and incoming_bg_color is not None:
    reset_canvas(active, incoming_bg_color)
else:
    active.Clear()
```

`reset_canvas` is already in `widgets/_image_fit.py` and handles
the None-vs-tuple case (calls `Clear()` when bg is None,
`Fill(*bg)` otherwise). Reuse it for consistency.

### Threshold rationale

`t >= 0.5` matches the existing `incoming_scale` switch threshold.
Same midpoint feels coherent: by the visual midpoint of the
transition, the incoming section's "frame" (scale + bg) is in place
and the incoming widget begins dissolving in.

For pokeball-style transitions where Pikachu chases a ball across
the panel, this means: first half is Pikachu on outgoing-bg (typically
black for transitions between no-bg sections), second half is Pikachu
on incoming-bg (yellow for §8). The brightness ramps up smoothly
instead of clifftop.

### Plumbing

`app.py:run`'s call to `run_transition` (the inter-section call,
~line 666 area) needs to pass `incoming_bg_color=section.bg_color`.
`SectionConfig.bg_color` is already a `tuple | None`, so direct
passthrough.

The other `run_transition` call site is in `_run_swap` for the
inter-WIDGET transitions within a section. There the incoming widget
is in the SAME section as outgoing, so `incoming_bg_color` would be
the section's bg (or None). Same plumbing rule.

---

## Edge cases

**1. None bg → None bg (no-bg sections transitioning between each other)**

`incoming_bg_color is None` → falls through to `active.Clear()`.
Identical to current behavior. **No visual change for sections
without `bg_color`.**

**2. Some-bg → None bg (yellow §8 → black §9)**

t < 0.5: Clear (black) — outgoing was on yellow but transition
fades to black anyway. Behavior matches today's "flash through
black" design.
t ≥ 0.5: incoming_bg=None → Clear. Same.

The §8→§9 boundary still has a black flash, but going from yellow
to black is *less* jarring than black to yellow (eye adapts faster
to dimming than brightening). Acceptable; matches existing behavior
for transitions out of bg sections.

**3. Some-bg → Some-bg (e.g. yellow → wine)**

Both sections have bg. t < 0.5: black. t ≥ 0.5: wine. The yellow
→ black → wine sequence is more dramatic than necessary, but
it's also the rare case (no two adjacent showroom sections both
have bg today). Improvement over today, where it'd be yellow →
black → wine SNAP at t=1.0. Could optimize later by also tracking
`outgoing_bg_color` and cross-fading; **out of scope for v1**.

**4. Cross-scale transitions**

`incoming_scale` and `incoming_bg_color` switch at the same
threshold. The wrapper switch and the bg switch happen in the
same frame, which is the intended visual: at t=0.5 the section's
frame (scale, bg, content_height) is established and the widget
fades in.

---

## Test plan

`tests/test_transitions.py::TestRunTransition`:

1. **`test_clear_used_when_incoming_bg_color_is_none`** — default
   behavior. Spy on `Clear()` calls; with `incoming_bg_color=None`,
   every transition frame calls Clear (no Fill).
2. **`test_incoming_bg_color_fills_after_midpoint`** — pass
   `incoming_bg_color=(255, 230, 80)`. Spy on Fill calls; assert
   Fill(255, 230, 80) fires at t≥0.5 frames and Clear fires at
   t<0.5 frames.
3. **`test_incoming_bg_color_threshold_matches_incoming_scale`** —
   when both `incoming_scale` and `incoming_bg_color` are set, the
   bg switch happens at the SAME frame as the wrapper switch. Pin
   this behavior so a future refactor can't desync them.

`tests/test_app.py`:

4. **`test_run_passes_section_bg_color_to_run_transition`** —
   integration test asserting `_run`'s inter-section call propagates
   `section.bg_color`. Mock `run_transition` and inspect kwargs.

---

## CLAUDE.md update

Replace the "Accepted footgun" comment in `transitions/__init__.py`
with a note that explains the new behavior. In CLAUDE.md (currently
the `### Transition System` section), update or add:

> **Inter-section bg_color**: when `run_transition` is called with
> `incoming_bg_color` set, the panel ramps to the incoming bg over
> the second half of the transition (`t ≥ 0.5`, same threshold as
> `incoming_scale`). Without this, the engine paints black between
> sections per the "Clear before transition compositor" pattern,
> producing a visible flash on bright-bg sections (e.g. yellow §8
> in the showroom). The bg switch composes with `incoming_scale`'s
> switch — both happen in the same frame at midpoint.

---

## Effort

- Code: ~20 LOC (parameter, conditional, plumbing in 2 call sites)
- Tests: ~80 LOC (4 tests)
- CLAUDE.md: ~3 lines updated

Total: ~100 LOC. Single commit, single PR. ~30 min implementation
once spec is locked.

---

## Open questions

1. **Threshold value**: t ≥ 0.5 matches `incoming_scale`. Worth
   exposing as a parameter? My instinct: no — locked at 0.5 keeps
   the API surface small and matches the existing convention.
   Revisit only if a future use case wants asymmetric scale/bg
   timing.

2. **Cross-fade outgoing→incoming bg**: out of scope per the
   "some-bg → some-bg" edge case discussion above. Defer until a
   real use case demands it.

3. **Backward compat**: existing call sites that don't pass
   `incoming_bg_color` get the legacy Clear() behavior. Zero
   regression for sections without bg_color. Confirmed by the
   "None case" edge analysis above.

---

## Ready signal

Confirm the spec looks right and I'll execute on the worktree's
branch + open the PR.

# Defer-to-rest transition handoff (`frames_to_rest`) — Design

**Issue:** [#305](https://github.com/JamesAwesome/led-ticker/issues/305) — Safeguard discrete-cycle color providers (shimmer) against being cut short by a transition.

**Date:** 2026-07-01
**Status:** Approved (brainstorm + PM/engineer persona debate on cap policy +
antagonist review — 10 findings, all adjudicated and folded in below)

## Problem

The hold→transition handoff is a pure elapsed-time gate with zero awareness of
animation phase. Two visible artifact classes:

- **Shimmer** (cyclic sweep + pause): a `cut` can fire mid-sweep. The incoming
  widget's counter starts at frame 0, so the bright spot teleports from
  mid-text to the left edge. Cosmetic, reads as choppy.
- **Typewriter** (one-shot reveal, ~0.15 s/char at defaults): a hold shorter
  than the typing duration chops the message mid-type — the viewer never sees
  the full text. Content failure, and the remainder can be seconds.

## Decision summary

Issue #305 proposed a boolean `at_rest()` + a per-tick settle loop (its
"Option A"). This design supersedes that mechanism with a **compute-once
`frames_to_rest` + one extended `_hold_ticks` call** ("A′") — same seam,
simpler mechanics:

- No new engine loop: the extension reuses `_hold_ticks`, so hardware
  constraints #1 (swap capture) and #12 (advance-per-tick; enforced by the
  `tests/test_engine_redraw_contract.py` AST tripwire) are inherited, not
  re-implemented.
- No per-tick polling: one integer computed at hold expiry.
- **All-or-nothing cap**: if the remainder exceeds the cap, don't extend at
  all — never pay latency without a clean landing. (The settle-loop shape
  can't make this distinction; it always burns the full cap on a
  never-resting effect.)

Alternatives examined and rejected during brainstorm: phase carry-over
(fragile across differing char counts — also rejected in the issue), static
hold quantization (impossible: Shimmer's `restart_on_visit=False` counter
makes entry phase unpredictable), global-clock phase (breaks the
`pause_frame`/`resume_frame` transition-freeze contract), cut-only scoping
(conditional complexity for marginal savings), seeding the incoming at rest
(half-measure; unnecessary once the outgoing lands at rest).

**Cap policy** (PM + engineer personas, unanimous): **uniform ~1 s cap for
every effect** + a **validate warning** for the typewriter-duration
misconfiguration. No two-tier / one-shot-aware cap: a >1 s slip breaks
rotation-budget and scheduling assumptions, and one-shot-vs-cyclic is an
implementation distinction users don't hold. A bigger one-shot cap remains a
possible deliberate follow-up if support burden appears — not now.

## Design

### 1. Provider seam — `src/led_ticker/color_providers.py`

`ColorProviderBase` — the concrete class every shipped provider actually
inherits (`ColorProvider` at `color_providers.py:64` is a `typing.Protocol`;
a default added there would be runtime-invisible) — gains:

```python
def frames_to_rest(self, frame: int, total_chars: int) -> int:
    """Frames until this effect reaches a natural rest point.

    0 = at rest now, or no rest concept (never defers a transition).
    """
    return 0
```

All existing providers except Shimmer inherit the default (`_ConstantColor`,
`Random`, `Gradient`, `Rainbow`, `ColorCycle` → never defer).

`Shimmer` overrides it. The cycle math (`sweep_frames`, `pause_frames`,
`cycle_frames`) is **factored into one private helper** (e.g.
`_cycle_geometry(total_chars) -> tuple[float, float]`) used by *both*
`color_for` and `frames_to_rest`, so the two can't drift.

```
t = frame % cycle_frames
pause_frames < 1      -> 0        # no LANDABLE rest tick exists; never defer
t >= sweep_frames     -> 0        # inside the pause window
else                  -> ceil(sweep_frames - t)
```

**Edges:** `pause = 0.0` is a legal Shimmer config (cycle == sweep; a "rest
frame" is instantly the next sweep's frame 0). And **any sub-frame pause is
just as unlandable** (antagonist finding): advancing by
`ceil(sweep_frames - t)` lands at `t' ∈ [sweep_frames, sweep_frames + 1)`,
which is inside the pause window only when `pause_frames >= 1` — with
`pause = 0.02` (`pause_frames = 0.6`) the settle would overshoot into the
next sweep. Hence the guard is `pause_frames < 1 -> 0`, not `pause == 0`.
The provider seam applies duck-typed at the widget layer, so third-party
providers that don't inherit `ColorProviderBase` simply never defer.

### 2. Animation seam — `src/led_ticker/animations.py`

Same duck-typed signature on `Typewriter`:

```python
def frames_to_rest(self, frame: int, total_chars: int) -> int:
    done_frame = self.frames_per_char * (ceil(total_chars / self.chars_per_frame) - 1)
    return max(0, done_frame - frame)
```

One-shot semantics: monotonically decreasing, `0` forever once fully typed.
The `Animation` Protocol documents the optional method. The **typing-duration
formula lives here only** — the validate rule (§5) imports it, never
re-implements it.

**Char count is `len(full_text)` — raw, emoji-inclusive** (antagonist
finding, Critical): `Typewriter.frame_for` slices
`full_text[:chars_visible]` against `len(full_text)`
(`animations.py:73-75`), so its rest math must use the same raw length. The
color-provider count (`count_text_chars`, emoji-excluded) is a *different
quantity* — feeding it here under-counts emoji text, returns 0 mid-type, and
reintroduces the exact chop this design exists to prevent. Animation and
color-provider effects therefore get **per-effect-kind counts** in §3, not
one shared number.

`chars_per_frame` stays in the formula: the TOML dict form
(`{style = "typewriter", ...}`) passes arbitrary kwargs to the constructor
(`coercion.py:_coerce_animation`), so it is user-reachable even though only
`frames_per_char` is advertised.

### 3. Widget seam — `src/led_ticker/widgets/_frame_aware.py`

`FrameAwareBase` gains:

```python
def frames_to_transition_ready(self) -> int:
    """Max frames_to_rest across this widget's animated effects.

    Duck-typed per effect; must NEVER raise (mirror the should_display
    contract) — any error inside -> 0 (ready now). A readiness check may
    never stall or crash the render loop.
    """
```

- Iterates `_iter_effects()` (which already spans `_EFFECT_ATTRS`, including
  `animation`); duck-types each effect for `frames_to_rest` — effects without
  it (e.g. `BorderEffect`s, which have no rest concept today and are **out of
  scope**) contribute 0.
- Calls each with `self.frame_for(attr)` and that effect's char count.
- **Char counts must match what each effect actually consumes — per effect
  kind, not one shared number.** The overridable hook is
  `_effect_total_chars(attr_name) -> int`; each widget returns:
  - **color-provider attrs** (`font_color`, `top_color`, `bottom_color`, …):
    the same anchor the draw path passes to `color_for`
    (`count_text_chars(full_text)` on the emoji path, else
    `len(full_text)`) — factored from the draw path, not duplicated;
  - **`animation`**: `len(full_text)` raw (see §2 — Typewriter's own reveal
    length).

  `TickerMessage` implements both; `TwoRowMessage` per row (`top_color` →
  top text, `bottom_color` → bottom text; it has no `animation` field). The
  `FrameAwareBase` default returns a safe fallback derived from
  `getattr(self, "text", "")` (or 1) so untouched widgets don't break.
- Whole exception-wrapped: `try/except Exception -> return 0`.

### 4. Engine — `src/led_ticker/ticker.py`

One settle site at the hold→transition handoff in `_swap_and_scroll`, after
the final hold and before the function's terminal `return` — covering the
**two hold-terminated branches** (held-only, and scrolled-then-held). The
`forces_offscreen_scroll` and `wraps_forever` branches `return` early and
are **excluded by design** (antagonist finding): no rest-having effect
applies on those paths today; if a shimmer on a wrap-row ever matters, the
settle would need its own site there (noted, not built — YAGNI).

```python
MAX_SETTLE_TICKS = 1000 // ENGINE_TICK_MS  # ~1 s; module-level constant

extra = <duck-typed widget.frames_to_transition_ready(); getattr + try/except -> 0>
if 0 < extra <= MAX_SETTLE_TICKS:
    canvas, _ = await self._hold_ticks(canvas, ticker_obj, extra, pos, bg_color)
```

- **All-or-nothing:** `extra > MAX_SETTLE_TICKS` → no extension at all.
- Reuses `_hold_ticks` → constraints #1/#12 and breaker guarding inherited.
- **Breaker guard:** skip the settle entirely when
  `self.breaker.is_disabled(ticker_obj)` — a widget tripped during the hold
  must not buy up to ~1 s of extra blank-draw time (antagonist finding).
- The engine-side call is defensive (duck-typed + try/except → 0) even though
  the widget method also never raises — belt and suspenders around the render
  loop.

**Scope-out:** `play()`-style widgets (gif/image text overlays) own their
render loop and don't route through `_swap_and_scroll`'s holds — excluded. A
shimmer on a gif overlay keeps today's behavior. A follow-up could add the
same handoff inside `_play_with_text` if anyone hits it.

**Modes:** the seam fires where holds precede transitions — slideshow mode's
held/scrolled text path. `ticker` and `one_at_a_time` modes never call
`_swap_and_scroll` at all (`_scroll_side_by_side` / `_scroll_one_by_one` are
separate paths), so they're unaffected structurally, not by a flag. Within
`_swap_and_scroll`, the settle additionally sits inside the `not continuous`
guard alongside the holds it extends.

### 5. Validate rule 61 + startup warning — `src/led_ticker/validate.py`, `src/led_ticker/app/run.py`

**Rule 61 (warning):** a `typewriter` animation whose typing duration exceeds
the widget's effective hold time. Typing duration is computed by **calling the
shared formula from §2** (import from `animations.py`), converted via
`ENGINE_TICK_MS`.

**Effective hold mirrors the engine's actual math** (antagonist finding):
`effective_hold = max(section.hold_time, widget.hold_time or 0.0)` — the
engine resolves per-widget hold with `max()` (`ticker.py`, the
`hold_time = max(hold_time, getattr(widget, "hold_time", 0.0))` site), and
there is **no display-level `hold_time` tier** (`DisplayConfig` has no such
field). Rule 61 must not invent an override chain the engine doesn't have.

**`ENGINE_TICK_MS` moves to a leaf module** (antagonist finding): it
currently lives in `ticker.py`; importing it from `validate.py` would drag
the engine (and transitively the widget/drawing stack) into the static
preflight. Relocate the constant to a leaf home (new
`src/led_ticker/constants.py`), with `ticker.py` re-exporting it for
existing internal importers. `validate.py` and `animations.py` then import
the leaf.

Message shape (numbers + both fixes + the tail-hold note the PM flagged):

> `text takes ~6.0s to type but hold_time is 3.0s — the message will be cut
> mid-type. Raise hold_time to at least 6.0, or shorten the text. (After
> typing completes, the widget holds fully-typed for the remainder.)`

**Startup surfacing:** the same warning is logged at config-load in
`app/run.py` (`logging.warning`, matching the existing plugin-dependency
startup-warning pattern) so users who never run `validate` manually still see
it in `make logs`. The web UI config editor gets it for free (its PUT
validates).

### 6. No config knob

The behavior is automatic, bounded (≤ ~1 s), and invisible when nothing needs
it. No TOML field.

### 7. Docs

- Color-providers page, Shimmer section: one note — transitions wait up to
  ~1 s for the sweep to reach its pause before firing.
- Animations page, Typewriter section: note the validate warning and the
  hold_time relationship.
- **Plugin API surface** (antagonist finding): `FrameAwareBase` is exported
  via `led_ticker.plugin`, so `frames_to_transition_ready` +
  `_effect_total_chars` are additive, non-breaking API surface plugin
  widgets inherit. Update the docs-site Plugin API reference page (it is
  drift-guarded by `tests/test_docs_plugin_api_drift.py` — the guard will
  force this anyway) documenting both: default behavior, override contract
  (never raise; per-effect-kind counts).
- Per `docs/DOCS-STYLE.md`.

## Testing

**Shimmer math** (`tests/` unit):
- Mid-sweep: `frames_to_rest` returns the exact remaining frames; advancing
  by that amount always lands `t >= sweep_frames` (property-style check over
  a range of frames, when `pause > 0`).
- Whole pause window → 0; boundary at `sweep_frames` exact.
- Wrap-around (frame beyond one cycle).
- `pause = 0` → always 0; **sub-frame pause** (`0 < pause_frames < 1`, e.g.
  `pause = 0.02`) → always 0 (the overshoot edge).
- `color_for`/`frames_to_rest` share geometry: mutate via the single helper
  in a test double or assert both consume `_cycle_geometry`.

**Typewriter math:**
- Mid-type: exact remaining; done → 0 forever; `chars_per_frame > 1`.
- **Emoji text uses the raw length**: a `:slug:`-bearing message computes
  `frames_to_rest` against `len(full_text)` and stays > 0 until the full raw
  string (slug included) has revealed — guards Critical finding 1.
- **Formula-equality tripwire** (engineer persona): the validate rule's
  duration and `Typewriter.frames_to_rest`-derived duration agree for the
  same inputs — guards against a future re-implementation drifting.

**Defaults:** every other provider returns 0 (parametrized).

**Widget seam:**
- Max across multiple effects; raising effect → 0 (never propagates).
- `_effect_total_chars` matches the draw-path count for text with and
  without emoji (`TickerMessage`, per-row `TwoRowMessage`).

**Engine:**
- Stub widget reporting K (0 < K ≤ cap) → transition deferred exactly K
  ticks, `advance_frame` + `draw` called per settle tick, swap captured.
- Stub reporting cap+1 → **zero** deferral (all-or-nothing).
- Raising stub → zero deferral, no crash.
- **Breaker-tripped widget** (tripped during the hold) → zero deferral (the
  `is_disabled` guard), no blank-draw settle.
- Widget without the method → byte-identical behavior to today.
- `tests/test_engine_redraw_contract.py` stays green (reused loop; no new
  `_swap(` call sites beyond the expected count).

**Validate:**
- Rule 61 fires with the right numbers; doesn't fire when hold is
  sufficient; mirrors the engine's `max(section, widget)` hold math
  (including a widget `hold_time` *smaller* than the section's — max wins,
  no false fire).
- Startup log emission test (pattern-match the warning at config load).
- `ENGINE_TICK_MS` re-export: importing it from `ticker.py` still works
  (back-compat for existing internal callers).

## Out of scope

- `BorderEffect.frames_to_rest` (no border effect has a rest concept).
- `play()`-style widgets' text overlays (documented scope-out; follow-up seam
  exists in `_play_with_text`).
- Two-tier / one-shot-aware settle cap (deliberate possible follow-up, per
  the persona debate — only if real support burden appears).
- Seeding the incoming widget's phase (rejected alternative).

## Contributor process

- Branch + PR only; never commit to `main`. `make dev` in the worktree;
  `uv run --extra dev ruff check src/ tests/` and `ruff format` before push;
  full `make test` (the repo-wide meta-tripwires only fire on the full
  suite).

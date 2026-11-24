# Antagonistic review ledger — PR #566 (frame cadence, #525)

Protocol: fresh adversarial reviewer per cycle, mechanism-first (state → trigger → observable failure), no padding.
One fix pass per cycle. Exit: two CONSECUTIVE cycles with zero in-scope findings. Hard cap 5; if not converged, stop and flag.
Pre-existing issues outside the PR don't count; file as GitHub issues.

Branch: fix/animation-frame-cadence (worktree led-ticker-wt-525). Base: origin/main.

## Cycle 1 — lens: engine seams + settle math + back-compat dispatch
Baseline: 75 passed on the four cadence/settle test files.

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | MED | in-scope (regression on capped signs) | Nominal tick is banked, but `SwapOnVSync(canvas, framerate_fraction)` BLOCKS until a refresh where `frame_count % fraction == 0` (verified in the fork, `lib/led-matrix.cc` UpdateThread::SwapOnVSync → `frame_sync_.WaitOn`). On `limit_refresh_rate_hz = 100` the fraction is 5, so every swap is ≥ 50 ms and a `scroll_step_ms = 35` loop really ticks at 50 ms. Banking 35 → effects run 0.7× (0.4× at 20 ms). Main advanced one frame per real ~50 ms tick there and was correct. | FIX: floor the banked tick at the frame's swap interval (`fraction × 1000 / hz`, exposed via `LedFrame`, duck-typed with int guards so Mock frames floor at 0). Deterministic; a capped sign takes the plain `advance_frame` path and is byte-identical to main. Measured-clock rejected: needs a clock seam, makes cadence tests + render-demo load-dependent. Uncredited draw overrun on uncapped signs stays (closer to correct than main). Reword the (1,5) guarantee to "nominal tick, floored at the swap interval". Eyes-on at a capped sign is James's call. |
| 2 | MED | in-scope (hole in the (1,5) guarantee; byte-identical to main) | Core `SegmentMessage` (plugin export) has its own `advance_frame`, no `advance_frame_elapsed` → still one frame per scroll tick; a `color_cycle` segment row cycles 1.4× faster than TickerMessage rows beside it at 35 ms. | FIX: give `SegmentMessage` its own ms bank (shared helper), zero carry in `reset_frame`; AST tripwire: every core class defining `advance_frame` also defines `advance_frame_elapsed`; docs carve-out → duck-typed widgets. |
| 3 | LOW | in-scope | `_settle_ticks` caps OWED frames, not the delivered extension: `scroll_speed_ms = 2000` owing 1 frame → 1 tick = 2 s hold (main refused). | FIX: refuse when `ticks × tick_ms > MAX_SETTLE_MS`. |
| 4 | LOW | in-scope | Visit-ownership claim/check lives only in `advance_frame`, so sub-frame ticks from a stale visit bank up to 49 ms undetected. | FIX: claim/check in `advance_frame_elapsed` before banking (same order vs pause check as `advance_frame`). |
| 5 | LOW | in-scope (test strength) | (a) `test_paused_does_not_accumulate` passes with the pause guard removed (10×20 ms leaves no residual); (b) `visit_id` forwarding untested on sub-frame ticks; (c) AST tripwire accepts any `tick_ms=` kwarg. | FIX: 9-tick pause test asserting carry; sub-frame visit test; tripwire pinned to `tick_ms=self._scroll_tick_ms`. |
| 6 | DOCS | in-scope | `constants.py` still says `MAX_SETTLE_MS // tick_ms`; `_frame_aware.py` docstring + CLAUDE.md call `_frame_count` "the engine tick counter"; `widget.py` `FrameAwareWidget` Protocol lacks `advance_frame_elapsed`; plugin-system.md carve-out names only plugin play() loops. | FIX all. |

Nothing found (with evidence): `_scroll_tick_ms` rounding exact for 1..5000; settle never under-delivers (≤ N+1 frames when tick > 50); side-by-side dedup unchanged; proxies wrap canvases not widgets; `_hold_ticks`/`_play_no_text` at 50 ms are correct (SUPERSEDED by cycle 2 #4: on caps whose swap interval exceeds 50 ms they were not; floored since a7f2e32e); transitions pause; carry reset on every reset path; paused ticks not banked.

Pre-existing (not counted, ledger only): on a refresh-capped sign `scroll_step_ms`/`scroll_speed_ms` below the swap interval are silently ignored (marquee runs at the swap interval) — candidate validate warning, separate issue. `_hold_ticks` runs slow on refresh caps that don't divide evenly (SUPERSEDED: its frame counter now banks the floored tick — cycle 2 #4; the hold's wall-clock LENGTH still stretches, that part remains pre-existing).

Cycle 1 result: 6 in-scope (0 H / 2 M / 3 L / 1 D) → fix pass.

## Interlude — rebase onto main after #564/#565
PR #566 had `mergeable_state: dirty` so GitHub ran no `pull_request` CI. #564 (fade precursor) merged 2026-11-24 14:47Z and took API `(1, 5)` for the `frame_at` geometry kwargs. This PR's guarantee becomes `(1, 6)`; conflicts in CLAUDE.md, docs/plugin-system.md, api-reference.mdx, plugin.py; drift-test literals in api-reference.mdx + 01-scaffold.mdx move to `(1, 6)`; tests pin `>= (1, 6)`; PR title → API 1.6.

## Cycle 2 — lens: test validity via live mutations (throwaway worktree) + least-examined surfaces + merge check
Head 902ff5b7 (merged with main, API renumbered to (1, 6)). 23 mutants: 20 killed, 1 equivalent (`tick_ms != ENGINE_TICK_MS` dispatch condition is an optimisation — `advance_frame_elapsed(50)` ≡ one `advance_frame`), 2 survived (test gaps below). Both AST tripwires parse the post-merge layout and bite on a reverted site. Merge resolutions verified word-level against both parents: both guarantees present once, nothing dropped.

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | LOW | in-scope | `swap_interval_ms` returns 0 when `framerate_fraction == 1`, but `SwapOnVSync(canvas, 1)` still blocks until the next refresh: with `limit_refresh_rate_hz` in 1..29 (fraction 1) the swap interval is 1000/hz = 34–1000 ms and a 20 ms marquee banks 20 per ≥34 ms real tick (0.5× at 25 Hz; main ran 1.25× there). Unrealistic cap (strobes), hence LOW. | FIX: drop the `fraction <= 1` arm (keep `hz <= 0 → 0`); flip `test_fraction_one_is_no_floor` to expect `round(1000/hz)`. |
| 2 | LOW | in-scope (test gap) | Rounding in `swap_interval_ms` only exercised at hz=100 → `fraction*1000//hz` survives. | FIX: add hz=30 (→67) and hz=110 (→55) cases. |
| 3 | LOW | in-scope (test gap) | `round(scroll_speed*1000)` vs `int(...)` survives; `scroll_step_ms = 1001` is legal. | FIX: parametrised `_scroll_tick_ms == ms` over {29, 1001, 4999} with a Mock frame. |
| 4 | DOCS | in-scope | The (1, 6) text says the guarantee "holds on refresh-capped signs too", but the floor is applied only to scroll-paced loops; the ENGINE_TICK_MS loops (`_hold_ticks`, `_scroll_and_delay` post-scroll hold, gif/still `_play_no_text`) bank 50 per tick, and on caps whose swap interval exceeds 50 ms (30 Hz → 67, 70 → 57, 110 → 55 …) they really tick at that interval → held effects 0.75–0.95×. | FIX by extending the floor rather than qualifying the claim: `_hold_ticks` passes `tick_ms=floor_tick_ms(self.frame, ENGINE_TICK_MS)`; gif/still `_play_no_text` call `advance_frame_elapsed(floor_tick_ms(frame, ENGINE_TICK_MS))`. On uncapped and 100 Hz signs the floor returns 50 → plain path, byte-identical. Docs then stay as written ("every core loop"). |

Nit (not counted): `swap_interval_ms` sits between the `brightness` getter and setter — move below the setter.

Clean with evidence: SegmentMessage pause/reset interplay (no burst possible; `_reset_presenter`/`_show_one` zero carry); headless/render_demo/Mock frames all give nominal; `framerate_fraction` is an attrs default 1 pre-setup so `swap_interval_ms` is 0 until `setup()` (SUPERSEDED by cycle 2 #1: with the fraction-1 arm dropped a capped backend reads `1000/hz` pre-setup, ≤ 33 ms for hz ≥ 30, so `floor_tick_ms` never over-floors — cycle 3); all 7 advance sites enumerated, pacing expressions match; plugins monorepo: all 12 `advance_frame` overrides inherit `FrameAwareBase`; flair's deck snapshot copies `_frame_carry_ms` harmlessly; no `isinstance(FrameAwareWidget)` anywhere.

Pre-existing (ledger only): render-demo stub swap never blocks so GIFs on capped configs run effects fast (same as main); `SegmentMessage` never claims visits; plugin-system.md L238 "upcoming core `fade`" stale (main's text, fix opportunistically).

Cycle 2 result: 4 in-scope (0 H / 0 M / 3 L / 1 D) → fix pass. Not yet converged (exit needs two consecutive clean cycles).

Cycle 2 fix pass (a7f2e32e + dc1f4f1c): all four findings fixed as dispositioned, plus two items the fix pass surfaced:
- **Engine settle would have regressed** once `_hold_ticks` banks the floored tick: `_swap_and_scroll` handed `frames_to_transition_ready()` FRAMES to `_hold_ticks` as TICKS (exact while a hold tick was one frame; a 13-frame overshoot at 67 ms). New `Ticker._settle_hold_ticks` mirrors the image loops' `_settle_ticks` (`ceil((frames×50 − carry) / hold_tick_ms)`, refused when `ticks × hold_tick_ms > MAX_SETTLE_MS`; pass-through on uncapped/Mock frames and duck-typed widgets).
- **gif/still `_play_no_text` slept a flat 50 ms after `swap()`**: with a blocking swap the request lands just past a refresh boundary and the real tick runs to the next one (~100 ms at a 100 Hz cap) while 50 ms was banked — 0.5×, pre-existing on main. Now drift-compensated like every other loop (`sleep(max(0, tick − elapsed))`); on an uncapped sign this only subtracts draw time. Tests pin sleeps ≈ 0 when the swap consumes the budget.
- Tripwires added: `_hold_ticks` must pass `tick_ms=<local>` assigned from exactly `floor_tick_ms(self.frame, ENGINE_TICK_MS)`; no `_advance_frame_if_supported` call in ticker.py may omit `tick_ms=`.
Full suite after the pass: see cycle 3 header.

## Cycle 3 — lens: complexity / least-examined (the extended floor on 50 ms loops, `_settle_hold_ticks`, drift-compensated no-text sleeps, docs accuracy)
Head dc1f4f1c. Full suite 5613 passed, 5 skipped. 13 mutants: 10 killed, 3 survived (all test gaps, none equivalent). No behavioural defect found in `_settle_hold_ticks`, the hoisted hold floor, the drift-compensated no-text sleeps or `swap_interval_ms`.

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | LOW | in-scope (test gap) | `_settle_hold_ticks` guard `0 < frames` → `0 <= frames` survives: on a capped frame `max(1, 0 − carry)` would grant a 67 ms tick to a widget already at rest. | FIX: `test_nothing_owed_on_a_capped_frame_is_no_extension`. |
| 2 | LOW | in-scope (test gap) | gif no-text capped test uses a single-frame gif, so `_pick_frame_for_elapsed(tick * frame_tick_ms)` survives; the "frame pick unchanged" claim was unobservable. | FIX: three-frame gif + class-level spy asserting elapsed 0, 50, …, 250 while the counter banks 6×67. |
| 3 | LOW | in-scope (test gap) | still's drift-compensated sleep pinned from one side only; `sleep(0.0)` survives (a 10-tick hold would spin in ~0 ms). | FIX: frozen-clock test asserting every sleep is exactly 50 ms. |
| 4 | DOCS | in-scope | `constants.py` still said only the image loops convert owed frames; CLAUDE.md per-effect-counters clause and plugin-system.md scoped banking to the scroll-paced loops. | FIX: all three reworded (engine converts at its floored hold tick via `_settle_hold_ticks`; every core loop banks). |

Nits (not counted): garbled comment in test_gif.py L159 (fixed); `_settle_hold_ticks` / `_settle_ticks` share the same formula and are independently mutation-pinned — a shared pure helper would make drift impossible (left as is: no drift today, adds review surface at the cap).

Clean with evidence: carry read after the last advancing loop; delivered frames ≥ owed by construction, overshoot < 1 + hold/50; `_banks_elapsed` is the single predicate for advance and settle dispatch; `SegmentMessage` lacks `frames_to_transition_ready` → settle 0 before carry is read; no other frames-as-ticks caller; no finite `loop.time` iterator in tests; still fast path untouched; gif frame pick at nominal on a capped sign is pre-existing/by design (0.75× at 30 Hz; main was ~0.43×); `swap_interval_ms` pre-setup reads 1000/hz ≤ 33 for hz ≥ 30 so `floor_tick_ms` can never over-floor; `_rgb_frame` calls `setup()` so it is representative.

Cycle 3 fix pass: eef060d0 — each new test verified to fail against its mutant and only its mutant. Cycle 3 result: 4 in-scope (0 H / 0 M / 3 L / 1 D) → not converged. Cycle 4 next; cycle 5 is the hard cap.

## Cycle 4 — lens: fresh eyes, whole diff; engine seams revisited after three fix passes
Head eef060d0. Full suite 5616 passed, 5 skipped; `pyright src` 0 errors. 13 mutants: 12 killed, 1 survived (test gap). No behavioural defect in production code. End-to-end probes on the real engine path (`_show_one` ×2 visits, `_run_swap` with push_left, one-by-one, side-by-side, `_scroll_and_delay`, `run_transition` cut/push_left) at `scroll_step_ms` {20, 35} × swap interval {none, 50, 67}: `(frame_count, carry) == divmod(Σ banked tick, 50)` exactly, per-effect counters equal, carry zero at visit entry, transitions leak nothing. Settle on a 67 ms frame landed exactly on the typewriter rest point. Real `LedFrame(RgbMatrixBackend)` over the stub: intervals 0/40/67/50/50/55/50 for 0/25/30/60/100/110/120 Hz.

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | LOW | in-scope (test gap) | `SegmentMessage.advance_frame_elapsed` promises to route each banked frame through `advance_frame` (public building block; a subclass override would otherwise see 0 calls) — `_frame_count += frames` survived. | FIX: `TestSegmentMessageCadence::test_routes_through_advance_frame` (subclass spy, visit_id forwarded). |
| 2 | DOCS | in-scope | `FrameAwareWidget` and `SegmentMessage` docstrings still scoped `advance_frame_elapsed` to the scroll-paced loops (pre-cycle-2 behaviour). | FIX: reworded to every core loop. |
| 3 | DOCS | in-scope | api-reference.mdx L42/L301 used release-history framing ("previously", "it did not before"; DOCS-STYLE rule 17) and never linked `limit_refresh_rate_hz` (rule 3). | FIX: reworded; linked on first use. |

Nits folded in: tripwire docstring explains why scroll loops pin the per-tick property while `_hold_ticks` pins a hoisted local; `_settle_hold_ticks` reuses `frame._is_int`. Left as is: CLAUDE.md #12 "plain `advance_frame` path" wording (true for the engine dispatch; gif/still go through `advance_frame_elapsed(50)` ≡ one `advance_frame`); untouched pages saying "degrees per engine tick" (now true as per-50 ms-frame everywhere).

Pre-existing (ledger only): render-demo computes `swap_interval_ms` from the config but its stub swap never blocks, so a non-100 Hz cap would render HELD effects fast in GIFs (no such config exists; all 10 capped configs use 100 Hz → interval 50 → identical to main).

Cycle 4 fix pass: 3f49bbf8 (new test verified against mutant g). Cycle 4 result: 3 in-scope (0 H / 0 M / 1 L / 2 D) → not converged. Cycle 5 is the HARD CAP: if it is not clean, stop and flag to James.

## Cycle 5 (hard cap) — lens: everything added since cycle 3 + a final cold read of the public surface
Head 3f49bbf8. Full suite 5617 passed, 5 skipped; `pyright src` 0 errors; ruff clean. 7 new mutants: 4 killed, 2 equivalent (`framerate_fraction` default, `int()` cast under the int contract), 1 pre-existing gap (`SegmentMessage.reset_frame`'s `_frame_count = 0` is main's line, unpinned). All four cycle-3/4 fix mutants re-applied and killed by exactly the test each fix added. Public surface: `__all__` unchanged; a plugin `play()` loop can honour (1, 6) via `self.advance_frame_elapsed(max(tick, getattr(frame, "swap_interval_ms", 0)))`; "what `frame` means" consistent across all touched pages.

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | LOW | in-scope (behavioural, design-adjacent) | The delivered-extension refusal (`ticks × tick_ms > MAX_SETTLE_MS`, both twins) rejects a top-of-budget settle the frame check just admitted whenever the tick does not divide 1000: 20 owed frames at `scroll_speed_ms = 30` with carry 0 → 34 ticks = 1020 ms → REFUSED (transition fires 20 frames early), while the same debt at 50 ms is granted and at 30 ms with carry 30 is granted (33 ticks). Effective budget becomes `floor(1000/tick) × tick` (990 @ 30, 980 @ 35, 938 @ 67); a 20-frame debt at a 67 ms interval is refused for every carry. Reachable: `flair.blink` with `period_ms = 2000, duty = 0.5` reports exactly 20 at off-phase start. The rule is implemented exactly as the constants.py comment and cycle-1 #3 specify; what is unintended is refusing a landing that would be clean 5–20 ms over budget. | **OPEN — James's call.** Option A: tolerate a sub-tick overshoot — refuse when `tick_ms > MAX_SETTLE_MS or (ticks − 1) × tick_ms >= MAX_SETTLE_MS` (keeps the 2000 ms refusal; test at 30 ms / carry 0 / 20 frames on both twins). Option B: keep the strict rule and document the effective budget. |
| 2 | DOCS | in-scope | plugin-system.md still said a duck-typed widget "advances one frame per scroll tick". | FIXED (this commit): "per loop tick". |
| 3 | DOCS | in-scope (ledger accuracy) | Three cycle-1/2 lines were superseded by later fixes without a note. | FIXED (this commit): SUPERSEDED annotations added. |

Cycle 5 result: 3 in-scope (0 H / 0 M / 1 L / 2 D). **Hard cap reached without two consecutive clean cycles → loop stopped; outstanding item #1 flagged to James.** Trajectory: 6 → 4 → 4 → 3 → 3 in-scope; the last three cycles found no HIGH/MEDIUM and the only behavioural items were narrow (cycle 5 #1 is the sole open one).

## Summary for the PR
17 items found and fixed across cycles 1–4 (2 MEDIUM, 9 LOW, 6 DOCS), including two mechanisms nobody expected going in: `SwapOnVSync(canvas, fraction)` blocks for the swap interval (so nominal ticks under-count on refresh-capped signs), and the engine settle seam passed frames as ticks. One LOW behavioural item open at the cap (cycle 5 #1). Pre-existing items for separate issues: validate warning when `scroll_step_ms`/`scroll_speed_ms` is below the swap interval; render-demo's stub swap never blocks (a non-100 Hz cap would render held effects fast); `SegmentMessage.reset_frame` count reset unpinned; flair docs say settle applies to `message` only.

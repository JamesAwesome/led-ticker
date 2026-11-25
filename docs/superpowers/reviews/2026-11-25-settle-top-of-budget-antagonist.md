# Antagonistic review ledger — #570 (settle refuses a top-of-budget extension)

Protocol: fresh adversarial reviewer per TASK while building, then a fresh reviewer per CYCLE on the open draft PR; mechanism-first (state → trigger → observable failure), no padding. One fix pass per cycle. Exit (James's rule for this PR): the first cycle whose findings are all LOW/DOCS — fold them in, then ask James for merge permission. Hard cap 5 cycles; at the cap, stop and ask James how to proceed.

Branch: fix/settle-top-of-budget (worktree led-ticker-wt-settle). Base: origin/main at 118a2669 (#566).

Fix: Option A from the issue. Both settle twins refuse only when `tick_ms > MAX_SETTLE_MS or (ticks − 1) × tick_ms >= MAX_SETTLE_MS` — a tick may not START past the budget line, but the last tick may cross it. Consequences recorded as a choice (pinned by `test_wide_tick_overshoot_is_a_recorded_choice`): overshoot is bounded by one tick, so a 600 ms image tick owing 20 frames delivers 1200 ms and the worst case (999 ms tick) is just under 2 s. On the image twin the second clause is implied (owed ≤ budget, carry ≥ 0); on the engine twin it is live for a duck-typed negative carry.

## Build-phase task reviews

### Task 1 — image twin (`_BaseImageWidget._settle_ticks`, 09e509ef)
Mutants (15 incl. 3 call-site): 10 killed, 4 equivalent/defensive (`>=`→`>` and drop-second-clause — implied on this twin; `max(1, owed)`; `max(1, tick)`), 1 SURVIVED: a clamp to the old cap at BOTH call sites. The rule is correct; floored tick passed at both call sites; loop consumption of the new counts verified.

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | MEDIUM | in | No loop-level test drives a newly granted count — a `min(_settle_ticks(...), MAX_SETTLE_MS // tick)` clamp at the call sites passes everything; two-row had no #570 case at all. | FIX: `test_single_row_loop_delivers_a_top_of_budget_settle` + `test_two_row_loop_delivers_a_top_of_budget_settle` (30 ms, 20 frames → 5 + 34 paints); verified to fail against the clamp mutant before the fix. |
| 2 | LOW | in | Docstring filed the 2000 ms refusal under the START heading; "is implied" read as holding rather than never-refusing. | FIX: reworded — three checks (owed, tick length, tick start); start clause can never refuse here, kept for parity. |
| 3 | LOW | in (design) | In FRAMES the overshoot is up to `tick/50` past the rest point, so a rest window shorter than the tick (shimmer pause = 10 frames) can be overshot at `scroll_speed_ms >= 550`. | Recorded in the wide-tick test docstring as part of the choice; a validate warning for very slow image ticks is a possible follow-up. |
| 4 | DOCS | in | Stale old-rule wording in `test_image_frame_cadence.py` (TestSettleConversion / TestSettleDeliveredCap docstrings, `test_play_loop_refuses_the_overshoot`). | FIX: rewritten / renamed `test_play_loop_refuses_a_tick_longer_than_the_budget`. |
| 5 | DOCS | out (old ledger) | #566 ledger row still "OPEN — James's call". | FIX: marked RESOLVED → #570; cycle-1 #3 annotated SUPERSEDED. |
| 6 | LOW | out (pre-existing) | `max(1, tick_ms)` guard unpinned. | FIX: `test_non_positive_tick_is_treated_as_one_ms`. |

### Build-phase fix pass
All in-scope items from Tasks 1–3 folded in (one commit). Not changed, listed as follow-ups: the non-banking pass-through has no wall-clock budget on a capped frame (engine, #566 design); very slow image ticks (≥ 550 ms) can overshoot a short rest window; rule-17 "as before" prose on two unrelated docs pages.

### Task 2 — engine twin (`Ticker._settle_hold_ticks`, e7d2177e)
Mutants (7): 6 killed, 1 survived (`>=` → `>`, equivalent on the reachable domain). Enumeration hz 0..120 × frames 1..20 × carry 0..49: new grants ⊇ old grants, no undershoot, every granted count ≤ 20 ticks.

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | LOW | in | Both post-conversion refusal clauses are unreachable in core: `bank_frames` keeps carry ∈ [0, 49] so `(ticks−1)·h < owed ≤ 1000`; the rgbmatrix `swap_interval_ms = round(fraction·1000/hz)` ≤ 1000 for hz ≥ 1. Docstring/test present the negative-carry backstop as live. | FIX: reword docstring + test — unreachable for in-tree classes/backend, kept for third-party banking classes/backends and twin parity. Keep refuse semantics (a bogus carry is a contract violation; no extension is the safe outcome). |
| 2 | LOW | in | Negative-carry test says "duck-typed widget"; a truly duck-typed widget takes the pass-through and its carry is never read. | FIX: rename/reword to "third-party class defining `advance_frame_elapsed` with its own carry". |
| 3 | LOW | in (test gap) | `>=` → `>` survives; only distinguishable at `(ticks−1)·h == 1000`, which needs a negative carry (h=100, carry −50, 20 frames → 11 ticks). | FIX: add that boundary to the negative-carry test. |
| 4 | LOW | out (pre-existing, #566) | Pass-through branch (non-banking widget on a capped frame) returns `frames` ticks with no wall-clock budget: 20 frames at 67 ms = 1340 ms, at hz=1 = 20 s. | Qualify CLAUDE.md "bounded by one tick" → "for banking widgets"; list as a follow-up in the PR. |
| 5 | DOCS | in | Stale test names: `test_delivered_extension_over_budget_is_refused`, `test_delivered_extension_at_exactly_the_budget_is_granted`. | FIX: rename. |
| 6 | DOCS | out (image twin) | `TestSettleDeliveredCap` class name/docstring states the old rule. | FIX with Task 1's pass. |
| 7 | DOCS | scheduled | constants.py / CLAUDE.md old wording — already rewritten in a833eae9, verified against the code. | none |
| 8 | LOW | out (inherent) | Coarse intervals land ≤ `ceil(h/50)−1` frames past the rest point. | note only |

### Task 3 — comments + CLAUDE.md (a833eae9)
No HIGH/MEDIUM. Formula, refusal and every quoted number verified against both twins; all 11 cited tripwire names exist; old-rule sweep clean apart from item 1.

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | DOCS | in | `TestSettleDeliveredCap` class docstring states the old rule. | FIX: rewrite docstring (keep the class name — CLAUDE.md cites it). |
| 2 | LOW | in | CLAUDE.md settle invariant lists only the #305/#526 tripwire files; #12 says "pinned" without naming the pin. | FIX: name `TestSettleConvertsFramesToFlooredTicks` / `TestSettleDeliveredCap` / `test_wide_tick_overshoot_is_a_recorded_choice`. |
| 3 | LOW | in | Wide-tick overshoot pinned on the image twin only. | FIX: add the engine twin case (interval 600, 20 frames → 2 ticks). |
| 4 | LOW | in | "would START past it" — the clause is `>=`, so a tick starting exactly AT the line is refused. | FIX: "at or past" at the five sites. |
| 5 | DOCS | in | api-reference.mdx "up to roughly one second" is honest for ordinary ticks; the plugin contract page should state the bound. | FIX: add the one-sentence budget statement (rule-17 clean). |
| 6 | DOCS | out (pre-existing) | Rule-17 violations in color-providers.mdx:151 and value-tokens.mdx:100 ("as before"). | Leave — unrelated page prose; note for a docs pass. |
| 7 | LOW | in | Ledger Task 1/2 sections pending. | Filled as the reviews land. |

## PR cycles

### Cycle 1 — fresh whole-diff reviewer on draft #571 (head 9beff3e1)
Brute force tick 1..2000 × frames 1..20 × carry 0..49: new grants ⊇ old, nothing newly refused, start clause fires 0× for carry ≥ 0. Mutants 20: 18 killed, 2 equivalent (image start clause / `>=`). Drift tripwires green. No in-tree config reaches the changed branch (the two non-dividing ticks in `config/` are a scrolling marquee and constant row colors). API minor bump: not warranted (agreed).

| # | Sev | Scope | Finding | Disposition |
|---|-----|-------|---------|-------------|
| 1 | LOW | in (disclosure) | The PR body disclosed the 20–100 and 500–1000 ms tick bands but not 101–499 ms: up to 1497 ms delivered and 9 frames past rest (tick 451, 19 frames, carry 47); the offered stricter one-liner does not touch that band. | FIX: disclosed in the PR body. |
| 2 | LOW | in (test honesty) | Loop-level pins assert `_frame_count >= 23` where `== 23` is known. | FIX: `==`. |
| 3 | DOCS | in | "reachable only with `limit_refresh_rate_hz <= 4`" — hz 4 gives a 250 ms interval (divides the budget); ≥ 500 needs hz ≤ 2, 600 needs a third-party backend. | FIX: docstring + PR body. |
| 4 | DOCS | in | api-reference sentence said "past" where the rule is "at or past". | FIX. |
| 5 | DOCS | in | #566 ledger cycle-2 fix-pass line still stated the delivered rule without a SUPERSEDED note. | FIX. |

Cycle 1 result: 5 in-scope (0 H / 0 M / 2 L / 3 D) → **exit condition met** (all LOW/DOCS). Folded in; merge permission requested from James.

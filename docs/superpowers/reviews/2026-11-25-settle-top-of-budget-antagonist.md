# Antagonistic review ledger — #570 (settle refuses a top-of-budget extension)

Protocol: fresh adversarial reviewer per TASK while building, then a fresh reviewer per CYCLE on the open draft PR; mechanism-first (state → trigger → observable failure), no padding. One fix pass per cycle. Exit (James's rule for this PR): the first cycle whose findings are all LOW/DOCS — fold them in, then ask James for merge permission. Hard cap 5 cycles; at the cap, stop and ask James how to proceed.

Branch: fix/settle-top-of-budget (worktree led-ticker-wt-settle). Base: origin/main at 118a2669 (#566).

Fix: Option A from the issue. Both settle twins refuse only when `tick_ms > MAX_SETTLE_MS or (ticks − 1) × tick_ms >= MAX_SETTLE_MS` — a tick may not START past the budget line, but the last tick may cross it. Consequences recorded as a choice (pinned by `test_wide_tick_overshoot_is_a_recorded_choice`): overshoot is bounded by one tick, so a 600 ms image tick owing 20 frames delivers 1200 ms and the worst case (999 ms tick) is just under 2 s. On the image twin the second clause is implied (owed ≤ budget, carry ≥ 0); on the engine twin it is live for a duck-typed negative carry.

## Build-phase task reviews

### Task 1 — image twin (`_BaseImageWidget._settle_ticks`, 09e509ef)
_pending_

### Task 2 — engine twin (`Ticker._settle_hold_ticks`, e7d2177e)
_pending_

### Task 3 — comments + CLAUDE.md
_pending_

## PR cycles
_pending_

# Antagonist review ledger: center wipes (`center-wipes` branch)

Protocol (roadmap §1.4): fresh reviewer per cycle, full diff each time, cap 5.
Exit when a cycle reports only LOW / DOCS; fold those in. Cycle 5 ending with
MEDIUM+ stops and flags. Pre-existing issues outside the diff do not count;
they get GitHub issues.

Range: `b91fbd3f..HEAD`. Package: `.superpowers/sdd/2026-11-17-center-wipes/`.

| Cycle | Lens | HIGH | MED | LOW/DOCS | Result |
|---|---|---|---|---|---|
| 1 | correctness, engine seams, test validity | 1 | 2 | 1 LOW, 2 DOCS | HIGH: cap at `half` left all-black tail frames (vertical, ease_out: 5/16). Fixed via `front_cap` (inward `(n-1)//2`, outward `n//2-1`); near-end tests now assert black + sweep colour only. MED: bottom letterbox band unpinned → sentinel both bands; MED: sweep line reach into bands unpinned → asserted at rows 4/32/60. LOW (odd-extent early completion) covered by the cap. DOCS: "Opening reveal" wording; CLAUDE.md file map. All folded in commit after 0c241754. Engine-seam e2e (run_transition cross-scale, bg colours, scroll_pos) clean. |
| 2 | perf, mutation-tested validity, config/validate path, docs accuracy | 0 | 3 | 3 LOW, 2 DOCS | MED (all test gaps, each proven by a surviving mutant): axis/direction identity of 3 classes unpinned → parametrized mid-sweep identity test with painting widget; `scale_switch_at` unpinned → added to `hard_edged`; `transition_color` never asserted at pixel level → asserted. LOW: per-pixel line loops (4096 SetPixel/frame at scale 4) → one SubFill per span; no line on frame 0 → lines at front start positions (family consistency); package re-export block missing the four → added. DOCS: `split` sentence corrected; `min_frames` duration floors stated. Pre-existing, not counted (candidate issues): `transition_color` shape unvalidated end to end (a string crashes `SetPixel` on hardware); `transition_colors` silently dropped on single-direction wipes; `min_frames` floor vs documented 0.4–0.8 s for `wipe_left/right`; per-pixel line loops in `wipe.py`; ease_out static tail on 16-row panels. |

# Antagonist review ledger: center wipes (`center-wipes` branch)

Protocol (roadmap §1.4): fresh reviewer per cycle, full diff each time, cap 5.
Exit when a cycle reports only LOW / DOCS; fold those in. Cycle 5 ending with
MEDIUM+ stops and flags. Pre-existing issues outside the diff do not count;
they get GitHub issues.

Range: `b91fbd3f..HEAD`. Package: `.superpowers/sdd/2026-11-17-center-wipes/`.

| Cycle | Lens | HIGH | MED | LOW/DOCS | Result |
|---|---|---|---|---|---|
| 1 | correctness, engine seams, test validity | 1 | 2 | 1 LOW, 2 DOCS | HIGH: cap at `half` left all-black tail frames (vertical, ease_out: 5/16). Fixed via `front_cap` (inward `(n-1)//2`, outward `n//2-1`); near-end tests now assert black + sweep colour only. MED: bottom letterbox band unpinned → sentinel both bands; MED: sweep line reach into bands unpinned → asserted at rows 4/32/60. LOW (odd-extent early completion) covered by the cap. DOCS: "Opening reveal" wording; CLAUDE.md file map. All folded in commit after 0c241754. Engine-seam e2e (run_transition cross-scale, bg colours, scroll_pos) clean. |

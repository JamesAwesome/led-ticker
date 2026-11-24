# Antagonist loop — `fade` FEATURE PR (branch `fade-transition`, stacked on `fade-precursor`)

Target: the diff `fade-precursor..fade-transition` (`transitions/fade.py` + tests;
sixteen-member pool pins; rule 74 wording; fact-pack and snippet drift tripwires;
docs + demo GIF; CLAUDE.md). Design: `docs/superpowers/specs/2026-11-21-fade-design.md`.
Plan: `docs/superpowers/plans/2026-11-22-fade-transition.md` (Tasks 7-10).
Rules: fresh reviewer per cycle, full diff each time, cap 5, exit when only
LOW/DOCS remain (folded in). Pre-existing issues outside the diff do not count.
The precursor has its own ledger (`2026-11-22-fade-precursor-antagonist.md`).

## Cycle 1

Reviewer: fresh subagent; 14 live mutations on a scratch copy, end-to-end renders, full suite 5357 passed / 2 skipped. VERDICT: 0 HIGH, 0 MEDIUM, 4 LOW, 2 DOCS -> exit condition met (LOW/DOCS only); folded.

- LOW a malformed SECTION bg (`[99.0, 60, 138]`, `[300, 0, 0]`) reaches the runner un-validated and would raise from `Fill` / `Image.new` inside `_snapshot`'s except path. FOLDED: `_norm_bg` coerces to three ints 0..255 or drops to black with a WARNING, before the try; raise point 3 in the module docstring now covers the section bg; test `test_malformed_section_bg_is_dropped_not_raised`.
- LOW `_wrap` inside the try attributed a config error (`content_height * scale > rows`) to the widget and disabled it. FOLDED: the wrapper is built outside the try (the runner's own re-wrap raises on the same config for every switching transition); only `draw` + conversion are guarded.
- LOW the tripped-snapshot DEBUG line named the guard class. FOLDED: names the inner widget.
- LOW Review Focus 2 / 4 tests did not exercise the named input; through-cache size key unpinned. FOLDED: cancel test runs through a two-member `random` pool and checks the pick advanced; draws-nothing test goes through a guard and asserts nothing tripped; one dip `Fade` at two panel sizes.
- DOCS special.mdx stated the `pwm_bits` finding as fact and said image widgets' borders soften. FOLDED: hedged as pending the hardware check; "a text widget's border".
- DOCS CLAUDE.md file map: the sprite-trail parenthetical hung under `fade.py`. FOLDED: `fade.py` lines moved below it.
- Mutations: 11 of 14 caught; the three survivors are equivalent mutants (single-slot through cache: panel size is fixed per process, now pinned anyway; `SetImage` on the wrapper forwards to `.real` at native coords; `_key` kept after `end_firing` is gated by `_out_img is None`).
- Unverified by the reviewer: Pi first-frame cost (Mac best-of-3: 1.7-4.2 ms on 256x64 at scale 4; ~10-20 ms at a Pi factor, inside the 50 ms tick) and the `pwm_bits` claim — both are what the hardware check measures.
- Pre-existing, out of scope: validate has no `bg_color` shape rule; `content_height * scale > panel` passes `load_config` and the runner's `_maybe_wrap` raises for every switching transition; breaker `_key` is content-keyed.

## Exit

Loop exits after cycle 1 (0 HIGH / 0 MEDIUM; James's rule: fold LOW/DOCS and stop). Next: hardware check on moonbunny, findings into the design's "Hardware findings" and the special page's tuning bullet.

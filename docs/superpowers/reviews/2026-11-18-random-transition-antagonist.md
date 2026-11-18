# Antagonist loop — PR B `random-transition` (feature)

Roadmap item 2: `random` / `auto` meta-transitions. Stacked on PR A
(`random-transition-precursor`). Rules: fresh reviewer per cycle, cap 5, exit
when only LOW/DOCS remain (folded, then ship). Design:
`docs/superpowers/specs/2026-11-17-random-transition-design.md` (approved via
its own loop, see `2026-11-18-random-transition-design-antagonist.md`).

## Cycle 1

Reviewer: fresh fable subagent. VERDICT: 1 HIGH, 4 MEDIUM, 6 LOW, 3 DOCS.

- HIGH `inf` / `nan` entry durations passed the factory and validate, then `int(inf / 0.05)` raised before the runner's `try` and escaped `run()`. FOLDED: `math.isfinite` in the factory refusal; tests at both layers.
- MEDIUM rule 21's bounds not applied to entry durations (design said so). FOLDED: rule 73 warns `> 5 s` / `< 0.05 s` per entry.
- MEDIUM unhashable entry `type` raised `TypeError` from the exclude filter before the shape check. FOLDED: shape first pass, then exclude.
- MEDIUM no end-to-end `run_transition` pin through a factory-built wrapper. FOLDED: cross-scale `auto [wipe_left, dissolve@1.0]` test (41/21 frames, 500/1000 ms, re-wrap at 1.0 / 0.5).
- MEDIUM entry `transition_color` clearing inherited `colors` was unpinned (masked by the constructor check). FOLDED: both-colour stub pin.
- LOW ×6 FOLDED: warnings walk post-exclude members; dead checks removed; dedupe keyed on the resolved member; docs anchor; decision-3 block skipped when default errored; `_`-token pin.
- DOCS ×3 FOLDED: fact-pack Pools pointer removed (OptionsTable renders the whole body); "one runner knob"; index.mdx inter-widget chain ends at `cut` and the `default` row describes what it is.

## Cycle 2

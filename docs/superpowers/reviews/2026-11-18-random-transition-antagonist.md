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

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 2 MEDIUM, 4 LOW, 1 DOCS.

- MEDIUM inherited parent colour never shape-checked on pool children; after the rebase the precursor's rule 74 grades the random/auto slot by its own constructor (reads nothing) → WARNING while the sign would crash at the first child firing. FOLDED: the resolver shape-checks whatever each child ends up carrying (own or inherited) → ValueError → rule 73 ERROR, rebase-proof; pins at both layers.
- MEDIUM dead `_registered_transition_names` in the feature's validate.py would collide with the precursor's live copy on rebase. FOLDED: removed.
- LOW ×4 FOLDED: garbled "need at least 2need at least 2" literal; dedupe keyed on the RESOLVED duration (a table pinning the parent's duration collapses with the bare name; docstring and test agree); entry duration above 3600 s refused (`int(1e308 / 0.05)` overflowed before the runner's `try`); one `META_TYPES` exported from `transitions.meta` replaces three spellings (the precursor's `_META_TRANSITION_TYPES_R74` unifies at rebase).
- DOCS FOLDED: "lock-step" → "start aligned on the first pass, then drift apart as widget counts differ".

## Cycle 3

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 0 MEDIUM, 5 LOW, 4 DOCS → loop exits.

- LOW ×5 FOLDED: inherited-colour refusal names the slot, not a phantom entry (rule 74 on the slot is skipped for meta types at rebase so it does not double-report); inherited slot `duration` validated on children and `_pool_member_key` loses its dead parameter; `_MAX_ENTRY_DURATION_S` comment corrected; one-call lazy-import wrapper inlined; decision-3(b) warning states the real effect.
- DOCS ×4 FOLDED: design spec gains an "Amendments from the PR antagonist loops" section; special.mdx "slot's `transition_color`" and the two example forms marked as alternatives; index.mdx `default` row names which slots inherit.
- Out of scope, pre-existing (noted for follow-up): rule 21 tracebacks on a string/list slot `duration` for any type.

## Exit

Severity trend: 1H/4M → 0H/2M → 0H/0M. Next: rebase onto the precursor's final
head, full suite, hardware check (ask first), draft PR stacked on PR A.

## Hardware check (bigsign, 2026-11-18)

Feature branch at `e4336ab4` deployed to the bigsign via `make update`, test config with `random` (default pool, within-section swaps and entry), a `between_sections` pool `["wipe_in", "push_up", "dissolve", {flair.sand, duration 2.0}]`, a scale-2 section entered through that pool, and two `auto` sections on `["push_left", "wipe_right", "dissolve"]`. 130 s of preview-mirror frames captured in-container plus DEBUG pick lines. Live config validated clean against the branch first (flair 0.22 installed).

- `random`: 36 firings across the two default-pool instances, zero consecutive index repeats, all 15 members picked. Between-sections instance: 9 firings, zero repeats; `flair.sand @2s` ran 2.0 s where `wipe_in`/`push_up` ran the 3.0 s section duration (`duration_override` honoured by the runner).
- `auto`: two sections, four instances (entry + widget each), every one cycled 0→1→2→0 in pool order over 9 cycles, independently.
- Cross-scale entry (scale 4 → 2): pushes/wipes snap at the end, dissolve switches mid-way — each child's own `scale_switch_at`, forwarded through the wrapper; no mid-sweep jolt.
- Validate's rule-73 build attempt logs one construction pick per meta slot at startup (four extra one-line tags); harmless, DEBUG only.
- `wipe_left`/`wipe_right` fire for 2.0 s at `duration = 0.5` in every slot: the pre-existing `min_frames = 40` floor on `main`, not a regression.
- No tracebacks. Sign restored to `main` with its original config afterwards.

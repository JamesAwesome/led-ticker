# Antagonist loop — PR A `random-transition-precursor`

Precursor PR for roadmap item 2 (per the roadmap process: DRY refactor +
campsite fixes ship ahead of the feature, attached to its first consumer).
Contents: shared `rgb_shape_error` predicates; `ticker._run_swap` guard for a
widget-slot `transition_fn` of `None`; `_iter_transition_slots` replacing five
per-slot validate loops; validate rule 74 (transition colour shape).
Rules: fresh reviewer per cycle, cap 5, exit when only LOW/DOCS remain (folded,
then ship). Base `44f55d30` (origin/main).

## Cycle 1

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 3 MEDIUM, 5 LOW, 2 DOCS.

- MEDIUM rule 74 warning fix text wrong when `transition_color` and `transition_colors` both set (the list shadows the single colour; neither applies) and "takes a single colour" false for colourless types. FOLDED: three-way wording (shadowing / single-colour hint / plain ignored).
- MEDIUM rule 74 docstring misdescribed two shapes (short list = `IndexError` at build → guarded cut, not a SetPixel crash; long list runs today by truncation). FOLDED: docstring corrected; long list stays an ERROR, called out in the PR body as newly refused.
- MEDIUM ticker tripwire patched a name `_run_swap` never reads. FOLDED: patches `led_ticker.transitions.run_transition`; still red pre-fix (mock would be called with None).
- LOW ×5 FOLDED: `wipe_alternating` < 4 colours warns; suffix on warnings; unknown types skipped; rule 60 slot loop on the helper; pins for entry/widget/default slots, empty list, load-stage carve-out, rule 53 default inclusion.
- DOCS ×2 FOLDED: forward references marked "stacked follow-up"; nested message no longer stutters; tupled-string hint added.

## Cycle 2

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 1 MEDIUM, 6 LOW, 1 DOCS.

- MEDIUM pyright `reportArgumentType` on rule 74's `_issue(severity: str)` (introduced by the cycle-1 fold; CI's lint job runs `pyright src/`). FOLDED: `Literal["error", "warning"]`; `pyright src/` back to the 2 pre-existing errors.
- LOW ×6 FOLDED: tupled-string hint requires a non-empty tuple and covers list elements; `_SINGLE_COLOR_TYPES` branch pinned ("takes a single colour"); hand-kept type sets replaced by `_allowed_init_kwargs` (color / colors) read off the registered constructor, `_registered_transition_names` shared with rule 39; single colour beside a list on a consumer warns, `wipe_alternating` warns on any count ≠ 4; malformed colour on a type that reads neither is a WARNING (would otherwise block hot-reload for a config that runs today), plugin/unknown stay ERROR; firebird example's dead `[transitions] transition_colors` moved onto the `default` table (own commit).
- DOCS FOLDED: rule 60's issue order change (slots first, then section-level) noted for the PR body.

## Cycle 3

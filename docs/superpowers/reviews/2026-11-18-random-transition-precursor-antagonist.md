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

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 3 MEDIUM, 4 LOW, 0 DOCS.

- MEDIUM the firebird fold moved the palette to `default`, another slot that is never built (between_sections is set; sections without `transition` cut). FOLDED: palette on `widget_transition` of the three transition-less sections; `[transitions]` comment says what `default` does there. Cycle-2 ledger line corrected by this entry.
- MEDIUM rule 74 graded severity per TYPE while the factory forwards per FIELD (`colors` wins; `color` only reaches a single-colour constructor with no list beside it). FOLDED: per-field effectiveness; malformed-but-ineffective → one WARNING naming why.
- MEDIUM an ERROR at `transitions.default` could refuse a config whose default is never built (between_sections set). FOLDED: WARNING there with the reason; ERROR only when default stands in for an omitted between_sections.
- LOW ×4 FOLDED: plural "ignores it anyway" branch pinned; registered meta type skip pinned with a throwaway `random`; registered plugin types classified by their constructor like core (unknown stays conservative); three filming TOMLs drop the dead `[transitions] transition_colors` key (not a slot; rule 74 cannot see it — stated for the PR body).

## Cycle 4

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 1 MEDIUM, 7 LOW, 2 DOCS.

- MEDIUM two of the three firebird `widget_transition` lines sat on single-widget sections (no within-section swap ever happens). FOLDED: only the multi-widget class-list section carries the pool, with `duration`/`easing` inline (widget_transition tables parse against a bare TransitionConfig); `[transitions]` comment rewritten.
- LOW ×7 FOLDED: empty `transition_color(s)` on a core constructor → WARNING (falls back to its default; `wipe_random` stays ERROR, it raises on an empty pool); a `section.transition` shadowed by both entry_transition and widget_transition → WARNING (never built); takes-neither type with both fields → one "Remove both" warning; malformed single colour beside a list → one warning; plugin table `colors`/`color` key precedence modelled (`extra` wins on the dotted path); the four feature-PR spec files pulled out of the cycle-3 commit (they ship with the stacked PR; the precursor ledger stays here).
- DOCS ×2: PR body will carry rule 66's order change, the throwaway-`random` test the stacked PR must replace, and the empty-value / long-list / bare-key notes. Pyright baseline: pinned `uv run pyright src/` → 0 errors; `PYRIGHT_PYTHON_FORCE_VERSION=latest` → the same 2 pre-existing errors (run.py:763, ticker.py:767) as origin/main.

## Cycle 5 (cap)

Reviewer: fresh fable subagent; 1,218-cell severity matrix run end to end (load → rule 74 → build → frame_at on a strict SetPixel canvas): no live cell warns on a crash shape, none errors on a running config beyond the ledgered long-list refusal. VERDICT: 0 HIGH, 0 MEDIUM, 2 LOW, 3 DOCS → loop exits at the cap with only LOW/DOCS.

- LOW ×2 FOLDED: `wipe_alternating` shape-checks only the four colours it consumes (a short list is ignored entirely → warning; a bad fifth colour is the count warning); a malformed single colour no longer hides the "list ignored" warning on a type that reads neither.
- DOCS ×3 FOLDED: plugin own-`color`-key precedence worded like its `colors` twin; this ledger committed with the branch; the two over-claiming commit messages (d79e407f, d84143c3) are corrected in the PR body.

## Exit

Severity trend: 0H/3M → 0H/1M → 0H/3M → 0H/1M → 0H/0M. Ships as the precursor PR; the feature PR stacks on this head.

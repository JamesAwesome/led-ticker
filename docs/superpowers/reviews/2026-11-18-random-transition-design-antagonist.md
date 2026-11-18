# Antagonist loop — `random` / `auto` meta-transition DESIGN

Target: `docs/superpowers/specs/2026-11-17-random-transition-design.md`.
Rules: fresh reviewer per cycle, cap 5 cycles, exit when only LOW/DOCS remain
(folded in, then the design is stamped approved). A cycle 5 that still
reports MEDIUM+ stops and asks James. Delegated by James 2026-11-18
("start the antagonist loop, mark approved when approved").

Pre-loop reconciliation (2026-11-18, before cycle 1): default pool 17 → 15
(registry re-read on origin/main); rules 72/73 → 73/74 (71/72 taken by the
validate pattern table); factory steps 2/4 rewritten to clone-and-overlay with
exact `"duration" in entry`; `easing` removed from per-entry keys; decision 3
corrected (`default` IS the `between_sections` fallback object when
`between_sections` is omitted); `_iter_transition_slots` DRY move and rule 53
extension added; CLAUDE.md sprite-family lines located by content.

## Cycle 1

Reviewer: fresh fable subagent. VERDICT: 1 HIGH, 4 MEDIUM, 8 LOW, 4 DOCS.

- HIGH widget-slot `transition_fn=None` + non-None config → `run_transition(transition=None)` raises (pre-existing, reachable from one bad pool member). Verified in `ticker.py:857-864` / `run.py:1361-1371`. FOLDED: campsite fix + tripwire added to the design.
- MEDIUM pick-on-`t>=1.0` depends on easing endpoints (plugin easings share `EASING`). FOLDED: advance moved to a runner-called `end_firing()` hook in `finally`; `frame_at` is pure delegation.
- MEDIUM `transition_colors` dead under random/auto; inherited `colors` shadows an entry's `transition_color`. FOLDED: overlay clears `colors` on entry `transition_color` (and vice versa); rule 73 parent-level warning; rule 74 skips pool children and warns on `transition_colors` for every non-dotted type except the two colour wrappers.
- MEDIUM decision-3 warnings mis-model typeless tables; rule 66 false-warns on `between_sections = { pool = [...] }`. FOLDED: 3(a) conditions on `type_specified`, 3(b) covers section `transition`, rule 66 skip added.
- MEDIUM `_iter_transition_slots` not behaviour-neutral (seven loops, three slot sets). FOLDED: helper gets `include_default`; 39/53/66 True, 57/60/scroll-sep False, rule 50 not moved; one pin test per moved rule.
- LOW ×8 all FOLDED: rule 73 does its own build attempt (53 untouched); rule 74 load-time non-iterable note; `is not None` for `duration_override`; rule 21 bounds on entry durations; per-instance no-repeat scope documented + instance tag in the DEBUG line; aliasing hazard noted in decision 3 and filed as follow-up; unknown keys on non-dotted entries refused; `exclude` names validated.
- DOCS ×4 all FOLDED: separator knobs dropped from the overlay; CLAUDE.md five sites; gate §5 17 → 15; test wording 61 `frame_at` calls.

## Cycle 2

Reviewer: fresh fable subagent. VERDICT: 1 HIGH, 4 MEDIUM, 6 LOW, 3 DOCS.

- HIGH pool-entry colour shape had no owner (`"red"` would reach `SetPixel` via a child; `255` / `[255,0]` would raise out of `validate_config`). FOLDED: one shared `coercion.rgb_shape_error` used by the factory helper (clean `ValueError` at build), rule 73 per entry, and rule 74; rule 73's build attempt catches `Exception`.
- MEDIUM campsite tripwire targeted the wrong layer. FOLDED: guard moves to `ticker._run_swap` (`transition_fn is not None`), tripwire at `Ticker` level.
- MEDIUM entry `duration` type/range unowned at the factory; string would crash the runner. FOLDED: factory refuses non-numeric / bool / `<= 0`; rule 73 type-checks first; `is not None` test uses 0.05.
- MEDIUM rule 74 slot gating unspecified; common misconfiguration lands on the shared `default` object. FOLDED: `include_default=True`, location quirk named in the message.
- MEDIUM parent `transition_color` + `transition_colors` lost both on core children. FOLDED: helper drops `colors` for non-dotted children; rule 73 warning reworded and conditioned on a non-dotted member.
- LOW ×6 FOLDED: rule 74 skips random/auto for the colours warning; warning text covers dotted `colors` consumers; 3(a) also requires no typeless section table; `auto` lock-step documented, index 0 pinned, two-section hardware case; `end_firing` after both resumes, try/except logged; `DEFAULT_SCALE_SWITCH_AT` hoisted.
- DOCS ×3 FOLDED: cancel wording; rule 60 stays its own loop, rule 66 order note; gate §5-B/§8 marked superseded.

## Cycle 3

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 2 MEDIUM, 5 LOW, 4 DOCS.

- MEDIUM the design's own pool example did not build (`flair.splitflap` unregistered; `flair.sand` takes no `colors`). FOLDED: `flair.splitflap.forward`, `flair.fireworks` (declares `colors`).
- MEDIUM a non-dotted entry's own `transition_colors` was a silent double-drop. FOLDED: refused by the factory and rule 73 (ERROR) on non-dotted entries.
- LOW ×5 FOLDED: 3(b) fires only for a key the typeless table does not write itself; nested-picker match on the final `.`/`_` token; dotted-without-duration warning only in a mixed pool; colour predicate pinned as `list | tuple` of 3 non-bool ints 0..255; first pick logged at construction.
- DOCS ×4 FOLDED: separator knobs removed from entry-key lists (config surface, decision 2); factory refusal scope split stated; gate banner extended to §6.1; load-time carve-out names both singular and flat-plural shapes.
- Follow-ups noted (pre-existing, not folded): firebird example's `[transitions] transition_colors` is never read; rule 21 has no type guard.

## Cycle 4

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 2 MEDIUM, 6 LOW, 5 DOCS.

- MEDIUM nested-picker token match false-positives on the leaf `flair.splitflap.random`; family pickers forward shared `min_frames`/`scale_switch_at`, so the stale-read rationale was overstated. FOLDED: downgraded to a validate-only WARNING; decision 4 rewritten; ERROR kept for the core wrappers and random/auto nesting.
- MEDIUM factory and rule 73 not one-for-one (token check, entry shape, `exclude` names, string pool/exclude). FOLDED: factory gains list/entry-shape/exclude-name checks before the clone; rule 73 mirrors the string case; the token check is explicitly validate-only.
- LOW ×6 FOLDED: dotted children keep inherited `colors` only when the constructor declares it; stub-level `0.0` test pins `is not None`; dedupe by name before the size check; named tests for every refusal and warning; did-you-mean for `color`/`colors`; `_sprite_migration` hint filed as follow-up.
- DOCS ×5 FOLDED: N+1 pick lines; `between_sections` build path named; stale gate bullet dropped; decision 1/2 wording; sixth CLAUDE.md site.

## Cycle 5

Reviewer: fresh fable subagent. VERDICT: 0 HIGH, 0 MEDIUM, 5 LOW, 4 DOCS → loop exits (cap reached with only LOW/DOCS).

- LOW ×5 FOLDED: dedupe on the normalised entry (same `type` with different knobs stays distinct; no-repeat by index; pick line carries the index); non-str `type` / `exclude` elements refused before any registry lookup; an entry's own `transition_colors` on a `color`-only dotted child is an ERROR / ValueError; `exclude` matches `type`, absent names warn; `rng: random.Random | None = None` constructor kwarg.
- DOCS ×4 FOLDED: decision 2 carries the declares-`colors` clause; decision 4 mechanism reworded; "five" → "six" CLAUDE.md sites; parent-level sentences prefixed.

## Exit

Design stamped APPROVED 2026-11-18. Severity trend: 1H/4M → 1H/4M → 0H/2M → 0H/2M → 0H/0M.
Next: plan (`docs/superpowers/plans/2026-11-18-random-transition.md`), build in `../led-ticker-random-transition`, per-PR antagonist loop (separate ledger).

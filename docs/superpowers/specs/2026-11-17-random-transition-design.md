# Design: `random` and `auto` meta-transitions

Roadmap item 2, approach B plus per-child duration (picked by James 2026-11-17).
Gate: `2026-11-17-random-transition-gate.md`. Status: APPROVED 2026-11-18 via the design antagonist loop (5 cycles, exit on LOW/DOCS only; delegated by James: "start the antagonist loop, mark approved when approved"). Ledger: `docs/superpowers/reviews/2026-11-18-random-transition-design-antagonist.md`. Size: a project (new module, a runner hook, a config/factory seam,
validate rules, docs).

## Intent and why

Variety between messages the way Alpha Automode and Huidu Random give it, but
able to include this project's plugin effects without mis-timing them. Usable
in every slot the engine actually runs: `between_sections` and the
per-section `transition`, `entry_transition`, `widget_transition`
(`[transitions] default` is only an inheritance base, see decision 3).

## Goals / non-goals / anti-goals

- Goals: `transition = "random"` (no back-to-back repeat) and
  `transition = "auto"` (cycle in order) over a core-only default pool; a
  table form with `pool` / `exclude`; a pool entry may carry its own
  `duration` and other transition knobs; the runner honours a per-firing
  duration; validate catches bad pools; the four existing core wrappers and
  every other transition are byte-identical.
- Non-goals: unifying `push_random` / `wipe_random` / `*_alternating` with
  flair's `Cycling` / `RandomNoRepeat` (own item, needs API bump + release);
  shuffle-bag policy (possible later knob); weighting.
- Anti-goals: a mid-sweep resize on a cross-scale entry because the runner
  read the wrong child's `scale_switch_at`; children rebuilt per firing; a
  pool that silently shrinks to one member; `scroll` or `cut` inside a pool.

## Approaches considered

A fixed core pool with no knob (rejected: 54 of 210 per-section transition
lines in the example configs pick plugin effects, and the live smallsign's
are 8 of 9). B pool/exclude knobs (chosen) plus per-child duration (chosen,
it is what makes plugin children safe). C B plus unifying the core wrappers
(deferred).

## Design

### Config surface

```toml
transition = "random"                       # default pool, section duration
transition = "auto"                         # same pool, registry order
transition = { type = "random", exclude = ["color_flash", "dissolve"] }
transition = { type = "random", pool = [
  "wipe_in", "push_up",
  { type = "flair.splitflap.forward", duration = 3.0 },
  { type = "flair.fireworks", duration = 2.0, colors = [[255,110,0],[255,190,40]] },
] }
```

- `pool`: list; each entry is a transition name or a transition table (same
  shape as any transition table: `type` required, plus `duration`,
  `transition_color`, and plugin kwargs; a dotted entry may also set
  `transition_colors`; `easing` / `transition_fps` / separator knobs are
  refused on every entry, see decision 1, and `transition_colors` is refused
  on a non-dotted entry because no core pool member takes it). Entries
  inherit the parent's knobs unless they set their own, by cloning the parent
  `TransitionConfig` and overlaying the entry's keys (decision 2; colours
  have extra rules there).
- `exclude`: list of names dropped from the pool (default or explicit); it
  matches an entry's `type`. A registered name that is not in the pool is a
  no-op at runtime and a rule-73 WARNING.
- Default pool: every registered NON-dotted transition except the hard
  exclusions `cut`, `scroll`, `random`, `auto` and the existing wrappers
  `push_random`, `push_alternating`, `wipe_random`, `wipe_alternating`.
  Fifteen members today (`color_flash`, `dissolve`, `push_down`, `push_left`,
  `push_right`, `push_up`, `split`, `wipe_down`, `wipe_in`,
  `wipe_in_vertical`, `wipe_left`, `wipe_out`, `wipe_out_vertical`,
  `wipe_right`, `wipe_up`); grows automatically with new core transitions.
  Plugin (dotted) transitions join only through an explicit `pool`.
- `auto` order: the `pool` list order when given, else sorted registry order.

### Classes (`src/led_ticker/transitions/meta.py`, auto-discovered)

`_PickAhead` base, registered subclasses `RandomTransition` (`"random"`) and
`AutoTransition` (`"auto"`).

- Constructed with `children: list[Transition]` and
  `durations: list[float | None]` (None = use the section's duration) plus
  `names` for logging; built ONCE per wrapper instance (the M6 lesson), by the
  factory, never inside `frame_at`.
- Holds `_current`: the index that the NEXT firing will run. At
  construction it is 0 for `auto` (first member) and a seeded-RNG pick for
  `random`; re-chosen by `end_firing()`, which the runner calls once
  per firing after its frame loop (see Runner hooks). The pick is NOT keyed
  on `t`: plugin easings join the same `EASING` dict (`api.easing`), so a
  `t >= 1.0` rule would depend on every easing's endpoint. So the runner's
  one-time reads before a firing see the child that will actually run:
  - `min_frames` -> `getattr(children[_current], "min_frames", Transition.min_frames)`
  - `scale_switch_at` -> `getattr(children[_current], "scale_switch_at",
    DEFAULT_SCALE_SWITCH_AT)` where `DEFAULT_SCALE_SWITCH_AT = 0.5` is hoisted
    in `transitions/__init__.py` and the runner's own `getattr` default uses
    it too (no drift).
  - `duration_override` -> `durations[_current]`
- `frame_at` is pure delegation to `children[_current]`. A caller outside
  `run_transition` that drives `frame_at` itself must call `end_firing()`
  when its firing ends or the same child replays (documented on the class).
- Constructor signature `_PickAhead(children, durations, names, *,
  rng: random.Random | None = None)`; `RandomTransition` uses `rng or
  random.Random()` (the factory passes none; tests pass a seeded one so the
  construction-time pick is deterministic too).
- `RandomTransition._advance`: choose uniformly among indices != current
  (never back-to-back by INDEX; two entries of the same `type` with
  different knobs are distinct members and may follow each other, so the
  pick line carries the index and the hardware check compares indices
  WITHIN this instance; a section's entry and widget slots are separate
  instances via `_cached_trans_obj`, and `between_sections` is a third built
  by `_build_trans_obj_guarded` in `run()` / on reload, so the panel may
  legitimately show the same child on an entry and the next widget swap).
- `AutoTransition._advance`: `(current + 1) % n`, per instance. Instances
  are per `(role, id(cfg))`, so N sections each writing `transition = "auto"`
  all start at member 0 and lock-step on the first pass; the docs say to
  prefer `between_sections = "auto"` for cross-section cycling, and the
  hardware plan includes a two-section case.
- Logs the pick at DEBUG with an instance tag so the hardware check can
  count repeats per instance:
  `transition random[1f3a]: next = wipe_in (duration 0.6s)`, emitted at
  construction for the first pick as well as from every `end_firing`, so a
  log of N firings has N+1 pick lines, the first N naming the firings that
  ran.
- Pool size < 2 raises `ValueError` at construction (clean config error).

### Runner hooks (`transitions/__init__.py::run_transition`)

Two additive `getattr` hooks; no existing transition defines either name,
so every other transition is byte-identical.

1. After `ease_fn`, before `frame_count` (so `frame_count`, `min_frames`
   flooring and the `duration_ms` kwarg all see it):

   ```python
   override = getattr(transition, "duration_override", None)
   if override is not None:
       duration = override
   ```

   (`is not None`, not `or`: a `0.0` must not silently fall back.)

2. In the existing `finally` after the frame loop, AFTER both
   `_resume_presenter` calls (so a raising hook can never leave a widget
   paused), and swallowed like an overlay hook (bookkeeping must never
   escape `run_transition` or mask the loop's own exception):

   ```python
   end = getattr(transition, "end_firing", None)
   if callable(end):
       try:
           end()
       except Exception:
           logger.exception("transition end_firing hook failed")
   ```

   `finally` so a firing ended by task cancellation (shutdown) or by a
   `frame_at` exception still advances (every started firing counts once;
   hot reload never interrupts a transition, it lands at the outer-loop top
   and the per-section seam). Both call sites (`app/run.py` entry,
   `ticker.py` within-section) go through `run_transition`, so both get
   both hooks. `_scroll_between` is untouched because `scroll` is a hard
   exclusion (and `is_scroll` is an `isinstance(..., Scroll)` check the
   wrapper never passes).

### Factory seam (`app/factories.py::_build_trans_obj`)

For `trans_cfg.type in ("random", "auto")`:

1. Read `pool` / `exclude` from `trans_cfg.extra` (they are non-built-in keys
   so config already carries them there). Any other key in `extra` is an
   error ("random/auto accept pool and exclude only").
2. Resolve member list: explicit `pool` entries -> child `TransitionConfig`s
   via a small factories helper `_child_transition_cfg(parent, entry)`:
   `dataclasses.replace(parent, extra={})` then overlay the entry's keys.
   A string entry overlays `type` only. A table overlays `type`, `duration`,
   `transition_color` / `transition_colors` (coerced to tuples exactly as
   `config._parse_transition` does, but through one shared shape check,
   `coercion.rgb_shape_error(value) -> str | None` / `rgb_list_shape_error`,
   that returns a message for anything that is not a 3-list of ints 0..255,
   so a bad entry colour is a clean `ValueError` at build and never reaches
   `SetPixel`) and carries its non-built-in keys as the child's `extra`.
   Colour forwarding rules: an entry that sets `transition_color` clears the
   inherited `colors` (and vice versa), because `_build_trans_obj` forwards
   `colors` in preference to `color`; and for a NON-dotted child the
   inherited `colors` is always dropped (no core pool member takes
   `colors`; `wipe_random` / `wipe_alternating` are hard-excluded), so a
   parent `transition_color` reaches core children even when the parent
   also wrote `transition_colors`. Dotted children keep the inherited
   `colors` ONLY when the constructor declares `colors`
   (`_allowed_init_kwargs`); a dotted child with a `color`-only constructor
   (flair fairy / lightning) has the list dropped so the parent's `color`
   reaches it (the dotted path forwards `colors` in preference to `color`).
   The PARENT's separator knobs, `easing`, `transition_fps` and
   `type_specified` are cloned by `replace` but never honoured (no pool member reads them; the
   runner takes easing/fps from the parent slot). Shape checks run BEFORE
   the clone: `pool` and `exclude` must be lists (a TOML string would
   iterate per character), each entry a `str` or a table whose `type` value
   is a `str`, every `exclude` element a `str` (checked BEFORE any registry
   lookup: `explain_unknown_transition(5)` raises `TypeError`), every
   `exclude` name registered. Default pool names -> the same helper with a
   string entry. Apply `exclude` (by `type`), then dedupe on the NORMALISED
   entry (a bare name for a string; `type` plus the overlaid knobs for a
   table), first occurrence wins, BEFORE the size check: `["wipe_in",
   "wipe_in"]` is "1 distinct member" and raises, while `[{type="dissolve",
   duration=0.3}, {type="dissolve", duration=3.0}]` is two legitimate
   members (and `auto` over `[a, b, a, c]` keeps its sequence only when the
   repeated entries differ; identical repeats collapse). Refusals, all
   `ValueError`: non-list `pool`/`exclude`; a malformed entry (non-str,
   table without `type`, non-str `type`, non-str `exclude` element); an
   unregistered `pool` or `exclude` name; hard exclusions; nesting
   (`random`/`auto` inside a pool); `easing` / `transition_fps` / separator
   knobs on ANY entry; `transition_colors` on a NON-dotted entry or on a
   dotted entry whose constructor does not declare `colors` ("member takes
   transition_color, not transition_colors", the `_allowed_init_kwargs`
   check applied to the entry's OWN list as well as the inherited one);
   unknown (non-built-in) keys on a NON-dotted entry (the unknown-key
   message carries a did-you-mean for `color` -> `transition_color` and
   `colors` -> `transition_colors`, the shape the config-options page
   currently shows); a bad colour shape; an entry `duration` that is not a
   positive int/float (bool excluded, `<= 0` refused); fewer than 2 distinct
   members. Rule 73 mirrors each refusal one-for-one as an ERROR; its
   WARNINGs (below) have no factory counterpart.
3. Build each child with `_build_trans_obj(child_cfg)` (reusing color
   forwarding and plugin kwargs). A child that fails to build fails the
   wrapper; the guarded caller logs once and falls back to cut. That
   fallback is only safe once the campsite fix below lands.
4. `durations[i] = entry["duration"] if "duration" in entry else None`
   (exact: the helper sees the raw entry, so no equality heuristic).
5. Return `RandomTransition(children, durations, names)` or `AutoTransition(...)`.

### Campsite: unbuildable widget-slot transition crashes the engine

Pre-existing, found by the cycle-1 design review. `app/run.py` (widget
transition precedence block) sets `transition_fn = _cached_trans_obj(...)`,
which is `None` after a build failure, but still sets
`transition_config = widget_trans_cfg`; `ticker.py::_run_swap` dispatches on
`transition_config is not None` and calls `run_transition(...,
transition=None)`, which raises `AttributeError` on the first widget swap
and escapes `run()` (only `CancelledError` / `RestartRequested` are caught).
Today reachable with any uninstalled plugin `widget_transition`; with
random/auto one bad pool member reaches it. Fix in this PR, at the layer
the tripwire exercises: `ticker._run_swap`'s branch becomes
`elif self.transition_config is not None and self.transition_fn is not
None:` (a `None` fn falls through to the cut path; `Ticker` is a public
constructor so the guard belongs there, and the entry slot already tolerates
`None`, `run.py::_entry_transition_active`); tripwire drives
`Ticker.run_slideshow` with `transition_config` set and `transition_fn=None`
and asserts a cut, not a raise.

### Validate (`validate.py`)

- `_iter_transition_slots(config, *, include_default: bool)` yields
  `(trans_cfg, location)` with the rule-39 gating: `default` only when
  `include_default`; `between_sections` when specified; `section.transition`
  when `transition_specified`; `entry_transition` / `widget_transition` when
  not None. Rules 39, 53 and 66 move onto it with `include_default=True`
  (66's issue order changes from between_sections-then-default to
  default-then-between_sections; not a regression); rule 57 and the
  scroll-separator-font check with `False` (they skip `default` today).
  NOT moved: rule 50 (`transition_fps`, iterates every `section.transition`
  ungated) and rule 60 (carries an inline per-section `separator_size` check
  the helper cannot yield). One test per moved rule pins `default`
  inclusion/exclusion; the existing rule tests guard the rest. The new rules
  73/74 use the helper with `include_default=True` (so a
  `default = { type = "random", pool = [...] }` is checked once, not once
  per section).
- Rule 73 (random/auto pool) on every slot:
  - `extra` keys ⊆ {pool, exclude} (ERROR).
  - `pool` / `exclude` must be lists (ERROR; a string is NOT iterated);
    `pool` entries are strings or tables whose `type` is a string, and
    `exclude` elements are strings (ERROR, checked before any registry
    lookup); every `pool` AND `exclude` name registered (ERROR, rule 39's
    unknown-name explanation); a registered `exclude` name absent from the
    pool (WARNING); hard-excluded or nested (`random`/`auto`) members
    (ERROR); `easing` / `transition_fps` / separator knobs on any entry
    (ERROR "section-level only" / "scroll only"); `transition_colors` on a
    non-dotted entry, or on a dotted entry whose constructor does not
    declare `colors` (ERROR "member takes transition_color, not
    transition_colors"); unknown keys on a non-dotted entry (ERROR, with the
    `color` / `colors` did-you-mean).
  - A plugin member whose final `.`- or `_`-separated name token is
    `random` / `alternating` (WARNING "looks like a variant picker; the pool
    already provides variety; list the variants themselves if so" — a
    warning, not an error, because a leaf such as `flair.splitflap.random`
    shares the shape; validate-only, no factory counterpart).
  - Distinct member count >= 2 after `exclude` and normalised-entry dedupe
    (ERROR "pool has N distinct member(s)"); identical duplicate entries
    (WARNING).
  - Entry `duration`: must be an int/float (not bool) — a string or other
    type is an ERROR checked BEFORE any comparison; `<= 0` ERROR; plus rule
    21's two bounds (`> 5 s` "looks like milliseconds", `< 0.05 s`) as
    WARNINGs.
  - Entry `transition_color` / `transition_colors`: rule 74's shape
    predicate (the shared `rgb_shape_error`) applied per entry, ERROR; this
    runs before the build attempt.
  - A dotted member without its own `duration`, only in a MIXED pool (at
    least one non-dotted member; an all-dotted pool's section duration was
    written for those members) (WARNING: "shares the section's N s; plugin
    effects usually want their own duration").
  - `transition_colors` on the parent when the pool has at least one
    non-dotted member (WARNING, once, parent level: "core members ignore
    transition_colors and take transition_color; only plugin members that
    declare `colors` receive the list").
  - When the static checks pass, rule 73 itself attempts
    `_build_trans_obj(trans_cfg)` and reports ANY `Exception` (a plugin
    child's unknown/missing kwargs, or a child constructor's own refusal)
    under rule 73, so validate never raises on a bad entry; rule 53 keeps
    skipping non-dotted types, so nothing double-reports.
  - Decision-3 shapes: (a) `default` is `random`/`auto` AND
    `between_sections` is specified with `type_specified` AND no section has
    `transition_specified and not transition.type_specified` (a typeless
    section table inherits `default`'s type, so it does run there) (WARNING
    "default never runs"); (b) a typeless table (`between_sections` or a section
    `transition`) inheriting `random`/`auto` from a `default` that carries
    `pool`/`exclude` that the typeless table does NOT write itself
    (`between_sections = { pool = [...] }` under such a `default` is fine;
    `{ duration = 1.0 }` is not) (WARNING "pool/exclude are not inherited").
  - Rule 66 is amended to skip a typeless table whose inherited type is
    `random`/`auto` and whose `extra` ⊆ {pool, exclude}: that shape works.
- Rule 74 (color shape, campsite from item 1): the shared predicate accepts
  a `list | tuple` of exactly 3 `int` (bool excluded explicitly; floats
  refused, the C binding wants ints) each in 0..255, and for
  `transition_colors` a `list | tuple` whose every element passes it (ERROR;
  today `"red"` -> `('r','e','d')` and `[255, 0]` reach `SetPixel` on
  hardware and raise). Validate sees TUPLES on slots (`_parse_transition`
  and the per-section override already `tuple(...)` them) and raw TOML
  lists on pool entries, hence `list | tuple`. Non-iterable shapes
  (`transition_color = 255`, or a flat `transition_colors = [255, 0, 0]`
  whose elements are ints) already fail inside `load_config` as a rule-less
  load error, which stays; rule 74's tests do not expect a rule-74 issue
  for them). `transition_colors`
  on any non-dotted type other than `wipe_random` / `wipe_alternating` is
  dropped by the constructor -> WARNING naming `transition_color`; rule 74
  skips `random` / `auto` slots for that warning (rule 73 owns it there).
  Rule 74 runs on the slots with `include_default=True`, not on pool
  children (rule 73 applies the same predicate to entries). Location quirk,
  named in the message: a section WITHOUT its own `transition` that writes
  `transition_color = ...` mutates the shared `default_transition` object
  (`load_config` per-section overrides), so the issue is reported at
  `transitions.default` with "(also written by a section's transition_color
  on a section without its own transition)".

### Docs

- `docs/content-source/transitions/special.md`: rows for `random` and `auto`
  plus a "Pools" subsection with the table example, the duration caveat, the
  per-instance scope of "no repeat", and which slots are live (decision 3).
- `docs/site/src/content/docs/transitions/index.mdx`: a short "Random and
  auto" block under per-section overrides linking to special.
- `CLAUDE.md`: Transition System gains a "Meta" bullet (pick-ahead rule,
  `duration_override` / `end_firing`, hard exclusions, the widget-slot
  `transition_fn is None` invariant); the sprite-family "one package per
  family" claims corrected to "inside the flair package
  (`led_ticker_flair/{nyancat,pokeball,pacman,sailor_moon}`)" at all six
  sites located by content: the file-map comment under `effects.py`, the
  "Hi-res transition infra" bullet, the Transition System "Sprite-trail"
  bullet, the Plugin invariants intro, the Plugin ecosystem bullet, and the
  "Extracted widgets retain core hooks" bullet ("the sprite-trail packages").
- Config-options drift test is unaffected (`TransitionConfig` unchanged).

### Tests

- Pick-ahead tripwire: pool `[dissolve, wipe_left]`, assert that before every
  firing `min_frames` and `scale_switch_at` equal the child that then runs;
  an end-to-end `run_transition` on a cross-scale banded entry never re-wraps
  before the final frame when the running child is a sweep; `end_firing` is
  called exactly once per `run_transition` (including a cancelled one) and
  `frame_at` never advances on its own.
- No back-to-back repeat over 200 firings; `auto` visits every member once
  per cycle in order; default pool equals the registry minus exclusions
  (names listed, 15 today); pool of 1 and nested/hard-excluded members raise
  at build; children constructed exactly once across 50 firings (counting
  constructor calls on a stub child).
- `duration_override`: a 3.0 s child under a 0.5 s section gives
  `frame_count = 60`, so `frame_at` is called 61 times (`range(frame_count
  + 1)`) and `duration_ms=3000`; `None` falls back to the section's; a
  `0.05` override under a 0.5 s section with a `min_frames`-less stub child
  gives `frame_count = 1` (override shortens below the section); a
  runner-level stub with `duration_override = 0.0` (bypassing the factory,
  which refuses it) gives `frame_count = 1`, not the section's 10 (pins
  `is not None` over `or`).
- `end_firing` runs after both `resume_frame` calls and a raising hook is
  logged, not propagated; the two defaults the wrapper forwards equal the
  runner's (`DEFAULT_SCALE_SWITCH_AT`, `Transition.min_frames`).
- Colour forwarding: parent `transition_color` + `transition_colors` →
  every core child gets the `color`; a dotted stub child declaring `colors`
  gets the list; a bad entry colour (`"red"`, `[255, 0]`, `255`) is a
  `ValueError` at build and a rule-73 ERROR at validate (never a
  `TypeError` / `IndexError` out of `validate_config`).
- Per-child knobs: a pool entry with its own `transition_color` reaches the
  child even when the parent set `transition_colors`; a plugin-style entry's
  extra kwargs reach its constructor.
- Factory refusals, one named test each (`test_pool_refuses_*`): non-list
  `pool` / `exclude`; malformed entry (`5`, a table without `type`);
  unregistered `pool` name; unregistered `exclude` name; hard exclusion;
  nesting; `easing`, `transition_fps`, separator knob on an entry;
  `transition_colors` on a non-dotted entry; unknown key on a non-dotted
  entry with the did-you-mean text; bad colour shapes; `duration` string /
  bool / `0` / negative; duplicates collapsing below 2 distinct members;
  `exclude` shrinking the default pool below 2. Positive: `exclude` removes
  exactly the named members from the default pool; a `color`-only dotted
  stub child receives the parent's `color` when the parent also wrote
  `transition_colors`.
- Validate warnings, one named test each with its negative: variant-picker
  token (`nyancat.alternating` warns, `flair.splitflap.random` warns too,
  `nyancat.forward` does not); mixed-pool dotted-without-duration (all-
  dotted pool silent); parent `transition_colors` (all-dotted pool silent);
  3(a) and 3(b) including 3(b)'s "writes it itself" negative; duplicates.
- Construction-time DEBUG pick line carries the instance tag and the first
  child; `end_firing` lines follow.
- Campsite: `run_slideshow` with `transition_config` set and
  `transition_fn=None` performs a cut instead of raising.
- Validate rules 73 and 74, positive and negative, via `validate_config`,
  including the decision-3 shapes, the rule-66 skip, and a failing plugin
  child reported under 73 (not 53); one test per moved rule pins
  `_iter_transition_slots` default inclusion/exclusion.
- Registry count 21 -> 23; default pool names == the 15 listed; `wipe.py` /
  `push.py` / `effects.py` untouched.

## Process

Worktree `random-transition` off origin/main. TDD, mutation check before
every commit (commit BEFORE mutating). Antagonist loop capped at 5, exit on
LOW/DOCS only, cycle 5 with MEDIUM+ stops and asks. Hardware check via the
preview mirror on both signs: 20+ firings of `random`, no consecutive
repeats of the pool INDEX in the DEBUG log (per instance tag), no mid-sweep resize on a cross-scale entry, `auto`
cycles in order; a two-section `auto` config shows the documented
lock-step (so the docs claim is checked, not assumed). Ends ready-and-ask. Follow-ups filed, not folded: flair
README stale row (other repo), wrapper unification (approach C), the
`_sprite_migration` hint in `transitions/__init__.py` that still points at
`plugins/<family>` subdirectories, the config-options page's `color = ...`
inline-table example (should be `transition_color`), the firebird example's
unread `[transitions] transition_colors`, rule 21's missing type guard, and
the `_parse_transition(None, default)` aliasing hazard (decision 3).

## Builder-check decisions (2026-11-17)

Amended 2026-11-18 by the design antagonist loop (cycle 1): see
`docs/superpowers/reviews/2026-11-18-random-transition-design-antagonist.md`.

1. **Per-entry knobs that take effect per firing: `duration` only.** The runner
   gets `easing` and `transition_fps` from the section at both call sites;
   adding overrides for them widens the hook for no asked-for value. The
   factory and rule 73 both REFUSE `easing` / `transition_fps` inside a pool entry with the message
   "section-level only". Docs say so.
2. **Colors inherit.** Explicit pool entries inherit the parent's
   `transition_color` (and, for dotted entries, `transition_colors`) unless
   they set their own, the same as default-pool children. Implemented by
   cloning the parent `TransitionConfig` and overlaying the entry's keys
   (small helper in factories), NOT by `config._parse_transition`, which
   inherits duration/easing only. A parent `transition_colors` list reaches
   each DOTTED child whose constructor declares `colors`, whole, and is
   dropped for every other child (core members and `color`-only plugin
   members take `transition_color`);
   no zipping across children (zipping is `WipeAlternating`'s own policy).
   Separator knobs are cloned by `replace` but never honoured (scroll-only,
   and `scroll` is hard-excluded).
3. **`[transitions] default` is live for entries only through
   `between_sections`.** `config.load_config` parses `between_sections` with
   `default` as its base, so when `between_sections` is OMITTED the two are
   the same object and `default = "random"` (table form included, `extra`
   intact) runs on every section entry. A TYPELESS `between_sections` table
   (`{ pool = [...] }`, `{ duration = 1.0 }`) inherits `default`'s type but
   builds `extra` from its own keys, so `{ pool = [...] }` works (rule 66 is
   taught not to warn on it) while `{ duration = 1.0 }` silently drops a
   `pool`/`exclude` written on `default`; the same holds for a typeless
   section `transition` table (`entry_transition` / `widget_transition`
   parse against a bare `TransitionConfig()` and inherit `cut`). Within-
   section swaps never consult `default` (they fall to `cut` unless the
   section sets a transition), and when `between_sections` is written WITH
   a type, `default`'s type is dead. Rule 73's two warnings (a)/(b) encode
   exactly this (see Validate). The slots where `random`/`auto` run:
   `between_sections` (or `default` standing in for it), section
   `transition`, `entry_transition`, `widget_transition`. Two pre-existing
   oddities are noted and filed, not fixed: a `default` whose type never
   reaches within-section swaps (contrary to the docs table), and the
   aliasing hazard that `_parse_transition(None, default)` returns the SAME
   object which `load_config` then mutates for a section's
   `transition_duration` / `transition_fps` / `transition_color(s)` when the
   section omits `transition`, so one section's `transition_duration`
   retimes `default`, `between_sections` and every other inheriting section
   (and, under `default = "random"`, every default-pool child).

4. **No nested core pickers; plugin pickers warned.** Core `push_random` /
   `push_alternating` / `wipe_random` / `wipe_alternating` join the
   hard-exclusion set for explicit pools too (ERROR; their refire rule is
   the older `t`-keyed one and they add nothing a pool does not). A plugin
   member whose final `.`- or `_`-separated name token is `random` /
   `alternating` (`nyancat.alternating`, `baseball.roll_alternating`) gets a
   validate WARNING "looks like a variant picker; the pool already provides
   variety" and still builds: family pickers report family-shared values
   (next-child or child-0 `min_frames`; class-attribute or forwarded
   `scale_switch_at`; `laser.*` forwards `min_frames` only, a pre-existing
   flair gap that nesting neither causes nor worsens), so nesting costs only
   double randomness, not a stale pick-ahead read beyond what using the
   picker directly already has;
   and a leaf like `flair.splitflap.random` (random settle ORDER within one
   firing) shares the name shape and must not be refused.

## Left to the builder

Exact DEBUG log wording; whether `_PickAhead` exposes the current child name
for the status board; test stub shapes for a "child that fails to build".

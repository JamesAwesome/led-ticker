# Gate: item 2, global `random` / `auto` meta-transition

Roadmap: `2026-11-15-effects-roadmap.md`, item 2. Status: **gate open, awaiting
James's pick of approach and two answers.** No code written. Untracked.

## 1. What the audit asked for

Alpha AUTOMODE and Huidu's "Random" effect checkbox pick a different effect
per message. led-ticker only has per-family randoms (`push_random`,
`wipe_random`, flair `*.random`) and per-family cyclers (`*_alternating`).

> 2026-11-18: §5-B and §8 describe a kwargs-forwarding mechanism, and §6.1 a
> `t >= 1.0` / `t == 0.0` pick rule, both superseded by the design (the wrapper
> advances via a runner-called `end_firing()` hook; (`pool` / `exclude` are read from `TransitionConfig.extra` and
> children built via a clone-and-overlay helper). The design is authoritative.

## 2. What exists today (recon 2026-11-17)

- Core wrappers: `PushRandom`, `PushAlternating` (`push.py:227-284`),
  `WipeRandom`, `WipeAlternating` (`wipe.py:146-236`). Four hand-rolled
  copies of the same shape, differing in details: refire rule is `t < _last_t`
  only; `PushRandom` pre-picks a throwaway child in `__init__`; `WipeRandom`
  draws a random color per firing and reports `min_frames = 40` before the
  first firing; `WipeAlternating` zips `colors` to children.
- flair already abstracted the shape: `flair/_variants.py` has `Cycling` and
  `RandomNoRepeat` with a refined refire rule (`t == 0.0 or t < _last_t`, so
  a firing cancelled right after its t=0 frame cannot replay a stale variant)
  and forwards `min_frames` / `scale_switch_at` from child 0. Interlock and
  blinds use it; laser, accordion, splitflap, sprite families keep their own.
- The runner reads `min_frames` (`transitions/__init__.py:318`) and
  `scale_switch_at` (`:340`) off the wrapper ONCE, before the first `frame_at`.
  Any wrapper that picks its child inside `frame_at` reports the previous
  child's values. Harmless within one family; a mixed pool has `dissolve`
  (`scale_switch_at = 0.5`, no floor) beside sweeps (`1.0`, floors 16 to 40),
  so a wrong read reproduces the 2026-06-30 mid-sweep resize bug on
  cross-scale entries. **The meta-transition must pick its NEXT child ahead of
  the runner's read**, the way `WipeAlternating.min_frames` already reports the
  next child.
- One instance per section config, per role (`run._cached_trans_obj`, fix
  #532 after `.alternating` reset on every section entry). Hot reload clears
  the cache. So wrapper state lives for the life of a config load.
- `scroll` is dispatched to `ticker._scroll_between` (`ticker.py:844`) by
  type, bypassing `run_transition`; wrapped inside `random` it would run
  through `run_transition` instead and lose its continuous-strip semantics.
  `cut` builds to `None`. Both are hard exclusions, as are `random`/`auto`
  themselves.
- Built-in transitions never receive `extra` (`_build_trans_obj` forwards it
  for dotted types only), so `transition = {type = "random", pool = [...]}`
  would be silently dropped today. A pool knob is a seam in `factories.py`.
- Hi-res sprite families have a lowres path (`nyancat.py:278`), so scale 1
  needs no pool exclusion.
- Config evidence of demand: `config/config.random_transitions.toml` exists;
  the smallsign's live config runs `between_sections = nyancat.alternating`
  at 4.0 s beside a 0.5 s default, and a three-color `transition_colors`
  pool. Variety is wanted; a single duration feeding every child is the
  design problem.

## 3. Should we build: rubric

| Question | Evidence | Verdict |
|---|---|---|
| Wanted? | Alpha AUTOMODE and Huidu Random in vendor lists; in-repo `config.random_transitions.toml`; the live smallsign config already reaches for variety (alternating sprite entry, color pools). | **Yes, stronger than item 1.** |
| Good design? | Fits the existing wrapper pattern and the per-section-instance cache. Risk: one `transition_duration` for children that want 0.5 s (wipes) vs 3 s (splitflap) vs 4 s (sprite trails). A default pool restricted to core hard-edged + dissolve + color_flash keeps durations compatible; plugin children only by explicit pool. | OK with a restricted default pool. |
| Too hard? | Seams: new module; `_build_trans_obj` must forward `pool`/`exclude` to a built-in; validate rule for pool members (registered, buildable, not cut/scroll/random/auto, size >= 2); docs. Medium. The DRY of the four core wrappers is a behavior change (see §6) and is scoped separately. | Medium. |
| Reviews poor? | Two real bugs in this exact shape: `92fc7fa7` (PushRandom sub-transition pre-construction, M6) and #532 (wrapper rebuilt per entry, cycle reset). Both are instance-lifetime and first-firing issues; the design must state its answers to both. | Known failure modes, both addressable. |

## 4. Research and sourcing (read 2026-11-17)

- Alpha 215 remote manual (<https://daylight.net/manuals/alpha-215-remote-control.pdf>,
  text extracted): "Because Automode [AUT] was used in your message ... the
  text of your message will be displayed in a variety of formats." Automode
  picks among the sign's modes at the sign's speed; no per-mode duration.
- Python `random` docs (<https://docs.python.org/3/library/random.html>):
  "You can instantiate your own instances of Random to get generators that
  don't share state." and "By reusing a seed value, the same sequence should
  be reproducible from run to run." One `Random()` per wrapper instance (the
  flair/wipe precedent), seedable for tests.
- Fisher-Yates (<https://en.wikipedia.org/wiki/Fisher%E2%80%93Yates_shuffle>):
  "The algorithm produces an unbiased permutation: every permutation is
  equally likely", O(n), in place. This is what `random.shuffle` does and is
  the basis of a shuffle-bag policy (draw a permutation, deal it out, reshuffle).
- Shuffle play (<https://en.wikipedia.org/wiki/Shuffle_play>): "Shuffle
  playback prevents repeated tracks, which makes it distinct from random
  playback". Supports offering a no-repeat policy; says nothing about why.
- Family rule here is "never the same back-to-back" (`WipeRandom`,
  `RandomNoRepeat`). Keep it as the default; shuffle-bag is a possible knob,
  not a default.
- Huidu HD2018 manual: the effect list carries a "Random" checkbox (read in
  the 2026-11-15 audit; not re-opened for this gate).

## 5. Approaches

**A. Core `random` + `auto` with a fixed core pool, no knob.** Pool = every
core transition except `cut`, `scroll`, `random`, `auto` and the existing
`*_random` / `*_alternating` wrappers (so 15 members after item 1: 21 registered minus `cut`, `scroll` and the four wrappers).
`random` = no back-to-back repeat; `auto` = cycle in registry order. Picks
the next child at construction and after every completed firing, so the
runner's one-time read of `min_frames` / `scale_switch_at` sees the right
child. No config plumbing change. Plugin transitions never participate.

**B. A plus `pool = [...]` / `exclude = [...]` knobs.** Same classes; the
table form `transition = {type = "random", pool = ["wipe_in", "flair.sand"]}`
works because `_build_trans_obj` forwards declared kwargs to built-ins the
same way it does for plugins (`_allowed_init_kwargs`). Validate gains a rule:
members registered, not in the hard-exclusion set, at least two, each
buildable with the section's color knobs. Plugin children allowed, duration
mismatch is the user's call and documented.

**C. B plus unifying the four core wrappers on one core `Cycling` /
`RandomNoRepeat` base exported for flair.** Changes behavior of
`push_random` / `wipe_random` (refire rule, pre-pick, color policy) and
needs an `API_VERSION` bump and a core release before flair can adopt.
Right thing eventually, wrong PR to carry it.

Recommendation: **B**, with the DRY (C) split into its own later item after
characterization tests of the four wrappers exist. If James only wants
variety on `between_sections` with core effects, **A** is enough.

## 6. Decisions the design must settle

1. Picking ahead: wrapper holds `_next` chosen at init and re-chosen when a
   firing completes (`t >= 1.0`) or a new one starts without completion
   (`t == 0.0` after a non-1.0 `_last_t`). `min_frames` and `scale_switch_at`
   read from `_next`. Tripwire: a pool of `dissolve` + `wipe_left` on a
   cross-scale entry never re-wraps mid-sweep.
2. Children receive the section's `color` / `colors` where their constructor
   accepts them; children are built once per wrapper instance (no per-firing
   construction; the M6 lesson), via the same path `_build_trans_obj` uses.
3. Pool of one is a config error at build time and a validate error; an
   unbuildable member fails the whole wrapper (validate reports it; runtime
   falls back to cut via `_build_trans_obj_guarded` with one warning).
4. `auto` order: registry sort order, stable across releases only as long as
   names do not change; documented as such.
5. Docs: new rows in `docs/content-source/transitions/special.md`, a
   `random`/`auto` paragraph in `transitions/index.mdx` under per-section
   overrides, and the duration caveat.

## 7. Campsite and DRY

- Same seam, from item 1's loop: `transition_color` shape is unvalidated end
  to end (a string crashes `SetPixel` on hardware); `transition_colors` is
  silently dropped on single-direction wipes. The validate rule for pool
  members can carry the color-shape rule too.
- `CLAUDE.md` (lines 76, 106, 208) says the sprite families are per-family
  packages; they live under `plugins/flair/src/led_ticker_flair/{nyancat,...}`.
  Docs fix, this PR.
- flair README `transition_colors` "known gap" row is stale; other repo, own
  small PR.
- DRY of the four core wrappers: deferred to its own item (approach C).

## 8. Seams touched

`transitions/meta.py` (new, auto-discovered), `app/factories.py::_build_trans_obj`
(forward declared kwargs to built-ins), `validate.py` (new rule + color-shape
rule), `tests/test_transitions.py` registry count 21 -> 23, docs as in §6.5,
`CLAUDE.md` sprite-family lines.

## 9. Hardware check plan

Smallsign and bigsign, frames via the preview mirror as in item 1: a section
with `transition = "random"` over 20 firings, assert no two consecutive
identical children (log the pick per firing at DEBUG), no mid-sweep resize on
a cross-scale entry, and `auto` visiting every pool member once per cycle.

## 10. Questions for James

1. Where would you use it: `[transitions] default`, `between_sections`, or
   per section? (A fixed core pool serves the first two; per-section mixing
   with plugin effects wants B.)
2. Should plugin transitions be eligible at all, given one duration per
   section?

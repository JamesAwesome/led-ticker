# `random` / `auto` meta-transitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `transition = "random"` / `"auto"` (plus a `pool` / `exclude` table form with per-entry `duration`) picks one child transition per firing from a pool, with the runner honouring the child's own `min_frames`, `scale_switch_at` and duration.

**PR shape (per the roadmap process: DRY refactors and campsite fixes ship in a precursor PR attached to the seam's first consumer):**
- **PR A, branch `random-transition-precursor` off `origin/main`:** Task 3 (RGB predicates), Task 5 (ticker crash guard), Task 6a (`_iter_transition_slots` refactor), Task 6b (rule 74). Refactor + two pre-existing bugs, no feature. Its own antagonist loop.
- **PR B, branch `random-transition` stacked on A:** Tasks 1, 2, 4, 6c (rule 73 + rule 66 skip), 7, 8. Draft PR with base = A's branch; retarget to `main` after A merges.
Execution order below is A then B; each task commits on its PR's branch.

**Architecture:** A `_PickAhead` wrapper in `transitions/meta.py` holds pre-built children and the index of the NEXT firing; `run_transition` gains two additive `getattr` hooks (`duration_override` before `frame_count`, `end_firing()` in `finally`). The factory resolves the pool once per wrapper via clone-and-overlay child configs; validate rule 73 reuses the same resolver so refusals are one-for-one, rule 74 closes the item-1 colour-shape crash, and one `_iter_transition_slots` helper replaces five copy-pasted slot loops. One pre-existing crash (widget-slot `transition_fn=None`) is fixed in `ticker._run_swap`.

**Tech Stack:** Python 3.14 stdlib (`dataclasses.replace`, `random.Random`, `logging`), pytest (+ `caplog`, `monkeypatch`), existing `tests/conftest.py` fixtures (`canvas`, `mock_frame`, `make_widget`, `no_sleep`), `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-17-random-transition-design.md` (APPROVED 2026-11-18 via the design antagonist loop; ledger `docs/superpowers/reviews/2026-11-18-random-transition-design-antagonist.md`; gate `docs/superpowers/specs/2026-11-17-random-transition-gate.md`).

## Global Constraints

- Every other transition stays byte-identical: `wipe.py`, `push.py`, `effects.py`, `center_wipe.py` untouched; both hooks are `getattr`-additive.
- Hardware constraints (CLAUDE.md): swap return captured, no GetPixel, SetPixel/SubFill only, cross-scale re-wrap and bg cut-over keyed on the wrapper-forwarded `scale_switch_at`.
- Children are built ONCE per wrapper instance, never inside `frame_at`.
- Hard exclusions: `cut`, `scroll`, `random`, `auto`, `push_random`, `push_alternating`, `wipe_random`, `wipe_alternating`. Default pool = registered non-dotted names minus these = 15 today.
- Validate rule numbers: 73 (pools), 74 (colour shape). 71/72 are taken.
- `[dev]` tooling: `uv run pytest`, `uv run ruff check`, `uv run ruff format`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright` before push. No `from __future__ import annotations`.
- Commit BEFORE any mutation check (lesson from item 1). TDD per step.
- Docs follow `docs/DOCS-STYLE.md`; `special.md` is the fact-pack behind `<OptionsTable source="transitions/special" />`.

## Review Focus

Inputs the spec implies but no task's tests exercise directly; each gets the named test in the owning task:

1. A plugin easing with an endpoint ≠ 1.0 — the pick must still advance exactly once per firing (Task 1: `test_end_firing_called_once_with_custom_easing`).
2. `exclude` that empties the default pool to one member on a sign where a future core transition was added — error, not a one-member pool (Task 4: `test_pool_refuses_exclude_below_two`).
3. A hot reload that replaces the section config mid-run — the new wrapper instance starts fresh and the old one is dropped by `_cached_trans_obj` (Task 4: `test_cached_trans_obj_rebuilds_meta_on_new_cfg`).
4. A section without its own `transition` writing `transition_color = "red"` mutates the shared default object — rule 74 must still report it, at `transitions.default` (Task 6: `test_rule74_section_level_color_on_shared_default`).
5. A `random` wrapper whose child raises inside `frame_at` — the exception propagates out of `run_transition` (the breaker guards widget draws, not `frame_at`), both widgets are resumed, and `end_firing` still runs so the next firing is a fresh pick (Task 1: `test_end_firing_runs_after_frame_at_exception`).

---

### Task 1: Runner hooks and `DEFAULT_SCALE_SWITCH_AT`

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py` (module constant near `EASING`; `run_transition` body at the `ease_fn` / `frame_count` lines and the `finally`)
- Test: `tests/test_transitions_meta_hooks.py` (new)

**Interfaces:**
- Produces: `DEFAULT_SCALE_SWITCH_AT: float = 0.5` (module-level, exported in `__all__` if one exists); `run_transition` reads `transition.duration_override` (`float | None`, `is not None` test) before computing `frame_count`, and calls `transition.end_firing()` once in `finally` after both `_resume_presenter` calls, wrapped in `try/except Exception: logger.exception(...)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transitions_meta_hooks.py
class _Stub:
    """Transition stub: records frame_at calls and end_firing calls."""
    def __init__(self, duration_override=None, scale_switch_at=None):
        self.calls = []; self.ends = 0
        if duration_override is not None: self.duration_override = duration_override
        if scale_switch_at is not None: self.scale_switch_at = scale_switch_at
    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        self.calls.append((t, kw.get("duration_ms"))); return canvas
    def end_firing(self): self.ends += 1

async def test_duration_override_sets_frame_count_and_duration_ms(canvas, mock_frame, make_widget, no_sleep):
    s = _Stub(duration_override=3.0)
    await run_transition(canvas, mock_frame, make_widget(), make_widget(), transition=s, duration=0.5, scroll_speed=0.05)
    assert len(s.calls) == 61 and s.calls[0][1] == 3000

async def test_duration_override_none_uses_section_duration(...):  # 11 calls, duration_ms 500
async def test_duration_override_zero_is_honoured_not_or(...):      # override 0.0 → 2 calls (frame_count floors to 1), not 11
async def test_duration_override_shortens_below_section(...):       # 0.05 → 2 calls
async def test_end_firing_called_once_after_resume(...):            # ends == 1; order: a FrameAware-like stub records resume_frame before end_firing
async def test_end_firing_called_on_cancellation(...):              # cancel the task mid-loop (no_sleep + a frame_at that cancels); ends == 1
async def test_end_firing_runs_after_frame_at_exception(...):       # frame_at raises RuntimeError → propagates, ends == 1
async def test_end_firing_exception_is_logged_not_raised(caplog, ...):  # end_firing raises → run_transition returns, caplog has "end_firing"
async def test_end_firing_called_once_with_custom_easing(monkeypatch, ...):  # EASING["flat"] = lambda p: 0.5 → ends == 1
def test_default_scale_switch_at_constant_is_runner_default(monkeypatch, ...):
    # a transition WITHOUT scale_switch_at re-wraps at DEFAULT_SCALE_SWITCH_AT; monkeypatch it to 1.0 and assert the re-wrap moves to the final frame
async def test_transition_without_hooks_is_unchanged(...):          # a bare stub (no attrs) → 11 calls, no AttributeError
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_transitions_meta_hooks.py -q`
Expected: FAIL (`duration_ms` 500 not 3000; `ends == 0`; `DEFAULT_SCALE_SWITCH_AT` ImportError).

- [ ] **Step 3: Implement**

In `transitions/__init__.py`: add `DEFAULT_SCALE_SWITCH_AT: float = 0.5` beside `EASING`; replace the literal `0.5` in `getattr(transition, "scale_switch_at", 0.5)` with the constant; after `ease_fn = EASING[easing]` insert the `duration_override` block from the spec; extend the `finally` with the `end_firing` block AFTER the two resumes.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_transitions_meta_hooks.py tests/test_transitions.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/__init__.py tests/test_transitions_meta_hooks.py
git commit -m "feat(transitions): duration_override and end_firing runner hooks; hoist DEFAULT_SCALE_SWITCH_AT"
```

---

### Task 2: `meta.py` — `_PickAhead`, `RandomTransition`, `AutoTransition`

**Files:**
- Create: `src/led_ticker/transitions/meta.py`
- Modify: `src/led_ticker/transitions/__init__.py` (re-export `RandomTransition`, `AutoTransition`, `HARD_EXCLUDED`, `default_pool_names` beside the existing re-exports), `tests/test_transitions.py` (registry count 21 → 23 and the expected-names list)
- Test: `tests/test_transitions_meta.py` (new)

**Interfaces:**
- Produces:
  - `HARD_EXCLUDED: frozenset[str]` = the eight names above.
  - `default_pool_names() -> list[str]`: `sorted(n for n in list_transition_names() if "." not in n and n not in HARD_EXCLUDED)`.
  - `class _PickAhead: def __init__(self, children: list[Any], durations: list[float | None], names: list[str], *, rng: random.Random | None = None)`; raises `ValueError("random/auto pool needs at least 2 members; got N")` when `len(children) < 2` or the three lists differ in length.
  - Properties: `min_frames -> int`, `scale_switch_at -> float`, `duration_override -> float | None`, `current_name -> str`, `current_index -> int`.
  - `frame_at(t, canvas, outgoing, incoming, **kwargs)` → `self._children[self._current].frame_at(...)` (pure delegation).
  - `end_firing() -> None`: `self._current = self._advance(); self._log_pick()`.
  - `_advance(self) -> int` abstract; `_tag = f"{id(self) & 0xffff:04x}"`; DEBUG line `transition %s[%s]: next = %s (index %d, duration %s)` where duration is `f"{d:.2f}s"` or `"section"`.
  - `@register_transition("random") class RandomTransition(_PickAhead)`: `self._rng = rng or random.Random()`; construction pick `self._rng.randrange(n)`; `_advance` = `self._rng.choice([i for i in range(n) if i != self._current])`.
  - `@register_transition("auto") class AutoTransition(_PickAhead)`: construction pick 0; `_advance` = `(self._current + 1) % n`.
- Consumes: `Transition.min_frames` (= 0) and `DEFAULT_SCALE_SWITCH_AT` from Task 1 as the `getattr` defaults.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transitions_meta.py  (children are small stubs with min_frames / scale_switch_at attrs and a frame_at recorder)
def test_registry_has_random_and_auto(): get_transition_class("random") is RandomTransition; "auto" likewise
def test_default_pool_names_are_the_fifteen(): == [the 15 names from the spec]
def test_hard_excluded_set(): HARD_EXCLUDED == frozenset({...8 names...})
def test_pool_below_two_raises(): ValueError match "at least 2"
def test_mismatched_lengths_raise()
def test_properties_track_current_child(): min_frames / scale_switch_at / duration_override equal children[current]'s before each firing, for 20 firings
def test_properties_default_when_child_lacks_attrs(): child without attrs → 0 and DEFAULT_SCALE_SWITCH_AT
def test_frame_at_is_pure_delegation_and_never_advances(): call frame_at at t=0.0, 0.5, 1.0, 1.0 → current unchanged, child recorded 4 calls
def test_end_firing_advances(): current changes (auto) / stays a valid index (random)
def test_random_never_repeats_index_over_200_firings(): seeded rng
def test_random_rng_kwarg_makes_first_pick_deterministic(): two wrappers with Random(7) pick the same first index
def test_random_with_two_members_alternates()
def test_auto_starts_at_zero_and_cycles_in_order(): [0,1,2,0,1,2]
def test_pick_logged_at_construction_and_each_end_firing(caplog): N end_firing → N+1 DEBUG lines, each carrying the tag and "index"
def test_children_are_not_constructed_by_the_wrapper(): pass instances; a counting stub class's constructor count stays what the test made
```

Also in `tests/test_transitions.py`: change `assert len(_TRANSITION_REGISTRY) == 21` to `23` and add `"random", "auto"` to the expected list.

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_transitions_meta.py tests/test_transitions.py -q`; Expected: ImportError / count 21.
- [ ] **Step 3: Implement `meta.py`** per Interfaces; `logger = logging.getLogger(__name__)`.
- [ ] **Step 4: Run** — same command; Expected: PASS.
- [ ] **Step 5: Commit** — `feat(transitions): random/auto pick-ahead meta-transitions`

---

### Task 3: Shared RGB shape predicate

**Files:**
- Modify: `src/led_ticker/app/coercion.py`
- Test: `tests/test_coercion_rgb_shape.py` (new)

**Interfaces:**
- Produces: `rgb_shape_error(value: Any) -> str | None` — `None` when `value` is a `list | tuple` of exactly 3 `int` (bool excluded) each in 0..255; otherwise a message like `"expected [r, g, b] with three ints 0-255; got 'red'"`. `rgb_list_shape_error(value: Any) -> str | None` — `None` when `value` is a `list | tuple` whose every element passes `rgb_shape_error`; non-empty required.

- [ ] **Step 1: Failing tests** — accepts `[255,0,0]`, `(255,0,0)`, `[0,0,0]`; refuses `"red"`, `('r','e','d')`, `[255,0]`, `[255,0,0,0]`, `[255.0,0,0]`, `[True,False,True]`, `[256,0,0]`, `[-1,0,0]`, `None`, `255`; list variant accepts `[[1,2,3],[4,5,6]]`, refuses `[]`, `[[1,2]]`, `[1,2,3]` (flat), `"red"`.
- [ ] **Step 2: Run, expect ImportError.** — `uv run pytest tests/test_coercion_rgb_shape.py -q`
- [ ] **Step 3: Implement** the two functions (pure, no imports beyond typing).
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `feat(coercion): shared rgb_shape_error / rgb_list_shape_error predicates`

---

### Task 4: Factory seam — pool resolution and child configs

**Files:**
- Modify: `src/led_ticker/app/factories.py` (`_build_trans_obj` gains a `random`/`auto` branch before the dotted branch; new helpers below it)
- Test: `tests/test_factories_meta_transition.py` (new)

**Interfaces:**
- Consumes: Task 2 (`RandomTransition`, `AutoTransition`, `HARD_EXCLUDED`, `default_pool_names`), Task 3 predicates, existing `_allowed_init_kwargs`, `get_transition_class`, `explain_unknown_transition`, `config._BUILTIN_TRANSITION_KEYS`.
- Produces:
  - `_META_TYPES = ("random", "auto")`; `_ENTRY_REFUSED_KEYS = {"easing", "transition_fps", "separator", "separator_color", "separator_font", "separator_font_size", "separator_size"}`.
  - `_child_transition_cfg(parent: TransitionConfig, entry: str | dict[str, Any]) -> TransitionConfig`: `dataclasses.replace(parent, extra={}, type_specified=True)` then overlay. String entry → `type` only. Table → `type` (must be `str`), `duration` (int/float not bool, `> 0`, else ValueError), `transition_color` / `transition_colors` through the Task 3 predicates (ValueError on a message), non-built-in keys → child `extra`. Colour rules: entry `transition_color` clears `colors`; entry `transition_colors` clears `color`; for a non-dotted child `colors` is always `None`; for a dotted child `colors` is kept only if `"colors" in _allowed_init_kwargs(cls)` — when the ENTRY wrote `transition_colors` and the constructor lacks `colors`, raise `ValueError("... takes transition_color, not transition_colors")`; when only INHERITED, drop silently. Refusals (ValueError): `_ENTRY_REFUSED_KEYS` on any entry ("section-level only" / "scroll only"); `transition_colors` or unknown keys on a non-dotted entry (unknown-key message appends `did you mean transition_color?` for `color`, `transition_colors?` for `colors`); `type` in `HARD_EXCLUDED` ("cannot be a pool member"); `type` in `_META_TYPES` ("cannot nest"); unregistered type (rule 39's `explain_unknown_transition` message).
  - `_resolve_pool(trans_cfg: TransitionConfig) -> list[tuple[TransitionConfig, float | None, str]]`: validates `extra` keys ⊆ {pool, exclude}; `pool` / `exclude` are lists; `exclude` elements are `str` and registered; entries = explicit `pool` or `default_pool_names()`; apply `exclude` by `type`; build child cfgs; dedupe on the normalised entry via `_pool_entry_key(entry) -> tuple`: a string entry is first normalised to `{"type": name}`, then the key is `tuple(sorted((k, repr(v)) for k, v in table.items()))`, so `"wipe_in"` and `{ type = "wipe_in" }` collide; first wins; rule 73's duplicate WARNING uses the same function; require ≥ 2 distinct (`ValueError("random/auto pool has N distinct member(s); need at least 2")`). Returns `(child_cfg, entry_duration_or_None, display_name)` where display name is `type` (plus ` @Ns` when the entry set a duration).
  - `_build_meta_transition(trans_cfg: TransitionConfig) -> Transition`: `_resolve_pool`, build each child with `_build_trans_obj(child_cfg)`, return `RandomTransition(children, durations, names)` or `AutoTransition(...)`.
  - `_build_trans_obj`: `if trans_cfg.type in _META_TYPES: return _build_meta_transition(trans_cfg)` placed right after the `cut` return.

- [ ] **Step 1: Failing tests** (register a few dotted stubs via `register_transition("testmeta.colors")` etc. in a fixture and pop them from `_TRANSITION_REGISTRY` in teardown — follow `tests/test_registry_collision.py`):

```python
def test_bare_random_builds_default_pool_of_fifteen(): names == default_pool_names(), all durations None
def test_bare_auto_builds_in_sorted_order()
def test_exclude_removes_named_members(); def test_pool_refuses_exclude_below_two()
def test_explicit_pool_strings_and_tables(): durations [None, None, 3.0]
def test_entry_duration_reaches_wrapper_duration_override()
def test_pool_refuses_non_list_pool(); _non_list_exclude(); _non_str_exclude_element(); _unregistered_exclude_name()
def test_pool_refuses_malformed_entry_int(); _table_without_type(); _non_str_type()
def test_pool_refuses_unregistered_type(); _hard_excluded(); _nested_random(); _nested_auto()
@pytest.mark.parametrize("key", sorted(_ENTRY_REFUSED_KEYS)) def test_pool_refuses_section_level_key_on_entry(key)
def test_pool_refuses_transition_colors_on_core_entry()
def test_pool_refuses_unknown_key_on_core_entry_with_did_you_mean(): "color" → message contains "transition_color"
@pytest.mark.parametrize("bad", ["red", [255, 0], [255.0, 0, 0], [True, True, True], 255]) def test_pool_refuses_bad_entry_color(bad)
@pytest.mark.parametrize("bad", ["3.0", True, 0, -1]) def test_pool_refuses_bad_entry_duration(bad)
def test_pool_dedupes_identical_entries_below_two(): ["wipe_in", "wipe_in"] raises "1 distinct"
def test_pool_dedupes_string_and_type_only_table(): ["wipe_in", {"type": "wipe_in"}] raises "1 distinct"
def test_pool_keeps_same_type_entries_with_different_knobs(): two dissolves with different durations → 2 members
def test_parent_color_reaches_core_children_even_with_parent_colors(): each core child built with color=(1,2,3)
def test_entry_transition_color_overrides_inherited_colors()
def test_dotted_child_declaring_colors_gets_inherited_list(); def test_dotted_color_only_child_gets_parent_color_not_list()
def test_dotted_entry_own_transition_colors_on_color_only_child_raises()
def test_dotted_entry_extra_kwargs_reach_constructor()
def test_children_built_once_across_fifty_firings(): counting stub class; call end_firing 50× → constructor count == 1 per member
def test_cached_trans_obj_rebuilds_meta_on_new_cfg(): two distinct cfg objects → two wrapper instances; same cfg → same instance
```

- [ ] **Step 2: Run, expect failures** — `uv run pytest tests/test_factories_meta_transition.py -q`
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** — plus `tests/test_app.py tests/test_transitions.py`; Expected: PASS.
- [ ] **Step 5: Commit** — `feat(factories): build random/auto pools via clone-and-overlay child configs`

---

### Task 5: Campsite — widget-slot `transition_fn=None` must cut, not crash

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_run_swap`: the `elif self.transition_config is not None:` branch)
- Test: `tests/test_ticker_display.py` (new test class `TestRunSwapNoneTransitionFn`)

**Interfaces:** `_run_swap`'s transition branch becomes `elif self.transition_config is not None and self.transition_fn is not None:`; a `None` fn falls through to the cut path.

- [ ] **Step 1: Failing test** — build `Ticker(monitors=[w1, w2], frame=mock_frame, transition_config=TransitionConfig(type="dissolve"), transition_fn=None, ...)` the way the neighbouring slideshow tests do (reuse their restart_check / notif_queue setup) and run one pass of `run_slideshow`; assert it returns without raising and `run_transition` was not called (patch `led_ticker.transitions.run_transition`).
- [ ] **Step 2: Run, expect `AttributeError: 'NoneType' object has no attribute 'frame_at'`.**
- [ ] **Step 3: Implement the one-line guard.**
- [ ] **Step 4: Run `tests/test_ticker_display.py -q`, expect PASS.**
- [ ] **Step 5: Commit** — `fix(ticker): a widget-slot transition that failed to build cuts instead of crashing`

---

### Task 6: Validate — slot iterator, rule 66 skip, rules 73 and 74

**Files:**
- Modify: `src/led_ticker/validate.py` (new `_iter_transition_slots`; refactor `_check_transition_names` (39), `_check_plugin_transition_kwargs` (53), `_check_typeless_transition_table` (66), `_check_separator_color_transition` (57), `_check_scroll_separator_font` onto it; rule 66 skip; new `_check_meta_transition_pools` (73) and `_check_transition_color_shape` (74); wire both into `_validate_static_prebuild` right after the rule-39 block)
- Test: `tests/test_validate.py` (append `# Rule 73` and `# Rule 74` blocks and a `# _iter_transition_slots` block)

Split across the two PRs: **6a** (PR A) the `_iter_transition_slots` helper and the five moves, with a validate-output baseline captured first (`for f in config/*.example.toml; do uv run led-ticker validate $f; done > .superpowers/sdd/2026-11-18-random-transition/validate-baseline.txt 2>&1` on `origin/main`, diffed after the move — must be identical); **6b** (PR A) rule 74; **6c** (PR B) rule 66 skip and rule 73 (rule 73 reports ONE error per slot from the resolver — Ruling: parity with the factory beats per-check enumeration; recorded in the ledger).

**Interfaces:**
- `_iter_transition_slots(config: AppConfig, *, include_default: bool) -> Iterator[tuple[TransitionConfig, str]]` with the rule-39 gating from the spec. NOT moved: rule 50 (`_check_transition_fps`) and rule 60 (`_check_separator_size_positive`).
- Rule 66 `_check`: return early when `trans_cfg.type in ("random", "auto") and set(trans_cfg.extra) <= {"pool", "exclude"}`.
- `_check_meta_transition_pools(config) -> tuple[list[ValidationIssue], list[ValidationIssue]]` (errors, warnings), `include_default=True`, only for slots with `type in ("random","auto")`: ERRORs = one per slot from `factories._resolve_pool(trans_cfg)` then `factories._build_trans_obj(trans_cfg)` inside `try/except Exception as exc` (message `str(exc)`, fix "Fix the pool entry named in the message; see docs.ledticker.dev/transitions/special/#pools"); skipped when a rule-39 error already exists at that location. WARNINGs are computed ONLY when the resolver succeeded (a malformed pool yields exactly one ERROR and a normal return; `test_rule73_malformed_pool_one_error_no_raise` pins `pool = 5` and `pool = [5]`), walking the resolver's normalised entries: registered `exclude` name not in the pool; variant-picker token (`name.rsplit(".",1)[-1].rsplit("_",1)[-1] in {"random","alternating"}` on a dotted member); identical duplicate entries; dotted member without `duration` in a MIXED pool; parent `transition_colors` when any non-dotted member; decision-3 (a) and (b) shapes (a: `default.type` meta AND `between_sections_specified` AND `between_sections.type_specified` AND no section with `transition_specified and not transition.type_specified`; b: a typeless `between_sections` or section `transition` whose inherited type is meta and `default.extra` has a key the table does not write).
- `_check_transition_color_shape(config) -> tuple[list, list]`, `include_default=True`: ERROR when `trans_cfg.color is not None and rgb_shape_error(trans_cfg.color)` or `trans_cfg.colors is not None and rgb_list_shape_error(trans_cfg.colors)`; location `transitions.default` messages append " (also written by a section's transition_color on a section without its own transition)"; WARNING when `colors is not None` and type is non-dotted and not in `{"wipe_random", "wipe_alternating", "random", "auto"}`.

- [ ] **Step 1: Failing tests** — one `async def test_rule73_*` / `test_rule74_*` per spec bullet (positive + negative), using the `conf` fixture and `validate_config`; plus `test_iter_slots_rule39_includes_default`, `test_iter_slots_rule57_excludes_default`, `test_iter_slots_rule66_order_default_first`, `test_rule66_skips_typeless_pool_table_under_random_default`, `test_rule74_section_level_color_on_shared_default`, and `test_rule73_reports_failing_plugin_child_not_rule53` (register a dotted stub whose constructor requires a kwarg the entry omits).
- [ ] **Step 2: Run, expect failures** — `uv run pytest tests/test_validate.py -q -k "rule73 or rule74 or iter_slots or rule66"`
- [ ] **Step 3: Implement** — helper first (run the whole validate suite to prove the refactor is neutral), then 66 skip, then 73, then 74, then wiring.
- [ ] **Step 4: Run `uv run pytest tests/test_validate.py tests/test_backgrounds.py -q`, expect PASS.**
- [ ] **Step 5: Commit** per sub-task: 6a `refactor(validate): one _iter_transition_slots helper for the per-slot rules`; 6b `feat(validate): rule 74 — transition colour shape and misplaced transition_colors`; 6c `feat(validate): rule 73 — random/auto pool checks; rule 66 skips pool tables`.

---

### Task 7: Docs, CLAUDE.md, spec artefacts

**Files:**
- Modify: `docs/content-source/transitions/special.md` (two rows + "Pools" subsection), `docs/site/src/content/docs/transitions/index.mdx` ("Random and auto" block under per-section overrides), `CLAUDE.md` (Transition System "Meta" bullet; six sprite-family sites; file-map line for `meta.py`)
- Already copied into the worktree: the design, gate, design-review ledger, this plan.

- [ ] **Step 1: special.md** — rows: `random` ("Picks a different pool member each firing, never the same one twice in a row (per slot); default pool = every core transition except cut/scroll and the four *_random/*_alternating wrappers") and `auto` ("Cycles the pool in order"). "Pools" subsection: the spec's TOML example, per-entry `duration` (only), which slots are live, the per-instance scope, `between_sections = "auto"` for cross-section cycling, the plugin-duration caveat.
- [ ] **Step 2: index.mdx** — a short block after the precedence chains: bare `random`/`auto`, link to special `#pools`.
- [ ] **Step 3: CLAUDE.md** — add `meta.py` to the file map; add a **Meta** bullet to the Transition System list (pick-ahead via `end_firing`, `duration_override`, hard exclusions, "a widget-slot `transition_fn` of `None` must cut"); fix the six sprite-family sites to "inside the flair package (`led_ticker_flair/{nyancat,pokeball,pacman,sailor_moon}`)".
- [ ] **Step 4: Verify** — `uv run pytest tests/test_docs_config_options_drift.py tests/test_no_legacy_mode_names.py -q`; `grep -n "one package per family\|per-family" CLAUDE.md` returns nothing.
- [ ] **Step 5: Commit** — `docs(transitions): random/auto pools; CLAUDE.md meta bullet and flair sprite-family corrections` (include the spec/gate/ledger/plan files).

---

### Task 8: Whole-suite verification

- [ ] `uv run pytest -q > .superpowers/sdd/2026-11-18-random-transition/full-suite.txt 2>&1; tail -3 …` Expected: all pass, 2 skipped (baseline 4944 passed on origin/main before #547; the count grows).
- [ ] `uv run ruff check . && uv run ruff format --check .` Expected: clean.
- [ ] `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright` Expected: 0 errors.
- [ ] Mutation spot-checks AFTER committing: (a) change `is not None` to `or` in the duration hook → `test_duration_override_zero_is_honoured_not_or` fails; (b) move `end_firing` before the resumes → the ordering test fails; (c) drop the `transition_fn is not None` guard → Task 5 test fails; (d) drop the dedupe → `test_pool_dedupes_identical_entries_below_two` fails. Revert with `git checkout -- <file>` only after confirming the tree is committed.

Then: per-PR antagonist loop (cap 5, exit on LOW/DOCS), hardware check via the preview mirror on both signs (ASK FIRST), draft PR.

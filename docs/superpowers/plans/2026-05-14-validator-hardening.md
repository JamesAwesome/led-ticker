# Validator hardening implementation plan

> **Every subagent prompt MUST tell the subagent to run `git branch --show-current` first and abort if it returns `main`.** Expected: `worktree-validator-hardening`.

**Goal:** Promote rule 1 to error severity, add rules 33, 34, 35. Pure additive — no field renames, no engine changes.

**Spec:** `docs/superpowers/specs/2026-05-14-validator-hardening-design.md`.

**Working directory:** `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/validator-hardening/`

---

### Task 1: Add `_raw` field to `SectionConfig`

**Files:**
- Modify: `src/led_ticker/config.py` — `SectionConfig` dataclass + loader
- Test: `tests/test_config.py` — verify `_raw` round-trips

**Steps:**
1. Add `_raw: dict[str, Any] = field(default_factory=dict, repr=False)` to `SectionConfig`. Place at end of the dataclass (after `start_hold`-and-friends, before any `field(init=False)` entries if present).
2. In `load_config`'s section loader, pass `_raw=section_raw` to the `SectionConfig(...)` constructor.
3. Test:
   - Construct a SectionConfig from a known TOML, assert `_raw == section_raw`.
   - Construct without `_raw` arg (direct programmatic construction), assert `_raw == {}`.

Commit: `config: expose raw section TOML dict on SectionConfig`.

### Task 2: Promote rule 1 to error severity

**Files:**
- Modify: `src/led_ticker/validate.py` — find rule 1 in `_check_soft`, move it to `_check_static` with `severity="error"`.
- Update: `tests/test_validate.py` — the existing `test_rule1_content_height_overflow` test expects a warning. Flip the assertion to expect an error.
- Update: `docs/site/src/content/docs/pitfalls.mdx` — rule 1 entry moves from Warnings to Errors section.
- Update: `docs/site/src/content/docs/tools/validate.mdx` — rule 1 row severity flips.

Commit: `validate: promote rule 1 (content_height × scale ceiling) to error`.

### Task 3: Rule 33 — `mode = "gif"` legacy warning

**Files:**
- Modify: `src/led_ticker/validate.py` — `_check_soft`, after rule 21.
- Test: `tests/test_validate.py` — 2 new tests.
- Update: pitfalls.mdx, validate.mdx.

**Rule body:**

```python
for i, section in enumerate(config.sections):
    if section.mode == "gif":
        warnings.append(
            ValidationIssue(
                rule=33,
                location=f"section[{i}]",
                severity="warning",
                message=(
                    f"mode='gif' is legacy. Use mode='swap' with a "
                    f"gif widget for the same effect; the dedicated "
                    f"'gif' mode is preserved for back-compat but may "
                    f"be removed in a future release."
                ),
                fix=(
                    "Change mode to 'swap'. Each gif widget in the "
                    "section's `widget` list will play through its "
                    "gif_loops then transition."
                ),
            )
        )
```

Commit: `validate: rule 33 — mode = "gif" is legacy`.

### Task 4: Rule 34 — `scroll_step_ms` / `scroll_speed_ms` cross-scope bridge

**Files:**
- Modify: `src/led_ticker/validate.py`.
- Test: `tests/test_validate.py` — 4 new tests.
- Update: pitfalls.mdx, validate.mdx.

**Two halves:**

**Rule 34a (section level):** If `"scroll_speed_ms" in section._raw`, that field belongs at widget level. Error at `section[i].scroll_speed_ms`. Place in `_check_static`'s outer section loop.

**Rule 34b (widget level):** Inside the widget loop, if widget type is `gif` or `image` and `"scroll_step_ms" in widget_cfg`, that field belongs at section level. Error at `section[i].widget[j].scroll_step_ms`.

Other widget types receiving `scroll_step_ms` are caught by the existing unknown-field path when one ships; for now they're silently ignored. Don't widen this rule beyond gif/image — those are the only widgets that have a `scroll_speed_ms` to be confused with.

Commit: `validate: rule 34 — scroll_step_ms / scroll_speed_ms cross-scope bridge`.

### Task 5: Rule 35 — `default = ` inside section block

**Files:**
- Modify: `src/led_ticker/validate.py`.
- Test: `tests/test_validate.py` — 2 new tests.
- Update: pitfalls.mdx, validate.mdx.

**Rule body in `_check_soft`:**

```python
for i, section in enumerate(config.sections):
    if "default" in section._raw:
        warnings.append(
            ValidationIssue(
                rule=35,
                location=f"section[{i}].default",
                severity="warning",
                message=(
                    f"`default` is a [transitions]-block key. "
                    f"Inside a [[playlist.section]], the equivalent "
                    f"is `transition`. The key as written is silently "
                    f"ignored."
                ),
                fix="Rename `default = '...'` to `transition = '...'`.",
            )
        )
```

Commit: `validate: rule 35 — default = inside section is silently ignored`.

### Task 6: Tests + regression sweep

Run the full test suite. Then validate every TOML in `config/` and `docs/site/demos-*/`. Expected outcomes:

- Some configs will now trip rule 33 (`mode = "gif"`) — that's the intended behavior, the warning surfaces existing legacy usage.
- No config should trip rule 1 (now error), rule 34, or rule 35.

If a bundled example config trips an unexpected rule, fix the config (it was wrong) rather than soften the rule.

Commit (if needed): `examples: fix configs flagged by new validator rules`.

### Task 7: Final verification + PR

- `make test`
- `make lint`
- `uv run pyright src/`
- `make docs-lint`
- `git push -u origin worktree-validator-hardening`
- `gh pr create` with body covering all 4 rules and the rule 1 promotion

---

## Self-review

- Each rule has a clear trigger and a clear fix message.
- No field renames; all rules are additive.
- Rule 1 promotion is the most "breaking" thing — any config that hit rule 1 as a warning before now hits it as an error. The bundled examples don't hit it (verified pre-PR); third-party users who somehow had a config that worked despite tripping rule 1 will get a hard error and must fix.
- The `_raw` field on SectionConfig is the smallest plumbing change that unlocks rules 34/35.
- No changes to engine, no changes to widget classes.

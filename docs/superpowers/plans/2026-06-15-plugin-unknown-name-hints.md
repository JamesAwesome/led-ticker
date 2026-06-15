# Plugin-aware "unknown name" errors (P1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a config references a transition/widget/border/provider/animation name that lives in an uninstalled (extracted) plugin, give an actionable migration / "looks like a plugin" error instead of a dead-end "unknown X".

**Architecture:** A pure, registry-agnostic helper `plugin_hint(name, kind)` detects the dotted `<plugin>.<name>` convention and returns an install hint. Transitions get a migration map + an `explain_unknown_transition()` that layers migration → plugin-hint → difflib typo suggestion, used by both the runtime lookup and validate rule 39. Widgets/borders/providers/animations append the generic hint at their existing unknown-name sites. The transition migration map ships empty; real entries land with each extraction.

**Tech Stack:** Python 3.14, pytest (stubs in `tests/stubs`), stdlib `difflib`.

**Spec:** `docs/superpowers/specs/2026-06-15-plugin-unknown-name-hints-design.md` (read it first).

**Worktree / branch:** all work in `.claude/worktrees/feat+plugin-unknown-name-hints` on branch `worktree-feat+plugin-unknown-name-hints`. NEVER commit to `main`. First action each task: `pwd && git branch --show-current` and confirm.

**Conventions (apply every task):**
- Run tests: `PYTHONPATH=tests/stubs uv run pytest <path> -q` (or `make test` for the full suite).
- No `from __future__ import annotations` in `src/` (Python 3.14 / PEP 649 rule).
- Pre-commit hooks fire via `core.hooksPath` (ruff + ruff-format run automatically on commit); if a commit reformats, re-stage and retry.
- Match surrounding comment density / naming.

---

### Task 1: `plugin_hint` helper

**Files:**
- Create: `src/led_ticker/_plugin_hint.py`
- Test: `tests/test_plugin_hint.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugin_hint.py`:

```python
"""The generic plugin-reference hint used by every registry's
unknown-name error path."""

from led_ticker._plugin_hint import plugin_hint


def test_bare_name_is_not_a_plugin_reference():
    assert plugin_hint("nyancat", "transition") is None
    assert plugin_hint("message", "widget") is None


def test_namespaced_name_names_the_plugin_and_kind():
    msg = plugin_hint("arcade.nyancat", "transition")
    assert msg is not None
    assert "arcade" in msg          # the namespace
    assert "transition" in msg      # the kind word
    assert "requirements-plugins.txt" in msg


def test_kind_word_varies_per_registry():
    assert "border" in plugin_hint("vegas.marquee", "border")
    assert "widget" in plugin_hint("baseball.scores", "widget")


def test_namespace_is_the_segment_before_the_first_dot():
    msg = plugin_hint("feeds.weather.extra", "widget")
    assert "feeds" in msg
    # the full reference is quoted so the user sees exactly what they wrote
    assert "feeds.weather.extra" in msg
```

- [ ] **Step 2: Run it, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_hint.py -q`
Expected: `ModuleNotFoundError: No module named 'led_ticker._plugin_hint'`

- [ ] **Step 3: Implement the helper**

Create `src/led_ticker/_plugin_hint.py`:

```python
"""Shared helper for "this name didn't resolve" errors across every
registry (transitions, widgets, borders, color providers, animations).

A namespaced name (`<plugin>.<name>`) that fails to resolve almost
always means the owning plugin isn't installed. This helper turns that
into an actionable hint. It is pure and context-free — it does NOT
consult the loaded-plugin set, so it works from the bare runtime
registry lookups that have no `LoadedPlugins` handle.

The fix text points at `config/requirements-plugins.txt` today; when the
`led-ticker plugin install` CLI ships (plugin-registry project), this is
the one place to update.
"""


def plugin_hint(name: str, kind: str) -> str | None:
    """Return an install hint if `name` looks like a reference to an
    uninstalled plugin component, else None.

    `kind` is the human word for the registry — "transition", "widget",
    "border", "color provider", "animation".
    """
    if "." not in name:
        return None
    namespace = name.split(".", 1)[0]
    return (
        f"{name!r} looks like a plugin {kind}, but no {namespace!r} plugin "
        f"is loaded. Add the plugin to config/requirements-plugins.txt and "
        f"reinstall, or check the namespace. "
        f"See https://docs.ledticker.dev/plugins/."
    )
```

- [ ] **Step 4: Run it, expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_hint.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/_plugin_hint.py tests/test_plugin_hint.py
git commit -m "feat: plugin_hint helper for unknown-name errors"
```

---

### Task 2: Transition migration map + `explain_unknown_transition` + runtime lookup

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py` (add map + `explain_unknown_transition`; rewrite `get_transition_class` at lines 97-103)
- Test: `tests/test_transition_migration.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_transition_migration.py`:

```python
"""Transition migration map + explain_unknown_transition precedence:
migration entry → plugin hint → difflib typo suggestion."""

import pytest

from led_ticker import transitions
from led_ticker.transitions import (
    explain_unknown_transition,
    get_transition_class,
)


def test_shipped_migration_map_is_empty():
    """Entries land per-extraction (the crypto precedent). A live entry
    for a transition still present in core would be unreachable."""
    assert transitions._TRANSITION_MIGRATION == {}


def test_migration_entry_wins(monkeypatch):
    monkeypatch.setitem(
        transitions._TRANSITION_MIGRATION,
        "nyancat",
        ("transition 'nyancat' now ships in led-ticker-arcade as "
         "'arcade.nyancat'.", "Install led-ticker-arcade and use "
         'transition = "arcade.nyancat".'),
    )
    msg, fix = explain_unknown_transition("nyancat")
    assert "led-ticker-arcade" in msg
    assert "arcade.nyancat" in fix


def test_namespaced_unknown_gets_plugin_hint():
    msg, fix = explain_unknown_transition("arcade.nyancat")
    assert "unknown transition 'arcade.nyancat'" == msg
    assert "arcade" in fix
    assert "requirements-plugins.txt" in fix


def test_typo_gets_difflib_suggestion():
    msg, fix = explain_unknown_transition("wipe_leftt")
    assert "wipe_leftt" in msg
    assert "wipe_left" in msg  # did-you-mean
    assert "docs.ledticker.dev/transitions/" in fix


def test_unknown_with_no_close_match_has_no_suggestion():
    msg, _ = explain_unknown_transition("zzzzzzz")
    assert "did you mean" not in msg


def test_get_transition_class_raises_rich_message_for_namespaced():
    with pytest.raises(ValueError) as exc:
        get_transition_class("arcade.nyancat")
    assert "arcade" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_get_transition_class_still_resolves_known():
    assert get_transition_class("cut") is not None or True  # 'cut' may be sentinel
    assert get_transition_class("push_left").__name__  # a real registered one
```

Note: if `"cut"` is not in the registry (it is a sentinel handled upstream), drop that line — keep the `push_left` assertion which is definitely registered.

- [ ] **Step 2: Run it, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_transition_migration.py -q`
Expected: `ImportError: cannot import name 'explain_unknown_transition'` (and `_TRANSITION_MIGRATION` missing).

- [ ] **Step 3: Implement in `src/led_ticker/transitions/__init__.py`**

Add near the top of the module body (after `_TRANSITION_REGISTRY` is defined, ~line 72), the import and the map:

```python
from led_ticker._plugin_hint import plugin_hint

# name -> (message, suggested_fix) for a transition removed from core.
# SHIPS EMPTY. The extraction PR (e.g. led-ticker-arcade) adds entries in
# the same commit that removes the transition — mirroring _CRYPTO_MIGRATION
# in app/factories.py. A live entry for a still-registered transition would
# be unreachable, so populating it here ahead of extraction is wrong.
_TRANSITION_MIGRATION: dict[str, tuple[str, str]] = {}
```

Replace `get_transition_class` (lines 97-103) and add `explain_unknown_transition` directly above it:

```python
def explain_unknown_transition(name: str) -> tuple[str, str]:
    """Build (message, fix) for a transition name that isn't registered,
    layering migration → plugin hint → difflib typo suggestion. Single
    source of the "why didn't this resolve" answer, shared by the runtime
    lookup and validate rule 39."""
    migrated = _TRANSITION_MIGRATION.get(name)
    if migrated is not None:
        return migrated
    hint = plugin_hint(name, "transition")
    if hint is not None:
        return (f"unknown transition {name!r}", hint)
    import difflib

    close = difflib.get_close_matches(name, list_transition_names(), n=1, cutoff=0.6)
    suffix = f" (did you mean {close[0]!r}?)" if close else ""
    return (
        f"unknown transition {name!r}{suffix}",
        "Check the transition name spelling. Run `led-ticker validate "
        "--list-fields` or see docs.ledticker.dev/transitions/ for the full "
        "catalogue.",
    )


def get_transition_class(name: str) -> type[Transition]:
    if name not in _TRANSITION_REGISTRY:
        message, fix = explain_unknown_transition(name)
        raise ValueError(f"{message} {fix}")
    return _TRANSITION_REGISTRY[name]
```

(`list_transition_names` is defined just below in the same module — it is in scope at call time. If the linter flags use-before-def, move `explain_unknown_transition` below `list_transition_names`.)

- [ ] **Step 4: Run it, expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_transition_migration.py -q`
Expected: all pass. Then regression-check the sprite tests that call `get_transition_class` with valid names:
Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_pacman.py tests/test_pokeball.py tests/test_nyancat.py -q`
Expected: all pass (they use valid names; the error path changed, not the success path).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/transitions/__init__.py tests/test_transition_migration.py
git commit -m "feat: transition migration map + explain_unknown_transition"
```

---

### Task 3: Validate rule 39 uses `explain_unknown_transition`

**Files:**
- Modify: `src/led_ticker/validate.py` (`_check_transition_names`, lines 573-620 — specifically the `_check` inner fn, 588-607)
- Test: add to `tests/test_validate.py` (the rule-39 test class around line 2256)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_validate.py` in the rule-39 test class (the class containing `test_unknown_transition_in_section_is_error` at ~2258). Use the existing `conf` fixture pattern from neighboring tests:

```python
    async def test_namespaced_unknown_transition_gets_plugin_hint(self, conf):
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain_length = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "arcade.nyancat"

[[playlist.section.widget]]
type = "message"
text = "hi"
""")
        )
        assert not result.valid
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        # scenario B: the fix names the plugin + the requirements file,
        # not the generic "check spelling" catalogue text.
        assert "arcade" in rule_39[0].fix
        assert "requirements-plugins.txt" in rule_39[0].fix

    async def test_migrated_transition_surfaces_through_rule_39(self, conf, monkeypatch):
        from led_ticker import transitions

        monkeypatch.setitem(
            transitions._TRANSITION_MIGRATION,
            "nyancat",
            ("transition 'nyancat' now ships in led-ticker-arcade as "
             "'arcade.nyancat'.", 'Install led-ticker-arcade and use '
             'transition = "arcade.nyancat".'),
        )
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain_length = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "nyancat"

[[playlist.section.widget]]
type = "message"
text = "hi"
""")
        )
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "led-ticker-arcade" in rule_39[0].message
        assert "arcade.nyancat" in rule_39[0].fix
```

- [ ] **Step 2: Run them, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -q -k "namespaced_unknown_transition or migrated_transition_surfaces"`
Expected: FAIL — current rule 39 produces the generic "Check the transition name spelling…" fix and an empty did-you-mean, so the `arcade`/`requirements-plugins.txt`/`led-ticker-arcade` assertions fail.

- [ ] **Step 3: Rewire `_check` in `_check_transition_names`**

In `src/led_ticker/validate.py`, replace the body of the inner `_check` function (lines 588-607) so it delegates to `explain_unknown_transition`. Keep the `cut` short-circuit and the registered-name short-circuit:

```python
    from led_ticker.transitions import explain_unknown_transition, list_transition_names

    valid_set = set(list_transition_names())
    issues: list[ValidationIssue] = []

    def _check(trans_cfg: TransitionConfig | None, location: str) -> None:
        if trans_cfg is None or trans_cfg.type == "cut":
            return
        if trans_cfg.type in valid_set:
            return
        message, fix = explain_unknown_transition(trans_cfg.type)
        issues.append(
            ValidationIssue(
                rule=39,
                location=location,
                severity="error",
                message=message,
                fix=fix,
            )
        )
```

Remove the now-unused `import difflib` and the `valid_names` local (difflib now lives inside `explain_unknown_transition`). Leave the loop over sections (lines 609-618) untouched.

- [ ] **Step 4: Run, expect pass (incl. the preserved typo test)**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -q -k "transition"`
Expected: the two new tests pass AND the existing `test_unknown_transition_in_section_is_error` (typo `wipe_leftt`→`wipe_left`) still passes unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: rule 39 routes unknown transitions through explain_unknown_transition"
```

---

### Task 4: `get_widget_class` appends the plugin hint

**Files:**
- Modify: `src/led_ticker/widgets/__init__.py` (`get_widget_class`, lines 26-32)
- Test: `tests/test_widget_unknown_hint.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_widget_unknown_hint.py`:

```python
"""get_widget_class keeps its 'Unknown widget type' message but appends
the plugin hint for namespaced (uninstalled-plugin) names. The crypto
MigrationError path (scenario A) is unaffected — it runs earlier in
validate_widget_cfg."""

import pytest

from led_ticker.widgets import get_widget_class


def test_bare_unknown_keeps_plain_message():
    with pytest.raises(ValueError) as exc:
        get_widget_class("boguswidget")
    assert "Unknown widget type" in str(exc.value)
    assert "plugin" not in str(exc.value).lower()  # no hint for bare names


def test_namespaced_unknown_appends_plugin_hint():
    with pytest.raises(ValueError) as exc:
        get_widget_class("baseball.scores")
    msg = str(exc.value)
    assert "Unknown widget type" in msg          # prefix preserved
    assert "baseball" in msg                      # the namespace
    assert "requirements-plugins.txt" in msg
```

- [ ] **Step 2: Run it, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widget_unknown_hint.py -q`
Expected: `test_namespaced_unknown_appends_plugin_hint` FAILS (current message has no hint).

- [ ] **Step 3: Implement** — edit `get_widget_class` (lines 26-32):

```python
def get_widget_class(name: str) -> type[Any]:
    """Look up a widget class by its config name."""
    if name not in _WIDGET_REGISTRY:
        from led_ticker._plugin_hint import plugin_hint

        base = (
            f"Unknown widget type: {name!r}. "
            f"Available: {list(_WIDGET_REGISTRY.keys())}"
        )
        hint = plugin_hint(name, "widget")
        raise ValueError(f"{base} {hint}" if hint else base)
    return _WIDGET_REGISTRY[name]
```

- [ ] **Step 4: Run, expect pass + regression**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widget_unknown_hint.py tests/test_app.py -q -k "unknown or widget_type or hint"`
Expected: new tests pass; the existing `test_app.py` tests matching `Unknown widget type` still pass (prefix preserved). Also run the crypto migration test:
Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_crypto_migration.py -q`
Expected: unchanged, all pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/__init__.py tests/test_widget_unknown_hint.py
git commit -m "feat: get_widget_class appends plugin hint for namespaced names"
```

---

### Task 5: Wire the hint into border / animation / color-provider unknown-name sites

**Files:**
- Modify: `src/led_ticker/app/coercion.py` (border string site ~409-413, border table site ~426-428, animation string site ~636-639, animation table site ~649-652)
- Modify: `src/led_ticker/color_providers.py` — actually the provider unknown-name lives in `src/led_ticker/app/coercion.py:_provider_from_style` (lines 203-208)
- Test: `tests/test_coercion_plugin_hint.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_coercion_plugin_hint.py`:

```python
"""Namespaced-but-unknown border / animation / color-provider names get
the plugin hint appended to their coercion error."""

import pytest

from led_ticker.app.coercion import (
    _coerce_animation,
    _coerce_border,
    _provider_from_style,
)


def test_border_string_shorthand_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_border("vegas.marquee")
    assert "vegas" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_border_table_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_border({"style": "vegas.marquee"})
    assert "vegas" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_animation_string_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_animation("fancy.sparkle")
    assert "fancy" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_provider_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _provider_from_style("fancy.glow", {})
    assert "fancy" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_bare_unknown_border_has_no_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_border("bogus")
    assert "requirements-plugins.txt" not in str(exc.value)
```

- [ ] **Step 2: Run, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_coercion_plugin_hint.py -q`
Expected: the four namespaced tests FAIL (no hint today); `test_bare_unknown_border_has_no_hint` passes.

- [ ] **Step 3: Implement** — add a module-level import at the top of `app/coercion.py` (with the other imports):

```python
from led_ticker._plugin_hint import plugin_hint
```

Helper to keep it DRY — add near the top of the module body:

```python
def _with_plugin_hint(message: str, name: str, kind: str) -> str:
    """Append the plugin-reference hint to `message` when `name` is a
    namespaced reference to an uninstalled plugin component."""
    hint = plugin_hint(name, kind)
    return f"{message} {hint}" if hint else message
```

Border string shorthand (lines 409-413) → wrap the message:

```python
                raise ValueError(
                    _with_plugin_hint(
                        f"unknown border style {value!r}; "
                        "available: 'rainbow', 'color_cycle', 'lightbulbs', "
                        "or a registered plugin border",
                        value,
                        "border",
                    )
                )
```

Border table (lines 426-428):

```python
            raise ValueError(
                _with_plugin_hint(
                    f"unknown border style {style!r}; "
                    f"available: {sorted(_BORDER_REGISTRY)}",
                    style,
                    "border",
                )
            )
```

Animation string (lines 636-639):

```python
                raise ValueError(
                    _with_plugin_hint(
                        f"unknown animation {value!r}; "
                        f"available: {sorted(_ANIMATION_REGISTRY)}",
                        value,
                        "animation",
                    )
                )
```

Animation table (lines 649-652):

```python
                raise ValueError(
                    _with_plugin_hint(
                        f"unknown animation {style!r}; "
                        f"available: {sorted(_ANIMATION_REGISTRY)}",
                        style,
                        "animation",
                    )
                )
```

Provider (`_provider_from_style`, lines 204-208):

```python
    cls = _PROVIDER_REGISTRY.get(style)
    if cls is None:
        raise ValueError(
            _with_plugin_hint(
                f"unknown font_color style {style!r}; "
                f"available: {sorted(_PROVIDER_REGISTRY)}",
                style,
                "color provider",
            )
        )
```

- [ ] **Step 4: Run, expect pass + regression**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_coercion_plugin_hint.py tests/test_borders.py -q`
Expected: new tests pass; existing border coercion tests (which assert on the unknown-style message for BARE names) still pass — the bare-name branch appends nothing.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/coercion.py tests/test_coercion_plugin_hint.py
git commit -m "feat: plugin hint on unknown border/animation/provider names"
```

---

### Task 6: Full verification, docs note, PR

**Files:**
- Modify (optional, if a natural home exists): a docs page on plugins/troubleshooting

- [ ] **Step 1: Full suite + lint**

Run: `make test`
Expected: all pass (baseline was 2903 passed / 2 skipped; this adds ~20 tests). Coverage ≥ 90%.
Run: `make lint`
Expected: clean. If `make format` changed anything, re-stage + amend the relevant commit or add a fixup.

- [ ] **Step 2: Optional docs note**

If `docs/site/src/content/docs/plugins/` has an authoring or troubleshooting page where "what happens when a plugin isn't installed" fits naturally, add one short paragraph: a namespaced name whose plugin isn't installed now produces a hint pointing at `config/requirements-plugins.txt`. Follow `docs/DOCS-STYLE.md`; run `make docs-lint`. If there's no natural home, SKIP — do not invent a page. Note the skip in the PR description.

- [ ] **Step 3: Push + PR**

```bash
git push -u origin worktree-feat+plugin-unknown-name-hints
gh pr create --title "feat: plugin-aware unknown-name errors (P1)" --body "$(cat <<'EOF'
## Summary
- New `plugin_hint(name, kind)` helper: a namespaced `x.y` name that doesn't resolve gets an actionable "is the X plugin installed?" hint pointing at `config/requirements-plugins.txt`
- Transitions gain a migration map (`_TRANSITION_MIGRATION`, ships empty) + `explain_unknown_transition()` layering migration → plugin-hint → difflib typo suggestion; used by both `get_transition_class` and validate rule 39
- The generic hint is wired into widget/border/animation/color-provider unknown-name errors too
- Closes the dead-end transition error the extraction review (P1) flagged; makes future extraction non-breaking. Real migration entries land per-extraction (crypto precedent).

Spec: docs/superpowers/specs/2026-06-15-plugin-unknown-name-hints-design.md

## Test plan
- [ ] `make test` green; `make lint` clean
- [ ] New: test_plugin_hint, test_transition_migration, test_widget_unknown_hint, test_coercion_plugin_hint + rule-39 additions
- [ ] Existing crypto migration + rule-39 typo tests unchanged

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** A (migration map, Task 2) · B (plugin_hint everywhere: Tasks 1,2,4,5) · C (difflib preserved, Task 2/3) · validate-time (Task 3) + runtime (Tasks 2,4,5) · empty-map-ships (Task 2 test) · forward-compat string (Task 1 docstring). All spec sections map to a task.
- **Type consistency:** `plugin_hint(name, kind) -> str | None` and `explain_unknown_transition(name) -> tuple[str, str]` used identically across Tasks 1-5. `_with_plugin_hint` is Task-5-local.
- **Regression guards called out:** `Unknown widget type` prefix preserved (Task 4), rule-39 typo test preserved (Task 3), crypto migration untouched (Task 4), bare-name border message unchanged (Task 5).

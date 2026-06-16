# Calendar Extraction — Phase 1: Plugin Validation Warnings Channel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, errors-vs-warnings-aware validation channel to the led-ticker plugin API so plugins can emit advisory (warning-severity) preflight checks — the prerequisite for re-homing calendar's three advisory `validate.py` rules into the led-ticker-calendar plugin.

**Architecture:** A new public `ValidationContext` dataclass (geometry a per-widget check needs) is exported from `led_ticker.plugin`. Widget classes may define an optional `validate_config_warnings(cls, cfg, ctx) -> list[str]` classmethod (sibling to the existing errors-only `validate_config`). A new factories runner invokes it with error-isolation; a new `validate.py` Phase-2 check builds a per-section `ValidationContext`, runs the runner for every widget, and emits each returned string as a `severity="warning"` `ValidationIssue` (rule 55). Purely additive: no existing plugin, behavior, or error path changes.

**Tech Stack:** Python 3.14, attrs/dataclasses, pytest (`PYTHONPATH=tests/stubs`), `ast`-guarded docs drift test.

---

## Scope

This plan is Phase 1 of the calendar extraction (see
`docs/superpowers/specs/2026-06-16-calendar-extraction-design.md`). It ships and
merges independently of the calendar move; it touches **only core** and adds no
calendar-specific logic. Phases 2–4 (plugin repo, core removal, docs-site) are
separate plans authored after this lands.

**Out of scope for Phase 1:** runtime-build-path WARNING logging of these
warnings. The channel surfaces through `led-ticker validate` (the documented
preflight tool); wiring the same warnings into the live app-startup build path
needs section geometry threaded into `_build_widget` and is deferred to a small
follow-on so this plan stays bounded.

## File Structure

- Modify `src/led_ticker/plugin.py` — add `ValidationContext` dataclass + add
  `"ValidationContext"` to `__all__`; bump `API_VERSION` to `(1, 1)`.
- Modify `src/led_ticker/app/factories.py` — add `_run_validate_config_warnings`
  + `collect_validation_warnings` helpers.
- Modify `src/led_ticker/validate.py` — add `_check_plugin_validation_warnings`
  Phase-2 check; wire it into the warnings aggregation.
- Create `tests/test_plugin_validation_warnings.py` — unit + integration tests.
- Modify `docs/site/src/content/docs/plugins/api-reference.mdx` — add
  `ValidationContext` to the exported-names table + document the
  `validate_config_warnings` convention hook.
- Modify `docs/plugin-system.md` — authoring note (errors vs warnings).

---

### Task 1: Public `ValidationContext` dataclass + export

**Files:**
- Modify: `src/led_ticker/plugin.py` (dataclass near `StartupContext` ~line 156; `__all__` ~line 88–134; `API_VERSION` line 147)
- Test: `tests/test_plugin_validation_warnings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugin_validation_warnings.py`:

```python
"""Plugin validation warnings channel (calendar extraction Phase 1)."""

from pathlib import Path

import led_ticker.plugin as plugin
from led_ticker.plugin import ValidationContext


def test_validation_context_is_public_and_frozen():
    assert "ValidationContext" in plugin.__all__
    ctx = ValidationContext(
        scale=4,
        content_height=16,
        panel_width=256,
        panel_height=64,
        config_dir=Path("/tmp/cfg"),
    )
    assert ctx.scale == 4
    assert ctx.content_height == 16
    assert ctx.panel_width == 256
    assert ctx.panel_height == 64
    assert ctx.config_dir == Path("/tmp/cfg")
    # frozen
    import dataclasses

    try:
        ctx.scale = 1  # type: ignore[misc]
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised


def test_api_version_bumped_to_1_1():
    assert plugin.API_VERSION == (1, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_validation_warnings.py -q`
Expected: FAIL — `ImportError: cannot import name 'ValidationContext'`.

- [ ] **Step 3: Add the dataclass + export + version bump**

In `src/led_ticker/plugin.py`, add `"ValidationContext"` to the `__all__` list
(keep alphabetical-ish placement near the other public types, e.g. after
`"TwoRowMessage"`/before `"Updatable"`), change `API_VERSION` to `(1, 1)`, and
add the dataclass immediately after the `StartupContext` definition:

```python
@dataclass(frozen=True)
class ValidationContext:
    """Geometry passed to a widget's optional ``validate_config_warnings``.

    The per-widget ``validate_config`` hook only sees the widget's own ``cfg``;
    warning-severity render-prediction checks (e.g. "this text may be cut off
    at this scale") also need the section/display geometry, supplied here.

    ``config_dir`` is the directory of the loaded ``config.toml`` so a check can
    resolve a relative ``file://``/path field (e.g. a calendar ``ics_url``).
    """

    scale: int
    content_height: int
    panel_width: int
    panel_height: int
    config_dir: Path
```

(`dataclass` and `Path` are already imported in `plugin.py` — confirm at the top
of the file; `StartupContext` uses both.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_validation_warnings.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/plugin.py tests/test_plugin_validation_warnings.py
git commit -m "feat(plugins): public ValidationContext + API_VERSION 1.1"
```

---

### Task 2: `validate_config_warnings` runner in factories

**Files:**
- Modify: `src/led_ticker/app/factories.py` (after `_run_validate_config`, ~line 565)
- Test: `tests/test_plugin_validation_warnings.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugin_validation_warnings.py`:

```python
from pathlib import Path as _P

from led_ticker.app.factories import (
    _run_validate_config_warnings,
    collect_validation_warnings,
)
from led_ticker.plugin import ValidationContext as _VC

_CTX = _VC(scale=1, content_height=16, panel_width=160, panel_height=16, config_dir=_P("."))


class _WidgetWithWarnings:
    @classmethod
    def validate_config_warnings(cls, cfg, ctx):
        out = []
        if ctx.scale > 2:
            out.append("scale is large")
        if cfg.get("noisy"):
            out.append("noisy is set")
        return out


class _WidgetNoHook:
    pass


class _WidgetBadHook:
    @classmethod
    def validate_config_warnings(cls, cfg, ctx):
        raise RuntimeError("boom")


def test_runner_returns_hook_warnings():
    assert _run_validate_config_warnings(_WidgetWithWarnings, {"noisy": True}, _CTX) == [
        "noisy is set"
    ]


def test_runner_absent_hook_returns_empty():
    assert _run_validate_config_warnings(_WidgetNoHook, {}, _CTX) == []


def test_runner_isolates_raising_hook(caplog):
    # A warnings hook that raises must NOT crash validation.
    assert _run_validate_config_warnings(_WidgetBadHook, {}, _CTX) == []


def test_collect_unknown_type_returns_empty():
    # No 'type' / unknown type => no warnings, no crash.
    assert collect_validation_warnings({}, _CTX) == []
    assert collect_validation_warnings({"type": "does-not-exist"}, _CTX) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_validation_warnings.py -q`
Expected: FAIL — `ImportError: cannot import name '_run_validate_config_warnings'`.

- [ ] **Step 3: Implement the runner + collector**

In `src/led_ticker/app/factories.py`, immediately after `_run_validate_config`,
add:

```python
def _run_validate_config_warnings(
    cls: type, cfg: dict[str, Any], ctx: Any
) -> list[str]:
    """Run a widget class's optional ``validate_config_warnings(cls, cfg, ctx)``.

    Sibling to ``_run_validate_config`` but ADVISORY: every returned string is a
    warning, never an error, and a hook that raises is isolated (logged, then
    treated as "no warnings") so a buggy plugin check can never fail validation
    or freeze startup. The hook gets a COPY of the config.
    """
    hook = getattr(cls, "validate_config_warnings", None)
    if hook is None:
        return []
    try:
        messages = hook(dict(cfg), ctx)
    except Exception as e:  # isolation: advisory checks never crash validation
        logging.warning("validate_config_warnings raised (ignored): %s", e)
        return []
    return list(messages) if messages else []


def collect_validation_warnings(widget_cfg: dict[str, Any], ctx: Any) -> list[str]:
    """Resolve a widget dict's class and collect its advisory warnings.

    Returns ``[]`` for a missing/unknown ``type`` (those are reported by other
    rules / the migration path); never raises.
    """
    wtype = widget_cfg.get("type")
    if not isinstance(wtype, str) or not wtype:
        return []
    try:
        cls = get_widget_class(wtype)
    except Exception:
        return []
    return _run_validate_config_warnings(cls, widget_cfg, ctx)
```

`logging`, `Any`, and `get_widget_class` are already imported/used in
`factories.py` (see `_run_validate_config` and line ~665 `get_widget_class`).

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_validation_warnings.py -q`
Expected: PASS (all tests so far).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_plugin_validation_warnings.py
git commit -m "feat(plugins): validate_config_warnings runner + collector"
```

---

### Task 3: Surface warnings as a Phase-2 `validate.py` check

**Files:**
- Modify: `src/led_ticker/validate.py` (new `_check_plugin_validation_warnings` near the other `_check_*` funcs; wire into the Phase-2 block ~line 1948)
- Test: `tests/test_plugin_validation_warnings.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugin_validation_warnings.py`:

```python
from led_ticker.validate import _check_plugin_validation_warnings
from led_ticker.widgets import get_widget_class, register


def test_check_emits_warning_issue(monkeypatch):
    # Register a throwaway widget type that emits a warning, then build a
    # minimal AppConfig-like object exposing .display and .sections.
    @register("phase1_warn_probe")
    class _Probe:
        @classmethod
        def validate_config_warnings(cls, cfg, ctx):
            return [f"probe warned at scale {ctx.scale}"]

    from types import SimpleNamespace

    display = SimpleNamespace(
        cols=160, rows=16, chain_length=1, parallel=1, default_scale=1
    )
    section = SimpleNamespace(
        scale=1, content_height=16, widgets=[{"type": "phase1_warn_probe"}]
    )
    config = SimpleNamespace(display=display, sections=[section])

    issues = _check_plugin_validation_warnings(config, Path("."))
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].rule == 55
    assert issues[0].location == "section[0].widget[0]"
    assert "probe warned at scale 1" in issues[0].message
```

> Note: `_panel_w_real`/`_panel_h_real` read `display.cols/rows/chain_length/
> parallel` etc. Confirm the `SimpleNamespace` exposes whatever
> `DisplayConfig` fields those helpers read (inspect `validate.py:838-855`);
> add the missing attributes to the `display` namespace if the test errors on
> an attribute.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_validation_warnings.py::test_check_emits_warning_issue -q`
Expected: FAIL — `ImportError: cannot import name '_check_plugin_validation_warnings'`.

- [ ] **Step 3: Implement the check**

In `src/led_ticker/validate.py`, add (near the other `_check_*` functions, e.g.
after `_check_calendar_ics_paths`):

```python
# Rule 55: advisory warnings contributed by a widget's
# validate_config_warnings(cls, cfg, ctx) hook (plugins + core widgets alike).
def _check_plugin_validation_warnings(
    config: AppConfig, config_dir: Path
) -> list[ValidationIssue]:
    """Collect each widget's advisory ``validate_config_warnings`` output.

    Builds a per-section ``ValidationContext`` (geometry + config_dir) and emits
    every returned string as a warning. The hook is error-isolated inside
    ``collect_validation_warnings`` so a buggy check never breaks validation.
    """
    from led_ticker.app.factories import collect_validation_warnings
    from led_ticker.plugin import ValidationContext

    issues: list[ValidationIssue] = []
    panel_w = _panel_w_real(config.display)
    panel_h = _panel_h_real(config.display)
    for i, section in enumerate(config.sections):
        ctx = ValidationContext(
            scale=section.scale,
            content_height=section.content_height,
            panel_width=panel_w,
            panel_height=panel_h,
            config_dir=config_dir,
        )
        for j, widget_cfg in enumerate(section.widgets):
            for msg in collect_validation_warnings(dict(widget_cfg), ctx):
                issues.append(
                    ValidationIssue(
                        rule=55,
                        location=f"section[{i}].widget[{j}]",
                        severity="warning",
                        message=msg,
                        fix="Advisory check from the widget/plugin. "
                        "See the plugin's documentation for how to resolve it.",
                    )
                )
    return issues
```

- [ ] **Step 4: Wire it into the Phase-2 warnings block**

In `src/led_ticker/validate.py`, in the `if not errors:` Phase-2 block (the one
that calls `_check_soft` / `_check_held_top_text_overflow` /
`_check_transition_fps` / `_check_calendar_ics_paths`, ~line 1948), add:

```python
        warnings.extend(_check_plugin_validation_warnings(config, path.parent))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_validation_warnings.py -q`
Expected: PASS.

Also run the existing validate suite to confirm no regression:
Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -q`
Expected: PASS (unchanged — additive check only fires when a widget defines the hook; none do yet in core).

- [ ] **Step 6: Clean up the test registry side effect**

The `@register("phase1_warn_probe")` in the test registers into the global
registry. Add an autouse cleanup fixture at the top of
`tests/test_plugin_validation_warnings.py` so the probe type doesn't leak:

```python
import pytest

from led_ticker import widgets as _widgets_mod


@pytest.fixture(autouse=True)
def _cleanup_probe_registration():
    yield
    # Defensive: drop any probe types registered by tests in this module.
    reg = getattr(_widgets_mod, "_REGISTRY", None)
    if isinstance(reg, dict):
        for name in list(reg):
            if name.startswith("phase1_"):
                reg.pop(name, None)
```

> Confirm the registry attribute name by grepping
> `src/led_ticker/widgets/__init__.py` for the dict that `register` writes to
> (likely `_REGISTRY` / `_WIDGETS`); adjust the fixture to match. If the
> registry is keyed differently, register the probe inside the test with the
> real key shape.

- [ ] **Step 7: Run the full file again + commit**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_validation_warnings.py -q`
Expected: PASS.

```bash
git add src/led_ticker/validate.py tests/test_plugin_validation_warnings.py
git commit -m "feat(plugins): validate-time warnings channel (rule 55)"
```

---

### Task 4: Docs — api-reference + authoring note + drift test green

**Files:**
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx`
- Modify: `docs/plugin-system.md`
- Test: `tests/test_docs_plugin_api_drift.py` (existing — must stay green)

- [ ] **Step 1: Run the drift test to see it fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_plugin_api_drift.py -q`
Expected: FAIL — `test_exported_names_match` reports `ValidationContext` missing
from the API reference page (it was added to `__all__` in Task 1).

- [ ] **Step 2: Add `ValidationContext` to the exported-names table**

In `docs/site/src/content/docs/plugins/api-reference.mdx`, inside the marked
exported-names region (the table the drift test parses), add a row for
`ValidationContext` matching the existing row format, e.g.:

```md
| `ValidationContext` | Geometry passed to `validate_config_warnings` (scale, content_height, panel_width, panel_height, config_dir). |
```

(Match the exact column layout of the surrounding rows — inspect neighbors like
`StartupContext` for the precise pipe/wording style the parser expects.)

- [ ] **Step 3: Document the `validate_config_warnings` convention hook**

In the same page, in the by-convention validation section (where
`validate_config(cls, cfg) -> list[str]` is documented), add a short subsection:

```md
### Advisory warnings: `validate_config_warnings`

A widget class may also define an optional classmethod:

```python
@classmethod
def validate_config_warnings(cls, cfg: dict, ctx: ValidationContext) -> list[str]:
    ...
```

Each returned string is surfaced by `led-ticker validate` as a **warning**
(not an error) — use it for advisory render-prediction checks (e.g. "this text
may be cut off at this scale"). Unlike `validate_config`, it receives a
`ValidationContext` carrying section/display geometry and the config directory.
A hook that raises is isolated and ignored. Requires core API ≥ 1.1.
```

- [ ] **Step 4: Add the authoring note**

In `docs/plugin-system.md`, add a short note under the validation discussion
distinguishing the two hooks: `validate_config` → errors (fail load),
`validate_config_warnings` → advisory warnings (surfaced by `led-ticker
validate`, never fail load), with the `ValidationContext` field list.

- [ ] **Step 5: Run the drift test + full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_plugin_api_drift.py -q`
Expected: PASS.

Run: `PYTHONPATH=tests/stubs uv run pytest -q`
Expected: PASS (full core suite green).

Run: `uv run --extra dev ruff check src/ tests/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/content/docs/plugins/api-reference.mdx docs/plugin-system.md
git commit -m "docs(plugins): document validate_config_warnings + ValidationContext"
```

---

## Self-Review

**Spec coverage (Phase-1 portion of the design):**
- "validate_config stays errors-only and untouched" → no edits to
  `_run_validate_config` / `validate_config`. ✓
- "optional sibling classmethod `validate_config_warnings(cls, cfg, ctx)`" →
  Task 2 runner + Task 4 docs. ✓
- "public ValidationContext dataclass exported from led_ticker.plugin with
  scale/content_height/panel_width/panel_height/config_dir" → Task 1. ✓
- "validate.py builds ctx per section, emits ValidationIssue(severity=warning)"
  → Task 3. ✓
- "API_VERSION bumps" → Task 1 (`(1,0)` → `(1,1)`, backward-compatible minor:
  loader gates on major `API_VERSION[0]` only). ✓
- "drift-guarded api-reference + authoring note updated" → Task 4. ✓
- Runtime WARNING logging → explicitly deferred in Scope (documented deviation,
  not silent). ✓

**Placeholder scan:** Three `>` callouts ask the engineer to confirm exact
attribute/registry names against the live source (DisplayConfig fields the panel
helpers read; the widgets registry dict name; the mdx table column style). These
are verification instructions with a concrete fallback, not unfinished work.

**Type consistency:** `ValidationContext` field names (`scale`,
`content_height`, `panel_width`, `panel_height`, `config_dir`) are identical in
Task 1 (definition), Task 2 (`_CTX` test fixture), and Task 3 (`ctx = `
construction). Hook name `validate_config_warnings` and helpers
`_run_validate_config_warnings` / `collect_validation_warnings` match across
Tasks 2–3. Rule id `55` matches in Task 3 implementation and its test.

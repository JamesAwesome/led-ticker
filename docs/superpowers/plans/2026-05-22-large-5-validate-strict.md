# Large #5: validate --strict Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Rule 39 (transition name validation, always-on) and `--strict` mode to `led-ticker validate`, which promotes all warnings to errors and adds asset-path existence checks (Rule 40).

**Architecture:** Three independent additions in dependency order: (1) a `list_transition_names()` public API on the transitions registry; (2) Rule 39 `_check_transition_names()` wired into the normal-mode sync check phase; (3) `--strict` flag in CLI + `validate_config(strict=False)` signature change + Rule 40 `_check_asset_paths()` + warning-promotion logic. Each task leaves tests green.

**Tech Stack:** Python 3.12, pytest (`asyncio_mode = "auto"`), argparse, uv. No new dependencies.

---

## Background & Context

The engine-review identified that a typo in `transition = "wipe_leftt"` passes `led-ticker validate` cleanly but crashes at startup with a `ValueError` from `get_transition_class`. Similarly, `path = "assets/missing.gif"` passes validate but crashes at runtime with `FileNotFoundError`. These are the two main silent failures addressed by this plan.

`--strict` mode inverts the silent-failure default for all warnings: rule 24 (unknown font file), rule 23 (top_text overflow), rule 30 (hold_time + bottom_text_loops), rule 33 (mode='gif' deprecated), etc. In strict mode every warning becomes an error and exits 1.

## What's Already Done (do NOT re-implement)

- `MigrationError(message, suggested_fix)` — typed and in `validate.py`
- `_build_widget` unknown-kwarg allowlist (rule 38) with `difflib.get_close_matches`
- `--list-fields TYPE` CLI flag
- `list_transition_names()` does NOT yet exist — add it in Task 1

## File Map

| Task | Action | Path | Responsibility |
|------|--------|------|----------------|
| Task 1 | Modify | `src/led_ticker/transitions/__init__.py` | Add `list_transition_names() -> list[str]` |
| Task 1 | Create | `tests/test_transitions_registry.py` | Smoke test for new public API |
| Task 2 | Modify | `src/led_ticker/validate.py` | Add `_check_transition_names()`, wire into `validate_config` |
| Task 2 | Modify | `tests/test_validate.py` | Rule 39 tests |
| Task 3 | Modify | `src/led_ticker/validate.py` | Add `_check_asset_paths()`, update `validate_config(strict=)`, warning-promotion |
| Task 3 | Modify | `tests/test_validate.py` | Rule 40 tests + strict-promotion tests |
| Task 4 | Modify | `src/led_ticker/app/cli.py` | Add `--strict` flag, pass to `validate_config` |
| Task 4 | Modify | `tests/test_validate.py` | CLI `--strict` integration tests |

---

## Task 1: `list_transition_names()` public API

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py` (after `get_transition_class`, around line 112)
- Create: `tests/test_transitions_registry.py`

The `_TRANSITION_REGISTRY` dict is already populated at module load by the pkgutil auto-discovery at the bottom of `transitions/__init__.py`. Adding a public accessor avoids coupling validate.py to the private `_TRANSITION_REGISTRY` name.

- [ ] **Step 1: Write the failing test**

Create `tests/test_transitions_registry.py`:

```python
"""Smoke tests for the transitions public registry API."""
from led_ticker.transitions import list_transition_names


def test_list_transition_names_returns_sorted_list():
    names = list_transition_names()
    assert isinstance(names, list)
    assert names == sorted(names)


def test_list_transition_names_includes_core_transitions():
    names = list_transition_names()
    for expected in ("cut", "wipe_left", "push_right", "dissolve", "nyancat"):
        assert expected in names, f"{expected!r} not in registry"


def test_list_transition_names_does_not_include_private():
    names = list_transition_names()
    for name in names:
        assert not name.startswith("_"), f"private name {name!r} leaked into registry"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_transitions_registry.py -v
```

Expected: `ImportError: cannot import name 'list_transition_names'`

- [ ] **Step 3: Add `list_transition_names` to `src/led_ticker/transitions/__init__.py`**

Find the block immediately after `get_transition_class` (around line 112) and add:

```python
def list_transition_names() -> list[str]:
    """Return all registered transition names, sorted alphabetically."""
    return sorted(_TRANSITION_REGISTRY.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_transitions_registry.py -v
```

Expected: 3 passing tests.

- [ ] **Step 5: Run full suite to verify no regressions**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

Expected: all tests passing, count ≥ 1892.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/transitions/__init__.py tests/test_transitions_registry.py
git commit -m "feat: add list_transition_names() public registry API"
```

---

## Task 2: Rule 39 — Transition name validation (always-on)

**Files:**
- Modify: `src/led_ticker/validate.py`
- Modify: `tests/test_validate.py`

Rule 39: A transition name used anywhere in the config must exist in the transition registry. A typo currently passes `validate` but raises `ValueError` at startup. This check runs in normal mode (not just strict) because there is no deploy-target excuse for a misspelled transition name.

Locations checked: `[transitions] default`, `[transitions] between_sections`, per-section `transition` (when `transition_specified=True`), per-section `entry_transition`, per-section `widget_transition`.

The special sentinel `"cut"` is always valid (it means "no transition") and must be skipped.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_validate.py`:

```python
class TestRule39TransitionNames:
    """Unknown transition names surface as rule-39 errors."""

    async def test_unknown_transition_in_section_is_error(self, conf):
        result = await validate_config(conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "wipe_leftt"

[[playlist.section.widget]]
type = "message"
text = "hello"
"""))
        assert not result.valid
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "wipe_leftt" in rule_39[0].message

    async def test_did_you_mean_appears_for_close_typo(self, conf):
        result = await validate_config(conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "wipe_leftt"

[[playlist.section.widget]]
type = "message"
text = "hello"
"""))
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert any("wipe_left" in e.message for e in rule_39)

    async def test_cut_sentinel_is_always_valid(self, conf):
        result = await validate_config(conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "cut"

[[playlist.section.widget]]
type = "message"
text = "hello"
"""))
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert rule_39 == []

    async def test_known_transition_name_passes(self, conf):
        result = await validate_config(conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "wipe_left"

[[playlist.section.widget]]
type = "message"
text = "hello"
"""))
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert rule_39 == []

    async def test_unknown_between_sections_is_error(self, conf):
        result = await validate_config(conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[transitions]
between_sections = "pokball_alternating"

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
"""))
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "pokball_alternating" in rule_39[0].message

    async def test_unknown_entry_transition_is_error(self, conf):
        result = await validate_config(conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
entry_transition = "dissolvre"

[[playlist.section.widget]]
type = "message"
text = "hello"
"""))
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "dissolvre" in rule_39[0].message
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_validate.py::TestRule39TransitionNames -v
```

Expected: all 6 fail (some with `AssertionError` on `rule_39 == []` or not finding rule 39).

- [ ] **Step 3: Add `_check_transition_names` to `src/led_ticker/validate.py`**

Add the import at the top (with other TYPE_CHECKING imports or inline):
```python
import difflib
```
(Check if `difflib` is already imported; if not, add it to the top-level imports.)

Add the function after `_check_static` (around line 424):

```python
def _check_transition_names(config: "AppConfig") -> list[ValidationIssue]:
    """Rule 39: Named transitions must exist in the transition registry.

    Runs in normal mode (not just strict) — a typo in a transition name
    always fails at startup with no deploy-target excuse.

    Checks: [transitions] default, [transitions] between_sections,
    per-section `transition` (when transition_specified), `entry_transition`,
    `widget_transition`. The "cut" sentinel is always valid.
    """
    from led_ticker.transitions import list_transition_names

    valid_names = list_transition_names()
    valid_set = set(valid_names)
    issues: list[ValidationIssue] = []

    from led_ticker.config import TransitionConfig

    def _check(trans_cfg: "TransitionConfig | None", location: str) -> None:
        if trans_cfg is None or trans_cfg.type == "cut":
            return
        if trans_cfg.type in valid_set:
            return
        close = difflib.get_close_matches(trans_cfg.type, valid_names, n=1, cutoff=0.6)
        hint = f" (did you mean {close[0]!r}?)" if close else ""
        issues.append(
            ValidationIssue(
                rule=39,
                location=location,
                severity="error",
                message=f"unknown transition {trans_cfg.type!r}{hint}",
                fix=(
                    "Check the transition name spelling. "
                    "Run `led-ticker validate --list-fields` or see "
                    "docs.ledticker.dev/transitions/ for the full catalogue."
                ),
            )
        )

    _check(config.default_transition, "transitions.default")
    _check(config.between_sections, "transitions.between_sections")
    for i, section in enumerate(config.sections):
        if section.transition_specified:
            _check(section.transition, f"section[{i}].transition")
        if section.entry_transition is not None:
            _check(section.entry_transition, f"section[{i}].entry_transition")
        if section.widget_transition is not None:
            _check(section.widget_transition, f"section[{i}].widget_transition")

    return issues
```

- [ ] **Step 4: Wire `_check_transition_names` into `validate_config`**

In `validate_config`, find the Phase 1b block (around line 1154):

```python
    # Phase 1b: Static dict checks (rules enforced in widget constructors)
    errors.extend(_check_static(config))
```

Add immediately after:

```python
    # Phase 1b (cont.): Rule 39 — transition name registry check.
    # Always runs (not just --strict): a typo in a transition name always
    # fails at startup and has no deploy-target excuse.
    errors.extend(_check_transition_names(config))
```

- [ ] **Step 5: Run Rule 39 tests to verify they pass**

```bash
uv run pytest tests/test_validate.py::TestRule39TransitionNames -v
```

Expected: all 6 pass.

- [ ] **Step 6: Run full suite to verify no regressions**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

Expected: all tests passing, count increased by 6.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: validate rule 39 — unknown transition names surface as errors"
```

---

## Task 3: `--strict` mode — asset paths (Rule 40) + warning promotion

**Files:**
- Modify: `src/led_ticker/validate.py`
- Modify: `tests/test_validate.py`

`validate_config(path, *, strict=False)` gains a `strict` keyword argument. When `strict=True`:

1. Rule 40 runs: `path` fields on `gif`/`image` widgets must resolve to existing files relative to the config directory.
2. All warnings accumulated during the run are moved into the errors list before the function returns (making `result.valid` False on any warning).

This "promote warnings to errors" approach keeps the `ValidationResult` shape unchanged — callers already check `result.valid` which reads `len(errors) == 0`. In strict mode, the result is presented with all issues as errors.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_validate.py`:

```python
class TestRule40AssetPaths:
    """Asset path existence is checked in --strict mode only."""

    async def test_missing_gif_path_in_strict_mode_is_error(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "assets/missing.gif"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path, strict=True)
        rule_40 = [e for e in result.errors if e.rule == 40]
        assert len(rule_40) == 1
        assert "missing.gif" in rule_40[0].message

    async def test_missing_gif_path_in_normal_mode_is_not_error(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "assets/missing.gif"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path)
        rule_40 = [e for e in result.errors if e.rule == 40]
        assert rule_40 == []

    async def test_existing_gif_path_in_strict_mode_passes(self, tmp_path):
        gif_path = tmp_path / "assets" / "test.gif"
        gif_path.parent.mkdir()
        gif_path.write_bytes(b"GIF89a")  # minimal gif header
        toml_text = f"""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "assets/test.gif"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path, strict=True)
        rule_40 = [e for e in result.errors if e.rule == 40]
        assert rule_40 == []

    async def test_message_widget_path_not_checked(self, tmp_path):
        """message widgets have no path field — rule 40 must not fire."""
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path, strict=True)
        rule_40 = [e for e in result.errors if e.rule == 40]
        assert rule_40 == []


class TestStrictModeWarningPromotion:
    """In strict mode, warnings become errors."""

    async def test_strict_promotes_unknown_font_warning_to_error(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
font = "NonExistentFont"
font_size = 24
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)

        # Normal mode: rule 24 is a warning
        normal = await validate_config(config_path)
        rule_24_warnings = [w for w in normal.warnings if w.rule == 24]
        assert len(rule_24_warnings) == 1
        assert normal.valid  # warnings don't fail normal mode

        # Strict mode: rule 24 becomes an error
        strict = await validate_config(config_path, strict=True)
        rule_24_errors = [e for e in strict.errors if e.rule == 24]
        assert len(rule_24_errors) == 1
        assert not strict.valid

    async def test_strict_mode_no_warnings_remain(self, tmp_path):
        """In strict mode, ValidationResult.warnings is empty — all moved to errors."""
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
font = "NonExistentFont"
font_size = 24
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        strict = await validate_config(config_path, strict=True)
        assert strict.warnings == []

    async def test_clean_config_valid_in_both_modes(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "hello"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        normal = await validate_config(config_path)
        strict = await validate_config(config_path, strict=True)
        assert normal.valid
        assert strict.valid
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_validate.py::TestRule40AssetPaths tests/test_validate.py::TestStrictModeWarningPromotion -v
```

Expected: all fail (`TypeError: validate_config() got an unexpected keyword argument 'strict'`).

- [ ] **Step 3: Add `_check_asset_paths` to `src/led_ticker/validate.py`**

Add after `_check_transition_names`:

```python
def _check_asset_paths(config: "AppConfig", config_dir: Path) -> list[ValidationIssue]:
    """Rule 40: Asset `path` fields for gif/image widgets must exist on disk.

    Only runs in --strict mode. In normal mode, missing paths are silently
    allowed because the asset might only be present on the deploy target.
    """
    issues: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        for j, widget_cfg in enumerate(section.widgets):
            if widget_cfg.get("type") not in ("gif", "image"):
                continue
            raw_path = widget_cfg.get("path")
            if not raw_path:
                continue
            candidate = Path(raw_path)
            resolved = (
                candidate
                if candidate.is_absolute()
                else (config_dir / candidate).resolve()
            )
            if not resolved.exists():
                issues.append(
                    ValidationIssue(
                        rule=40,
                        location=f"section[{i}].widget[{j}]",
                        severity="error",
                        message=(
                            f"asset path {raw_path!r} does not exist"
                            f" (resolved to {resolved})"
                        ),
                        fix=(
                            "Check the path is correct relative to the config "
                            "file. In --strict mode all referenced asset files "
                            "must be present."
                        ),
                    )
                )
    return issues
```

- [ ] **Step 4: Update `validate_config` signature and add strict logic**

Change the function signature:

```python
async def validate_config(path: Path, *, strict: bool = False) -> ValidationResult:
    """Validate a TOML config file. Raises FileNotFoundError if path does not exist.

    When `strict=True`, all warnings are promoted to errors and asset-path
    existence is checked (Rule 40).
    """
```

Find the line that currently reads `return ValidationResult(path=path, errors=errors, warnings=warnings)` at the end of `validate_config` (around line 1257). Replace it with:

```python
    # Phase 2 (strict only): asset path existence check.
    # Not in normal mode — asset files may only exist on the deploy target.
    if strict:
        errors.extend(_check_asset_paths(config, path.parent))

    # Strict: promote all remaining warnings to errors before returning.
    # This keeps ValidationResult.valid semantics unchanged — callers
    # already check result.valid which reads len(errors) == 0.
    if strict and warnings:
        errors.extend(warnings)
        warnings = []

    return ValidationResult(path=path, errors=errors, warnings=warnings)
```

- [ ] **Step 5: Run Rule 40 + strict promotion tests to verify they pass**

```bash
uv run pytest tests/test_validate.py::TestRule40AssetPaths tests/test_validate.py::TestStrictModeWarningPromotion -v
```

Expected: all 7 pass.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

Expected: all tests passing.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: validate rule 40 (asset paths) and strict warning-promotion"
```

---

## Task 4: CLI `--strict` flag

**Files:**
- Modify: `src/led_ticker/app/cli.py`
- Modify: `tests/test_validate.py`

Wire `--strict` into the `validate` subcommand argparse. Pass `strict=True` to `validate_config`. The exit code is already 1 when `result.valid is False` — no change needed there since strict mode moves warnings into errors.

- [ ] **Step 1: Write the failing CLI tests**

Add to `tests/test_validate.py`:

```python
class TestStrictModeCLI:
    """--strict flag is accepted by the validate subcommand."""

    def test_cli_strict_exits_1_when_warnings_present(self, conf):
        """A config with only warnings exits 0 normally, 1 with --strict."""
        # Build a config with a warning: rule 24 (unknown font)
        toml = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
font = "GhostFont"
font_size = 24
"""
        path = conf(toml)
        # Normal mode: exits 0 (warning, not error)
        r_normal = subprocess.run(
            ["uv", "run", "led-ticker", "validate", str(path)],
            capture_output=True,
        )
        assert r_normal.returncode == 0, r_normal.stderr.decode()

        # Strict mode: exits 1 (warning promoted to error)
        r_strict = subprocess.run(
            ["uv", "run", "led-ticker", "validate", "--strict", str(path)],
            capture_output=True,
        )
        assert r_strict.returncode == 1

    def test_cli_strict_exits_0_on_clean_config(self, conf):
        path = conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        r = subprocess.run(
            ["uv", "run", "led-ticker", "validate", "--strict", str(path)],
            capture_output=True,
        )
        assert r.returncode == 0

    def test_cli_strict_json_output_valid_false_on_warning(self, conf):
        toml = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
font = "GhostFont"
font_size = 24
"""
        path = conf(toml)
        r = subprocess.run(
            ["uv", "run", "led-ticker", "validate", "--strict", "--json", str(path)],
            capture_output=True,
            text=True,
        )
        data = json.loads(r.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) > 0
        assert data["warnings"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_validate.py::TestStrictModeCLI -v
```

Expected: fail (`test_cli_strict_exits_1_when_warnings_present` exits 0 even with `--strict`; `--strict` flag may cause argparse to error).

- [ ] **Step 3: Add `--strict` flag to `src/led_ticker/app/cli.py`**

In `main()`, find the `val_parser.add_argument("--list-fields", ...)` block and add immediately after it:

```python
    val_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "Treat all warnings as errors. "
            "Also checks that asset file paths (gif/image `path`) exist. "
            "Use in CI to enforce a warning-clean config."
        ),
    )
```

Then find the `validate_config` call (around line 101):

```python
        result = asyncio.run(validate_config(args.path))
```

Change to:

```python
        result = asyncio.run(validate_config(args.path, strict=args.strict))
```

- [ ] **Step 4: Run CLI tests to verify they pass**

```bash
uv run pytest tests/test_validate.py::TestStrictModeCLI -v
```

Expected: all 3 pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

Expected: all tests passing.

- [ ] **Step 6: Manual smoke test**

```bash
uv run led-ticker validate --help
```

Expected: `--strict` appears in the help text for the validate subcommand.

```bash
uv run led-ticker validate --strict config/config.toml
```

Expected: Either exits 0 (clean) or shows promoted errors.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app/cli.py tests/test_validate.py
git commit -m "feat: add --strict flag to validate subcommand"
```

---

## Self-Review

**Spec coverage:**
- Rule 39 (transition name validation, always-on) ✓ Task 2
- Rule 40 (asset path existence, strict-only) ✓ Task 3
- `--strict` promotes warnings to errors ✓ Task 3
- `--strict` CLI flag + exit code ✓ Task 4
- `list_transition_names()` prerequisite ✓ Task 1

**No placeholders:** All steps have exact code, exact commands, exact expected output.

**Type consistency:** `validate_config(path: Path, *, strict: bool = False)` — `strict` is keyword-only (avoids positional collision with existing callers that pass only `path`). Every call site (`_format_human`, `_format_json`) only touches `ValidationResult` which has unchanged shape.

**Caller compatibility:** `asyncio.run(validate_config(args.path))` in cli.py and `await validate_config(conf(...))` in all existing tests keep working because `strict` is keyword-only with default `False`. Zero existing tests need updating.

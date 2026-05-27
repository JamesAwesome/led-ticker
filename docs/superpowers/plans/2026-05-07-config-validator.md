# Config Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `led-ticker validate <path> [--json]` that checks a TOML config for errors and warnings without running the display, usable by humans and by the `creating-a-config` skill.

**Architecture:** Two-phase validation — call `load_config()` for TOML/structural errors (phase 1a), then call `_build_widget(…, validate_only=True)` per widget for build-time errors (phase 1b), then run soft-rule checks against the loaded `AppConfig` dataclasses (phase 2). `app.py`'s `main()` is extended with a `validate` subparser; `--config` at the top level is preserved for back-compat.

**Tech Stack:** Python stdlib only (`argparse`, `asyncio`, `copy`, `json`); existing `led_ticker.app._build_widget`, `led_ticker.config.load_config`.

---

## File map

| File | Action |
|------|--------|
| `src/led_ticker/app.py` | Add `validate_only: bool = False` param to `_build_widget`; add `validate` subparser to `main()` |
| `src/led_ticker/validate.py` | **Create** — `ValidationIssue`, `ValidationResult`, `validate_config()`, `main()` |
| `tests/test_validate.py` | **Create** — all validator tests |
| `.claude/skills/creating-a-config/references/decision-rules.md` | Fix rule 12 wording (countdown + gif/image support) |
| `.claude/skills/creating-a-config/SKILL.md` | Add `led-ticker validate --json` calls at three checkpoints |

---

## Task 1: ValidationResult dataclasses

**Files:**
- Create: `src/led_ticker/validate.py`
- Create: `tests/test_validate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validate.py
from pathlib import Path
import textwrap
import pytest
from led_ticker.validate import ValidationIssue, ValidationResult


def test_valid_when_no_errors():
    r = ValidationResult(path=Path("x.toml"), errors=[], warnings=[])
    assert r.valid is True


def test_invalid_when_errors_present():
    issue = ValidationIssue(rule=1, location="section[0]", message="bad", fix="fix it", severity="error")
    r = ValidationResult(path=Path("x.toml"), errors=[issue], warnings=[])
    assert r.valid is False


def test_valid_with_only_warnings():
    w = ValidationIssue(rule=21, location="section[0]", message="slow", fix="speed up", severity="warning")
    r = ValidationResult(path=Path("x.toml"), errors=[], warnings=[w])
    assert r.valid is True
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -x -q
```
Expected: `ImportError: cannot import name 'ValidationIssue' from 'led_ticker.validate'`

- [ ] **Step 3: Create `src/led_ticker/validate.py` with dataclasses**

```python
"""Config file validator for led-ticker."""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class ValidationIssue:
    rule: int | None
    location: str
    message: str
    fix: str
    severity: Literal["error", "warning"]


@dataclass
class ValidationResult:
    path: Path
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


def validate_config(path: Path) -> ValidationResult:
    """Validate a config file. Returns a ValidationResult."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError
```

- [ ] **Step 4: Run tests — expect PASS (3 tests)**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -x -q
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: add ValidationIssue and ValidationResult dataclasses"
```

---

## Task 2: Add `validate_only` mode to `_build_widget`

**Files:**
- Modify: `src/led_ticker/app.py` (line ~398)

- [ ] **Step 1: Write failing test**

Add to `tests/test_validate.py`:

```python
import asyncio
from led_ticker.app import _build_widget


def test_build_widget_validate_only_returns_none_for_valid_widget():
    cfg = {"type": "message", "text": "hello"}
    result = asyncio.run(
        _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]
    )
    assert result is None


def test_build_widget_validate_only_raises_on_text_scale():
    cfg = {"type": "message", "text": "hi", "text_scale": 2}
    with pytest.raises(ValueError, match="text_scale"):
        asyncio.run(
            _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]
        )


def test_build_widget_validate_only_raises_on_animation_wrong_type():
    cfg = {"type": "weather", "location": "NYC", "animation": "typewriter"}
    with pytest.raises(ValueError, match="animation is only valid"):
        asyncio.run(
            _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]
        )
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py::test_build_widget_validate_only_returns_none_for_valid_widget -x -q
```
Expected: `TypeError: _build_widget() got an unexpected keyword argument 'validate_only'`

- [ ] **Step 3: Add `validate_only` parameter to `_build_widget` in `app.py`**

Find the function signature at line ~398 and add the parameter:

```python
async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
    validate_only: bool = False,
) -> Any:
```

Then find the two lines at the bottom of the function (~lines 605-608) that construct the widget:

```python
    if hasattr(cls, "start"):
        widget = await cls.start(session=session, **widget_cfg)
    else:
        widget = cls(**widget_cfg)

    return widget
```

Replace with:

```python
    if validate_only:
        return None

    if hasattr(cls, "start"):
        widget = await cls.start(session=session, **widget_cfg)
    else:
        widget = cls(**widget_cfg)

    return widget
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -x -q
```
Expected: `6 passed`

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
PYTHONPATH=tests/stubs uv run pytest -q 2>&1 | tail -5
```
Expected: `1386 passed, 1 skipped` (same as before)

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app.py tests/test_validate.py
git commit -m "feat: add validate_only mode to _build_widget"
```

---

## Task 3: Hard-error collection in `validate_config`

**Files:**
- Modify: `src/led_ticker/validate.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validate.py`:

```python
import textwrap
from led_ticker.validate import validate_config


@pytest.fixture
def conf(tmp_path):
    """Write a TOML string to a temp file and return its Path."""
    def _write(toml_str: str) -> Path:
        p = tmp_path / "config.toml"
        p.write_text(textwrap.dedent(toml_str))
        return p
    return _write


GOOD_CONFIG = """\
    [display]
    rows = 32
    cols = 64
    chain = 8
    default_scale = 4

    [[playlist.section]]
    mode = "swap"
    hold_time = 3

    [[playlist.section.widget]]
    type = "message"
    text = "hello"
    """


def test_happy_path_returns_valid(conf):
    result = validate_config(conf(GOOD_CONFIG))
    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


def test_toml_syntax_error_returns_error(conf):
    result = validate_config(conf("[display\n"))
    assert not result.valid
    assert len(result.errors) == 1
    assert result.errors[0].location == "config"


def test_unknown_widget_type_returns_error(conf):
    result = validate_config(conf(GOOD_CONFIG + "\n[[playlist.section.widget]]\ntype = \"banana\"\n"))
    assert not result.valid
    assert any("section[0].widget[1]" in e.location for e in result.errors)


def test_text_scale_migration_error(conf):
    cfg = GOOD_CONFIG.replace('text = "hello"', 'text = "hello"\ntext_scale = 2')
    result = validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 20 for e in result.errors)


def test_animation_on_wrong_widget_type(conf):
    extra = '\n[[playlist.section.widget]]\ntype = "weather"\nlocation = "NYC"\nanimation = "typewriter"\n'
    result = validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 12 for e in result.errors)


def test_border_on_wrong_widget_type(conf):
    extra = '\n[[playlist.section.widget]]\ntype = "weather"\nlocation = "NYC"\nborder = "rainbow"\n'
    result = validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 15 for e in result.errors)


def test_rule3_scroll_plus_stretch(conf):
    extra = '\n[[playlist.section.widget]]\ntype = "image"\npath = "x.png"\ntext_align = "scroll"\nfit = "stretch"\n'
    result = validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 3 for e in result.errors)


def test_rule7_text_x_offset_with_scroll(conf):
    extra = '\n[[playlist.section.widget]]\ntype = "image"\npath = "x.png"\ntext_align = "scroll"\ntext_x_offset = 5\n'
    result = validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 7 for e in result.errors)


def test_rule8_hold_seconds_too_short(conf):
    extra = '\n[[playlist.section.widget]]\ntype = "image"\npath = "x.png"\nhold_seconds = 0.001\n'
    result = validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 8 for e in result.errors)


def test_rule14_typewriter_on_gif_two_row(conf):
    extra = '\n[[playlist.section.widget]]\ntype = "gif"\npath = "x.gif"\nanimation = "typewriter"\nbottom_text = "hello"\ntext = "world"\n'
    result = validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 14 for e in result.errors)


def test_rule14_typewriter_on_gif_single_row_ok(conf):
    extra = '\n[[playlist.section.widget]]\ntype = "gif"\npath = "x.gif"\nanimation = "typewriter"\ntext = "world"\n'
    result = validate_config(conf(GOOD_CONFIG + extra))
    # single-row with non-empty text — typewriter is allowed on gif
    assert all(e.rule != 14 for e in result.errors)


def test_missing_config_file_raises():
    with pytest.raises(FileNotFoundError):
        validate_config(Path("/tmp/does_not_exist_xyz.toml"))
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -x -q 2>&1 | head -15
```
Expected: `NotImplementedError` from `validate_config`

- [ ] **Step 3: Implement `validate_config` in `validate.py`**

Replace the stub `validate_config` with the full implementation:

```python
from led_ticker.app import _build_widget, _configure_user_font_dir
from led_ticker.config import AppConfig, SectionConfig, load_config


# Maps substrings in exception messages to (rule, fix) pairs.
_ERROR_PATTERNS: list[tuple[str, int | None, str]] = [
    ("text_scale removed", 20, "Replace text_scale with font_size = N × cell_h (e.g. font_size=24 for 6×12 BDF at 2×)"),
    ("presentation removed", None, "Use font_color / animation instead of presentation"),
    ("animation is only valid on", 12, "Remove animation from this widget type; valid on message, gif, image"),
    ("border is only valid on", 15, "Remove border from this widget type; valid on message, countdown, two_row, gif, image"),
    ("requires font_size", 5, "Add font_size = <pixels> next to font (e.g. font_size = 24 on bigsign)"),
    ("font_threshold", 10, "Use an integer 0–255 for font_threshold (not float, string, or bool)"),
]


def _classify_error(msg: str) -> tuple[int | None, str]:
    for pattern, rule, fix in _ERROR_PATTERNS:
        if pattern in msg:
            return rule, fix
    return None, "See error message for details."


async def _run_build_checks(
    sections: list[SectionConfig], config_dir: Path
) -> list[tuple[str, str]]:
    """Run _build_widget(validate_only=True) for every widget. Returns (location, error_msg) pairs."""
    issues: list[tuple[str, str]] = []
    for i, section in enumerate(sections):
        for j, widget_cfg in enumerate(section.widgets):
            try:
                await _build_widget(
                    copy.deepcopy(widget_cfg),
                    session=None,  # type: ignore[arg-type]
                    config_dir=config_dir,
                    validate_only=True,
                )
            except Exception as e:
                issues.append((f"section[{i}].widget[{j}]", str(e)))
    return issues


def _check_static(config: AppConfig) -> list[ValidationIssue]:
    """Synchronous checks on raw widget dicts for errors not caught by _build_widget."""
    issues: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        for j, widget_cfg in enumerate(section.widgets):
            loc = f"section[{i}].widget[{j}]"
            wtype = widget_cfg.get("type", "")

            # Rule 3: scroll + stretch
            if widget_cfg.get("text_align") in ("scroll", "scroll_over") and widget_cfg.get("fit") == "stretch":
                issues.append(ValidationIssue(
                    rule=3, location=loc, severity="error",
                    message="text_align='scroll' with fit='stretch': no transparent regions for text to walk behind",
                    fix="Change fit to 'pillarbox', 'letterbox', or 'crop'; or change text_align to 'left'/'right'",
                ))

            # Rule 7: text_x_offset + scroll
            if widget_cfg.get("text_x_offset", 0) != 0 and widget_cfg.get("text_align") in ("scroll", "scroll_over"):
                issues.append(ValidationIssue(
                    rule=7, location=loc, severity="error",
                    message="text_x_offset is invalid with scroll text_align",
                    fix="Remove text_x_offset, or use a non-scroll text_align",
                ))

            # Rule 8: hold_seconds < 0.05
            hold_s = widget_cfg.get("hold_seconds")
            if hold_s is not None and float(hold_s) < 0.05:
                issues.append(ValidationIssue(
                    rule=8, location=loc, severity="error",
                    message=f"hold_seconds={hold_s} is too short (< 50 ms), likely a typo",
                    fix="Raise hold_seconds to at least 0.05 (50 ms)",
                ))

            # Rule 14: typewriter on gif/image constraints
            if wtype in ("gif", "image") and widget_cfg.get("animation") == "typewriter":
                if widget_cfg.get("bottom_text", "") != "":
                    issues.append(ValidationIssue(
                        rule=14, location=loc, severity="error",
                        message="animation='typewriter' on gif/image is single-row only; bottom_text is set",
                        fix="Remove animation or remove bottom_text",
                    ))
                if widget_cfg.get("text_align") in ("scroll", "scroll_over"):
                    issues.append(ValidationIssue(
                        rule=14, location=loc, severity="error",
                        message="animation='typewriter' on gif/image cannot combine with scrolling text_align",
                        fix="Remove animation, or change text_align to 'left'/'right'/'auto'",
                    ))
                if not widget_cfg.get("text", ""):
                    issues.append(ValidationIssue(
                        rule=14, location=loc, severity="error",
                        message="animation='typewriter' on gif/image requires non-empty text",
                        fix="Add text = '...' or remove animation",
                    ))
    return issues


def validate_config(path: Path) -> ValidationResult:
    """Validate a TOML config file. Raises FileNotFoundError if path does not exist."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    # Phase 1a: TOML load + structural parse
    try:
        config = load_config(path)
    except Exception as e:
        errors.append(ValidationIssue(
            rule=None, location="config", severity="error",
            message=str(e),
            fix="Fix the TOML syntax or structural error above.",
        ))
        return ValidationResult(path=path, errors=errors, warnings=warnings)

    # Phase 1b: Static dict checks (rules enforced in widget constructors, not _build_widget)
    errors.extend(_check_static(config))

    # Phase 1c: Build-time checks via _build_widget(validate_only=True)
    _configure_user_font_dir(path)
    build_errors = asyncio.run(_run_build_checks(config.sections, path.parent))
    for location, msg in build_errors:
        rule, fix = _classify_error(msg)
        errors.append(ValidationIssue(
            rule=rule, location=location, severity="error",
            message=msg, fix=fix,
        ))

    # Phase 2: Soft rule warnings (only run when no hard errors)
    if not errors:
        warnings.extend(_check_soft(config))

    return ValidationResult(path=path, errors=errors, warnings=warnings)
```

Also add a stub for `_check_soft` (implemented in Task 4):

```python
def _check_soft(config: AppConfig) -> list[ValidationIssue]:
    return []
```

- [ ] **Step 4: Run tests — expect near-full PASS**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -x -q
```
Expected: most tests pass; `test_happy_path_returns_valid` and soft-rule tests may fail if `_check_soft` stub returns issues — debug if needed.

- [ ] **Step 5: Run full suite for regressions**

```bash
PYTHONPATH=tests/stubs uv run pytest -q 2>&1 | tail -3
```
Expected: same pass count as before + new tests passing.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py src/led_ticker/app.py
git commit -m "feat: validate_config phase 1 — hard-error collection"
```

---

## Task 4: Soft rule checks (Rules 1, 2, 6, 21)

**Files:**
- Modify: `src/led_ticker/validate.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validate.py`:

```python
def test_rule1_content_height_overflow(conf):
    # bigsign: scale=4, panel_h=64; content_height=20 → 20×4=80 > 64
    cfg = GOOD_CONFIG.replace("hold_time = 3", "hold_time = 3\ncontent_height = 20")
    result = validate_config(conf(cfg))
    assert result.valid is True  # soft warning, not error
    assert any(w.rule == 1 for w in result.warnings)


def test_rule1_no_warning_when_within_limits(conf):
    # content_height=16 × scale=4 = 64 == panel_h=64, not over
    result = validate_config(conf(GOOD_CONFIG))
    assert all(w.rule != 1 for w in result.warnings)


def test_rule2_font_threshold_mismatch(conf):
    cfg = GOOD_CONFIG + textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "message"
        text = "bold"
        font = "Inter-Bold"
        font_threshold = 128

        [[playlist.section.widget]]
        type = "message"
        text = "regular"
        font = "Inter-Regular"
        font_threshold = 80
        """)
    result = validate_config(conf(cfg))
    assert any(w.rule == 2 for w in result.warnings)


def test_rule2_no_warning_when_thresholds_match(conf):
    cfg = GOOD_CONFIG + textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "message"
        text = "bold"
        font = "Inter-Bold"
        font_threshold = 80

        [[playlist.section.widget]]
        type = "message"
        text = "regular"
        font = "Inter-Regular"
        font_threshold = 80
        """)
    result = validate_config(conf(cfg))
    assert all(w.rule != 2 for w in result.warnings)


def test_rule6_two_row_at_scale4(conf):
    cfg = GOOD_CONFIG + textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "@handle"
        bottom_text = "promo"
        """)
    result = validate_config(conf(cfg))
    assert any(w.rule == 6 for w in result.warnings)


def test_rule21_duration_too_large(conf):
    cfg = GOOD_CONFIG.replace(
        "[[playlist.section]]",
        "[[playlist.section]]\ntransition_duration = 500.0\n"
    )
    result = validate_config(conf(cfg))
    assert any(w.rule == 21 for w in result.warnings)


def test_rule21_duration_too_small(conf):
    cfg = GOOD_CONFIG.replace(
        "[[playlist.section]]",
        "[[playlist.section]]\ntransition_duration = 0.001\n"
    )
    result = validate_config(conf(cfg))
    assert any(w.rule == 21 for w in result.warnings)


def test_rule21_normal_duration_no_warning(conf):
    result = validate_config(conf(GOOD_CONFIG))
    assert all(w.rule != 21 for w in result.warnings)
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py::test_rule1_content_height_overflow -x -q
```
Expected: `AssertionError` — `_check_soft` stub returns `[]`

- [ ] **Step 3: Implement `_check_soft` in `validate.py`**

Replace the stub:

```python
from led_ticker.config import DisplayConfig

_WEIGHT_SUFFIXES = frozenset(
    "Regular Bold Light Medium Thin Black Heavy ExtraBold SemiBold Italic BoldItalic".split()
)


def _font_family(name: str) -> str:
    """Return the family stem by stripping a trailing weight suffix."""
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1] in _WEIGHT_SUFFIXES:
        return parts[0]
    return name


def _panel_h_real(display: DisplayConfig) -> int:
    """Best-effort panel height in real pixels."""
    if display.pixel_mapper_config.startswith("Remap:"):
        # "Remap:256,64|..." — second number is total canvas height
        remap = display.pixel_mapper_config[6:]
        dims = remap.split("|")[0]
        return int(dims.split(",")[1])
    return display.rows * display.parallel


def _check_soft(config: AppConfig) -> list[ValidationIssue]:
    warnings: list[ValidationIssue] = []
    ph = _panel_h_real(config.display)

    for i, section in enumerate(config.sections):
        # Rule 1: content_height overflow
        product = section.content_height * section.scale
        if product > ph:
            warnings.append(ValidationIssue(
                rule=1, location=f"section[{i}]", severity="warning",
                message=(
                    f"content_height {section.content_height} × scale {section.scale} "
                    f"= {product} exceeds panel height {ph}px — edges will clip"
                ),
                fix=f"Lower content_height to {ph // section.scale} (= panel_h ÷ scale)",
            ))

        # Rule 6: two_row at scale=4
        for j, widget_cfg in enumerate(section.widgets):
            if widget_cfg.get("type") == "two_row" and section.scale == 4:
                warnings.append(ValidationIssue(
                    rule=6, location=f"section[{i}].widget[{j}]", severity="warning",
                    message="two_row at scale=4: logical canvas is only 64px wide — handles may scroll instead of fitting",
                    fix="Add scale = 2 to this section for a 128px logical canvas",
                ))

        # Rule 2: font_threshold mismatch within font family
        family_thresholds: dict[str, list[int]] = {}
        for widget_cfg in section.widgets:
            fname = widget_cfg.get("font")
            if fname is None:
                continue
            thr = int(widget_cfg.get("font_threshold", 128))
            family = _font_family(str(fname))
            family_thresholds.setdefault(family, []).append(thr)

        for family, thresholds in family_thresholds.items():
            unique = set(thresholds)
            if len(unique) > 1:
                warnings.append(ValidationIssue(
                    rule=2, location=f"section[{i}]", severity="warning",
                    message=(
                        f"Font family '{family}' used with mismatched font_threshold values: "
                        f"{sorted(unique)} — weight contrast may invert on panel"
                    ),
                    fix="Set the same font_threshold on all widgets in the same font family (e.g. both at 80)",
                ))

    # Rule 21: transition_duration plausibility
    trans_locations: list[tuple[str, Any]] = [
        ("transitions.default", config.default_transition),
        ("transitions.between_sections", config.between_sections),
    ]
    for i, section in enumerate(config.sections):
        trans_locations.append((f"section[{i}].transition", section.transition))

    for loc, trans in trans_locations:
        d = trans.duration
        if d > 5.0:
            warnings.append(ValidationIssue(
                rule=21, location=loc, severity="warning",
                message=f"transition_duration {d} looks like milliseconds (> 5 s is unusual)",
                fix=f"Divide by 1000 → {d / 1000:.3f} s",
            ))
        elif d < 0.05:
            warnings.append(ValidationIssue(
                rule=21, location=loc, severity="warning",
                message=f"transition_duration {d} is extremely short (< 50 ms)",
                fix="Raise to at least 0.05 s",
            ))

    return warnings
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -x -q
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: validate_config phase 2 — soft rule warnings (rules 1, 2, 6, 21)"
```

---

## Task 5: Output formatting and `main()`

**Files:**
- Modify: `src/led_ticker/validate.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validate.py`:

```python
import subprocess


def test_json_output_valid_config(conf):
    path = conf(GOOD_CONFIG)
    from led_ticker.validate import _format_json
    result = validate_config(path)
    data = json.loads(_format_json(result))
    assert data["valid"] is True
    assert data["errors"] == []
    assert data["warnings"] == []
    assert data["path"] == str(path)


def test_json_output_with_error(conf):
    from led_ticker.validate import _format_json
    issue = ValidationIssue(rule=5, location="section[0].widget[0]", message="bad", fix="fix", severity="error")
    result = ValidationResult(path=Path("x.toml"), errors=[issue], warnings=[])
    data = json.loads(_format_json(result))
    assert data["valid"] is False
    assert len(data["errors"]) == 1
    assert data["errors"][0]["rule"] == 5
    assert data["errors"][0]["location"] == "section[0].widget[0]"
    assert data["errors"][0]["message"] == "bad"
    assert data["errors"][0]["fix"] == "fix"


def test_cli_exit_code_0_on_valid(conf, tmp_path):
    path = conf(GOOD_CONFIG)
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0


def test_cli_exit_code_1_on_error(conf, tmp_path):
    path = conf(GOOD_CONFIG + "\n[[playlist.section.widget]]\ntype = \"banana\"\n")
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1


def test_cli_exit_code_2_on_missing_file(tmp_path):
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(tmp_path / "missing.toml")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2


def test_cli_json_flag_produces_parseable_output(conf):
    path = conf(GOOD_CONFIG)
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(path), "--json"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["valid"] is True
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py::test_json_output_valid_config -x -q
```
Expected: `ImportError: cannot import name '_format_json'`

- [ ] **Step 3: Implement `_format_json`, `_format_human`, and `main()` in `validate.py`**

```python
def _issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    return {
        "rule": issue.rule,
        "location": issue.location,
        "message": issue.message,
        "fix": issue.fix,
    }


def _format_json(result: ValidationResult) -> str:
    return json.dumps(
        {
            "valid": result.valid,
            "path": str(result.path),
            "errors": [_issue_to_dict(e) for e in result.errors],
            "warnings": [_issue_to_dict(w) for w in result.warnings],
        },
        indent=2,
    )


def _format_human(result: ValidationResult) -> str:
    lines = [f"Validating {result.path}...", ""]
    for issue in result.errors:
        rule_tag = f" [rule {issue.rule}]" if issue.rule is not None else ""
        lines.append(f"✗ ERROR   {issue.location}: {issue.message}{rule_tag}")
        lines.append(f"          Fix: {issue.fix}")
        lines.append("")
    for issue in result.warnings:
        rule_tag = f" [rule {issue.rule}]" if issue.rule is not None else ""
        lines.append(f"⚠ WARNING {issue.location}: {issue.message}{rule_tag}")
        lines.append(f"          Fix: {issue.fix}")
        lines.append("")
    n = len(result.errors) + len(result.warnings)
    if n == 0:
        lines.append("No issues found.")
    else:
        lines.append(
            f"{n} issue(s): {len(result.errors)} error(s), {len(result.warnings)} warning(s)"
        )
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate a led-ticker config file")
    parser.add_argument("path", type=Path, help="Path to TOML config file")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON")
    args = parser.parse_args()

    try:
        result = validate_config(args.path)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    if args.json_output:
        print(_format_json(result))
    else:
        print(_format_human(result))

    sys.exit(0 if result.valid else 1)
```

- [ ] **Step 4: Run tests (non-CLI first, then CLI)**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -x -q -k "not test_cli"
```
Expected: all non-CLI tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: add _format_json, _format_human, and validate main()"
```

---

## Task 6: Subcommand refactor of `app.py` — wire `validate`

**Files:**
- Modify: `src/led_ticker/app.py`

- [ ] **Step 1: Write failing CLI test**

The CLI tests from Task 5 will pass once `led-ticker validate` is wired up. Run them now to confirm they fail:

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py::test_cli_exit_code_0_on_valid -x -q
```
Expected: `AssertionError` — `led-ticker validate` prints error about unknown subcommand

- [ ] **Step 2: Refactor `main()` in `app.py` to add `validate` subparser**

Replace the existing `main()` function body:

```python
def main() -> None:
    """CLI entry point."""
    _setup_logging()

    parser = argparse.ArgumentParser(description="LED Ticker Display")
    # Top-level --config kept for back-compat: `led-ticker --config foo.toml`
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML configuration file (default: config.toml)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # `validate` subcommand
    val_parser = subparsers.add_parser(
        "validate",
        help="Validate a config file without running the display",
    )
    val_parser.add_argument("path", type=Path, help="Path to TOML config file")
    val_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit JSON output",
    )

    args = parser.parse_args()

    if args.command == "validate":
        from led_ticker.validate import main as _validate_main

        sys.argv = [sys.argv[0], str(args.path)]
        if args.json_output:
            sys.argv.append("--json")
        _validate_main()
        return

    # Default: run the display (back-compat path)
    if not args.config.exists():
        print(f"Config file not found: {args.config}", file=sys.stderr)
        print(
            "Copy config.example.toml to config.toml and customize it.",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(run(args.config))
```

- [ ] **Step 3: Run all CLI tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py -x -q
```
Expected: all tests pass.

- [ ] **Step 4: Run full suite for regressions**

```bash
PYTHONPATH=tests/stubs uv run pytest -q 2>&1 | tail -3
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app.py tests/test_validate.py
git commit -m "feat: add 'led-ticker validate' subcommand"
```

---

## Task 7: Update skill files

**Files:**
- Modify: `.claude/skills/creating-a-config/references/decision-rules.md`
- Modify: `.claude/skills/creating-a-config/SKILL.md`

- [ ] **Step 1: Fix rule 12 in `decision-rules.md`**

Find the rule 12 section and replace it:

**Old:**
```markdown
## Rule 12: animation = "typewriter" only on message widget

**SOURCE:** CLAUDE.md — "Color providers and animations" section (line 243-244).

**DETECT:** A widget of type other than `"message"` (or `"countdown"` which extends `"message"`) specifies `animation = "typewriter"`.

**SYMPTOM:** Config load raises with an error message: "_build_widget raises if `animation` appears on any other widget type."

**FIX:** Remove `animation = "typewriter"` from non-message widgets. Typewriter effect is only supported on TickerMessage and TickerCountdown. For other widgets (gif, image, two_row, etc.), use `font_color = "rainbow"` or other color effects instead.
```

**New:**
```markdown
## Rule 12: animation = "typewriter" only on message, countdown, gif, image

**SOURCE:** CLAUDE.md — "Color providers and animations" and "Typewriter on image widgets" sections.

**DETECT:** A widget of type other than `"message"`, `"countdown"`, `"gif"`, or `"image"` specifies `animation = "typewriter"`.

**SYMPTOM:** Config load raises: "animation is only valid on type='message', 'gif', or 'image'."

**FIX:** Remove `animation = "typewriter"` from data widgets (weather, rss_feed, mlb, crypto, etc.). Typewriter is supported on:
- `message` / `countdown` — full support
- `gif` / `image` — single-row only (see rule 14 for constraints)

For other widgets, use `font_color = "rainbow"` or other color effects instead.
```

- [ ] **Step 2: Add validator calls to `SKILL.md` at three checkpoints**

In `SKILL.md`, find the three validation checkpoints and add the validator invocation before each. The three checkpoints are:

1. **Phase 2, step 5** — per-section lint: add after the rule-check instruction:
```markdown
   Run `led-ticker validate config/config.toml --json` and surface any `errors` or `warnings` from the output as flag-and-ask items, citing each `rule` and `fix` field.
```

2. **Phase 3 final validation** — add after "Run final validation: full pass...":
```markdown
Run `led-ticker validate config/config.toml --json`. Surface all `errors` as mandatory fixes and `warnings` as flag-and-ask before writing.
```

3. **Refine mode, step 1** — after "Run a full validation pass":
```markdown
   Run `led-ticker validate config/config.toml --json` and cache the output as the violation list (use `errors` and `warnings` from the JSON).
```

- [ ] **Step 3: Commit skill updates**

```bash
git add .claude/skills/creating-a-config/references/decision-rules.md \
        .claude/skills/creating-a-config/SKILL.md
git commit -m "docs: update skill files to use led-ticker validate; fix rule 12 wording"
```

---

## Final check

- [ ] **Run full test suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -q 2>&1 | tail -5
```
Expected: all tests pass (1386+ total).

- [ ] **Manual smoke test**

```bash
uv run led-ticker validate config/config.random_transitions.toml
uv run led-ticker validate config/config.random_transitions.toml --json | python3 -m json.tool
```
Expected: first command prints "No issues found.", second prints valid JSON with `"valid": true`.

- [ ] **Back-compat check**

```bash
uv run led-ticker --help
```
Expected: shows `--config` option AND `validate` subcommand in help text.

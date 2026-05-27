# Config Coerce-and-Warn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a coerce-and-warn pass at config load so `font_size = "25"` and `image_align = "Left"` (and similar slips) coerce to canonical values silently, emitting warnings via `led-ticker validate` and runtime startup logs instead of crashing.

**Architecture:** Three pure coerce helpers (`coerce_int`, `coerce_float`, `coerce_choice`) in a new `_coerce.py` module. They return `(value, warning_msg_or_None)` so the caller decides where the warning goes. Call sites: `config.py:load_config` (for `SectionConfig` / `DisplayConfig` / `TransitionConfig` fields), `app.py:_build_widget` (for widget_cfg int/float/enum fields), `transitions/__init__.py` (for `easing` lookup — also fixes today's silent fallback to `linear`). Warnings collected on `AppConfig._coerce_warnings`; `validate.py` surfaces them as new rule-37 warnings, `app.py:run()` logs them via `logging.warning`.

**Tech Stack:** Python 3.13, attrs (widget dataclasses), dataclasses (config), pytest, tomllib.

**Spec:** [docs/superpowers/specs/2026-05-19-config-coerce-and-warn-design.md](../specs/2026-05-19-config-coerce-and-warn-design.md)

---

## File Structure

**New files:**
- `src/led_ticker/_coerce.py` — three pure helpers + `CoercionWarning` dataclass.
- `tests/test_coerce.py` — unit tests for the helpers.
- `tests/test_app_runtime_warnings.py` — runtime startup-log integration test.

**Modified files:**
- `src/led_ticker/config.py` — `AppConfig` gets `_coerce_warnings: list[CoercionWarning]`; `load_config` populates it by coercing `DisplayConfig`, `SectionConfig`, and `TransitionConfig` fields.
- `src/led_ticker/app.py` — `_build_widget` gains coercion of widget_cfg int/float/enum fields. `run()` logs warnings at startup.
- `src/led_ticker/transitions/__init__.py` — `EASING.get(easing, linear)` → explicit coerce-and-validate with unknown-easing error.
- `src/led_ticker/validate.py` — new `_check_coercions` reads warnings from `AppConfig`, emits rule-37 warnings.
- `tests/test_validate.py` — end-to-end tests that `font_size = "25"`, `image_align = "Left"`, `easing = "Linear"` all produce warnings (not errors); `font_color = "255,0,0"` is still an error; `font_size = true` is still an error.
- `docs/site/src/content/docs/reference/config-options.mdx` — new "Coercion behavior" callout.

---

## Task 1: Coerce helpers — int

**Files:**
- Create: `src/led_ticker/_coerce.py`
- Test: `tests/test_coerce.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_coerce.py`:

```python
"""Tests for led_ticker._coerce — pure coercion helpers for config load."""

import pytest

from led_ticker._coerce import CoercionWarning, coerce_int


class TestCoerceInt:
    def test_int_passthrough_no_warning(self):
        value, warning = coerce_int(25, field="font_size")
        assert value == 25
        assert warning is None

    def test_string_of_digits_coerces_with_warning(self):
        value, warning = coerce_int("25", field="font_size")
        assert value == 25
        assert isinstance(warning, CoercionWarning)
        assert warning.field == "font_size"
        assert warning.original == "25"
        assert warning.coerced == 25
        assert "font_size" in warning.message
        assert '"25"' in warning.message

    def test_negative_string_coerces(self):
        value, warning = coerce_int("-5", field="text_y_offset")
        assert value == -5
        assert warning is not None

    def test_bool_rejected(self):
        # bool is an int subclass; coercing true→1 would reopen the
        # font_threshold / bottom_text_loops hole.
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int(True, field="font_size")

    def test_non_numeric_string_rejected(self):
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int("big", field="font_size")

    def test_float_rejected(self):
        # Floats should use coerce_float; rejecting here makes intent explicit.
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int(2.5, field="font_size")

    def test_float_string_rejected(self):
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int("2.5", field="font_size")

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int(None, field="font_size")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_coerce.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'led_ticker._coerce'`

- [ ] **Step 3: Implement `_coerce.py` with `coerce_int`**

Create `src/led_ticker/_coerce.py`:

```python
"""Pure coercion helpers for config load.

Each helper returns `(coerced_value, warning_or_None)`. The caller
decides whether to surface the warning via `led-ticker validate`
output, runtime `logging.warning`, or both.

Bool is rejected explicitly in `coerce_int` / `coerce_float` because
bool is a subclass of `int` in Python. Silently coercing `true → 1`
would reopen the hole that the existing `bottom_text_loops` and
`font_threshold` validators close.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoercionWarning:
    field: str
    original: object
    coerced: object
    message: str


def coerce_int(value: object, *, field: str) -> tuple[int, CoercionWarning | None]:
    """Coerce string-of-digits → int. Raise ValueError otherwise.

    Rejects: bool, float, non-numeric strings, None.
    """
    if isinstance(value, bool):
        raise ValueError(
            f"{field} must be an int; got bool ({value!r}). "
            f"TOML has native true/false — if you meant a number, drop the "
            f"true/false and write 0 or 1 explicitly."
        )
    if isinstance(value, int):
        return value, None
    if isinstance(value, str):
        try:
            coerced = int(value)
        except ValueError:
            raise ValueError(
                f"{field} must be an int; got str ({value!r}). "
                f"Drop the quotes around the number (e.g. {field} = 25 "
                f"instead of {field} = \"25\")."
            ) from None
        return coerced, CoercionWarning(
            field=field,
            original=value,
            coerced=coerced,
            message=(
                f"{field} was a string ({value!r}); coerced to int {coerced}. "
                f"Drop the quotes around the number to silence this warning."
            ),
        )
    raise ValueError(
        f"{field} must be an int; got {type(value).__name__} ({value!r})."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_coerce.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/_coerce.py tests/test_coerce.py
git commit -m "feat: add coerce_int helper for config load"
```

---

## Task 2: Coerce helpers — float

**Files:**
- Modify: `src/led_ticker/_coerce.py`
- Test: `tests/test_coerce.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coerce.py`:

```python
from led_ticker._coerce import coerce_float


class TestCoerceFloat:
    def test_float_passthrough(self):
        value, warning = coerce_float(3.0, field="hold_time")
        assert value == 3.0
        assert warning is None

    def test_int_promotes_to_float_no_warning(self):
        # int → float promotion is standard Python; no coercion warning.
        value, warning = coerce_float(3, field="hold_time")
        assert value == 3.0
        assert isinstance(value, float)
        assert warning is None

    def test_string_of_decimal_coerces_with_warning(self):
        value, warning = coerce_float("3.0", field="hold_time")
        assert value == 3.0
        assert warning is not None
        assert warning.field == "hold_time"
        assert warning.original == "3.0"
        assert warning.coerced == 3.0

    def test_string_of_integer_coerces_to_float(self):
        value, warning = coerce_float("3", field="hold_time")
        assert value == 3.0
        assert warning is not None

    def test_bool_rejected(self):
        with pytest.raises(ValueError, match="must be a float"):
            coerce_float(True, field="hold_time")

    def test_non_numeric_string_rejected(self):
        with pytest.raises(ValueError, match="must be a float"):
            coerce_float("3s", field="hold_time")

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="must be a float"):
            coerce_float(None, field="hold_time")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_coerce.py::TestCoerceFloat -v`
Expected: FAIL with `ImportError: cannot import name 'coerce_float'`

- [ ] **Step 3: Implement `coerce_float`**

Append to `src/led_ticker/_coerce.py`:

```python
def coerce_float(value: object, *, field: str) -> tuple[float, CoercionWarning | None]:
    """Coerce string-of-number → float. Accept int passthrough.

    Rejects: bool, non-numeric strings, None.
    """
    if isinstance(value, bool):
        raise ValueError(
            f"{field} must be a float; got bool ({value!r}). "
            f"Use a number (e.g. {field} = 3.0)."
        )
    if isinstance(value, int):
        return float(value), None
    if isinstance(value, float):
        return value, None
    if isinstance(value, str):
        try:
            coerced = float(value)
        except ValueError:
            raise ValueError(
                f"{field} must be a float; got str ({value!r}). "
                f"Drop the quotes around the number (e.g. {field} = 3.0 "
                f"instead of {field} = \"3.0\")."
            ) from None
        return coerced, CoercionWarning(
            field=field,
            original=value,
            coerced=coerced,
            message=(
                f"{field} was a string ({value!r}); coerced to float {coerced}. "
                f"Drop the quotes around the number to silence this warning."
            ),
        )
    raise ValueError(
        f"{field} must be a float; got {type(value).__name__} ({value!r})."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_coerce.py -v`
Expected: PASS — 15 tests.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/_coerce.py tests/test_coerce.py
git commit -m "feat: add coerce_float helper for config load"
```

---

## Task 3: Coerce helpers — choice (closed-set enum)

**Files:**
- Modify: `src/led_ticker/_coerce.py`
- Test: `tests/test_coerce.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coerce.py`:

```python
from led_ticker._coerce import coerce_choice


class TestCoerceChoice:
    VALID = frozenset({"left", "right", "center"})

    def test_canonical_value_passthrough(self):
        value, warning = coerce_choice(
            "left", field="image_align", valid=self.VALID
        )
        assert value == "left"
        assert warning is None

    def test_uppercase_lowercases_with_warning(self):
        value, warning = coerce_choice(
            "Left", field="image_align", valid=self.VALID
        )
        assert value == "left"
        assert warning is not None
        assert warning.field == "image_align"
        assert warning.original == "Left"
        assert warning.coerced == "left"

    def test_whitespace_stripped(self):
        value, warning = coerce_choice(
            "  right  ", field="image_align", valid=self.VALID
        )
        assert value == "right"
        assert warning is not None

    def test_mixed_case_lowercases(self):
        value, warning = coerce_choice(
            "CENTER", field="image_align", valid=self.VALID
        )
        assert value == "center"
        assert warning is not None

    def test_unknown_value_after_normalize_rejected(self):
        with pytest.raises(ValueError, match="not a valid"):
            coerce_choice("Middle", field="image_align", valid=self.VALID)

    def test_unknown_value_passthrough_rejected(self):
        with pytest.raises(ValueError, match="not a valid"):
            coerce_choice("middle", field="image_align", valid=self.VALID)

    def test_non_string_rejected(self):
        with pytest.raises(ValueError, match="must be a string"):
            coerce_choice(42, field="image_align", valid=self.VALID)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_coerce.py::TestCoerceChoice -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `coerce_choice`**

Append to `src/led_ticker/_coerce.py`:

```python
def coerce_choice(
    value: object, *, field: str, valid: frozenset[str]
) -> tuple[str, CoercionWarning | None]:
    """Normalize a closed-set enum string (lowercase + strip).

    Raise ValueError if the input isn't a string, or if the normalized
    value still isn't in `valid`.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"{field} must be a string; got {type(value).__name__} "
            f"({value!r}). Expected one of {sorted(valid)}."
        )
    normalized = value.strip().lower()
    if normalized not in valid:
        raise ValueError(
            f"{field}={value!r} is not a valid choice; expected one of "
            f"{sorted(valid)}."
        )
    if normalized == value:
        return normalized, None
    return normalized, CoercionWarning(
        field=field,
        original=value,
        coerced=normalized,
        message=(
            f"{field} was {value!r}; coerced to {normalized!r}. Enum "
            f"values are case-insensitive but the canonical form is "
            f"lowercase — write {field} = {normalized!r} to silence "
            f"this warning."
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_coerce.py -v`
Expected: PASS — 22 tests.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/_coerce.py tests/test_coerce.py
git commit -m "feat: add coerce_choice helper for closed-set enums"
```

---

## Task 4: Wire `_coerce_warnings` into `AppConfig`

**Files:**
- Modify: `src/led_ticker/config.py`
- Test: `tests/test_config.py` (existing or new — check first)

- [ ] **Step 1: Check whether `tests/test_config.py` exists**

Run: `ls tests/test_config.py 2>/dev/null || echo "NOT FOUND"`

If NOT FOUND, the new tests go in `tests/test_config.py`. If FOUND, append to it.

- [ ] **Step 2: Write the failing test**

Add (or create) in `tests/test_config.py`:

```python
def test_load_config_collects_coerce_warnings(tmp_path):
    """AppConfig._coerce_warnings is a list; populated when load_config
    coerces a string-of-digits to int on a Section field."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[[playlist.section]]
mode = "swap"
hold_time = "3.0"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert hasattr(config, "_coerce_warnings")
    assert isinstance(config._coerce_warnings, list)
    # The actual coercion in load_config is Task 6 — for now the list
    # exists but may be empty. This test just asserts the field is wired.
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_config.py::test_load_config_collects_coerce_warnings -v`
Expected: FAIL with `AttributeError: 'AppConfig' object has no attribute '_coerce_warnings'`

- [ ] **Step 4: Add the field to `AppConfig`**

In `src/led_ticker/config.py`, at the top of the file with the other imports, add:

```python
from led_ticker._coerce import CoercionWarning
```

Modify the `AppConfig` dataclass (around line 130-140):

```python
@dataclass
class AppConfig:
    display: DisplayConfig
    sections: list[SectionConfig]
    title_delay: int = 5
    default_transition: TransitionConfig = field(
        default_factory=TransitionConfig,
    )
    between_sections: TransitionConfig = field(
        default_factory=TransitionConfig,
    )
    # Warnings collected during load_config when string-of-digits or
    # mixed-case enum values get coerced to canonical typed values.
    # validate.py surfaces these as rule-37 warnings; app.py:run() logs
    # them at startup. Empty list when no coercions fired.
    _coerce_warnings: list[CoercionWarning] = field(
        default_factory=list, repr=False, compare=False
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_config.py::test_load_config_collects_coerce_warnings -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/config.py tests/test_config.py
git commit -m "feat: add _coerce_warnings collector to AppConfig"
```

---

## Task 5: Coerce `DisplayConfig` numeric fields in `load_config`

**Files:**
- Modify: `src/led_ticker/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_load_config_coerces_display_brightness_string(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32
brightness = "60"

[[playlist.section]]
mode = "swap"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.display.brightness == 60
    assert isinstance(config.display.brightness, int)
    assert any(w.field == "display.brightness" for w in config._coerce_warnings)


def test_load_config_coerces_multiple_display_fields(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = "16"
cols = "32"
chain = "1"
brightness = "60"
gpio_slowdown = "3"

[[playlist.section]]
mode = "swap"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.display.rows == 16
    assert config.display.cols == 32
    assert config.display.chain == 1
    assert config.display.brightness == 60
    assert config.display.gpio_slowdown == 3
    # Five coercions, one warning per field.
    fields_warned = {w.field for w in config._coerce_warnings}
    assert fields_warned >= {
        "display.rows",
        "display.cols",
        "display.chain",
        "display.brightness",
        "display.gpio_slowdown",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_config.py::test_load_config_coerces_display_brightness_string -v`
Expected: FAIL — `brightness` is the literal string `"60"`, type check or numeric op blows up downstream.

- [ ] **Step 3: Implement display coercion in `load_config`**

In `src/led_ticker/config.py`, modify the `load_config` function. Replace the `display = DisplayConfig(...)` block (around lines 177-193) with a helper-based version. Add this helper near the top of the file (after the `TransitionConfig` dataclass, before `_parse_transition`):

```python
def _coerce_display(
    display_raw: dict[str, Any], warnings: list[CoercionWarning]
) -> DisplayConfig:
    """Build DisplayConfig from raw TOML, coercing string-of-digits → int
    on numeric fields. Warnings appended to `warnings`."""
    from led_ticker._coerce import coerce_int

    int_fields = (
        ("rows", 16),
        ("cols", 32),
        ("chain", 1),
        ("parallel", 1),
        ("default_scale", 1),
        ("brightness", 100),
        ("gpio_slowdown", 1),
        ("pwm_bits", 11),
        ("pwm_lsb_nanoseconds", 130),
        ("rp1_rio", 0),
    )
    kwargs: dict[str, Any] = {}
    for name, default in int_fields:
        if name in display_raw:
            value, warning = coerce_int(
                display_raw[name], field=f"display.{name}"
            )
            kwargs[name] = value
            if warning is not None:
                warnings.append(warning)
        else:
            kwargs[name] = default
    # String / bool fields don't need coercion at this stage.
    kwargs["pixel_mapper_config"] = display_raw.get("pixel_mapper_config", "")
    kwargs["hardware_mapping"] = display_raw.get("hardware_mapping", "adafruit-hat")
    kwargs["show_refresh_rate"] = display_raw.get("show_refresh_rate", False)
    kwargs["disable_hardware_pulsing"] = display_raw.get("disable_hardware_pulsing", False)
    return DisplayConfig(**kwargs)
```

Replace the existing `display = DisplayConfig(...)` block with:

```python
    coerce_warnings: list[CoercionWarning] = []
    display = _coerce_display(display_raw, coerce_warnings)
```

At the end of `load_config`, change the return to thread the warnings through:

```python
    return AppConfig(
        display=display,
        sections=sections,
        title_delay=raw.get("title", {}).get("delay", 5),
        default_transition=default_transition,
        between_sections=between_sections,
        _coerce_warnings=coerce_warnings,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Verify nothing else broke**

Run: `make test`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/config.py tests/test_config.py
git commit -m "feat: coerce DisplayConfig numeric fields in load_config"
```

---

## Task 6: Coerce `SectionConfig` + `TransitionConfig` fields in `load_config`

**Files:**
- Modify: `src/led_ticker/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_load_config_coerces_section_hold_time_string(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[[playlist.section]]
mode = "swap"
hold_time = "3.0"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.sections[0].hold_time == 3.0
    assert any(
        w.field == "section[0].hold_time" for w in config._coerce_warnings
    )


def test_load_config_coerces_section_content_height_string(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[[playlist.section]]
mode = "swap"
content_height = "16"
scale = "2"
loop_count = "3"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.sections[0].content_height == 16
    assert config.sections[0].scale == 2
    assert config.sections[0].loop_count == 3
    fields_warned = {w.field for w in config._coerce_warnings}
    assert "section[0].content_height" in fields_warned
    assert "section[0].scale" in fields_warned
    assert "section[0].loop_count" in fields_warned


def test_load_config_coerces_transition_easing_case(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[transitions]
default = "cut"
easing = "Linear"

[[playlist.section]]
mode = "swap"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.default_transition.easing == "linear"
    assert any(
        w.field == "transitions.easing" for w in config._coerce_warnings
    )


def test_load_config_unknown_easing_raises(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[transitions]
easing = "easeout"

[[playlist.section]]
mode = "swap"
""")
    from led_ticker.config import load_config

    with pytest.raises(ValueError, match="not a valid choice"):
        load_config(cfg)
```

Make sure `import pytest` is at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_config.py -v`
Expected: FAIL — hold_time is "3.0" string, never coerced.

- [ ] **Step 3: Add section coercion helper**

In `src/led_ticker/config.py`, add this helper after `_coerce_display`:

```python
def _coerce_section(
    section_raw: dict[str, Any],
    index: int,
    display: DisplayConfig,
    warnings: list[CoercionWarning],
) -> dict[str, Any]:
    """Coerce SectionConfig numeric fields. Returns a kwargs dict
    suitable for passing to SectionConfig(...). Bool-typed and
    free-text fields pass through unchanged."""
    from led_ticker._coerce import coerce_float, coerce_int

    prefix = f"section[{index}]"

    def _maybe_int(name: str, default: Any) -> Any:
        if name not in section_raw:
            return default
        value, warning = coerce_int(section_raw[name], field=f"{prefix}.{name}")
        if warning is not None:
            warnings.append(warning)
        return value

    def _maybe_float(name: str, default: Any) -> Any:
        if name not in section_raw:
            return default
        value, warning = coerce_float(section_raw[name], field=f"{prefix}.{name}")
        if warning is not None:
            warnings.append(warning)
        return value

    def _maybe_optional_int(name: str) -> int | None:
        if name not in section_raw:
            return None
        value, warning = coerce_int(section_raw[name], field=f"{prefix}.{name}")
        if warning is not None:
            warnings.append(warning)
        return value

    def _maybe_optional_float(name: str) -> float | None:
        if name not in section_raw:
            return None
        value, warning = coerce_float(section_raw[name], field=f"{prefix}.{name}")
        if warning is not None:
            warnings.append(warning)
        return value

    return {
        "loop_count": _maybe_int("loop_count", 1),
        "hold_time": _maybe_float("hold_time", 3.0),
        "scale": _maybe_int("scale", display.default_scale),
        "content_height": _maybe_int("content_height", 16),
        "scroll_step_ms": _maybe_optional_int("scroll_step_ms"),
        "start_hold": _maybe_optional_float("start_hold"),
        "separator_font_size": _maybe_optional_int("separator_font_size"),
    }
```

- [ ] **Step 4: Add transition easing coercion**

Add another helper:

```python
def _coerce_easing(
    raw: dict[str, Any], default_easing: str, prefix: str,
    warnings: list[CoercionWarning],
) -> str:
    """Coerce the `easing` value if present. Unknown values raise."""
    from led_ticker._coerce import coerce_choice
    from led_ticker.transitions import EASING

    if "easing" not in raw:
        return default_easing
    valid = frozenset(EASING.keys())
    value, warning = coerce_choice(
        raw["easing"], field=f"{prefix}.easing", valid=valid
    )
    if warning is not None:
        warnings.append(warning)
    return value
```

- [ ] **Step 5: Wire the helpers into `load_config`**

In `load_config`, replace the existing section-building block with calls to `_coerce_section`. The existing pattern around line 232 becomes:

```python
        section_kwargs = _coerce_section(
            section_raw, i, display, coerce_warnings
        )
        # Coerce transition easing on the section's transition override
        # if present. (Section-level easing inheritance is unchanged.)
        if "transition" in section_raw and isinstance(
            section_raw["transition"], dict
        ):
            trans.easing = _coerce_easing(
                section_raw["transition"],
                trans.easing,
                f"section[{i}].transition",
                coerce_warnings,
            )
        bg_color_raw = section_raw.get("bg_color")
        bg_color = tuple(bg_color_raw) if bg_color_raw is not None else None

        section = SectionConfig(
            mode=section_raw.get("mode", "forever_scroll"),
            title=section_raw.get("title"),
            widgets=section_raw.get("widget", []),
            transition=trans,
            transition_specified=transition_specified,
            hold_time_specified=("hold_time" in section_raw),
            continuous_scroll=section_raw.get("continuous_scroll", False),
            bg_color=bg_color,
            separator=section_raw.get("separator"),
            separator_font=section_raw.get("separator_font"),
            separator_color=section_raw.get("separator_color"),
            _raw=section_raw,
            **section_kwargs,
        )
        sections.append(section)
```

You'll need to wrap the section loop with `for i, section_raw in enumerate(...)` instead of just iterating — make sure `i` is bound.

Also coerce the top-level `[transitions]` easing — modify the `default_transition` construction:

```python
    default_transition = TransitionConfig(
        type=transitions_raw.get("default", "cut"),
        duration=transitions_raw.get("duration", 0.5),
        easing=_coerce_easing(
            transitions_raw, "linear", "transitions", coerce_warnings
        ),
        show_pikachu=transitions_raw.get("show_pikachu", True),
        show_pokeball=transitions_raw.get("show_pokeball", True),
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 7: Run full test suite to catch regressions**

Run: `make test`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/config.py tests/test_config.py
git commit -m "feat: coerce SectionConfig + TransitionConfig fields in load_config"
```

---

## Task 7: Coerce widget_cfg numeric fields in `_build_widget`

**Files:**
- Modify: `src/led_ticker/app.py`
- Test: `tests/test_app.py` (existing — append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py` (or wherever `_build_widget` tests live; check with `grep -l "_build_widget" tests/`):

```python
@pytest.mark.asyncio
async def test_build_widget_coerces_font_size_string(tmp_path):
    """font_size = "25" should coerce to int 25 and emit a warning, not
    crash with TypeError deep in resolve_font."""
    from led_ticker._coerce import CoercionWarning
    from led_ticker.app import _build_widget

    cfg = {
        "type": "message",
        "text": "hi",
        "font": "Inter-Bold",
        "font_size": "25",
    }
    warnings: list[CoercionWarning] = []
    widget = await _build_widget(
        cfg,
        session=None,
        config_dir=tmp_path,
        coercion_collector=warnings,
    )
    assert widget is not None
    assert any(w.field == "widget.font_size" for w in warnings)


@pytest.mark.asyncio
async def test_build_widget_coerces_font_threshold_string(tmp_path):
    from led_ticker._coerce import CoercionWarning
    from led_ticker.app import _build_widget

    cfg = {
        "type": "message",
        "text": "hi",
        "font": "Inter-Bold",
        "font_size": 25,
        "font_threshold": "80",
    }
    warnings: list[CoercionWarning] = []
    widget = await _build_widget(
        cfg,
        session=None,
        config_dir=tmp_path,
        coercion_collector=warnings,
    )
    assert widget is not None
    assert any(w.field == "widget.font_threshold" for w in warnings)


@pytest.mark.asyncio
async def test_build_widget_font_size_bool_still_rejected(tmp_path):
    """Bool stays a hard error (the existing rule 28 guard pattern)."""
    from led_ticker.app import _build_widget

    cfg = {
        "type": "message",
        "text": "hi",
        "font": "Inter-Bold",
        "font_size": True,
    }
    with pytest.raises(ValueError, match="must be an int"):
        await _build_widget(cfg, session=None, config_dir=tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_app.py -v -k coerce`
Expected: FAIL — `_build_widget` has no `coercion_collector` parameter; also the `font_size = "25"` test crashes with `TypeError` inside `resolve_font`.

- [ ] **Step 3: Add coercion to `_build_widget`**

In `src/led_ticker/app.py`, find the `_build_widget` signature (around line 540) and add the `coercion_collector` parameter:

```python
async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession | None,
    *,
    config_dir: Path,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
    validate_only: bool = False,
    coercion_collector: list[Any] | None = None,
) -> Any:
```

Right after the `widget_type = widget_cfg.pop("type")` line (around line 591), add the coercion pass. Define this helper at module scope (above `_build_widget`):

```python
# Numeric fields that flow through widget_cfg before reaching the
# widget constructor. The pop()-side fields (font_size, font_threshold,
# top_font_size, etc.) also pass through here so their type is fixed
# before resolve_font sees them.
_WIDGET_INT_FIELDS = frozenset({
    "font_size",
    "font_threshold",
    "top_font_size",
    "bottom_font_size",
    "top_font_threshold",
    "bottom_font_threshold",
    "top_row_height",
    "text_loops",
    "bottom_text_loops",
    "gif_loops",
    "padding",
    "scroll_speed_ms",
    "text_x_offset",
    "text_y_offset",
    "top_text_y_offset",
    "bottom_text_y_offset",
})

_WIDGET_FLOAT_FIELDS = frozenset({
    "hold_seconds",
})


def _coerce_widget_cfg(
    widget_cfg: dict[str, Any],
    collector: list[Any] | None,
) -> None:
    """In-place coerce of widget_cfg numeric fields. Bool stays a hard
    error so the existing bottom_text_loops / font_threshold guards
    continue to fire."""
    from led_ticker._coerce import coerce_float, coerce_int

    for name in list(widget_cfg.keys()):
        if name in _WIDGET_INT_FIELDS:
            value, warning = coerce_int(widget_cfg[name], field=f"widget.{name}")
            widget_cfg[name] = value
            if warning is not None and collector is not None:
                collector.append(warning)
        elif name in _WIDGET_FLOAT_FIELDS:
            value, warning = coerce_float(widget_cfg[name], field=f"widget.{name}")
            widget_cfg[name] = value
            if warning is not None and collector is not None:
                collector.append(warning)
```

Then call `_coerce_widget_cfg(widget_cfg, coercion_collector)` right after `widget_type = widget_cfg.pop("type")` (around line 591).

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_app.py -v -k coerce`
Expected: PASS.

- [ ] **Step 5: Run full suite to catch regressions**

Run: `make test`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "feat: coerce widget_cfg numeric fields in _build_widget"
```

---

## Task 8: Coerce widget_cfg enum fields in `_build_widget`

**Files:**
- Modify: `src/led_ticker/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:

```python
@pytest.mark.asyncio
async def test_build_widget_coerces_image_align_case(tmp_path):
    """image_align = 'Left' should coerce to 'left' and warn."""
    from led_ticker._coerce import CoercionWarning
    from led_ticker.app import _build_widget

    # Use a 1x1 PNG sitting in tmp_path
    from PIL import Image
    img_path = tmp_path / "tiny.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(img_path)

    cfg = {
        "type": "image",
        "path": "tiny.png",
        "image_align": "Left",
        "fit": "Letterbox",
    }
    warnings: list[CoercionWarning] = []
    widget = await _build_widget(
        cfg,
        session=None,
        config_dir=tmp_path,
        coercion_collector=warnings,
    )
    assert widget is not None
    fields_warned = {w.field for w in warnings}
    assert "widget.image_align" in fields_warned
    assert "widget.fit" in fields_warned


@pytest.mark.asyncio
async def test_build_widget_unknown_image_align_rejected(tmp_path):
    """'Middle' (after lowercase) still isn't a valid image_align."""
    from led_ticker.app import _build_widget
    from PIL import Image
    img_path = tmp_path / "tiny.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(img_path)

    cfg = {
        "type": "image",
        "path": "tiny.png",
        "image_align": "Middle",
    }
    with pytest.raises(ValueError, match="not a valid choice"):
        await _build_widget(cfg, session=None, config_dir=tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_app.py -v -k "image_align or fit_case"`
Expected: FAIL — `validate_choice` rejects `"Left"` because it's case-sensitive.

- [ ] **Step 3: Add enum-field coercion to `_build_widget`**

In `src/led_ticker/app.py`, extend `_coerce_widget_cfg` from Task 7 to handle enum fields. Add a registry of enum-typed widget fields:

```python
# Closed-set enum fields. Each maps to a frozenset of valid lowercase
# values. The widget's own validator (validate_choice in _image_fit /
# _image_base) will still run after coercion — this just normalizes
# case + whitespace upstream so the validator never sees "Left".
def _widget_enum_fields() -> dict[str, frozenset[str]]:
    from led_ticker.widgets._image_base import (
        VALID_SCROLL_DIRECTIONS,
        VALID_TEXT_ALIGNS,
        VALID_TEXT_VALIGNS,
    )
    from led_ticker.widgets._image_fit import VALID_FITS, VALID_IMAGE_ALIGNS

    return {
        "text_align": VALID_TEXT_ALIGNS,
        "text_valign": VALID_TEXT_VALIGNS,
        "image_align": VALID_IMAGE_ALIGNS,
        "scroll_direction": VALID_SCROLL_DIRECTIONS,
        "fit": VALID_FITS,
        "bottom_text_scroll": frozenset({"marquee", "scroll_through"}),
    }
```

Then extend `_coerce_widget_cfg`:

```python
def _coerce_widget_cfg(
    widget_cfg: dict[str, Any],
    collector: list[Any] | None,
) -> None:
    from led_ticker._coerce import coerce_choice, coerce_float, coerce_int

    enum_fields = _widget_enum_fields()
    for name in list(widget_cfg.keys()):
        if name in _WIDGET_INT_FIELDS:
            value, warning = coerce_int(widget_cfg[name], field=f"widget.{name}")
            widget_cfg[name] = value
            if warning is not None and collector is not None:
                collector.append(warning)
        elif name in _WIDGET_FLOAT_FIELDS:
            value, warning = coerce_float(widget_cfg[name], field=f"widget.{name}")
            widget_cfg[name] = value
            if warning is not None and collector is not None:
                collector.append(warning)
        elif name in enum_fields:
            value, warning = coerce_choice(
                widget_cfg[name],
                field=f"widget.{name}",
                valid=enum_fields[name],
            )
            widget_cfg[name] = value
            if warning is not None and collector is not None:
                collector.append(warning)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_app.py -v -k "image_align or fit_case"`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `make test`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "feat: coerce widget_cfg enum fields (case-insensitive)"
```

---

## Task 9: Tighten `EASING.get` fallback in `transitions/__init__.py`

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py`
- Test: `tests/test_transitions.py` (existing — append)

Note: Task 6 already coerced easing at config-load time. This task is a defense-in-depth tightening — if anything constructs a `TransitionConfig` programmatically (in tests, in `_parse_transition` for inline dict forms inside sections), an unknown easing should still surface clearly instead of silently falling back to `linear`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_transitions.py`:

```python
def test_run_transition_unknown_easing_raises():
    """Programmatic use with an unknown easing should fail loudly,
    not silently fall back to linear."""
    import asyncio
    from led_ticker.transitions import run_transition

    # Construct a minimal scenario that would normally just call
    # EASING.get; we want to assert the unknown value is rejected.
    with pytest.raises(KeyError, match="easeout"):
        # The simplest way to surface the easing lookup: pass through
        # a code path that resolves it. We can do this by calling the
        # helper that does the lookup directly if exported, otherwise
        # construct a minimal run_transition call with a fake transition.
        from led_ticker.transitions import _resolve_easing

        _resolve_easing("easeout")
```

Adjust the test if the new helper name differs from `_resolve_easing` — the assertion is that an unknown easing raises rather than silently returning `linear`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_transitions.py::test_run_transition_unknown_easing_raises -v`
Expected: FAIL — `_resolve_easing` doesn't exist OR the current code silently returns `linear`.

- [ ] **Step 3: Add `_resolve_easing` helper and replace the silent fallback**

In `src/led_ticker/transitions/__init__.py`, after the `EASING` dict definition, add:

```python
def _resolve_easing(easing: str) -> Callable[[float], float]:
    """Look up an easing function by name. Raises KeyError on unknown
    values (was a silent fallback to `linear` pre-coerce-and-warn —
    config-load now catches unknown values via coerce_choice, but
    programmatic callers still benefit from a loud failure)."""
    if easing not in EASING:
        raise KeyError(
            f"unknown easing {easing!r}; expected one of {sorted(EASING)}"
        )
    return EASING[easing]
```

Find the existing `ease_fn = EASING.get(easing, linear)` line (around line 157) and replace with:

```python
    ease_fn = _resolve_easing(easing)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_transitions.py::test_run_transition_unknown_easing_raises -v`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `make test`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/transitions/__init__.py tests/test_transitions.py
git commit -m "feat: replace silent easing fallback with explicit error"
```

---

## Task 10: Surface coerce warnings in `led-ticker validate`

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py` (existing — append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validate.py`:

```python
@pytest.mark.asyncio
async def test_validate_surfaces_coerced_font_size_as_warning(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 64
cols = 256
default_scale = 4

[[playlist.section]]
mode = "swap"
content_height = 16
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "hi"
font = "Inter-Bold"
font_size = "25"
""")
    from led_ticker.validate import validate_config

    result = await validate_config(cfg)
    assert result.valid  # warnings don't fail validation
    assert len(result.errors) == 0
    assert any(
        w.rule == 37 and "font_size" in w.message
        for w in result.warnings
    )


@pytest.mark.asyncio
async def test_validate_surfaces_image_align_case_as_warning(tmp_path):
    # Create a tiny PNG so the image widget validates
    from PIL import Image
    img_path = tmp_path / "tiny.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(img_path)

    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 64
cols = 256
default_scale = 4

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "image"
path = "tiny.png"
image_align = "Left"
""")
    from led_ticker.validate import validate_config

    result = await validate_config(cfg)
    assert result.valid
    assert any(
        w.rule == 37 and "image_align" in w.message
        for w in result.warnings
    )


@pytest.mark.asyncio
async def test_validate_font_size_true_still_errors(tmp_path):
    """Bool is still a hard error — the rule-28 / rule-10 pattern."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 64
cols = 256
default_scale = 4

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
font = "Inter-Bold"
font_size = true
""")
    from led_ticker.validate import validate_config

    result = await validate_config(cfg)
    assert not result.valid
    assert any("must be an int" in e.message for e in result.errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_validate.py -v -k "coerce or align_case or font_size_true"`
Expected: FAIL — no rule 37 yet; coerced widget_cfg warnings not surfaced.

- [ ] **Step 3: Thread coercion collector through `_run_build_checks`**

In `src/led_ticker/validate.py`, modify `_run_build_checks` (around line 86) to collect coerce warnings per widget:

```python
async def _run_build_checks(
    sections: list[SectionConfig], config_dir: Path,
) -> tuple[list[tuple[str, str]], list[Any]]:
    """Run _build_widget(validate_only=True) for every widget.

    Returns (build_errors, coerce_warnings):
    - build_errors: (location, error_msg) pairs
    - coerce_warnings: CoercionWarning objects collected from
      _build_widget's coercion pass for each widget.
    """
    from led_ticker.app import _build_widget

    issues: list[tuple[str, str]] = []
    warnings: list[Any] = []
    for i, section in enumerate(sections):
        for j, widget_cfg in enumerate(section.widgets):
            widget_warnings: list[Any] = []
            try:
                await _build_widget(
                    copy.deepcopy(widget_cfg),
                    session=None,
                    config_dir=config_dir,
                    validate_only=True,
                    coercion_collector=widget_warnings,
                )
            except Exception as e:
                issues.append((f"section[{i}].widget[{j}]", str(e)))
            # Annotate each warning with its widget location so the
            # validator can surface it under the right section[i].widget[j].
            for w in widget_warnings:
                warnings.append((f"section[{i}].widget[{j}]", w))
    return issues, warnings
```

- [ ] **Step 4: Add `_check_coercions` to surface warnings as rule 37**

In `src/led_ticker/validate.py`, modify `validate_config` (around line 1103). After `_run_build_checks`, add:

```python
    # Phase 1c (cont.): rule 37 — coerce warnings from load_config
    # (section/display/transition fields) and from _build_widget
    # (widget_cfg fields). Both surface as warnings so the user knows
    # which fields had non-canonical values.
    for w in config._coerce_warnings:
        warnings.append(
            ValidationIssue(
                rule=37,
                location=w.field,
                severity="warning",
                message=w.message,
                fix=f"Update {w.field} to {w.coerced!r} (or the canonical typed form).",
            )
        )
```

And replace the existing `build_errors = await _run_build_checks(...)` line with:

```python
    build_errors, build_warnings = await _run_build_checks(
        config.sections, path.parent,
    )
    for location, w in build_warnings:
        warnings.append(
            ValidationIssue(
                rule=37,
                location=f"{location}.{w.field}",
                severity="warning",
                message=w.message,
                fix=f"Update {w.field} to {w.coerced!r} (or the canonical typed form).",
            )
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_validate.py -v -k "coerce or align_case or font_size_true"`
Expected: PASS.

- [ ] **Step 6: Run full suite**

Run: `make test`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: surface coerce warnings as rule-37 in led-ticker validate"
```

---

## Task 11: Log coerce warnings at runtime startup

**Files:**
- Modify: `src/led_ticker/app.py`
- Create: `tests/test_app_runtime_warnings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_app_runtime_warnings.py`:

```python
"""Verify runtime startup logs coerce warnings (without needing real hardware)."""

import logging

import pytest


def test_load_config_warnings_logged_at_startup(tmp_path, caplog):
    """The list of CoercionWarning collected by load_config should be
    logged via logging.warning() so users see the same message in their
    journal that they'd see from `led-ticker validate`."""
    from led_ticker.app import _log_coerce_warnings
    from led_ticker.config import load_config

    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32
brightness = "60"

[[playlist.section]]
mode = "swap"
hold_time = "3.0"
""")

    config = load_config(cfg)
    with caplog.at_level(logging.WARNING):
        _log_coerce_warnings(config)
    messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("brightness" in m for m in messages)
    assert any("hold_time" in m for m in messages)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_app_runtime_warnings.py -v`
Expected: FAIL — `_log_coerce_warnings` doesn't exist.

- [ ] **Step 3: Add `_log_coerce_warnings` helper and call from `run()`**

In `src/led_ticker/app.py`, add a helper near the other private helpers:

```python
def _log_coerce_warnings(config: Any) -> None:
    """Emit one logging.warning per CoercionWarning collected during
    load_config. Mirrors the messages surfaced by `led-ticker validate`
    so users who run the binary directly still see the same fixes."""
    for w in getattr(config, "_coerce_warnings", []):
        logging.warning("config coerce: %s", w.message)
```

Find `run()` and add `_log_coerce_warnings(config)` right after `config = load_config(args.config)` (or wherever `load_config` is called). Also call it after each `_build_widget` pass that collected its own warnings — for runtime, the simplest approach is to pass a single shared collector list:

```python
        runtime_coerce: list[Any] = []
        # ... in the widget-build loop:
        widget = await _build_widget(
            cfg,
            session,
            config_dir=config_path.parent,
            default_bg_color=section.bg_color,
            panel_h_for_warning=panel_h_for_warning,
            coercion_collector=runtime_coerce,
        )
        # After each section finishes building, drain the collector:
        for w in runtime_coerce:
            logging.warning("config coerce: %s", w.message)
        runtime_coerce.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_app_runtime_warnings.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `make test`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app.py tests/test_app_runtime_warnings.py
git commit -m "feat: log coerce warnings at runtime startup"
```

---

## Task 12: Reproduce the original bug as a regression test

**Files:**
- Modify: `tests/test_validate.py`

This is the user's exact crash from the original bug report. Adding it as a regression test ensures no future change re-introduces it.

- [ ] **Step 1: Write the failing test (it should already pass post-Task 10, but add as explicit tripwire)**

Append to `tests/test_validate.py`:

```python
@pytest.mark.asyncio
async def test_original_bug_font_size_string_no_typeerror(tmp_path):
    """Regression: font_size = "25" on a hires font used to crash with
    `TypeError: '<' not supported between instances of 'str' and 'int'`
    deep in resolve_font. After coerce-and-warn, it's a warning."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 64
cols = 256
default_scale = 4

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 30.0

[[playlist.section.widget]]
type = "gif"
path = "missing.gif"
fit = "letterbox"
image_align = "center"
text = "Moon         Bunny"
font = "Inter-Bold"
font_size = "25"
""")
    from led_ticker.validate import validate_config

    result = await validate_config(cfg)
    # The gif file doesn't exist, so we'll have an error about that —
    # but it must NOT be the TypeError about str < int.
    type_errors = [e for e in result.errors if "'<' not supported" in e.message]
    assert type_errors == []
    # And the coerce warning IS surfaced.
    coerce = [w for w in result.warnings if "font_size" in w.message]
    assert len(coerce) >= 1
```

- [ ] **Step 2: Run test to verify it passes**

Run: `PYTHONPATH=tests/stubs python -m pytest tests/test_validate.py::test_original_bug_font_size_string_no_typeerror -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_validate.py
git commit -m "test: regression for font_size string TypeError"
```

---

## Task 13: Update docs site config-options.mdx

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`

- [ ] **Step 1: Find the file**

Run: `ls docs/site/src/content/docs/reference/config-options.mdx`
Expected: file exists.

- [ ] **Step 2: Read the existing structure**

Run: `head -50 docs/site/src/content/docs/reference/config-options.mdx`

- [ ] **Step 3: Add a "Coercion behavior" section near the top**

Insert (after the existing intro / overview, before the field reference tables) the following section:

```mdx
## Coercion behavior

Some config slips that would crash startup are silently corrected with a warning. The warning shows up in `led-ticker validate` output and in the runtime log — fix the source to silence them.

**Numeric strings → numbers.** Every integer or float field accepts a string-of-digits in addition to a bare number. Both forms work, but the unquoted form is canonical:

```toml
font_size = "25"   # works (coerced to 25, warns)
font_size = 25     # canonical, no warning
```

This applies to `font_size`, `font_threshold`, `hold_time`, `brightness`, `content_height`, and every other numeric field.

**Closed-set enum strings → case-insensitive.** Fields with a fixed value set (`text_align`, `text_valign`, `image_align`, `scroll_direction`, `fit`, `bottom_text_scroll`, `easing`) are case-insensitive. The canonical form is lowercase:

```toml
image_align = "Left"   # works (coerced to "left", warns)
image_align = "left"   # canonical, no warning
```

**What's NOT coerced.** Colors (`[r, g, b]`), booleans, file paths, and free-text fields stay strict — typos here surface as hard errors rather than silent fixes. The `style` keys inside inline-table providers (`font_color = {style="rainbow", ...}`) also stay case-sensitive.
```

- [ ] **Step 4: Commit**

```bash
git add docs/site/src/content/docs/reference/config-options.mdx
git commit -m "docs: document coerce-and-warn behavior"
```

---

## Task 14: Run full verification suite + open PR

- [ ] **Step 1: Run the full test suite**

Run: `make test`
Expected: All tests pass. Note the test count — should be higher than the pre-change baseline by ~30+ tests.

- [ ] **Step 2: Run lint**

Run: `make lint`
Expected: Clean (no ruff complaints).

- [ ] **Step 3: Run format**

Run: `make format`
Expected: Clean (no changes needed; if files were rewritten, commit the formatting).

If files were reformatted, commit:
```bash
git add -A
git commit -m "chore: ruff format"
```

- [ ] **Step 4: Push the branch**

Run: `git push -u origin config-coerce-and-warn`
Expected: branch pushed to GitHub.

- [ ] **Step 5: Open the PR**

Run:
```bash
gh pr create --title "feat: config coerce-and-warn for numeric/enum slips" --body "$(cat <<'EOF'
## Summary
- Adds a coerce-and-warn pass at config load: `font_size = "25"` and `image_align = "Left"` are silently fixed to canonical values, with a warning surfaced via `led-ticker validate` and runtime logs.
- New `_coerce.py` module with three pure helpers (`coerce_int`, `coerce_float`, `coerce_choice`).
- Bool is still rejected as a hard error on numeric fields (preserves the rule-28 / rule-10 guards).
- `easing` silently-fallback-to-linear path is now an explicit error (defensive depth — config-load also coerces case).

Spec: `docs/superpowers/specs/2026-05-19-config-coerce-and-warn-design.md`
Plan: `docs/superpowers/plans/2026-05-19-config-coerce-and-warn.md`

## Test plan
- [ ] `make test` passes (added ~30 new tests across `test_coerce.py`, `test_config.py`, `test_validate.py`, `test_app.py`, `test_app_runtime_warnings.py`)
- [ ] `make lint` clean
- [ ] Manual: load a config with `font_size = "25"` — verify `led-ticker validate` shows a rule-37 warning and runtime startup logs the same message
- [ ] Manual: load a config with `image_align = "Left"` — same
- [ ] Manual: load a config with `font_color = "255,0,0"` — verify it's still a hard error (not coerced)
- [ ] Manual: load a config with `font_size = true` — verify still hard error

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL printed.

- [ ] **Step 6: Return the PR URL**

Report the PR URL to the user.

---

## Self-review notes

**Spec coverage check:**
- ✅ Numeric strings → number: Tasks 5, 6, 7
- ✅ Closed-set enum strings → lowercased: Tasks 6, 8
- ✅ `easing` silent fallback fix: Task 9
- ✅ Bool rejection preserved: Tasks 1, 7, 10 (test asserts)
- ✅ Validate output: Task 10
- ✅ Runtime log: Task 11
- ✅ Docs update: Task 13
- ✅ Regression test for original bug: Task 12

**Type consistency:**
- `CoercionWarning` is defined in Task 1, used in Tasks 4, 5, 6, 7, 8, 10, 11.
- `coercion_collector: list[Any]` parameter signature is consistent across `_build_widget` calls (Tasks 7, 8, 10, 11).
- `AppConfig._coerce_warnings` populated in load_config (Tasks 5, 6), read by validate (Task 10) and runtime (Task 11).

**Placeholder scan:** No TBDs, no "implement appropriate error handling" — every code block is complete.

**Out of scope (per spec):**
- Enum-validating `mode` (separate follow-up)
- "Strict mode" flag for CI (separate follow-up)
- Coercing inline-table `style` values (separate follow-up)

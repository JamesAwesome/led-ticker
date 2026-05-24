# Batch 5: Allowlist + Schema Export

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Critical #1 (unknown widget kwargs bypass `validate` and crash at startup as raw `TypeError`) and add `led-ticker validate --list-fields TYPE` to eliminate the memorize-or-grep tax on widget field discovery.

**Architecture:** Task 1 adds a per-widget allowlist check in `_build_widget` using `cls.__attrs_attrs__`, with `difflib.get_close_matches` for did-you-mean suggestions; the check fires at both validate-time and runtime. Task 2 reuses the same `cls.__attrs_attrs__` mechanism to build a human-readable field listing and exposes it via a new `--list-fields TYPE` argument on the `validate` subcommand.

**Tech Stack:** Python standard library (`difflib`, `attrs`), `pytest`, `pytest-asyncio` (already configured with `asyncio_mode = "auto"`)

---

## File map

| File | Change |
|------|--------|
| `src/led_ticker/app.py` | Add `import difflib`; add allowlist check in `_build_widget`; add `_list_widget_fields` helper; add `--list-fields` to `validate` CLI |
| `src/led_ticker/validate.py` | Add `_ERROR_PATTERNS` entry for rule 38 (unknown kwarg) |
| `tests/test_app.py` | Add `TestUnknownKwargAllowlist` (Task 1) and `TestListWidgetFields` (Task 2) |
| `tests/test_validate.py` | Add `TestUnknownKwargValidationRule` to verify rule 38 surfaces via `validate_config` |

---

## Context for all tasks

**The project uses `asyncio_mode = "auto"` in `pyproject.toml`**, so `async def test_*` methods run automatically without an explicit `@pytest.mark.asyncio` decorator. However the existing tests in `TestFontSizeMigration` DO use `@pytest.mark.asyncio` — follow that pattern for consistency.

**`_build_widget` signature:**
```python
async def _build_widget(
    widget_cfg: dict[str, Any],
    session: aiohttp.ClientSession,  # may be None when validate_only=True
    config_dir: Path | None = None,
    default_bg_color: tuple[int, int, int] | None = None,
    panel_h_for_warning: int | None = None,
    validate_only: bool = False,
    coercion_collector: list[Any] | None = None,
) -> Any:
```

**Current structure of `_build_widget` (relevant region):**

```python
# line 881
_coerce_widget_colors(widget_cfg)

# ← Task 1 inserts the allowlist check HERE

# line 883
if validate_only:
    return None

# line 886
if hasattr(cls, "start"):
    widget = await cls.start(session=session, **widget_cfg)
else:
    widget = cls(**widget_cfg)
```

**By the point of insertion**, all dispatch-level keys have been popped from `widget_cfg`:
- `type` → popped at line 694
- `animation` → popped then re-added as coerced object (or gone if None)
- `border` → popped then re-added as coerced object (or gone if None)
- `font` → popped then re-added as resolved Font object (or gone if font_name was None)
- `font_size` → popped; re-added only for gif/image widgets that have `font_size` in attrs
- `font_threshold`, `top_font_size`, `top_font_threshold`, `bottom_font_size`, `bottom_font_threshold` → popped, NOT re-added
- `text_wrap`, `text_separator`, `text_separator_color` → popped for non-gif/image widgets
- `bottom_text_wrap`, `bottom_text_separator`, `bottom_text_separator_color` → popped for non-gif/image/two_row widgets
- `top_font`, `bottom_font` → popped then re-added as resolved Font objects (or gone if not provided)
- `text` → renamed to `message` (or dropped if `message` also present) for widgets without a `text` attr

The remaining keys are exactly what `cls(**widget_cfg)` receives — compare these against `cls_init_fields`.

**`cls_fields` already exists at line 852** but includes ALL attrs fields (including `init=False`). Create a separate `cls_init_fields` for the allowlist that filters to `init=True` only.

---

## Task 1: Unknown-kwarg allowlist with did-you-mean

**Files:**
- Modify: `src/led_ticker/app.py`
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_app.py`
- Test: `tests/test_validate.py`

- [ ] **Step 1: Write failing tests**

Add a new test class to `tests/test_app.py` (near `TestFontSizeMigration` around line 825):

```python
class TestUnknownKwargAllowlist:
    """_build_widget raises a clear ValueError (not TypeError) for unknown
    widget fields, surfacing at validate-time instead of startup."""

    @pytest.mark.asyncio
    async def test_typo_field_raises_value_error(self):
        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "text_color": [255, 0, 0]}
        with pytest.raises(ValueError, match="got unknown field"):
            await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_did_you_mean_suggestion_included(self):
        """font_clor → suggests font_color via difflib."""
        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "font_clor": [255, 0, 0]}
        with pytest.raises(ValueError, match="did you mean 'font_color'"):
            await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_no_suggestion_for_random_garbage(self):
        """Completely unlike any field → error still raised, no suggestion."""
        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "xyz_not_a_field": 1}
        with pytest.raises(ValueError, match="got unknown field"):
            await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_multiple_unknown_fields_all_reported(self):
        """Both bad keys appear in the error message."""
        from led_ticker.app import _build_widget

        cfg = {
            "type": "message",
            "text": "hi",
            "text_color": [255, 0, 0],
            "alignement": "left",
        }
        with pytest.raises(ValueError, match="got unknown fields"):
            await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_valid_fields_do_not_raise(self):
        """Sanity check: a well-formed message config passes the allowlist."""
        from led_ticker.app import _build_widget

        cfg = {
            "type": "message",
            "text": "hello",
            "font_color": [255, 255, 255],
            "center": True,
            "padding": 4,
        }
        # Should not raise
        result = await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]
        assert result is None  # validate_only=True returns None on success

    @pytest.mark.asyncio
    async def test_fires_at_runtime_not_only_validate(self):
        """The check runs even when validate_only=False (before cls(**widget_cfg))."""
        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "text_color": [255, 0, 0]}
        # validate_only=False → still raises ValueError, not TypeError from attrs
        with pytest.raises(ValueError, match="got unknown field"):
            await _build_widget(cfg, session=None, validate_only=False)  # type: ignore[arg-type]
```

Add to `tests/test_validate.py` (near `TestMigrationError`):

```python
class TestUnknownKwargValidationRule:
    """Unknown widget kwargs surface as rule-38 errors in ValidationResult."""

    @pytest.mark.asyncio
    async def test_unknown_kwarg_surfaces_as_validation_error(self, tmp_path):
        """text_color (typo for font_color) → rule=38 error in ValidationResult."""
        import tomllib

        from led_ticker.validate import validate_config

        toml_text = """
[display]
rows = 16
cols = 160
hardware_mapping = "adafruit-hat"
gpio_slowdown = 2

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
text_color = [255, 0, 0]
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path)

        assert not result.valid
        rule_38_errors = [e for e in result.errors if e.rule == 38]
        assert len(rule_38_errors) == 1
        assert "text_color" in rule_38_errors[0].message
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
.venv/bin/pytest tests/test_app.py::TestUnknownKwargAllowlist tests/test_validate.py::TestUnknownKwargValidationRule -v 2>&1 | tail -20
```

Expected: All tests fail with `Failed: DID NOT RAISE` (the check doesn't exist yet).

- [ ] **Step 3: Add `import difflib` to `app.py` module-level imports**

Open `src/led_ticker/app.py`. The current imports block starts at line 1:

```python
import argparse
import asyncio
import itertools
import logging
import sys
```

Add `import difflib` in alphabetical order (before `import itertools`):

```python
import argparse
import asyncio
import difflib
import itertools
import logging
import sys
```

- [ ] **Step 4: Add the allowlist check to `_build_widget`**

In `src/led_ticker/app.py`, after `_coerce_widget_colors(widget_cfg)` (line 881) and before `if validate_only:` (line 883), insert:

```python
    # Dispatch-level keys were all popped above; remaining keys are splatted
    # directly into cls(**widget_cfg). Any key not in attrs __init__ raises
    # a raw TypeError from attrs — catch it here with a usable message.
    cls_init_fields = {
        a.name for a in getattr(cls, "__attrs_attrs__", ()) if a.init is not False
    }
    unknown = set(widget_cfg.keys()) - cls_init_fields
    if unknown:
        suggestions = []
        for key in sorted(unknown):
            matches = difflib.get_close_matches(
                key, sorted(cls_init_fields), n=1, cutoff=0.6
            )
            hint = f" (did you mean {matches[0]!r}?)" if matches else ""
            suggestions.append(f"{key!r}{hint}")
        raise ValueError(
            f"widget type={widget_type!r} got unknown "
            f"{'field' if len(unknown) == 1 else 'fields'}: "
            + ", ".join(suggestions)
        )
```

The full context after the edit (lines 881–895 approximately):

```python
    _coerce_widget_colors(widget_cfg)

    # Dispatch-level keys were all popped above; remaining keys are splatted
    # directly into cls(**widget_cfg). Any key not in attrs __init__ raises
    # a raw TypeError from attrs — catch it here with a usable message.
    cls_init_fields = {
        a.name for a in getattr(cls, "__attrs_attrs__", ()) if a.init is not False
    }
    unknown = set(widget_cfg.keys()) - cls_init_fields
    if unknown:
        suggestions = []
        for key in sorted(unknown):
            matches = difflib.get_close_matches(
                key, sorted(cls_init_fields), n=1, cutoff=0.6
            )
            hint = f" (did you mean {matches[0]!r}?)" if matches else ""
            suggestions.append(f"{key!r}{hint}")
        raise ValueError(
            f"widget type={widget_type!r} got unknown "
            f"{'field' if len(unknown) == 1 else 'fields'}: "
            + ", ".join(suggestions)
        )

    if validate_only:
        return None

    if hasattr(cls, "start"):
        widget = await cls.start(session=session, **widget_cfg)
    else:
        widget = cls(**widget_cfg)

    return widget
```

- [ ] **Step 5: Add rule 38 to `_ERROR_PATTERNS` in `validate.py`**

In `src/led_ticker/validate.py`, find `_ERROR_PATTERNS` (around line 50). Add a new entry at the end of the list:

```python
_ERROR_PATTERNS: list[tuple[str, int | None, str]] = [
    (
        "animation is only valid on",
        12,
        (
            "Remove animation from this widget type;"
            " valid on message, countdown, gif, image"
        ),
    ),
    (
        "border is only valid on",
        15,
        (
            "Remove border from this widget type;"
            " valid on message, countdown, two_row, gif, image"
        ),
    ),
    (
        "requires font_size",
        5,
        "Add font_size = <pixels> next to font (e.g. font_size = 24 on bigsign)",
    ),
    (
        "font_threshold",
        10,
        "Use an integer 0–255 for font_threshold (not float, string, or bool)",
    ),
    (
        "got unknown field",
        38,
        (
            "Remove or rename the field. "
            "Run `led-ticker validate --list-fields TYPE` to see valid fields."
        ),
    ),
]
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/test_app.py::TestUnknownKwargAllowlist tests/test_validate.py::TestUnknownKwargValidationRule -v 2>&1 | tail -20
```

Expected: All tests pass.

- [ ] **Step 7: Run the full test suite to check for regressions**

```bash
.venv/bin/pytest --tb=short -q 2>&1 | tail -30
```

Expected: All existing tests pass. If any test breaks, it likely tested a widget config that now has an unknown field (fix the config dict in the test to use the correct field name, or verify the field IS in the widget's attrs).

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/app.py src/led_ticker/validate.py \
        tests/test_app.py tests/test_validate.py
git commit -m "feat: per-widget unknown-kwarg allowlist with did-you-mean (fixes Critical #1)

_build_widget now compares remaining widget_cfg keys against cls.__attrs_attrs__
after all dispatch-level pops. Unknown keys raise ValueError with difflib
get_close_matches suggestions instead of crashing at startup as a raw TypeError.
Surfaces as rule-38 ValidationIssue via validate_config.

Fixes: text_color (typo for font_color) now caught at validate time."
```

---

## Task 2: `led-ticker validate --list-fields TYPE`

**Files:**
- Modify: `src/led_ticker/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing tests**

Add a new test class to `tests/test_app.py` (after `TestUnknownKwargAllowlist`):

```python
class TestListWidgetFields:
    """_list_widget_fields returns a formatted string for a valid widget type."""

    def test_returns_str_for_message(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_attrs_field_names(self):
        """Known TickerMessage attrs fields appear in the output."""
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "message" in result
        assert "font_color" in result
        assert "padding" in result

    def test_contains_dispatch_field_names(self):
        """Dispatch-level fields (font, animation) appear in the output."""
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "font" in result
        assert "animation" in result
        assert "type" in result

    def test_unknown_type_raises_value_error(self):
        """An unknown widget type raises ValueError."""
        from led_ticker.app import _list_widget_fields

        with pytest.raises(ValueError, match="Unknown widget type"):
            _list_widget_fields("nonexistent_widget")

    def test_unknown_type_includes_did_you_mean(self):
        """A close mis-spelling includes a suggestion."""
        from led_ticker.app import _list_widget_fields

        with pytest.raises(ValueError, match="Did you mean"):
            _list_widget_fields("mesage")

    def test_two_row_fields_included(self):
        """two_row widget shows its specific fields."""
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("two_row")
        assert "top_text" in result
        assert "bottom_text" in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/test_app.py::TestListWidgetFields -v 2>&1 | tail -15
```

Expected: All tests fail with `ImportError: cannot import name '_list_widget_fields'`.

- [ ] **Step 3: Add `_list_widget_fields` to `app.py`**

Add the function to `src/led_ticker/app.py`, just before `def main()` (around line 1311). The dispatch-level fields listed are the ones `_build_widget` pops before the allowlist check:

```python
def _list_widget_fields(widget_type: str) -> str:
    """Return a human-readable field listing for widget_type.

    Prints dispatch-level fields (_build_widget pops these) and the
    widget's init-able attrs fields with types and defaults.
    """
    import difflib as _difflib

    import attrs as _attrs

    from led_ticker.widgets import _WIDGET_REGISTRY

    if widget_type not in _WIDGET_REGISTRY:
        candidates = sorted(_WIDGET_REGISTRY.keys())
        matches = _difflib.get_close_matches(widget_type, candidates, n=3, cutoff=0.6)
        hint = f"\nDid you mean: {', '.join(repr(m) for m in matches)}" if matches else ""
        raise ValueError(
            f"Unknown widget type: {widget_type!r}. "
            f"Available: {candidates}{hint}"
        )

    cls = _WIDGET_REGISTRY[widget_type]
    lines: list[str] = [f'Fields for type="{widget_type}":', ""]

    # Widget-specific attrs fields (init=True only)
    init_attrs = [
        a for a in getattr(cls, "__attrs_attrs__", ()) if a.init is not False
    ]
    if init_attrs:
        lines.append("Widget-level fields:")
        for a in init_attrs:
            if a.type is None:
                type_str = ""
            elif isinstance(a.type, str):
                type_str = a.type
            else:
                type_str = getattr(a.type, "__name__", str(a.type))

            if a.default is _attrs.NOTHING:
                default_str = "(required)"
            elif isinstance(a.default, _attrs.Factory):  # type: ignore[arg-type]
                default_str = "default: <computed>"
            else:
                default_str = f"default: {a.default!r}"

            lines.append(f"  {a.name:<30}  {type_str:<35}  {default_str}")
        lines.append("")

    # Dispatch-level fields that _build_widget handles (popped before allowlist)
    lines.append("Dispatch-level fields (shared; _build_widget handles these):")
    dispatch: list[tuple[str, str]] = [
        ("type", "required; widget type name (e.g. 'message', 'gif')"),
        ("text", "alias → widget's primary text field"),
        ("font", "BDF alias or hi-res font name"),
        ("font_size", "pixel height; required for hi-res fonts"),
        ("font_threshold", "int 0–255; default 128"),
        ("animation", "e.g. 'typewriter'; valid on message/gif/image only"),
        ("border", "{style='...',...}; valid on message/countdown/two_row/gif/image"),
        ("text_wrap", "bool; valid on gif/image only"),
        ("text_separator", "str; valid on gif/image only"),
        ("text_separator_color", "color; valid on gif/image only"),
        ("bottom_text_wrap", "bool; valid on gif/image/two_row"),
        ("bottom_text_separator", "str; valid on gif/image/two_row"),
        ("bottom_text_separator_color", "color; valid on gif/image/two_row"),
        ("top_font", "font name; valid on two_row"),
        ("top_font_size", "pixel height; valid on two_row"),
        ("top_font_threshold", "int 0–255; valid on two_row"),
        ("bottom_font", "font name; valid on two_row"),
        ("bottom_font_size", "pixel height; valid on two_row"),
        ("bottom_font_threshold", "int 0–255; valid on two_row"),
    ]
    for name, desc in dispatch:
        lines.append(f"  {name:<30}  {desc}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to confirm `_list_widget_fields` tests pass**

```bash
.venv/bin/pytest tests/test_app.py::TestListWidgetFields -v 2>&1 | tail -15
```

Expected: All 6 tests pass.

- [ ] **Step 5: Wire `--list-fields` into the CLI**

In `src/led_ticker/app.py`, find `def main()` (around line 1311). The current `validate` subparser looks like:

```python
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
```

Replace the entire `val_parser` block (from `val_parser = subparsers.add_parser(` through the closing `)`  of the `--json` add_argument call) with:

```python
    val_parser = subparsers.add_parser(
        "validate",
        help="Validate a config file without running the display",
    )
    val_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=None,
        help="Path to TOML config file (required unless --list-fields is given)",
    )
    val_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit JSON output",
    )
    val_parser.add_argument(
        "--list-fields",
        metavar="TYPE",
        dest="list_fields",
        default=None,
        help=(
            "Print all valid fields for a widget type and exit "
            "(e.g. --list-fields message)"
        ),
    )
```

Then find the `if args.command == "validate":` block (around line 1342) and update it to handle `--list-fields` first:

```python
    if args.command == "validate":
        if args.list_fields is not None:
            try:
                print(_list_widget_fields(args.list_fields))
            except ValueError as e:
                print(str(e), file=sys.stderr)
                sys.exit(2)
            sys.exit(0)

        if args.path is None:
            val_parser.print_usage(sys.stderr)
            print(
                "error: path is required when --list-fields is not given",
                file=sys.stderr,
            )
            sys.exit(2)

        from led_ticker.validate import (  # noqa: PLC0415
            _format_human,
            _format_json,
            validate_config,
        )

        try:
            result = asyncio.run(validate_config(args.path))
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)

        if args.json_output:
            print(_format_json(result))
        else:
            print(_format_human(result))

        sys.exit(0 if result.valid else 1)
```

- [ ] **Step 6: Run the full test suite**

```bash
.venv/bin/pytest --tb=short -q 2>&1 | tail -20
```

Expected: All tests pass. The `--list-fields` path is not directly tested via the CLI (that would require subprocess), but `_list_widget_fields` is tested directly and that's the substance.

- [ ] **Step 7: Smoke-test the CLI by hand**

```bash
.venv/bin/led-ticker validate --list-fields message 2>&1 | head -30
```

Expected output (approximate — exact field names match `TickerMessage.__attrs_attrs__`):

```
Fields for type="message":

Widget-level fields:
  message                           str                                  (required)
  font                              Font                                 default: <computed>
  font_color                        Color | ColorProvider                default: <computed>
  bg_color                          Color | None                         default: None
  center                            bool                                 default: True
  padding                           int                                  default: 6
  animation                         Any | None                           default: None
  border                            Any | None                           default: None

Dispatch-level fields (shared; _build_widget handles these):
  type                              required; widget type name (e.g. 'message', 'gif')
  text                              alias → widget's primary text field
  font                              BDF alias or hi-res font name
  ...
```

```bash
.venv/bin/led-ticker validate --list-fields nonexistent 2>&1
```

Expected: prints `Unknown widget type: 'nonexistent'. Available: [...]` to stderr, exits 2.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "feat: add --list-fields TYPE to validate subcommand (Significant #12)

led-ticker validate --list-fields message prints all init-able attrs fields
with types and defaults, plus the dispatch-level fields _build_widget handles
before passing to cls(**widget_cfg). Eliminates the memorize-or-grep tax on
discovering valid widget config keys.

path argument made optional; required when --list-fields is not given."
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task | Status |
|-------------|------|--------|
| Critical #1: unknown kwargs surface at validate-time not startup | Task 1 | ✓ allowlist check in `_build_widget` |
| did-you-mean suggestion via `difflib.get_close_matches` | Task 1 | ✓ |
| Rule number + fix string in `ValidationResult` | Task 1 | ✓ rule 38 in `_ERROR_PATTERNS` |
| `led-ticker validate --list-fields TYPE` subcommand | Task 2 | ✓ |
| Shows attrs fields with types and defaults | Task 2 | ✓ |
| Shows dispatch-level fields | Task 2 | ✓ |
| Unknown type → did-you-mean suggestion | Task 2 | ✓ |

**Placeholder scan:** None. All code is complete.

**Type consistency:**
- `cls_init_fields` (Task 1, allowlist) and `init_attrs` (Task 2, `_list_widget_fields`) both filter on `a.init is not False` — consistent.
- `_list_widget_fields` is called from `main()` and tested directly — names match.
- `args.list_fields` in `main()` matches `dest="list_fields"` in `add_argument` — consistent.

**Sharp edges:**

- `cls_init_fields` is computed fresh inside the allowlist block (after line 881), NOT reusing the `cls_fields` at line 852. `cls_fields` (line 852) includes `init=False` attrs fields. If you try to merge them, `init=False` fields would appear in the allowlist and let unknown-ish keys slip through. Keep them separate.

- The allowlist check runs BEFORE `if validate_only: return None`. This is intentional — the check fires for both validate runs and production runtime. Do NOT move it after the `validate_only` guard.

- `args.list_fields` defaults to `None` (not `False`), so the `if args.list_fields is not None:` guard is correct. If you use `if args.list_fields:`, a widget type named `"0"` would be skipped (falsy string). Use `is not None`.

- `path` becomes `nargs="?"` with `default=None`. The existing `args.config` (top-level `--config` argument) is separate and still uses `Path("config.toml")` as its default. Do not confuse them.

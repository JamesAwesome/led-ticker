# Config UX/DX Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch safety:** Before any work, run `git branch --show-current`. If it prints `main`, stop and create a worktree first.

**Goal:** Polish the config author experience for a new user — grouped `--list-fields` output with valid-value hints, enum allowlist validation for string fields, and hard renames (`message → text`, `gif_loops → loops`) with MigrationError fallbacks.

**Architecture:** Surface-layer only. Add a `FIELD_HINTS` dict and `FieldHint` namedtuple to `factories.py` that drives both `--list-fields` rendering and default display. Add a `FIELD_VALIDATORS` dict for enum allowlists. Renames use the existing `MigrationError` pattern from `text_scale → font_size`. No widget behaviour changes.

**Tech Stack:** Python, attrs, pytest, led-ticker config system (`src/led_ticker/app/factories.py`, `src/led_ticker/validate.py`, `src/led_ticker/widgets/message.py`, `src/led_ticker/widgets/gif.py`).

---

## Files modified

| File | Change |
|------|--------|
| `src/led_ticker/app/factories.py` | Add `FieldHint`, `FIELD_HINTS`, `TWO_ROW_OVERLAY_FIELDS`, `_DISPATCH_APPLICABLE_TYPES`, `FIELD_VALIDATORS`, `_enum_validator`; rewrite `_list_widget_fields`; call validators in `validate_widget_cfg`; add MigrationErrors for renamed fields |
| `src/led_ticker/validate.py` | Add coercion warning summary line to `_format_human` |
| `src/led_ticker/widgets/message.py` | Rename `message → text` on `TickerMessage` and `TickerCountdown` |
| `src/led_ticker/widgets/gif.py` | Rename `gif_loops → loops` on `GifPlayer` |
| `config/config.example.toml` | Update `message =` → `text =`; `gif_loops =` → `loops =` |
| `config/config.bigsign.example.toml` | Same |
| `config/config.moonbunny.example.toml` | Same |
| `config/config.presentation_test.example.toml` | Same |
| `config/config.showroom-bigsign.example.toml` | Same |
| `config/config.infini_scroll.toml` | Same |
| `tests/test_app.py` | Update `TestListWidgetFields`; add `TestFieldValidators`; add rename migration tests; update fixture dicts |
| `tests/test_validate.py` | Add coercion warning summary test |
| `tests/test_widgets/test_message.py` | Update `message=` fixtures → `text=` |
| `tests/test_widgets/test_gif.py` | Update `gif_loops=` fixtures → `loops=` |

---

## Task 1: Add FIELD_HINTS and grouping data to factories.py

**Files:**
- Modify: `src/led_ticker/app/factories.py` (after the imports block, before `_resolve_asset_paths`)

- [ ] **Step 1: Add `FieldHint` namedtuple and `FIELD_HINTS` dict**

Insert after the imports block (around line 40, after the `from led_ticker.transitions import ...` line):

```python
import collections

FieldHint = collections.namedtuple(
    "FieldHint", ["display_type", "description", "default_display"]
)

# Human-readable type strings, descriptions, and default overrides for --list-fields.
# Fields not in this dict fall back to attrs annotation + repr.
FIELD_HINTS: dict[str, FieldHint] = {
    # Universal widget fields
    "font": FieldHint("font name", "BDF alias or hi-res font name", "panel default font"),
    "font_size": FieldHint("int (pixels)", "text height in real pixels; required for hi-res fonts", "none"),
    "font_threshold": FieldHint("int 0–255", "bitmask threshold for hi-res font rendering", "128"),
    "font_color": FieldHint(
        'color | "rainbow" | "color_cycle" | "shimmer" | {style=...}',
        "text color or animated color provider",
        "white",
    ),
    "bg_color": FieldHint("[r, g, b] | none", "solid background fill color", "none"),
    "animation": FieldHint(
        '"typewriter" | {style="typewriter", frames_per_char=N}',
        "text animation effect",
        "none",
    ),
    "border": FieldHint(
        '{style="rainbow_chase", speed=N, width=N}',
        "animated border painted at panel edges",
        "none",
    ),
    # TickerMessage / TickerCountdown
    "text": FieldHint("str", "widget text content", None),
    "center": FieldHint("bool", "center text when it fits; false = left-align", "true"),
    "padding": FieldHint("int (pixels)", "end padding (spacing in side-by-side scroll)", "6"),
    # GifPlayer / StillImage single-row
    "path": FieldHint("str", "path to file (relative to config dir or absolute)", None),
    "text_align": FieldHint(
        '"auto" | "scroll" | "scroll_over" | "left" | "right" | "center"',
        "text scroll/position mode",
        '"auto"',
    ),
    "text_valign": FieldHint('"top" | "center" | "bottom"', "vertical text alignment", '"center"'),
    "fit": FieldHint('"pillarbox" | "letterbox" | "stretch" | "crop"', "how image fills canvas", '"pillarbox"'),
    "image_align": FieldHint('"left" | "center" | "right"', "horizontal image alignment within canvas", '"center"'),
    "scroll_direction": FieldHint('"left" | "right"', "direction the text scrolls", '"left"'),
    "scroll_speed_ms": FieldHint("int (ms)", "milliseconds per scroll step", "50"),
    "text_loops": FieldHint("int", "minimum full scroll traversals before advancing; 0 = one loop", "0"),
    "loops": FieldHint("int", "per-visit gif loop count; 0 = play through hold_time", "1"),
    "hold_seconds": FieldHint("float (seconds)", "how long to display before advancing", None),
    # GifPlayer / StillImage two-row overlay (active when bottom_text != "")
    "top_text": FieldHint("str", "top row text content", "''"),
    "bottom_text": FieldHint("str", "bottom row text; set to non-empty to enable two-row mode", "''"),
    "top_color": FieldHint(
        'color | "rainbow" | "color_cycle" | "shimmer" | {style=...}',
        "top row text color",
        "white",
    ),
    "bottom_color": FieldHint(
        'color | "rainbow" | "color_cycle" | "shimmer" | {style=...}',
        "bottom row text color",
        "white",
    ),
    "top_align": FieldHint('"left" | "center" | "right"', "top row horizontal alignment", '"center"'),
    "bottom_align": FieldHint('"left" | "center" | "right"', "bottom row horizontal alignment", '"center"'),
    "bottom_text_scroll": FieldHint('"marquee" | "hold"', "bottom row scroll behavior on overflow", '"marquee"'),
    "top_row_height": FieldHint("int | none", "top row height in logical pixels (none = 50/50 split)", "none"),
}

# Attrs fields on gif/image widgets that only activate when bottom_text != "".
# _list_widget_fields groups these into a separate "Two-row overlay" section.
TWO_ROW_OVERLAY_FIELDS: frozenset[str] = frozenset(
    {
        "top_text",
        "bottom_text",
        "top_color",
        "bottom_color",
        "top_align",
        "bottom_align",
        "top_font",
        "top_font_size",
        "top_font_threshold",
        "top_text_y_offset",
        "top_emoji_y_offset",
        "bottom_font",
        "bottom_font_size",
        "bottom_font_threshold",
        "bottom_text_y_offset",
        "bottom_emoji_y_offset",
        "bottom_text_scroll",
        "bottom_text_wrap",
        "bottom_text_separator",
        "bottom_text_separator_color",
        "top_row_height",
    }
)

# Dispatch-level fields and which widget types they apply to.
# None = applies to all types. Fields applicable to the queried type
# AND not already present in widget-level attrs are shown in "Shared fields".
_DISPATCH_APPLICABLE_TYPES: dict[str, set[str] | None] = {
    "type": None,
    "text": None,
    "font_size": None,
    "font_threshold": None,
    "animation": {"message", "gif", "image"},
    "border": {"message", "countdown", "two_row", "gif", "image"},
    "text_wrap": {"gif", "image"},
    "text_separator": {"gif", "image"},
    "text_separator_color": {"gif", "image"},
    "bottom_text_wrap": {"gif", "image", "two_row"},
    "bottom_text_separator": {"gif", "image", "two_row"},
    "bottom_text_separator_color": {"gif", "image", "two_row"},
    "top_font": {"two_row"},
    "top_font_size": {"two_row"},
    "top_font_threshold": {"two_row"},
    "bottom_font": {"two_row"},
    "bottom_font_size": {"two_row"},
    "bottom_font_threshold": {"two_row"},
}
```

- [ ] **Step 2: Run existing tests to confirm no regressions**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestListWidgetFields -v
```
Expected: 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/led_ticker/app/factories.py
git commit -m "feat: add FIELD_HINTS, TWO_ROW_OVERLAY_FIELDS, _DISPATCH_APPLICABLE_TYPES to factories"
```

---

## Task 2: Rewrite `_list_widget_fields` with grouped output

**Files:**
- Modify: `src/led_ticker/app/factories.py:644-720` (the `_list_widget_fields` function)
- Modify: `tests/test_app.py` (`TestListWidgetFields` class)

- [ ] **Step 1: Write failing tests**

Replace `TestListWidgetFields` in `tests/test_app.py` with:

```python
class TestListWidgetFields:
    """_list_widget_fields grouped output and FIELD_HINTS rendering."""

    def test_message_has_required_section(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        assert "Required:" in result

    def test_message_has_optional_section(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        assert "Optional:" in result

    def test_message_no_two_row_section(self):
        """message widget has no two-row overlay fields."""
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        assert "Two-row" not in result

    def test_gif_has_two_row_section(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("gif")
        assert "Two-row overlay" in result

    def test_message_hides_gif_only_dispatch_fields(self):
        """text_wrap (gif/image only) must not appear in message output."""
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        assert "text_wrap" not in result

    def test_gif_shows_text_wrap_in_shared(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("gif")
        assert "text_wrap" in result

    def test_gif_shows_valid_values_for_text_align(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("gif")
        assert '"auto" | "scroll"' in result

    def test_gif_shows_valid_values_for_fit(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("gif")
        assert '"pillarbox" | "letterbox"' in result

    def test_font_default_is_human_readable(self):
        """Font object repr must not appear; FIELD_HINTS override shows plain English."""
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        assert "panel default font" in result
        assert "object at 0x" not in result

    def test_font_color_shows_provider_options(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        assert '"rainbow"' in result

    def test_font_not_duplicated_for_message(self):
        """font is an attrs field on TickerMessage; must not also appear in Shared."""
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        # font appears as a field line exactly once
        assert result.count("  font ") + result.count("  font\n") == 1

    def test_animation_any_none_not_shown(self):
        """animation: Any | None must not appear; FIELD_HINTS gives human-readable type."""
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        assert "Any | None" not in result

    def test_unknown_type_raises_value_error(self):
        from led_ticker.app import _list_widget_fields
        with pytest.raises(ValueError, match="Unknown widget type"):
            _list_widget_fields("nonexistent_widget")

    def test_unknown_type_includes_did_you_mean(self):
        from led_ticker.app import _list_widget_fields
        with pytest.raises(ValueError, match="Did you mean"):
            _list_widget_fields("mesage")

    def test_two_row_fields_included_for_two_row_type(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("two_row")
        assert "top_text" in result
        assert "bottom_text" in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestListWidgetFields -v
```
Expected: most new tests FAIL.

- [ ] **Step 3: Rewrite `_list_widget_fields` in factories.py**

Replace the existing function (lines 644-720) with:

```python
def _list_widget_fields(widget_type: str) -> str:
    """Return a human-readable grouped field listing for widget_type."""
    import attrs as _attrs

    from led_ticker.widgets import _WIDGET_REGISTRY

    if widget_type not in _WIDGET_REGISTRY:
        candidates = sorted(_WIDGET_REGISTRY.keys())
        matches = difflib.get_close_matches(widget_type, candidates, n=3, cutoff=0.6)
        hint = (
            f"\nDid you mean: {', '.join(repr(m) for m in matches)}" if matches else ""
        )
        raise ValueError(
            f"Unknown widget type: {widget_type!r}. Available: {candidates}{hint}"
        )

    cls = _WIDGET_REGISTRY[widget_type]
    init_attrs = [
        a
        for a in getattr(cls, "__attrs_attrs__", ())
        if a.init is not False and a.name != "session"
    ]
    widget_field_names = {a.name for a in init_attrs}

    def _render_field(a: Any) -> str:
        hint = FIELD_HINTS.get(a.name)
        type_str = hint.display_type if hint else (
            a.type if isinstance(a.type, str)
            else getattr(a.type, "__name__", str(a.type)) if a.type is not None
            else ""
        )
        if a.default is _attrs.NOTHING:
            default_str = "(required)"
        elif hint and hint.default_display is not None:
            default_str = f"default: {hint.default_display}"
        elif isinstance(a.default, _attrs.Factory):  # type: ignore[arg-type]
            default_str = "default: <computed>"
        else:
            default_str = f"default: {a.default!r}"
        return f"  {a.name:<28}  {type_str:<44}  {default_str}"

    # Partition widget attrs into required / optional / two-row-overlay.
    # Two-row overlay only applies to gif/image — for other types all attrs
    # go into required/optional only.
    use_two_row_split = widget_type in ("gif", "image")
    required_attrs = [a for a in init_attrs if a.default is _attrs.NOTHING]
    if use_two_row_split:
        two_row_attrs = [
            a for a in init_attrs
            if a.default is not _attrs.NOTHING and a.name in TWO_ROW_OVERLAY_FIELDS
        ]
        optional_attrs = [
            a for a in init_attrs
            if a.default is not _attrs.NOTHING and a.name not in TWO_ROW_OVERLAY_FIELDS
        ]
    else:
        two_row_attrs = []
        optional_attrs = [a for a in init_attrs if a.default is not _attrs.NOTHING]

    lines: list[str] = [f'Fields for type="{widget_type}":', ""]

    if required_attrs:
        lines.append("Required:")
        for a in required_attrs:
            lines.append(_render_field(a))
        lines.append("")

    if optional_attrs:
        lines.append("Optional:")
        for a in optional_attrs:
            lines.append(_render_field(a))
        lines.append("")

    if two_row_attrs:
        lines.append("Two-row overlay (set bottom_text to enable):")
        for a in two_row_attrs:
            lines.append(_render_field(a))
        lines.append("")

    # Shared dispatch fields: applicable to this widget type AND not
    # already shown in widget-level (dedup by name).
    dispatch_rows: list[tuple[str, str]] = []
    for name, applicable_types in _DISPATCH_APPLICABLE_TYPES.items():
        if applicable_types is not None and widget_type not in applicable_types:
            continue
        if name in widget_field_names:
            continue  # already shown above
        hint = FIELD_HINTS.get(name)
        if hint:
            type_part = f"{hint.display_type}"
            default_part = f"default: {hint.default_display}" if hint.default_display else ""
            desc = f"{type_part}  {default_part}".rstrip()
        else:
            desc = ""
        dispatch_rows.append((name, desc))

    if dispatch_rows:
        lines.append("Shared fields (all types):")
        for name, desc in dispatch_rows:
            lines.append(f"  {name:<28}  {desc}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestListWidgetFields -v
```
Expected: all 15 tests pass.

- [ ] **Step 5: Smoke-test visually**

```bash
uv run led-ticker validate --list-fields message
uv run led-ticker validate --list-fields gif
```
Verify: Required/Optional sections visible, no `Any | None`, no `object at 0x`, `"auto" | "scroll"...` visible for `text_align`, `panel default font` visible for `font`.

- [ ] **Step 6: Run full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -q --ignore=tests/test_docs_config_options_drift.py
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_app.py
git commit -m "feat: rewrite --list-fields with grouped output and FIELD_HINTS"
```

---

## Task 3: Add `FIELD_VALIDATORS` enum allowlist checks

**Files:**
- Modify: `src/led_ticker/app/factories.py` (add `FIELD_VALIDATORS`, `_enum_validator`; call in `validate_widget_cfg`)
- Modify: `tests/test_app.py` (add `TestFieldValidators` class)

- [ ] **Step 1: Write failing tests**

Add after `TestListWidgetFields` in `tests/test_app.py`:

```python
class TestFieldValidators:
    """Enum-like string fields raise ValueError for unrecognised values."""

    @pytest.mark.asyncio
    async def test_text_align_invalid_raises(self):
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {"type": "gif", "path": "x.gif", "text_align": "centre"}
        with pytest.raises(ValueError, match="text_align"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_text_align_valid_passes(self):
        from led_ticker.app.factories import validate_widget_cfg
        import copy
        cfg = {"type": "gif", "path": "x.gif", "text_align": "scroll"}
        # Should not raise
        await validate_widget_cfg(copy.deepcopy(cfg), session=None)

    @pytest.mark.asyncio
    async def test_text_align_case_insensitive_after_coerce(self):
        """Coercion lowercases enum strings before validation; 'Scroll' must pass."""
        from led_ticker.app.factories import validate_widget_cfg
        import copy
        cfg = {"type": "gif", "path": "x.gif", "text_align": "Scroll"}
        # coercion normalises to "scroll" → validator passes
        await validate_widget_cfg(copy.deepcopy(cfg), session=None)

    @pytest.mark.asyncio
    async def test_fit_invalid_raises(self):
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {"type": "gif", "path": "x.gif", "fit": "squish"}
        with pytest.raises(ValueError, match="fit"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_scroll_direction_invalid_raises(self):
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {"type": "gif", "path": "x.gif", "scroll_direction": "up"}
        with pytest.raises(ValueError, match="scroll_direction"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_text_valign_invalid_raises(self):
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {"type": "gif", "path": "x.gif", "text_valign": "middle"}
        with pytest.raises(ValueError, match="text_valign"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_image_align_invalid_raises(self):
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {"type": "gif", "path": "x.gif", "image_align": "justify"}
        with pytest.raises(ValueError, match="image_align"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_bottom_text_scroll_invalid_raises(self):
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {
            "type": "gif",
            "path": "x.gif",
            "bottom_text": "hi",
            "bottom_text_scroll": "loop",
        }
        with pytest.raises(ValueError, match="bottom_text_scroll"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_error_message_includes_valid_values(self):
        """The error for an invalid enum value must list the allowed values."""
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {"type": "gif", "path": "x.gif", "fit": "wrong"}
        with pytest.raises(ValueError, match="pillarbox"):
            await validate_widget_cfg(cfg, session=None)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestFieldValidators -v
```
Expected: all 9 tests FAIL (validators don't exist yet).

- [ ] **Step 3: Add `_enum_validator` and `FIELD_VALIDATORS` to factories.py**

First update the typing import at the top of `factories.py` (line ~14):
```python
# Before:
from typing import Any
# After:
from typing import Any, Callable
```

Then add after the `_DISPATCH_APPLICABLE_TYPES` dict (module-level constants block):

```python
def _enum_validator(
    allowed: set[str], hint: str
) -> "Callable[[Any], str | None]":
    """Return a validator that checks value is in allowed (post-coercion)."""
    from typing import Callable  # noqa: F401 — used in annotation above

    def validate(value: Any) -> str | None:
        if isinstance(value, str) and value not in allowed:
            return f"got {value!r}; valid values: {hint}"
        return None

    return validate


# Field-level validators called in validate_widget_cfg after coercion.
# Each callable receives the (already coerced) value and returns an error
# string or None. Keyed by TOML field name.
FIELD_VALIDATORS: dict[str, "Callable[[Any], str | None]"] = {
    "text_align": _enum_validator(
        {"auto", "scroll", "scroll_over", "left", "right", "center"},
        '"auto" | "scroll" | "scroll_over" | "left" | "right" | "center"',
    ),
    "fit": _enum_validator(
        {"pillarbox", "letterbox", "stretch", "crop"},
        '"pillarbox" | "letterbox" | "stretch" | "crop"',
    ),
    "scroll_direction": _enum_validator(
        {"left", "right"},
        '"left" | "right"',
    ),
    "image_align": _enum_validator(
        {"left", "center", "right"},
        '"left" | "center" | "right"',
    ),
    "text_valign": _enum_validator(
        {"top", "center", "bottom"},
        '"top" | "center" | "bottom"',
    ),
    "bottom_text_scroll": _enum_validator(
        {"marquee", "hold"},
        '"marquee" | "hold"',
    ),
}
```

- [ ] **Step 4: Call validators in `validate_widget_cfg`**

In `validate_widget_cfg`, after the `_coerce_widget_cfg(widget_cfg, coercion_collector)` call and before the `animation_value = widget_cfg.pop("animation", None)` line, add:

```python
    # Enum allowlist checks. Run after coercion so case-normalised values pass.
    for field_name, validator in FIELD_VALIDATORS.items():
        if field_name in widget_cfg:
            error = validator(widget_cfg[field_name])
            if error is not None:
                raise ValueError(f"widget type={widget_type!r}: {field_name} {error}")
```

- [ ] **Step 5: Verify pyright passes**

```bash
uv run pyright src/led_ticker/app/factories.py
```
Expected: 0 errors.

- [ ] **Step 6: Run the new tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestFieldValidators -v
```
Expected: all 9 tests pass.

- [ ] **Step 7: Run full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -q --ignore=tests/test_docs_config_options_drift.py
```
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_app.py
git commit -m "feat: add FIELD_VALIDATORS enum allowlist checks to validate_widget_cfg"
```

---

## Task 4: Add coercion warning summary to `validate.py`

**Files:**
- Modify: `src/led_ticker/validate.py` (function `_format_human`, around line 1395)
- Modify: `tests/test_validate.py` (add summary test)

- [ ] **Step 1: Write failing test**

Add to `tests/test_validate.py`:

```python
def test_coerce_warning_summary_appears(tmp_path):
    """When validate emits coercion warnings, a summary count line appears."""
    import asyncio
    from led_ticker.validate import validate_config_file

    # Write a config with a string-int coercible field
    config_content = """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
hold_seconds = 3.0

[[playlist.section.widget]]
type = "message"
text = "hello"
padding = "6"
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    result = asyncio.run(validate_config_file(config_file))
    output = result.format_human()
    # The summary line should mention coercion warnings if any were emitted
    if result.warnings:
        assert "coercion warning" in output.lower()
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py::test_coerce_warning_summary_appears -v
```
Expected: FAIL (summary line not present yet) or SKIP if no coercion warnings are emitted for this config. Adjust the config if needed to trigger a warning (use `padding = "6"` which is a string-int coercion).

- [ ] **Step 3: Add summary line to `_format_human` in validate.py**

The current `_format_human` ends (around line 1408):
```python
    n = len(result.errors) + len(result.warnings)
    if n == 0:
        lines.append("No issues found.")
    else:
        lines.append(
            f"{n} issue(s):"
            f" {len(result.errors)} error(s),"
            f" {len(result.warnings)} warning(s)"
        )
    return "\n".join(lines)
```

Change to:
```python
    n = len(result.errors) + len(result.warnings)
    coerce_warnings = [w for w in result.warnings if w.rule == 37]
    if n == 0:
        lines.append("No issues found.")
    else:
        lines.append(
            f"{n} issue(s):"
            f" {len(result.errors)} error(s),"
            f" {len(result.warnings)} warning(s)"
        )
        if coerce_warnings:
            lines.append(
                f"  {len(coerce_warnings)} coercion warning(s)"
                " — update your config to silence these."
            )
    return "\n".join(lines)
```

- [ ] **Step 4: Run the test**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_validate.py::test_coerce_warning_summary_appears -v
```
Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -q --ignore=tests/test_docs_config_options_drift.py
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: add coercion warning summary count to validate output"
```

---

## Task 5: Rename `message` → `text` on TickerMessage and TickerCountdown

**Context:** `TickerMessage.message` and `TickerCountdown.message` are attrs fields holding the display text. Every other widget uses `text` or `top_text`/`bottom_text`. The `validate_widget_cfg` already has a `text → message` alias (it renames `text` to `message` when the class has no `text` field). After this task: `text` is the canonical attrs field name; `message` becomes a `MigrationError`.

**Files:**
- Modify: `src/led_ticker/widgets/message.py`
- Modify: `src/led_ticker/app/factories.py` (add MigrationError, remove text→message alias)
- Modify: `tests/test_app.py` (update fixture dicts; add migration tests)
- Modify: `tests/test_widgets/test_message.py` (update `message=` → `text=`)
- Modify: `config/config.example.toml`, `config/config.bigsign.example.toml`, `config/config.presentation_test.example.toml`, `config/config.showroom-bigsign.example.toml`, `config/config.infini_scroll.toml`

- [ ] **Step 1: Write failing migration tests**

Add to `tests/test_app.py`:

```python
class TestMessageFieldRename:
    """message field renamed to text on TickerMessage and TickerCountdown."""

    @pytest.mark.asyncio
    async def test_message_key_raises_migration_error_on_ticker_message(self):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError
        cfg = {"type": "message", "message": "hello"}
        with pytest.raises(MigrationError, match="text"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_text_key_works_on_ticker_message(self):
        from led_ticker.app.factories import _build_widget
        import aiohttp
        import copy
        cfg = {"type": "message", "text": "hello"}
        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(copy.deepcopy(cfg), session=session)
        assert widget.text == "hello"

    @pytest.mark.asyncio
    async def test_message_key_raises_migration_error_on_countdown(self):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError
        cfg = {"type": "countdown", "message": "Days Until Summer", "target_date": "2026-06-21"}
        with pytest.raises(MigrationError, match="text"):
            await validate_widget_cfg(cfg, session=None)

    def test_list_fields_message_shows_text_not_message(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("message")
        assert "  text " in result
        # "message" should not appear as a field name in the output
        lines_with_message = [
            l for l in result.splitlines()
            if l.strip().startswith("message")
        ]
        assert lines_with_message == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestMessageFieldRename -v
```
Expected: all 4 FAIL.

- [ ] **Step 3: Rename `message` → `text` in `message.py`**

In `src/led_ticker/widgets/message.py`:

Find `TickerMessage`:
```python
@register("message")
@attrs.define
class TickerMessage:
    ...
    message: str
```
Change to:
```python
@register("message")
@attrs.define
class TickerMessage:
    ...
    text: str
```
Then update every use of `self.message` in `TickerMessage` methods to `self.text`.

Find `TickerCountdown`:
```python
@attrs.define
class TickerCountdown:
    ...
    message: str
```
Change to:
```python
@attrs.define
class TickerCountdown:
    ...
    text: str
```
Then update every use of `self.message` in `TickerCountdown` methods to `self.text`.

- [ ] **Step 4: Add MigrationError and remove the text→message alias in factories.py**

In `validate_widget_cfg`, find the existing alias block:
```python
    if "text" in widget_cfg and "text" not in cls_fields:
        if "message" not in widget_cfg:
            widget_cfg["message"] = widget_cfg.pop("text")
        else:
            widget_cfg.pop("text")
```
Delete this entire block (no longer needed — TickerMessage now has `text` as its attrs field).

In the migration checks section (after the `presentation` check), add:
```python
    if "message" in widget_cfg and widget_type in ("message", "countdown"):
        raise MigrationError(
            f'type={widget_type!r}: the primary text field was renamed from '
            f'"message" to "text". Update your config.',
            suggested_fix='Rename "message" to "text" in your config.',
        )
```

- [ ] **Step 5: Update sample configs**

In each of these files, replace `message =` with `text =` on TickerMessage/TickerCountdown widget blocks (not on section headers or comments):

- `config/config.example.toml` — lines 69, 74
- `config/config.bigsign.example.toml` — lines 107, 112
- `config/config.presentation_test.example.toml` — lines 225, 243
- `config/config.showroom-bigsign.example.toml` — lines 240, 392
- `config/config.infini_scroll.toml` — lines 47, 53

Verify exact line numbers with `grep -n "message = " config/config.example.toml` first.

- [ ] **Step 6: Update tests that use `message=` in fixture dicts**

Search for all occurrences:
```bash
grep -rEn '"message":|message=' tests/ | grep -vE "type.*message|widget_type|MigrationError|match="
```
Update each found fixture to use `"text":` instead of `"message":`. Do NOT change `"type": "message"` entries — only the field value key.

- [ ] **Step 7: Run the migration tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestMessageFieldRename -v
```
Expected: all 4 pass.

- [ ] **Step 8: Run full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -q --ignore=tests/test_docs_config_options_drift.py
```
Expected: all pass.

- [ ] **Step 9: Update CLAUDE.md references**

Search for `message` used as a field name (not widget type) in CLAUDE.md:
```bash
grep -n '"message"' CLAUDE.md
```
Update any field-name references from `message = "..."` to `text = "..."`.

- [ ] **Step 10: Commit**

```bash
git add src/led_ticker/widgets/message.py src/led_ticker/app/factories.py \
        tests/test_app.py tests/test_widgets/test_message.py \
        config/config.example.toml config/config.bigsign.example.toml \
        config/config.presentation_test.example.toml \
        config/config.showroom-bigsign.example.toml \
        config/config.infini_scroll.toml CLAUDE.md
git commit -m "feat: rename message → text on TickerMessage/TickerCountdown with MigrationError"
```

---

## Task 6: Rename `gif_loops` → `loops` on GifPlayer

**Context:** `gif_loops` is the per-visit loop count on `GifPlayer`. The `gif_` prefix is redundant on a `type="gif"` widget. `StillImage` has no loop field so there's no collision.

**Files:**
- Modify: `src/led_ticker/widgets/gif.py`
- Modify: `src/led_ticker/app/factories.py` (add MigrationError; update FIELD_HINTS key)
- Modify: `tests/test_app.py` (add migration test)
- Modify: `tests/test_widgets/test_gif.py` (update `gif_loops=` fixtures)
- Modify: `config/config.bigsign.example.toml`, `config/config.moonbunny.example.toml`

- [ ] **Step 1: Write failing migration test**

Add to `tests/test_app.py`:

```python
class TestGifLoopsRename:
    """gif_loops field renamed to loops on GifPlayer."""

    @pytest.mark.asyncio
    async def test_gif_loops_raises_migration_error(self):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError
        cfg = {"type": "gif", "path": "x.gif", "gif_loops": 2}
        with pytest.raises(MigrationError, match="loops"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_loops_field_works_on_gif(self):
        from led_ticker.app.factories import validate_widget_cfg
        import copy
        cfg = {"type": "gif", "path": "x.gif", "loops": 2}
        # Should not raise
        await validate_widget_cfg(copy.deepcopy(cfg), session=None)

    def test_list_fields_gif_shows_loops_not_gif_loops(self):
        from led_ticker.app import _list_widget_fields
        result = _list_widget_fields("gif")
        assert "  loops " in result or "  loops\n" in result
        assert "gif_loops" not in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestGifLoopsRename -v
```
Expected: all 3 FAIL.

- [ ] **Step 3: Rename `gif_loops` → `loops` in `gif.py`**

In `src/led_ticker/widgets/gif.py`, find:
```python
    gif_loops: int = 1
```
Change to:
```python
    loops: int = 1
```
Update every use of `self.gif_loops` in `GifPlayer` methods to `self.loops`. (There will be uses in `__attrs_post_init__` validation and in `play()`.)

- [ ] **Step 4: Add MigrationError in factories.py**

In `validate_widget_cfg`, in the migration checks section (alongside the `presentation` and `message` checks), add:
```python
    if "gif_loops" in widget_cfg:
        raise MigrationError(
            'gif_loops was renamed to loops. Update your config.',
            suggested_fix='Rename "gif_loops" to "loops" in your config.',
        )
```

Update `FIELD_HINTS` key from `"gif_loops"` to `"loops"` (the entry was added in Task 1).

- [ ] **Step 5: Update sample configs**

```bash
grep -rn "gif_loops" config/
```
Replace `gif_loops = ` with `loops = ` in each occurrence:
- `config/config.bigsign.example.toml`
- `config/config.moonbunny.example.toml`

- [ ] **Step 6: Update gif test fixtures**

```bash
grep -rn "gif_loops" tests/
```
Update each occurrence to `loops`.

- [ ] **Step 7: Run the tests**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestGifLoopsRename -v
```
Expected: all 3 pass.

- [ ] **Step 8: Run full suite**

```bash
PYTHONPATH=tests/stubs uv run pytest -q --ignore=tests/test_docs_config_options_drift.py
```
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/widgets/gif.py src/led_ticker/app/factories.py \
        tests/test_app.py tests/test_widgets/test_gif.py \
        config/config.bigsign.example.toml config/config.moonbunny.example.toml
git commit -m "feat: rename gif_loops → loops on GifPlayer with MigrationError"
```

---

## Final validation

- [ ] **Run full suite one more time**

```bash
PYTHONPATH=tests/stubs uv run pytest -q --ignore=tests/test_docs_config_options_drift.py
```
Expected: all pass, 0 failures.

- [ ] **Smoke-test the renamed fields**

```bash
uv run led-ticker validate --list-fields message  # shows "text" not "message"
uv run led-ticker validate --list-fields gif      # shows "loops" not "gif_loops"
```

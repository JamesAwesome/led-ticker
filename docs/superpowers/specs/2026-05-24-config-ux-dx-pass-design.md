# Config UX/DX Pass — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the config author experience for a new user writing their first led-ticker config — better field discovery via `--list-fields`, cleaner validation error messages, and hard renames of confusing field names with migration errors.

**Approach:** Surface-layer polish. Fix the rendering and validation layers without touching the underlying attrs data model. A `FIELD_HINTS` dict drives both `--list-fields` output and error message context. A `FIELD_VALIDATORS` dict adds allowlist checks for enum-like string fields. Renames use the existing `MigrationError` mechanism.

**Scope:** Three independent work areas, each shippable as its own commit. No widget behaviour changes. No new widget types.

---

## Area 1: `--list-fields` output overhaul

### Problems being fixed

- **Noise from inapplicable fields.** `--list-fields message` shows `text_wrap: bool; valid on gif/image only` — a new user sees 30+ fields with no idea which apply.
- **Type annotations say nothing.** `animation: Any | None`, `border: Any | None`, `font: Font` — type-system accurate, useless to humans.
- **Enum strings show no valid values.** `text_align: str default: 'auto'` — valid values aren't listed anywhere in the output.
- **Raw Python object in defaults.** `font: default: <led_ticker._rgbmatrix_stub.Font object at 0x...>` — leaks stub internals.

### Design

**`FIELD_HINTS` dict** in `src/led_ticker/app/factories.py`. Maps field name → `FieldHint(display_type, valid_values, description, default_display)`. This is a static dict — no new data model, no changes to attrs definitions.

```python
@dataclass
class FieldHint:
    display_type: str          # human-readable type string
    valid_values: str | None   # e.g. '"auto" | "scroll" | "scroll_over"'
    description: str           # one-line description
    default_display: str | None  # overrides attrs default repr when set
```

Fields not in `FIELD_HINTS` fall back to attrs annotation + repr (current behaviour). The dict only needs entries for fields with bad defaults, complex types, or enum-like values.

**Output restructuring** in `_list_fields_for_type()` (factories.py). The current two-section layout (widget-level + dispatch-level) becomes four groups:

```
Fields for type="message":

Required:
  text    str    — widget text content

Optional:
  font        font name                     default: panel default font
  font_color  color or "rainbow" | ...      default: white
  center      bool                          default: true
  padding     int                           default: 6
  animation   "typewriter" | {style=...}    default: none
  border      {style="rainbow_chase",...}   default: none
  bg_color    [r, g, b] | none              default: none

Two-row overlay (set bottom_text to enable):
  top_text        str    default: ''
  bottom_text     str    default: ''
  top_color       ...
  ...

Shared fields (all widget types):
  type            required; widget type name (e.g. 'message', 'gif')
  font_threshold  int 0–255; default 128
```

**Filtering rules:**
- "Widget-level" fields are partitioned into Required / Optional / Two-row overlay based on: `(required)` tag from attrs, membership in `TWO_ROW_OVERLAY_FIELDS` set, everything else → Optional.
- Dispatch-level fields that are tagged `valid on gif/image only` or `valid on two_row` are **not shown** when the queried type doesn't match. Only genuinely universal dispatch fields appear in the Shared section.
- **Deduplication:** when a field name appears in both widget-level attrs and dispatch-level hints (e.g. `font`, `font_size`, `animation`, `border`), the widget-level row wins and the dispatch-level entry is suppressed. Shared section shows only fields that have no attrs counterpart in the widget class (e.g. `type`, `font_threshold`).

**`TWO_ROW_OVERLAY_FIELDS`** — a frozenset defined alongside `FIELD_HINTS` listing fields that only activate when `bottom_text != ""`: `top_text`, `bottom_text`, `top_color`, `bottom_color`, `top_align`, `bottom_align`, `top_font`, `top_font_size`, `top_font_threshold`, `top_text_y_offset`, `bottom_text_y_offset`, `top_emoji_y_offset`, `bottom_emoji_y_offset`, `top_row_height`, `bottom_font`, `bottom_font_size`, `bottom_font_threshold`, `bottom_text_scroll`, `bottom_text_wrap`, `bottom_text_separator`, `bottom_text_separator_color`.

### Files touched
- `src/led_ticker/app/factories.py` — add `FieldHint`, `FIELD_HINTS`, `TWO_ROW_OVERLAY_FIELDS`; rewrite `_list_fields_for_type()`
- `tests/test_app.py` — update `--list-fields` snapshot tests; add tests for grouping, valid-values hints, filtered dispatch fields

---

## Area 2: Validation error audit + new validations

### Problems being fixed

- **Missing enum validation.** `text_align = "centre"` is accepted silently and the widget runs with unexpected layout. Same for `fit`, `scroll_direction`, `image_align`, `text_valign`, `bottom_text_scroll`.
- **Inconsistent bool-as-int error messages.** Some int fields raise clean errors for bools, others don't. Format isn't uniform.
- **Computed defaults absent from error context.** Missing-required-field errors don't tell the user what format to use.
- **Coercion warnings not prominent enough.** String-to-int and case-normalisation coercions are collected but don't stand out in validate output.

### Design

**`FIELD_VALIDATORS` dict** in `factories.py`. Maps field name → `validate(value) -> str | None` callable (returns error string or `None`). String enum fields register their allowlists here.

```python
FIELD_VALIDATORS: dict[str, Callable[[Any], str | None]] = {
    "text_align": _enum_validator(
        {"auto", "scroll", "scroll_over", "left", "right", "center"},
        hint='valid values: "auto" | "scroll" | "scroll_over" | "left" | "right" | "center"',
    ),
    "fit": _enum_validator(
        {"pillarbox", "letterbox", "stretch", "crop"},
        hint='valid values: "pillarbox" | "letterbox" | "stretch" | "crop"',
    ),
    "scroll_direction": _enum_validator(
        {"left", "right"},
        hint='valid values: "left" | "right"',
    ),
    "image_align": _enum_validator(
        {"left", "center", "right"},
        hint='valid values: "left" | "center" | "right"',
    ),
    "text_valign": _enum_validator(
        {"top", "center", "bottom"},
        hint='valid values: "top" | "center" | "bottom"',
    ),
    "bottom_text_scroll": _enum_validator(
        {"marquee", "hold"},
        hint='valid values: "marquee" | "hold"',
    ),
}
```

`_enum_validator(allowed, hint)` returns a closure that checks `value in allowed` (after coercion has already lowercased/stripped) and returns an error string citing the hint on failure.

**Call site:** `validate_widget_cfg` calls field validators after `_coerce_widget_cfg` and before `_validate_cfg_fields`. Failures raise `ValueError` with the hint text embedded. The existing rule system assigns these `rule 41+` (next available after rule 40).

**Bool-as-int standardisation audit.** Walk every `int`-typed attrs field in every widget class. Confirm all have the same error message pattern: `"{field} must be an integer; got bool (true/false). Use 0, 1, 2, …"`. Standardise any that don't.

**Coercion warning prominence.** In `validate.py`'s human-readable output, coercion warnings already print as `⚠ WARNING`. Add a summary line at the end: `N coercion warning(s) — update your config to silence these.` if any warnings were emitted. No change to the warning content itself.

### Files touched
- `src/led_ticker/app/factories.py` — add `FIELD_VALIDATORS`, `_enum_validator`, call validators in `validate_widget_cfg`
- `src/led_ticker/validate.py` — add coercion warning summary line
- `tests/test_app.py` — tests for each new enum validator; typo cases (`"centre"`, `"Stretch"` post-coerce, etc.)
- `tests/test_validate.py` — test coercion warning summary line

---

## Area 3: Field rename strategy + sample config updates

### Mechanism (applies to all confirmed renames)

Every rename follows this four-step pattern, matching the existing `text_scale → font_size` precedent:

1. **Add `MigrationError`** in `_validate_cfg_fields` for the old field name. `MigrationError.suggested_fix` says exactly: `'rename {old!r} → {new!r} in your config'`.
2. **Remove the old field name** from the attrs definition (or alias table) so `_validate_cfg_fields`'s unknown-field check no longer suppresses it.
3. **Update all sample configs:** `config/config.example.toml`, `config/config.bigsign.example.toml`, `config/config.moonbunny.example.toml`.
4. **Update tests** that use the old field name in fixture dicts.

### Rename audit task

Before any renames are implemented, a dedicated audit task reads every widget's attrs definition and every sample config and produces a confirmed rename list. The audit must answer for each candidate:
- Is the old name used in any sample config or test fixture?
- Is there an existing alias that already accepts the new name?
- Would the rename break any call site in the non-test codebase?

### Known rename candidates (to be confirmed by audit)

| Old name | New name | Widget(s) | Rationale |
|----------|----------|-----------|-----------|
| `message` (primary text field) | `text` | `TickerMessage` | Every other widget uses `text` or `top_text`/`bottom_text`; `text` alias already works; `message` as canonical name reads as the widget type, not the content |
| `gif_loops` | `loops` | `GifPlayer` | `gif_` prefix is redundant on a `type="gif"` widget; `StillImage` has no loops field so there's no collision |
| (further candidates TBD by audit) | | | |

### Files touched (per rename)
- `src/led_ticker/app/factories.py` — `MigrationError` entry in `_validate_cfg_fields`
- `src/led_ticker/widgets/<widget>.py` — rename attrs field; remove old name from alias handling if present
- `config/config.example.toml`, `config/config.bigsign.example.toml`, `config/config.moonbunny.example.toml`
- `tests/test_app.py`, `tests/test_widgets/` — update fixture dicts
- `CLAUDE.md` — update any field-name references

---

## Testing strategy

- `--list-fields` output: snapshot tests asserting the grouped structure, presence of valid-values hints, absence of inapplicable dispatch fields.
- Enum validators: one test per field, covering valid value, invalid value (typo), and post-coercion valid (e.g. `"Left"` → `"left"` passes).
- Rename migrations: one test per rename asserting old name raises `MigrationError` with the correct `suggested_fix`.
- Coercion warning summary: integration test through `validate.py` asserting the summary line appears when warnings are present.

## Out of scope

- Changes to widget behaviour or rendering.
- New widget types or fields.
- Docs site updates (the docs drift test will catch any new fields; prose updates are a separate pass).
- `font_color` vs `top_color`/`bottom_color` naming — audit may determine this inconsistency is acceptable given the two-row overlay model.

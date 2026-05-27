# Config coerce-and-warn pass

**Status:** Approved, awaiting implementation plan
**Date:** 2026-05-19

## Problem

Users hand-edit `config.toml` and hit two recurring footguns that produce confusing crashes deep in the call stack:

1. **String where number expected.** `font_size = "25"` crashes with `TypeError: '<' not supported between instances of 'str' and 'int'` in `resolve_font` — the error doesn't name the field, the file, or suggest the fix.
2. **Case-sensitive enum values.** `image_align = "Left"` (instead of `"left"`) trips an opaque validation error somewhere downstream.

Both are unambiguous slips — there's no realistic config where the user *meant* a string `"25"` or capitalized `"Left"`. But today they crash startup with stack traces.

## Decision

Add a **coerce-and-warn** pass at config load:

- Silently fix the obvious slips (string-of-digits → int; `"Left"` → `"left"`).
- Emit a **warning** (not error) so the user knows it happened and can fix the source.
- Warnings surface both in `led-ticker validate` output (as a new rule) AND at runtime startup (via `logging.warning`).

Coerce-and-warn was chosen over reject-with-clear-error because the user prefers configs to "just work" with a heads-up, rather than requiring a re-edit cycle for typos.

## Scope

### Coerce silently + warn (safe)

**Numeric strings → number.** Every `int` / `float` field on:

- `SectionConfig` (`config.py`): `content_height`, `scale`, `hold_time`, `loop_count`, `start_hold`, `scroll_step_ms`, `separator_font_size`, etc.
- `DisplayConfig` (`config.py`): `rows`, `cols`, `chain`, `parallel`, `brightness`, `gpio_slowdown`, `pwm_bits`, `pwm_lsb_ns`, `default_scale`, etc.
- Widget dataclass fields with `int` / `float` type annotations (especially `_image_base.py`, `two_row.py`, `message.py`, `weather.py`, the crypto widgets).
- Font-resolution fields popped in `_build_widget`: `font_size`, `font_threshold`, `top_font_size`, `bottom_font_size`, `separator_font_size`.

**Bool is explicitly rejected** — `bool` is an `int` subclass and coercing `true → 1` would re-open the hole that rule 28 (`bottom_text_loops`) closed.

### Coerce + warn with caveat

**Closed-set enum strings → lowercased + stripped.** Only fields with a `frozenset` of valid values:

- `text_align`, `text_valign`, `image_align`, `scroll_direction`, `fit`, `bottom_text_scroll` (defined in `_image_fit.py` / `_image_base.py`)
- `easing` (defined in `transitions/__init__.py`)

`"Left"` → `"left"`, `" scroll_over "` → `"scroll_over"`.

**Caveat (documented):** This makes TOML enum values case-insensitive — a one-way contract change. Once shipped, `"Left"` becomes part of the supported surface; the docs site must reflect this in `docs/site/.../reference/config-options.mdx`.

**Bonus fix in same PR:** The `easing` lookup in `transitions/__init__.py:157` currently silently falls back to `linear` on unknown values. Switch that to an explicit unknown-value check that emits a warning (the case-normalization fits naturally in the same code path).

### Explicitly NOT coerced (kept strict)

- **RGB lists / color shorthand.** `font_color`, `bg_color`, `top_color`, `bottom_color`, `transition_color`, `separator_color`, `border` shorthand. A string like `"255,0,0"` is ambiguous (CSV? hex?) — reject cleanly with a "use `[r, g, b]`" hint.
- **Bool fields.** TOML has native `true` / `false`; coercing `"true"` would weaken type safety.
- **Inline-table `style` values.** `font_color = {style="gradient", ...}`, `animation = {style="typewriter", ...}`, `border = {style="rainbow", ...}` — the `style` key set is open-ended; case-normalizing locks the spelling for every future provider.
- **`mode` field on sections.** No enum-check today; case-normalizing without first adding the enum is half a fix. Tracked as a follow-up.
- **Free-text / paths / font names.** `text`, `top_text`, `bottom_text`, `font`, `path`, `feed_url` — a typo here should surface as a clean file-not-found, not a silent fix.

## Architecture

### New module: `src/led_ticker/_coerce.py`

Three small helpers + a shared exception type:

```python
def coerce_int(value, *, field: str) -> tuple[int, str | None]:
    """Return (coerced_value, warning_msg_or_None). Rejects bool.
    Raises ValueError for non-numeric strings or wrong types."""

def coerce_float(value, *, field: str) -> tuple[float, str | None]:
    """Same shape for floats. Rejects bool."""

def coerce_choice(value, *, field: str, valid: frozenset[str]) -> tuple[str, str | None]:
    """Lowercases + strips. Returns warning if input differed.
    Raises ValueError if the normalized value still isn't in `valid`."""
```

Each returns `(value, warning_message_or_None)`. The caller decides whether to push the warning into the validation issue list or log it at runtime. This decoupling is what lets the same coercion fire in both `led-ticker validate` and at startup.

### Call sites

1. **`config.py` — `SectionConfig.__post_init__` and `DisplayConfig.__post_init__`** walk their own dataclass fields, dispatching by type annotation. Collected warnings hang on `_coerce_warnings: list[str]` on the config object.
2. **`app.py:_build_widget`** — before `cls(**widget_cfg)`, run the same pass over `widget_cfg` using `cls.__attrs_attrs__` for type info. Warnings appended to a context list passed through `validate_only` mode.
3. **`transitions/__init__.py`** — `easing` lookup gets an explicit unknown-value check; valid values come from `EASING.keys()`.

### Warning surfaces

- **`led-ticker validate`** — new `_check_coercions` function in `validate.py` reads `config._coerce_warnings` and the build-pass collector, surfaces as rule 37+ warnings with severity `warning`.
- **Runtime startup** — `app.py:run()` after `load_config`, iterate the warning list and `logging.warning(...)` each. Same message text as the validate output.

## Testing

TDD, one test per coercion class:

- **`tests/test_coerce.py`** — unit tests on the three helpers:
  - `coerce_int` happy path, rejects bool, rejects non-numeric string, accepts int passthrough
  - `coerce_float` same shape, accepts numeric string with decimal
  - `coerce_choice` lowercases, strips whitespace, rejects unknown values, accepts canonical passthrough
- **`tests/test_validate.py` additions** — full-pipeline tests:
  - Config with `font_size = "25"` → validation result has one warning, zero errors
  - Config with `image_align = "Left"` → same
  - Config with `font_color = "255,0,0"` → still hard error (not coerced)
  - Config with `font_size = true` → hard error (bool rejected explicitly)
- **`tests/test_app_runtime_warnings.py`** (new) — startup with a coerced config emits the expected `logging.warning`.
- **Tripwire:** existing `tests/test_engine_*` and `tests/test_widgets/*` stay green — no regressions from changed config-load semantics.

## Migration / back-compat

- All existing configs continue to work unchanged (this only adds warnings to configs that were previously crashing).
- The existing rule 10 (`font_threshold must be int 0-255`) and rule 28 (`bottom_text_loops must be int`) remain — they reject *bool*, which the new coercer also rejects, so they continue to fire on `true` / `false`.
- The `font_threshold` and `bottom_text_loops` bool-guards in their current locations are kept as a belt-and-braces layer.

## Docs

`docs/site/.../reference/config-options.mdx` gets a "Coercion behavior" callout listing:

- Which numeric fields auto-coerce from string
- Which enum fields are case-insensitive (with the canonical lowercase form documented as the recommended spelling)
- The list of fields that remain strict, with one-line rationales

## Out of scope (follow-up PRs)

- Enum-validating `mode` on sections (precondition for case-normalizing it).
- A "strict mode" flag to escalate warnings → errors for CI use.
- Coercing inline-table `style` strings inside provider configs.
- Generic "did you mean" suggestions on unknown enum values (the current explicit `valid:` list is enough for v1).

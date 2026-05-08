# Design: Config Validator

**Date:** 2026-05-07
**Status:** Approved

## Overview

A `led-ticker validate` subcommand that checks a TOML config file for errors and warnings without running the display. Usable by humans before copying a config to the Pi, and by the `creating-a-config` skill as a programmatic helper. Output is human-readable by default; `--json` emits structured data for skill integration.

---

## What It Validates

Two-phase approach — reuses the real app machinery, no duplication of widget or font knowledge.

**Phase 1 — Hard errors (real load pipeline)**

Calls `load_config()` then `_build_widget()` for every widget. Exceptions caught and reported as errors. The `_compat.py` shim already stubs `rgbmatrix` when the real hardware library is absent (same mechanism the test suite uses), so widget construction works without a Pi.

Catches:
- TOML syntax errors
- Unknown widget `type` (not in registry)
- Unknown transition `type` (not in registry)
- `animation = "typewriter"` on widget types other than `message`, `countdown`, `gif`, `image` (rule 12)
- `animation = "typewriter"` on `gif`/`image` when `bottom_text != ""`, `text_align ∈ ("scroll", "scroll_over")`, or `text == ""` (rule 14)
- HiresFont without `font_size` (rule 5)
- Legacy `text_scale` field (rule 20, migration error)
- `border` on invalid widget type (rule 15)
- `text_align = "scroll"` + `fit = "stretch"` (rule 3)
- `text_x_offset != 0` + scroll `text_align` (rule 7)
- `hold_seconds < 0.05` (rule 8)
- `font_threshold` wrong type (rule 10)

If phase 1 fails (load raises), phase 2 is skipped and the load error is reported.

**Phase 2 — Soft warnings (checks against loaded dataclasses)**

Runs only when phase 1 succeeds. Checks the parsed `AppConfig`/`SectionConfig` dataclasses — no raw TOML re-parsing.

Produces warnings for:
- `content_height × effective_scale > panel_h_real` (rule 1). `effective_scale` is `section.scale` if set, else `display.default_scale`.
- Within-family `font_threshold` mismatch: two widgets in the same section sharing a font family stem (e.g., `Inter-Regular` / `Inter-Bold`) with different `font_threshold` values (rule 2).
- `transition_duration > 5.0` or `< 0.05` (rule 21, likely unit error or typo).
- `two_row` widget in a section where `effective_scale == 4` without a per-section `scale = 2` override (rule 6).

Rules 4, 11, 13, 16–19 are informational or auto-handled by the runtime — the validator does not flag them.

---

## CLI Interface

### Subcommand refactor

`app.py`'s existing flat argparse is promoted to a subparser structure. Backward compat preserved: `led-ticker --config config.toml` (no subcommand) continues to work by treating a missing subcommand as `run`.

```
led-ticker run --config <path>      # explicit run (new)
led-ticker --config <path>          # back-compat run (unchanged)
led-ticker validate <path> [--json] # new
```

`pyproject.toml` keeps the single `led-ticker` entry point — no new entry point added.

### Validate usage

```
led-ticker validate config/config.toml [--json]
```

**Exit codes:**
- `0` — valid (errors list is empty; warnings are OK)
- `1` — one or more errors found
- `2` — usage error or file not found

### Human-readable output (default)

ANSI color when stdout is a tty; plain text otherwise.

```
Validating config/config.toml...

✗ ERROR   section[1].widget[0]: HiresFont 'Inter-Regular' requires font_size [rule 5]
          Fix: add font_size = 24 next to font

⚠ WARNING section[0]: transition_duration 500.0 looks like milliseconds [rule 21]
          Fix: divide by 1000 → 0.5

2 issue(s): 1 error, 1 warning
```

### JSON output (`--json`)

```json
{
  "valid": false,
  "path": "config/config.toml",
  "errors": [
    {
      "rule": 5,
      "location": "section[1].widget[0]",
      "message": "HiresFont 'Inter-Regular' requires font_size",
      "fix": "add font_size = 24 next to font"
    }
  ],
  "warnings": [
    {
      "rule": 21,
      "location": "section[0]",
      "message": "transition_duration 500.0 looks like milliseconds",
      "fix": "divide by 1000 → 0.5"
    }
  ]
}
```

`valid` is `true` iff `errors` is empty. Warnings do not affect `valid`.

---

## Implementation

**Files changed:**

| File | Change |
|------|--------|
| `src/led_ticker/app.py` | Refactor `main()` to subparsers; `run` subcommand is default when none given |
| `src/led_ticker/validate.py` | New module: `ValidationIssue`, `ValidationResult`, `validate_config()`, `main()` |
| `tests/test_validate.py` | New test file (see Tests section) |
| `.claude/skills/creating-a-config/SKILL.md` | Add validator call at each validation checkpoint |
| `.claude/skills/creating-a-config/references/decision-rules.md` | Fix rule 12 wording: typewriter valid on gif/image (single-row only) |

**`validate.py` structure:**

```python
@dataclass
class ValidationIssue:
    rule: int | None       # None for load errors without a rule number
    location: str          # e.g. "section[1].widget[0]"
    message: str
    fix: str
    severity: Literal["error", "warning"]

@dataclass
class ValidationResult:
    path: Path
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

def validate_config(path: Path) -> ValidationResult: ...
def main() -> None: ...   # CLI shim: parse args, call validate_config, format + exit
```

`validate_config` imports `load_config` and `_build_widget` from `app`. Widget construction runs under the `_compat.py` stub environment — no hardware required.

---

## Skill Integration

`SKILL.md` updated at each of the three validation checkpoints (per-section lint, Phase 3 final, refine-mode step 1) to run:

```bash
led-ticker validate config/config.toml --json
```

The skill reads `valid`, `errors`, and `warnings` from the JSON and surfaces each item via flag-and-ask, citing `rule` and `fix` from the output. This replaces the current approach of reasoning over `decision-rules.md` inline.

`decision-rules.md` is kept as the human-readable source of truth; it is no longer the primary validation mechanism at runtime.

---

## Tests

`tests/test_validate.py` — calls `validate_config(path)` directly (no subprocess).

- **Happy path**: well-formed config → `valid=True`, empty errors and warnings
- **TOML syntax error**: returns one error, no crash
- **Unknown widget type**: error with correct `section[N].widget[M]` location
- **Rule 1** (content_height × scale > panel): warning with section location
- **Rule 2** (font_threshold mismatch): warning identifying both widgets
- **Rule 3** (scroll + stretch): error
- **Rule 5** (HiresFont missing font_size): error
- **Rule 6** (two_row at scale=4 without scale override): warning
- **Rule 10** (font_threshold wrong type): error
- **Rule 12** (animation on invalid widget type): error; no error on message/countdown/gif/image
- **Rule 14** (typewriter on gif/image two-row or scroll): error; no error on gif/image single-row with text
- **Rule 21** (duration > 5 or < 0.05): warning
- **JSON output**: `--json` produces parseable JSON matching `ValidationResult` schema
- **Exit codes**: 0 on clean, 1 on errors, 2 on missing file

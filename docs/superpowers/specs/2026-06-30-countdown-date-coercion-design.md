# Countdown/countup date coercion — design

**Date:** 2026-06-30
**Status:** Approved (brainstorm complete). Small bounded fix → direct PR (no full plan/SDD).

## Problem

`TickerCountdown.countdown_date` and `TickerCountup.countup_date` (`src/led_ticker/widgets/count.py`) are typed `date` with **no attrs converter**. TOML parses an *unquoted* `2027-01-01` as a native `datetime.date` (works) but a *quoted* `"2027-01-01"` as a `str`, which survives into `_days()` → `(self.countdown_date - self._today()).days` → `TypeError: unsupported operand type(s) for -: 'str' and 'datetime.date'`. The render breaker disables the widget. Both quoted and unquoted forms appear in committed configs. `validate_widget_cfg` does **not** construct the widget, so the bad value passes preflight silently and crashes only at draw.

Scope is bounded: a repo grep finds **no other** date-typed coerced config fields (`clock.py`/`schedule.py` take runtime `datetime` params; schedule windows use time-strings). This fix touches `count.py` only.

## Fix (applied identically to BOTH `countdown_date` and `countup_date`)

### 1. Converter `_coerce_date` (the core fix)
A module-level helper in `count.py`, applied via `converter=` on both fields (mirrors the existing `_coerce_font_color` pattern in the same file):

```python
def _coerce_date(value: Any) -> date:
    """Coerce a config date value to datetime.date.

    Accepts a native date (TOML unquoted date — passthrough), an ISO
    "YYYY-MM-DD" string (TOML quoted — parsed), or a datetime (→ .date(),
    since _today() returns a date and date - datetime would raise). Any
    other type, or an unparseable string, raises at config-load (widget
    construction) with a clear message — far better than a draw-time crash.
    """
    if isinstance(value, datetime):
        return value.date()          # before the date check: datetime IS-A date
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"date must be ISO YYYY-MM-DD (e.g. 2026-12-25), got {value!r}"
            ) from exc
    raise TypeError(
        f"date must be a YYYY-MM-DD string or a date, got {type(value).__name__}"
    )
```

Note `datetime` is checked **before** `date` because `datetime` is a subclass of `date`. Apply: `countdown_date: date = attrs.field(kw_only=True, converter=_coerce_date)` and the same for `countup_date`.

### 2. Un-mask the wrong-side advisory
`_wrong_side_warning` (`count.py`) runs on the **raw** cfg value (a `str` when quoted); its `if not isinstance(value, date): return []` guard skips, silently dropping the "this date is in the past / future — won't display" hint. Coerce the value first via `_coerce_date` inside a `try/except` (return `[]` on an unparseable value — that's reported by the validate rule below), then run the existing past/future comparison. The advisory then fires for both quoted and unquoted dates.

### 3. Validate preflight rule (friendly message; closes the silent-accept gap)
Since `validate_widget_cfg` doesn't construct the widget, the converter never runs at `make validate`. Add a date-field check to each subclass's `validate_config` (the base already validates `timezone`): the date field is **required**, and a string value must parse as ISO. Emit a friendly error, e.g. `countdown_date must be a date (YYYY-MM-DD, e.g. 2026-12-25)`. Each subclass checks its own field name (`countdown_date` / `countup_date`); factor the shared check into a helper to avoid duplication.

## Tests (`tests/test_widgets/test_count.py` or the existing count test file)

- `countdown` + `countup` built with a **quoted string** date compute `_days()` correctly (no crash) — the regression.
- A **native `date`** still works (no behavior change).
- A **`datetime`** value is coerced to its `.date()`.
- A **bad string** (`"not-a-date"`) raises a clear error at construction.
- `_wrong_side_warning` fires for a **string-supplied** past date (countdown) / future date (countup) — previously masked.
- `validate_config` rejects a **malformed / missing** date with the friendly message; accepts a valid string and a valid native date.

## Non-goals

- No change to `_days()`, `_today()`, the render path, or any other widget.
- No new date-ish config fields (none exist).
- Not bundled with inline-tokens; ships as its own fix and rides the next release.

## Execution

Direct PR off `main` (post-#321), worktree `fix/countdown-date-coercion`. Gates: `PYTHONPATH=tests/stubs uv run --extra dev pytest`, `ruff check src/ tests/`, `pyright src/`. PEP 649 (no `from __future__ import annotations`). Then cut a release bundling inline value tokens (#321) + this fix.

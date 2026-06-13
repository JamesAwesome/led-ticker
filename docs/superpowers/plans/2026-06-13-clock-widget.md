# Clock Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `type = "clock"` widget that displays the current time (12h/24h preset or custom strftime), with an optional timezone override and inline date, rendered through the existing text surface.

**Architecture:** A thin `Clock(FrameAwareBase)` widget whose `draw()` mirrors `TickerCountdown.draw` — it resolves the timezone, computes the time string via a pure `format_clock(now, fmt)`, and dispatches through the shared text-render helpers (so `font_color`/`font`/`bg_color`/`border` behave exactly like the message widget). No new dependencies (stdlib `zoneinfo`); no engine changes (held widgets already redraw every 50ms tick via `_hold_ticks`).

**Tech Stack:** stdlib (`datetime`, `zoneinfo`), attrs. No new deps.

**Spec:** `docs/superpowers/specs/2026-06-13-clock-widget-design.md`

**Worktree notes (read first):**
- Work in `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/clock-widget`, branch `feat/clock-widget`. Run `git branch --show-current` and ABORT if it prints `main`.
- Tests: `PYTHONPATH=tests/stubs uv run pytest <files> -q` · Lint: `uv run --extra dev ruff check src/ tests/` · Format: `uv run --extra dev ruff format <files>`.
- Commit with hooks ON: `PATH="$PWD/.venv/bin:$PATH" git commit -m "..."` (do NOT use `--no-verify`; if the format hook reformats a file, `git add -u` and commit again).
- House style: no gun metaphors; say pitfall/gotcha/sharp edge.
- This branch is isolated from PR #203 by design — only net-new files + append-only edits (see spec "Merge isolation").

**Pre-verified code facts (do not re-derive):**
- `TickerCountdown` (`src/led_ticker/widgets/message.py`, around line 306) is the exact template. Its `draw(canvas, cursor_pos=0, *, y_offset=0, font_color=None)` does: coerce override font_color via `_ConstantColor` if not a provider; `provider = font_color or self.font_color`; compute the text; `content_width = get_text_width(self.font, text, padding=0, canvas=canvas)`; `cursor_pos, end_padding = compute_cursor(canvas.width, content_width, cursor_pos, self.padding, center=self.center)`; cache `_baseline_y = compute_baseline(self.font, canvas, valign="center")`; paint border `if self.border is not None: self.border.paint(canvas, self.frame_for("border"))`; then the `if provider.per_char:` branch uses `draw_text_per_char(canvas, self.font, cursor_pos, baseline_y + y_offset, text, lambda idx, total: provider.color_for(self.frame_for("font_color"), idx, total))`, else `color = provider.color_for(self.frame_for("font_color"), 0, len(text))` + `draw_text(canvas, self.font, cursor_pos, baseline_y + y_offset, color, text)`; `cursor_pos += end_padding`; `return canvas, cursor_pos`.
- Imports available in message.py to copy: `from led_ticker._types import Canvas, Color, DrawResult, Font`; `from led_ticker.color_providers import ColorProvider, _ConstantColor`; `from led_ticker.colors import DEFAULT_COLOR`; `from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width`; `from led_ticker.fonts import FONT_DEFAULT`; `from led_ticker.text_render import draw_text, draw_text_per_char`; `from led_ticker.widgets import register`; `from led_ticker.widgets._frame_aware import FrameAwareBase`. `_coerce_font_color(value)` wraps a raw Color in `_ConstantColor`.
- The widget must be `@register("clock") @attrs.define class Clock(FrameAwareBase)` — `@attrs.define` is REQUIRED or `FrameAwareBase.__new__` raises `TypeError`.
- `border` field: `factories.py` (~line 669) rejects `border` unless `widget_type in ("message","countdown","two_row","gif","image")` OR `_widget_declares_field(cls, "border")` (line 510). Declaring a `border` attrs field on `Clock` satisfies the gate — do NOT edit the allowlist. Border is coerced from TOML by the build pipeline (`coercion._coerce_border`) via field name; the widget just declares `border: Any | None = attrs.field(default=None, kw_only=True)` like countdown.
- `format`/`timezone` are plain str fields — the coercion layer leaves unknown-named fields untouched, so they pass straight to `cls(**cfg)`. Unknown *field names* are caught generically; only *value* checks need `validate_config`.
- `validate_config(cls, cfg) -> list[str]` classmethod is the validation hook (`factories._run_validate_config`, line 517): it's called with a copy of cfg; a non-empty returned list becomes `ValueError(f"{widget_type}: {'; '.join(messages)}")`. Must be a `@classmethod`.
- `FIELD_HINTS` (`factories.py:55`) is a GLOBAL name-keyed dict of `FieldHint(display_type, description, default_display)` namedtuples. Add `format` and `timezone` keys (shared across widgets, not per-widget).
- The `canvas` test fixture (`tests/conftest.py:45`) is a `mock.Mock()` with `width=160, height=16`. The stub `graphics.DrawText` returns a real int advance even on the Mock, so cursor_pos math works (that's how `test_message` asserts numeric cursor_pos).
- `tests/test_list_fields_golden.py` has a hardcoded `TYPES` list NOT including clock — a golden is optional, not required.
- `tests/test_border_surface_drift.py` has a `FACT_PACK_FILES` tuple `("message","countdown","two_row","gif","image")` — since clock advertises `border`, add `"clock"` there + a fact-pack with a border row.

**File structure:**

| File | Change |
|---|---|
| `src/led_ticker/widgets/clock.py` (create) | `format_clock` pure fn + `Clock` widget |
| `src/led_ticker/widgets/__init__.py` (modify) | add `clock` to the auto-import tuple |
| `src/led_ticker/app/factories.py` (modify) | `FIELD_HINTS` += `format`, `timezone` |
| `docs/site/src/content/docs/widgets/clock.mdx` (create) | user docs |
| `docs/content-source/widgets/clock.md` (create) | fact-pack (with border row) |
| `tests/test_border_surface_drift.py` (modify) | add `clock` to `FACT_PACK_FILES` |
| `tests/test_widgets/test_clock.py` (create) | all widget + format tests |

---

### Task 1: `format_clock` pure function

**Files:**
- Create: `src/led_ticker/widgets/clock.py`
- Test: `tests/test_widgets/test_clock.py` (create)

- [ ] **Step 1: Write the failing tests** — create `tests/test_widgets/test_clock.py`:

```python
"""Tests for led_ticker.widgets.clock."""

from datetime import datetime

import pytest

from led_ticker.widgets.clock import format_clock


def _dt(h, m):
    return datetime(2026, 6, 13, h, m)


def test_12h_preset_no_leading_zero_pm():
    assert format_clock(_dt(15, 9), "12h") == "3:09 PM"


def test_12h_preset_midnight_is_12_am():
    assert format_clock(_dt(0, 9), "12h") == "12:09 AM"


def test_12h_preset_noon_is_12_pm():
    assert format_clock(_dt(12, 0), "12h") == "12:00 PM"


def test_24h_preset_pads_hour():
    assert format_clock(_dt(15, 9), "24h") == "15:09"
    assert format_clock(_dt(3, 9), "24h") == "03:09"


def test_custom_strftime_passthrough():
    # Any value containing % is a strftime template, rendered verbatim.
    assert format_clock(_dt(15, 9), "%H:%M") == "15:09"


def test_custom_date_format_one_line():
    # A date token in the format renders date + time inline (v1's "date line").
    assert format_clock(_dt(15, 9), "%Y-%m-%d %H:%M") == "2026-06-13 15:09"


def test_unknown_preset_raises():
    with pytest.raises(ValueError, match="12h"):
        format_clock(_dt(15, 9), "12hr")
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_clock.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.widgets.clock'`

- [ ] **Step 3: Implement** — create `src/led_ticker/widgets/clock.py` with just the pure function for now (the widget class lands in Task 2):

```python
"""Clock widget: current time as a held/centered text display.

format_clock is a pure, timezone-agnostic formatter (it formats an
already-localized datetime). Presets are built from datetime fields rather
than via %- strftime codes, which are a libc passthrough Python does not
guarantee — building from fields keeps preset output deterministic across
platforms. A custom format string (containing %) is passed to strftime
verbatim.
"""

from datetime import datetime


def format_clock(now: datetime, fmt: str) -> str:
    """Format `now` per `fmt`: a preset ("12h"/"24h") or a strftime template.

    A value containing "%" is treated as a strftime template. Otherwise it
    must be a known preset keyword; an unknown preset raises ValueError.
    """
    if "%" in fmt:
        return now.strftime(fmt)
    if fmt == "12h":
        hour12 = now.hour % 12 or 12
        meridiem = "AM" if now.hour < 12 else "PM"
        return f"{hour12}:{now.minute:02d} {meridiem}"
    if fmt == "24h":
        return f"{now.hour:02d}:{now.minute:02d}"
    raise ValueError(
        f"clock format {fmt!r} is not a known preset (expected '12h' or '24h') "
        "and is not a strftime template (no '%'). "
        "Use '12h', '24h', or a strftime string like '%H:%M'."
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_clock.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/widgets/clock.py tests/test_widgets/test_clock.py
git add src/led_ticker/widgets/clock.py tests/test_widgets/test_clock.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(clock): format_clock pure formatter (presets + strftime)"
```

---

### Task 2: `Clock` widget + registration

**Files:**
- Modify: `src/led_ticker/widgets/clock.py`
- Modify: `src/led_ticker/widgets/__init__.py`
- Test: `tests/test_widgets/test_clock.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_widgets/test_clock.py`):

```python
from unittest import mock

from led_ticker.widget import Widget
from led_ticker.widgets.clock import Clock


class TestClockWidget:
    def test_registered(self):
        from led_ticker.widgets import get_widget_class

        assert get_widget_class("clock") is Clock

    def test_conforms_to_widget_protocol(self):
        assert isinstance(Clock(), Widget)

    def test_draw_returns_canvas_and_int_cursor(self, canvas):
        result_canvas, cursor_pos = Clock().draw(canvas)
        assert result_canvas is canvas
        assert isinstance(cursor_pos, int)

    def test_draw_uses_format_clock_with_monkeypatched_now(self, canvas, monkeypatch):
        # Pin the clock's time source so draw() renders a known string, then
        # confirm the widget centered the SAME string format_clock produces.
        import led_ticker.widgets.clock as clock_mod
        from led_ticker.drawing import compute_cursor, get_text_width
        from led_ticker.widgets.clock import format_clock

        fixed = datetime(2026, 6, 13, 15, 9)

        class _FrozenDatetime:
            @staticmethod
            def now(tz=None):
                return fixed

        monkeypatch.setattr(clock_mod, "datetime", _FrozenDatetime)
        widget = Clock(format="24h", center=True)
        _, cursor_pos = widget.draw(canvas)

        expected_text = format_clock(fixed, "24h")  # "15:09"
        width = get_text_width(widget.font, expected_text, padding=0, canvas=canvas)
        start, end_padding = compute_cursor(
            canvas.width, width, 0, widget.padding, center=True
        )
        assert cursor_pos == start + width + end_padding

    def test_border_painted_when_set(self, canvas):
        border = mock.Mock()
        Clock(border=border).draw(canvas)
        assert border.paint.called

    def test_rainbow_font_color_advances_frame(self, canvas):
        # A per-char provider drives the per-char branch; advancing the frame
        # changes the hue the provider is asked for (same contract as message).
        widget = Clock(font_color="rainbow")
        widget.draw(canvas)
        widget.advance_frame()
        widget.draw(canvas)  # must not raise; frame_for("font_color") advanced

    def test_timezone_resolved_in_draw(self, canvas, monkeypatch):
        # When timezone is set, draw() calls datetime.now(ZoneInfo(tz)); confirm
        # the tz is threaded through (the now() call receives a tzinfo).
        import led_ticker.widgets.clock as clock_mod

        seen = {}

        class _SpyDatetime:
            @staticmethod
            def now(tz=None):
                seen["tz"] = tz
                return datetime(2026, 6, 13, 15, 9)

        monkeypatch.setattr(clock_mod, "datetime", _SpyDatetime)
        Clock(timezone="America/New_York").draw(canvas)
        assert seen["tz"] is not None  # a ZoneInfo was passed
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_clock.py -q`
Expected: FAIL — `ImportError: cannot import name 'Clock'` (and registry lookup fails).

- [ ] **Step 3a: Implement the `Clock` class** — replace the imports + add the class in `src/led_ticker/widgets/clock.py`. The full file becomes:

```python
"""Clock widget: current time as a held/centered text display.

format_clock is a pure, timezone-agnostic formatter (it formats an
already-localized datetime). Presets are built from datetime fields rather
than via %- strftime codes, which are a libc passthrough Python does not
guarantee — building from fields keeps preset output deterministic across
platforms. A custom format string (containing %) is passed to strftime
verbatim.

The Clock widget mirrors TickerCountdown.draw: it recomputes the time each
draw() (the engine's _hold_ticks redraws held widgets every 50ms tick, so the
display stays current with no special mechanism), then dispatches through the
shared text-render helpers so font_color / font / bg_color / border behave
exactly as on the message widget.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase


def format_clock(now: datetime, fmt: str) -> str:
    """Format `now` per `fmt`: a preset ("12h"/"24h") or a strftime template.

    A value containing "%" is treated as a strftime template. Otherwise it
    must be a known preset keyword; an unknown preset raises ValueError.
    """
    if "%" in fmt:
        return now.strftime(fmt)
    if fmt == "12h":
        hour12 = now.hour % 12 or 12
        meridiem = "AM" if now.hour < 12 else "PM"
        return f"{hour12}:{now.minute:02d} {meridiem}"
    if fmt == "24h":
        return f"{now.hour:02d}:{now.minute:02d}"
    raise ValueError(
        f"clock format {fmt!r} is not a known preset (expected '12h' or '24h') "
        "and is not a strftime template (no '%'). "
        "Use '12h', '24h', or a strftime string like '%H:%M'."
    )


def _coerce_font_color(value: Any) -> ColorProvider:
    """Wrap a raw Color in _ConstantColor so draw() can always call color_for."""
    if not hasattr(value, "color_for"):
        return _ConstantColor(value)
    return value


@register("clock")
@attrs.define
class Clock(FrameAwareBase):
    """Displays the current time. Held/centered; intended for swap-mode sections.

    `format` is a preset ("12h"/"24h") or a strftime template; `timezone` is an
    optional IANA name (default: system local). Reuses the message widget's
    text-render path for color/font/border.
    """

    format: str = "12h"
    timezone: str | None = None
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR),
        converter=_coerce_font_color,
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    # Optional perimeter border — same contract as TickerMessage.border;
    # declaring the field satisfies factories' border-type gate.
    border: Any | None = attrs.field(default=None, kw_only=True)
    _baseline_y: int = attrs.field(init=False, default=-1)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        provider: ColorProvider = font_color or self.font_color

        tz = ZoneInfo(self.timezone) if self.timezone else None
        now = datetime.now(tz)
        text = format_clock(now, self.format)

        content_width = get_text_width(self.font, text, padding=0, canvas=canvas)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, center=self.center
        )

        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y

        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        if provider.per_char:
            cursor_pos += draw_text_per_char(
                canvas,
                self.font,
                cursor_pos,
                baseline_y + y_offset,
                text,
                lambda idx, total: provider.color_for(
                    self.frame_for("font_color"), idx, total
                ),
            )
        else:
            color = provider.color_for(self.frame_for("font_color"), 0, len(text))
            cursor_pos += draw_text(
                canvas, self.font, cursor_pos, baseline_y + y_offset, color, text
            )
        cursor_pos += end_padding
        return canvas, cursor_pos
```

(Note: `font_color="rainbow"` reaches the converter as a string — `_coerce_font_color` only wraps non-providers in `_ConstantColor`, but the TOML path coerces "rainbow" to a Rainbow provider upstream. For the direct-construction test, pass `font_color="rainbow"` only if `_ConstantColor("rainbow")` is acceptable; if the rainbow test needs a real provider, construct it as `Clock(font_color=Rainbow())` importing from `color_providers`. Adjust the test import to whichever the codebase exposes — check `color_providers` for the Rainbow class name and use it directly so `per_char` is True.)

- [ ] **Step 3b: Register via auto-import** — in `src/led_ticker/widgets/__init__.py`, add `clock` to the auto-import tuple (currently `gif, message, rss_feed, still, two_row, weather`):

```python
from led_ticker.widgets import (  # noqa: E402, F401
    clock,
    gif,
    message,
    rss_feed,
    still,
    two_row,
    weather,
)
```

- [ ] **Step 3c: Fix the rainbow test** — if `_coerce_font_color("rainbow")` does not yield a `per_char` provider, change `test_rainbow_font_color_advances_frame` to construct the provider directly. Read `src/led_ticker/color_providers.py` for the rainbow class (e.g. `Rainbow`) and use `Clock(font_color=Rainbow())`. The test only needs a `per_char=True` provider to exercise the per-char branch.

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_clock.py -q`
Expected: PASS (all format + widget tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/widgets/ tests/test_widgets/test_clock.py
git add src/led_ticker/widgets/clock.py src/led_ticker/widgets/__init__.py tests/test_widgets/test_clock.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(clock): Clock widget mirroring TickerCountdown.draw"
```

---

### Task 3: config surface — FIELD_HINTS + validate_config

**Files:**
- Modify: `src/led_ticker/widgets/clock.py` (add `validate_config` classmethod)
- Modify: `src/led_ticker/app/factories.py` (FIELD_HINTS entries)
- Test: `tests/test_widgets/test_clock.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_widgets/test_clock.py`):

```python
class TestClockValidation:
    def test_validate_config_accepts_presets_and_strftime(self):
        assert Clock.validate_config({"format": "12h"}) == []
        assert Clock.validate_config({"format": "24h"}) == []
        assert Clock.validate_config({"format": "%H:%M"}) == []
        assert Clock.validate_config({}) == []  # format defaulted

    def test_validate_config_rejects_unknown_preset(self):
        msgs = Clock.validate_config({"format": "12hr"})
        assert msgs and "12h" in msgs[0]

    def test_validate_config_accepts_valid_timezone(self):
        assert Clock.validate_config({"timezone": "America/New_York"}) == []

    def test_validate_config_rejects_bad_timezone(self):
        msgs = Clock.validate_config({"timezone": "Mars/Phobos"})
        assert msgs and "timezone" in msgs[0].lower()


def test_list_fields_clock_shows_format_and_timezone():
    from led_ticker.app.factories import _list_widget_fields

    out = _list_widget_fields("clock")
    assert "format" in out
    assert "timezone" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_clock.py -q`
Expected: FAIL — `Clock` has no `validate_config`; `--list-fields` lacks hints.

- [ ] **Step 3a: Add `validate_config`** to `Clock` in `src/led_ticker/widgets/clock.py` (add `from zoneinfo import ZoneInfoNotFoundError` to the imports):

```python
    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Value-level checks run at config load (factories._run_validate_config).
        Unknown FIELD names are caught generically elsewhere; this checks values."""
        errors: list[str] = []
        fmt = cfg.get("format", "12h")
        if isinstance(fmt, str) and "%" not in fmt and fmt not in ("12h", "24h"):
            errors.append(
                f"format {fmt!r} is not a known preset ('12h'/'24h') or a "
                "strftime template (no '%')"
            )
        tz = cfg.get("timezone")
        if tz is not None:
            try:
                ZoneInfo(tz)
            except (ZoneInfoNotFoundError, ValueError):
                errors.append(f"timezone {tz!r} is not a valid IANA timezone name")
        return errors
```

(`ZoneInfo` is already imported from Task 2; add `ZoneInfoNotFoundError` to that import line: `from zoneinfo import ZoneInfo, ZoneInfoNotFoundError`.)

- [ ] **Step 3b: Add FIELD_HINTS** — in `src/led_ticker/app/factories.py`, add two entries to the `FIELD_HINTS` dict (place them near the countdown/weather type-specific hints with a `# --- Clock ---` comment):

```python
    # --- Clock ---
    "format": FieldHint(
        '"12h" | "24h" | strftime template',
        'time format: a preset or a strftime string like "%a %b %-d  %-I:%M %p"',
        '"12h"',
    ),
    "timezone": FieldHint(
        "IANA name | none",
        'timezone override, e.g. "America/New_York" (default: system local)',
        "system local",
    ),
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_clock.py -q`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/widgets/clock.py src/led_ticker/app/factories.py tests/test_widgets/test_clock.py
git add src/led_ticker/widgets/clock.py src/led_ticker/app/factories.py tests/test_widgets/test_clock.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(clock): validate_config + --list-fields hints"
```

---

### Task 4: docs, border-drift, full gates, smoke, PR

**Files:**
- Create: `docs/site/src/content/docs/widgets/clock.mdx`
- Create: `docs/content-source/widgets/clock.md`
- Modify: `tests/test_border_surface_drift.py`

- [ ] **Step 1: Border-drift test + fact-pack.** First read an existing fact-pack to copy its shape: `cat docs/content-source/widgets/countdown.md` and `sed -n '1,60p' tests/test_border_surface_drift.py` (find `FACT_PACK_FILES` and the `border` row format it asserts). Then:
  - Create `docs/content-source/widgets/clock.md` mirroring `countdown.md`'s structure, including a `border` row in whatever table/format the drift test parses, plus rows for `format`, `timezone`, `font_color`, `font`, `font_size`, `bg_color`, `center`, `padding`.
  - Add `"clock"` to the `FACT_PACK_FILES` tuple in `tests/test_border_surface_drift.py`.
  - Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_border_surface_drift.py -q` until green (it tells you exactly what the border row must contain).

- [ ] **Step 2: User docs page.** Read `docs/DOCS-STYLE.md` first, and an existing widget page (`docs/site/src/content/docs/widgets/countdown.mdx`) for structure/voice. Create `docs/site/src/content/docs/widgets/clock.mdx`: what it does; the `format` knob (presets + strftime, with the inline-date example and the note that `%-` codes are a Linux-ism for custom formats); `timezone`; the shared color/font/border knobs (cross-link the relevant concept pages); a note that it's intended for `swap`-mode sections (it will scroll in scroll modes); and that stacked date-over-time is a future addition. Add it to the sidebar/nav however sibling widget pages register (check `astro.config.mjs` or the content collection). Run `make docs-lint`; if prettier complains, `cd docs/site && pnpm prettier --write <file>` and re-stage.

- [ ] **Step 3: Full gates** — run and report exact numbers:

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/
uv run --extra dev ruff format --check src/ tests/ 2>&1 | tail -1
PYTHONPATH=tests/stubs uv run pyright src/ 2>&1 | grep -E "^[0-9]+ error"
make docs-lint 2>&1 | tail -3
```
All must pass. If the docs config-options drift test (`tests/test_docs_config_options_drift.py`) flags the new widget, follow its message to reconcile.

- [ ] **Step 4: Smoke test** (throwaway under /tmp, deleted after): write a minimal config.toml with a `swap`-mode section containing a `[[playlist.section.widget]] type = "clock"` (try `format = "24h"`, then a custom `format = "%a %b %d  %H:%M"`, then `timezone = "America/New_York"`, then a bad `timezone = "Mars/Phobos"`); run `PYTHONPATH=tests/stubs:src uv run led-ticker validate /tmp/clock-smoke.toml` and confirm the good configs pass and the bad timezone + a bad `format = "12hr"` each produce a clear error. Also run `PYTHONPATH=tests/stubs:src uv run led-ticker validate --list-fields clock` and confirm `format`/`timezone` appear with their hints. Paste output in the report.

- [ ] **Step 5: Push + PR (do NOT merge — user confirms merges).** PR body: what the clock does + config knobs; the `format` presets-vs-strftime design and the `%-` Linux-ism note; timezone via stdlib zoneinfo (no new dep); that it mirrors `TickerCountdown` and needs no engine change (held widgets redraw every tick); swap-mode-intended (scrolls in scroll modes); merge-isolation from #203; and that it went through an adversarial spec review. Hardware validation step for longboi: drop a `swap` section with a clock into the config, confirm the time displays and updates across the hold; try a custom date format and a tz override.

```bash
git push -u origin feat/clock-widget
gh pr create --title "feat: clock widget (steal #3, part 1)" --body "..."
```

---

## Self-review notes (done at plan-writing time)

- **Spec coverage:** widget shape mirroring countdown (T2), format presets-in-Python + strftime passthrough + tz-agnostic format_clock (T1), tz resolved in draw via zoneinfo (T2), border declared + painted (T2), font_color/font/etc. free via the inherited fields (T2), validate_config for unknown-preset + bad-tz (T3), FIELD_HINTS (T3), the liveness/no-engine-change property (asserted implicitly — held widgets redraw; the monkeypatched-now draw test pins format wiring; no separate engine tripwire needed since the mechanism is the existing _hold_ticks, not new code), scroll-mode caveat (docs T4), both docs trees + border-drift (T4), merge isolation (no shared files with #203). Out-of-scope items (seconds toggle, blink, stacked date, calendar) appear in no task.
- **Type/name consistency:** `format_clock(now: datetime, fmt: str) -> str`; `Clock(format, timezone, font, font_color, bg_color, center, padding, border)`; `validate_config(cls, cfg) -> list[str]`; FIELD_HINTS keys `format`/`timezone`. Used identically across tasks.
- **Known uncertainty flagged inline:** the rainbow provider class name (T2 step 3c — read color_providers and use the real class so per_char is True); the exact fact-pack/border-row format (T4 step 1 — read countdown.md + the drift test and match). Both say to read the real file rather than guess.
- **No engine files touched, no #203 overlap:** clock.py (new), __init__.py (append), factories.py (FIELD_HINTS append), test_border_surface_drift.py (tuple append), new docs + test files. None are files #203 modifies.

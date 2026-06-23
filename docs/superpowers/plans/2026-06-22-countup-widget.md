# Countup Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a core `countup` widget (days since a past date) that shares the countdown render implementation, and make both count widgets disappear from the rotation when out of range (instead of rendering a negative number).

**Architecture:** A new `widgets/count.py` holds a shared `_CountWidget` base plus `TickerCountdown` (moved from `message.py`) and new `TickerCountup`. A duck-typed `should_display()` hook, filtered in `ticker._expand_sources`, drops out-of-range count widgets per pass. A `validate_config_warnings` hook surfaces a non-blocking warning for a wrong-side date.

**Tech Stack:** Python 3.14, attrs, pytest (asyncio mode AUTO — async tests need no marker).

## Global Constraints

- Both `countdown` and `countup` stay in **core** (no plugin).
- `countdown_date` field is **unchanged** — zero config migration for existing countdowns.
- **Days only.** No `direction` param, no hours/minutes, no live-tick, no `expired_text` (YAGNI).
- Out-of-range rule applies to **both** widgets (behavior change: countdown past its date now disappears instead of showing `-N`). Configs stay valid; it's a documented behavior change, not a migration.
- Wrong-side date is a **warning, not an error** (a future countup date can be legitimate).
- No `from __future__ import annotations` (PEP 649 / project rule).
- Run `uv run --extra dev ruff check src/ tests/` before every commit. Local git hook is broken — commit/push with `--no-verify`.
- Run tests with `PYTHONPATH=tests/stubs uv run pytest <path> -q`.

---

### Task 1: `widgets/count.py` — shared base + both widgets

**Files:**
- Create: `src/led_ticker/widgets/count.py`
- Modify: `src/led_ticker/widgets/message.py` (remove `TickerCountdown`, add back-compat re-export, drop now-unused `date` import)
- Modify: `src/led_ticker/widgets/__init__.py` (add `count` to the auto-import tuple)
- Test: `tests/test_widgets/test_count.py` (new)

**Interfaces:**
- Consumes: `FrameAwareBase` (`widgets/_frame_aware.py`), `register` (`widgets/__init__.py`), drawing/text/color helpers (same imports `message.py` uses today).
- Produces:
  - `_CountWidget(FrameAwareBase)` — shared base; method `_days(self) -> int` (NotImplementedError in base), `should_display(self) -> bool` (returns `self._days() >= 0`), and `draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None) -> DrawResult`.
  - `TickerCountdown(_CountWidget)` (`@register("countdown")`) — field `countdown_date: date` (kw_only); `_days()` = `(countdown_date - date.today()).days`.
  - `TickerCountup(_CountWidget)` (`@register("countup")`) — field `countup_date: date` (kw_only); `_days()` = `(date.today() - countup_date).days`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_widgets/test_count.py`:
```python
"""countup/countdown shared-base widgets: _days math, should_display, render."""

from datetime import date, timedelta

import pytest

from led_ticker.widgets.count import TickerCountdown, TickerCountup


def _future(days=10):
    return date.today() + timedelta(days=days)


def _past(days=10):
    return date.today() - timedelta(days=days)


def test_countdown_days_positive_for_future():
    assert TickerCountdown("Launch", countdown_date=_future(5))._days() == 5


def test_countdown_days_zero_today():
    assert TickerCountdown("Launch", countdown_date=date.today())._days() == 0


def test_countdown_days_negative_for_past():
    assert TickerCountdown("Launch", countdown_date=_past(3))._days() == -3


def test_countup_days_positive_for_past():
    assert TickerCountup("Since", countup_date=_past(7))._days() == 7


def test_countup_days_zero_today():
    assert TickerCountup("Since", countup_date=date.today())._days() == 0


def test_countup_days_negative_for_future():
    assert TickerCountup("Since", countup_date=_future(4))._days() == -4


def test_should_display_in_range_true():
    assert TickerCountdown("X", countdown_date=_future(1)).should_display() is True
    assert TickerCountup("X", countup_date=_past(1)).should_display() is True


def test_should_display_out_of_range_false():
    assert TickerCountdown("X", countdown_date=_past(1)).should_display() is False
    assert TickerCountup("X", countup_date=_future(1)).should_display() is False


def test_countup_renders_label_and_count(canvas):
    # The `canvas` fixture (tests/conftest.py:45) is the test stub canvas that
    # writes real pixels; draw() returns the same canvas + an advanced cursor.
    w = TickerCountup("Days", countup_date=_past(42))
    result_canvas, cursor = w.draw(canvas, 0)
    assert result_canvas is canvas
    assert cursor > 0


def test_registered_names():
    from led_ticker.widgets import get_widget_class

    assert get_widget_class("countdown") is TickerCountdown
    assert get_widget_class("countup") is TickerCountup


def test_back_compat_countdown_import():
    # The move must not break the historical import path.
    from led_ticker.widgets.message import TickerCountdown as FromMessage

    assert FromMessage is TickerCountdown
```

The `canvas` fixture is defined in `tests/conftest.py:45` and is the same one the existing `TickerMessage`/`TickerCountdown` draw tests use (`tests/test_widgets/test_message.py`, e.g. `def test_draw_centered(self, canvas)`). No verification needed — use `canvas` directly.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_count.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'led_ticker.widgets.count'`.

- [ ] **Step 3: Create `count.py`**

Create `src/led_ticker/widgets/count.py`:
```python
"""Day-count widgets: TickerCountdown (days until) and TickerCountup (days since).

Both share `_CountWidget`, which owns the full render surface (font, color
provider, border, centering — identical to the old TickerCountdown). The
subclasses differ only by their date field and the sign of `_days()`.

Out of range (countdown past its date / countup before its date) a widget
returns `should_display() == False`; the engine's `_expand_sources` drops it
from the rotation that pass (see ticker.py), so it disappears instead of
rendering a negative number.
"""

from datetime import date
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase


def _coerce_font_color(value: Any) -> ColorProvider:
    """Coerce a raw Color or ColorProvider to a ColorProvider (wraps a raw
    graphics.Color in _ConstantColor so draw() can always call color_for)."""
    if not hasattr(value, "color_for"):
        return _ConstantColor(value)
    return value


@attrs.define
class _CountWidget(FrameAwareBase):
    """Shared base for day-count widgets. Renders `f"{text}: {days}"`; `days`
    comes from the subclass `_days()`. Subclasses add the date field + sign."""

    text: str
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR),
        converter=_coerce_font_color,
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    # Optional perimeter border — same contract as TickerMessage.border.
    border: Any | None = attrs.field(default=None, kw_only=True)
    _baseline_y: int = attrs.field(init=False, default=-1)

    def _days(self) -> int:
        """Signed day distance from today. Subclass responsibility."""
        raise NotImplementedError

    def should_display(self) -> bool:
        """Engine visibility hook (filtered in ticker._expand_sources): a count
        widget shows only while its count is non-negative. Out of range it drops
        from the rotation."""
        return self._days() >= 0

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

        text = f"{self.text}: {self._days()}"

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


@register("countdown")
@attrs.define
class TickerCountdown(_CountWidget):
    """Days until a future date. Disappears from rotation once the date passes."""

    countdown_date: date = attrs.field(kw_only=True)

    def _days(self) -> int:
        return (self.countdown_date - date.today()).days


@register("countup")
@attrs.define
class TickerCountup(_CountWidget):
    """Days since a past date. Hidden until the date arrives, then counts up."""

    countup_date: date = attrs.field(kw_only=True)

    def _days(self) -> int:
        return (date.today() - self.countup_date).days
```

- [ ] **Step 4: Remove `TickerCountdown` from `message.py` and add the re-export**

In `src/led_ticker/widgets/message.py`:
1. Delete the entire `@register("countdown") @attrs.define class TickerCountdown(FrameAwareBase): ... return canvas, cursor_pos` block (the class starting at `class TickerCountdown`).
2. Near the top of the file (after the existing imports, before the first class), add the back-compat re-export:
```python
# TickerCountdown moved to widgets/count.py; keep the historical import path.
from led_ticker.widgets.count import TickerCountdown  # noqa: E402, F401
```
3. Update the module docstring's first line — change `"""Static text widgets: TickerMessage, TickerCountdown, and SegmentMessage."""` to `"""Static text widgets: TickerMessage and SegmentMessage (TickerCountdown re-exported from widgets/count.py)."""`.
4. Run ruff and remove any import that is now unused in `message.py` (the move makes `from datetime import date` unused — delete that line; verify nothing else in `message.py` references `date`).

- [ ] **Step 5: Register `count` in the widget package**

In `src/led_ticker/widgets/__init__.py`, add `count` to the auto-import tuple (so both `@register` decorators run at startup):
```python
from led_ticker.widgets import (  # noqa: E402, F401
    clock,
    count,
    message,
    still,
    two_row,
)
```

- [ ] **Step 6: Run the new tests + the existing countdown tests**

Run:
```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_count.py -q
PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_message.py tests/test_borders.py -q
```
Expected: PASS — new count tests pass, and the existing countdown tests (which construct `TickerCountdown("Days", countdown_date=...)` positionally for `text`, keyword for the date) still pass against the moved class.

- [ ] **Step 7: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/widgets/ tests/test_widgets/test_count.py
git add src/led_ticker/widgets/count.py src/led_ticker/widgets/message.py src/led_ticker/widgets/__init__.py tests/test_widgets/test_count.py
git commit --no-verify -m "feat(widgets): countup + shared _CountWidget base (countdown moved)"
```

---

### Task 2: Skip out-of-range widgets in `_expand_sources`

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_expand_sources` + a `_displayable` helper)
- Test: `tests/test_ticker_expand_sources.py` (new)

**Interfaces:**
- Consumes: `should_display()` from Task 1's count widgets (duck-typed — most widgets don't define it).
- Produces: `_expand_sources` now drops any widget (or container story) whose `should_display()` returns `False`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ticker_expand_sources.py`:
```python
"""_expand_sources drops widgets that opt out of a pass via should_display()."""

from datetime import date, timedelta

from led_ticker.ticker import _expand_sources
from led_ticker.widgets.count import TickerCountdown, TickerCountup


class _Plain:
    """A widget with no should_display() — always shown."""


class _Hidden:
    def should_display(self):
        return False


class _Shown:
    def should_display(self):
        return True


def test_widget_without_should_display_is_kept():
    w = _Plain()
    assert _expand_sources([w]) == [w]


def test_should_display_false_is_dropped():
    assert _expand_sources([_Hidden()]) == []


def test_should_display_true_is_kept():
    w = _Shown()
    assert _expand_sources([w]) == [w]


def test_out_of_range_countdown_is_dropped():
    # Behavior change: a countdown past its date now disappears (was: rendered -N).
    past = TickerCountdown("X", countdown_date=date.today() - timedelta(days=1))
    assert _expand_sources([past]) == []


def test_in_range_countup_is_kept():
    cu = TickerCountup("X", countup_date=date.today() - timedelta(days=1))
    assert _expand_sources([cu]) == [cu]


def test_should_display_raising_keeps_widget():
    class _Boom:
        def should_display(self):
            raise RuntimeError("boom")

    w = _Boom()
    # A visibility check must never crash the render loop or silently hide content.
    assert _expand_sources([w]) == [w]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_expand_sources.py -q`
Expected: FAIL — the out-of-range/hidden cases still return the widget (filter not implemented).

- [ ] **Step 3: Add the filter to `_expand_sources`**

In `src/led_ticker/ticker.py`, add a helper directly above `_expand_sources`:
```python
def _displayable(widget: Any) -> bool:
    """A widget may opt out of a rotation pass via `should_display()` (e.g. an
    out-of-range count widget). Duck-typed: widgets without the method always
    show. A check that raises keeps the widget — a visibility check must never
    crash the render loop or silently hide content."""
    check = getattr(widget, "should_display", None)
    if check is None:
        return True
    try:
        return bool(check())
    except Exception:  # noqa: BLE001 - visibility must not crash the render loop
        return True
```
Then update `_expand_sources` so the appended items are also visibility-filtered (the container itself is expanded, not displayed — filter its stories and the non-container widgets):
```python
    out: list[Any] = []
    for s in sources:
        if breaker is not None and breaker.is_disabled(s):
            continue
        if isinstance(s, Container):
            for story in s.feed_stories:
                if breaker is not None and breaker.is_disabled(story):
                    continue
                if _displayable(story):
                    out.append(story)
        elif _displayable(s):
            out.append(s)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_expand_sources.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the broader ticker suite (no regression — the breaker filter still works)**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_ticker_display.py tests/test_container_refresh.py -q`
Expected: PASS (existing container/breaker filtering unaffected).

- [ ] **Step 6: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/ticker.py tests/test_ticker_expand_sources.py
git add src/led_ticker/ticker.py tests/test_ticker_expand_sources.py
git commit --no-verify -m "feat(engine): _expand_sources skips widgets via should_display()"
```

---

### Task 3: Wrong-side date warning (`validate_config_warnings`)

**Files:**
- Modify: `src/led_ticker/widgets/count.py` (add a `_wrong_side_warning` helper + `validate_config_warnings` + the two class attrs on each widget)
- Test: `tests/test_widgets/test_count.py` (append) and `tests/test_count_validation.py` (new — end-to-end through the validator)

**Interfaces:**
- Consumes: the `validate_config_warnings(cls, cfg, ctx) -> list[str]` advisory hook contract (run by `factories._run_validate_config_warnings` → `collect_validation_warnings` → validate.py rule 55 → `ValidationResult.warnings`). The count widgets are the first **core** widgets to use it (plugins already do).
- Produces: a non-blocking warning when `countdown_date` is in the past / `countup_date` is in the future.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_count.py`:
```python
def test_countup_future_date_warns():
    cfg = {"countup_date": _future(5), "text": "X"}
    msgs = TickerCountup.validate_config_warnings(cfg, None)
    assert len(msgs) == 1 and "future" in msgs[0]


def test_countup_past_date_no_warning():
    cfg = {"countup_date": _past(5), "text": "X"}
    assert TickerCountup.validate_config_warnings(cfg, None) == []


def test_countdown_past_date_warns():
    cfg = {"countdown_date": _past(5), "text": "X"}
    msgs = TickerCountdown.validate_config_warnings(cfg, None)
    assert len(msgs) == 1 and "past" in msgs[0]


def test_countdown_future_date_no_warning():
    cfg = {"countdown_date": _future(5), "text": "X"}
    assert TickerCountdown.validate_config_warnings(cfg, None) == []


def test_wrong_side_warning_ignores_missing_or_nondate():
    assert TickerCountup.validate_config_warnings({"text": "X"}, None) == []
    assert TickerCountdown.validate_config_warnings({"countdown_date": "nope"}, None) == []
```

Create `tests/test_count_validation.py` (end-to-end: the warning reaches `ValidationResult.warnings`):
```python
"""A wrong-side count date surfaces as a non-blocking validation warning."""

from datetime import date, timedelta

from pathlib import Path

from led_ticker.app.factories import collect_validation_warnings
from led_ticker.plugin import ValidationContext


def _ctx():
    # ValidationContext fields (plugin.py): scale, content_height, panel_width,
    # panel_height, config_dir. The count hook ignores ctx, so values are nominal.
    return ValidationContext(
        scale=1,
        content_height=16,
        panel_width=160,
        panel_height=16,
        config_dir=Path("."),
    )


def test_future_countup_surfaces_warning():
    cfg = {
        "type": "countup",
        "text": "Since",
        "countup_date": date.today() + timedelta(days=30),
    }
    warnings = collect_validation_warnings(cfg, _ctx())
    assert any("future" in w for w in warnings)


def test_in_range_countup_no_warning():
    cfg = {
        "type": "countup",
        "text": "Since",
        "countup_date": date.today() - timedelta(days=30),
    }
    assert collect_validation_warnings(cfg, _ctx()) == []
```
The `ValidationContext` fields are pinned above (`scale, content_height, panel_width, panel_height, config_dir`, from `plugin.py`). The count hook ignores `ctx`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_count.py -k warn tests/test_count_validation.py -q`
Expected: FAIL — `validate_config_warnings` doesn't exist on the widgets yet.

- [ ] **Step 3: Add the warning helper + hooks to `count.py`**

In `src/led_ticker/widgets/count.py`, add the helper after `_coerce_font_color`:
```python
def _wrong_side_warning(date_field: str, value: Any, warn_when: str) -> list[str]:
    """One advisory string when a count date sits on the wrong side of today
    (so the widget would be perpetually hidden), else []. `warn_when` is "past"
    (countdown) or "future" (countup)."""
    if not isinstance(value, date):
        return []  # missing / wrong type is reported by other rules
    today = date.today()
    if warn_when == "past" and value < today:
        return [
            f"{date_field} {value.isoformat()} is in the past — this countdown "
            f"won't display (did you mean a countup?)"
        ]
    if warn_when == "future" and value > today:
        return [
            f"{date_field} {value.isoformat()} is in the future — this countup "
            f"won't display until then (did you mean a countdown?)"
        ]
    return []
```
Add the hook to `TickerCountdown` (inside the class body, after `_days`):
```python
    @classmethod
    def validate_config_warnings(cls, cfg: dict[str, Any], ctx: Any) -> list[str]:
        return _wrong_side_warning("countdown_date", cfg.get("countdown_date"), "past")
```
Add the hook to `TickerCountup` (inside the class body, after `_days`):
```python
    @classmethod
    def validate_config_warnings(cls, cfg: dict[str, Any], ctx: Any) -> list[str]:
        return _wrong_side_warning("countup_date", cfg.get("countup_date"), "future")
```
(`isinstance(value, date)` also matches `datetime` — fine; `tomllib` parses a bare `YYYY-MM-DD` to `datetime.date`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_count.py tests/test_count_validation.py -q`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/widgets/count.py tests/test_widgets/test_count.py tests/test_count_validation.py
git add src/led_ticker/widgets/count.py tests/test_widgets/test_count.py tests/test_count_validation.py
git commit --no-verify -m "feat(widgets): wrong-side date warning for count widgets"
```

---

### Task 4: Docs + example config

**Files:**
- Create: `docs/site/src/content/docs/widgets/countup.mdx`
- Modify: `docs/site/src/content/docs/widgets/countdown.mdx` (note the disappear-when-past behavior)
- Modify: an example config — `config/config.example.toml` (add a `countup` widget block)
- (Check) `docs/site/src/content/docs/widgets/` sidebar/index for where widget pages are listed

**Interfaces:** none (docs + example only).

- [ ] **Step 1: Read the existing countdown docs page to mirror its structure**

Run: `cat docs/site/src/content/docs/widgets/countdown.mdx`
Note its frontmatter, section order, example block, and any `<Aside>` usage — the countup page must mirror it. Follow `docs/DOCS-STYLE.md` (no padded openers, no "comprehensive/robust/seamlessly", no release-history framing, no "footgun"/gun metaphors).

- [ ] **Step 2: Create the countup docs page**

Create `docs/site/src/content/docs/widgets/countup.mdx` mirroring the countdown page's structure, with:
- Frontmatter `title: Count up` (match the countdown page's frontmatter shape exactly).
- One-line intro: counts the days since a past date.
- A TOML example:
```toml
[[section.widgets]]
type = "countup"
text = "Days since launch"
countup_date = 2026-01-01
```
- The shared styling knobs (font, font_color, border, center, padding, bg_color) — link to or mirror how the countdown page documents them rather than re-explaining each (DRY).
- A short note: while the date is still in the future the widget does not display (and a config-load warning is emitted); once the date arrives it shows `0`, then counts up.

- [ ] **Step 3: Update the countdown docs page**

In `docs/site/src/content/docs/widgets/countdown.mdx`, add a sentence (in the page's existing voice) documenting the behavior change: once the target date has passed, the countdown no longer displays (previously it showed a negative number). Cross-link to the new countup page ("counting up from a past date → see Count up").

- [ ] **Step 4: Add a countup block to the example config**

In `config/config.example.toml`, add a `countup` widget to an existing section (mirror the format of the existing `countdown` block if present; otherwise add a minimal section). Use a clearly-past date so the example renders, e.g.:
```toml
[[sections.widgets]]
type = "countup"
text = "Open for"
countup_date = 2024-01-01
```
Match the exact section/array-of-tables key style already used in that file (check whether it uses `[[sections.widgets]]` or `[[section.widgets]]`).

- [ ] **Step 5: Build the docs + run docs lint**

Run:
```bash
make docs-build
make docs-lint
```
Expected: build succeeds; docs-lint reports 0 errors. If a widget-page index/sidebar must list the new page explicitly (check `astro.config`/sidebar config or whether pages auto-list), add the entry and rebuild.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/content/docs/widgets/countup.mdx docs/site/src/content/docs/widgets/countdown.mdx config/config.example.toml
git commit --no-verify -m "docs: countup widget page + countdown behavior note + example"
```

---

## Final verification (before opening the PR)

- [ ] **Full suite + lint + docs**

Run:
```bash
uv run --extra dev ruff check src/ tests/
uv run pytest -q
make docs-lint
```
Expected: ruff clean; full suite passes (existing countdown tests pass against the moved class; new count/expand/validation tests pass); docs-lint clean.

- [ ] **Open the PR** (branch off main; do NOT merge without explicit user go-ahead). Summarize: new core `countup` widget + shared `_CountWidget` base (countdown moved, back-compat re-export); out-of-range count widgets skip the rotation via `should_display()` + `_expand_sources` (behavior change: countdown past its date disappears); non-blocking wrong-side date warning; docs + example.

## Self-Review notes (spec coverage)

- Spec §1 (two widgets, shared base, both core, `countdown_date` unchanged, back-compat re-export, `__init__` import) → Task 1.
- Spec §2 (`should_display()` + `_expand_sources` filter, duck-typed, all-skipped-section safe, general hook) → Tasks 1 (method) + 2 (filter + behavior-change tripwire). All-skipped-section safety relies on the existing empty-section handling (`None` sentinel in `_run_swap`) — Task 2's `test_out_of_range_countdown_is_dropped` proves `_expand_sources` returns `[]`; the engine's empty handling is already covered by existing tests, so no new engine code is added for it (matches the spec's "relies on existing handling").
- Spec §3 (wrong-side warning via `validate_config_warnings`, severity warning, surfaces in the validation result) → Task 3.
- Spec §4 scope (days only, no direction/hours/expired_text) → enforced by omission; behavior-change documented → Task 4 Step 3.
- Spec Docs section → Task 4. Spec Testing bullets → Tasks 1–3 test steps (the behavior-change tripwire is `test_out_of_range_countdown_is_dropped`).
- Spec Risks (behavior change, visibility seam non-raising, all-skipped section) → Task 2 (`_displayable` keeps-on-error; the raising-widget test) + the empty-section note above.

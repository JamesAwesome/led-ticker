# Per-Section `start_hold` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `start_hold: float | None` as a per-section field on `SectionConfig`. When set, it overrides the playlist-wide `[title] delay` for that section only. Validation rule 25 rejects the field on `swap` / `gif` sections (no runtime effect) and on negative values.

**Architecture:** One new field on `SectionConfig`. Three touch points: config parsing, app wiring, validator. Two test files plus a meta-tripwire update. Four docs pages. No changes to `Ticker` or `_scroll_and_delay` — the existing `if delay:` short-circuit in `_scroll_side_by_side` already handles `start_hold = 0`.

**Tech Stack:** Python 3.13, pytest, `@dataclass` (`attrs.Factory` for defaults), `tomllib` for parsing. Docs in Astro Starlight MDX.

**Spec reference:** `docs/superpowers/specs/2026-05-13-per-section-start-hold-design.md`.

---

## Pre-flight

Use `superpowers:using-git-worktrees` to create an isolated workspace. Suggested name: `start-hold-per-section`. Run `make test` baseline to confirm clean state (1492 passing, 2 skipped at HEAD).

---

### Task 1: Add `start_hold` field to `SectionConfig` and TOML parser

**Files:**
- Modify: `src/led_ticker/config.py:45-86` (`SectionConfig` dataclass)
- Modify: `src/led_ticker/config.py:191-204` (section loader)
- Modify: `tests/test_docs_config_options_drift.py:65-78` (DOCUMENTED_KEYS["section"] set)
- Test: `tests/test_config.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
import textwrap
from pathlib import Path

from led_ticker.config import load_config


def _write_cfg(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_section_start_hold_defaults_to_none(tmp_path):
    cfg = _write_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    assert app.sections[0].start_hold is None


def test_section_start_hold_parses_zero(tmp_path):
    cfg = _write_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    assert app.sections[0].start_hold == 0.0


def test_section_start_hold_parses_positive_float(tmp_path):
    cfg = _write_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = 2.5

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    assert app.sections[0].start_hold == 2.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py::test_section_start_hold_defaults_to_none tests/test_config.py::test_section_start_hold_parses_zero tests/test_config.py::test_section_start_hold_parses_positive_float -v`

Expected: all three FAIL with `AttributeError: 'SectionConfig' object has no attribute 'start_hold'`.

- [ ] **Step 3: Add the field to `SectionConfig`**

In `src/led_ticker/config.py`, add this field to the `SectionConfig` dataclass (immediately after the `scroll_step_ms` field at line 86; preserve the existing block of comments above `scroll_step_ms`):

```python
    # Pre-roll delay before the section's first widget begins scrolling
    # (forever_scroll / infini_scroll only). `None` inherits the
    # playlist-wide `[title] delay`. An explicit value (including 0.0)
    # overrides — set `start_hold = 0.0` to make this section start
    # immediately while leaving the global delay in place for other
    # sections. Has no runtime effect on `swap` / `gif` modes; the
    # validator (rule 25) rejects the field on those.
    start_hold: float | None = None
```

- [ ] **Step 4: Add to the section loader**

In `src/led_ticker/config.py`, inside the `SectionConfig(...)` constructor call (around line 191-204), add the field. Place it adjacent to `scroll_step_ms` so the loader visibly maps each TOML key:

```python
        section = SectionConfig(
            mode=section_raw.get("mode", "forever_scroll"),
            loop_count=section_raw.get("loop_count", 1),
            title=section_raw.get("title"),
            widgets=section_raw.get("widget", []),
            transition=trans,
            transition_specified=transition_specified,
            hold_time=section_raw.get("hold_time", 3.0),
            continuous_scroll=section_raw.get("continuous_scroll", False),
            scale=section_raw.get("scale", display.default_scale),
            content_height=section_raw.get("content_height", 16),
            bg_color=bg_color,
            scroll_step_ms=section_raw.get("scroll_step_ms"),
            start_hold=section_raw.get("start_hold"),
        )
```

- [ ] **Step 5: Update the drift-test allow-list**

In `tests/test_docs_config_options_drift.py`, add `"start_hold"` to the `DOCUMENTED_KEYS["section"]` set (around line 65-78). Place it alphabetically near `scroll_step_ms`. Without this, the meta-tripwire `test_docs_config_options_drift` fails because the new dataclass field has no matching docs row yet.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py::test_section_start_hold_defaults_to_none tests/test_config.py::test_section_start_hold_parses_zero tests/test_config.py::test_section_start_hold_parses_positive_float -v`

Expected: all three PASS.

Run: `uv run pytest tests/test_docs_config_options_drift.py -v`

Expected: the drift test PASSES — the new field is in the allow-list so the test stops complaining about the dataclass / docs mismatch even though we haven't added the docs row yet. (We'll add the docs row in Task 4; the allow-list update prevents Task 1's commit from leaving a red test on main.)

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/config.py tests/test_config.py tests/test_docs_config_options_drift.py
git commit -m "config: add start_hold field to SectionConfig

Per-section pre-roll override for forever_scroll / infini_scroll
sections. None (default) inherits [title] delay; an explicit value
(including 0.0) overrides. Wiring + validation in follow-up commits."
```

---

### Task 2: Wire `section.start_hold` into Ticker's `title_delay` kwarg

**Files:**
- Modify: `src/led_ticker/app.py:907` (`ticker_kwargs["title_delay"]` assignment)
- Test: `tests/test_app.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`. Look at existing tests in that file for the right harness — likely a `monkeypatch`-based `Ticker.__init__` capture pattern. If `test_app.py` has no precedent for asserting `title_delay` flowing into Ticker, use this self-contained shape:

```python
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from led_ticker.app import _build_ticker_kwargs_for_section
from led_ticker.config import load_config


def _write_cfg(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


# NOTE: if `_build_ticker_kwargs_for_section` does not exist as a
# separately importable helper, refactor it out in Step 3 below.
# Otherwise these tests need to drive the full app entrypoint, which
# is more complex.
```

ACTUAL test bodies depend on whether `_build_ticker_kwargs_for_section` exists as a helper. **First check:**

```bash
grep -n "_build_ticker_kwargs_for_section\|ticker_kwargs" src/led_ticker/app.py
```

If the helper doesn't exist, do NOT extract it — testing via the helper extraction is overkill for a one-line plumbing change. Instead, write a smaller-blast test:

```python
async def test_section_start_hold_overrides_title_delay(tmp_path, monkeypatch):
    """When section.start_hold is set, it wins over config.title_delay."""
    from led_ticker import app as app_mod

    captured: dict = {}

    class _CaptureTicker:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def run_forever_scroll(self, *args, **kwargs):
            return None

        async def run_infini_scroll(self, *args, **kwargs):
            return None

        async def run_swap(self, *args, **kwargs):
            return None

    monkeypatch.setattr(app_mod, "Ticker", _CaptureTicker)
    # ... drive the relevant section build path with section.start_hold = 0.0
    # ... assert captured["title_delay"] == 0.0


async def test_section_no_start_hold_inherits_title_delay(tmp_path, monkeypatch):
    """When section.start_hold is None, title_delay flows from [title] delay."""
    # Same shape, with [title] delay = 5 and no section start_hold,
    # assert captured["title_delay"] == 5
```

**The harness above is rough.** The implementer should look at existing `test_app.py` patterns for driving the section build path — if `play_loop` or `run` is the entry point, fixture out a single-section playlist and assert at the Ticker constructor. If patching is awkward, a smaller-grain test on a private helper is preferable to a half-mocked integration test.

**Preferred path if test_app.py has no precedent:** extract the `title_delay` computation into a tiny pure function and unit test that:

```python
# In src/led_ticker/app.py, new helper near RUN_MODES (line 674 area):
def _resolve_title_delay(section_start_hold: float | None, global_delay: int) -> float:
    """Section-level start_hold wins over the playlist-wide [title] delay.

    None means 'inherit'; any explicit value (including 0.0) overrides.
    """
    if section_start_hold is not None:
        return section_start_hold
    return float(global_delay)
```

Then test:

```python
def test_resolve_title_delay_inherits_when_none():
    from led_ticker.app import _resolve_title_delay
    assert _resolve_title_delay(None, 5) == 5.0


def test_resolve_title_delay_zero_overrides():
    from led_ticker.app import _resolve_title_delay
    # 0.0 explicitly set must NOT fall through to the global default.
    # This is the load-bearing case for the whole feature.
    assert _resolve_title_delay(0.0, 5) == 0.0


def test_resolve_title_delay_positive_overrides():
    from led_ticker.app import _resolve_title_delay
    assert _resolve_title_delay(1.5, 5) == 1.5
```

This is the recommended path. Three short pure-function tests beat one fragile integration test.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_app.py -k "title_delay" -v`

Expected: tests FAIL with `ImportError: cannot import name '_resolve_title_delay'`.

- [ ] **Step 3: Add the helper to `src/led_ticker/app.py`**

Add the `_resolve_title_delay` function near the `RUN_MODES` dict (around line 674):

```python
def _resolve_title_delay(section_start_hold: float | None, global_delay: int) -> float:
    """Section-level start_hold wins over the playlist-wide [title] delay.

    None means 'inherit'; any explicit value (including 0.0) overrides.
    """
    if section_start_hold is not None:
        return section_start_hold
    return float(global_delay)
```

- [ ] **Step 4: Replace the existing wiring**

In `src/led_ticker/app.py`, find the `ticker_kwargs["title_delay"]` assignment (around line 907):

```python
"title_delay": config.title_delay,
```

Replace with:

```python
"title_delay": _resolve_title_delay(section.start_hold, config.title_delay),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py -k "title_delay" -v`

Expected: all three PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "app: section.start_hold overrides config.title_delay

_resolve_title_delay returns section.start_hold when set (including
0.0), else falls through to the playlist-wide [title] delay. Plumbing
only — runtime _scroll_and_delay already short-circuits at delay=0."
```

---

### Task 3: Add validate rule 25 (`start_hold` on wrong mode + negative)

**Files:**
- Modify: `src/led_ticker/validate.py` (inside `_check_static`)
- Test: `tests/test_validate.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_validate.py` (use the existing `conf` fixture):

```python
async def test_rule25_start_hold_on_swap_section_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 25 for e in result.errors), (
        f"expected rule 25 error; got {[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule25_start_hold_on_gif_section_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "gif"
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 25 for e in result.errors)


async def test_rule25_start_hold_on_forever_scroll_is_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 25 for e in result.errors), (
        f"start_hold on forever_scroll must validate clean; got errors: "
        f"{[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule25_start_hold_on_infini_scroll_is_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "infini_scroll"
        start_hold = 2.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 25 for e in result.errors)


async def test_rule25_negative_start_hold_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = -1.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 25 for e in result.errors)


async def test_rule25_zero_start_hold_is_allowed(conf):
    # Exact zero is the load-bearing case for the whole feature — must NOT trip
    # the negative-value error path.
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert result.valid is True
    assert all(e.rule != 25 for e in result.errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validate.py -k "rule25" -v`

Expected: 4 of 6 FAIL. (The two `is_allowed` tests pass vacuously; the others fail because rule 25 doesn't exist yet.)

- [ ] **Step 3: Add rule 25 to `_check_static`**

In `src/led_ticker/validate.py`, the `_check_static` function has an outer `for i, section in enumerate(config.sections)` loop starting around line 113. The widget-level checks live inside that loop's inner `for j, widget_cfg in ...`. Add the section-level rule 25 check BEFORE the widget loop, at the top of the section loop body. The full insertion:

```python
def _check_static(config: AppConfig) -> list[ValidationIssue]:
    """Synchronous checks on raw widget dicts for errors not caught by _build_widget."""
    issues: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        # Rule 25: start_hold is only meaningful on scroll modes
        # (forever_scroll / infini_scroll), which are the only modes
        # that call _scroll_and_delay. Setting it on swap / gif has
        # no runtime effect — surface as an error so users don't think
        # they're tuning something they're not.
        if section.start_hold is not None:
            if section.mode in ("swap", "gif"):
                issues.append(
                    ValidationIssue(
                        rule=25,
                        location=f"section[{i}]",
                        severity="error",
                        message=(
                            f"start_hold has no effect on mode={section.mode!r};"
                            " only forever_scroll / infini_scroll honor it."
                        ),
                        fix=(
                            "Remove start_hold. For swap mode, use hold_time"
                            " (per-widget hold). For gif mode, the gif's own"
                            " duration controls timing."
                        ),
                    )
                )
            elif section.start_hold < 0:
                issues.append(
                    ValidationIssue(
                        rule=25,
                        location=f"section[{i}]",
                        severity="error",
                        message=(
                            f"start_hold must be >= 0; got {section.start_hold}"
                        ),
                        fix="Set start_hold to 0 or a positive number of seconds.",
                    )
                )

        for j, widget_cfg in enumerate(section.widgets):
            loc = f"section[{i}].widget[{j}]"
            wtype = widget_cfg.get("type", "")

            # Rule 3: scroll + stretch.
            # ...rest of existing function unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -k "rule25" -v`

Expected: all 6 PASS.

Run: `uv run pytest tests/test_validate.py -v` to confirm no regressions in other rules.

Expected: all PASS (current state is 48 tests; should be 54 after the six new ones).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "validate: rule 25 — start_hold only valid on scroll modes

start_hold has no runtime effect on mode='swap' / 'gif' (neither
calls _scroll_and_delay). Reject at validate time so users don't
silently configure a no-op. Also reject negative values."
```

---

### Task 4: Update docs

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx:68-82` (per-section table)
- Modify: `docs/site/src/content/docs/pitfalls.mdx` (rule 25 entry)
- Modify: `docs/site/src/content/docs/tools/validate.mdx` (table row)
- Modify: `docs/site/src/content/docs/concepts/sections-and-modes.mdx` if such a page exists; otherwise check `playback.mdx` or similar concept page

- [ ] **Step 1: Add row to config-options.mdx**

In `docs/site/src/content/docs/reference/config-options.mdx`, find the per-section field table (starts around line 68 with `| Field | Type | Default | Notes |`). Add this row between `scroll_step_ms` (line 80) and `transition_specified` (line 81):

```markdown
| `start_hold`           | float          | `null` (inherits `[title] delay`) | Pre-roll delay (seconds) before this section's first widget begins scrolling. Only honored on `forever_scroll` / `infini_scroll`. Setting it on `swap` / `gif` is a validation error. `start_hold = 0.0` makes the section start scrolling immediately, leaving the global `[title] delay` unchanged for other sections.                  |
```

Keep the column alignment by adjusting trailing spaces. Run `pnpm run format` from `docs/site/` after if alignment matters.

- [ ] **Step 2: Add rule 25 entry to pitfalls.mdx**

In `docs/site/src/content/docs/pitfalls.mdx`, find the Errors section. Add this entry after rule 22 (the last existing error rule):

```markdown
### Rule 25 — `start_hold` is only valid on scroll modes

`start_hold` controls the pre-roll delay before a `forever_scroll` / `infini_scroll` section's first widget begins moving. It calls into `_scroll_and_delay`, which `swap` and `gif` modes don't use. Setting `start_hold` on a `swap` / `gif` section would silently do nothing — the validator rejects it so the misconfiguration surfaces immediately. For `swap` mode, the per-widget hold is `hold_time`. For `gif` mode, the gif's own duration controls timing. Also rejected: `start_hold < 0`.
```

- [ ] **Step 3: Add rule 25 row to validate.mdx**

In `docs/site/src/content/docs/tools/validate.mdx`, find the table around line 135-145. Add this row in the errors section (before the warnings rows that start with `two_row` widget at `scale = 4`):

```markdown
| `start_hold` on `swap` / `gif` section or negative value         | error    | remove `start_hold` or set it to ≥ 0              |
```

- [ ] **Step 4: Check the concepts page**

```bash
ls docs/site/src/content/docs/concepts/
```

If a page named `sections-and-modes.mdx` or `playback.mdx` exists and discusses forever_scroll / infini_scroll pre-roll behavior, add a sentence near the existing prose on those modes:

> By default a section's first widget scrolls in from the right edge and pauses for `[title] delay` seconds before the side-by-side stream begins. Override per section with `start_hold` — for example, `start_hold = 0` on a marquee section that should start moving immediately.

If no such page exists, skip. Don't create a new page for one sentence.

- [ ] **Step 5: Lint and verify docs build**

Run from the worktree root:

```bash
make docs-lint
make docs-build
```

Expected: both PASS.

- [ ] **Step 6: Run the meta-tripwire to confirm docs ↔ dataclass alignment**

```bash
uv run pytest tests/test_docs_config_options_drift.py -v
```

Expected: PASS. The drift test now sees `start_hold` documented in the table AND in the allow-list — both updated.

- [ ] **Step 7: Commit**

```bash
git add docs/site/src/content/docs/reference/config-options.mdx \
        docs/site/src/content/docs/pitfalls.mdx \
        docs/site/src/content/docs/tools/validate.mdx
# Plus the concepts page if updated in step 4
git commit -m "docs: per-section start_hold + rule 25"
```

---

### Task 5: Final verification

**Files:** none modified; verification + cleanup only.

- [ ] **Step 1: Run the full test suite**

```bash
make test
```

Expected: PASS. Test count should be ~1502 (1492 baseline + 3 config + 3 app + 6 validate = 1504, ± any I'm miscounting).

- [ ] **Step 2: Run lint + typecheck + docs-lint**

```bash
make lint
uv run pyright src/
make docs-lint
```

Expected: all PASS.

- [ ] **Step 3: Sweep example configs for unexpected rule-25 hits**

```bash
find config docs/site -name "*.toml" -not -path "*/node_modules/*" 2>/dev/null | while read -r f; do
  out=$(uv run led-ticker validate "$f" --json 2>/dev/null)
  r25=$(echo "$out" | python -c "import json,sys; d=json.load(sys.stdin); print(len([e for e in d.get('errors',[]) if e.get('rule')==25]))" 2>/dev/null || echo 0)
  if [ "$r25" -gt 0 ]; then
    echo "FLAG: $f → $r25 rule-25 error(s)"
  fi
done
echo "sweep done"
```

Expected: zero flagged configs. None of the bundled examples set `start_hold` today, so none should trip the new rule.

- [ ] **Step 4: Smoke-test the user's scenario**

Write a quick test config to `/tmp/start_hold_smoke.toml`:

```toml
[display]
rows = 32
cols = 64
chain = 8
default_scale = 4

[title]
delay = 5

[[playlist.section]]
mode = "forever_scroll"
loop_count = 4
start_hold = 0.0

[[playlist.section.widget]]
type = "message"
text = "K-POP DANCE CLASS  *  NOW OPEN  *  ALL LEVELS"
font_size = 24
```

Run `uv run led-ticker validate /tmp/start_hold_smoke.toml`. Expected: `No issues found.`

- [ ] **Step 5: Use `superpowers:finishing-a-development-branch`** to push + PR.

Title: `validate: per-section start_hold for forever_scroll / infini_scroll (rule 25)`.

Body should include: link to spec, summary of the 4 commits, test plan checkboxes, and a note that the feature is opt-in (no behavior change for configs that don't set `start_hold`).

---

## Self-review

Done after writing all tasks above. Inline notes:

- **Spec coverage:** every requirement in `2026-05-13-per-section-start-hold-design.md` maps to a task. Field + parsing → Task 1. App wiring → Task 2. Rule 25 → Task 3. Docs → Task 4.
- **No placeholders:** all code blocks complete. Test bodies are pasteable. The one fuzzy spot is Task 2 Step 1 — there's an "ACTUAL test bodies depend on" branch, but the recommended path is spelled out concretely and the implementer is told to choose the recommended path when in doubt.
- **Type consistency:** `start_hold: float | None` everywhere. `_resolve_title_delay` signature uses the same types. Test fixtures use `0.0` (not `0`) so type coercion isn't accidentally exercised.
- **Test naming:** `test_rule25_*` mirrors existing `test_rule3_*` / `test_rule22_*` / `test_rule23_*` conventions.

---

## Tradeoffs explicitly chosen

- **Type of the new field:** `float | None` rather than `float` with default `5.0`. Sentinel-based "inherit from global" is more honest than redundantly copying the global default into every section.
- **Severity:** error, not warning. Existing rules of the same shape (12, 14, 15) are errors. Consistency matters more than leniency.
- **Negative values:** rejected at validate time. The alternative (clamp to 0) silently rewrites user intent.
- **No changes to `Ticker.title_delay` typing:** stays `int` in the class annotation. The `float()` coercion in `_resolve_title_delay` returns a float, and `_scroll_and_delay`'s `delay` param is already `float`, so the type widens informally. Tightening `Ticker.title_delay: float` is a follow-up if pyright ever complains; it doesn't today.

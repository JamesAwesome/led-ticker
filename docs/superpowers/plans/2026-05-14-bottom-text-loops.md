# `bottom_text_loops` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Every subagent prompt MUST instruct the subagent to run `git branch --show-current` as its first action and abort if the result is `main`.**

**Goal:** Add `bottom_text_loops: int = 0` to `TwoRowMessage` and make the engine honor it in the `wraps_forever` branch, so `bottom_text_wrap = true` widgets can declare a minimum number of full cycles before the section transitions. Validation rule 28 rejects negative values and rejects `bottom_text_loops > 0` without `bottom_text_wrap = true`.

**Architecture:** One new attrs field on `TwoRowMessage`. Engine's wrap-forever branch in `ticker.py` extends `n_ticks` on the first iteration using the cycle width that `draw()` already returns. New validate rule 28. Spec calls out the corollary validator unknown-kwarg gap as a related-but-separate follow-up.

**Tech Stack:** Python 3.13, pytest, attrs, `tomllib`. Docs in Astro Starlight MDX.

**Spec reference:** `docs/superpowers/specs/2026-05-14-bottom-text-loops-design.md`.

---

## Pre-flight

The worktree `worktree-bottom-text-loops` already exists at `.claude/worktrees/bottom-text-loops/`. Subagents work in that directory. Run `make test` baseline before Task 1 to confirm clean state.

---

### Task 1: Add `bottom_text_loops` field + post-init validation

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py` — add field next to `bottom_text_wrap` (around line 140); add validation in `__attrs_post_init__`
- Test: `tests/test_widgets/test_two_row_wrap.py` — 4 new widget-level tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_widgets/test_two_row_wrap.py`:

```python
def test_bottom_text_loops_defaults_to_zero():
    """Today's behavior preserved: default 0 means no minimum."""
    from led_ticker.widgets.two_row import TwoRowMessage

    m = TwoRowMessage(top_text="top", bottom_text="bottom")
    assert m.bottom_text_loops == 0


def test_bottom_text_loops_with_wrap_constructs_cleanly():
    """Setting bottom_text_loops > 0 alongside bottom_text_wrap=True is the happy path."""
    from led_ticker.widgets.two_row import TwoRowMessage

    m = TwoRowMessage(
        top_text="top",
        bottom_text="bottom",
        bottom_text_wrap=True,
        bottom_text_loops=4,
    )
    assert m.bottom_text_loops == 4
    assert m.bottom_text_wrap is True


def test_bottom_text_loops_without_wrap_raises():
    """The field is only meaningful in wrap mode. Without wrap, the bottom
    row scrolls once over its overflow — there's no concept of 'cycle'.
    Mirrors the existing validation for bottom_text_separator on the
    same widget."""
    import pytest
    from led_ticker.widgets.two_row import TwoRowMessage

    with pytest.raises(ValueError, match="bottom_text_wrap"):
        TwoRowMessage(
            top_text="top",
            bottom_text="bottom",
            bottom_text_loops=4,
            # bottom_text_wrap defaults to False
        )


def test_bottom_text_loops_negative_raises():
    """Mirrors _BaseImageWidget.text_loops < 0 check."""
    import pytest
    from led_ticker.widgets.two_row import TwoRowMessage

    with pytest.raises(ValueError, match="bottom_text_loops"):
        TwoRowMessage(
            top_text="top",
            bottom_text="bottom",
            bottom_text_wrap=True,
            bottom_text_loops=-1,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_widgets/test_two_row_wrap.py -k "bottom_text_loops" -v`

Expected: all four FAIL — `bottom_text_loops` field doesn't exist yet.

- [ ] **Step 3: Add the field to `TwoRowMessage`**

In `src/led_ticker/widgets/two_row.py`, after the existing `bottom_text_separator_color` field (around line 142), add:

```python
    # Minimum wrap cycles the bottom row must complete before the section
    # can end. 0 (default) preserves today's behavior — engine timing is
    # controlled by section `hold_time` alone. > 0 raises the floor:
    # engine runs at least `bottom_text_loops × cycle_width` ticks
    # (one cycle = bottom_text + separator). Mirrors `text_loops` on
    # `_BaseImageWidget` two-row mode. Only meaningful when
    # `bottom_text_wrap = True`; rule 28 rejects otherwise.
    bottom_text_loops: int = attrs.field(default=0, kw_only=True)
```

- [ ] **Step 4: Add validation in `__attrs_post_init__`**

In `__attrs_post_init__` (around line 156), after the existing `bottom_text_separator_color` validation block (around line 198), add:

```python
        if self.bottom_text_loops < 0:
            raise ValueError(
                f"bottom_text_loops must be >= 0, got {self.bottom_text_loops!r}"
            )
        if self.bottom_text_loops > 0 and not self.bottom_text_wrap:
            raise ValueError(
                f"bottom_text_loops={self.bottom_text_loops} requires "
                f"bottom_text_wrap=True. Without wrap, the bottom row "
                f"scrolls once over its overflow — there's no cycle to count."
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_widgets/test_two_row_wrap.py -k "bottom_text_loops" -v`

Expected: all 4 PASS.

Run: `uv run pytest tests/test_widgets/test_two_row_wrap.py -v` for regressions.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/two_row.py tests/test_widgets/test_two_row_wrap.py
git commit -m "two_row: add bottom_text_loops field

Per-widget minimum-cycles knob for bottom_text_wrap mode. Default 0
preserves today's behavior. Validation: rejects negative values and
rejects > 0 without bottom_text_wrap=True. Engine cooperation in
follow-up commit."
```

---

### Task 2: Engine cooperation in `_swap_and_scroll`

**Files:**
- Modify: `src/led_ticker/ticker.py` — wrap-forever branch (around line 1027-1042)
- Test: `tests/test_ticker_wraps_forever.py` — new tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ticker_wraps_forever.py`:

```python
async def test_wraps_forever_extends_n_ticks_for_bottom_text_loops():
    """When bottom_text_loops > 0 and N × cycle_width exceeds the
    hold_time-based n_ticks, engine runs the extended count.
    """
    import asyncio
    from unittest.mock import MagicMock

    from led_ticker.ticker import _swap_and_scroll

    # Mock widget: wraps_forever=True, bottom_text_loops=4, cycle_width=10
    # → loops_floor * cycle_width = 40 ticks
    # hold_time=0.5s, scroll_speed=0.05 → 10 ticks from hold_time
    # Final: max(10, 40) = 40 draws expected.
    widget = MagicMock()
    widget.wraps_forever = True
    widget.bottom_text_loops = 4
    widget.bg_color = None
    widget.draw.return_value = (MagicMock(), 10)  # (canvas, cycle_width=10)
    frame = MagicMock()
    frame.matrix.SwapOnVSync = lambda c: c

    await _swap_and_scroll(
        canvas=MagicMock(width=128),
        frame=frame,
        ticker_obj=widget,
        cursor_pos=0,
        hold_time=0.5,
        scroll_speed=0.05,
        continuous=False,
    )

    # Expected at least 40 draw calls (4 loops × 10 cycle_width)
    assert widget.draw.call_count >= 40, (
        f"expected >= 40 draws (4 loops × 10 cycle_width), "
        f"got {widget.draw.call_count}"
    )


async def test_wraps_forever_hold_time_wins_when_longer():
    """When hold_time-derived n_ticks exceeds N × cycle_width, the
    longer duration wins (matches max() semantics).
    """
    from unittest.mock import MagicMock
    from led_ticker.ticker import _swap_and_scroll

    # hold_time=5s, scroll_speed=0.05 → 100 ticks
    # bottom_text_loops=2, cycle_width=10 → 20 ticks
    # max(100, 20) = 100. Don't truncate.
    widget = MagicMock()
    widget.wraps_forever = True
    widget.bottom_text_loops = 2
    widget.bg_color = None
    widget.draw.return_value = (MagicMock(), 10)
    frame = MagicMock()
    frame.matrix.SwapOnVSync = lambda c: c

    await _swap_and_scroll(
        canvas=MagicMock(width=128),
        frame=frame,
        ticker_obj=widget,
        cursor_pos=0,
        hold_time=5.0,
        scroll_speed=0.05,
        continuous=False,
    )

    # hold_time gives 100 ticks; bottom_text_loops gives 20; max is 100.
    assert 95 <= widget.draw.call_count <= 105, (
        f"expected ~100 draws (hold_time wins), "
        f"got {widget.draw.call_count}"
    )


async def test_wraps_forever_bottom_text_loops_zero_uses_hold_time_only():
    """Regression: bottom_text_loops=0 (default) preserves today's exact
    behavior. n_ticks comes purely from hold_time / scroll_speed.
    """
    from unittest.mock import MagicMock
    from led_ticker.ticker import _swap_and_scroll

    # hold_time=0.5s, scroll_speed=0.05 → 10 ticks
    widget = MagicMock()
    widget.wraps_forever = True
    widget.bottom_text_loops = 0
    widget.bg_color = None
    widget.draw.return_value = (MagicMock(), 100)  # Big cycle_width — should be IGNORED
    frame = MagicMock()
    frame.matrix.SwapOnVSync = lambda c: c

    await _swap_and_scroll(
        canvas=MagicMock(width=128),
        frame=frame,
        ticker_obj=widget,
        cursor_pos=0,
        hold_time=0.5,
        scroll_speed=0.05,
        continuous=False,
    )

    # Should be exactly 10 (no extension because bottom_text_loops=0).
    assert widget.draw.call_count == 10, (
        f"expected exactly 10 draws (hold_time only), "
        f"got {widget.draw.call_count}"
    )
```

- [ ] **Step 2: Run tests to verify they fail or skip**

Run: `uv run pytest tests/test_ticker_wraps_forever.py -k "bottom_text_loops or hold_time_wins or zero_uses_hold_time" -v`

Expected: at least one FAILS — the engine doesn't yet honor `bottom_text_loops`. Test 3 may pass coincidentally (today's behavior matches the assertion).

- [ ] **Step 3: Modify the engine's wrap-forever branch**

In `src/led_ticker/ticker.py`, the wrap-forever branch (around lines 1027-1042) currently has:

```python
if getattr(ticker_obj, "wraps_forever", False) is True:
    n_ticks = max(1, int(hold_time / scroll_speed))
    for _ in range(n_ticks):
        _advance_frame_if_supported(ticker_obj)
        reset_canvas(canvas, bg_color)
        canvas, _ = ticker_obj.draw(canvas, cursor_pos=pos)
        canvas = _swap(canvas, frame)
        pos -= 1
        await asyncio.sleep(scroll_speed)
    return canvas, cursor_pos, pos
```

Replace with:

```python
if getattr(ticker_obj, "wraps_forever", False) is True:
    n_ticks = max(1, int(hold_time / scroll_speed))
    loops_floor = getattr(ticker_obj, "bottom_text_loops", 0)
    tick = 0
    while tick < n_ticks:
        _advance_frame_if_supported(ticker_obj)
        reset_canvas(canvas, bg_color)
        # Wrap-mode TwoRowMessage.draw() returns (canvas, cycle_width).
        # Capture it on the first tick to extend n_ticks if the user
        # set bottom_text_loops > 0.
        canvas, cycle_width = ticker_obj.draw(canvas, cursor_pos=pos)
        if tick == 0 and loops_floor > 0 and cycle_width > 0:
            n_ticks = max(n_ticks, loops_floor * cycle_width)
        canvas = _swap(canvas, frame)
        pos -= 1
        await asyncio.sleep(scroll_speed)
        tick += 1
    return canvas, cursor_pos, pos
```

Key changes:
- `for _ in range(n_ticks)` → `while tick < n_ticks` so n_ticks is mutable
- Capture cycle_width from draw's return (was `_` before)
- On tick 0 only, extend n_ticks if bottom_text_loops > 0 and cycle_width is positive

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ticker_wraps_forever.py -k "bottom_text_loops or hold_time_wins or zero_uses_hold_time" -v`

Expected: all 3 PASS.

Run: `uv run pytest tests/test_ticker_wraps_forever.py -v` for regressions.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/ticker.py tests/test_ticker_wraps_forever.py
git commit -m "ticker: wraps_forever branch honors bottom_text_loops

Capture cycle_width from TwoRowMessage.draw()'s existing return value
on the first tick. When bottom_text_loops > 0, extend n_ticks to
max(hold_time_ticks, loops × cycle_width). Default 0 preserves
today's behavior exactly."
```

---

### Task 3: Validator rule 28

**Files:**
- Modify: `src/led_ticker/validate.py` — add rule 28 to `_check_static`
- Test: `tests/test_validate.py` — 4 new rule-28 tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_validate.py`:

```python
async def test_rule27_bottom_text_loops_without_wrap_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "top"
        bottom_text = "bottom"
        bottom_text_loops = 4
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 28 for e in result.errors), (
        f"expected rule 28 error; got {[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule27_bottom_text_loops_negative_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "top"
        bottom_text = "bottom"
        bottom_text_wrap = true
        bottom_text_loops = -1
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 28 for e in result.errors)


async def test_rule27_bottom_text_loops_with_wrap_is_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "top"
        bottom_text = "bottom"
        bottom_text_wrap = true
        bottom_text_loops = 4
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 27 for e in result.errors), (
        f"bottom_text_loops + wrap must validate clean; got errors: "
        f"{[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule27_bottom_text_loops_zero_is_allowed(conf):
    """Default value must not trip the rule."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "top"
        bottom_text = "bottom"
        bottom_text_loops = 0
        """
    result = await validate_config(conf(cfg))
    assert result.valid is True
    assert all(e.rule != 27 for e in result.errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validate.py -k "rule27" -v`

Expected: at least 2 FAIL (negative + without-wrap), 2 pass vacuously.

Note: the without-wrap and negative tests may ALSO trigger Task 1's `__attrs_post_init__` errors if `_build_widget` constructs the widget during validation. Check whether the validator path catches them via the existing build-error machinery. If `_build_widget(validate_only=True)` short-circuits before construction (which it does — see `app.py:666`), the validator will NOT see post-init errors. Rule 28 in `_check_static` is what surfaces them at validate time.

- [ ] **Step 3: Add rule 28 to `_check_static`**

In `src/led_ticker/validate.py`, find `_check_static` (around line 110). In the inner widget loop (`for j, widget_cfg in enumerate(...)`), after the existing widget-type-specific blocks, append a `two_row` block:

```python
            # Rule 28: bottom_text_loops on two_row requires wrap mode
            # (no concept of cycle without wrap separator). Mirrors the
            # post-init validation in TwoRowMessage so the error
            # surfaces at config-load time, not at runtime.
            if wtype == "two_row":
                btl = widget_cfg.get("bottom_text_loops", 0)
                btw = widget_cfg.get("bottom_text_wrap", False)
                if isinstance(btl, int) and btl < 0:
                    issues.append(
                        ValidationIssue(
                            rule=28,
                            location=loc,
                            severity="error",
                            message=(
                                f"bottom_text_loops must be >= 0; got {btl}"
                            ),
                            fix=(
                                "Set bottom_text_loops to 0 or a positive"
                                " integer."
                            ),
                        )
                    )
                elif isinstance(btl, int) and btl > 0 and not btw:
                    issues.append(
                        ValidationIssue(
                            rule=28,
                            location=loc,
                            severity="error",
                            message=(
                                f"bottom_text_loops={btl} requires "
                                f"bottom_text_wrap=true. Without wrap, the "
                                f"bottom row scrolls once over its "
                                f"overflow — there's no cycle to count."
                            ),
                            fix=(
                                "Set bottom_text_wrap = true alongside "
                                "bottom_text_loops, or drop bottom_text_loops."
                            ),
                        )
                    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -k "rule27" -v`

Expected: all 4 PASS.

Run: `uv run pytest tests/test_validate.py -v` for regressions.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "validate: rule 28 — bottom_text_loops requires bottom_text_wrap

Surfaces the TwoRowMessage __attrs_post_init__ check at validate time
so users see the error before deploy. Two conditions:
  - bottom_text_loops < 0 → error
  - bottom_text_loops > 0 with bottom_text_wrap unset → error"
```

---

### Task 4: Docs

**Files:**
- Modify: `docs/site/src/content/docs/widgets/two_row.mdx` — add `bottom_text_loops` field
- Modify: `docs/site/src/content/docs/pitfalls.mdx` — rule 28 entry
- Modify: `docs/site/src/content/docs/tools/validate.mdx` — rule 28 row

NOTE: this feature adds a WIDGET field, not a section field. The drift-test `test_docs_config_options_drift.py` covers section fields only (per the previous PR work). Don't touch it for this PR.

- [ ] **Step 1: Update `two_row.mdx`**

Open `docs/site/src/content/docs/widgets/two_row.mdx`. Find the section that documents `bottom_text_wrap` and related wrap fields (added in PR #59). Add `bottom_text_loops` adjacent to those. Match the existing prose style:

```markdown
### `bottom_text_loops`

Minimum number of full wrap cycles the bottom row must complete before the section can transition. One cycle = `bottom_text` + `bottom_text_separator`. Default `0` means "no minimum" — the section's `hold_time` alone controls duration.

- Requires `bottom_text_wrap = true`. Setting `bottom_text_loops > 0` without wrap is a validation error (rule 28); the bottom row in non-wrap mode scrolls once over its overflow and has no cycle.
- When both `hold_time` and `bottom_text_loops` are set, the engine uses the LONGER of the two ("max" semantics): if `hold_time / scroll_speed_ms` exceeds `bottom_text_loops × cycle_ticks`, hold_time wins.
- Mirrors `text_loops` on `gif` / `image` widgets in two-row mode.
```

Place this near the existing `bottom_text_wrap` / `bottom_text_separator` documentation.

- [ ] **Step 2: Update `pitfalls.mdx`**

After the rule 26 entry (last one added in PR #55), append:

```markdown
### Rule 28 — `bottom_text_loops` requires `bottom_text_wrap`

`bottom_text_loops` on a `two_row` widget controls how many full wrap cycles the bottom row must play before the section ends. A cycle is `bottom_text` + the separator — both only exist when `bottom_text_wrap = true`. In non-wrap mode the bottom row scrolls once over its overflow and there's no cycle to count, so the validator rejects `bottom_text_loops > 0` without wrap. Negative values are also rejected. Either turn on wrap mode, or drop `bottom_text_loops`.
```

- [ ] **Step 3: Update `validate.mdx`**

Add a row to the reference table, in the errors group:

```markdown
| `bottom_text_loops` on `two_row` without `bottom_text_wrap`     | error    | set `bottom_text_wrap = true`, or drop the field   |
```

- [ ] **Step 4: Verify**

```bash
make docs-lint
make docs-build
```

Both PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/site/src/content/docs/widgets/two_row.mdx \
        docs/site/src/content/docs/pitfalls.mdx \
        docs/site/src/content/docs/tools/validate.mdx
git commit -m "docs: bottom_text_loops on two_row + rule 28"
```

---

### Task 5: Final verification + PR

**Files:** none modified; verification + cleanup only.

- [ ] **Step 1: Full test suite**

```bash
make test
```

Expected: PASS. Test count delta: +11 (4 widget + 3 engine + 4 validate).

- [ ] **Step 2: Lint + typecheck + docs-lint**

```bash
make lint
uv run pyright src/
make docs-lint
```

All PASS.

- [ ] **Step 3: Sweep example configs for rule-28 false positives**

```bash
find config docs/site -name "*.toml" -not -path "*/node_modules/*" | while read -r f; do
  out=$(uv run led-ticker validate "$f" --json 2>/dev/null)
  r28=$(echo "$out" | python -c "import json,sys; d=json.load(sys.stdin); print(len([e for e in d.get('errors',[]) if e.get('rule')==27]))" 2>/dev/null || echo 0)
  if [ "$r28" -gt 0 ]; then
    echo "FLAG: $f → $r28 rule-28 error(s)"
  fi
done
echo "sweep done"
```

Expected: zero flagged.

- [ ] **Step 4: Smoke test the moonbunny scenario**

Write `/tmp/bottom_text_loops_smoke.toml`:

```toml
[display]
rows = 32
cols = 64
chain = 8
default_scale = 4
pixel_mapper = "Remap:256,64|U-mapper"

[[playlist.section]]
mode = "swap"
hold_time = 3
scale = 2
content_height = 32

[[playlist.section.widget]]
type = "two_row"
top_text = ":instagram: @moonbunnyaerial"
top_align = "center"
top_font = "Inter-Bold"
top_font_size = 22
bottom_text = "Now booking spring classes — all levels welcome!"
bottom_text_wrap = true
bottom_text_loops = 4
bottom_color = [254, 255, 204]
bottom_font = "Inter-Regular"
bottom_font_size = 24
```

Run: `uv run led-ticker validate /tmp/bottom_text_loops_smoke.toml`. Expected: clean (no rule-28 errors).

Same config but with `bottom_text_wrap` removed: expected to fail with rule 28.

- [ ] **Step 5: Push + PR**

```bash
git push -u origin worktree-bottom-text-loops
gh pr create --title "two_row: bottom_text_loops for minimum wrap cycles (rule 28)" --body "..."
```

PR body should reference both spec and plan, list the 4 task commits, and note the related-but-deferred validator unknown-kwarg gap.

---

## Self-review

- **Spec coverage:** every requirement maps to a task. Field + post-init → Task 1. Engine cooperation → Task 2. Rule 28 → Task 3. Docs → Task 4.
- **No placeholders:** all code blocks pasteable. Test bodies complete with assertions.
- **Type consistency:** `bottom_text_loops: int = 0` everywhere. Engine reads via `getattr(ticker_obj, "bottom_text_loops", 0)` so Mock widgets without the attribute default to 0 (no spurious extension).
- **Subagent contract:** every subagent prompt explicitly tells the subagent to run `git branch --show-current` first and abort if `main`. Cwd should always be the worktree (`.claude/worktrees/bottom-text-loops/`).

## Tradeoffs explicitly chosen

- **No new property/method on TwoRowMessage.** The widget's draw() already returns `(canvas, cycle_width)` in wrap mode. The engine captures that return value on first iteration. One-line API surface change to the engine's existing return-value-discard pattern.
- **First-iteration capture, not pre-draw.** Pre-drawing once to measure cycle width and then drawing again would either render a wasted frame (visible flicker) or require complex caching. First-iteration capture extends `n_ticks` after the first draw is already on-screen — cleanest semantics.
- **Validation in BOTH __attrs_post_init__ AND rule 28.** Defense in depth: validator catches at config-time (clean error message, before runtime); post-init catches direct programmatic widget construction (test paths, etc).

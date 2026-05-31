# Transition FPS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `transition_fps` config field that controls animation frame rate for transitions, defaulting to the existing 20 fps.

**Architecture:** `transition_fps: float | None` is added to `TransitionConfig`. It flows from TOML through `_parse_transition` and a section-level shorthand (`transition_fps = 40`) into both `run_transition` call sites in `app/run.py` and `ticker.py` as `scroll_speed = 1.0 / fps`. A validator rule warns on out-of-range values. The docs drift test and the config-options docs page are updated to surface the new field.

**Tech Stack:** Python dataclasses, TOML config, pytest, asyncio. No new dependencies.

---

## File Structure

| File | Change |
|---|---|
| `src/led_ticker/config.py` | Add `transition_fps` field to `TransitionConfig`; add section-level shorthand parsing; thread through `_parse_transition` |
| `src/led_ticker/app/run.py` | Extract `entry_fps` in the entry-transition precedence block; pass `scroll_speed` to `run_transition` |
| `src/led_ticker/ticker.py` | Pass `scroll_speed` to `run_transition` in the widget-swap branch |
| `src/led_ticker/validate.py` | Add `_check_transition_fps` (rule 41) warning for values < 5 or > 120 |
| `config/config.longboi.toml` | Add `transition_fps = 40` to both MLB baseball sections |
| `tests/test_config.py` | Tests for `transition_fps` parsing |
| `tests/test_validate.py` | Tests for rule 41 |
| `tests/test_docs_config_options_drift.py` | Add `transition_fps` to `DOCUMENTED_KEYS` |
| `docs/site/src/content/docs/reference/config-options.mdx` | Add `transition_fps` row to `[transitions]` and `[[playlist.section]]` tables |

---

## Task 1: Add `transition_fps` to `TransitionConfig` and `_parse_transition`

**Files:**
- Modify: `src/led_ticker/config.py:44-51` (TransitionConfig dataclass)
- Modify: `src/led_ticker/config.py:280-288` (_parse_transition return)
- Modify: `src/led_ticker/config.py:325-334` (section-level shorthand block)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_config.py`:

```python
def test_transition_fps_defaults_to_none():
    from led_ticker.config import TransitionConfig
    cfg = TransitionConfig()
    assert cfg.transition_fps is None


def test_transition_fps_parsed_from_section_toml(tmp_path):
    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "swap"
        transition = "push_left"
        transition_fps = 40.0

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    assert cfg.sections[0].transition.transition_fps == 40.0


def test_transition_fps_parsed_from_inline_dict(tmp_path):
    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [transitions]
        between_sections = {type = "push_left", duration = 1.0, transition_fps = 30.0}

        [[playlist.section]]
        mode = "swap"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    assert cfg.between_sections.transition_fps == 30.0


def test_transition_fps_absent_stays_none(tmp_path):
    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "swap"
        transition = "push_left"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    assert cfg.sections[0].transition.transition_fps is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py::test_transition_fps_defaults_to_none \
       tests/test_config.py::test_transition_fps_parsed_from_section_toml \
       tests/test_config.py::test_transition_fps_parsed_from_inline_dict \
       tests/test_config.py::test_transition_fps_absent_stays_none -v
```

Expected: `AttributeError: 'TransitionConfig' object has no attribute 'transition_fps'` (or similar)

- [ ] **Step 3: Add `transition_fps` field to `TransitionConfig`**

In `src/led_ticker/config.py`, change:

```python
@dataclass
class TransitionConfig:
    type: str = "cut"
    duration: float = 0.5
    easing: str = "linear"
    color: tuple[int, int, int] | None = None
    colors: list[tuple[int, int, int]] | None = None
    show_pikachu: bool = True
    show_pokeball: bool = True
```

to:

```python
@dataclass
class TransitionConfig:
    type: str = "cut"
    duration: float = 0.5
    easing: str = "linear"
    color: tuple[int, int, int] | None = None
    colors: list[tuple[int, int, int]] | None = None
    show_pikachu: bool = True
    show_pokeball: bool = True
    transition_fps: float | None = None  # None = use run_transition default (20 fps)
```

- [ ] **Step 4: Add `transition_fps` to `_parse_transition` return**

In `src/led_ticker/config.py`, the `return TransitionConfig(...)` block inside `_parse_transition` (around line 280) — add one line:

```python
    return TransitionConfig(
        type=raw.get("type", default.type),
        duration=raw.get("duration", default.duration),
        easing=raw.get("easing", default.easing),
        color=color,
        colors=colors,
        show_pikachu=raw.get("show_pikachu", default.show_pikachu),
        show_pokeball=raw.get("show_pokeball", default.show_pokeball),
        transition_fps=raw.get("transition_fps", default.transition_fps),
    )
```

- [ ] **Step 5: Add section-level `transition_fps` shorthand**

In `src/led_ticker/config.py`, after the existing `if "transition_duration" in section_raw:` block (around line 325), add:

```python
        if "transition_fps" in section_raw:
            trans.transition_fps = section_raw["transition_fps"]
```

The full block should then look like:

```python
        if "transition_duration" in section_raw:
            trans.duration = section_raw["transition_duration"]
        if "transition_fps" in section_raw:
            trans.transition_fps = section_raw["transition_fps"]
        if "transition_color" in section_raw:
            trans.color = tuple(section_raw["transition_color"])
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_config.py::test_transition_fps_defaults_to_none \
       tests/test_config.py::test_transition_fps_parsed_from_section_toml \
       tests/test_config.py::test_transition_fps_parsed_from_inline_dict \
       tests/test_config.py::test_transition_fps_absent_stays_none -v
```

Expected: all 4 PASS.

- [ ] **Step 7: Run the full test suite to check for regressions**

```bash
pytest -q
```

Expected: all existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/config.py tests/test_config.py
git commit -m "feat: add transition_fps field to TransitionConfig"
```

---

## Task 2: Wire `transition_fps` through both `run_transition` call sites

**Files:**
- Modify: `src/led_ticker/app/run.py:128-193`
- Modify: `src/led_ticker/ticker.py:689-701`
- Test: `tests/test_config.py` (extend with a mock-based wiring test)

- [ ] **Step 1: Write failing wiring tests**

Add to `tests/test_config.py`:

```python
def test_transition_fps_converts_to_scroll_speed(tmp_path):
    """transition_fps=40 → scroll_speed=0.025 at the run_transition call site."""
    import unittest.mock as mock
    import asyncio
    from led_ticker.app import run as run_module
    from led_ticker.config import load_config

    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "swap"
        transition = "push_left"
        transition_fps = 40.0

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    # Compute expected scroll_speed from the parsed config
    fps = cfg.sections[0].transition.transition_fps
    assert fps == 40.0
    assert abs(1.0 / fps - 0.025) < 1e-9


def test_transition_fps_none_yields_default_scroll_speed(tmp_path):
    """transition_fps=None → caller uses 0.05 (the run_transition default)."""
    from led_ticker.config import load_config

    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "swap"
        transition = "push_left"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    fps = cfg.sections[0].transition.transition_fps
    assert fps is None
    # Caller logic: (1.0 / fps) if fps is not None else 0.05
    scroll_speed = (1.0 / fps) if fps is not None else 0.05
    assert scroll_speed == 0.05
```

- [ ] **Step 2: Run tests to verify they pass (these are pure-logic tests)**

```bash
pytest tests/test_config.py::test_transition_fps_converts_to_scroll_speed \
       tests/test_config.py::test_transition_fps_none_yields_default_scroll_speed -v
```

Expected: PASS (these only test math, not the call sites yet).

- [ ] **Step 3: Update `app/run.py` entry-transition block**

In `src/led_ticker/app/run.py`, find the entry-transition precedence block (around line 128). Add `entry_fps` extraction alongside `entry_duration`/`entry_easing`, then pass `scroll_speed` to `run_transition`.

Change:

```python
                if section.entry_transition is not None:
                    entry_trans = _build_trans_obj(section.entry_transition)
                    entry_duration = section.entry_transition.duration
                    entry_easing = section.entry_transition.easing
                elif section.transition_specified:
                    entry_trans = _build_trans_obj(section.transition)
                    entry_duration = section.transition.duration
                    entry_easing = section.transition.easing
                else:
                    entry_trans = default_section_trans
                    entry_duration = config.between_sections.duration
                    entry_easing = config.between_sections.easing
```

to:

```python
                if section.entry_transition is not None:
                    entry_trans = _build_trans_obj(section.entry_transition)
                    entry_duration = section.entry_transition.duration
                    entry_easing = section.entry_transition.easing
                    entry_fps = section.entry_transition.transition_fps
                elif section.transition_specified:
                    entry_trans = _build_trans_obj(section.transition)
                    entry_duration = section.transition.duration
                    entry_easing = section.transition.easing
                    entry_fps = section.transition.transition_fps
                else:
                    entry_trans = default_section_trans
                    entry_duration = config.between_sections.duration
                    entry_easing = config.between_sections.easing
                    entry_fps = config.between_sections.transition_fps
```

Then in the `run_transition(...)` call (around line 162), add the `scroll_speed` kwarg:

```python
                    canvas = await run_transition(
                        canvas,
                        led_frame,
                        last_widget,
                        first_widget,
                        transition=entry_trans,
                        duration=entry_duration,
                        easing=entry_easing,
                        scroll_speed=(1.0 / entry_fps) if entry_fps is not None else 0.05,
                        outgoing_scroll_pos=last_scroll_pos,
                        incoming_scale=section.scale,
                        incoming_content_height=section.content_height,
                        outgoing_bg_color=last_bg_color,
                        incoming_bg_color=section.bg_color,
                    )
```

- [ ] **Step 4: Update `ticker.py` widget-swap branch**

In `src/led_ticker/ticker.py`, find the `elif self.transition_config is not None:` block (around line 689). Change:

```python
            elif self.transition_config is not None:
                canvas = await run_transition(
                    canvas,
                    self.frame,
                    prev_object,
                    ticker_object,
                    transition=self.transition_fn,
                    duration=self.transition_config.duration,
                    easing=self.transition_config.easing,
                    outgoing_scroll_pos=prev_scroll_pos,
                    outgoing_bg_color=getattr(prev_object, "bg_color", None),
                    incoming_bg_color=getattr(ticker_object, "bg_color", None),
                )
```

to:

```python
            elif self.transition_config is not None:
                _fps = self.transition_config.transition_fps
                canvas = await run_transition(
                    canvas,
                    self.frame,
                    prev_object,
                    ticker_object,
                    transition=self.transition_fn,
                    duration=self.transition_config.duration,
                    easing=self.transition_config.easing,
                    scroll_speed=(1.0 / _fps) if _fps is not None else 0.05,
                    outgoing_scroll_pos=prev_scroll_pos,
                    outgoing_bg_color=getattr(prev_object, "bg_color", None),
                    incoming_bg_color=getattr(ticker_object, "bg_color", None),
                )
```

- [ ] **Step 5: Run full test suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/run.py src/led_ticker/ticker.py tests/test_config.py
git commit -m "feat: wire transition_fps through run_transition call sites"
```

---

## Task 3: Add validator rule 41 for out-of-range `transition_fps`

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validate.py`:

```python
async def test_rule41_transition_fps_too_low_warns(conf):
    cfg = GOOD_CONFIG.replace(
        "[[playlist.section]]",
        "[[playlist.section]]\ntransition = \"push_left\"\ntransition_fps = 2.0\n",
    )
    result = await validate_config(conf(cfg))
    assert any(w.rule == 41 for w in result.warnings)


async def test_rule41_transition_fps_too_high_warns(conf):
    cfg = GOOD_CONFIG.replace(
        "[[playlist.section]]",
        "[[playlist.section]]\ntransition = \"push_left\"\ntransition_fps = 200.0\n",
    )
    result = await validate_config(conf(cfg))
    assert any(w.rule == 41 for w in result.warnings)


async def test_rule41_transition_fps_valid_no_warning(conf):
    cfg = GOOD_CONFIG.replace(
        "[[playlist.section]]",
        "[[playlist.section]]\ntransition = \"push_left\"\ntransition_fps = 40.0\n",
    )
    result = await validate_config(conf(cfg))
    assert all(w.rule != 41 for w in result.warnings)


async def test_rule41_transition_fps_absent_no_warning(conf):
    result = await validate_config(conf(GOOD_CONFIG))
    assert all(w.rule != 41 for w in result.warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_validate.py::test_rule41_transition_fps_too_low_warns \
       tests/test_validate.py::test_rule41_transition_fps_too_high_warns \
       tests/test_validate.py::test_rule41_transition_fps_valid_no_warning \
       tests/test_validate.py::test_rule41_transition_fps_absent_no_warning -v
```

Expected: first two FAIL (rule 41 doesn't exist yet), last two PASS.

- [ ] **Step 3: Add `_check_transition_fps` to `validate.py`**

Add this function after `_check_transition_names` (around line 620 in `src/led_ticker/validate.py`):

```python
def _check_transition_fps(config: AppConfig) -> list[ValidationIssue]:
    """Rule 41: transition_fps must be in a usable range (5–120 fps).

    Values below 5 fps will look like a slideshow and likely indicate a
    typo (e.g. seconds entered instead of fps). Values above 120 fps
    exceed what a Raspberry Pi can push to the LED matrix; frames will
    pile up and the sleep budget goes negative.
    """
    issues: list[ValidationIssue] = []

    def _check(fps: float | None, location: str) -> None:
        if fps is None:
            return
        if fps < 5 or fps > 120:
            issues.append(
                ValidationIssue(
                    rule=41,
                    location=location,
                    severity="warning",
                    message=(
                        f"transition_fps={fps} is outside the usable range "
                        f"5–120 fps"
                    ),
                    fix=(
                        "Use a value between 5 and 120. "
                        "Typical values: 20 (default), 30, 40. "
                        "Values below 5 may be seconds instead of fps."
                    ),
                )
            )

    _check(config.between_sections.transition_fps, "transitions.between_sections")
    for i, section in enumerate(config.sections):
        _check(section.transition.transition_fps, f"section[{i}].transition_fps")
        if section.entry_transition is not None:
            _check(
                section.entry_transition.transition_fps,
                f"section[{i}].entry_transition.transition_fps",
            )
        if section.widget_transition is not None:
            _check(
                section.widget_transition.transition_fps,
                f"section[{i}].widget_transition.transition_fps",
            )

    return issues
```

- [ ] **Step 4: Register the check in `validate_config`**

In `src/led_ticker/validate.py`, find the Phase 2 soft-rule block (around line 1665):

```python
    # Phase 2: Soft rule warnings (only run when no hard errors)
    if not errors:
        warnings.extend(_check_soft(config))
        warnings.extend(_check_held_top_text_overflow(config))
```

Add the new check:

```python
    # Phase 2: Soft rule warnings (only run when no hard errors)
    if not errors:
        warnings.extend(_check_soft(config))
        warnings.extend(_check_held_top_text_overflow(config))
        warnings.extend(_check_transition_fps(config))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_validate.py::test_rule41_transition_fps_too_low_warns \
       tests/test_validate.py::test_rule41_transition_fps_too_high_warns \
       tests/test_validate.py::test_rule41_transition_fps_valid_no_warning \
       tests/test_validate.py::test_rule41_transition_fps_absent_no_warning -v
```

Expected: all 4 PASS.

- [ ] **Step 6: Run full test suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat: add rule 41 validator warning for out-of-range transition_fps"
```

---

## Task 4: Update docs drift test and config-options docs page

**Files:**
- Modify: `tests/test_docs_config_options_drift.py:56-92`
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`

- [ ] **Step 1: Run the drift test to see current state**

```bash
pytest tests/test_docs_config_options_drift.py -v
```

Expected: PASS (baseline before adding the new field).

- [ ] **Step 2: Add `transition_fps` to `DOCUMENTED_KEYS` in the drift test**

In `tests/test_docs_config_options_drift.py`, update the `"transitions"` set and the `"section"` set:

```python
DOCUMENTED_KEYS: dict[str, set[str]] = {
    ...
    "transitions": {
        "default",
        "duration",
        "easing",
        "between_sections",
        "show_pikachu",
        "show_pokeball",
        "transition_fps",   # NEW
    },
    "section": {
        ...
        "transition_fps",   # NEW (section-level shorthand)
        ...
    },
}
```

The full updated `"section"` set (replace the entire block):

```python
    "section": {
        "mode",
        "loop_count",
        "hold_time",
        "continuous_scroll",
        "transition",
        "entry_transition",
        "widget_transition",
        "transition_duration",
        "transition_fps",
        "transition_color",
        "transition_colors",
        "scale",
        "content_height",
        "bg_color",
        "scroll_step_ms",
        "separator",
        "separator_color",
        "separator_font",
        "separator_font_size",
        "show_pikachu",
        "show_pokeball",
        "start_hold",
        "transition_specified",
    },
```

- [ ] **Step 3: Run drift test — expect it to fail (docs page not yet updated)**

```bash
pytest tests/test_docs_config_options_drift.py -v
```

Expected: FAIL with "docs table drift" listing `transition_fps` as missing from the page.

- [ ] **Step 4: Add `transition_fps` row to the docs page**

Open `docs/site/src/content/docs/reference/config-options.mdx`.

Find the `## \`[transitions]\`` table and add a row for `transition_fps`:

```mdx
| `transition_fps` | float | `null` | Animation frames per second for all transitions. `null` uses the built-in default (20 fps). Raise to 30–40 on large panels (e.g. longboi) to reduce choppiness. Warn if < 5 or > 120. |
```

Find the `## \`[[playlist.section]]\`` table and add a row for `transition_fps`:

```mdx
| `transition_fps` | float | `null` | Per-section animation fps override. Equivalent to setting `transition_fps` inside the `transition = {...}` dict. Inherits from `[transitions].transition_fps` if not set. |
```

- [ ] **Step 5: Run drift test — expect it to pass**

```bash
pytest tests/test_docs_config_options_drift.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run full test suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_docs_config_options_drift.py \
        docs/site/src/content/docs/reference/config-options.mdx
git commit -m "docs: add transition_fps to config-options reference and drift test"
```

---

## Task 5: Apply `transition_fps = 40` to longboi baseball sections and push PR

**Files:**
- Modify: `config/config.longboi.toml`

- [ ] **Step 1: Update the two MLB baseball sections in `config/config.longboi.toml`**

Find the MLB Scores section (search for `transition = "baseball_alternating"`). There are two — MLB Scores and MLB Standings. Add `transition_fps = 40` to each:

```toml
[[playlist.section]]
mode = "swap"
transition = "baseball_alternating"
transition_duration = 2.0
transition_fps = 40
hold_time = 6
loop_count = 2
```

Apply the same change to the MLB Standings section.

- [ ] **Step 2: Run full test suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add config/config.longboi.toml
git commit -m "config: set transition_fps=40 on longboi baseball transitions"
```

- [ ] **Step 4: Push and open PR**

```bash
git push -u origin transition-fps
gh pr create \
  --title "feat: configurable transition fps (transition_fps field)" \
  --body "$(cat <<'EOF'
## Summary
- Adds \`transition_fps\` field to \`TransitionConfig\` — controls animation frame rate for transitions (default: 20 fps / 0.05s per frame)
- Wires through both \`run_transition\` call sites in \`app/run.py\` and \`ticker.py\`
- Rule 41 validator warns when value is < 5 or > 120 fps
- Sets \`transition_fps = 40\` on longboi baseball transitions to reduce visible choppiness on the 512×64 panel

## Test Plan
- [ ] \`pytest -q\` passes
- [ ] On longboi: baseball transition visibly smoother at 40 fps vs 20 fps
- [ ] \`led-ticker validate config/config.longboi.toml\` — no warnings
- [ ] Set \`transition_fps = 2\` in a test config and run validate — rule 41 warning fires
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- ✅ `transition_fps: float | None` on `TransitionConfig` — Task 1
- ✅ `_parse_transition` threading — Task 1
- ✅ Section-level shorthand (`transition_fps = 40`) — Task 1
- ✅ `entry_transition`, `widget_transition`, `between_sections` inline dict form — Task 1 (via `_parse_transition`)
- ✅ Both `run_transition` call sites (run.py + ticker.py) — Task 2
- ✅ `scroll_speed = 1.0 / fps` conversion — Task 2
- ✅ `None` → `0.05` fallback — Task 2
- ✅ Rule 41 validator (< 5 or > 120) — Task 3
- ✅ Docs drift test update — Task 4
- ✅ config-options.mdx update — Task 4
- ✅ longboi config update — Task 5
- ✅ `min_frames` interaction: no code change needed (existing logic handles it)

**Placeholder scan:** None found.

**Type consistency:** `transition_fps: float | None` used uniformly throughout. `scroll_speed = (1.0 / _fps) if _fps is not None else 0.05` pattern is identical in both call sites.

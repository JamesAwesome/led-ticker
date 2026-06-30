# Scroll Separator — Phase 2a: color config + geometry/frame + validation + docs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users recolor the `scroll` transition's separator dot via `separator_color` on the transition config — fixing the "jarring white dot" — with the inter-widget scroll path honoring it (incl. animated providers), validation, and docs.

**Architecture:** Add `separator_color` to `TransitionConfig`; `_build_trans_obj` coerces it to a `ColorProvider` and builds a `SeparatorSpec(kind="dot", ...)` passed to `Scroll`. The section-entry scroll path already threads the spec + a derived frame (Phase 1); this plan threads the same spec + derived frame into the inter-widget `_scroll_between`/`_draw_scroll_frame` path. The glyph kind is **Phase 2b** (deferred).

**Tech Stack:** Python 3.14, attrs, pytest, Astro/Markdown docs.

## Global Constraints

- **Color-only this phase.** Only `separator_color` is added to `TransitionConfig`. NO `separator`/`separator_font`/`separator_font_size` (those are the glyph kind — Phase 2b). The separator stays `kind="dot"`.
- **Zero drift on the default:** a scroll transition with no `separator_color` renders the same white 2×2 dot as today (Scroll defaults to `DEFAULT_DOT_SPEC`).
- `separator_color` is honored ONLY by the `scroll` transition; reject it on any other `TransitionConfig` type, across all four homes (`between_sections`, `transition`, `entry_transition`, `widget_transition`).
- `separator_color` accepts the same shapes as widget `font_color`: `[r,g,b]`, `"rainbow"`/`"color_cycle"`/`"shimmer"`, or `{style=...}` — coerced via `_coerce_color_provider`.
- **Docs ship in this PR** (the `tests/test_docs_config_options_drift.py` gate audits `config-options.mdx` against the config dataclasses — a new field without a doc row fails CI).
- Repo workflow: branch `feat/scroll-separator-config`; never commit to `main`; `make dev` once; `uv run --extra dev ruff check` before pushing.

---

## Prerequisite (once)

- [ ] **Worktree venv + branch check**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-sep2 && make dev && git branch --show-current`
Expected: deps install; prints `feat/scroll-separator-config`.

---

### Task 1: `TransitionConfig.separator_color` field + loader parsing

**Files:**
- Modify: `src/led_ticker/config.py` (`TransitionConfig` dataclass; `_parse_transition`; `_BUILTIN_TRANSITION_KEYS`)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `TransitionConfig.separator_color: list[int] | str | dict[str, Any] | None` (raw, uncoerced). Consumed by Tasks 2 + 4.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_transition_separator_color_parsed_and_not_in_extra(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n\n"
        "[[playlist.section]]\nmode='slideshow'\n"
        "widget_transition={type='scroll', separator_color=[80,80,80]}\n"
        "[[playlist.section.widget]]\ntype='message'\ntext='hi'\n"
    )
    from led_ticker.config import load_config

    loaded = load_config(str(cfg))
    wt = loaded.sections[0].widget_transition
    assert wt.type == "scroll"
    assert wt.separator_color == [80, 80, 80]
    # must be a first-class field, NOT swept into plugin `extra`
    assert "separator_color" not in wt.extra
```

(If `load_config`/section access differs, mirror an existing `tests/test_config.py` transition test's setup — keep the three assertions.)

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_config.py::test_transition_separator_color_parsed_and_not_in_extra -v`
Expected: FAIL — `TransitionConfig` has no `separator_color` (AttributeError).

- [ ] **Step 3: Add the field + parse it**

In `src/led_ticker/config.py`, add to the `TransitionConfig` dataclass (after `colors`):

```python
    # Per-transition separator color (the scroll transition's dot). Same shapes
    # as widget `font_color`: [r,g,b], "rainbow"/"color_cycle"/"shimmer", or
    # {style=...}. Honored ONLY by type="scroll"; the validator rejects it on
    # other transition types. Raw/uncoerced here; _build_trans_obj coerces it.
    separator_color: list[int] | str | dict[str, Any] | None = None
```

In `_parse_transition`, add to the `TransitionConfig(...)` constructor call (alongside `color=color`):

```python
        separator_color=raw.get("separator_color"),
```

Find `_BUILTIN_TRANSITION_KEYS` in `config.py` and add `"separator_color"` to it (so it isn't swept into `extra`).

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_config.py::test_transition_separator_color_parsed_and_not_in_extra -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/config.py tests/test_config.py
git add src/led_ticker/config.py tests/test_config.py
git commit -m "feat(config): TransitionConfig.separator_color (raw, scroll-only)"
```

---

### Task 2: `Scroll` accepts a spec; `_build_trans_obj` builds the recolored dot

**Files:**
- Modify: `src/led_ticker/transitions/effects.py` (`Scroll.__init__`)
- Modify: `src/led_ticker/app/factories.py` (`_build_trans_obj`)
- Test: `tests/test_transitions.py`

**Interfaces:**
- Consumes: `TransitionConfig.separator_color` (Task 1).
- Produces: a `Scroll` instance whose `_spec` carries the configured color. Consumed by Task 3 (inter-widget path reads `transition_fn._spec`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_transitions.py`:

```python
class TestScrollSeparatorColor:
    def test_build_trans_obj_scroll_color_sets_spec(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig

        scroll = _build_trans_obj(
            TransitionConfig(type="scroll", separator_color=[80, 80, 80])
        )
        rgb = scroll._spec.color.color_for(0, 0, 1)
        got = rgb if isinstance(rgb, tuple) else (rgb.red, rgb.green, rgb.blue)
        assert got == (80, 80, 80)

    def test_build_trans_obj_scroll_default_is_white_dot(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig
        from led_ticker.separator import DEFAULT_DOT_SPEC

        scroll = _build_trans_obj(TransitionConfig(type="scroll"))
        assert scroll._spec is DEFAULT_DOT_SPEC

    def test_scroll_frame_paints_configured_color(self, canvas, make_widget):
        from led_ticker.separator import SeparatorSpec

        scroll = Scroll(spec=SeparatorSpec(kind="dot", color=(10, 20, 30), size=2))
        scroll.frame_at(0.5, canvas, make_widget(40), make_widget(40))
        colors = {c.args[2:5] for c in canvas.SetPixel.call_args_list}
        assert (10, 20, 30) in colors
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_transitions.py::TestScrollSeparatorColor -v`
Expected: FAIL — `Scroll.__init__` doesn't accept `spec`; `_build_trans_obj` doesn't set it.

- [ ] **Step 3: `Scroll` accepts a spec**

In `src/led_ticker/transitions/effects.py`, change `Scroll.__init__`:

```python
    def __init__(self, *, spec: SeparatorSpec = DEFAULT_DOT_SPEC, **kwargs: Any) -> None:
        self._spec = spec
        self._sep_w: int = scroll_separator_width(self._spec)
        self._gap: int = SCROLL_GAP
```

Add `SeparatorSpec` to the `from led_ticker.separator import (...)` block at the top of `effects.py`.

- [ ] **Step 4: `_build_trans_obj` builds the spec for scroll**

In `src/led_ticker/app/factories.py` `_build_trans_obj`, replace the final `return cls(**kwargs)` block with:

```python
    kwargs: dict[str, Any] = {}
    if trans_cfg.colors is not None:
        kwargs["colors"] = trans_cfg.colors
    elif trans_cfg.color is not None:
        kwargs["color"] = trans_cfg.color
    if trans_cfg.type == "scroll" and trans_cfg.separator_color is not None:
        from led_ticker.app.coercion import _coerce_color_provider
        from led_ticker.separator import SeparatorSpec

        kwargs["spec"] = SeparatorSpec(
            kind="dot",
            color=_coerce_color_provider(trans_cfg.separator_color, "separator_color"),
        )
    return cls(**kwargs)
```

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest tests/test_transitions.py::TestScrollSeparatorColor -v`
Expected: PASS (all 3).

- [ ] **Step 6: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/transitions/effects.py src/led_ticker/app/factories.py tests/test_transitions.py
git add src/led_ticker/transitions/effects.py src/led_ticker/app/factories.py tests/test_transitions.py
git commit -m "feat(scroll): recolor the separator dot via separator_color"
```

---

### Task 3: inter-widget scroll path honors the spec + derived frame

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_draw_scroll_frame` signature; `_scroll_between`)
- Test: `tests/test_ticker_display.py`

**Interfaces:**
- Consumes: `transition_fn._spec` (the `Scroll` instance on the Ticker, set in `run.py`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ticker_display.py`:

```python
class TestScrollBetweenSeparatorColor:
    def test_draw_scroll_frame_uses_spec_color(self):
        from unittest.mock import MagicMock

        from led_ticker.separator import SeparatorSpec
        from led_ticker.ticker import _draw_scroll_frame

        canvas = MagicMock()
        canvas.width, canvas.height = 160, 16
        out, inc = MagicMock(), MagicMock()
        spec = SeparatorSpec(kind="dot", color=(10, 20, 30), size=2)
        _draw_scroll_frame(
            canvas, out, inc,
            outgoing_pos=0, bullet_x=50, incoming_pos=200, clear_start=160,
            spec=spec, frame=0,
        )
        colors = {c.args[2:5] for c in canvas.SetPixel.call_args_list}
        assert (10, 20, 30) in colors
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_ticker_display.py::TestScrollBetweenSeparatorColor -v`
Expected: FAIL — `_draw_scroll_frame()` got an unexpected keyword argument `spec`.

- [ ] **Step 3: Thread spec + frame through the inter-widget path**

In `src/led_ticker/ticker.py`, change `_draw_scroll_frame`'s signature and the render call:

```python
def _draw_scroll_frame(
    canvas: Canvas,
    outgoing: Any,
    incoming: Any,
    outgoing_pos: int,
    bullet_x: int,
    incoming_pos: int,
    clear_start: int,
    spec: SeparatorSpec = DEFAULT_DOT_SPEC,
    frame: int = 0,
) -> None:
```

and replace the `render_separator(...)` line (and its Phase-1 placeholder comment) with:

```python
    render_separator(canvas, bullet_x, frame, spec)
```

Add `SeparatorSpec` to the `from led_ticker.separator import (...)` block in `ticker.py`.

In `_scroll_between`, before the loop, resolve the spec from the transition function; inside the loop, pass `spec` to `scroll_separator_width` and `spec`/`frame` to `_draw_scroll_frame`:

```python
            w = canvas.width
            spec = getattr(self.transition_fn, "_spec", DEFAULT_DOT_SPEC)
            sep_w = scroll_separator_width(spec)
            total_travel = w + sep_w
            for offset in range(total_travel + 1):
                ...
                _draw_scroll_frame(
                    canvas,
                    outgoing_draw,
                    incoming_draw,
                    outgoing_pos,
                    bullet_x,
                    incoming_pos,
                    clear_start,
                    spec=spec,
                    frame=offset,
                )
```

(`bullet_x = w + SCROLL_GAP - offset` is unchanged; the gap is constant.)

- [ ] **Step 4: Run — expect pass + scroll tripwires green**

Run: `uv run pytest tests/test_ticker_display.py::TestScrollBetweenSeparatorColor tests/test_transitions.py -k "Scroll or scroll" -v`
Expected: PASS — new test green; all existing scroll tripwires still green (default spec → white dot, sep_w 14).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/ticker.py tests/test_ticker_display.py
git add src/led_ticker/ticker.py tests/test_ticker_display.py
git commit -m "feat(scroll): inter-widget scroll honors separator spec + derived frame"
```

---

### Task 4: validation — reject `separator_color` on non-scroll transitions

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `TransitionConfig.separator_color` across the four section transition homes.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validate.py` (mirrors the existing rule-26 tests — `async def`, the
`conf` fixture, `await validate_config(...)`, assert on `result.errors`):

```python
async def test_rule57_separator_color_on_non_scroll_transition_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5
        default_scale = 1

        [[playlist.section]]
        mode = "slideshow"
        widget_transition = { type = "dissolve", separator_color = [80, 80, 80] }

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 57 for e in result.errors)


async def test_rule57_separator_color_on_scroll_transition_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5
        default_scale = 1

        [[playlist.section]]
        mode = "slideshow"
        widget_transition = { type = "scroll", separator_color = [80, 80, 80] }

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert not any(e.rule == 57 for e in result.errors)
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_validate.py -k separator_color -v`
Expected: FAIL — no such rule yet (the non-scroll case is not flagged).

- [ ] **Step 3: Add the validation rule**

In `src/led_ticker/validate.py`, in the per-section loop (near the rule-26 separator check), inspect each transition home and reject `separator_color` on a non-scroll type:

```python
        # Rule 57: separator_color is only honored by the scroll transition.
        # Per-section homes; `between_sections` is the GLOBAL default — if it's
        # reachable on the top-level config here, validate it once outside this
        # loop with the same check (confirm the attribute names against
        # SectionConfig / the loaded config in this file).
        for home_name in ("transition", "entry_transition", "widget_transition"):
            trans = getattr(section, home_name, None)
            if trans is None or getattr(trans, "separator_color", None) is None:
                continue
            if trans.type != "scroll":
                issues.append(
                    ValidationIssue(
                        rule=57,
                        location=f"section[{i}].{home_name}",
                        severity="error",
                        message=(
                            f"separator_color is only honored by the scroll "
                            f"transition; {home_name}.type={trans.type!r} ignores it."
                        ),
                        fix=(
                            "Use separator_color only with type='scroll', or remove it."
                        ),
                    )
                )
```

(Confirm `SectionConfig` exposes those four transition homes; mirror the exact attribute names used elsewhere in `validate.py`. `between_sections` may live on the top-level config rather than the section — if so, validate it from wherever the global transition config is reachable, and drop it from this per-section loop.)

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_validate.py -k separator_color -v`
Expected: PASS (both).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/validate.py tests/test_validate.py
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat(validate): reject separator_color on non-scroll transitions"
```

---

### Task 5: docs + drift gate

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx` (`[transitions]` table)
- Modify: `docs/site/src/content/docs/transitions/special.mdx` (scroll note)
- Modify: `tests/test_docs_config_options_drift.py` if its allow-list needs `separator_color` for `TransitionConfig`

- [ ] **Step 1: Run the drift test to see what it demands**

Run: `uv run pytest tests/test_docs_config_options_drift.py -v`
Expected: FAIL — `TransitionConfig.separator_color` is undocumented in the `[transitions]` table (or the test names the exact missing field).

- [ ] **Step 2: Add the `[transitions]` table row**

In `docs/site/src/content/docs/reference/config-options.mdx`, under `## [transitions]`, add a row to the table:

```
| `separator_color`  | list / string  | `null`     | Color of the `scroll` transition's separator dot. Same shapes as a widget `font_color` (`[r,g,b]`, `"rainbow"`, `"color_cycle"`, `{style=…}`). Only honored by `type = "scroll"`; rejected on other transitions. Default white. |
```

- [ ] **Step 3: Add the scroll note in special.mdx**

In `docs/site/src/content/docs/transitions/special.mdx`, under the `scroll` variant, add a short paragraph:

```
The scroll separator is a small white dot by default. Recolor it (e.g. to tone
it down on bright content) with `separator_color` on the transition table —
`transition = { type = "scroll", separator_color = [80, 80, 80] }` — accepting
the same values as a widget `font_color`, including `"rainbow"`.
```

- [ ] **Step 4: Update the drift allow-list if needed**

If `tests/test_docs_config_options_drift.py` carries an explicit allow-list keyed by config object, ensure `separator_color` is associated with `TransitionConfig` / the `[transitions]` table (mirror how `color`/`colors` are handled there).

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest tests/test_docs_config_options_drift.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/content/docs/reference/config-options.mdx docs/site/src/content/docs/transitions/special.mdx tests/test_docs_config_options_drift.py
git commit -m "docs(transitions): document scroll separator_color"
```

---

### Task 6: full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `make test`
Expected: all pass, including the new config/transition/ticker/validate/drift tests; no regression in existing scroll/separator tripwires.

- [ ] **Step 2: Lint**

Run: `uv run --extra dev ruff check src/ tests/ tools/`
Expected: no violations.

- [ ] **Step 3: End-to-end sanity (the actual fix)**

Run:
```bash
uv run python -c "
from led_ticker.app.factories import _build_trans_obj
from led_ticker.config import TransitionConfig
s = _build_trans_obj(TransitionConfig(type='scroll', separator_color='rainbow'))
print('spec kind:', s._spec.kind, '| provider:', type(s._spec.color).__name__)
"
```
Expected: `spec kind: dot | provider: Rainbow` — confirms an animated provider wires through.

---

## Notes

- **Phase 2b (next):** the `glyph` kind — `separator` / `separator_font` / `separator_font_size` on `TransitionConfig`, the glyph render path in `render_separator` (canvas-less width measurement, Color normalization, BDF/hires), and the shared `_resolve_separator_spec` extraction.
- **Phase 3:** the `separator_size` knob (dot/circle) on both homes.
- This phase keeps `kind="dot"` for the scroll separator; the dot's width stays canvas-independent (`size`), so `scroll_separator_width(spec)` at `Scroll.__init__` / `_scroll_between` is correct without a canvas.

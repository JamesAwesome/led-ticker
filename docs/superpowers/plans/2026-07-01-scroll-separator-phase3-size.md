# Scroll Separator — Phase 3: the `separator_size` knob — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `separator_size` config knob controlling the dot/circle filled-shape pixel size — on the scroll transition (dot) AND the ticker-mode section separator (circle, closing the "can't shrink the big circle" gap).

**Architecture:** The renderer already reads `SeparatorSpec.size` (`_render_dot` uses `size`, `_render_circle` uses `size // 2` as radius, `separator_width` returns `size`) — Phase 3 is pure config plumbing. Add `separator_size` to `TransitionConfig` + `SectionConfig`; the shared `_resolve_separator_spec` applies it to the scroll dot; `_CircleBufferMsg` gains a `size` field for the ticker circle; validation + docs extend.

**Tech Stack:** Python 3.14, attrs, pytest, Astro/Markdown docs.

## Global Constraints

- **Builds on Phase 1/2a/2b (merged).** `SeparatorSpec(kind, color, size=2, glyph, font)`; `render_separator` already sizes dot/circle by `spec.size`; `_resolve_separator_spec(*, separator, separator_color, separator_font, separator_font_size, default_kind)` exists (scroll-side).
- **`separator_size` applies to the DOT and CIRCLE kinds only** (filled shapes). On a GLYPH separator it's a no-op (glyph size comes from `separator_font_size`).
- **Zero drift on the default:** no `separator_size` → today's sizes (scroll dot 2, ticker circle 8/radius 4). The default `DEFAULT_DOT_SPEC` identity + circle appearance must be preserved.
- **Positive int, validated.** `separator_size` must be a positive int; reject otherwise.
- **Honored per scope:** the `TransitionConfig` one only by `scroll` (extend rule 57); the `SectionConfig` one only by `ticker` mode (extend rule 26). The ticker circle only exists on the bigsign (scale > 1); on smallsign the separator is a BDF glyph, unaffected by `separator_size` (document this).
- **Docs ship with the fields** (drift gate). Repo workflow: branch `feat/scroll-separator-size`; never `main`; `make dev` once; before pushing, `uv run --extra dev ruff check` AND `uv run pyright src/` must be clean (the pre-push gate runs pyright).

---

## Prerequisite (once)

- [ ] **Worktree venv + branch check**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-sep3 && make dev && git branch --show-current`
Expected: deps install; prints `feat/scroll-separator-size`.

---

### Task 1: `separator_size` config fields (both homes) + loader

**Files:**
- Modify: `src/led_ticker/config.py` (`TransitionConfig`; `SectionConfig`; `_parse_transition`; `_BUILTIN_TRANSITION_KEYS`; the section coercion block)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `TransitionConfig.separator_size: int | None`, `SectionConfig.separator_size: int | None` (raw). Consumed by Tasks 2-4.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_separator_size_parsed_on_both_homes(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n\n"
        "[[playlist.section]]\nmode='ticker'\nseparator_size=4\n"
        "widget_transition={type='scroll', separator_size=3}\n"
        "[[playlist.section.widget]]\ntype='message'\ntext='hi'\n"
    )
    from led_ticker.config import load_config

    section = load_config(str(cfg)).sections[0]
    assert section.separator_size == 4
    assert section.widget_transition.separator_size == 3
    assert "separator_size" not in section.widget_transition.extra
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_config.py::test_separator_size_parsed_on_both_homes -v`
Expected: FAIL — no `separator_size` attribute.

- [ ] **Step 3: Add the fields + parsing**

In `TransitionConfig` (after `separator_font_size`):

```python
    # The scroll transition's dot size in logical px (Phase 3). `None` = default
    # (2). No effect on a glyph separator. Honored ONLY by type="scroll".
    separator_size: int | None = None
```

In `SectionConfig` (after its `separator_font_size`):

```python
    # Ticker-mode separator circle size in logical px (Phase 3). `None` = default
    # (8 → radius 4). Only affects the bigsign hi-res circle; the smallsign BDF
    # "•" is unaffected. Honored ONLY by mode="ticker".
    separator_size: int | None = None
```

In `_parse_transition`'s `TransitionConfig(...)` call add `separator_size=raw.get("separator_size"),` and add `"separator_size"` to `_BUILTIN_TRANSITION_KEYS`.

In the section coercion block (near `"separator_font_size": _maybe("separator_font_size", coerce_int, None),`) add `"separator_size": _maybe("separator_size", coerce_int, None),` — and ensure the SectionConfig constructor call that reads `separator_font=section_raw.get(...)` also passes `separator_size=...` (mirror how `separator_font_size` flows to the dataclass).

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_config.py::test_separator_size_parsed_on_both_homes -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/config.py tests/test_config.py
git add src/led_ticker/config.py tests/test_config.py
git commit -m "feat(config): separator_size on TransitionConfig + SectionConfig"
```

---

### Task 2: scroll dot size — `_resolve_separator_spec` + `_build_trans_obj`

**Files:**
- Modify: `src/led_ticker/app/factories.py` (`_resolve_separator_spec` signature + body; `_build_trans_obj` guard + call)
- Test: `tests/test_transitions.py`

**Interfaces:**
- Consumes: `TransitionConfig.separator_size` (Task 1).
- Produces: a scroll `Scroll._spec` whose `size` reflects `separator_size` (dot kind).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_transitions.py`:

```python
class TestScrollSeparatorSize:
    def test_size_only_sets_dot_size(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig

        scroll = _build_trans_obj(TransitionConfig(type="scroll", separator_size=5))
        assert scroll._spec.kind == "dot"
        assert scroll._spec.size == 5
        assert scroll._sep_w == 6 + 5 + 6  # gap + size + gap

    def test_default_size_unchanged(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig
        from led_ticker.separator import DEFAULT_DOT_SPEC

        assert _build_trans_obj(TransitionConfig(type="scroll"))._spec is DEFAULT_DOT_SPEC

    def test_size_ignored_for_glyph(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig

        scroll = _build_trans_obj(
            TransitionConfig(type="scroll", separator="-", separator_size=5)
        )
        assert scroll._spec.kind == "glyph"  # size does not switch/resize a glyph
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_transitions.py::TestScrollSeparatorSize -v`
Expected: FAIL — `_resolve_separator_spec` has no `separator_size` param.

- [ ] **Step 3: Thread `separator_size` through the resolver**

In `_resolve_separator_spec`, add a keyword param `separator_size: int | None` (place it in the signature after `separator_font_size`). Update the "anything set" early-return and the non-glyph path:

```python
    color_set = separator_color is not None
    size_set = separator_size is not None
    # Defensive: unreachable via _build_trans_obj (guards on ≥1 field set).
    if not glyph_set and not color_set and not size_set:
        return base

    color = (
        _coerce_color_provider(separator_color, "separator_color")
        if color_set
        else RGB_WHITE
    )
    if not glyph_set:
        # color/size-only: keep the default kind, recolored/resized.
        changes: dict[str, Any] = {"color": color}
        if size_set:
            changes["size"] = separator_size
        return attrs.evolve(base, **changes)
    # glyph: separator_size is a no-op (glyph size comes from separator_font_size).
    from led_ticker.fonts import FONT_DEFAULT, resolve_font
    ...
```

In `_build_trans_obj`, extend the scroll guard and the call:

```python
    if trans_cfg.type == "scroll" and (
        trans_cfg.separator_color is not None
        or trans_cfg.separator is not None
        or trans_cfg.separator_font is not None
        or trans_cfg.separator_font_size is not None
        or trans_cfg.separator_size is not None
    ):
        kwargs["spec"] = _resolve_separator_spec(
            separator=trans_cfg.separator,
            separator_color=trans_cfg.separator_color,
            separator_font=trans_cfg.separator_font,
            separator_font_size=trans_cfg.separator_font_size,
            separator_size=trans_cfg.separator_size,
            default_kind="dot",
        )
```

- [ ] **Step 4: Run — expect pass + Phase-2a/2b tests green**

Run: `uv run pytest tests/test_transitions.py -k "TestScrollSeparator" -v`
Expected: PASS (Size + the Color/Glyph tests from earlier phases — default identity + color-only dot + glyph all intact).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/app/factories.py tests/test_transitions.py
git add src/led_ticker/app/factories.py tests/test_transitions.py
git commit -m "feat(scroll): separator_size resizes the scroll dot"
```

---

### Task 3: ticker circle size — `_CircleBufferMsg` + `_resolve_buffer_msg`

**Files:**
- Modify: `src/led_ticker/ticker.py` (`_CircleBufferMsg` gains a `size` field; `draw` threads it)
- Modify: `src/led_ticker/app/factories.py` (`_resolve_buffer_msg` — include `separator_size` in the "set" gate + pass `size` to the circle)
- Test: `tests/test_ticker.py` (or `test_ticker_display.py`)

**Interfaces:**
- Consumes: `SectionConfig.separator_size` (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ticker.py` (mirror `test_circle_buffer_msg_hires_path_paints_circle`):

```python
def test_circle_buffer_msg_size_shrinks_circle():
    """separator_size drives the hi-res circle radius (radius = size // 2)."""
    from unittest.mock import MagicMock

    from led_ticker.ticker import _CircleBufferMsg

    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    big = _CircleBufferMsg(text=" • ", center=False, font_color=RGB_WHITE, size=8)
    small = _CircleBufferMsg(text=" • ", center=False, font_color=RGB_WHITE, size=4)

    _, big_cursor = big.draw(canvas, cursor_pos=0)
    real.SetPixel.reset_mock()
    _, small_cursor = small.draw(canvas, cursor_pos=0)

    # size 4 → radius 2 → fewer painted pixels + a shorter advance than size 8.
    assert small_cursor < big_cursor
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_ticker.py::test_circle_buffer_msg_size_shrinks_circle -v`
Expected: FAIL — `_CircleBufferMsg` has no `size` kwarg.

- [ ] **Step 3: Add `size` to `_CircleBufferMsg` + thread it**

In `src/led_ticker/ticker.py`, add a `size` attrs field to `_CircleBufferMsg` (it's `@attrs.define class _CircleBufferMsg(TickerMessage)`). Since it subclasses `TickerMessage`, add the field with a default so existing constructions stay valid:

```python
    size: int = 8
```

In its `draw`, thread the size into the circle spec:

```python
        if is_scaled(canvas):
            advance = render_separator(
                canvas,
                cursor_pos + _CIRCLE_LOGICAL_PAD,
                self.frame_for("font_color"),
                attrs.evolve(DEFAULT_CIRCLE_SPEC, color=self.font_color, size=self.size),
            )
            new_pos = cursor_pos + _CIRCLE_LOGICAL_PAD + advance + _CIRCLE_LOGICAL_PAD
            return canvas, new_pos
```

- [ ] **Step 4: Wire `_resolve_buffer_msg` to pass the size**

In `src/led_ticker/app/factories.py` `_resolve_buffer_msg`: add `separator_size` to the "is any separator field set" gate (so a size-only section builds a resized circle rather than returning `None`), and pass `size` to the color-only `_CircleBufferMsg(...)`:

```python
    size = section.separator_size if section.separator_size is not None else 8
    ...
    # in the color/size-only (not text_or_font_set) branch:
        return _CircleBufferMsg(
            text=" • ", center=False, font_color=color_provider, size=size
        )
```

Make sure the early `return None` only fires when ALL of separator / separator_font / separator_font_size / separator_color / separator_size are unset. (`separator_size` alone must build a resized circle, not fall back to the size-8 default.)

- [ ] **Step 5: Run — expect pass + ticker circle tripwires green**

Run: `uv run pytest tests/test_ticker.py -k "circle_buffer_msg or default_buffer_msg" -v`
Expected: PASS — the new size test + the Phase-1 circle tripwires (default `cursor == 10` at size 8, rainbow animates, smallsign delegates).

- [ ] **Step 6: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/ticker.py src/led_ticker/app/factories.py tests/test_ticker.py
git add src/led_ticker/ticker.py src/led_ticker/app/factories.py tests/test_ticker.py
git commit -m "feat(ticker): separator_size shrinks/grows the hi-res circle separator"
```

---

### Task 4: validation — positive-int bound + scope (rules 57 & 26)

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_validate.py` (async / `conf`):

```python
async def test_separator_size_on_non_scroll_transition_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5
        default_scale = 1

        [[playlist.section]]
        mode = "slideshow"
        widget_transition = { type = "dissolve", separator_size = 4 }

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 57 for e in result.errors)


async def test_separator_size_on_non_ticker_section_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5
        default_scale = 1

        [[playlist.section]]
        mode = "slideshow"
        separator_size = 4

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_validate.py -k "separator_size" -v`
Expected: FAIL — neither rule includes `separator_size` yet.

- [ ] **Step 3: Extend rule 57 (transition) and rule 26 (section) field sets**

In `_check_separator_color_transition` (the rule-57 function), add `"separator_size"` to the tuple of fields it checks for "any set on a non-scroll transition" (the same `any(getattr(trans_cfg, f, None) is not None for f in (...))` set). In the rule-26 section check, add `or section.separator_size is not None` to the `separator_set` predicate.

(Positive-int coercion: `coerce_int` in the loader already rejects non-ints. If a dedicated `separator_size <= 0` check is wanted, mirror the nearest existing positive-int rule; otherwise the int coercion + these scope rules are sufficient for this task — do NOT add an unrequested new rule number.)

- [ ] **Step 4: Run — expect pass + existing rule-57/26 tests green**

Run: `uv run pytest tests/test_validate.py -k "separator_size or rule57 or rule26 or separator_glyph" -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/validate.py tests/test_validate.py
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat(validate): separator_size scoped to scroll (rule 57) + ticker (rule 26)"
```

---

### Task 5: docs + drift gate

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`; `docs/site/src/content/docs/transitions/special.mdx`; `docs/site/src/content/docs/concepts/sections-and-modes.mdx`; `tests/test_docs_config_options_drift.py`

- [ ] **Step 1: Run the drift test to see demands**

Run: `uv run pytest tests/test_docs_config_options_drift.py -v`
Expected: FAIL — `separator_size` undocumented for `[transitions]` AND `[[playlist.section]]` (or the test names them).

- [ ] **Step 2: Add the `[transitions]` row**

In `config-options.mdx`, under `## [transitions]`, add:

```
| `separator_size`   | int            | `null`     | Size (logical px) of the `scroll` transition's separator dot. `null` = the default 2. No effect on a glyph separator. Only honored by `type = "scroll"`. |
```

- [ ] **Step 3: Add the `[[playlist.section]]` row**

In `config-options.mdx`, in the `[[playlist.section]]` separator rows, add:

```
| `separator_size`      | int             | `null`     | Size (logical px) of the ticker-mode separator circle (radius = size ÷ 2). `null` = the default 8. Only affects the bigsign hi-res circle; the smallsign BDF `•` is unaffected. Only honored by `mode = "ticker"`. |
```

- [ ] **Step 4: Add notes**

In `special.mdx`, append to the scroll separator paragraph: "`separator_size` sets the dot's pixel size (default 2)." In `sections-and-modes.mdx`, near the ticker separator description, add: "`separator_size` shrinks or grows the bigsign separator circle (default 8; radius = size ÷ 2)."

- [ ] **Step 5: Update the drift keys**

In `tests/test_docs_config_options_drift.py`, add `"separator_size"` to BOTH `DOCUMENTED_KEYS["transitions"]` AND the `[[playlist.section]]` key set.

- [ ] **Step 6: Run — expect pass**

Run: `uv run pytest tests/test_docs_config_options_drift.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/site/src/content/docs tests/test_docs_config_options_drift.py
git commit -m "docs: document separator_size (scroll dot + ticker circle)"
```

---

### Task 6: full-suite verification

- [ ] **Step 1: Full suite**

Run: `make test`
Expected: all pass; no regression in Phase-1/2a/2b separator tests.

- [ ] **Step 2: Lint + typecheck (the pre-push gate)**

Run: `uv run --extra dev ruff check src/ tests/ tools/` → clean.
Run: `uv run pyright src/` → 0 errors.

- [ ] **Step 3: End-to-end sanity**

Run:
```bash
uv run python -c "
from led_ticker.app.factories import _build_trans_obj
from led_ticker.config import TransitionConfig
s = _build_trans_obj(TransitionConfig(type='scroll', separator_size=5))
print('scroll dot size:', s._spec.size, '| sep_w:', s._sep_w)
"
```
Expected: `scroll dot size: 5 | sep_w: 17`.

---

## Notes

- This completes the configurable-scroll-separator feature (Phases 1→2a→2b→3): the scroll separator now supports color, glyph, font, and size — full parity with the ticker separator, which also gains the size knob (closing the "can't shrink the big circle" gap).
- Deferred (from earlier reviews): the pre-existing section `_check_separator_fonts` `"requires font_size"` substring bug; optionally converging `_resolve_buffer_msg` fully onto `_resolve_separator_spec`.

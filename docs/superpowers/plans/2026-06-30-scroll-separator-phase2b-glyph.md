# Scroll Separator — Phase 2b: the glyph kind — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users replace the `scroll` transition's separator dot with an arbitrary character/glyph (`separator` + `separator_font` + `separator_font_size`), at full parity with the ticker-mode separator.

**Architecture:** Add a `glyph` kind to the shared `render_separator` (draws via `text_render.draw_text`, width via `drawing.get_text_width`, color normalized to a `graphics.Color`). Add the three glyph fields to `TransitionConfig`; a shared `_resolve_separator_spec` builds a `SeparatorSpec` (color-only → recolored dot; glyph set → glyph spec with a resolved font) consumed by `_build_trans_obj`. Validation + docs extend to the new fields.

**Tech Stack:** Python 3.14, attrs, pytest, the BDF/hires font loaders, Astro/Markdown docs.

## Global Constraints

- **Builds on Phase 2a (merged):** `TransitionConfig.separator_color` + rule 57 + `SeparatorSpec(kind, color, size, glyph="", font=None)` + `render_separator(canvas, x, frame, spec)` already exist.
- **`separator.py` stays a leaf module** — import `text_render`, `drawing`, `colors`, `fonts` only via LOCAL imports inside the glyph functions (matching the existing style); never import `ticker`/`transitions`.
- **Width at `Scroll.__init__` is canvas-less:** `separator_width(glyph_spec) = get_text_width(font, glyph, padding=0)` (canvas=None → `SCALE_FALLBACK=4`). This matches real hardware (smallsign BDF = canvas-independent; bigsign = scale 4 = the fallback). Document this assumption.
- **Color shapes:** `separator_color` keeps the same shapes (`[r,g,b]`, `"rainbow"`, `{style=…}`). The glyph path needs a `graphics.Color`, so normalize a tuple result via `make_color`.
- **Default glyph** when `separator` is unset but a font is set: `"•"`. An explicit `separator = ""` renders nothing (gap only).
- **Honored ONLY by `scroll`:** rule 57 extends to the new fields; reject on non-scroll across all four transition homes.
- **Docs ship with the fields** (drift gate).
- Repo workflow: branch `feat/scroll-separator-glyph`; never `main`; `make dev` once; `uv run --extra dev ruff check` before pushing.

---

## Prerequisite (once)

- [ ] **Worktree venv + branch check**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-sep2b && make dev && git branch --show-current`
Expected: deps install; prints `feat/scroll-separator-glyph`.

---

### Task 1: the `glyph` render kind in `separator.py`

**Files:**
- Modify: `src/led_ticker/separator.py` (`render_separator` dispatch; new `_render_glyph`; `separator_width`)
- Test: `tests/test_separator.py`

**Interfaces:**
- Produces: `render_separator` handles `spec.kind == "glyph"`; `separator_width(glyph_spec)` returns the glyph's logical advance. Consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_separator.py`:

```python
def test_separator_width_glyph_uses_font_advance():
    from led_ticker.drawing import get_text_width
    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.separator import SeparatorSpec, separator_width

    spec = SeparatorSpec(kind="glyph", color=RGB_WHITE, glyph="-", font=FONT_DEFAULT)
    assert separator_width(spec) == get_text_width(FONT_DEFAULT, "-", padding=0)


def test_render_glyph_paints_on_plain_canvas_and_returns_width():
    from led_ticker.drawing import get_text_width
    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.separator import SeparatorSpec, render_separator

    canvas = _plain()
    spec = SeparatorSpec(kind="glyph", color=RGB_WHITE, glyph="-", font=FONT_DEFAULT)
    width = render_separator(canvas, x=20, frame=0, spec=spec)
    assert canvas.SetPixel.called  # BDF rasterizer painted pixels
    assert width == get_text_width(FONT_DEFAULT, "-", padding=0, canvas=canvas)


def test_render_glyph_normalizes_tuple_color_to_graphics_color():
    """A provider that yields a tuple must be wrapped to a graphics.Color
    (draw_text reads .red/.green/.blue)."""
    from unittest.mock import patch

    from led_ticker.fonts import FONT_DEFAULT
    from led_ticker.separator import SeparatorSpec, render_separator

    canvas = _plain()
    spec = SeparatorSpec(kind="glyph", color=(10, 20, 30), glyph="-", font=FONT_DEFAULT)
    with patch("led_ticker.text_render.draw_text", return_value=5) as mock_dt:
        render_separator(canvas, x=0, frame=0, spec=spec)
    color_arg = mock_dt.call_args.args[4]  # draw_text(canvas, font, x, y, color, text)
    assert (color_arg.red, color_arg.green, color_arg.blue) == (10, 20, 30)
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_separator.py -k glyph -v`
Expected: FAIL — `render_separator` doesn't handle `kind="glyph"` (falls through to `_render_dot`, paints a 2-px square, width 2).

- [ ] **Step 3: Implement the glyph kind**

In `src/led_ticker/separator.py`, add `_render_glyph` (local imports keep the module a leaf):

```python
def _render_glyph(canvas: Canvas, x: int, frame: int, spec: "SeparatorSpec") -> int:
    from led_ticker.colors import make_color
    from led_ticker.drawing import compute_baseline, get_text_width
    from led_ticker.text_render import draw_text

    c = _as_provider(spec.color).color_for(frame, 0, 1)
    color = c if hasattr(c, "red") else make_color(*c)
    baseline_y = compute_baseline(spec.font, canvas, "center")
    draw_text(canvas, spec.font, x, baseline_y, color, spec.glyph)
    return get_text_width(spec.font, spec.glyph, padding=0, canvas=canvas)
```

Change `render_separator` to dispatch glyph first:

```python
def render_separator(canvas: Canvas, x: int, frame: int, spec: SeparatorSpec) -> int:
    """Paint the separator mark at logical x; return its logical width (no pad)."""
    if spec.kind == "glyph":
        return _render_glyph(canvas, x, frame, spec)
    rgb = _resolve_rgb(spec.color, frame)
    if spec.kind == "circle" and is_scaled(canvas):
        return _render_circle(canvas, x, rgb, spec.size)
    return _render_dot(canvas, x, rgb, spec.size)
```

Change `separator_width` to handle glyph (canvas-less; `SCALE_FALLBACK` matches real hardware):

```python
def separator_width(spec: SeparatorSpec) -> int:
    """The mark's own logical width (no padding)."""
    if spec.kind == "glyph":
        from led_ticker.drawing import get_text_width

        return get_text_width(spec.font, spec.glyph, padding=0)
    return spec.size
```

- [ ] **Step 4: Run — expect pass + leaf check**

Run: `uv run pytest tests/test_separator.py -v`
Expected: PASS (all, incl. the 3 new glyph tests; the existing dot/circle tests unchanged).
Run: `uv run python -c "import ast,sys; t=ast.parse(open('src/led_ticker/separator.py').read()); tops=[n for n in t.body if isinstance(n,(ast.Import,ast.ImportFrom))]; bad=[a for n in tops for a in ([n.module] if isinstance(n,ast.ImportFrom) else [x.name for x in n.names]) if a and ('ticker' in a or 'transitions' in a)]; print('LEAF OK' if not bad else f'CYCLE: {bad}')"`
Expected: `LEAF OK` (top-level imports never reference ticker/transitions).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/separator.py tests/test_separator.py
git add src/led_ticker/separator.py tests/test_separator.py
git commit -m "feat(separator): add the glyph render kind (draw_text + canvas-less width)"
```

---

### Task 2: `TransitionConfig` glyph fields + loader

**Files:**
- Modify: `src/led_ticker/config.py` (`TransitionConfig`; `_parse_transition`; `_BUILTIN_TRANSITION_KEYS`)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `TransitionConfig.separator: str | None`, `separator_font: str | None`, `separator_font_size: int | None` (raw). Consumed by Tasks 3 + 4.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_transition_glyph_fields_parsed(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n\n"
        "[[playlist.section]]\nmode='slideshow'\n"
        "widget_transition={type='scroll', separator='-', separator_font='6x12'}\n"
        "[[playlist.section.widget]]\ntype='message'\ntext='hi'\n"
    )
    from led_ticker.config import load_config

    wt = load_config(str(cfg)).sections[0].widget_transition
    assert wt.separator == "-"
    assert wt.separator_font == "6x12"
    assert "separator" not in wt.extra and "separator_font" not in wt.extra
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_config.py::test_transition_glyph_fields_parsed -v`
Expected: FAIL — `TransitionConfig` has no `separator`/`separator_font`.

- [ ] **Step 3: Add fields + parse them**

In `TransitionConfig` (after `separator_color`):

```python
    # The scroll transition's separator GLYPH (Phase 2b). `None` = the default
    # dot. An explicit "" renders nothing (gap only). `separator_font` /
    # `separator_font_size` pick the glyph's font (same resolution as widget
    # fonts). Honored ONLY by type="scroll".
    separator: str | None = None
    separator_font: str | None = None
    separator_font_size: int | None = None
```

In `_parse_transition`'s `TransitionConfig(...)` call (after `separator_color=...`):

```python
        separator=raw.get("separator"),
        separator_font=raw.get("separator_font"),
        separator_font_size=raw.get("separator_font_size"),
```

Add `"separator"`, `"separator_font"`, `"separator_font_size"` to `_BUILTIN_TRANSITION_KEYS`.

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_config.py::test_transition_glyph_fields_parsed -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/config.py tests/test_config.py
git add src/led_ticker/config.py tests/test_config.py
git commit -m "feat(config): TransitionConfig glyph fields (separator/separator_font/separator_font_size)"
```

---

### Task 3: `_resolve_separator_spec` + wire `_build_trans_obj` for glyph

**Files:**
- Modify: `src/led_ticker/app/factories.py` (new `_resolve_separator_spec`; `_build_trans_obj`)
- Test: `tests/test_transitions.py`

**Interfaces:**
- Consumes: the `TransitionConfig` glyph fields (Task 2); `SeparatorSpec` (Task 1).
- Produces: a `Scroll` whose `_spec` is a glyph spec when `separator`/`separator_font`/`separator_font_size` is set; a recolored dot when only `separator_color`; `DEFAULT_DOT_SPEC` when nothing is set.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_transitions.py` (extends the Phase-2a `TestScrollSeparatorColor` area):

```python
class TestScrollSeparatorGlyph:
    def test_glyph_spec_built_with_default_font(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig

        scroll = _build_trans_obj(TransitionConfig(type="scroll", separator="-"))
        assert scroll._spec.kind == "glyph"
        assert scroll._spec.glyph == "-"
        assert scroll._spec.font is not None  # FONT_DEFAULT

    def test_glyph_spec_resolves_named_font(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig
        from led_ticker.fonts import resolve_font

        scroll = _build_trans_obj(
            TransitionConfig(type="scroll", separator="*", separator_font="6x12")
        )
        assert scroll._spec.kind == "glyph"
        assert scroll._spec.font is resolve_font("6x12", None)

    def test_color_only_still_recolored_dot(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig

        scroll = _build_trans_obj(
            TransitionConfig(type="scroll", separator_color=[80, 80, 80])
        )
        assert scroll._spec.kind == "dot"

    def test_default_is_default_dot_spec(self):
        from led_ticker.app.factories import _build_trans_obj
        from led_ticker.config import TransitionConfig
        from led_ticker.separator import DEFAULT_DOT_SPEC

        assert _build_trans_obj(TransitionConfig(type="scroll"))._spec is DEFAULT_DOT_SPEC
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_transitions.py::TestScrollSeparatorGlyph -v`
Expected: FAIL — no glyph branch yet (`separator="-"` yields a dot spec, not glyph).

- [ ] **Step 3: Add the shared resolver + wire it**

In `src/led_ticker/app/factories.py`, add the resolver (near `_resolve_buffer_msg`):

```python
def _resolve_separator_spec(
    *,
    separator: str | None,
    separator_color: Any,
    separator_font: str | None,
    separator_font_size: int | None,
    default_kind: str,
) -> Any:
    """Build a SeparatorSpec from the separator_* config family.

    default_kind selects the site's default mark ("dot" for the scroll
    transition, "circle" for the ticker separator). Color-only keeps that
    default kind recolored; any glyph field switches to kind="glyph".
    """
    import attrs

    from led_ticker.colors import RGB_WHITE
    from led_ticker.separator import (
        DEFAULT_CIRCLE_SPEC,
        DEFAULT_DOT_SPEC,
        SeparatorSpec,
    )

    base = DEFAULT_DOT_SPEC if default_kind == "dot" else DEFAULT_CIRCLE_SPEC
    glyph_set = (
        separator is not None
        or separator_font is not None
        or separator_font_size is not None
    )
    color_set = separator_color is not None
    if not glyph_set and not color_set:
        return base

    color = (
        _coerce_color_provider(separator_color, "separator_color")
        if color_set
        else RGB_WHITE
    )
    if not glyph_set:
        return attrs.evolve(base, color=color)

    from led_ticker.fonts import FONT_DEFAULT, resolve_font

    glyph = separator if separator is not None else "•"
    font = (
        resolve_font(separator_font, separator_font_size)
        if separator_font is not None
        else FONT_DEFAULT
    )
    return SeparatorSpec(kind="glyph", color=color, glyph=glyph, font=font)
```

In `_build_trans_obj`, replace the Phase-2a inline scroll-spec block with the shared resolver:

```python
    if trans_cfg.type == "scroll" and (
        trans_cfg.separator_color is not None
        or trans_cfg.separator is not None
        or trans_cfg.separator_font is not None
        or trans_cfg.separator_font_size is not None
    ):
        kwargs["spec"] = _resolve_separator_spec(
            separator=trans_cfg.separator,
            separator_color=trans_cfg.separator_color,
            separator_font=trans_cfg.separator_font,
            separator_font_size=trans_cfg.separator_font_size,
            default_kind="dot",
        )
    return cls(**kwargs)
```

(Leave `_resolve_buffer_msg`, the ticker path, untouched — the shared resolver is scroll-only for now.)

- [ ] **Step 4: Run — expect pass + Phase-2a color tests still green**

Run: `uv run pytest tests/test_transitions.py -k "TestScrollSeparatorGlyph or TestScrollSeparatorColor" -v`
Expected: PASS (glyph + the Phase-2a color tests — color-only still a recolored dot, default still `DEFAULT_DOT_SPEC`).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/app/factories.py tests/test_transitions.py
git add src/led_ticker/app/factories.py tests/test_transitions.py
git commit -m "feat(scroll): glyph separator via separator/separator_font (shared _resolve_separator_spec)"
```

---

### Task 4: validation — extend rule 57 to glyph fields + resolve `separator_font`

**Files:**
- Modify: `src/led_ticker/validate.py` (`_check_separator_color_transition` → generalize; add a transition `separator_font` resolution check)
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: the `TransitionConfig` glyph fields across the four transition homes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_validate.py` (async / `conf` pattern, like the rule-57 tests):

```python
async def test_rule57_separator_glyph_on_non_scroll_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5
        default_scale = 1

        [[playlist.section]]
        mode = "slideshow"
        widget_transition = { type = "dissolve", separator = "-" }

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 57 for e in result.errors)


async def test_scroll_unknown_separator_font_warns(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5
        default_scale = 1

        [[playlist.section]]
        mode = "slideshow"
        widget_transition = { type = "scroll", separator = "-", separator_font = "no_such_font" }

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert any("no_such_font" in (w.message or "") for w in result.warnings)
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_validate.py -k "separator_glyph_on_non_scroll or unknown_separator_font" -v`
Expected: FAIL — rule 57 only checks `separator_color`; no transition font resolution yet.

- [ ] **Step 3: Generalize rule 57 + add the font check**

In `src/led_ticker/validate.py` `_check_separator_color_transition`, change the per-home guard from a single `separator_color` check to "any separator_* field set" and update the message:

```python
        sep_set = any(
            getattr(trans_cfg, f, None) is not None
            for f in ("separator", "separator_color", "separator_font", "separator_font_size")
        )
        if not sep_set:
            continue
        if trans_cfg.type != "scroll":
            issues.append(
                ValidationIssue(
                    rule=57,
                    location=...,  # keep the existing location expression
                    severity="error",
                    message=(
                        "separator / separator_color / separator_font fields are "
                        f"only honored by the scroll transition; type="
                        f"{trans_cfg.type!r} ignores them."
                    ),
                    fix="Use the separator fields only with type='scroll', or remove them.",
                )
            )
```

Add a sibling check that resolves a scroll transition's `separator_font` (mirror `_check_separator_fonts`): iterate the same four homes, and for a `scroll` transition with `separator_font` set, `resolve_font(trans_cfg.separator_font, trans_cfg.separator_font_size)` inside try/except → `UnknownFontError` becomes a rule-24 warning, a `ValueError` containing "requires font_size" becomes a rule-5 error (same mapping `_check_separator_fonts` uses). Register the new check function wherever `_check_separator_color_transition` is registered (search for rule 57 wiring near `validate.py:2114`).

- [ ] **Step 4: Run — expect pass + Phase-2a rule-57 tests still green**

Run: `uv run pytest tests/test_validate.py -k "rule57 or separator_font" -v`
Expected: PASS — the glyph-on-non-scroll error, the unknown-font warning, AND the existing Phase-2a rule-57 color tests.

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/validate.py tests/test_validate.py
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat(validate): rule 57 covers glyph fields; resolve scroll separator_font"
```

---

### Task 5: docs + drift gate

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`; `docs/site/src/content/docs/transitions/special.mdx`; `tests/test_docs_config_options_drift.py` (DOCUMENTED_KEYS)

- [ ] **Step 1: Run the drift test to see what's demanded**

Run: `uv run pytest tests/test_docs_config_options_drift.py -v`
Expected: FAIL — `separator`/`separator_font`/`separator_font_size` undocumented for the `[transitions]` table (or the test names them).

- [ ] **Step 2: Add the `[transitions]` rows**

In `config-options.mdx`, under `## [transitions]`, add three rows:

```
| `separator`        | string         | `null`     | The `scroll` transition's separator glyph. `null` = the default dot; `""` renders nothing (gap only). Only honored by `type = "scroll"`. |
| `separator_font`   | string         | `null`     | Font (BDF alias or hires name) for the scroll `separator` glyph. `null` uses the default 6×12 BDF font. |
| `separator_font_size` | int         | `null`     | Pixel size for a hires `separator_font` (ignored for BDF). Required when `separator_font` is a hires font. |
```

- [ ] **Step 3: Extend the special.mdx scroll note**

Append to the scroll separator paragraph in `special.mdx`:

```
To use a character instead of a dot, set `separator` (and optionally
`separator_font` / `separator_font_size`): `transition = { type = "scroll",
separator = "·", separator_font = "6x12" }`.
```

- [ ] **Step 4: Update the drift DOCUMENTED_KEYS**

In `tests/test_docs_config_options_drift.py`, add `"separator"`, `"separator_font"`, `"separator_font_size"` to the `DOCUMENTED_KEYS["transitions"]` set.

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest tests/test_docs_config_options_drift.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/content/docs/reference/config-options.mdx docs/site/src/content/docs/transitions/special.mdx tests/test_docs_config_options_drift.py
git commit -m "docs(transitions): document scroll separator glyph fields"
```

---

### Task 6: full-suite verification

**Files:** none.

- [ ] **Step 1: Full suite**

Run: `make test`
Expected: all pass; no regression in Phase-1/2a separator/scroll tests.

- [ ] **Step 2: Lint**

Run: `uv run --extra dev ruff check src/ tests/ tools/`
Expected: no violations.

- [ ] **Step 3: End-to-end sanity (the actual feature)**

Run:
```bash
uv run python -c "
from led_ticker.app.factories import _build_trans_obj
from led_ticker.config import TransitionConfig
s = _build_trans_obj(TransitionConfig(type='scroll', separator='·', separator_color='rainbow'))
print('kind:', s._spec.kind, '| glyph:', s._spec.glyph, '| font:', type(s._spec.font).__name__, '| sep_w:', s._sep_w)
"
```
Expected: `kind: glyph | glyph: · | font: Font | sep_w: <N>` — a rainbow-colored glyph separator with a non-default width.

---

## Notes

- **Phase 3 (next):** the `separator_size` knob (dot/circle filled-shape size) on both `TransitionConfig` and `SectionConfig` — also closes the ticker "can't shrink the circle" gap.
- **Deferred / optional:** converging `_resolve_buffer_msg` (the ticker path) onto `_resolve_separator_spec` — the shared resolver exists now (scroll-only); a later cleanup can route the ticker path through it.
- The canvas-less `separator_width(glyph_spec)` uses `SCALE_FALLBACK=4`; correct on both real signs (smallsign BDF canvas-independent; bigsign scale 4). A hypothetical scale-2 hires canvas would be off, but no such canvas exists in this project.

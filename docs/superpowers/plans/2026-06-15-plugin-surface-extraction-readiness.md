# Extraction-readiness plugin-API audit (P3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `led_ticker.plugin`'s public surface complete enough that the planned extractions (`calendar`, `weather`, `rss_feed`, the arcade sprite transitions) need zero re-vendoring of core internals, and lock it with a tripwire.

**Architecture:** Add a public `as_color_provider` factory + five more re-exports to `led_ticker.plugin`; dogfood the factory in core's calendar/weather (behavior-identical); add an AST-based extraction-readiness tripwire that fails on any new internal reach; update the drift-guarded api-reference + an authoring note. Purely additive — no extraction, no behavior change.

**Tech Stack:** Python 3.14, pytest (`PYTHONPATH=tests/stubs`), `ast` (stdlib), attrs.

**Spec:** `docs/superpowers/specs/2026-06-15-plugin-surface-extraction-readiness-design.md` (read first).

**Worktree / branch:** all work in `.claude/worktrees/feat+plugin-surface-extraction-readiness` on branch `worktree-feat+plugin-surface-extraction-readiness`. NEVER commit to `main`. First action each task: `pwd && git branch --show-current` and confirm.

**Conventions:** tests `PYTHONPATH=tests/stubs uv run pytest <path> -q`; NO `from __future__ import annotations` in `src/`; pre-commit hooks (ruff/format) fire on commit — re-stage if reformatted; docs-lint needs node via nvm (`node --version`; else `source ~/.nvm/nvm.sh && nvm use`).

---

### Task 1: `as_color_provider` factory + six public exports

**Files:**
- Modify: `src/led_ticker/color_providers.py` (add factory after `_ConstantColor`, ~line 100)
- Modify: `src/led_ticker/plugin.py` (imports ~30-62, `draw_text` body ~366, `__all__` ~92-124)
- Test: `tests/test_plugin_surface_p3.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugin_surface_p3.py`:

```python
"""P3 — the six symbols planned extractions need, on the public surface."""

import led_ticker.plugin as plugin


def test_new_symbols_importable_from_plugin():
    from led_ticker.plugin import (  # noqa: F401
        ColorTuple,
        as_color_provider,
        count_text_chars,
        draw_text_per_char,
        draw_with_emoji,
        format_clock,
    )


def test_new_symbols_in_all():
    for name in (
        "ColorTuple",
        "as_color_provider",
        "count_text_chars",
        "draw_text_per_char",
        "draw_with_emoji",
        "format_clock",
    ):
        assert name in plugin.__all__, name


def test_as_color_provider_wraps_a_color_uniformly():
    from led_ticker.plugin import as_color_provider, make_color

    c = make_color(10, 20, 30)
    prov = as_color_provider(c)
    assert hasattr(prov, "color_for")  # it's a ColorProvider
    got = prov.color_for(frame=0, char_index=0, total_chars=1)
    assert (got.red, got.green, got.blue) == (10, 20, 30)
    # uniform: same color regardless of char position / frame
    got2 = prov.color_for(frame=5, char_index=3, total_chars=8)
    assert (got2.red, got2.green, got2.blue) == (10, 20, 30)
```

- [ ] **Step 2: Run, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_surface_p3.py -q`
Expected: ImportError (`as_color_provider` doesn't exist; the six names aren't in `__all__`).

- [ ] **Step 3: Add the factory** to `src/led_ticker/color_providers.py`

Immediately after the `_ConstantColor` class (it ends before the next class def, ~line 100 — place the function after the class body, at module level):

```python
def as_color_provider(color: Color) -> ColorProvider:
    """Wrap a constant ``Color`` as a uniform (non-animated) ``ColorProvider``.

    The public way to get a constant-color provider — e.g. a widget's default
    font color. ``_ConstantColor`` stays private; this is the supported surface.
    """
    return _ConstantColor(color)
```

(`Color` is already imported at the top of `color_providers.py`; `ColorProvider` is the Protocol defined in this module — confirm both are in scope, they are per the file's existing `_ConstantColor(ColorProviderBase)` definition.)

- [ ] **Step 4: Add the exports to `src/led_ticker/plugin.py`**

(a) `_types` import (line 30) — add `ColorTuple`:
```python
from led_ticker._types import Canvas, Color, ColorTuple, DrawResult, Font, PixelData
```

(b) `color_providers` import (line 33) — add `as_color_provider`:
```python
from led_ticker.color_providers import ColorProvider, ColorProviderBase, as_color_provider
```

(c) pixel_emoji imports — currently:
```python
from led_ticker.pixel_emoji import (
    HiResEmoji,
    draw_emoji_at,
    measure_emoji_at,
    measure_width,
)
from led_ticker.pixel_emoji import draw_with_emoji as _draw_with_emoji
```
Replace BOTH with a single un-aliased block:
```python
from led_ticker.pixel_emoji import (
    HiResEmoji,
    count_text_chars,
    draw_emoji_at,
    draw_with_emoji,
    measure_emoji_at,
    measure_width,
)
```
Then update the `draw_text` wrapper body (line ~366): change `return x + _draw_with_emoji(canvas, font, x, y, color, text)` to `return x + draw_with_emoji(canvas, font, x, y, color, text)`.

(d) Add a `text_render` import for `draw_text_per_char` (place near the pixel_emoji import):
```python
from led_ticker.text_render import draw_text_per_char
```

(e) Add a `widgets.clock` import for `format_clock` (place with the widget imports, after `from led_ticker.widgets._frame_aware import FrameAwareBase`):
```python
from led_ticker.widgets.clock import format_clock
```

(f) Add all six names to `__all__`, matching the list's roughly-alphabetical ordering:
`"ColorTuple"` (near `Color`), `"as_color_provider"` (near `Animation`/lowercase helpers — place with the lowercase function names, e.g. after `"AnimationFrame"`'s lowercase neighbors; alphabetically it sorts among the lowercase block near `"colors"`), `"count_text_chars"`, `"draw_text_per_char"`, `"draw_with_emoji"` (near the existing `"draw_text"`/`"draw_emoji_at"`), `"format_clock"` (near `"font_line_height_logical"`). Exact placement isn't load-bearing (the drift test extracts names, not order) — keep it tidy.

- [ ] **Step 5: Run, expect pass + import sanity**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_surface_p3.py -q`
Expected: 3 passed.
Run: `PYTHONPATH=tests/stubs uv run python -c "import led_ticker.plugin"` — clean import (no circular-import error from the new `widgets.clock`/`text_render` imports).
Run: `uv run ruff check src/led_ticker/plugin.py src/led_ticker/color_providers.py tests/test_plugin_surface_p3.py`

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/color_providers.py src/led_ticker/plugin.py tests/test_plugin_surface_p3.py
git commit -m "feat: as_color_provider factory + extraction-readiness exports on plugin surface"
```

---

### Task 2: Dogfood `as_color_provider` in calendar + weather

**Files:**
- Modify: `src/led_ticker/widgets/weather.py` (import line 11; sites 58, 60)
- Modify: `src/led_ticker/widgets/calendar.py` (import line 24; sites 538, 542, 543, 637, 778)

- [ ] **Step 1: Confirm the regression baseline is green**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_calendar.py tests/test_widgets/test_weather.py -q`
Expected: all pass (this is the behavior-preservation guard for the swap).

- [ ] **Step 2: Swap weather.py**

Change the import (line 11) from:
```python
from led_ticker.color_providers import ColorProvider, _ConstantColor
```
to:
```python
from led_ticker.color_providers import ColorProvider, as_color_provider
```
Then sites 58 / 60:
```python
            self.font_color = as_color_provider(self.font_color)
        ...
            self.font_color_temp = as_color_provider(self.font_color_temp)
```

- [ ] **Step 3: Swap calendar.py**

Change the import (line 24) from `from led_ticker.color_providers import ColorProvider, _ConstantColor` to `from led_ticker.color_providers import ColorProvider, as_color_provider`. Then replace every `_ConstantColor(` call with `as_color_provider(`:
- line 538: `return as_color_provider(DEFAULT_COLOR)`
- line 542: `return as_color_provider(make_color(*value))`
- line 543: `return as_color_provider(value)  # already a graphics.Color`
- line 637: `font_color = as_color_provider(font_color)`
- line 778: `font_color = as_color_provider(font_color)`
Also update the docstring mentions of `_ConstantColor` in the coerce helper (lines ~530-532) to say `as_color_provider` so the prose matches the code. Grep after: `grep -n "_ConstantColor" src/led_ticker/widgets/calendar.py src/led_ticker/widgets/weather.py` must return NOTHING.

- [ ] **Step 4: Run regression**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widgets/test_calendar.py tests/test_widgets/test_weather.py -q`
Expected: all pass, unchanged (the swap is behavior-identical — `as_color_provider(c)` returns `_ConstantColor(c)`).
Run: `uv run ruff check src/led_ticker/widgets/calendar.py src/led_ticker/widgets/weather.py`

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/calendar.py src/led_ticker/widgets/weather.py
git commit -m "refactor: calendar/weather use public as_color_provider (dogfood)"
```

---

### Task 3: Extraction-readiness tripwire

**Files:**
- Test: `tests/test_plugin_extraction_readiness.py` (new)

- [ ] **Step 1: Write the test**

Create `tests/test_plugin_extraction_readiness.py`. It AST-scans each candidate module for names imported from `led_ticker.*` and asserts each is either public (in `plugin.__all__` or an attribute of the public `colors` module) or in that candidate's documented allowlist. A GAP fails the test. A self-check proves the test is non-vacuous.

```python
"""Extraction-readiness tripwire (P3).

For each planned-extraction candidate, every name it imports from
`led_ticker.*` must be reachable by a plugin: on the public
`led_ticker.plugin` surface, an attribute of the public `colors` module,
or a per-candidate ALLOWED name with a documented reason. A new internal
reach fails this test until it's exported or justified. This is the
extraction audit, made executable.
"""

import ast
from pathlib import Path

import led_ticker.plugin as plugin
from led_ticker import colors

SRC = Path(__file__).resolve().parent.parent / "src" / "led_ticker"

# Per-candidate allowlist: name -> reason it's OK to be internal.
# Anything imported from led_ticker.* and NOT public must appear here.
_ALLOWED = {
    "widgets/calendar.py": {
        "register": "replaced by api.widget(name) when the plugin registers",
    },
    "widgets/weather.py": {
        "register": "replaced by api.widget(name)",
        "_match_condition": "weather_icons moves with weather into the plugin",
    },
    "widgets/weather_icons.py": {},
    "widgets/rss_feed.py": {
        "register": "replaced by api.widget(name)",
    },
    "transitions/nyancat.py": {
        "register_transition": "replaced by api.transition(name)",
        "HIRES_REGISTRY": "built-in dispatch only; extracted arcade uses the "
        "P2 HiresSpec + is_scaled pattern",
        "render_hires_frame": "public (P2)",  # imported func-locally; see note
    },
    "transitions/pokeball.py": {
        "register_transition": "replaced by api.transition(name)",
        "HIRES_REGISTRY": "built-in dispatch only; P2 HiresSpec pattern on extraction",
        "render_hires_frame": "public (P2)",
    },
    "transitions/pacman.py": {
        "register_transition": "replaced by api.transition(name)",
    },
    "transitions/sailor_moon.py": {
        "register_transition": "replaced by api.transition(name)",
    },
}

_PUBLIC = set(plugin.__all__)


def _imported_led_ticker_names(path: Path) -> set[str]:
    """Names brought in via `from led_ticker... import X` (any depth, incl.
    function-local imports)."""
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "led_ticker" or node.module.startswith("led_ticker."):
                for alias in node.names:
                    names.add(alias.name)
    return names


def _is_reachable(name: str, allowed: dict) -> bool:
    return name in _PUBLIC or hasattr(colors, name) or name in allowed


def test_candidates_are_extraction_ready():
    failures = []
    for rel, allowed in _ALLOWED.items():
        path = SRC / rel
        assert path.exists(), f"candidate file missing: {rel}"
        for name in sorted(_imported_led_ticker_names(path)):
            if not _is_reachable(name, allowed):
                failures.append(f"{rel}: {name!r} is not on the public surface")
    assert not failures, "Extraction-readiness GAPs:\n" + "\n".join(failures)


def test_tripwire_is_not_vacuous():
    # A bogus internal name must be classified a GAP (the test can fail).
    assert not _is_reachable("definitely_not_public_xyz", {})
    # And a public name must be reachable.
    assert _is_reachable("make_color", {})
```

NOTE on `render_hires_frame`: it's public via P2, so it's already in `_PUBLIC` — the allowlist entry is harmless/redundant but documents intent. If the test flags any name not anticipated here (e.g. an intra-package name like a sibling helper), STOP and report it — that's a real audit finding to resolve (export it, or add an allowlist entry with a reason), not something to silently widen the allowlist for.

- [ ] **Step 2: Run, expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_extraction_readiness.py -q`
Expected: both tests pass. After Tasks 1–2, every candidate's internal reaches are either public or allowlisted. If `test_candidates_are_extraction_ready` FAILS, read the named gap: it's a real symbol a plugin would need — resolve by exporting it (extend Task 1) or, if it's genuinely a moves-with/api-replaced case, add an allowlist entry WITH a reason and report the addition.

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugin_extraction_readiness.py
git commit -m "test: extraction-readiness tripwire for the plugin public surface"
```

---

### Task 4: Drift guard (api-reference) + authoring note

**Files:**
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx` (api-exports table ~114-186)
- Modify: a plugins authoring/extending page (the one documenting widget/transition authoring — `extending/writing-a-transition.mdx` covers transitions; for the widget-rendering helpers check `extending/` for a widget page or the authoring chapters)

- [ ] **Step 1: Run the drift test, expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_plugin_api_drift.py -q`
Expected: FAIL — `__all__` now has six names the api-exports region lacks (it names them).

- [ ] **Step 2: Add six rows to the api-exports table**

In `docs/site/src/content/docs/plugins/api-reference.mdx`, inside the `{/* <!-- api-exports:start --> */} ... {/* <!-- api-exports:end --> */}` table, add rows matching the existing backticked-symbol-first-column format (function rows use the call-signature form like `make_color(r, g, b)`, which the drift extractor maps to the bare name):
```
| `as_color_provider(color)`                                                 | Wrap a constant `Color` as a uniform (non-animated) `ColorProvider` (e.g. a widget's default font color)                                                                                                                      |
| `draw_with_emoji(canvas, font, cursor_pos, y, color, text, ...)`           | Full rich-text renderer: inline `:emoji:` + per-char `ColorProvider` colors (the `draw_text` helper is the simpler `Color`-only form)                                                                                          |
| `count_text_chars(text)`                                                   | Count rendered characters in `text`, treating each `:emoji:` token as one — pair with a per-char provider's `total_chars`                                                                                                     |
| `draw_text_per_char(...)`                                                  | Lower-level per-character text draw used by data widgets                                                                                                                                                                       |
| `format_clock(...)`                                                        | Format a time per led-ticker's clock conventions (12h/24h presets)                                                                                                                                                            |
| `ColorTuple`                                                               | Type alias `tuple[int, int, int]` for raw RGB                                                                                                                                                                                  |
```
Place them sensibly among the existing rows (helpers near helpers, the type alias near `Color`). Read 2–3 existing rows first to match column count exactly.

- [ ] **Step 3: Run drift + lint**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_plugin_api_drift.py -q` → PASS.
Run: `make docs-lint` (node via nvm if needed). Re-stage if prettier reformats.

- [ ] **Step 4: Authoring note**

Read `docs/DOCS-STYLE.md`, then find the plugins authoring/extending page that documents building a widget (list `docs/site/src/content/docs/plugins/extending/` and `authoring/`). Add a short note (extend an existing section; don't invent a page): a data/text plugin widget renders rich text (inline emoji + animated per-char color) with `draw_with_emoji` + `count_text_chars`; gets a constant-color provider via `as_color_provider`; and reads the named color constants (`RED`, `DEFAULT_COLOR`, …) from the public `colors` module. Keep it tight; follow DOCS-STYLE. If no widget-authoring page exists and only a transition one does, add the note where it fits best and report the placement.

- [ ] **Step 5: Lint + commit**

Run: `make docs-lint` → clean.
```bash
git add docs/site/src/content/docs/plugins/
git commit -m "docs: api-reference + authoring note for the P3 plugin exports"
```

---

### Task 5: Full verification + PR

- [ ] **Step 1: Full suite + lint**

Run: `make test` — all pass (baseline ~2975 + the new P3 tests). Coverage ≥ 90%.
Run: `make lint` — clean.

- [ ] **Step 2: Confirm the private reach is gone**

Run: `grep -rn "_ConstantColor" src/led_ticker/widgets/calendar.py src/led_ticker/widgets/weather.py` → NOTHING (calendar/weather fully dogfooded). `_ConstantColor` should still exist only in `color_providers.py` (definition + the `as_color_provider` factory) and `clock.py`/coercion/tests.

- [ ] **Step 3: Push + PR**

```bash
git push -u origin worktree-feat+plugin-surface-extraction-readiness
gh pr create --title "feat: extraction-readiness plugin-API audit (P3)" --body "$(cat <<'EOF'
## Summary
P3, the last prerequisite from the plugin-extraction review (after P1 #214/#216 and P2 #218). Makes the public `led_ticker.plugin` surface complete enough that the planned extractions (calendar, weather, rss_feed, arcade sprite transitions) need **zero re-vendoring** of core internals.

- New public factory `as_color_provider(color)` (wraps a constant `Color` as a uniform `ColorProvider`; `_ConstantColor` stays private). Core's calendar/weather are dogfooded onto it (behavior-identical).
- Five more re-exports on `led_ticker.plugin`: `format_clock`, `draw_text_per_char`, `draw_with_emoji`, `count_text_chars`, `ColorTuple` (the audit found four beyond the review's two).
- **Extraction-readiness tripwire** (`test_plugin_extraction_readiness.py`): AST-scans each candidate's `led_ticker.*` imports and fails on any internal reach not public or allowlisted (with documented reasons: `register*`→api decorators, `weather_icons` moves-with, `HIRES_REGISTRY`→P2-resolved). Locks the audit so the surface can't silently rot.
- api-reference drift rows + authoring note.

No extraction here; this unblocks them. Spec: docs/superpowers/specs/2026-06-15-plugin-surface-extraction-readiness-design.md

## Test plan
- [ ] `make test` green; `make lint` / `make docs-lint` clean
- [ ] New: test_plugin_surface_p3 (factory + exports), test_plugin_extraction_readiness (tripwire, non-vacuous)
- [ ] calendar/weather suites unchanged (dogfood is behavior-identical)
- [ ] drift guard updated for the six new exports

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes
- **Spec coverage:** factory (T1) · six exports incl. the un-alias of draw_with_emoji (T1) · dogfood calendar+weather (T2) · readiness tripwire w/ allowlist + non-vacuity (T3) · drift rows + authoring note (T4) · color-constants-via-`colors` (encoded in the tripwire's `hasattr(colors, name)`) · grep-clean verification (T5). All mapped.
- **Type consistency:** `as_color_provider(color: Color) -> ColorProvider` used identically in T1 (def), T1 test, T2 (calls), T4 (docs). The six export names spelled identically across T1/T3/T4.
- **Regression guards:** calendar/weather suites (T2 step 1 + 4) prove the dogfood is behavior-identical; the drift guard (T4) and `import led_ticker.plugin` sanity (T1 step 5) catch surface mistakes; the tripwire's `test_tripwire_is_not_vacuous` proves it can fail.

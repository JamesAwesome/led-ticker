# Plugin System — Phase B Implementation Plan (coercion registries)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make **color providers, animations, borders, and easing** pluggable — a plugin can `api.color_provider("fire")(MyProvider)` / `api.animation(...)` / `api.border(...)` / `api.easing("snap", fn)` and reference them in TOML as `{style="ns.fire"}` / `easing="ns.snap"`, with no core fork.

**Architecture:** A **hybrid registry** per surface: a `dict[str, type]` registry is the source of truth for which styles exist (built-ins + plugins); built-ins keep their existing special-case value coercion (TOML `from`/`to` hue-ranges, RGB→`Color`, shorthands), while plugin styles take a generic path (validate kwargs against `inspect.signature(cls)`, then `cls(**kwargs)`). Each surface plugs into the Phase A machinery by adding one `PluginAPI._buffers` key, one `api.*` method, and one `_REGISTRY_MAP` entry — `_commit` is unchanged.

**Tech Stack:** Python 3.14, the merged Phase A (`led_ticker.plugin.PluginAPI` with `_buffers`, `_plugin_loader._REGISTRY_MAP` + generic `_commit`), `inspect.signature`, the existing `coercion.py` coercers, pytest.

**Spec:** `docs/superpowers/specs/2026-05-31-plugin-system-design.md` (Phase B section).

**Conventions:**
- New files: NO `from __future__ import annotations` (3.14/PEP 649; a tripwire forbids it).
- Tests: `PYTHONPATH=tests/stubs uv run --extra dev pytest <path>`.
- Commit hooks-disabled: `git -c core.hooksPath=/dev/null commit` (use `bash -c '...'` for multi-line). 88-char ruff limit; `make lint` before each commit. End commits with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Plugin tests live under `tests/test_plugins/`. Every test that loads plugins or registers into a registry uses the `reset_plugins()` autouse fixture pattern from Phase A so registrations don't leak.

**Phase A recap (what's already there):** `PluginAPI._buffers: dict[str, dict]` keyed by surface name with `widget`/`transition` methods; `_plugin_loader._REGISTRY_MAP` mapping surface name → registry dict; generic two-pass `_commit` (validate-all-then-write-all) that iterates `_buffers` filtered by `_REGISTRY_MAP`, counting into `PluginInfo.counts`; `reset_plugins()` drops dotted keys from every `_REGISTRY_MAP.values()` registry. **Adding a surface = (1) a `_buffers` key + `api.*` method in `plugin.py`, (2) a `_REGISTRY_MAP` entry in `_plugin_loader.py`.**

---

## File Structure

- `src/led_ticker/color_providers.py` (modify) — add `_PROVIDER_REGISTRY` + register the 5 built-ins.
- `src/led_ticker/animations.py` (modify) — add `_ANIMATION_REGISTRY` + register `Typewriter`.
- `src/led_ticker/borders.py` (modify) — add `_BORDER_REGISTRY` + register the 4 built-ins.
- `src/led_ticker/app/coercion.py` (modify) — `_provider_from_style`, `_coerce_animation`, `_coerce_border` look up the registry; built-in special-cases preserved; plugin styles take the generic path.
- `src/led_ticker/transitions/__init__.py` — `EASING` is already the easing registry; no structural change.
- `src/led_ticker/plugin.py` (modify) — add `_buffers` keys + `color_provider`/`animation`/`border`/`easing` methods + re-export `ColorProvider`/`ColorProviderBase`/`Animation`/`BorderEffect`/`BorderEffectBase`/`Color`.
- `src/led_ticker/_plugin_loader.py` (modify) — add the 4 `_REGISTRY_MAP` entries.
- `tests/test_plugins/test_provider_plugins.py`, `test_animation_plugins.py`, `test_border_plugins.py`, `test_easing_plugins.py` (new).

**Shared helper used by the generic path** (define once, in `coercion.py`):
```python
def _allowed_init_kwargs(cls: type) -> set[str]:
    """Keyword names a class's constructor accepts (for plugin coercion)."""
    import inspect

    return {
        name
        for name, p in inspect.signature(cls).parameters.items()
        if p.kind
        in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    }
```

---

## Task B1: Color-provider registry + coercion refactor (built-in behavior preserved)

**Files:** Modify `src/led_ticker/color_providers.py`, `src/led_ticker/app/coercion.py`. Test: `tests/test_plugins/test_provider_plugins.py` (regression half).

**Context:** `coercion._provider_from_style` hardcodes `registry = {"rainbow": (Rainbow, {...}), "gradient": (Gradient, {...}), ...}` and has special-case blocks for `gradient`/`color_cycle`/`shimmer` (TOML `from`/`to`/`base`/`shimmer` → constructor kwargs + RGB→`Color`). This task moves the *existence* map into `color_providers._PROVIDER_REGISTRY` and dispatches: special-cased styles keep their exact existing blocks; everything else (`rainbow`, `random`, and future plugin styles) uses a generic `inspect.signature` path. **No behavior change for any built-in style** — this task is a pure refactor guarded by regression tests.

- [ ] **Step 1: Write the regression test FIRST** (locks current built-in behavior)

Create `tests/test_plugins/test_provider_plugins.py`:
```python
import pytest

from led_ticker.app.coercion import _coerce_color_provider


@pytest.mark.parametrize(
    "spec",
    [
        "rainbow",
        "color_cycle",
        "random",
        {"style": "rainbow", "speed": 5, "char_offset": 3},
        {"style": "color_cycle", "speed": 2},
        {"style": "gradient", "from": [255, 0, 0], "to": [0, 0, 255]},
        {"style": "shimmer", "base": [255, 255, 255], "shimmer": [0, 200, 255]},
    ],
)
def test_builtin_providers_still_coerce(spec):
    provider = _coerce_color_provider(spec, field="font_color")
    assert hasattr(provider, "color_for")


def test_unknown_style_lists_available():
    with pytest.raises(ValueError, match="unknown font_color style"):
        _coerce_color_provider({"style": "nope"}, field="font_color")
```
(Check the real signature of `_coerce_color_provider` first — `grep -n "def _coerce_color_provider" src/led_ticker/app/coercion.py` — and match its call form; the `field=` kwarg above is illustrative. Use the actual signature.)

- [ ] **Step 2: Run it — should PASS now** (current behavior). This is the regression baseline; keep it green through the refactor.

`PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_provider_plugins.py -v`

- [ ] **Step 3: Add the registry to `color_providers.py`**

Read the 5 provider class names (`Random`, `Rainbow`, `ColorCycle`, `Gradient`, `Shimmer`). At the end of `color_providers.py`, add:
```python
# Registry of color-provider styles. Built-ins below; plugins add namespaced
# entries via PluginAPI.color_provider(). coercion._provider_from_style looks
# styles up here.
_PROVIDER_REGISTRY: dict[str, type] = {
    "random": Random,
    "rainbow": Rainbow,
    "color_cycle": ColorCycle,
    "gradient": Gradient,
    "shimmer": Shimmer,
}
```

- [ ] **Step 4: Refactor `_provider_from_style`**

Read the full current function first. Replace the local `registry = {...}` lookup with the shared registry, and split dispatch into "special-cased built-in" vs "generic". Concretely:
- Add near the top of `coercion.py` the `_allowed_init_kwargs` helper (from File Structure above) and a constant `_SPECIAL_PROVIDER_STYLES = {"gradient", "color_cycle", "shimmer"}`.
- In `_provider_from_style`, change the existence check + class lookup to:
```python
    from led_ticker.color_providers import _PROVIDER_REGISTRY

    cls = _PROVIDER_REGISTRY.get(style)
    if cls is None:
        raise ValueError(
            f"unknown font_color style {style!r}; "
            f"available: {sorted(_PROVIDER_REGISTRY)}"
        )
```
- KEEP the existing `gradient` / `color_cycle` / `shimmer` special-case blocks EXACTLY as they are (they pop `from`/`to`/`base`/`shimmer`, RGB-validate, build `graphics.Color`, set the constructor kwargs). Those blocks already reference `cls`.
- REPLACE the final "validate remaining kwargs against the hardcoded `allowed` set, then `return cls(**kwargs)`" tail with a branch:
```python
    if style not in _SPECIAL_PROVIDER_STYLES:
        allowed = _allowed_init_kwargs(cls)
        unknown = set(kwargs) - allowed
        if unknown:
            raise ValueError(
                f"font_color style {style!r} got unknown keys "
                f"{sorted(unknown)!r}; allowed: {sorted(allowed)}"
            )
    return cls(**kwargs)
```
  For the special-cased styles, after their blocks the remaining kwargs are already the constructor kwargs, so `cls(**kwargs)` is correct — but to preserve their *original* friendlier `_user_allowed` error messages, leave each special block's own existing kwarg-validation in place (do not route special styles through the generic `unknown` check). The generic `unknown` check applies only to non-special styles (rainbow/random/plugins).

- [ ] **Step 5: Run the regression test — must still PASS**

`PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_provider_plugins.py -v`
Then the broader coercion tests for no regression:
`PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_app.py tests/ -q -k "provider or coerce or color"`

- [ ] **Step 6: Lint + typecheck + commit**

```bash
make lint && make typecheck
git add src/led_ticker/color_providers.py src/led_ticker/app/coercion.py tests/test_plugins/test_provider_plugins.py
git -c core.hooksPath=/dev/null commit -m "refactor: color-provider registry; coercion looks it up (built-ins unchanged)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task B2: `api.color_provider` + loader wiring + re-exports (plugin providers work)

**Files:** Modify `src/led_ticker/plugin.py`, `src/led_ticker/_plugin_loader.py`. Test: extend `tests/test_plugins/test_provider_plugins.py`.

- [ ] **Step 1: Write the failing test** (a plugin provider, coerced from `{style="ns.fire"}`)

Append to `tests/test_plugins/test_provider_plugins.py`:
```python
from led_ticker import _plugin_loader as L


@pytest.fixture
def _clean_plugins():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_plugin_color_provider_coerces(_clean_plugins, tmp_path):
    src = '''
import attrs
from led_ticker.plugin import ColorProviderBase

@attrs.define
class Fire(ColorProviderBase):
    frame_invariant = True
    intensity: int = 5
    def color_for(self, frame, char_index, total_chars):
        from led_ticker._compat import require_graphics
        return require_graphics().Color(self.intensity, 0, 0)

def register(api):
    api.color_provider("fire")(Fire)
'''
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)

    from led_ticker.app.coercion import _coerce_color_provider

    provider = _coerce_color_provider({"style": "acme.fire", "intensity": 9}, field="font_color")
    assert provider.color_for(0, 0, 1) is not None
```
(Match `_coerce_color_provider`'s real signature; `ColorProviderBase` requires the `frame_invariant` class attribute — the test class sets it.)

- [ ] **Step 2: Run — expect FAIL** (`api.color_provider` doesn't exist; `acme.fire` unknown).

- [ ] **Step 3: Add the surface to `plugin.py`**

In `PluginAPI.__init__`, add `"color_providers": {}` to the `_buffers` dict. Add the method (alongside `widget`/`transition`):
```python
    def color_provider(self, style: str) -> Callable[[_T], _T]:
        """Register a ColorProvider class under ``namespace.style``."""

        def deco(cls: _T) -> _T:
            self._buffers["color_providers"][self._qualify(style)] = cls
            return cls

        return deco
```
Add re-exports: import `from led_ticker.color_providers import ColorProvider, ColorProviderBase` and `from led_ticker._types import Color`; add `"Color"`, `"ColorProvider"`, `"ColorProviderBase"` to `__all__`.

- [ ] **Step 4: Wire the loader**

In `src/led_ticker/_plugin_loader.py`, import `from led_ticker.color_providers import _PROVIDER_REGISTRY` and add `"color_providers": _PROVIDER_REGISTRY` to `_REGISTRY_MAP`.

- [ ] **Step 5: Run — expect PASS**; then full plugin suite + the regression test.

`PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/ -q`

- [ ] **Step 6: Lint + typecheck + commit**

```bash
make lint && make typecheck
git add src/led_ticker/plugin.py src/led_ticker/_plugin_loader.py tests/test_plugins/test_provider_plugins.py
git -c core.hooksPath=/dev/null commit -m "feat: pluggable color providers via api.color_provider

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task B3: Animations — registry + coercion + `api.animation` (clean surface)

**Files:** Modify `src/led_ticker/animations.py`, `src/led_ticker/app/coercion.py`, `src/led_ticker/plugin.py`, `src/led_ticker/_plugin_loader.py`. Test: `tests/test_plugins/test_animation_plugins.py`.

**Context:** `_coerce_animation` is clean (no TOML-key remapping) — just `(class, allowed_kwargs)` + direct instantiate. So this surface is fully generic.

- [ ] **Step 1: Write the test**

Create `tests/test_plugins/test_animation_plugins.py`:
```python
import pytest

from led_ticker import _plugin_loader as L
from led_ticker.app.coercion import _coerce_animation


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_builtin_typewriter_still_coerces():
    anim = _coerce_animation("typewriter")
    assert hasattr(anim, "frame_for")
    anim2 = _coerce_animation({"style": "typewriter", "frames_per_char": 6})
    assert hasattr(anim2, "frame_for")


def test_plugin_animation_coerces(tmp_path):
    src = '''
import attrs
from led_ticker.plugin import Animation

@attrs.define
class Scramble:
    speed: int = 2
    def frame_for(self, frame, full_text, canvas_width, text_width):
        from led_ticker.animations import AnimationFrame
        return AnimationFrame(visible_text=full_text)

def register(api):
    api.animation("scramble")(Scramble)
'''
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)
    anim = _coerce_animation({"style": "acme.scramble", "speed": 4})
    assert hasattr(anim, "frame_for")
```
(Verify `AnimationFrame`'s real constructor field name via `grep -n "class AnimationFrame" src/led_ticker/animations.py`; adjust if needed.)

- [ ] **Step 2: Run — expect FAIL** (`acme.scramble` unknown; `api.animation` missing).

- [ ] **Step 3: Add `_ANIMATION_REGISTRY` to `animations.py`**

At the end of `animations.py`:
```python
_ANIMATION_REGISTRY: dict[str, type] = {
    "typewriter": Typewriter,
}
```

- [ ] **Step 4: Refactor `_coerce_animation`**

Read the full function. Replace its local `registry = {"typewriter": (Typewriter, {...})}` with the shared registry + generic kwargs:
```python
    from led_ticker.animations import _ANIMATION_REGISTRY
```
For both the `str` and `dict` branches, look up `cls = _ANIMATION_REGISTRY.get(name_or_style)`; if `None` → `raise ValueError(f"unknown animation {...!r}; available: {sorted(_ANIMATION_REGISTRY)}")`. For the dict branch, validate `set(kwargs) - _allowed_init_kwargs(cls)` (the shared helper from B1) and `return cls(**kwargs)`. The `str` branch returns `cls()`.

- [ ] **Step 5: Add the plugin surface**

`plugin.py`: add `"animations": {}` to `_buffers`; add the `animation(self, style)` method (mirrors `color_provider`, buffering into `"animations"`); import + re-export `Animation` from `led_ticker.animations` (add `"Animation"` to `__all__`).
`_plugin_loader.py`: import `_ANIMATION_REGISTRY`, add `"animations": _ANIMATION_REGISTRY` to `_REGISTRY_MAP`.

- [ ] **Step 6: Run — expect PASS**; full plugin + animation suites; lint + typecheck; commit.

```bash
PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/ tests/ -q -k "anim or plugin"
make lint && make typecheck
git add src/led_ticker/animations.py src/led_ticker/app/coercion.py src/led_ticker/plugin.py src/led_ticker/_plugin_loader.py tests/test_plugins/test_animation_plugins.py
git -c core.hooksPath=/dev/null commit -m "feat: pluggable animations (registry + api.animation)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task B4: Borders — registry + coercion refactor + `api.border` (special-cases preserved)

**Files:** Modify `src/led_ticker/borders.py`, `src/led_ticker/app/coercion.py`, `src/led_ticker/plugin.py`, `src/led_ticker/_plugin_loader.py`. Test: `tests/test_plugins/test_border_plugins.py`.

**Context:** `_coerce_border` has shorthands (`"rainbow"`, `[r,g,b]`) and special-case blocks (`rainbow` from/to hue range, `constant` color). Same hybrid as providers: registry for existence + plugin generic path; built-in `match style` blocks preserved.

- [ ] **Step 1: Write the regression + plugin test**

Create `tests/test_plugins/test_border_plugins.py`:
```python
import pytest

from led_ticker import _plugin_loader as L
from led_ticker.app.coercion import _coerce_border


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


@pytest.mark.parametrize(
    "spec",
    [
        "rainbow",
        "color_cycle",
        "lightbulbs",
        [255, 0, 0],
        {"style": "rainbow", "speed": 4, "thickness": 2},
        {"style": "constant", "color": [0, 255, 0], "thickness": 1},
    ],
)
def test_builtin_borders_still_coerce(spec):
    b = _coerce_border(spec)
    assert hasattr(b, "paint")


def test_plugin_border_coerces(tmp_path):
    src = '''
import attrs
from led_ticker.plugin import BorderEffectBase

@attrs.define
class Neon(BorderEffectBase):
    frame_invariant = False
    speed: int = 3
    def paint(self, canvas, frame=0):
        return None

def register(api):
    api.border("neon")(Neon)
'''
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)
    b = _coerce_border({"style": "acme.neon", "speed": 6})
    assert hasattr(b, "paint")
```
(Verify `BorderEffectBase` / `BorderEffect`'s exact `paint` signature via `grep -n "def paint" src/led_ticker/borders.py`; match it in the test class.)

- [ ] **Step 2: Run — built-in cases PASS, plugin case FAILS.** (Run the parametrized regression separately first to confirm green baseline, then the plugin case to confirm it fails.)

- [ ] **Step 3: `_BORDER_REGISTRY` in `borders.py`**

```python
_BORDER_REGISTRY: dict[str, type] = {
    "rainbow": RainbowChaseBorder,
    "color_cycle": ColorCycleBorder,
    "constant": ConstantBorder,
    "lightbulbs": LightbulbBorder,
}
```

- [ ] **Step 4: Refactor `_coerce_border`'s inline-table branch**

Keep the shorthand handling (`None`, `[r,g,b]` → `ConstantBorder`, the string `match` for `rainbow`/`color_cycle`/`lightbulbs`) UNCHANGED. In the inline-`dict` branch, after extracting `style` + `kwargs`: look up `cls = _BORDER_REGISTRY.get(style)`; if `None` → unknown-style error listing `sorted(_BORDER_REGISTRY)`. Keep the existing `rainbow` / `constant` `match style` special-case blocks verbatim. Add a default branch for styles not specially handled (i.e. plugin borders, plus any built-in without a special block): validate `set(kwargs) - _allowed_init_kwargs(cls)` and `return cls(**kwargs)`.

- [ ] **Step 5: Add the plugin surface**

`plugin.py`: `"borders": {}` in `_buffers`; `border(self, name)` method (buffering into `"borders"`); re-export `BorderEffect`, `BorderEffectBase` from `led_ticker.borders` (add to `__all__`).
`_plugin_loader.py`: import `_BORDER_REGISTRY`, add `"borders": _BORDER_REGISTRY` to `_REGISTRY_MAP`.

- [ ] **Step 6: Run — all PASS**; full plugin + border suites; lint + typecheck; commit.

```bash
PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/ tests/ -q -k "border or plugin"
make lint && make typecheck
git add src/led_ticker/borders.py src/led_ticker/app/coercion.py src/led_ticker/plugin.py src/led_ticker/_plugin_loader.py tests/test_plugins/test_border_plugins.py
git -c core.hooksPath=/dev/null commit -m "feat: pluggable borders (registry + api.border, built-in special-cases kept)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task B5: Easing — `api.easing` + loader wiring

**Files:** Modify `src/led_ticker/plugin.py`, `src/led_ticker/_plugin_loader.py`. Test: `tests/test_plugins/test_easing_plugins.py`.

**Context:** `EASING: dict[str, Callable[[float], float]]` in `transitions/__init__.py` is *already* the easing registry. Easing registers a **callable, not a class**, so `api.easing` is a direct call (not a decorator). The generic `_commit` writes `EASING[ns.name] = fn` like any other surface.

- [ ] **Step 1: Write the test**

Create `tests/test_plugins/test_easing_plugins.py`:
```python
import pytest

from led_ticker import _plugin_loader as L
from led_ticker.transitions import EASING


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_plugin_easing_registers_namespaced(tmp_path):
    src = '''
def register(api):
    api.easing("snap", lambda p: p * p)
'''
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)
    assert "acme.snap" in EASING
    assert EASING["acme.snap"](0.5) == 0.25


def test_builtin_easing_untouched():
    assert "linear" in EASING and "ease_out" in EASING
```
(`reset_plugins()` drops dotted keys from every `_REGISTRY_MAP` registry — once `EASING` is mapped in Step 3, `acme.snap` is cleaned up between tests; built-in `linear`/`ease_out` have no dot and survive.)

- [ ] **Step 2: Run — expect FAIL** (`api.easing` missing; `acme.snap` not in EASING).

- [ ] **Step 3: Implement**

`plugin.py`: add `"easing": {}` to `_buffers`; add:
```python
    def easing(self, name: str, fn: Callable[[float], float]) -> None:
        """Register an easing function under ``namespace.name``."""
        self._buffers["easing"][self._qualify(name)] = fn
```
`_plugin_loader.py`: import `from led_ticker.transitions import EASING`, add `"easing": EASING` to `_REGISTRY_MAP`.

- [ ] **Step 4: Run — expect PASS**; full plugin + transitions suites.

`PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/ tests/ -q -k "easing or transition or plugin"`

- [ ] **Step 5: Lint + typecheck + commit**

```bash
make lint && make typecheck
git add src/led_ticker/plugin.py src/led_ticker/_plugin_loader.py tests/test_plugins/test_easing_plugins.py
git -c core.hooksPath=/dev/null commit -m "feat: pluggable easing functions via api.easing

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase B final verification

- [ ] `make lint`, `make typecheck`, `PYTHONPATH=tests/stubs uv run --extra dev pytest -q` all green on 3.14.
- [ ] No `from __future__ import annotations` added (tripwire passes).
- [ ] `PluginAPI._buffers` now has `widgets, transitions, color_providers, animations, borders, easing`; `_REGISTRY_MAP` mirrors them. `__all__` re-exports `ColorProvider`, `ColorProviderBase`, `Animation`, `BorderEffect`, `BorderEffectBase`, `Color`.
- [ ] Built-in providers/animations/borders/easing behave identically (regression tests green).
- [ ] A plugin can contribute each of the four surfaces, referenced as `ns.name` in TOML.
- [ ] Hand off: this is Phase B of the plugin system; merge, then Phase C (emojis + fonts) is the next plan.

## Notes for the implementer

- The `_allowed_init_kwargs` helper (B1) is shared by B1/B3/B4 — define it once in `coercion.py`; don't duplicate.
- For each coercion refactor, **read the full current function first** and preserve the existing built-in special-case blocks verbatim — the regression tests are the guard. The only structural change is "registry lookup for existence + a generic branch for non-special styles."
- Plugin provider/animation/border classes are expected to be `@attrs.define` and conformant (`color_for` / `frame_for` / `paint`); `ColorProviderBase` / `BorderEffectBase` enforce the `frame_invariant` class attribute via `__init_subclass__`. The tests model conformant plugin classes — keep them minimal but valid.
- Out of scope for Phase B (later phases): emojis + fonts (C), lifecycle hooks (D), `[plugins]` config + CLI + docs + example (E), and the namespace-token hygiene follow-up from Phase A's review (E).

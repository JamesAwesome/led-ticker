# Plugin System — Phase C (Emojis + Fonts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let plugins contribute low-res emojis, hi-res emojis, and font files — referenced in TOML as `namespace.slug` (inline `:namespace.slug:`) and `font = "namespace.Name"` — with no edit to `src/led_ticker`.

**Architecture:** Phase C extends the existing plugin framework (Phases A+B) without changing its shape. Three new `PluginAPI` buffers (`emojis`, `hires_emojis`, `fonts`) map to three registries via the existing generic `_REGISTRY_MAP` + `_commit` machinery. Emoji resolution is essentially free once the registries hold namespaced keys: the lookups in `pixel_emoji.py` already key by string slug, so the only code change is widening the inline `EMOJI_PATTERN` so `:ns.slug:` parses. Fonts get a `_PLUGIN_FONTS: dict[str, Path]` registry consulted ahead of the `config/fonts/` → bundled → BDF chain; the plugin's filesystem root (for resolving relative font paths) is computed inside the loader from the discovery `source`.

**Tech Stack:** Python 3.14, pytest. No `from __future__ import annotations` (forbidden by tripwire). Native PEP 604 / PEP 585 syntax. No new dependencies.

**Builds on (already merged):**
- Phase A — `led_ticker.plugin.PluginAPI` (`_buffers` dict, `_qualify`, namespacing, atomic commit) + `led_ticker._plugin_loader` (`_REGISTRY_MAP`, `_commit`, `_discover_local`/`_discover_entry_points`, `_load_one`, `load_plugins`, `reset_plugins`).
- Phase B — color providers, animations, borders, easing made pluggable via the same `_buffers`/`_REGISTRY_MAP` pattern.

**Out of scope (Phase E):** `[plugins]` config block, `led-ticker plugins` CLI, `validate`/`--list-fields` integration, `examples/plugins/`, docs. Phase C proves the emoji + font *mechanics* end-to-end through `load_plugins` + the existing draw / `resolve_font` paths.

---

## File Structure

**Modified:**
- `src/led_ticker/plugin.py` — add `root` param to `PluginAPI.__init__`; add `emojis`/`hires_emojis`/`fonts` buffers; add `emoji()`/`hires_emoji()`/`font()` methods; re-export `PixelData`, `HiResEmoji`, `draw_emoji_at`, `measure_emoji_at`, `get_text_width`, `compute_baseline`, `colors`.
- `src/led_ticker/fonts/hires_loader.py` — define `_PLUGIN_FONTS`; `_find_font_path` consults it first.
- `src/led_ticker/pixel_emoji.py` — fix the lazy `_get_registry()` build gate (sentinel, not truthiness); widen `EMOJI_PATTERN`; make `_parse_segments` split via `EMOJI_PATTERN` (single source of truth).
- `src/led_ticker/_plugin_loader.py` — import the three new registries into `_REGISTRY_MAP`; add `_resolve_root()`; build `PluginAPI(namespace, root=...)` in `_load_one`.

**Created (tests):**
- `tests/test_plugins/test_emoji_plugins.py` — emoji registry wiring, lazy-build regression, namespaced parse/resolve.
- `tests/test_plugins/test_font_plugins.py` — `_PLUGIN_FONTS` lookup, root resolution, end-to-end `resolve_font("ns.Name")`.
- Extends `tests/test_plugins/test_plugin_api.py` — new buffers/methods/exports.

**Surface invariant (do not break):** adding a registry surface = one `_buffers` key (plugin.py) + one `api.*` method (plugin.py) + one `_REGISTRY_MAP` entry (_plugin_loader.py), all sharing the same surface-name string. `_commit` and `reset_plugins` stay generic. Phase C adds three surfaces: `emojis`, `hires_emojis`, `fonts`.

---

## Pre-flight (run once before Task C1)

- [ ] **Confirm branch and baseline**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-c
git branch --show-current   # MUST print: feat/plugin-phase-c  — abort if it prints main
make dev                    # set up the project venv (pyright + dev tools)
make test                   # baseline — expect all green (2496 passed, 2 skipped at branch point)
```

If `git branch --show-current` prints `main`, STOP — do not implement on main.

---

## Task C1: PluginAPI surface — emoji/hires_emoji/font buffers, methods, re-exports

**Files:**
- Modify: `src/led_ticker/plugin.py`
- Test: `tests/test_plugins/test_plugin_api.py`

**Context:** `PluginAPI` (plugin.py:44) holds a `_buffers` dict, one key per surface, and exposes a method per surface that buffers under the namespaced name. Class surfaces (`widget`, `transition`, …) are decorators; non-class surfaces (`easing`) are direct calls. Emojis and fonts are direct calls too (an emoji is pixel data; a font is a file path). `font()` needs the plugin's filesystem root, which the loader supplies in Task C4 — so `__init__` grows a `root` parameter now (defaulting to `None`, so existing call sites keep working until C4 passes a real root).

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/test_plugins/test_plugin_api.py` (the file currently imports only `from led_ticker.plugin import API_VERSION, PluginAPI` — add `pytest`):

```python
import pytest
```

Append these tests to `tests/test_plugins/test_plugin_api.py`:

```python
def test_emoji_and_hires_emoji_buffer_under_namespace():
    api = PluginAPI("acme")
    api.emoji("spark", [(0, 0, 255, 0, 0)])
    api.hires_emoji("glow", object())  # API does not validate sprite shape
    assert api._buffers["emojis"] == {"acme.spark": [(0, 0, 255, 0, 0)]}
    assert "acme.glow" in api._buffers["hires_emojis"]


def test_font_buffers_resolved_absolute_path(tmp_path):
    api = PluginAPI("acme", root=tmp_path)
    api.font("Brand", "fonts/Brand.ttf")
    assert api._buffers["fonts"]["acme.Brand"] == (tmp_path / "fonts/Brand.ttf").resolve()


def test_font_without_root_raises():
    api = PluginAPI("acme")  # root defaults to None
    with pytest.raises(ValueError, match="needs a plugin root"):
        api.font("Brand", "fonts/Brand.ttf")


def test_public_surface_exports_emoji_and_font_helpers():
    import led_ticker.plugin as p

    for name in (
        "PixelData",
        "HiResEmoji",
        "draw_emoji_at",
        "measure_emoji_at",
        "get_text_width",
        "compute_baseline",
        "colors",
    ):
        assert hasattr(p, name), f"missing public export: {name}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins/test_plugin_api.py -q`
Expected: FAIL — `PluginAPI.__init__()` got an unexpected keyword `root`; `AttributeError: 'PluginAPI' object has no attribute 'emoji'`; missing exports.

- [ ] **Step 3: Add the imports and extend `__all__`**

In `src/led_ticker/plugin.py`, replace the import block (lines 10–19) with:

```python
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

# Re-exports: the stable surface plugin authors subclass / annotate against.
from led_ticker import colors
from led_ticker._types import Canvas, Color, PixelData
from led_ticker.animations import Animation, AnimationFrame
from led_ticker.borders import BorderEffect, BorderEffectBase
from led_ticker.color_providers import ColorProvider, ColorProviderBase
from led_ticker.drawing import compute_baseline, get_text_width
from led_ticker.pixel_emoji import HiResEmoji, draw_emoji_at, measure_emoji_at
from led_ticker.transitions import Transition
from led_ticker.widget import Widget, spawn_tracked
```

Replace the `__all__` list (lines 21–37) with:

```python
__all__ = [
    "API_VERSION",
    "PluginAPI",
    "Animation",
    "AnimationFrame",
    "BorderEffect",
    "BorderEffectBase",
    "Canvas",
    "Color",
    "ColorProvider",
    "ColorProviderBase",
    "HiResEmoji",
    "PixelData",
    "Transition",
    "Widget",
    "colors",
    "compute_baseline",
    "draw_emoji_at",
    "get_text_width",
    "make_color",
    "measure_emoji_at",
    "spawn_tracked",
]
# Phase D will add: StartupContext.
```

> **Import-cycle note:** `plugin.py` is imported lazily (by `_plugin_loader` at app startup and by plugins), not from `led_ticker/__init__.py`, and neither `pixel_emoji`, `drawing`, nor `colors` imports `plugin`/`_plugin_loader`. So these top-level re-exports introduce no cycle. If `make typecheck`/`pytest` surfaces a cycle anyway, move the offending import into a `TYPE_CHECKING` block / lazy function — but verify first; the expected outcome is no cycle.

- [ ] **Step 4: Add `root` to `__init__` and the three new buffers**

In `src/led_ticker/plugin.py`, replace `PluginAPI.__init__` (lines 53–65) with:

```python
    def __init__(self, namespace: str, root: Path | None = None) -> None:
        self.namespace = namespace
        # Filesystem root for resolving api.font() relative paths. The loader
        # supplies it (the plugin's dir / package dir); None when undeterminable.
        self.root = root
        # One buffer per surface, keyed by surface name, so the loader's commit
        # is a single generic loop as later phases add surfaces.
        self._buffers: dict[str, dict[str, Any]] = {
            "widgets": {},
            "transitions": {},
            "color_providers": {},
            "animations": {},
            "borders": {},
            "easing": {},
            "emojis": {},
            "hires_emojis": {},
            "fonts": {},
        }
```

- [ ] **Step 5: Add the `emoji`, `hires_emoji`, and `font` methods**

In `src/led_ticker/plugin.py`, immediately after the `easing` method (ends at line 129), add:

```python
    def emoji(self, slug: str, data: PixelData) -> None:
        """Register a low-res 8x8 emoji under ``namespace.slug``.

        Direct call (not a decorator) — emoji data is a pixel list, not a
        class. Resolvable inline as ``:namespace.slug:`` once committed.
        """
        self._buffers["emojis"][self._qualify(slug)] = data

    def hires_emoji(self, slug: str, data: HiResEmoji) -> None:
        """Register a hi-res emoji under ``namespace.slug``.

        Used preferentially when the canvas is scaled (``scale > 1``). With no
        matching ``emoji(slug, ...)`` there is no low-res fallback, so the slug
        only renders on a scaled canvas — same rule as built-in hi-res-only
        sprites. Direct call.
        """
        self._buffers["hires_emojis"][self._qualify(slug)] = data

    def font(self, name: str, path: str) -> None:
        """Register a font file under ``namespace.name``.

        ``path`` is relative to the plugin's root (its directory for a local
        plugin, its package dir for an installed one). Resolved to an absolute
        path now; the font loader consults it ahead of ``config/fonts/`` and
        the bundled fonts. Direct call — a font is a file, not a class.
        """
        if self.root is None:
            raise ValueError(
                f"api.font({name!r}) needs a plugin root, but none could be "
                "determined for this plugin (zip-imported package?)."
            )
        self._buffers["fonts"][self._qualify(name)] = (self.root / path).resolve()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_plugins/test_plugin_api.py -q`
Expected: PASS (all tests in the file, including the pre-existing ones).

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/plugin.py tests/test_plugins/test_plugin_api.py
git -c core.hooksPath=/dev/null commit -m "feat(plugins): add emoji/hires_emoji/font API surface + re-exports"
```

---

## Task C2: Registry wiring + emoji lazy-build fix + `_PLUGIN_FONTS`

**Files:**
- Modify: `src/led_ticker/fonts/hires_loader.py`
- Modify: `src/led_ticker/pixel_emoji.py`
- Modify: `src/led_ticker/_plugin_loader.py`
- Test: `tests/test_plugins/test_emoji_plugins.py` (create)

**Context:** The three new buffers from C1 are silently skipped by `_commit` until they're in `_REGISTRY_MAP` (it logs `surface ... not in _REGISTRY_MAP` and continues). This task wires them up. Two registries already exist in `pixel_emoji.py` (`EMOJI_REGISTRY`, `HIRES_REGISTRY`); the third (`_PLUGIN_FONTS`) is created in `hires_loader.py`.

**Sharp edge being fixed:** `EMOJI_REGISTRY` is built lazily by `_get_registry()` (pixel_emoji.py:2793), gated on `if not EMOJI_REGISTRY`. Once Phase C commits a namespaced slug into `EMOJI_REGISTRY`, that gate sees a non-empty dict and **never loads the built-ins** — every built-in emoji would silently vanish. The fix: gate on an explicit sentinel and merge built-ins with `setdefault` (so a pre-committed plugin slug can't suppress them).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins/test_emoji_plugins.py`:

```python
import led_ticker.pixel_emoji as pe
from led_ticker import _plugin_loader as L


def test_plugin_emoji_commit_does_not_suppress_builtins():
    """A namespaced slug committed before the lazy build must NOT stop the
    built-ins from loading (regression for the `if not EMOJI_REGISTRY` gate)."""
    L.reset_plugins()
    # Force the un-built state, then simulate a plugin commit landing first.
    pe.EMOJI_REGISTRY.clear()
    pe._EMOJI_BUILTINS_LOADED = False
    pe.EMOJI_REGISTRY["acme.spark"] = pe.HEART  # any PixelData
    try:
        reg = pe._get_registry()
        assert "acme.spark" in reg, "plugin slug was dropped"
        assert "heart" in reg, "built-in emojis were suppressed by the plugin slug"
    finally:
        pe.EMOJI_REGISTRY.pop("acme.spark", None)


def test_registry_map_includes_emoji_and_font_surfaces():
    assert L._REGISTRY_MAP["emojis"] is pe.EMOJI_REGISTRY
    assert L._REGISTRY_MAP["hires_emojis"] is pe.HIRES_REGISTRY
    from led_ticker.fonts.hires_loader import _PLUGIN_FONTS

    assert L._REGISTRY_MAP["fonts"] is _PLUGIN_FONTS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins/test_emoji_plugins.py -q`
Expected: FAIL — `AttributeError: module 'led_ticker.pixel_emoji' has no attribute '_EMOJI_BUILTINS_LOADED'`; `KeyError: 'emojis'` in `_REGISTRY_MAP`.

- [ ] **Step 3: Fix the lazy build gate in `pixel_emoji.py`**

In `src/led_ticker/pixel_emoji.py`, replace `_get_registry` (lines 2793–2797) with:

```python
_EMOJI_BUILTINS_LOADED = False


def _get_registry() -> dict[str, PixelData]:
    """Return EMOJI_REGISTRY, materializing built-ins on first use.

    Uses an explicit sentinel rather than ``if not EMOJI_REGISTRY`` because a
    plugin may commit a namespaced slug into EMOJI_REGISTRY before any built-in
    lookup happens; a truthiness gate would then see a non-empty dict and never
    load the built-ins. ``setdefault`` also guarantees built-ins never clobber
    an already-committed plugin slug (slugs are namespaced, so they cannot
    collide anyway — belt-and-suspenders).
    """
    global _EMOJI_BUILTINS_LOADED  # noqa: PLW0603
    if not _EMOJI_BUILTINS_LOADED:
        for slug, data in _build_emoji_registry().items():
            EMOJI_REGISTRY.setdefault(slug, data)
        _EMOJI_BUILTINS_LOADED = True
    return EMOJI_REGISTRY
```

- [ ] **Step 4: Define `_PLUGIN_FONTS` in `hires_loader.py`**

In `src/led_ticker/fonts/hires_loader.py`, immediately before `def _find_font_path` (line 86), add:

```python
# Plugin-contributed fonts: ``namespace.name`` -> absolute path to the font
# file. Populated by the plugin loader's commit; consulted by _find_font_path
# ahead of the user + bundled dirs. Cleared (dotted keys) by reset_plugins().
_PLUGIN_FONTS: dict[str, Path] = {}
```

- [ ] **Step 5: Wire the three registries into `_REGISTRY_MAP`**

In `src/led_ticker/_plugin_loader.py`, add to the import block (after line 17, `from led_ticker.widgets import _WIDGET_REGISTRY`):

```python
from led_ticker.fonts.hires_loader import _PLUGIN_FONTS
from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY
```

Replace `_REGISTRY_MAP` (lines 25–32) with:

```python
_REGISTRY_MAP: dict[str, dict[str, Any]] = {
    "widgets": _WIDGET_REGISTRY,
    "transitions": _TRANSITION_REGISTRY,
    "color_providers": _PROVIDER_REGISTRY,
    "animations": _ANIMATION_REGISTRY,
    "borders": _BORDER_REGISTRY,
    "easing": EASING,
    "emojis": EMOJI_REGISTRY,
    "hires_emojis": HIRES_REGISTRY,
    "fonts": _PLUGIN_FONTS,
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_plugins/test_emoji_plugins.py -q`
Expected: PASS.

- [ ] **Step 7: Run the full plugin suite + emoji suite (no regressions)**

Run: `pytest tests/test_plugins/ tests/test_pixel_emoji.py -q`
Expected: PASS (the `reset_plugins()` loop now also clears dotted keys from `EMOJI_REGISTRY`/`HIRES_REGISTRY`/`_PLUGIN_FONTS`; built-in bare-slug entries are untouched).

> If `tests/test_pixel_emoji.py` does not exist, run `pytest tests/test_plugins/ -q -k emoji` plus `pytest tests/ -q -k pixel_emoji` to exercise the emoji paths.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/pixel_emoji.py src/led_ticker/fonts/hires_loader.py \
        src/led_ticker/_plugin_loader.py tests/test_plugins/test_emoji_plugins.py
git -c core.hooksPath=/dev/null commit -m "feat(plugins): wire emoji/hires/font registries; fix lazy emoji build gate"
```

---

## Task C3: Widen the inline emoji pattern (`:ns.slug:`) — single source of truth

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py`
- Test: `tests/test_plugins/test_emoji_plugins.py` (extend)

**Context:** Inline emoji are parsed by `_parse_segments` (pixel_emoji.py:2800), which splits on a **hardcoded literal** `re.split(r"(:[a-z_]+:)", text)` — separate from the `EMOJI_PATTERN` constant at line 37. That literal only admits `[a-z_]+`, so `:acme.heart:` mis-parses (no dot allowed). Widen the pattern to admit a leading `[a-z_]` then any of `[a-z0-9_.]`, and make `_parse_segments` split via `EMOJI_PATTERN.pattern` so there is exactly one pattern definition (no drift). The widened class still matches every built-in slug (`heart`, `partly_cloudy`, …) and still rejects clock-like `12:30:45` (the char after `:` must be `[a-z_]`, not a digit).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_emoji_plugins.py`:

```python
import inspect


def test_emoji_pattern_admits_namespaced_and_builtin_slugs():
    assert pe.EMOJI_PATTERN.fullmatch(":acme.heart:")
    assert pe.EMOJI_PATTERN.fullmatch(":heart:")
    assert pe.EMOJI_PATTERN.fullmatch(":partly_cloudy:")
    # A clock time must NOT be treated as an emoji token.
    assert pe.EMOJI_PATTERN.search("score 12:30:45 final") is None


def test_parse_segments_uses_the_shared_pattern_and_parses_namespaced():
    # DRY: the split must derive from EMOJI_PATTERN, not a hardcoded literal.
    src = inspect.getsource(pe._parse_segments)
    assert "EMOJI_PATTERN.pattern" in src

    pe._get_registry()  # materialize built-ins
    pe.EMOJI_REGISTRY["acme.spark"] = pe.HEART
    try:
        segs = pe._parse_segments("hi :acme.spark: and :heart: ok")
        assert ("emoji", "acme.spark") in segs
        assert ("emoji", "heart") in segs
    finally:
        pe.EMOJI_REGISTRY.pop("acme.spark", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins/test_emoji_plugins.py -q -k "pattern or parse_segments"`
Expected: FAIL — `:acme.heart:` doesn't fullmatch the old `:[a-z_]+:`; `EMOJI_PATTERN.pattern` not found in `_parse_segments` source; `acme.spark` not parsed as an emoji.

- [ ] **Step 3: Widen `EMOJI_PATTERN`**

In `src/led_ticker/pixel_emoji.py`, replace line 37:

```python
EMOJI_PATTERN: re.Pattern[str] = re.compile(r":[a-z_]+:")
```

with:

```python
# Admits both built-in slugs (`:heart:`, `:partly_cloudy:`) and namespaced
# plugin slugs (`:acme.heart:`). The leading `[a-z_]` keeps clock times like
# `12:30:45` from being parsed as emoji tokens.
EMOJI_PATTERN: re.Pattern[str] = re.compile(r":[a-z_][a-z0-9_.]*:")
```

- [ ] **Step 4: Make `_parse_segments` split via the shared pattern**

In `src/led_ticker/pixel_emoji.py`, in `_parse_segments` (line 2805), replace:

```python
    parts = re.split(r"(:[a-z_]+:)", text)
```

with:

```python
    parts = re.split(f"({EMOJI_PATTERN.pattern})", text)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_plugins/test_emoji_plugins.py -q`
Expected: PASS.

- [ ] **Step 6: Guard against regressions in the broader emoji render path**

Run: `pytest tests/ -q -k "emoji or pixel_emoji"`
Expected: PASS — built-in inline emoji (`:heart:`, `:partly_cloudy:`, variant slugs like `:heart_red:`) still parse and render unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/pixel_emoji.py tests/test_plugins/test_emoji_plugins.py
git -c core.hooksPath=/dev/null commit -m "feat(plugins): widen inline emoji pattern for namespaced :ns.slug: tokens"
```

---

## Task C4: Font root resolution + `_find_font_path` consults `_PLUGIN_FONTS`

**Files:**
- Modify: `src/led_ticker/_plugin_loader.py`
- Modify: `src/led_ticker/fonts/hires_loader.py`
- Test: `tests/test_plugins/test_font_plugins.py` (create)

**Context:** `api.font(name, path)` (added in C1) needs `api.root`. The loader builds the API in `_load_one` (currently `api = PluginAPI(namespace)` at _plugin_loader.py:116). The plugin's root is derived from the discovery `source` string — for local plugins `source` is the filesystem path to the `.py` file or package dir (`_discover_local` yields `str(entry)`); for entry points it's `"entry-point:<value>"` (no path), so the root comes from the register callable's module file. This keeps the discovery tuple arity unchanged (so Phase A's discovery tests still pass). `_find_font_path` then consults `_PLUGIN_FONTS` before the user/bundled scan; because plugin font names are namespaced (dotted) they never collide with built-in font names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins/test_font_plugins.py`:

```python
from pathlib import Path

from led_ticker import _plugin_loader as L
from led_ticker.fonts import hires_loader


def test_resolve_root_for_single_file_local_plugin():
    # source is the path to the .py file -> root is its parent dir.
    root = L._resolve_root("/tmp/cfg/plugins/myclock.py", lambda api: None)
    assert root == Path("/tmp/cfg/plugins")


def test_resolve_root_for_package_local_plugin(tmp_path):
    # source is the package dir itself -> root is that dir.
    pkg = tmp_path / "myclock"
    pkg.mkdir()
    root = L._resolve_root(str(pkg), lambda api: None)
    assert root == pkg


def test_resolve_root_for_entry_point_uses_module_file(tmp_path):
    # Entry-point source has no path; root comes from the register's module.
    mod_file = tmp_path / "acme_pkg" / "__init__.py"
    mod_file.parent.mkdir()
    mod_file.write_text("def register(api):\n    pass\n")
    import importlib.util

    spec = importlib.util.spec_from_file_location("acme_pkg_test", mod_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = L._resolve_root("entry-point:acme_pkg:register", module.register)
    assert root == mod_file.parent


def test_find_font_path_prefers_plugin_fonts(tmp_path):
    font = tmp_path / "Brand.ttf"
    font.write_bytes(b"not-a-real-font")  # presence is all _find_font_path checks
    hires_loader._PLUGIN_FONTS["acme.Brand"] = font.resolve()
    try:
        assert hires_loader._find_font_path("acme.Brand") == font.resolve()
        # A missing registered path resolves to None (not an exception).
        hires_loader._PLUGIN_FONTS["acme.Gone"] = tmp_path / "nope.ttf"
        assert hires_loader._find_font_path("acme.Gone") is None
    finally:
        hires_loader._PLUGIN_FONTS.pop("acme.Brand", None)
        hires_loader._PLUGIN_FONTS.pop("acme.Gone", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins/test_font_plugins.py -q`
Expected: FAIL — `AttributeError: module 'led_ticker._plugin_loader' has no attribute '_resolve_root'`; `_find_font_path` ignores `_PLUGIN_FONTS`.

- [ ] **Step 3: Add `_resolve_root` and use it in `_load_one`**

In `src/led_ticker/_plugin_loader.py`, add to the imports (after line 5, `import logging`):

```python
import inspect
```

Add this function immediately before `def _load_one` (before line 88):

```python
def _resolve_root(
    source: str, register: Callable[[PluginAPI], None]
) -> Path | None:
    """Best-effort plugin root for resolving ``api.font()`` relative paths.

    Local plugins: the dir containing the plugin file — a single-file plugin's
    parent (the plugins dir), or the package dir itself. Entry-point plugins:
    the dir of the register callable's module. Returns ``None`` when it cannot
    be determined (e.g. a zip-imported package); ``api.font`` then raises a
    clear error rather than guessing.
    """
    if source.startswith("entry-point:"):
        module = inspect.getmodule(register)
        module_file = getattr(module, "__file__", None)
        return Path(module_file).parent if module_file else None
    path = Path(source)
    return path.parent if path.is_file() else path
```

In `_load_one`, replace line 116:

```python
    api = PluginAPI(namespace)
```

with:

```python
    root = _resolve_root(source, register)
    api = PluginAPI(namespace, root=root)
```

- [ ] **Step 4: Make `_find_font_path` consult `_PLUGIN_FONTS` first**

In `src/led_ticker/fonts/hires_loader.py`, replace `_find_font_path` (lines 86–97) with:

```python
def _find_font_path(name: str) -> Path | None:
    """Look up a font by name: plugin fonts first, then user + bundled dirs.

    Plugin fonts (namespaced, e.g. ``acme.Brand``) win because their names
    cannot collide with built-in/user font names. A registered-but-missing
    plugin path returns ``None`` (treated as "not found", same as the dir
    scan), so a broken plugin font surfaces as ``UnknownFontError`` rather
    than crashing. User dir then wins over bundled on collisions. Tries
    ``.otf`` first, then ``.ttf``.
    """
    plugin_path = _PLUGIN_FONTS.get(name)
    if plugin_path is not None:
        return plugin_path if plugin_path.exists() else None
    for ext in (".otf", ".ttf"):
        for base in (USER_FONT_DIR, BUNDLED_HIRES_DIR):
            candidate = base / f"{name}{ext}"
            if candidate.exists():
                return candidate.resolve()
    return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_plugins/test_font_plugins.py -q`
Expected: PASS.

- [ ] **Step 6: Run the loader + font suites (no regressions)**

Run: `pytest tests/test_plugins/ tests/ -q -k "loader or font or hires"`
Expected: PASS — the discovery-tuple arity is unchanged, so existing loader tests still pass; `_resolve_root` is additive.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/_plugin_loader.py src/led_ticker/fonts/hires_loader.py \
        tests/test_plugins/test_font_plugins.py
git -c core.hooksPath=/dev/null commit -m "feat(plugins): resolve plugin root + plugin font lookup in _find_font_path"
```

---

## Task C5: End-to-end — a local plugin contributes an emoji, hi-res emoji, and font

**Files:**
- Test: `tests/test_plugins/test_font_plugins.py` (extend), `tests/test_plugins/test_emoji_plugins.py` (extend)

**Context:** This proves the whole Phase C path through the real `load_plugins` entry point — a temp `config/plugins/` dir with one plugin file that registers a low-res emoji, a hi-res emoji, and a font (a real bundled `.ttf`/`.otf` copied in), then asserts each resolves through the production code (`_get_registry`, `HIRES_REGISTRY`, `measure_emoji_at` on a scaled canvas, `resolve_font`). It also confirms the spec's hi-res-only rule (a slug registered only via `hires_emoji` does not appear in the low-res registry). No `src/` changes — if any assertion fails, the gap is in C1–C4 and must be fixed there.

- [ ] **Step 1: Write the failing end-to-end test**

Append to `tests/test_plugins/test_font_plugins.py`:

```python
import textwrap

import pytest

from led_ticker.fonts import resolve_font
from led_ticker.fonts.hires_loader import BUNDLED_HIRES_DIR, load_hires_font


def _a_bundled_font_path() -> Path:
    for ext in ("*.otf", "*.ttf"):
        hits = sorted(BUNDLED_HIRES_DIR.glob(ext))
        if hits:
            return hits[0]
    pytest.skip("no bundled hi-res font available to copy")


def test_local_plugin_contributes_emoji_hires_and_font(tmp_path):
    import led_ticker.pixel_emoji as pe
    from led_ticker import _plugin_loader as L

    L.reset_plugins()
    load_hires_font.cache_clear()

    plugin_dir = tmp_path / "plugins"
    fonts_dir = plugin_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    # Copy a real bundled font in as the plugin's Brand.ttf so resolve_font
    # actually rasterizes it.
    src_font = _a_bundled_font_path()
    (fonts_dir / "Brand.ttf").write_bytes(src_font.read_bytes())

    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import HiResEmoji

            def register(api):
                api.emoji("spark", [(0, 0, 255, 0, 0)])
                api.hires_emoji(
                    "glow",
                    HiResEmoji(pixels=((0, 0, 255, 255, 0),), physical_size=16),
                )
                api.font("Brand", "fonts/Brand.ttf")
            """
        )
    )

    try:
        result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed

        # Low-res emoji resolves through the production registry accessor.
        assert "acme.spark" in pe._get_registry()
        # Hi-res emoji landed in the hi-res registry...
        assert "acme.glow" in pe.HIRES_REGISTRY
        # ...and is hi-res-ONLY (no low-res fallback for it).
        assert "acme.glow" not in pe._get_registry()

        # Font resolves to a real rasterized HiresFont.
        font = resolve_font("acme.Brand", size=16)
        assert font.__class__.__name__ == "HiresFont"
    finally:
        L.reset_plugins()
        load_hires_font.cache_clear()
```

- [ ] **Step 2: Write the failing scaled-canvas emoji measurement test**

Append to `tests/test_plugins/test_emoji_plugins.py`:

```python
def test_plugin_hires_emoji_measures_on_scaled_canvas(tmp_path):
    import textwrap

    from led_ticker.pixel_emoji import ScaledCanvas, measure_emoji_at

    L.reset_plugins()
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import HiResEmoji

            def register(api):
                api.hires_emoji(
                    "glow",
                    HiResEmoji(pixels=((0, 0, 255, 255, 0),), physical_size=16),
                )
            """
        )
    )
    try:
        result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed
        scaled = ScaledCanvas(scale=2)
        width = measure_emoji_at(scaled, "acme.glow")
        assert isinstance(width, int) and width > 0
    finally:
        L.reset_plugins()
```

> **If `ScaledCanvas` cannot be constructed with `scale=2` alone** (check its `__init__`), build it the way existing tests in the repo do — search `tests/` for `ScaledCanvas(` and copy a working construction. The assertion (a positive int width) is what matters, not the exact canvas wiring.

- [ ] **Step 3: Run the tests to verify they fail (or reveal a gap)**

Run: `pytest tests/test_plugins/test_font_plugins.py tests/test_plugins/test_emoji_plugins.py -q -k "local_plugin or scaled_canvas"`
Expected: FAIL only if a C1–C4 gap exists. If they fail for a *fixture* reason (e.g. `ScaledCanvas` construction), fix the test per the note. If they fail for a *production* reason, fix the responsible earlier task.

- [ ] **Step 4: Make them pass**

These tests should pass on correct C1–C4 implementations with no `src/` change. If a real gap surfaces, fix it in the owning module (plugin.py / pixel_emoji.py / hires_loader.py / _plugin_loader.py) and re-run.

- [ ] **Step 5: Run the whole plugin suite**

Run: `pytest tests/test_plugins/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_plugins/test_font_plugins.py tests/test_plugins/test_emoji_plugins.py
git -c core.hooksPath=/dev/null commit -m "test(plugins): end-to-end local plugin emoji + hires + font resolution"
```

---

## Task C6: Phase C final verification

**Files:** none (verification only)

- [ ] **Step 1: Lint**

Run: `make lint`
Expected: `All checks passed!`

- [ ] **Step 2: Typecheck**

Run: `make typecheck`
Expected: `0 errors, 0 warnings, 0 informations`

- [ ] **Step 3: Full test suite + coverage**

Run: `make test`
Expected: all green (baseline 2496 passed + the Phase C additions), coverage ≥ the project floor (≈95%).

- [ ] **Step 4: Confirm the public-API tripwire reflects the new surface**

Run: `pytest tests/test_plugins/test_plugin_api.py -q -k export`
Expected: PASS — `PixelData`, `HiResEmoji`, `draw_emoji_at`, `measure_emoji_at`, `get_text_width`, `compute_baseline`, `colors` all exported from `led_ticker.plugin`.

- [ ] **Step 5: Report**

Summarize: surfaces added (`emojis`, `hires_emojis`, `fonts`), the lazy-build gate fix, the widened inline pattern, font-root resolution, and the green suite. Hand back to the controller for the final whole-phase review + `finishing-a-development-branch`.

---

## Self-Review (performed against the spec)

**1. Spec coverage (Phase C lines of `2026-05-31-plugin-system-design.md`):**
- "widened inline parsing" → Task C3 (EMOJI_PATTERN + `_parse_segments`, single source of truth).
- "`_PLUGIN_FONTS` with package-resource resolution" → Task C2 (registry) + C4 (`_resolve_root` handles both local dir and installed-package module file; the entry-point branch covers the package case the spec calls "importlib.resources for an installed package" via the module `__file__`).
- "`api.emoji` / `api.hires_emoji` insert `ns.slug` … lo/hi-res fallback … resolve namespaced slugs … hi-res-only requires scale>1" → C1 (methods) + C2 (registry wiring) + C5 (end-to-end incl. the hi-res-only rule).
- "font loader gains a namespaced lookup that consults `_PLUGIN_FONTS` before the config/fonts → bundled → BDF-alias chain" → C4 (`_find_font_path`). The `@functools.lru_cache` key `(name, size, threshold)` is unchanged (name is now `ns.font`).
- "Loose user fonts keep working via config/fonts/" → unchanged dir scan retained in `_find_font_path`.
- Re-exports (`PixelData`, `HiResEmoji`, drawing helpers, `colors`) from the spec's public-surface list → C1.

**2. Placeholder scan:** No TBD/"handle errors"/"similar to". Every code step shows complete code. The one conditional ("if `ScaledCanvas` needs more args") gives an explicit fallback procedure, not a placeholder.

**3. Type/name consistency:** Surface keys (`emojis`, `hires_emojis`, `fonts`) are identical across `_buffers` (C1), `_REGISTRY_MAP` (C2), and the commit loop. `_PLUGIN_FONTS` is `dict[str, Path]` in C2 and consumed as such in C4. `api.font` stores a resolved `Path`; `_find_font_path` returns `Path | None`; both agree. `_resolve_root` signature in C4 matches its test in C4 and its call site in `_load_one`. `root: Path | None = None` added in C1 is what C4 passes.

**Pitfall explicitly handled:** the lazy `_get_registry()` truthiness gate (would suppress built-ins once a plugin commits an emoji) — fixed in C2 with a sentinel + `setdefault`, regression-tested.

# Plugin System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let widgets, transitions, emojis, color providers, animations, borders, easing, and fonts be contributed from outside `src/led_ticker` (local `config/plugins/` files or installed entry-point packages), namespaced and error-isolated, plus lifecycle hooks (validation, overlay, startup/shutdown).

**Architecture:** A single public module `led_ticker.plugin` (the only thing plugins import) exposes a namespace-bound `PluginAPI` whose calls buffer registrations; an internal `_plugin_loader` discovers plugins from both channels, calls each plugin's `register(api)`, and commits the buffer atomically into the existing registries (or logs-and-skips on failure). Names are `namespace.name` (dot separator).

**Tech Stack:** Python 3.14, `importlib.util` / `importlib.metadata` (entry points), the existing `_WIDGET_REGISTRY` / `_TRANSITION_REGISTRY` / coercion maps / emoji & font loaders, pytest.

**Spec:** `docs/superpowers/specs/2026-05-31-plugin-system-design.md`

**Conventions for every task:**
- New files do **not** add `from __future__ import annotations` (the repo is on 3.14 / PEP 649; the import was removed everywhere — a tripwire forbids it).
- Run tests: `PYTHONPATH=tests/stubs uv run --extra dev pytest <path>` (uv reads `.python-version` = 3.14).
- Commit hooks-disabled (worktree hooks broken): `git -c core.hooksPath=/dev/null commit` (use `bash -c '...'` for multi-line messages).
- 88-char ruff limit; run `make lint` before each commit. End commit messages with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

**Scope of THIS plan: Phase A (the framework) in full.** Phases B–E are a task-level roadmap at the end; each will be expanded into its own bite-sized plan after Phase A lands and the real API shape is proven (so they reflect reality rather than guesses). Phase A is a complete, independently-testable milestone: a local or entry-point plugin can contribute a working namespaced widget and transition with no core fork, with atomic load + error isolation.

---

## File Structure (all phases — map)

**New:**
- `src/led_ticker/plugin.py` — public author API (`PluginAPI`, re-exports, `API_VERSION`, `StartupContext`). *(Phase A: widgets/transitions + framework; later phases add methods.)*
- `src/led_ticker/_plugin_loader.py` — discovery (local + entry points), atomic commit, error isolation, `LoadedPlugins`. *(Phase A core; later phases extend commit + hook collection.)*
- `tests/test_plugins/` — loader + per-surface tests; fixture plugins written to `tmp_path`.
- `examples/plugins/` — reference plugin *(Phase E)*.

**Modified across phases:** `app/run.py` (load + hook wiring), `app/coercion.py` (provider/animation/border maps → registries — Phase B), `pixel_emoji.py` (emoji namespacing — Phase C), fonts loader (Phase C), `app/cli.py` + `validate.py` + `config.py` (Phase E), `config.example.toml` + `CLAUDE.md` + docs (Phase E).

---

## Task A1: Public API module (`led_ticker.plugin`)

**Files:**
- Create: `src/led_ticker/plugin.py`
- Test: `tests/test_plugins/test_plugin_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/__init__.py` (empty) and `tests/test_plugins/test_plugin_api.py`:

```python
from led_ticker.plugin import API_VERSION, PluginAPI


def test_widget_decorator_buffers_under_namespace():
    api = PluginAPI("acme")

    @api.widget("clock")
    class Clock:
        pass

    assert api._widgets == {"acme.clock": Clock}
    assert api._transitions == {}


def test_transition_decorator_buffers_under_namespace():
    api = PluginAPI("acme")

    @api.transition("swoosh")
    class Swoosh:
        pass

    assert api._transitions == {"acme.swoosh": Swoosh}


def test_decorator_returns_the_class_unchanged():
    api = PluginAPI("acme")

    class W:
        pass

    assert api.widget("w")(W) is W


def test_api_version_is_major_minor_tuple():
    assert isinstance(API_VERSION, tuple) and len(API_VERSION) == 2


def test_public_surface_exports_protocols():
    import led_ticker.plugin as p

    for name in ("PluginAPI", "API_VERSION", "Widget", "Transition", "Canvas",
                 "spawn_tracked"):
        assert hasattr(p, name), f"missing public export: {name}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_plugin_api.py -v`
Expected: FAIL — `led_ticker.plugin` does not exist.

- [ ] **Step 3: Implement**

Create `src/led_ticker/plugin.py`:

```python
"""Public plugin API for led-ticker.

Plugins import ONLY this module. Everything else under ``led_ticker`` is
internal and may change without notice. A plugin defines a top-level
``register(api)`` function; the loader passes a :class:`PluginAPI` bound to the
plugin's namespace. Every registered name is auto-prefixed with that namespace
(``"namespace.name"``) and buffered until the loader commits it atomically.
"""

from collections.abc import Callable

# Re-exports: the stable surface plugin authors subclass / annotate against.
from led_ticker._types import Canvas
from led_ticker.transitions import Transition
from led_ticker.widget import Widget, spawn_tracked

__all__ = [
    "API_VERSION",
    "PluginAPI",
    "Canvas",
    "Transition",
    "Widget",
    "spawn_tracked",
]

API_VERSION: tuple[int, int] = (1, 0)


class PluginAPI:
    """Namespace-bound registrar passed to a plugin's ``register(api)``.

    Calls buffer registrations keyed by the namespaced name; the loader commits
    the buffers into the real registries only if ``register`` returns cleanly.
    A plugin therefore cannot register a bare (un-namespaced) name and cannot
    half-register on error.
    """

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._widgets: dict[str, type] = {}
        self._transitions: dict[str, type] = {}

    def _qualify(self, name: str) -> str:
        return f"{self.namespace}.{name}"

    def widget(self, name: str) -> Callable[[type], type]:
        """Register a widget class under ``namespace.name``."""

        def deco(cls: type) -> type:
            self._widgets[self._qualify(name)] = cls
            return cls

        return deco

    def transition(self, name: str) -> Callable[[type], type]:
        """Register a transition class under ``namespace.name``."""

        def deco(cls: type) -> type:
            self._transitions[self._qualify(name)] = cls
            return cls

        return deco
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_plugin_api.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint + commit**

```bash
make lint
git add src/led_ticker/plugin.py tests/test_plugins/
git -c core.hooksPath=/dev/null commit -m "feat: public PluginAPI surface (widget/transition buffering)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task A2: Loader core — atomic commit + error isolation

**Files:**
- Create: `src/led_ticker/_plugin_loader.py`
- Test: `tests/test_plugins/test_loader_core.py`

**Context:** The loader writes a plugin's buffered registrations into `_WIDGET_REGISTRY` / `_TRANSITION_REGISTRY` (in `led_ticker.widgets` / `led_ticker.transitions`) **only after** its `register(api)` returns cleanly — that is the atomicity guarantee. A plugin whose `register` raises is logged and skipped; the registries are untouched.

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_loader_core.py`:

```python
import pytest

from led_ticker import _plugin_loader as L
from led_ticker.plugin import PluginAPI
from led_ticker.transitions import _TRANSITION_REGISTRY
from led_ticker.widgets import _WIDGET_REGISTRY


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def _ok_register(api):
    @api.widget("clock")
    class Clock:
        pass

    @api.transition("swoosh")
    class Swoosh:
        pass


def test_clean_register_commits_namespaced(tmp_path):
    result = L.LoadedPlugins()
    L._load_one("acme", "test", _ok_register, None, set(), result)
    assert "acme.clock" in _WIDGET_REGISTRY
    assert "acme.swoosh" in _TRANSITION_REGISTRY
    assert result.loaded[0].namespace == "acme"
    assert result.loaded[0].widgets == 1
    assert not result.failed


def test_raising_register_is_isolated_and_atomic():
    def boom(api):
        @api.widget("ok")
        class Ok:
            pass

        raise RuntimeError("kaboom")

    result = L.LoadedPlugins()
    L._load_one("bad", "test", boom, None, set(), result)
    # Nothing committed (atomic), recorded as failed, no exception propagated.
    assert "bad.ok" not in _WIDGET_REGISTRY
    assert result.loaded == []
    assert result.failed and result.failed[0][0] == "bad"


def test_cannot_shadow_a_builtin_name():
    # built-ins are bare ("weather"); a plugin name is always namespaced, so a
    # plugin can never produce a bare key. Confirm the qualified key is used.
    def reg(api):
        @api.widget("weather")  # becomes "acme.weather", NOT "weather"
        class W:
            pass

    result = L.LoadedPlugins()
    L._load_one("acme", "test", reg, None, set(), result)
    assert "acme.weather" in _WIDGET_REGISTRY
    assert _WIDGET_REGISTRY["weather"].__name__ != "W"  # builtin untouched
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_loader_core.py -v`
Expected: FAIL — `_plugin_loader` does not exist.

- [ ] **Step 3: Implement**

Create `src/led_ticker/_plugin_loader.py`:

```python
"""Plugin discovery and loading (internal). Plugins never import this."""

import logging
from dataclasses import dataclass, field

from led_ticker.plugin import API_VERSION, PluginAPI
from led_ticker.transitions import _TRANSITION_REGISTRY
from led_ticker.widgets import _WIDGET_REGISTRY

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "led_ticker.plugins"


@dataclass
class PluginInfo:
    namespace: str
    source: str
    widgets: int = 0
    transitions: int = 0


@dataclass
class LoadedPlugins:
    loaded: list[PluginInfo] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


_LOADED: LoadedPlugins | None = None


def reset_plugins() -> None:
    """Test helper: drop all namespaced (dotted) registry entries + load guard."""
    global _LOADED  # noqa: PLW0603
    for reg in (_WIDGET_REGISTRY, _TRANSITION_REGISTRY):
        for key in [k for k in reg if "." in k]:
            del reg[key]
    _LOADED = None


def _commit(api: PluginAPI, info: PluginInfo) -> None:
    """Write a cleanly-registered plugin's buffers into the registries.

    Two-pass (validate all, then write all) so a mid-commit collision can't
    leave a partial registration.
    """
    for name in api._widgets:
        if name in _WIDGET_REGISTRY:
            raise ValueError(f"widget {name!r} already registered")
    for name in api._transitions:
        if name in _TRANSITION_REGISTRY:
            raise ValueError(f"transition {name!r} already registered")
    for name, cls in api._widgets.items():
        _WIDGET_REGISTRY[name] = cls
        info.widgets += 1
    for name, cls in api._transitions.items():
        _TRANSITION_REGISTRY[name] = cls
        info.transitions += 1


def _load_one(
    namespace: str,
    source: str,
    register,
    requires_api: int | None,
    loaded_namespaces: set[str],
    result: LoadedPlugins,
) -> None:
    """Run + commit one plugin's register(), isolating all failures."""
    if namespace in loaded_namespaces:
        result.failed.append(
            (namespace, "namespace already claimed by another plugin")
        )
        logger.error("plugin namespace %r already claimed; skipping %s",
                     namespace, source)
        return
    if requires_api is not None and requires_api != API_VERSION[0]:
        msg = f"requires API v{requires_api}, core is v{API_VERSION[0]}"
        result.failed.append((namespace, msg))
        logger.error("plugin %r %s; skipping", namespace, msg)
        return
    if register is None or not callable(register):
        result.failed.append((namespace, "no callable register(api) found"))
        logger.error("plugin %r has no register(api); skipping %s",
                     namespace, source)
        return
    api = PluginAPI(namespace)
    info = PluginInfo(namespace=namespace, source=source)
    try:
        register(api)
        _commit(api, info)
    except Exception as e:  # isolation: a plugin must never crash the app
        logger.exception("plugin %r (%s) failed to load", namespace, source)
        result.failed.append((namespace, str(e)))
        return
    loaded_namespaces.add(namespace)
    result.loaded.append(info)
    logger.info(
        "plugin %r loaded from %s (%d widgets, %d transitions)",
        namespace, source, info.widgets, info.transitions,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_loader_core.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

```bash
make lint
git add src/led_ticker/_plugin_loader.py tests/test_plugins/test_loader_core.py
git -c core.hooksPath=/dev/null commit -m "feat: plugin loader core — atomic commit + error isolation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task A3: Local-directory discovery

**Files:**
- Modify: `src/led_ticker/_plugin_loader.py`
- Test: `tests/test_plugins/test_loader_local.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_loader_local.py`:

```python
import pytest

from led_ticker import _plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY, get_widget_class

PLUGIN_SRC = '''
from led_ticker.plugin import Widget

def register(api):
    @api.widget("clock")
    class Clock:
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            return canvas, cursor_pos
'''


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_local_py_file_namespaced_by_stem(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "myclock.py").write_text(PLUGIN_SRC)

    result = L.load_plugins(pdir, entry_points_enabled=False)

    assert "myclock.clock" in _WIDGET_REGISTRY
    assert get_widget_class("myclock.clock").__name__ == "Clock"
    assert [i.namespace for i in result.loaded] == ["myclock"]


def test_underscore_files_and_missing_dir_are_skipped(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "_helper.py").write_text("x = 1\n")
    res1 = L.load_plugins(pdir, entry_points_enabled=False)
    assert res1.loaded == []
    L.reset_plugins()
    # missing dir: no error
    res2 = L.load_plugins(tmp_path / "nope", entry_points_enabled=False)
    assert res2.loaded == [] and res2.failed == []


def test_import_error_in_plugin_is_isolated(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "broken.py").write_text("import this_module_does_not_exist\n")
    (pdir / "good.py").write_text(PLUGIN_SRC)
    result = L.load_plugins(pdir, entry_points_enabled=False)
    assert "good.clock" in _WIDGET_REGISTRY
    assert any(ns == "broken" for ns, _ in result.failed)
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_loader_local.py -v`
Expected: FAIL — `load_plugins` not defined.

- [ ] **Step 3: Implement**

Add to `src/led_ticker/_plugin_loader.py` — imports at top:

```python
import importlib.util
from pathlib import Path
from types import ModuleType
```

Add these functions (after `_load_one`):

```python
def _import_from_path(mod_name: str, init: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, init)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin module from {init}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _discover_local(plugin_dir: Path):
    """Yield (namespace, source, thunk) for each local plugin. The thunk
    imports the module lazily and returns (register, requires_api)."""
    if not plugin_dir.is_dir():
        return
    for entry in sorted(plugin_dir.iterdir()):
        if entry.name.startswith("_"):
            continue
        if entry.suffix == ".py" and entry.is_file():
            ns, init = entry.stem, entry
        elif entry.is_dir() and (entry / "__init__.py").exists():
            ns, init = entry.name, entry / "__init__.py"
        else:
            continue

        def thunk(ns=ns, init=init):
            mod = _import_from_path(f"led_ticker_plugin_{ns}", init)
            return getattr(mod, "register", None), getattr(mod, "requires_api", None)

        yield ns, str(entry), thunk


def load_plugins(plugin_dir: Path | None, *, entry_points_enabled: bool = True
                 ) -> LoadedPlugins:
    """Discover + load all plugins once. Idempotent (call reset_plugins() in
    tests to reload)."""
    global _LOADED  # noqa: PLW0603
    if _LOADED is not None:
        return _LOADED
    result = LoadedPlugins()
    loaded_ns: set[str] = set()
    sources = []
    if plugin_dir is not None:
        sources.extend(_discover_local(plugin_dir))
    # entry-point discovery added in Task A4
    for ns, source, thunk in sources:
        try:
            register, requires = thunk()
        except Exception as e:
            logger.exception("plugin %r (%s) failed to import", ns, source)
            result.failed.append((ns, str(e)))
            continue
        _load_one(ns, source, register, requires, loaded_ns, result)
    _LOADED = result
    return result
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_loader_local.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

```bash
make lint
git add src/led_ticker/_plugin_loader.py tests/test_plugins/test_loader_local.py
git -c core.hooksPath=/dev/null commit -m "feat: plugin local-directory discovery (namespace = filename)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task A4: Entry-point discovery channel

**Files:**
- Modify: `src/led_ticker/_plugin_loader.py`
- Test: `tests/test_plugins/test_loader_entrypoints.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_loader_entrypoints.py`:

```python
import importlib.metadata

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def _register(api):
    @api.widget("clock")
    class Clock:
        pass


class _FakeEP:
    def __init__(self, name, fn):
        self.name = name
        self.value = "fake:register"
        self._fn = fn

    def load(self):
        return self._fn


def test_entry_point_plugin_namespaced_by_ep_name(monkeypatch):
    def fake_entry_points(*, group):
        assert group == L.ENTRY_POINT_GROUP
        return [_FakeEP("acme", _register)]

    monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
    result = L.load_plugins(None, entry_points_enabled=True)
    assert "acme.clock" in _WIDGET_REGISTRY
    assert [i.namespace for i in result.loaded] == ["acme"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_loader_entrypoints.py -v`
Expected: FAIL — entry-point discovery not wired (no `acme.clock`).

- [ ] **Step 3: Implement**

Add to `_plugin_loader.py` imports: `import importlib.metadata`.

Add a discovery generator and call it from `load_plugins`:

```python
def _discover_entry_points():
    """Yield (namespace, source, thunk) for installed entry-point plugins."""
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # pragma: no cover - defensive across importlib versions
        return
    for ep in eps:
        def thunk(ep=ep):
            obj = ep.load()
            if callable(obj) and not isinstance(obj, type):
                return obj, getattr(obj, "requires_api", None)
            register = getattr(obj, "register", None)
            return register, getattr(obj, "requires_api", None)

        yield ep.name, f"entry-point:{ep.value}", thunk
```

In `load_plugins`, after the local-discovery block, add:

```python
    if entry_points_enabled:
        sources.extend(_discover_entry_points())
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_loader_entrypoints.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
make lint
git add src/led_ticker/_plugin_loader.py tests/test_plugins/test_loader_entrypoints.py
git -c core.hooksPath=/dev/null commit -m "feat: plugin entry-point discovery (namespace = entry-point name)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task A5: Namespace-collision + API-version isolation (integration)

**Files:**
- Test only: `tests/test_plugins/test_loader_policy.py`

**Context:** The policy logic lives in `_load_one` (Tasks A2). This task adds end-to-end tests through `load_plugins` to lock the behavior in.

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_loader_policy.py`:

```python
import pytest

from led_ticker import _plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY

ONE = '''
def register(api):
    @api.widget("a")
    class A: pass
'''
TWO = '''
def register(api):
    @api.widget("b")
    class B: pass
'''
FUTURE = '''
requires_api = 99
def register(api):
    @api.widget("c")
    class C: pass
'''


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_namespace_collision_second_skipped(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    # same namespace "dup" from two files is impossible by filename, so simulate
    # via a package dir + py file sharing a stem is also impossible; instead
    # assert the in-loader guard directly:
    result = L.LoadedPlugins()
    ns_seen: set[str] = set()
    L._load_one("dup", "p1", lambda api: api.widget("a")(type("A", (), {})), None,
                ns_seen, result)
    L._load_one("dup", "p2", lambda api: api.widget("b")(type("B", (), {})), None,
                ns_seen, result)
    assert "dup.a" in _WIDGET_REGISTRY
    assert "dup.b" not in _WIDGET_REGISTRY
    assert any(ns == "dup" for ns, _ in result.failed)


def test_incompatible_api_version_skipped(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "fromfuture.py").write_text(FUTURE)
    result = L.load_plugins(pdir, entry_points_enabled=False)
    assert "fromfuture.c" not in _WIDGET_REGISTRY
    assert any(ns == "fromfuture" for ns, _ in result.failed)
```

- [ ] **Step 2: Run to verify it fails / passes**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_loader_policy.py -v`
Expected: these should PASS already (the logic exists in `_load_one`). If `test_incompatible_api_version_skipped` fails, confirm `requires_api` is read in `_discover_local`'s thunk (Task A3) and passed through — fix if the thunk drops it.

- [ ] **Step 3: Commit**

```bash
make lint
git add tests/test_plugins/test_loader_policy.py
git -c core.hooksPath=/dev/null commit -m "test: plugin namespace-collision + API-version isolation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task A6: Wire plugin loading into the run loop

**Files:**
- Modify: `src/led_ticker/app/run.py` (after `load_config`, ~line 100)
- Test: `tests/test_plugins/test_run_integration.py`

**Context:** Plugins must be loaded before any widget is built (`_build_widget` → `get_widget_class`). The earliest safe point is right after `load_config` parses the TOML (it stores raw widget dicts; it does NOT resolve type names). For Phase A, the plugin dir defaults to `<config dir>/plugins`; the `[plugins]` config block (enable/disable/custom dir) is Phase E.

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins/test_run_integration.py`:

```python
import pytest

from led_ticker import _plugin_loader as L

PLUGIN_SRC = '''
def register(api):
    @api.widget("clock")
    class Clock:
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            return canvas, cursor_pos
'''


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_run_loads_plugins_from_config_dir(tmp_path, monkeypatch):
    # A config dir with a plugins/ subdir; assert load_plugins picks it up via
    # the helper run() uses.
    cfg_dir = tmp_path
    pdir = cfg_dir / "plugins"
    pdir.mkdir()
    (pdir / "myclock.py").write_text(PLUGIN_SRC)

    from led_ticker.app.run import _load_plugins_for_config

    result = _load_plugins_for_config(cfg_dir / "config.toml")
    from led_ticker.widgets import get_widget_class

    assert get_widget_class("myclock.clock").__name__ == "Clock"
    assert [i.namespace for i in result.loaded] == ["myclock"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_run_integration.py -v`
Expected: FAIL — `_load_plugins_for_config` not defined.

- [ ] **Step 3: Implement**

In `src/led_ticker/app/run.py`, add the import near the other `led_ticker` imports:

```python
from led_ticker._plugin_loader import load_plugins
```

Add a small helper above `async def run(...)`:

```python
def _load_plugins_for_config(config_path: Path):
    """Load plugins from <config dir>/plugins (and installed entry points).
    Phase A: the dir is fixed; the [plugins] config block lands in a later phase.
    """
    return load_plugins(config_path.parent / "plugins")
```

In `run()`, immediately after the `_configure_user_font_dir(config_path)` line (the existing line ~100, before `build_frame_from_config`), add:

```python
    plugins = _load_plugins_for_config(config_path)
    for ns, err in plugins.failed:
        logging.warning("plugin %r failed to load: %s", ns, err)
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_run_integration.py -v`
Then the full app suite for regressions:
Run: `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_app.py -q`
Expected: both PASS.

- [ ] **Step 5: Lint + typecheck + commit**

```bash
make lint
make typecheck
git add src/led_ticker/app/run.py tests/test_plugins/test_run_integration.py
git -c core.hooksPath=/dev/null commit -m "feat: load plugins in run() before widgets are built

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase A final verification

- [ ] `make lint`, `make typecheck`, `PYTHONPATH=tests/stubs uv run --extra dev pytest -q` all green on 3.14.
- [ ] End-to-end smoke: a `config/plugins/demo.py` registering a widget makes `type = "demo.<name>"` resolvable (write a throwaway config + `led-ticker validate` — note: full `validate` integration is Phase E, but `get_widget_class("demo.x")` resolving proves the registry path).
- [ ] No `from __future__ import annotations` added (the existing tripwire passes).

Phase A is a complete milestone: plugins (local + entry-point) contribute namespaced widgets and transitions, atomically and error-isolated, with no core fork.

---

# Phases B–E — roadmap (expand into full plans after Phase A)

Each phase mirrors Phase A's TDD shape (failing test → minimal impl → commit) and reuses the loader/`PluginAPI`/namespacing/atomic-commit machinery. The buffers in `PluginAPI` and the commit in `_plugin_loader._commit` extend by one surface each.

### Phase B — coercion registries (providers, animations, borders, easing)

**Files:** `src/led_ticker/app/coercion.py`, `src/led_ticker/transitions/__init__.py` (EASING), `src/led_ticker/plugin.py` (+`color_provider`/`animation`/`border`/`easing` methods + buffers), `_plugin_loader.py` (commit those buffers), `tests/test_plugins/test_coercion_plugins.py`.

- **B1 — provider registry:** replace the hardcoded `STYLE_MAP` in `coercion._provider_from_style` with `_PROVIDER_REGISTRY: dict[str, type[ColorProvider]]`; built-ins register into it; allowed kwargs derived from the provider class's `attrs` fields (preserve the current unknown/missing-kwarg error messages). Test: built-in `{style="rainbow"}` still coerces; a registered `acme.fire` coerces.
- **B2 — `api.color_provider` + commit:** add the API method/buffer and commit into `_PROVIDER_REGISTRY`. Test: a plugin provider usable via `font_color = {style="acme.fire"}`.
- **B3 — animations:** same treatment for `coercion._coerce_animation` (`coercion.py:508`) → `_ANIMATION_REGISTRY` + `api.animation`.
- **B4 — borders:** same for `coercion._coerce_border` (`coercion.py:305`, the `match style`) → `_BORDER_REGISTRY` + `api.border`.
- **B5 — easing:** `api.easing(name, fn)` commits `ns.name` into `EASING`; transitions resolve `easing = "ns.name"`. Test: a plugin easing applies.

### Phase C — emojis + fonts

**Files:** `src/led_ticker/pixel_emoji.py`, `src/led_ticker/fonts/__init__.py` + `fonts/hires_loader.py`, `plugin.py` (+`emoji`/`hires_emoji`/`font`), `_plugin_loader.py`, `tests/test_plugins/test_emoji_font_plugins.py`.

- **C1 — widen `EMOJI_PATTERN`:** `re.compile(r":[a-z_][a-z0-9_.]*:")` (and the `re.split` at `pixel_emoji.py:2701`) so `:ns.slug:` parses as one token; built-in `:slug:` unchanged. Test: `_parse_segments("hi :acme.x: there")` yields the namespaced token; built-ins still parse.
- **C2 — `api.emoji` / `api.hires_emoji`:** commit `ns.slug` into `EMOJI_REGISTRY` / `HIRES_REGISTRY`; `draw_emoji_at` / `measure_emoji_at` resolve namespaced slugs (hi-res-only slugs require `scale>1`). Test: a plugin emoji draws.
- **C3 — `api.font(name, path)` + `_PLUGIN_FONTS`:** the `PluginAPI` carries the plugin **root** (local dir or package); `font()` records `ns.name → (root, relpath)`; the font loader consults `_PLUGIN_FONTS` (resolving via `importlib.resources` for packages, filesystem for local) before the `config/fonts/`→bundled→BDF chain. Test: resolve `acme.Brand` from a local plugin dir AND a simulated package resource. **Note:** Task A2's `PluginAPI(namespace)` gains a `root` argument here; A-phase callers pass the discovered path.

### Phase D — lifecycle hooks

**Files:** `plugin.py` (+`overlay`/`on_startup`/`on_shutdown` + `StartupContext`), `_plugin_loader.py` (collect hook lists into `LoadedPlugins`), `app/run.py` (append guarded overlays after frame build; run startup hooks inside the aiohttp-session context; run shutdown hooks in `finally`), `app/factories.py` + `validate.py` (call `validate_config` classmethod), `tests/test_plugins/test_hooks.py`.

- **D1 — `validate_config` convention:** `validate_widget_cfg` / the static validator call `cls.validate_config(cfg)` when present and surface returned messages. Test: a plugin widget's rule reported by `validate`.
- **D2 — guarded overlay:** `api.overlay(paint)` → `LoadedPlugins.overlay_hooks`; `run()` wraps each in a log-and-disable guard and appends to `led_frame.overlay_hooks`. Test: a raising plugin overlay is disabled + logged; the panel still swaps (`swapping_frame`).
- **D3 — startup/shutdown:** `StartupContext(frame, session, config)`; `run()` awaits/calls startup hooks after the session opens, shutdown hooks in `finally`. Test: a startup hook spawns a tracked task; a shutdown hook fires.

### Phase E — config, CLI, docs, example

**Files:** `config.py` (`[plugins]` block: `enabled`/`dir`/`disable`), `app/run.py` + `_load_plugins_for_config` (honor `[plugins]`), `app/cli.py` (load plugins in `validate`/`--list-fields`; new `plugins` subcommand), `examples/plugins/` (reference plugin), `config.example.toml`, `CLAUDE.md`, docs-site "Plugins" page.

- **E1 — `[plugins]` config** + thread `enabled`/`dir`/`disable` into `load_plugins` (a `disable` set skips those namespaces).
- **E2 — CLI:** load plugins before `validate` and `--list-fields` (so `--list-fields acme.clock` works); add `led-ticker plugins` listing loaded/failed namespaces, sources, API version, contribution counts.
- **E3 — docs + example:** the "Plugins" page, `examples/plugins/` reference plugin (one of each surface + a hook), `config.example.toml` block, and the CLAUDE.md invariant (public-API boundary, atomic load, `.` separator + emoji reason, registry retrofits, plugin-overlay guard divergence, "plugins load after parse / before build").

---

## Cross-phase final verification (after Phase E)

- [ ] A local plugin and an entry-point package each contribute a working widget, transition, emoji, color provider, animation, border, easing, and font referenced as `ns.name`, with no `src/led_ticker` edit.
- [ ] Plugins import only `led_ticker.plugin` (import-surface tripwire).
- [ ] Broken plugin logged + skipped; app runs; siblings load.
- [ ] `validate` / `--list-fields ns.x` / `plugins` CLI all see contributions; `validate_config` / overlay / startup-shutdown hooks fire.
- [ ] `make test` / `make lint` / `make typecheck` green.
- [ ] Hand off to `superpowers:finishing-a-development-branch`.

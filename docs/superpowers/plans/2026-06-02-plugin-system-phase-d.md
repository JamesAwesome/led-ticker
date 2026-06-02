# Plugin System — Phase D (Lifecycle Hooks) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let plugins participate in the app lifecycle — a `validate_config` per-type convention, guarded overlay paint hooks, and `on_startup`/`on_shutdown` hooks receiving a `StartupContext` — without any edit to `src/led_ticker` by the plugin author.

**Architecture:** Hooks are *not* named registry entries, so (unlike Phases A–C) they do **not** go through `_buffers`/`_REGISTRY_MAP`/`_commit`. Instead `PluginAPI` collects them in plain lists; the loader gathers each successfully-loaded plugin's hooks into `LoadedPlugins` (tagged with namespace); and `app/run.py` wires them into the existing run loop. Plugin overlays are exception-wrapped (disable-and-log-once) before being appended to `LedFrame.overlay_hooks`, preserving the core "a raising overlay freezes the panel" invariant for core hooks only. `validate_config` is a by-convention classmethod the existing `validate_widget_cfg` calls when present.

**Tech Stack:** Python 3.14, pytest, attrs/dataclasses. No `from __future__ import annotations` (forbidden by tripwire). Native PEP 604/585 syntax. No new dependencies.

**Builds on (merged):** Phase A (PluginAPI/`_buffers`/`_commit`/loader), Phase B (coercion registries), Phase C (emojis + fonts). The framework is stable; Phase D adds a *second pillar* (lifecycle) alongside the registry pillar.

**Out of scope (Phase E):** `[plugins]` config block (enable/disable/dir); `led-ticker plugins` CLI; making `led-ticker validate` / `--list-fields` LOAD plugins first; `examples/plugins/`; docs site. Phase D establishes the `validate_config` *convention* at the existing `validate_widget_cfg` hook point (so it runs for any already-registered widget — built-ins always, plugin widgets once Phase E makes the CLI load them) and wires overlay/startup/shutdown into the live run loop. `validate_config` for **non-widget** surfaces (providers/transitions/borders) is deferred — the convention is established on the widget path (the documented primary case); extending it is additive later.

---

## File Structure

**Modified:**
- `src/led_ticker/plugin.py` — `StartupContext` dataclass + `StartupHook`/`ShutdownHook` type aliases; `PluginAPI` gains `_overlays`/`_startup_hooks`/`_shutdown_hooks` lists + `overlay()`/`on_startup()`/`on_shutdown()` methods; re-export `StartupContext`.
- `src/led_ticker/_plugin_loader.py` — `LoadedPlugins` gains `overlays`/`startup_hooks`/`shutdown_hooks` lists of `(namespace, callable)`; `_load_one` collects them on the success path; new helpers `_guarded_overlay`, `_run_startup_hooks`, `_run_shutdown_hooks`.
- `src/led_ticker/app/factories.py` — `_run_validate_config(cls, cfg, widget_type)` called inside `validate_widget_cfg` after `get_widget_class`.
- `src/led_ticker/app/run.py` — append guarded plugin overlays after busy-light; build a `StartupContext` and run startup hooks inside the session before the loop; wrap the main loop in `try/finally` running shutdown hooks.

**Created (tests):**
- `tests/test_plugins/test_hook_plugins.py` — API buffering, loader collection, overlay guard, startup/shutdown runners.
- `tests/test_plugins/test_validate_config.py` — the `validate_config` convention.

**Surface-parity note (do NOT mis-flag):** Phases A–C maintained "`_buffers` keys == `_REGISTRY_MAP` keys". Hooks are **lists, not name→object registries**, so they intentionally live OUTSIDE `_buffers` and are NOT in `_REGISTRY_MAP`. The 9-key buffer/registry parity is unchanged by Phase D; the three hook lists are a separate, deliberate mechanism (the spec calls this "pillar 2").

---

## Pre-flight (run once before Task D1)

- [ ] **Confirm branch and baseline**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d
git branch --show-current      # MUST print: feat/plugin-phase-d  — abort if it prints main
make dev                       # set up the project venv (uv sync; the pre-commit hook-install step may fail harmlessly because core.hooksPath is set — that is OK)
make test                      # baseline — expect all green (≈2518 passed at branch point)
```

If `git branch --show-current` is not `feat/plugin-phase-d`, STOP.

---

## Task D1: PluginAPI hook surface + StartupContext + re-exports

**Files:**
- Modify: `src/led_ticker/plugin.py`
- Test: `tests/test_plugins/test_plugin_api.py`, and create `tests/test_plugins/test_hook_plugins.py`

**Context:** `PluginAPI` (plugin.py:~64) currently buffers named registry contributions in `self._buffers`. Hooks are different — they're ordered lists of callables with no name key — so they get three dedicated list attributes, not `_buffers` entries. `overlay`/`on_startup`/`on_shutdown` are direct calls (like `easing`/`emoji`/`font`), not decorators. `StartupContext` is a small frozen dataclass passed to startup hooks; its fields are typed `Any` to avoid importing heavy internal modules (`frame.py`, config, aiohttp) into the public `plugin.py` — consistent with how `Canvas`/`Color` are already `Any` here.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_plugin_api.py`:

```python
def test_overlay_buffers_into_overlays_list():
    api = PluginAPI("acme")

    def paint(canvas):
        pass

    api.overlay(paint)
    assert api._overlays == [paint]


def test_on_startup_and_on_shutdown_buffer_into_lists():
    api = PluginAPI("acme")

    def boot(ctx):
        pass

    async def teardown():
        pass

    api.on_startup(boot)
    api.on_shutdown(teardown)
    assert api._startup_hooks == [boot]
    assert api._shutdown_hooks == [teardown]


def test_startup_context_is_exported_and_constructible():
    from led_ticker.plugin import StartupContext

    ctx = StartupContext(frame="F", session="S", config="C")
    assert (ctx.frame, ctx.session, ctx.config) == ("F", "S", "C")


def test_hook_lists_are_independent_of_buffers():
    # Hooks are NOT registry surfaces — they must not appear in _buffers.
    api = PluginAPI("acme")
    assert "overlays" not in api._buffers
    assert "startup_hooks" not in api._buffers
    assert "shutdown_hooks" not in api._buffers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugins/test_plugin_api.py -q -k "overlay or startup or shutdown or hook_lists"`
Expected: FAIL — `PluginAPI` has no `overlay`/`_overlays`; `StartupContext` not importable.

- [ ] **Step 3: Add imports, type aliases, and `StartupContext`**

In `src/led_ticker/plugin.py`, add `from dataclasses import dataclass` to the imports (place it with the stdlib imports, before the `from led_ticker...` block):

```python
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar
```

Immediately after the `API_VERSION` line (`API_VERSION: tuple[int, int] = (1, 0)`) and before `_T = TypeVar(...)`, add:

```python
# Lifecycle-hook callable shapes (collected by the loader, run by app/run.py).
# A startup hook may be sync or async; a shutdown hook takes no args.
StartupHook = Callable[["StartupContext"], Any]
ShutdownHook = Callable[[], Any]


@dataclass(frozen=True)
class StartupContext:
    """Passed to a plugin's ``on_startup`` hook.

    Fields are typed ``Any`` to keep the public ``plugin`` module free of heavy
    internal imports (matching ``Canvas``/``Color``). Real types:
    ``frame`` is the ``LedFrame`` (has ``overlay_hooks``, ``matrix``,
    ``get_clean_canvas()``, ``swap()``); ``session`` is the shared
    ``aiohttp.ClientSession``; ``config`` is the parsed app config.
    """

    frame: Any
    session: Any
    config: Any
```

- [ ] **Step 4: Extend `__all__`**

In `src/led_ticker/plugin.py`, add `"StartupContext"` to `__all__` (alphabetical among the type names — e.g. after `"PixelData"`), and delete the now-satisfied comment `# Phase D will add: StartupContext.` (replace it with `# (registry surfaces + lifecycle hooks complete; Phase E adds config/CLI/docs.)`).

- [ ] **Step 5: Add the hook lists to `__init__`**

In `PluginAPI.__init__`, after the `self._buffers = { ... }` dict literal closes, add:

```python
        # Lifecycle hooks are ordered lists of callables (no name key), so they
        # live outside _buffers and are NOT committed to a registry — the loader
        # collects them per-load into LoadedPlugins. See plan "pillar 2".
        self._overlays: list[Callable[[Any], None]] = []
        self._startup_hooks: list[StartupHook] = []
        self._shutdown_hooks: list[ShutdownHook] = []
```

- [ ] **Step 6: Add the three hook methods**

In `src/led_ticker/plugin.py`, immediately after the `font` method (it ends with the `self._buffers["fonts"][...] = (self.root / path).resolve()` line) and before the module-level `def make_color`, add:

```python
    def overlay(self, paint: Callable[[Any], None]) -> None:
        """Register an overlay painter run on every frame before the hardware
        swap. ``paint(canvas)`` draws directly on the real canvas (physical
        pixels), like the built-in busy-light. Direct call.

        Unlike core overlays, a plugin overlay that raises is disabled (and
        logged once) rather than freezing the panel — the loader wraps it.
        """
        self._overlays.append(paint)

    def on_startup(self, fn: StartupHook) -> None:
        """Register a hook run once, after the frame + session exist and before
        the main loop. Receives a :class:`StartupContext`; may be sync or async
        (awaited if it returns a coroutine). Spin up long-lived work via the
        public ``spawn_tracked``. Direct call.
        """
        self._startup_hooks.append(fn)

    def on_shutdown(self, fn: ShutdownHook) -> None:
        """Register a hook run best-effort when the run loop exits (in its
        ``finally``). Takes no arguments; may be sync or async. Direct call.
        """
        self._shutdown_hooks.append(fn)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_plugins/test_plugin_api.py -q`  → all PASS.
Then: `uv run python -c "import led_ticker.plugin"` → clean; `uv run ruff check src/led_ticker/plugin.py` → clean.

- [ ] **Step 8: Commit**

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d add src/led_ticker/plugin.py tests/test_plugins/test_plugin_api.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d -c core.hooksPath=/dev/null commit -m "feat(plugins): add overlay/on_startup/on_shutdown API + StartupContext"
```

---

## Task D2: Loader collects hooks; overlay guard; hook runners

**Files:**
- Modify: `src/led_ticker/_plugin_loader.py`
- Test: create `tests/test_plugins/test_hook_plugins.py`

**Context:** `_load_one` (loader) runs a plugin's `register(api)` then `_commit(api, info)` for registry surfaces. Hooks aren't committed — after a *successful* load, the loader reads `api._overlays`/`_startup_hooks`/`_shutdown_hooks` and appends them (tagged with namespace) to the returned `LoadedPlugins`. A failed plugin (raises in register, or commit collision) returns early and contributes no hooks. The loader also gains three helpers used by `app/run.py`: a guard wrapper for overlays (disable + log-once on raise) and async runners for startup/shutdown hooks that isolate failures. `import inspect` and `logger = logging.getLogger(__name__)` already exist in this file (from Phase C).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins/test_hook_plugins.py`:

```python
import asyncio
import logging
import textwrap

from led_ticker import _plugin_loader as L


def _write_plugin(plugin_dir, name, body):
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / f"{name}.py").write_text(textwrap.dedent(body))


def test_loader_collects_hooks_tagged_with_namespace(tmp_path):
    L.reset_plugins()
    _write_plugin(
        tmp_path / "plugins",
        "acme",
        """
        def register(api):
            api.overlay(lambda canvas: None)
            api.on_startup(lambda ctx: None)
            api.on_shutdown(lambda: None)
        """,
    )
    try:
        result = L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        assert not result.failed, result.failed
        assert [ns for ns, _ in result.overlays] == ["acme"]
        assert [ns for ns, _ in result.startup_hooks] == ["acme"]
        assert [ns for ns, _ in result.shutdown_hooks] == ["acme"]
    finally:
        L.reset_plugins()


def test_failed_plugin_contributes_no_hooks(tmp_path):
    L.reset_plugins()
    _write_plugin(
        tmp_path / "plugins",
        "bad",
        """
        def register(api):
            api.overlay(lambda canvas: None)
            raise RuntimeError("boom")
        """,
    )
    try:
        result = L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        assert any(ns == "bad" for ns, _ in result.failed)
        assert result.overlays == []
    finally:
        L.reset_plugins()


def test_guarded_overlay_disables_and_logs_once_on_raise(caplog):
    calls = {"n": 0}

    def boom(canvas):
        calls["n"] += 1
        raise ValueError("nope")

    guarded = L._guarded_overlay("acme", boom)
    with caplog.at_level(logging.ERROR):
        guarded("canvas-1")  # raises internally -> caught, disabled, logged
        guarded("canvas-2")  # already disabled -> no-op, no call
    assert calls["n"] == 1  # the painter ran once, then was disabled
    msgs = [r.getMessage() for r in caplog.records]
    assert sum("overlay" in m and "acme" in m for m in msgs) == 1  # logged once


def test_guarded_overlay_passes_through_when_ok():
    seen = []
    guarded = L._guarded_overlay("acme", lambda canvas: seen.append(canvas))
    guarded("c1")
    guarded("c2")
    assert seen == ["c1", "c2"]


def test_run_startup_hooks_sync_and_async_and_isolated(caplog):
    order = []

    def sync_hook(ctx):
        order.append(("sync", ctx))

    async def async_hook(ctx):
        order.append(("async", ctx))

    def boom(ctx):
        raise RuntimeError("startup boom")

    hooks = [("a", sync_hook), ("b", async_hook), ("c", boom)]
    with caplog.at_level(logging.ERROR):
        asyncio.run(L._run_startup_hooks(hooks, "CTX"))
    assert order == [("sync", "CTX"), ("async", "CTX")]
    assert any("on_startup" in r.getMessage() and "c" in r.getMessage()
               for r in caplog.records)


def test_run_shutdown_hooks_sync_and_async_and_isolated(caplog):
    order = []

    def sync_hook():
        order.append("sync")

    async def async_hook():
        order.append("async")

    def boom():
        raise RuntimeError("shutdown boom")

    hooks = [("a", sync_hook), ("b", async_hook), ("c", boom)]
    with caplog.at_level(logging.ERROR):
        asyncio.run(L._run_shutdown_hooks(hooks))
    assert order == ["sync", "async"]
    assert any("on_shutdown" in r.getMessage() and "c" in r.getMessage()
               for r in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugins/test_hook_plugins.py -q`
Expected: FAIL — `LoadedPlugins` has no `overlays`; `_guarded_overlay`/`_run_startup_hooks`/`_run_shutdown_hooks` undefined.

- [ ] **Step 3: Extend `LoadedPlugins`**

In `src/led_ticker/_plugin_loader.py`, replace the `LoadedPlugins` dataclass:

```python
@dataclass
class LoadedPlugins:
    loaded: list[PluginInfo] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
```

with (the `Callable` import already exists in this file):

```python
@dataclass
class LoadedPlugins:
    loaded: list[PluginInfo] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    # Lifecycle hooks, each tagged with the contributing namespace (for logging
    # and the overlay guard). Collected only from successfully-loaded plugins.
    overlays: list[tuple[str, Callable[[Any], None]]] = field(default_factory=list)
    startup_hooks: list[tuple[str, Callable[..., Any]]] = field(default_factory=list)
    shutdown_hooks: list[tuple[str, Callable[..., Any]]] = field(
        default_factory=list
    )
```

- [ ] **Step 4: Collect hooks on the `_load_one` success path**

In `_load_one`, find the success tail (after `_commit(api, info)` succeeds), currently:

```python
    loaded_namespaces.add(namespace)
    result.loaded.append(info)
    _warn_unpaired_hires(namespace, api)
    logger.info("plugin %r loaded from %s (%s)", namespace, source, info.counts)
```

Insert hook collection immediately before the `logger.info(...)` line:

```python
    loaded_namespaces.add(namespace)
    result.loaded.append(info)
    _warn_unpaired_hires(namespace, api)
    for paint in api._overlays:
        result.overlays.append((namespace, paint))
    for fn in api._startup_hooks:
        result.startup_hooks.append((namespace, fn))
    for fn in api._shutdown_hooks:
        result.shutdown_hooks.append((namespace, fn))
    logger.info("plugin %r loaded from %s (%s)", namespace, source, info.counts)
```

- [ ] **Step 5: Add the guard + runner helpers**

In `src/led_ticker/_plugin_loader.py`, add near the other module-level helpers (e.g. after `_warn_unpaired_hires`):

```python
def _guarded_overlay(
    namespace: str, paint: Callable[[Any], None]
) -> Callable[[Any], None]:
    """Wrap a plugin overlay so a raise disables it (and logs once) instead of
    propagating out of ``LedFrame.swap()``.

    Core overlays intentionally have no per-hook try/except (a raising core hook
    freezes the panel — the documented invariant). Plugin code is less trusted,
    so its overlays must never be able to freeze the panel.
    """
    state = {"disabled": False}

    def wrapped(canvas: Any) -> None:
        if state["disabled"]:
            return
        try:
            paint(canvas)
        except Exception:
            state["disabled"] = True
            logger.exception(
                "plugin %r overlay raised; disabling it for this run", namespace
            )

    return wrapped


async def _run_startup_hooks(
    hooks: list[tuple[str, Callable[..., Any]]], ctx: Any
) -> None:
    """Run each on_startup hook once, isolating failures. Awaits a hook that
    returns a coroutine."""
    for namespace, fn in hooks:
        try:
            result = fn(ctx)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("plugin %r on_startup hook failed", namespace)


async def _run_shutdown_hooks(
    hooks: list[tuple[str, Callable[..., Any]]],
) -> None:
    """Run each on_shutdown hook best-effort, isolating failures. Awaits a hook
    that returns a coroutine."""
    for namespace, fn in hooks:
        try:
            result = fn()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("plugin %r on_shutdown hook failed", namespace)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_plugins/test_hook_plugins.py -q` → all PASS.
Then: `uv run pytest tests/test_plugins/ -q` → all PASS; `uv run ruff check src/led_ticker/_plugin_loader.py` → clean.

- [ ] **Step 7: Commit**

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d add src/led_ticker/_plugin_loader.py tests/test_plugins/test_hook_plugins.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d -c core.hooksPath=/dev/null commit -m "feat(plugins): collect lifecycle hooks; overlay guard + hook runners"
```

---

## Task D3: `validate_config` per-type convention

**Files:**
- Modify: `src/led_ticker/app/factories.py`
- Test: create `tests/test_plugins/test_validate_config.py`

**Context:** `validate_widget_cfg` (factories.py:~535) validates a widget's config dict without constructing it; `_build_widget` calls it before instantiation, and the static validator's `_run_build_checks` (validate.py) calls it per widget. It raises `ValueError` on invalid config. Phase D adds a by-convention hook: if the resolved widget class defines `validate_config(cls, cfg) -> list[str]`, call it and raise `ValueError` with the joined messages when non-empty. The call goes right after `cls = get_widget_class(widget_type)` (factories.py:697) and before `_coerce_widget_cfg` (so it sees the user's config as written). Built-in widgets don't define `validate_config` (none today), so they're unaffected.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins/test_validate_config.py`:

```python
import pytest

from led_ticker.app.factories import _run_validate_config


def test_validate_config_messages_raise():
    class W:
        @classmethod
        def validate_config(cls, cfg):
            return ["text is required"] if not cfg.get("text") else []

    with pytest.raises(ValueError, match="text is required"):
        _run_validate_config(W, {}, "acme.thing")


def test_validate_config_empty_list_is_ok():
    class W:
        @classmethod
        def validate_config(cls, cfg):
            return []

    _run_validate_config(W, {"text": "hi"}, "acme.thing")  # no raise


def test_validate_config_absent_is_ok():
    class W:  # no validate_config defined
        pass

    _run_validate_config(W, {"anything": 1}, "acme.thing")  # no raise


def test_validate_config_receives_a_copy_not_the_live_cfg():
    seen = {}

    class W:
        @classmethod
        def validate_config(cls, cfg):
            cfg["injected"] = True  # must not leak back to caller's dict
            seen.update(cfg)
            return []

    live = {"text": "hi"}
    _run_validate_config(W, live, "acme.thing")
    assert "injected" not in live  # caller's dict untouched
    assert seen.get("injected") is True


def test_validate_config_raising_is_wrapped(caplog):
    class W:
        @classmethod
        def validate_config(cls, cfg):
            raise RuntimeError("kaboom")

    with pytest.raises(ValueError, match="validate_config raised"):
        _run_validate_config(W, {}, "acme.thing")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugins/test_validate_config.py -q`
Expected: FAIL — `cannot import name '_run_validate_config'`.

- [ ] **Step 3: Implement `_run_validate_config` and call it**

In `src/led_ticker/app/factories.py`, add this module-level helper (place it just above `validate_widget_cfg`):

```python
def _run_validate_config(cls: type, cfg: dict[str, Any], widget_type: str) -> None:
    """Run a widget class's optional ``validate_config(cls, cfg) -> list[str]``.

    A by-convention cross-field check that travels with the type (no API
    registration needed). Messages become a pre-flight ``ValueError``. The
    validator gets a COPY of the config so it can't mutate the real one. A
    validator that itself raises is wrapped so the error names the type.
    """
    validator = getattr(cls, "validate_config", None)
    if validator is None:
        return
    try:
        messages = validator(dict(cfg))
    except Exception as e:
        raise ValueError(f"{widget_type}: validate_config raised: {e}") from e
    if messages:
        raise ValueError(f"{widget_type}: {'; '.join(messages)}")
```

Then in `validate_widget_cfg`, right after these two existing lines (factories.py:696-697):

```python
    widget_type = widget_cfg.pop("type")
    cls = get_widget_class(widget_type)
```

insert:

```python
    _run_validate_config(cls, widget_cfg, widget_type)
```

(Before the existing `_coerce_widget_cfg(widget_cfg, coercion_collector)` line.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_plugins/test_validate_config.py -q` → all PASS.

- [ ] **Step 5: Regression — confirm no built-in widget regressed**

Run: `uv run pytest tests/ -q -k "validate or factories or build_widget"` → all PASS (built-ins define no `validate_config`, so `getattr` returns `None` and the path is a no-op for them).

- [ ] **Step 6: Lint + commit**

Run: `uv run ruff check src/led_ticker/app/factories.py` → clean.

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d add src/led_ticker/app/factories.py tests/test_plugins/test_validate_config.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d -c core.hooksPath=/dev/null commit -m "feat(plugins): per-type validate_config convention in validate_widget_cfg"
```

---

## Task D4: Wire overlays + startup/shutdown into the run loop

**Files:**
- Modify: `src/led_ticker/app/run.py`
- Test: `tests/test_plugins/test_run_integration.py` (extend) — light wiring assertions; the heavy hook logic is already tested in D2.

**Context:** `run()` (run.py:101) loads plugins (line 105), loads config (109), builds the frame (118), starts the busy-light overlay (120-121), then enters `async with aiohttp.ClientSession() as session:` (135) and an unbounded `while True:` loop (145-368). There is **no** `try/finally` around the loop today — shutdown happens by task cancellation. Phase D: (a) append guarded plugin overlays right after the busy-light block; (b) inside the session, before the loop, build a `StartupContext` and run startup hooks; (c) wrap the loop body in `try/finally` and run shutdown hooks in the `finally`. The hook-running logic lives in `_plugin_loader` (tested in D2); run.py only calls it.

- [ ] **Step 1: Add imports**

In `src/led_ticker/app/run.py`, add `StartupContext` to the `led_ticker.plugin` import surface and the three runner/guard helpers from `_plugin_loader`. Find the existing import of `load_plugins` (used by `_load_plugins_for_config`) — it imports from `led_ticker._plugin_loader`. Extend that import to also bring in the helpers:

```python
from led_ticker._plugin_loader import (
    _guarded_overlay,
    _run_shutdown_hooks,
    _run_startup_hooks,
    load_plugins,
)
```

(If `load_plugins` is currently imported on its own line, replace that line with the grouped import above. Keep any other existing imports from that module.)

And add, with the other `led_ticker` imports:

```python
from led_ticker.plugin import StartupContext
```

- [ ] **Step 2: Append guarded plugin overlays after the busy-light block**

In `run()`, find (run.py:120-121):

```python
    if config.busy_light.enabled:
        await _start_busy_light(config.busy_light, led_frame)
```

Immediately after it, add:

```python
    # Plugin overlays composite over every render path via LedFrame.swap(),
    # same as the busy-light. Each is exception-wrapped so a raising plugin
    # overlay disables itself (logged once) rather than freezing the panel.
    for ns, paint in plugins.overlays:
        led_frame.overlay_hooks.append(_guarded_overlay(ns, paint))
```

- [ ] **Step 3: Run startup hooks inside the session, before the loop; wrap the loop in try/finally for shutdown**

In `run()`, find the start of the session block and the loop (run.py:135-145):

```python
    async with aiohttp.ClientSession() as session:
        last_widget: Any = None  # track for section-to-section transitions
        last_scroll_pos: int = 0  # track scroll pos for between-section transitions
        last_scale: int = config.display.default_scale  # outgoing section's scale
        last_content_height: int = 16  # outgoing section's content_height
        last_bg_color: tuple[int, int, int] | None = (
            None  # outgoing section's bg_color (for run_transition's t<0.5 reset)
        )
        widget_cache: dict[str, Any] = {}

        while True:
            for section in config.sections:
```

Change it so the startup hooks run after the tracking vars are set up and the `while True:` loop is wrapped in `try`/`finally`:

```python
    async with aiohttp.ClientSession() as session:
        last_widget: Any = None  # track for section-to-section transitions
        last_scroll_pos: int = 0  # track scroll pos for between-section transitions
        last_scale: int = config.display.default_scale  # outgoing section's scale
        last_content_height: int = 16  # outgoing section's content_height
        last_bg_color: tuple[int, int, int] | None = (
            None  # outgoing section's bg_color (for run_transition's t<0.5 reset)
        )
        widget_cache: dict[str, Any] = {}

        # Plugin startup hooks run once now that the frame + session exist.
        await _run_startup_hooks(
            plugins.startup_hooks,
            StartupContext(frame=led_frame, session=session, config=config),
        )

        try:
            while True:
                for section in config.sections:
                    ...  # EXISTING LOOP BODY UNCHANGED — re-indented one level
        finally:
            # Best-effort: run plugin shutdown hooks when the loop exits
            # (normally via cancellation on Ctrl-C / SIGTERM).
            await _run_shutdown_hooks(plugins.shutdown_hooks)
```

**IMPORTANT — this is the one delicate edit.** The entire existing `while True:` body (from `for section in config.sections:` at line 146 through the end of the loop at ~line 368) must be indented by exactly one more level (4 spaces) so it sits inside the new `try:`. Do NOT change any logic inside the loop — only its indentation. After editing, verify structure with:
- `uv run python -c "import ast,sys; ast.parse(open('src/led_ticker/app/run.py').read()); print('parse-ok')"` → `parse-ok`
- `uv run ruff check src/led_ticker/app/run.py` → clean (ruff will catch a mis-indented block)
- `uv run pyright src/led_ticker/app/run.py` → no new errors

If re-indenting a ~220-line block in place is error-prone with your editor, an equivalent acceptable refactor is to extract the loop body into a local `async def _loop():` defined just above the `try`, then `try: await _loop() finally: await _run_shutdown_hooks(...)`. Either is fine as long as behavior is identical and the suite stays green. Prefer the minimal try/finally wrap if you can do it cleanly.

- [ ] **Step 4: Extend the run-integration test**

Read `tests/test_plugins/test_run_integration.py` to learn how it exercises `run()` / the loader against the rgbmatrix stub. Add a test that a plugin contributing an overlay + startup + shutdown is wired through. If the existing harness does NOT actually spin `run()` (because it needs a long-running loop), instead assert the wiring contract that run.py relies on, end-to-end through the loader:

```python
def test_loaded_plugin_hooks_are_consumable_by_run(tmp_path):
    import textwrap

    from led_ticker import _plugin_loader as L

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "svc.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import StartupContext  # importable by a plugin

            STATE = {"started": False, "stopped": False}

            def register(api):
                api.overlay(lambda canvas: None)
                api.on_startup(lambda ctx: STATE.__setitem__("started", True))
                api.on_shutdown(lambda: STATE.__setitem__("stopped", True))
            """
        )
    )
    try:
        plugins = L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        # run.py wraps each overlay and runs the hook lists:
        wrapped = [L._guarded_overlay(ns, p) for ns, p in plugins.overlays]
        assert len(wrapped) == 1
        import asyncio

        asyncio.run(L._run_startup_hooks(plugins.startup_hooks, object()))
        asyncio.run(L._run_shutdown_hooks(plugins.shutdown_hooks))
        # The plugin module's STATE proves both hooks fired.
        import sys

        mod = sys.modules["led_ticker_plugin_svc"]
        assert mod.STATE == {"started": True, "stopped": True}
    finally:
        L.reset_plugins()
```

> If the synthetic module name differs from `led_ticker_plugin_svc`, discover it: the loader imports local plugins under `f"led_ticker_plugin_{namespace}"` (confirm in `_plugin_loader._discover_local`). Adjust the `sys.modules[...]` key to match.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_plugins/ -q` → all PASS.
Run: `uv run pytest tests/ -q -k "run or integration"` → all PASS (the run() structural change didn't break the existing loop).

- [ ] **Step 6: Commit**

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d add src/led_ticker/app/run.py tests/test_plugins/test_run_integration.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-d -c core.hooksPath=/dev/null commit -m "feat(plugins): wire plugin overlays + startup/shutdown hooks into run loop"
```

---

## Task D5: Final verification + whole-phase review

**Files:** none (verification only)

- [ ] **Step 1: Lint** — `make lint` → `All checks passed!`
- [ ] **Step 2: Typecheck** — `make typecheck` → `0 errors, 0 warnings, 0 informations`
- [ ] **Step 3: Full suite + coverage** — `make test` → all green (baseline + Phase D additions), coverage ≥ project floor (≈95%).
- [ ] **Step 4: Confirm the public surface** — `uv run pytest tests/test_plugins/test_plugin_api.py -q -k "export or startup or overlay or shutdown"` → PASS; `uv run python -c "from led_ticker.plugin import StartupContext, PluginAPI; a=PluginAPI('x'); a.overlay(lambda c: None); a.on_startup(lambda ctx: None); a.on_shutdown(lambda: None); print('ok')"` → `ok`.
- [ ] **Step 5: Report** — summarize hooks added (overlay/startup/shutdown + `validate_config` convention + `StartupContext`), the overlay-guard divergence, the run-loop try/finally, and the green suite. Hand back to the controller for the whole-phase review + `finishing-a-development-branch`.

---

## Self-Review (against the spec — `docs/superpowers/specs/2026-05-31-plugin-system-design.md`, "Lifecycle hooks")

**1. Spec coverage:**
- "Per-type config validation by convention — `validate_config(cls, cfg) -> list[str]`, called by `validate_widget_cfg`, surfaced as pre-flight errors" → Task D3.
- "`api.overlay(paint)` collects `Callable[[Canvas], None]`; loader appends to `LedFrame.overlay_hooks`; plugin overlays exception-wrapped (disable + log once), unlike core" → D1 (API) + D2 (`_guarded_overlay`) + D4 (append). Core `swap()` is left unchanged (the divergence is the wrapper, applied only to plugin overlays).
- "`api.on_startup(fn)`/`api.on_shutdown(fn)`; `on_startup(ctx)` gets `StartupContext(frame, session, config)`, sync-or-async; `on_shutdown()` best-effort in the run-loop `finally`; spin work via `spawn_tracked`" → D1 (API + StartupContext) + D2 (runners) + D4 (wiring; startup before loop, shutdown in finally).
- Run order "build frame → append plugin overlays → enter session → run on_startup → main loop → (finally) on_shutdown" → D4 matches exactly.
- Re-export `StartupContext` → D1.
- Loader returns collected `overlay_hooks`/`startup_hooks`/`shutdown_hooks` in `LoadedPlugins` → D2.

**2. Placeholder scan:** No TBD/"handle errors"/"similar to". Every code step shows complete code. The one delicate step (D4 loop re-indent) gives explicit verification commands and an equivalent extract-to-`_loop()` fallback — not a placeholder.

**3. Type/name consistency:** `StartupContext(frame, session, config)` is defined in D1 and constructed identically in D4 and the D1 test. `_guarded_overlay(namespace, paint)`, `_run_startup_hooks(hooks, ctx)`, `_run_shutdown_hooks(hooks)` signatures match across D2 (definition + tests) and D4 (call sites). `LoadedPlugins.overlays/startup_hooks/shutdown_hooks` are `list[tuple[str, Callable]]` in D2 and consumed as `(ns, fn)` tuples in D4. `validate_config(cls, cfg) -> list[str]` matches the spec and D3's `_run_validate_config`.

**Deliberate scope calls (documented, not gaps):** `validate_config` is wired for widgets only (the spec's primary case; provider/transition validate_config is an additive follow-up). `[plugins]` config, the `plugins` CLI, and making `led-ticker validate` load plugins are Phase E. The hook lists intentionally sit outside `_buffers`/`_REGISTRY_MAP` (hooks aren't named registry entries) — the A–C surface-parity invariant is unchanged.

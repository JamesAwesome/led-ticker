"""Plugin discovery and loading (internal). Plugins never import this."""

import importlib.metadata
import importlib.util
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from led_ticker.color_providers import _PROVIDER_REGISTRY
from led_ticker.plugin import API_VERSION, PluginAPI
from led_ticker.transitions import _TRANSITION_REGISTRY
from led_ticker.widgets import _WIDGET_REGISTRY

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "led_ticker.plugins"

# surface name (matches PluginAPI._buffers keys) -> the registry it commits into.
# Later phases extend this map; the commit loop never changes.
_REGISTRY_MAP: dict[str, dict[str, Any]] = {
    "widgets": _WIDGET_REGISTRY,
    "transitions": _TRANSITION_REGISTRY,
    "color_providers": _PROVIDER_REGISTRY,
}


@dataclass
class PluginInfo:
    namespace: str
    source: str
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class LoadedPlugins:
    loaded: list[PluginInfo] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


# Load-once guard; assigned by load_plugins() (added in Task A3).
_LOADED: LoadedPlugins | None = None


def reset_plugins() -> None:
    """Test helper: drop all namespaced (dotted) registry entries + load guard."""
    global _LOADED  # noqa: PLW0603
    for registry in _REGISTRY_MAP.values():
        for key in [k for k in registry if "." in k]:
            del registry[key]
    _LOADED = None


def _commit(api: PluginAPI, info: PluginInfo) -> None:
    """Write a cleanly-registered plugin's buffers into the registries.

    Two-pass (validate all, then write all) so a mid-commit collision can't
    leave a partial registration. Only buffers that map to a registry are
    committed here (hook surfaces are collected separately in later phases).
    """
    for surface, buf in api._buffers.items():
        registry = _REGISTRY_MAP.get(surface)
        if registry is None:
            logger.debug(
                "surface %r not in _REGISTRY_MAP; skipping (hook surface?)", surface
            )
            continue
        for name in buf:
            if name in registry:
                raise ValueError(f"{surface} entry {name!r} already registered")
    for surface, buf in api._buffers.items():
        registry = _REGISTRY_MAP.get(surface)
        if registry is None:
            continue
        for name, obj in buf.items():
            registry[name] = obj
        if buf:
            info.counts[surface] = len(buf)


def _load_one(
    namespace: str,
    source: str,
    register: Callable[[PluginAPI], None] | None,
    requires_api: int | None,
    loaded_namespaces: set[str],
    result: LoadedPlugins,
) -> None:
    """Run + commit one plugin's register(), isolating all failures."""
    if namespace in loaded_namespaces:
        result.failed.append(
            (namespace, "namespace already claimed by another plugin")
        )
        logger.error(
            "plugin namespace %r already claimed; skipping %s", namespace, source
        )
        return
    if requires_api is not None and requires_api != API_VERSION[0]:
        msg = f"requires API v{requires_api}, core is v{API_VERSION[0]}"
        result.failed.append((namespace, msg))
        logger.error("plugin %r %s; skipping", namespace, msg)
        return
    if register is None or not callable(register):
        result.failed.append((namespace, "no callable register(api) found"))
        logger.error(
            "plugin %r has no register(api); skipping %s", namespace, source
        )
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
    logger.info("plugin %r loaded from %s (%s)", namespace, source, info.counts)


def _import_from_path(mod_name: str, init: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, init)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin module from {init}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _discover_local(plugin_dir: Path):
    """Yield (namespace, source, thunk) for each local plugin. The thunk imports
    the module lazily and returns (register, requires_api)."""
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


def _discover_entry_points():
    """Yield (namespace, source, thunk) for installed entry-point plugins.
    Namespace = the entry-point name; the thunk loads the entry point and
    resolves its register callable."""
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


def load_plugins(
    plugin_dir: Path | None, *, entry_points_enabled: bool = True
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
    if entry_points_enabled:
        sources.extend(_discover_entry_points())
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

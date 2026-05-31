"""Plugin discovery and loading (internal). Plugins never import this."""

import logging
from dataclasses import dataclass, field
from typing import Any

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
            info.counts[surface] = info.counts.get(surface, 0) + len(buf)


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

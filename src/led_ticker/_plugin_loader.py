"""Plugin discovery and loading (internal). Plugins never import this."""

import contextlib
import importlib.metadata
import importlib.util
import inspect
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from led_ticker.animations import _ANIMATION_REGISTRY
from led_ticker.backends import _REGISTRY as _BACKEND_REGISTRY
from led_ticker.borders import _BORDER_REGISTRY
from led_ticker.color_providers import _PROVIDER_REGISTRY
from led_ticker.config import PluginsConfig, _parse_plugins_block
from led_ticker.fonts.hires_loader import _PLUGIN_FONTS
from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY
from led_ticker.plugin import API_VERSION, PluginAPI
from led_ticker.sources import _PLUGIN_SOURCE_TYPES
from led_ticker.transitions import _TRANSITION_REGISTRY, EASING
from led_ticker.widgets import _WIDGET_REGISTRY

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "led_ticker.plugins"

# surface name (matches PluginAPI._buffers keys) -> the registry it commits into.
# Later phases extend this map; the commit loop never changes.
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
    "backends": _BACKEND_REGISTRY,
    "sources": _PLUGIN_SOURCE_TYPES,
}


@dataclass
class PluginInfo:
    namespace: str
    source: str
    counts: dict[str, int] = field(default_factory=dict)
    # Per-surface qualified contribution names (e.g. {"widgets": ["acme.clock"]})
    # — what an operator references in TOML.
    names: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class LoadedPlugins:
    loaded: list[PluginInfo] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    # Lifecycle hooks, each tagged with the contributing namespace (for logging
    # and the overlay guard). Collected only from successfully-loaded plugins.
    overlays: list[tuple[str, Callable[[Any], None]]] = field(default_factory=list)
    startup_hooks: list[tuple[str, Callable[..., Any]]] = field(default_factory=list)
    shutdown_hooks: list[tuple[str, Callable[..., Any]]] = field(default_factory=list)


# Load-once guard; assigned by load_plugins() (added in Task A3).
_LOADED: LoadedPlugins | None = None

# Serializes the FIRST load's discover+register+commit sequence. The
# lock-free `if _LOADED is not None: return _LOADED` guard below only
# serializes the *already-loaded* fast path (racing readers of a settled
# value) — it is check-then-act and does nothing to stop two near-
# simultaneous first callers (e.g. two webui to_thread validates) from both
# passing the check and racing the full discover+register+commit body,
# which produced a partially-committed registry, "already registered"
# errors, double-exec'd local plugins, and a last-writer-wins _LOADED that
# could permanently record every plugin as failed. Double-checked locking:
# the fast path stays lock-free; only the slow (first-load) path pays for
# the lock, and a second thread that loses the race re-checks _LOADED
# inside the lock and returns the winner's result instead of loading again.
_LOAD_LOCK = threading.Lock()


def reset_plugins() -> None:
    """Test helper: drop all namespaced (dotted) registry entries + load guard.

    Note: ``pixel_emoji._EMOJI_BUILTINS_LOADED`` is intentionally NOT reset
    here. Built-in emoji entries are bare slugs (no dot), so they survive the
    dotted-key deletion and the sentinel stays True — ``_get_registry()`` keeps
    returning them. A test that needs a pristine un-built emoji registry must
    also set ``pe._EMOJI_BUILTINS_LOADED = False`` and clear ``pe.EMOJI_REGISTRY``
    itself.
    """
    global _LOADED  # noqa: PLW0603
    for registry in _REGISTRY_MAP.values():
        for key in [k for k in registry if "." in k]:
            del registry[key]
    _LOADED = None
    # A plugin font name may have been looked up (and cached as a miss) before
    # its plugin registered. Drop the hi-res font cache so the next resolve
    # re-reads _PLUGIN_FONTS instead of returning a stale None.
    from led_ticker.fonts import hires_loader

    hires_loader.load_hires_font.cache_clear()


def _commit(api: PluginAPI, info: PluginInfo) -> None:
    """Write a cleanly-registered plugin's buffers into the registries.

    Two-pass (validate all, then write all) so a mid-commit collision can't
    leave a partial registration. Only buffers that map to a registry are
    committed here (hook surfaces are collected separately — see _load_one).
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
            info.names[surface] = sorted(buf)


def _resolve_root(source: str, register: Callable[[PluginAPI], None]) -> Path | None:
    """Best-effort plugin root for resolving ``api.font()`` relative paths.

    Local plugins: the dir containing the plugin file — a single-file plugin's
    parent (the plugins dir), or the package dir itself. Entry-point plugins:
    the dir of the register callable's module. Returns ``None`` when it cannot
    be determined (e.g. a zip-imported package); ``api.font`` then raises a
    clear error rather than guessing.

    Uses ``.py`` suffix rather than ``path.is_file()`` to discriminate between
    a single-file plugin and a package dir, so the check is existence-independent
    (works even when the source path is hypothetical or in a tmp dir in tests).

    For entry-point plugins, ``inspect.getmodule`` is tried first; if it
    returns ``None`` (e.g. the module was loaded via ``spec_from_file_location``
    without being registered in ``sys.modules``), we fall back to
    ``register.__globals__.get('__file__')`` which Py guarantees is set for
    any function defined in a source file.
    """
    if source.startswith("entry-point:"):
        module = inspect.getmodule(register)
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            # Fallback: function's own globals dict always has __file__ for
            # source-file functions, even when the module isn't in sys.modules.
            module_file = getattr(register, "__globals__", {}).get("__file__")
        return Path(module_file).parent if module_file else None
    path = Path(source)
    return path.parent if path.suffix == ".py" else path


def _warn_unpaired_hires(namespace: str, api: PluginAPI) -> None:
    """Warn when a plugin registers a hi-res emoji with no low-res counterpart.

    Inline ``:ns.slug:`` parsing and unscaled canvases resolve only through the
    low-res emoji registry, so a hi-res-only slug silently won't render there.
    Built-in emojis always pair the two; plugins must too for inline use.
    """
    lowres = set(api._buffers["emojis"])
    for slug in api._buffers["hires_emojis"]:
        if slug not in lowres:
            bare = slug.split(".", 1)[-1]
            logger.warning(
                "plugin %r: hi-res emoji %r has no low-res counterpart; it will "
                "not render inline (:%s:) or on unscaled canvases. Also register "
                "api.emoji(%r, ...).",
                namespace,
                slug,
                slug,
                bare,
            )


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
            # Never let a logging failure propagate into swap() and freeze
            # the panel — disabling the overlay is what matters.
            with contextlib.suppress(Exception):
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
    that returns a coroutine.

    Failure isolation covers ``Exception`` only. A hook that raises or
    propagates ``CancelledError``/``KeyboardInterrupt`` (both ``BaseException``)
    interrupts the remaining shutdown sequence — intentional: plugin code must
    not be able to suppress external cancellation, and this runner is invoked
    from the run-loop ``finally`` which is itself reached via cancellation.
    """
    for namespace, fn in hooks:
        try:
            result = fn()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("plugin %r on_shutdown hook failed", namespace)


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
        result.failed.append((namespace, "namespace already claimed by another plugin"))
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
        logger.error("plugin %r has no register(api); skipping %s", namespace, source)
        return
    root = _resolve_root(source, register)
    api = PluginAPI(namespace, root=root)
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
    _warn_unpaired_hires(namespace, api)
    for paint in api._overlays:
        result.overlays.append((namespace, paint))
    for fn in api._startup_hooks:
        result.startup_hooks.append((namespace, fn))
    for fn in api._shutdown_hooks:
        result.shutdown_hooks.append((namespace, fn))
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
    plugin_dir: Path | None,
    *,
    entry_points_enabled: bool = True,
    disable: set[str] | None = None,
) -> LoadedPlugins:
    """Discover + load all plugins once. Idempotent (call reset_plugins() in
    tests to reload). ``disable`` is a set of namespaces to skip + log."""
    global _LOADED  # noqa: PLW0603
    if _LOADED is not None:
        return _LOADED
    with _LOAD_LOCK:
        # Double-checked: another thread may have finished the first load
        # while we were waiting on the lock. Re-read under the lock rather
        # than trusting the lock-free peek above.
        if _LOADED is not None:
            return _LOADED
        disabled = disable or set()
        result = LoadedPlugins()
        loaded_ns: set[str] = set()
        sources = []
        if plugin_dir is not None:
            sources.extend(_discover_local(plugin_dir))
        if entry_points_enabled:
            sources.extend(_discover_entry_points())
        for ns, source, thunk in sources:
            if ns in disabled:
                logger.info("plugin %r disabled via [plugins].disable; skipping", ns)
                continue
            try:
                register, requires = thunk()
            except Exception as e:
                logger.exception("plugin %r (%s) failed to import", ns, source)
                result.failed.append((ns, str(e)))
                continue
            _load_one(ns, source, register, requires, loaded_ns, result)
        _LOADED = result
        return result


def read_plugins_config(config_path: Path) -> PluginsConfig:
    """Lightweight read of just the ``[plugins]`` block, so plugin discovery can
    run BEFORE full config validation (plugin-provided easings etc. must be
    registered before load_config validates them). Returns defaults only if the
    file is missing; a TOML syntax error or a structural ``[plugins]`` error
    propagates so the caller can report it.
    """
    import tomllib

    try:
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        return PluginsConfig()
    return _parse_plugins_block(raw)


def load_plugins_for_config(config_path: Path) -> LoadedPlugins:
    """Config-driven plugin load: read the ``[plugins]`` block, then load from
    ``<config dir>/<dir>`` honoring enable/disable. Used by the run loop, the
    ``validate`` path, and the ``plugins`` CLI command."""
    pc = read_plugins_config(config_path)
    if not pc.enabled:
        logger.info("plugins disabled via [plugins].enabled=false; skipping")
        return load_plugins(None, entry_points_enabled=False)
    plugin_dir = config_path.parent / pc.dir
    return load_plugins(plugin_dir, disable=set(pc.disable))

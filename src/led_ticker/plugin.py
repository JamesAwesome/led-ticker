"""Public plugin API for led-ticker.

Plugins import ONLY this module. Everything else under ``led_ticker`` is
internal and may change without notice. A plugin defines a top-level
``register(api)`` function; the loader passes a :class:`PluginAPI` bound to the
plugin's namespace. Every registered name is auto-prefixed with that namespace
(``"namespace.name"``) and buffered until the loader commits it atomically.
"""

from collections.abc import Callable
from typing import Any, TypeVar

# Re-exports: the stable surface plugin authors subclass / annotate against.
from led_ticker._types import Canvas, Color
from led_ticker.color_providers import ColorProvider, ColorProviderBase
from led_ticker.transitions import Transition
from led_ticker.widget import Widget, spawn_tracked

__all__ = [
    "API_VERSION",
    "PluginAPI",
    "Canvas",
    "Color",
    "ColorProvider",
    "ColorProviderBase",
    "Transition",
    "Widget",
    "spawn_tracked",
]
# Phase B will also re-export: Animation, BorderEffect, BorderEffectBase.
# Phase C: PixelData, HiResEmoji, and the drawing helpers. Phase D: StartupContext.

API_VERSION: tuple[int, int] = (1, 0)

_T = TypeVar("_T", bound=type)


class PluginAPI:
    """Namespace-bound registrar passed to a plugin's ``register(api)``.

    Calls buffer registrations keyed by the namespaced name; the loader commits
    the buffers into the real registries only if ``register`` returns cleanly.
    A plugin therefore cannot register a bare (un-namespaced) name and cannot
    half-register on error.
    """

    def __init__(self, namespace: str) -> None:
        # Phase C will add `root: Path | None = None` here (for api.font()).
        self.namespace = namespace
        # One buffer per surface, keyed by surface name, so the loader's commit
        # is a single generic loop as later phases add surfaces.
        self._buffers: dict[str, dict[str, Any]] = {
            "widgets": {},
            "transitions": {},
            "color_providers": {},
        }

    @property
    def _widgets(self) -> dict[str, Any]:
        return self._buffers["widgets"]

    @property
    def _transitions(self) -> dict[str, Any]:
        return self._buffers["transitions"]

    def _qualify(self, name: str) -> str:
        return f"{self.namespace}.{name}"

    def widget(self, name: str) -> Callable[[_T], _T]:
        """Register a widget class under ``namespace.name``."""

        def deco(cls: _T) -> _T:
            self._buffers["widgets"][self._qualify(name)] = cls
            return cls

        return deco

    def transition(self, name: str) -> Callable[[_T], _T]:
        """Register a transition class under ``namespace.name``."""

        def deco(cls: _T) -> _T:
            self._buffers["transitions"][self._qualify(name)] = cls
            return cls

        return deco

    def color_provider(self, style: str) -> Callable[[_T], _T]:
        """Register a ColorProvider class under ``namespace.style``."""

        def deco(cls: _T) -> _T:
            self._buffers["color_providers"][self._qualify(style)] = cls
            return cls

        return deco

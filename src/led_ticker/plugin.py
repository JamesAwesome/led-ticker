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

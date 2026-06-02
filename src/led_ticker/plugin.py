"""Public plugin API for led-ticker.

Plugins import ONLY this module. Everything else under ``led_ticker`` is
internal and may change without notice. A plugin defines a top-level
``register(api)`` function; the loader passes a :class:`PluginAPI` bound to the
plugin's namespace. Every registered name is auto-prefixed with that namespace
(``"namespace.name"``) and buffered until the loader commits it atomically.
"""

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

API_VERSION: tuple[int, int] = (1, 0)

_T = TypeVar("_T", bound=type)


class PluginAPI:
    """Namespace-bound registrar passed to a plugin's ``register(api)``.

    Calls buffer registrations keyed by the namespaced name; the loader commits
    the buffers into the real registries only if ``register`` returns cleanly.
    A plugin therefore cannot register a bare (un-namespaced) name and cannot
    half-register on error.
    """

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

    def animation(self, style: str) -> Callable[[_T], _T]:
        """Register an Animation class under ``namespace.style``."""

        def deco(cls: _T) -> _T:
            self._buffers["animations"][self._qualify(style)] = cls
            return cls

        return deco

    def border(self, name: str) -> Callable[[_T], _T]:
        """Register a BorderEffect class under ``namespace.name``."""

        def deco(cls: _T) -> _T:
            self._buffers["borders"][self._qualify(name)] = cls
            return cls

        return deco

    def easing(self, name: str, fn: Callable[[float], float]) -> None:
        """Register an easing function under ``namespace.name``.

        Unlike the class-registering surfaces, this is a direct call (not a
        decorator) — easing functions are plain callables, not classes.
        """
        self._buffers["easing"][self._qualify(name)] = fn

    def emoji(self, slug: str, data: PixelData) -> None:
        """Register a low-res 8x8 emoji under ``namespace.slug``.

        Direct call (not a decorator) — emoji data is a pixel list, not a
        class. Resolvable inline as ``:namespace.slug:`` once committed.
        ``data`` is a ``PixelData`` — a list of ``(x, y, r, g, b)`` int tuples
        (0-7 coordinates for an 8x8 sprite; 0-255 color channels).
        """
        self._buffers["emojis"][self._qualify(slug)] = data

    def hires_emoji(self, slug: str, data: HiResEmoji) -> None:
        """Register a hi-res emoji under ``namespace.slug``.

        The hi-res sprite is used by the direct draw API (``draw_emoji_at`` /
        ``measure_emoji_at``) on a scaled canvas. NOTE: inline ``:namespace.slug:``
        text and unscaled canvases resolve ONLY through the low-res registry, so
        for those a matching ``api.emoji(slug, ...)`` low-res counterpart is
        required. Registering a hi-res emoji with no low-res pairing logs a
        warning at load time. Direct call.
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
        # Resolved eagerly to an absolute Path; existence is NOT checked here —
        # a missing path surfaces as UnknownFontError at render time, same as a
        # mis-spelled bundled font name.
        self._buffers["fonts"][self._qualify(name)] = (self.root / path).resolve()


def make_color(r: int, g: int, b: int) -> Color:
    """Build a Color from RGB components (0-255), for use in a provider's
    ``color_for`` / a border's ``paint``. Wraps the rgbmatrix Color so plugins
    don't import internal modules."""
    from led_ticker._compat import require_graphics

    return require_graphics().Color(r, g, b)

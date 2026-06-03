"""Public plugin API for led-ticker.

Plugins import ONLY this module. Everything else under ``led_ticker`` is
internal and may change without notice. A plugin defines a top-level
``register(api)`` function; the loader passes a :class:`PluginAPI` bound to the
plugin's namespace. Every registered name is auto-prefixed with that namespace
(``"namespace.name"``) and buffered until the loader commits it atomically.

A registered widget class may also define a ``validate_config(cls, cfg) ->
list[str]`` classmethod (a @classmethod). When present it is called during
config validation; any returned messages become pre-flight errors. This is a
convention (no ``api.*`` registration) — the rule travels with the widget type.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

# Re-exports: the stable surface plugin authors subclass / annotate against.
from led_ticker import colors
from led_ticker._types import Canvas, Color, DrawResult, Font, PixelData
from led_ticker.animations import Animation, AnimationFrame
from led_ticker.borders import BorderEffect, BorderEffectBase
from led_ticker.color_providers import ColorProvider, ColorProviderBase
from led_ticker.drawing import compute_baseline, get_text_width
from led_ticker.fonts import resolve_font
from led_ticker.fonts.hires_loader import HiresFont
from led_ticker.pixel_emoji import HiResEmoji, draw_emoji_at, measure_emoji_at
from led_ticker.pixel_emoji import draw_with_emoji as _draw_with_emoji
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
    "DrawResult",
    "ColorProvider",
    "ColorProviderBase",
    "Font",
    "HiResEmoji",
    "HiresFont",
    "PixelData",
    "StartupContext",
    "Transition",
    "Widget",
    "colors",
    "compute_baseline",
    "draw_emoji_at",
    "draw_text",
    "get_text_width",
    "make_color",
    "measure_emoji_at",
    "resolve_font",
    "spawn_tracked",
]
# Public plugin surface: registry contributions + lifecycle hooks.

API_VERSION: tuple[int, int] = (1, 0)

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

    To add an overlay that reacts to startup state, register a paint function
    via ``api.overlay`` (it can read shared state your startup hook updates).
    Appending directly to ``frame.overlay_hooks`` works but is NOT exception-
    guarded.
    """

    frame: Any
    session: Any
    config: Any


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
        # is a single generic loop over all registry surfaces.
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
        # Lifecycle hooks are ordered lists of callables (no name key), so they
        # live outside _buffers and are NOT committed to a registry — the loader
        # collects them per-load into LoadedPlugins. See plan "pillar 2".
        self._overlays: list[Callable[[Any], None]] = []
        self._startup_hooks: list[StartupHook] = []
        self._shutdown_hooks: list[ShutdownHook] = []

    @property
    def _widgets(self) -> dict[str, Any]:
        return self._buffers["widgets"]

    @property
    def _transitions(self) -> dict[str, Any]:
        return self._buffers["transitions"]

    def _qualify(self, name: str) -> str:
        return f"{self.namespace}.{name}"

    def widget(self, name: str) -> Callable[[_T], _T]:
        """Register a widget class under ``namespace.name``.

        To accept the standard ``font_color`` / color-provider config knob,
        declare a ``font_color`` field on the widget (e.g.
        ``font_color: object = None``); the loader coerces the TOML value to a
        ColorProvider and injects it into that field. A widget without this
        field will reject ``font_color`` as an unknown field during validation.
        """

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

    def overlay(self, paint: Callable[[Any], None]) -> None:
        """Register an overlay painter run on every frame before the hardware
        swap. ``paint(canvas)`` draws directly on the real canvas (physical
        pixels) — use ``canvas.SetPixel(x, y, r, g, b)`` (see ``canvas.width`` /
        ``canvas.height`` for bounds); ``make_color`` builds Colors and
        ``draw_emoji_at`` paints emojis. Direct call.

        Register overlays HERE (via ``api.overlay``) rather than appending to
        ``StartupContext.frame.overlay_hooks`` in a startup hook: only overlays
        registered this way are exception-wrapped (a raise disables the hook and
        is logged once, rather than freezing the panel). A common service
        pattern is to register a paint function here that reads shared state an
        ``on_startup`` poller updates.
        """
        self._overlays.append(paint)

    def on_startup(self, fn: StartupHook) -> None:
        """Register a hook run once, after the frame + session exist and before
        the main loop. Receives a :class:`StartupContext`; may be sync or async
        (awaited if it returns a coroutine). Spin up long-lived work via the
        public ``spawn_tracked`` — pass a coroutine, e.g.
        ``spawn_tracked(poll())`` where ``poll`` is an ``async def``. Direct
        call.
        """
        self._startup_hooks.append(fn)

    def on_shutdown(self, fn: ShutdownHook) -> None:
        """Register a hook run best-effort when the run loop exits (in its
        ``finally``). Takes no arguments; may be sync or async. Direct call.
        """
        self._shutdown_hooks.append(fn)


def make_color(r: int, g: int, b: int) -> Color:
    """Build a Color from RGB components (0-255), for use in a provider's
    ``color_for`` / a border's ``paint``. Wraps the rgbmatrix Color so plugins
    don't import internal modules."""
    from led_ticker._compat import require_graphics

    return require_graphics().Color(r, g, b)


def draw_text(
    canvas: Canvas, font: Font, text: str, x: int, y: int, color: Color
) -> int:
    """Draw ``text`` on ``canvas`` at baseline ``y`` starting at column ``x``.

    For use inside an ``api.overlay`` painter (or anywhere a plugin has a
    canvas). ``font`` comes from ``resolve_font(name[, size])``; ``color`` from
    ``make_color(r, g, b)``. Inline ``:emoji:`` tokens in ``text`` render too.
    Returns the absolute x-position just past the drawn text (i.e. where the
    next ``draw_text`` should start) — so ``next_x = draw_text(canvas, font,
    s, x, y, c)`` chains correctly. Does not clamp to ``canvas.width`` — text
    past the right edge is simply not drawn.
    """
    return x + _draw_with_emoji(canvas, font, x, y, color, text)

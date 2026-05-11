"""RGB color definitions for the LED display.

Constants are constructed lazily via PEP 562 `__getattr__`: the first
access to e.g. `RGB_WHITE` calls `make_color(...)`, which triggers
`require_graphics()`. Importing this module is a no-op against the
rgbmatrix library — useful for keeping cold-start cost low and keeping
test stubs un-loaded until they're actually needed.

`lazy_palette()` is the reusable building block: pass a name → RGB
mapping, get back a function suitable for use as a module-level
`__getattr__`. `widgets/mlb.py` uses this pattern for its own palette.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING

from led_ticker._compat import require_graphics

if TYPE_CHECKING:
    from led_ticker._types import Color


def make_color(r: int, g: int, b: int) -> Color:
    """Construct a `graphics.Color`.

    Public because `widgets/mlb.py` calls it for team-color helpers
    that build colors on demand. Internal callers in this module use
    it too so there's one place that touches `require_graphics`.
    """
    g_mod = require_graphics()
    return g_mod.Color(r, g, b)


def lazy_palette(palette: dict[str, tuple[int, int, int]]) -> Callable[[str], Color]:
    """Build a module-level `__getattr__` that materializes colors on demand.

    Usage::

        # in some_widget.py
        __getattr__ = lazy_palette({
            "WIN_COLOR": (46, 200, 46),
            "LOSS_COLOR": (220, 30, 30),
        })

    The returned function caches each color so repeated access is O(1)
    and identity-stable.
    """

    @cache
    def _build(name: str) -> Color:
        if name not in palette:
            raise AttributeError(
                f"no such color {name!r} (available: {sorted(palette)})"
            )
        return make_color(*palette[name])

    return _build


# Source-of-truth palette. Mapping name → (r, g, b). Materialized
# to `graphics.Color` on first attribute access via `__getattr__`.
_PALETTE: dict[str, tuple[int, int, int]] = {
    "RGB_WHITE": (255, 255, 255),
    "DEFAULT_COLOR": (255, 255, 0),
    "RED": (255, 40, 40),
    "GREEN": (46, 200, 46),
    "BLUE": (40, 100, 255),
    "YELLOW": (255, 220, 0),
    "ORANGE": (255, 140, 0),
    "PURPLE": (160, 60, 200),
    "CYAN": (0, 220, 220),
    "PINK": (240, 70, 200),
}

__getattr__ = lazy_palette(_PALETTE)


def __dir__() -> list[str]:
    return [*globals(), *_PALETTE.keys()]

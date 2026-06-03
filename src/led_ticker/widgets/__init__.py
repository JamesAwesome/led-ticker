"""Widget registry and auto-discovery."""

from collections.abc import Callable
from typing import Any, TypeVar

_T = TypeVar("_T")

_WIDGET_REGISTRY: dict[str, type[Any]] = {}


def register(name: str) -> Callable[[_T], _T]:
    """Decorator to register a widget class by config name."""

    def decorator(cls: _T) -> _T:
        if name in _WIDGET_REGISTRY:
            raise ValueError(
                f"Widget name {name!r} is already registered to"
                f" {_WIDGET_REGISTRY[name].__name__!r}."  # type: ignore[union-attr]
            )
        _WIDGET_REGISTRY[name] = cls  # type: ignore[arg-type]
        return cls

    return decorator


def get_widget_class(name: str) -> type[Any]:
    """Look up a widget class by its config name."""
    if name not in _WIDGET_REGISTRY:
        raise ValueError(
            f"Unknown widget type: {name!r}. Available: {list(_WIDGET_REGISTRY.keys())}"
        )
    return _WIDGET_REGISTRY[name]


# Auto-import all built-in widget modules so they register themselves
from led_ticker.widgets import (  # noqa: E402, F401
    gif,
    message,
    mlb,
    mlb_standings,
    rss_feed,
    still,
    two_row,
    weather,
)
from led_ticker.widgets.crypto import coinbase, coingecko, etherscan  # noqa: E402, F401

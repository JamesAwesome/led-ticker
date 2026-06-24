"""Rendering-backend abstraction.

A `Backend` owns the matrix lifecycle the engine assumes: build the matrix
(privileged work) in `setup()`, hand out fresh back-buffer canvases via
`create_canvas()`, and present a canvas via `swap()` (returning the NEW
back-buffer — constraints #1/#8). `LedFrame` holds a backend and keeps all
backend-agnostic mechanism (overlay hooks, status-board, preview tee).

The 13 hardware-rendering constraints in CLAUDE.md are this protocol's
contract; `backends.conformance` encodes them as an importable test suite.
"""

from typing import Protocol, runtime_checkable

from led_ticker._types import Canvas


class BackendNotReadyError(RuntimeError):
    """Raised when a canvas/swap/brightness operation is attempted before
    `Backend.setup()` (and therefore before the matrix exists)."""


@runtime_checkable
class Backend(Protocol):
    """The rendering-backend contract. See module docstring + CLAUDE.md."""

    brightness: int  # settable; live brightness scheduling. The only mutable attr.
    framerate_fraction: int  # presentation hint; rgbmatrix-specific, 1 elsewhere.

    def setup(self) -> None:
        """Build the underlying matrix and perform all privileged work.
        The declared privilege-drop boundary. Called exactly once by the app
        after all pre-drop work."""
        ...

    def create_canvas(self) -> Canvas:
        """Return a fresh back-buffer canvas."""
        ...

    def swap(self, canvas: Canvas, framerate_fraction: int = 1) -> Canvas:
        """Present `canvas`; return the NEW back-buffer to draw into next.
        MUST return a different object than it was handed (constraints #1/#8)."""
        ...


_REGISTRY: dict[str, type] = {}


def register_backend(name: str):
    """Class decorator: register a backend implementation under `name`."""

    def _decorate(cls: type) -> type:
        _REGISTRY[name] = cls
        return cls

    return _decorate


def known_backends() -> list[str]:
    """Sorted list of registered backend names."""
    return sorted(_REGISTRY)


def get_backend_class(name: str) -> type:
    """Resolve a backend class by name. Raises ValueError (listing the known
    names) on an unknown name so the user can self-correct."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown backend {name!r}; known backends: {known_backends()}"
        ) from None

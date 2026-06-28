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
    # `brightness` is BUFFERED before `setup()` (the matrix doesn't exist yet)
    # and applied/live after `setup()`: the getter then reflects the matrix's
    # value and the setter forwards to it. The conformance kit checks both.

    def setup(self) -> None:
        """Build the underlying matrix and perform all privileged work.
        The declared privilege-drop boundary. Called exactly once by the app
        after all pre-drop work.

        Lifecycle: setup() is called from INSIDE the running asyncio loop (via
        LedFrame.setup() in app.run.run()), so a backend that needs background I/O
        may `asyncio.get_running_loop().create_task(...)` from setup(). setup() is
        still a sync def — guard get_running_loop() with try/except RuntimeError so
        the backend also works when constructed outside a loop (e.g. conformance)."""
        ...

    def create_canvas(self) -> Canvas:
        """Return a fresh back-buffer canvas."""
        ...

    def swap(self, canvas: Canvas) -> Canvas:
        """Present `canvas`; return the NEW back-buffer to draw into next.
        MUST return a different object than it was handed (constraints #1/#8).
        Any presentation hint (e.g. rgbmatrix's framerate_fraction) is an
        internal backend detail read inside the backend, not a protocol arg."""
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
        hint = ""
        if "." not in name:
            # Plugin backends are namespaced (`<plugin>.<name>`); a user who
            # wrote a bare name may have meant a registered dotted one.
            dotted = [k for k in _REGISTRY if "." in k and k.split(".", 1)[1] == name]
            if dotted:
                hint = f" (plugin backends are namespaced — did you mean {dotted!r}?)"
        raise ValueError(
            f"unknown backend {name!r}; known backends: {known_backends()}{hint}"
        ) from None


# Import implementations to trigger @register_backend decorators.
# These run eagerly at package import time: any `import led_ticker.backends`
# (or `from led_ticker.backends import ...`) registers both built-in backends
# before the caller reaches the registry.
from led_ticker.backends.headless import HeadlessBackend  # noqa: F401, E402
from led_ticker.backends.rgbmatrix import RgbMatrixBackend  # noqa: F401, E402

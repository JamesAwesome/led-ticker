"""Transition effects between widgets."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from led_ticker._types import Canvas
from led_ticker.ticker import _swap

# --- Easing functions ---


def linear(p: float) -> float:
    return p


def ease_out(p: float) -> float:
    return 1 - (1 - p) ** 2


def ease_in_out(p: float) -> float:
    return 3 * p * p - 2 * p * p * p


EASING: dict[str, Callable[[float], float]] = {
    "linear": linear,
    "ease_out": ease_out,
    "ease_in_out": ease_in_out,
}


# --- Transition protocol and registry ---


@runtime_checkable
class Transition(Protocol):
    min_frames: int

    def frame_at(
        self,
        t: float,
        canvas: Canvas,
        outgoing: Any,
        incoming: Any,
        **kwargs: Any,
    ) -> Canvas:
        """Render one frame at progress t (0.0 to 1.0)."""
        ...


_TRANSITION_REGISTRY: dict[str, type[Transition]] = {}


def register_transition(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        _TRANSITION_REGISTRY[name] = cls
        return cls

    return decorator


def get_transition_class(name: str) -> type[Transition]:
    if name not in _TRANSITION_REGISTRY:
        raise ValueError(
            f"Unknown transition: {name!r}. "
            f"Available: {list(_TRANSITION_REGISTRY.keys())}"
        )
    return _TRANSITION_REGISTRY[name]


# --- Transition runner ---


async def run_transition(
    canvas: Canvas,
    frame: Any,
    outgoing: Any,
    incoming: Any,
    transition: Transition,
    duration: float = 0.5,
    easing: str = "linear",
    scroll_speed: float = 0.05,
    outgoing_scroll_pos: int = 0,
    region: Any = None,
    skip_final_incoming: bool = False,
) -> Canvas:
    """Run a transition. Returns the current back-buffer canvas.

    The ``region`` parameter is accepted for forward-compatibility with
    zoned layouts but is not currently passed to ``frame_at``; transitions
    operate on the full canvas in this port.

    ``skip_final_incoming=True`` tells the transition to skip drawing the
    incoming widget at t=1.0. Used for inter-section dissolves where the
    incoming widget would render at the *outgoing* section's scale (since
    the canvas was wrapped at last_scale), creating a one-frame wrong-scale
    flash before the new section's first render at the correct scale.
    Skipping the t=1.0 draw leaves the canvas mostly black for that one
    frame, which the new section overwrites immediately.
    """
    del region  # plumbed but unused; future zoned layouts revisit this
    ease_fn = EASING.get(easing, linear)
    frame_count = max(1, int(duration / scroll_speed))
    if hasattr(transition, "min_frames"):
        frame_count = max(frame_count, transition.min_frames)

    for i in range(frame_count + 1):
        t = ease_fn(i / max(1, frame_count))
        canvas.Clear()
        transition.frame_at(
            t,
            canvas,
            outgoing,
            incoming,
            outgoing_scroll_pos=outgoing_scroll_pos,
            skip_final_incoming=skip_final_incoming,
        )
        canvas = _swap(canvas, frame)
        await asyncio.sleep(scroll_speed)

    return canvas


# --- Auto-import submodules so decorators execute ---
# ruff: noqa: E402
from led_ticker.transitions import (  # noqa: F401
    baseball,
    effects,
    nyancat,
    pacman,
    pokeball,
    push,
    sailor_moon,
    wipe,
)

# --- Re-export all transition classes ---
from led_ticker.transitions.baseball import (  # noqa: F401
    Baseball,
    BaseballAlternating,
    BaseballReverse,
)
from led_ticker.transitions.effects import (  # noqa: F401
    ColorFlash,
    Cut,
    Dissolve,
    Scroll,
    SplitHorizontal,
)
from led_ticker.transitions.nyancat import (  # noqa: F401
    NyanCat,
    NyanCatAlternating,
    NyanCatReverse,
)
from led_ticker.transitions.pacman import (  # noqa: F401
    Pacman,
    PacmanAlternating,
    PacmanReverse,
)
from led_ticker.transitions.pokeball import (  # noqa: F401
    Pokeball,
    PokeballAlternating,
    PokeballReverse,
)
from led_ticker.transitions.push import (  # noqa: F401
    PushAlternating,
    PushDown,
    PushLeft,
    PushRight,
    PushUp,
)
from led_ticker.transitions.sailor_moon import (  # noqa: F401
    SailorMoon,
    SailorMoonAlternating,
    SailorMoonReverse,
)
from led_ticker.transitions.wipe import (  # noqa: F401
    WipeAlternating,
    WipeDown,
    WipeLeft,
    WipeRight,
    WipeUp,
)

"""Transition effects between widgets."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from led_ticker._types import Canvas
from led_ticker.ticker import _maybe_wrap, _swap

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
    incoming_scale: int | None = None,
    incoming_content_height: int = 16,
) -> Canvas:
    """Run a transition. Returns the current back-buffer canvas.

    ``region`` is plumbed for forward-compat with zoned layouts; not
    currently passed to ``frame_at``.

    ``incoming_scale`` lets a dissolve cross between scales smoothly. If
    provided AND different from the wrapper's current scale, the canvas
    is re-wrapped at ``incoming_scale`` at t >= 0.5 so the incoming widget
    dissolves in at its native scale rather than briefly flashing at the
    outgoing scale before the new section's first render snaps to the
    correct one.

    ``incoming_content_height`` is the logical canvas height the incoming
    section uses (TwoRowMessage and similar widgets compute row positions
    from `canvas.height`). Must match the new section's `content_height`
    so the incoming widget dissolves IN at the same y-positions that
    `run_swap` will draw it at after the transition completes; otherwise
    the rows visibly jump vertically when the section starts.
    """
    del region  # plumbed but unused; future zoned layouts revisit this

    ease_fn = EASING.get(easing, linear)
    frame_count = max(1, int(duration / scroll_speed))
    if hasattr(transition, "min_frames"):
        frame_count = max(frame_count, transition.min_frames)

    current_scale = getattr(canvas, "scale", 1)
    needs_switch = incoming_scale is not None and incoming_scale != current_scale
    incoming_canvas: Canvas | None = None

    # Freeze any _FrameAware widget on outgoing/incoming for the duration of
    # the transition. Otherwise rendering the widget for compositing
    # advances its frame counter and either tears its phase
    # or eats into the next section's animation budget.
    _pause_presenter(outgoing)
    _pause_presenter(incoming)
    try:
        for i in range(frame_count + 1):
            t = ease_fn(i / max(1, frame_count))

            # At t >= 0.5, switch to a wrapper at incoming_scale so the
            # incoming widget dissolves in at its native size.
            if (
                needs_switch
                and incoming_scale is not None
                and t >= 0.5
                and incoming_canvas is None
            ):
                incoming_canvas = _maybe_wrap(
                    frame.matrix.CreateFrameCanvas(),
                    incoming_scale,
                    incoming_content_height,
                )

            active = incoming_canvas if incoming_canvas is not None else canvas
            # Transition compositing intentionally ignores bg_color — between
            # two sections with different bgs, the dissolve flashes through
            # black rather than coupling transition logic to widget state.
            # Accepted footgun per the bg-color design spec.
            active.Clear()
            transition.frame_at(
                t,
                active,
                outgoing,
                incoming,
                outgoing_scroll_pos=outgoing_scroll_pos,
                duration_ms=int(duration * 1000),
            )
            new_canvas = _swap(active, frame)
            if incoming_canvas is not None:
                incoming_canvas = new_canvas
            else:
                canvas = new_canvas
            await asyncio.sleep(scroll_speed)
    finally:
        _resume_presenter(outgoing)
        _resume_presenter(incoming)

    return incoming_canvas if incoming_canvas is not None else canvas


def _pause_presenter(obj: Any) -> None:
    pause = getattr(obj, "pause_frame", None)
    if callable(pause):
        pause()


def _resume_presenter(obj: Any) -> None:
    resume = getattr(obj, "resume_frame", None)
    if callable(resume):
        resume()


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

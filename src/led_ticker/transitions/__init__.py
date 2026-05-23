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
    min_frames: int = 0

    def frame_at(
        self,
        t: float,
        canvas: Canvas,
        outgoing: Any,
        incoming: Any,
        **kwargs: Any,
    ) -> Canvas:
        """Render one frame at progress t (0.0–1.0).

        Recognized kwargs (passed by run_transition; safe to ignore if
        the transition doesn't need them):

        - ``outgoing_scroll_pos: int`` — pixel offset where the outgoing
          widget stopped scrolling. Push transitions use this to continue
          the scroll in the same direction without a visible jump.
        - ``duration_ms: int`` — total transition duration in milliseconds.
          Sprite-trail transitions use this to compute crossing speed so
          the entity reaches the far edge exactly when t=1.0.
        - ``incoming_bg_color: tuple[int,int,int] | None`` — the new
          section's background color. Hires snap transitions (pokeball,
          nyancat, baseball) use this at t≥0.95 to Fill() before drawing
          incoming so a bg-colored section doesn't flash black for one
          tick.

        At t=0: render only outgoing. At t=1.0: render only incoming.
        The runner calls ``canvas.Clear()`` or ``canvas.Fill()`` BEFORE
        each ``frame_at`` call — transitions must NOT clear the canvas
        themselves.
        """
        ...


_TRANSITION_REGISTRY: dict[str, type[Transition]] = {}


def _normalize_bg(c: Any) -> tuple[int, int, int] | None:
    """Coerce an `(r, g, b)` tuple, a `graphics.Color`, or `None` to
    a tuple/None pair.

    Module-level so `_hires_loader._snap_reset` can call it without
    duplicating the logic — both call sites must accept the same
    inputs (widgets store `bg_color` as `graphics.Color` after
    `_build_widget` coercion; `SectionConfig.bg_color` is a tuple).
    """
    if c is None:
        return None
    if hasattr(c, "red"):
        return (c.red, c.green, c.blue)
    return c


def register_transition(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        if name in _TRANSITION_REGISTRY:
            raise ValueError(
                f"Transition name {name!r} is already registered to"
                f" {_TRANSITION_REGISTRY[name].__name__!r}."
            )
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


def list_transition_names() -> list[str]:
    """Return all registered transition names, sorted alphabetically."""
    return sorted(_TRANSITION_REGISTRY.keys())


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
    outgoing_bg_color: Any = None,
    incoming_bg_color: Any = None,
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

    ``outgoing_bg_color`` and ``incoming_bg_color`` make the per-frame
    reset preserve bg color through the transition. Without them, the
    per-frame reset is unconditional ``Clear()`` — both bgs disappear
    for the entire transition, then the new section's first
    ``reset_canvas`` snaps to the new bg in one tick (the "stutter"
    that PR #8's predecessor fix was chasing).

    With both set, the per-frame reset uses ``outgoing_bg_color`` at
    t<0.5 and ``incoming_bg_color`` at t>=0.5. The cut-over at 0.5
    matches ``incoming_scale``'s switch point so a section transition
    that crosses both scale and bg flips them together. Either side
    can be ``None`` independently — leaving outgoing as None means
    the outgoing's bg vanishes immediately when the transition starts
    (legacy behavior); leaving incoming as None means the panel
    flashes black at the cut-over.

    The hires snap inside ``render_hires_frame`` (pokeball/nyancat/
    baseball at t>=0.95) does its own ``Clear()`` before drawing
    incoming. This function passes ``incoming_bg_color`` to ``frame_at``
    via kwargs so the snap can paint ``Fill(incoming_bg)`` instead —
    otherwise the last frame of a hires transition shows incoming
    text on black, then the next tick (when the new section's
    ``reset_canvas`` runs) finally fills the panel with bg, producing
    a single-tick "border on black" flash on bordered widgets.
    """
    del region  # plumbed but unused; future zoned layouts revisit this

    outgoing_bg_color = _normalize_bg(outgoing_bg_color)
    incoming_bg_color = _normalize_bg(incoming_bg_color)

    # `easing` is validated at config-load via coerce_choice against
    # EASING.keys(); direct dict access here raises a clean KeyError
    # for programmatic callers who skipped that path.
    ease_fn = EASING[easing]
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
    # Reset the incoming widget's frame counter so frame-aware effects
    # (typewriter, color_cycle, rainbow) render their visit-initial
    # state during the transition. Without this, on loop iteration 2+
    # the incoming widget's _frame_count holds the value from the END
    # of its previous visit — typewriter shows the full text during
    # the wipe-in, then snaps to "R" when the section begins; rainbow
    # shows mid-rotation hues during the wipe, then snaps to hue 0.
    # `_show_one` also resets after the transition (covering paths
    # that bypass run_transition), so the post-transition reset is
    # idempotent — calling it twice is harmless.
    # Outgoing is intentionally NOT reset: its previous-end state is
    # the visual continuity story for the wipe-out.
    _reset_presenter(incoming)
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
            # Per-frame reset. The outgoing section is dominant before
            # t=0.5 — paint its bg so the wine/yellow/whatever stays
            # visible behind the outgoing widget for the first half.
            # At t>=0.5 the incoming section's bg takes over, matching
            # `incoming_scale`'s switch point. None on either side
            # falls back to Clear() — that's the legacy black-flash
            # behavior, fine for transitions between two no-bg
            # sections but a visible stutter when either side has bg.
            reset_bg = outgoing_bg_color if t < 0.5 else incoming_bg_color
            if reset_bg is not None:
                active.Fill(*reset_bg)
            else:
                active.Clear()
            transition.frame_at(
                t,
                active,
                outgoing,
                incoming,
                outgoing_scroll_pos=outgoing_scroll_pos,
                duration_ms=int(duration * 1000),
                # Hires transitions (pokeball/nyancat/baseball) do
                # their own Clear+draw snap at t>=0.95. Pass
                # incoming_bg_color so the snap can Fill() instead
                # — otherwise the last transition frame is "incoming
                # text on black", visible as a single-tick flash on
                # bg-colored sections.
                incoming_bg_color=incoming_bg_color,
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


def _reset_presenter(obj: Any) -> None:
    reset = getattr(obj, "reset_frame", None)
    if callable(reset):
        reset()


# --- Auto-import submodules so decorators execute ---
# ruff: noqa: E402
# pkgutil discovers every non-private .py file under transitions/ so
# @register_transition decorators run automatically. Adding a new
# transitions/my_effect.py only requires the decorator — no manual
# entry here. Private modules (leading _) are excluded.
import importlib
import pkgutil

import led_ticker.transitions as _transitions_pkg

for _mod_info in pkgutil.iter_modules(
    _transitions_pkg.__path__,
    _transitions_pkg.__name__ + ".",
):
    if not _mod_info.name.rsplit(".", 1)[-1].startswith("_"):
        importlib.import_module(_mod_info.name)

del importlib, pkgutil, _transitions_pkg

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
    PushRandom,
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
    WipeRandom,
    WipeRight,
    WipeUp,
)

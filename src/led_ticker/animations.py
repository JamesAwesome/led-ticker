"""Animations — frame-aware position/visibility behaviors for
TickerMessage.

Replaces the legacy `WidgetPresenter`-wrapped Typewriter with a
widget-level animation instance bound to TickerMessage's `animation`
field. Each tick TickerMessage asks the animation for an
`AnimationFrame` describing what to render this frame.

Color providers are orthogonal — animations control position and
visibility, providers control color. The two compose freely.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class AnimationFrame:
    """What the widget should render at the current frame.

    visible_text: The slice (or full text) to draw. Typewriter returns
                  growing prefixes.
    """

    visible_text: str


@runtime_checkable
class Animation(Protocol):
    """Protocol for frame-aware animations on TickerMessage and image widgets.

    An animation controls how much of ``full_text`` is revealed each tick.
    The ``frame`` counter comes from the widget's ``_FrameAware`` counter
    for the ``"animation"`` effect slot — it ticks at ENGINE_TICK_MS
    cadence, pauses during transitions, and resets per-visit (unless the
    class sets ``restart_on_visit = False``).

    Implementing a new animation: return growing prefixes of ``full_text``
    in ``visible_text`` for a typewriter effect, or return ``full_text``
    unchanged and control something else (e.g. cursor position via a
    future field on ``AnimationFrame``).

    See ``Typewriter`` for the canonical implementation.
    """

    def frame_for(
        self,
        frame: int,
        full_text: str,
        canvas_width: int,
        text_width: int,
    ) -> AnimationFrame: ...


class Typewriter:
    """Slice grows one character per `frames_per_char` frames.

    At the default ENGINE_TICK_MS=50ms, frames_per_char=3 means each
    char is on screen for ~150ms (~7 chars/sec) — fast enough to feel
    snappy, slow enough to read the typing.
    """

    def __init__(self, chars_per_frame: int = 1, frames_per_char: int = 3) -> None:
        self.chars_per_frame = chars_per_frame
        self.frames_per_char = frames_per_char

    def frame_for(
        self, frame: int, full_text: str, canvas_width: int, text_width: int
    ) -> AnimationFrame:
        # Effective progress: each frames_per_char ticks advances by
        # chars_per_frame characters. With defaults (1, 3): advance 1
        # char every 3 frames.
        progress = (frame // self.frames_per_char) + 1
        chars_visible = min(len(full_text), progress * self.chars_per_frame)
        return AnimationFrame(visible_text=full_text[:chars_visible])

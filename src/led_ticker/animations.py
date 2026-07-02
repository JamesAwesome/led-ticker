"""Animations — frame-aware position/visibility behaviors for
TickerMessage.

Replaces the legacy `WidgetPresenter`-wrapped Typewriter with a
widget-level animation instance bound to TickerMessage's `animation`
field. Each tick TickerMessage asks the animation for an
`AnimationFrame` describing what to render this frame.

Color providers are orthogonal — animations control position and
visibility, providers control color. The two compose freely.
"""

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from led_ticker.constants import ENGINE_TICK_MS


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
    The ``frame`` counter comes from the widget's ``FrameAwareBase`` counter
    for the ``"animation"`` effect slot — it ticks at ENGINE_TICK_MS
    cadence, pauses during transitions, and resets per-visit (unless the
    class sets ``restart_on_visit = False``).

    Implementing a new animation: return growing prefixes of ``full_text``
    in ``visible_text`` for a typewriter effect, or return ``full_text``
    unchanged and control something else (e.g. cursor position via a
    future field on ``AnimationFrame``).

    Animations MAY also define ``frames_to_rest(frame, total_chars) -> int``
    (0 = at rest / no rest concept): the engine consults it at the
    hold→transition handoff and can extend the hold up to ~1 s so a
    transition doesn't chop the animation mid-flight.

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

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        """Frames until the reveal completes (one-shot rest: 0 forever
        once fully typed).

        total_chars MUST be the raw ``len(full_text)`` — the same length
        ``frame_for`` slices against — INCLUDING any ``:slug:`` emoji
        characters. The emoji-excluded ``count_text_chars`` is a color-
        provider quantity; feeding it here under-counts and reports done
        mid-type.
        """
        if total_chars <= 0:
            return 0
        done_frame = self.frames_per_char * (
            math.ceil(total_chars / self.chars_per_frame) - 1
        )
        return max(0, done_frame - frame)

    def typing_duration_seconds(self, total_chars: int) -> float:
        """Wall-clock seconds to fully reveal ``total_chars`` raw
        characters at engine cadence. The ONLY home of the typing-
        duration formula — validate rule 61 imports and calls this;
        it must never re-implement the math."""
        return self.frames_to_rest(0, total_chars) * ENGINE_TICK_MS / 1000.0


_ANIMATION_REGISTRY: dict[str, type] = {
    "typewriter": Typewriter,
}

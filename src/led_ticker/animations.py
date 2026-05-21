"""Animations — frame-aware position/visibility behaviors for
TickerMessage.

Replaces the legacy `WidgetPresenter`-wrapped Typewriter with a
widget-level animation instance bound to TickerMessage's `animation`
field. Each tick TickerMessage asks the animation for an
`AnimationFrame` describing what to render this frame.

Color providers are orthogonal — animations control position and
visibility, providers control color. The two compose freely.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AnimationFrame:
    """What the widget should render at the current frame.

    visible_text: The slice (or full text) to draw. Typewriter returns
                  growing prefixes.
    """

    visible_text: str


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

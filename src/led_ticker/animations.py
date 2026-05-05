"""Animations — frame-aware position/visibility behaviors for
TickerMessage.

Replaces the legacy `WidgetPresenter`-wrapped Typewriter and Bounce
with widget-level animation instances bound to TickerMessage's
`animation` field. Each tick TickerMessage asks the animation for an
`AnimationFrame` describing what to render this frame.

Color providers are orthogonal — animations control position and
visibility, providers control color. The two compose freely.
"""

from __future__ import annotations

from dataclasses import dataclass

from led_ticker.transitions import ease_out


@dataclass
class AnimationFrame:
    """What the widget should render at the current frame.

    visible_text:    The slice (or full text) to draw. Typewriter
                     returns growing prefixes; Bounce returns the full.
    cursor_override: If set, place the text at this x. If None, the
                     orchestrator's cursor_pos is used (i.e. the
                     animation doesn't reposition).
    """

    visible_text: str
    cursor_override: int | None


class Typewriter:
    """Slice grows one character per frame (or `chars_per_frame`)."""

    def __init__(self, chars_per_frame: int = 1) -> None:
        self.chars_per_frame = chars_per_frame

    def frame_for(
        self, frame: int, full_text: str, canvas_width: int, text_width: int
    ) -> AnimationFrame:
        chars_visible = min(
            len(full_text),
            (frame + 1) * self.chars_per_frame,
        )
        return AnimationFrame(
            visible_text=full_text[:chars_visible],
            cursor_override=None,
        )


class Bounce:
    """Slide in from right (ease_out), hold at center (`hold_frames`),
    slide out left (ease_in)."""

    def __init__(self, hold_frames: int = 40, scroll_frames: int = 20) -> None:
        self.hold_frames = hold_frames
        self.scroll_frames = scroll_frames

    @property
    def total_frames(self) -> int:
        return self.scroll_frames + self.hold_frames + self.scroll_frames

    def frame_for(
        self, frame: int, full_text: str, canvas_width: int, text_width: int
    ) -> AnimationFrame:
        sf = self.scroll_frames
        hf = self.hold_frames
        center_x = max(0, (canvas_width - text_width) // 2)

        if frame < sf:
            # Scroll in from right with ease-out
            p = ease_out(frame / max(1, sf - 1))
            pos = int(canvas_width + (center_x - canvas_width) * p)
        elif frame < sf + hf:
            # Hold at center
            pos = center_x
        elif frame < self.total_frames:
            # Scroll out to left with ease-in (p^2)
            p = (frame - sf - hf) / max(1, sf - 1)
            eased = p * p
            pos = int(center_x + (-text_width - center_x) * eased)
        else:
            pos = center_x

        return AnimationFrame(visible_text=full_text, cursor_override=pos)

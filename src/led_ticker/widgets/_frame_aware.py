"""Frame counter mixin shared by every text-painting widget.

Replaces the `WidgetPresenter` wrapper's frame state. Each widget
tracks its own `_frame_count`; the orchestrator calls `advance_frame()`
per draw tick. Transitions call `pause_frame()` / `resume_frame()`
around their compositing loop so the count doesn't drift while the
widget is being re-rendered for a dissolve. `reset_frame()` is called
at the start of each visit so the count doesn't carry over between
widgets.

Use as a mixin alongside `@attrs.define` on each widget class. The
`init=False` fields don't show up in TOML; they're internal state.
"""

from __future__ import annotations

import attrs


@attrs.define
class _FrameAware:
    """Mixin providing a per-widget frame counter + pause control."""

    _frame_count: int = attrs.field(init=False, default=0)
    _frame_paused: bool = attrs.field(init=False, default=False)

    def advance_frame(self) -> None:
        """Increment the frame counter unless paused."""
        if not self._frame_paused:
            self._frame_count += 1

    def pause_frame(self) -> None:
        """Stop advancing the frame counter — used by `run_transition`
        so an outgoing widget mid-typewriter (etc.) doesn't keep
        ticking while it's only being re-rendered for compositing."""
        self._frame_paused = True

    def resume_frame(self) -> None:
        self._frame_paused = False

    def reset_frame(self) -> None:
        """Zero the counter at the start of a visit. Does NOT clear
        the pause flag — pause/resume are transition-scoped, reset is
        visit-scoped, the two are independent."""
        self._frame_count = 0

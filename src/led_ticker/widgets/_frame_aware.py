"""Frame counter mixin shared by every text-painting widget.

Each widget tracks its own `_frame_count` (engine tick counter,
resets per visit) AND a parallel `_effect_frames` dict tracking
per-effect-attribute counters that follow each effect's
`restart_on_visit` policy.

The orchestrator calls `advance_frame()` per draw tick (both the
primary counter and all per-effect counters increment). Transitions
call `pause_frame()` / `resume_frame()` around their compositing
loop so the count doesn't drift while the widget is being re-
rendered for a dissolve. `reset_frame()` is called by
`ticker._show_one` at the start of each visit; the primary counter
always resets, while per-effect counters reset only for effects
that opted into restart-on-visit (default `True` via `getattr`
fallback).

Widget code reads `self.frame_for(attr_name)` instead of
`self._frame_count` when calling effect APIs. This lets a widget
with both `Typewriter` (restart=True) and `RainbowChaseBorder`
(restart=False) get correct behavior on `loop_count > 1`: the
typewriter retypes each loop while the chase phase advances
continuously.

Use as a mixin alongside `@attrs.define` on each widget class. The
`init=False` fields don't show up in TOML; they're internal state.
"""

from __future__ import annotations

from typing import ClassVar

import attrs


@attrs.define
class _FrameAware:
    """Mixin providing per-widget + per-effect frame counters."""

    _EFFECT_ATTRS: ClassVar[frozenset[str]] = frozenset(
        {
            "font_color",
            "font_color_temp",
            "top_color",
            "bottom_color",
            "border",
            "animation",
        }
    )

    _frame_count: int = attrs.field(init=False, default=0)
    _frame_paused: bool = attrs.field(init=False, default=False)
    _effect_frames: dict[str, int] = attrs.field(init=False, factory=dict)

    def _iter_effects(self):
        """Yield (attr_name, effect_instance) for each non-None
        effect on the widget. Centralized so `advance_frame`,
        `reset_frame`, and any future callers can't drift."""
        for attr in self._EFFECT_ATTRS:
            effect = getattr(self, attr, None)
            if effect is not None:
                yield attr, effect

    def advance_frame(self) -> None:
        """Increment the primary counter AND all per-effect counters.
        No-op if paused."""
        if self._frame_paused:
            return
        self._frame_count += 1
        for attr_name, _ in self._iter_effects():
            self._effect_frames[attr_name] = self._effect_frames.get(attr_name, 0) + 1

    def pause_frame(self) -> None:
        """Stop advancing the frame counters — used by `run_transition`
        so an outgoing widget mid-typewriter (etc.) doesn't keep
        ticking while it's only being re-rendered for compositing."""
        self._frame_paused = True

    def resume_frame(self) -> None:
        self._frame_paused = False

    def reset_frame(self) -> None:
        """Visit-entry reset. The primary counter always resets;
        per-effect counters reset only for effects that opted in
        via `restart_on_visit = True` (the default). Effects with
        `restart_on_visit = False` keep their counter — that's what
        gives `RainbowChaseBorder` continuous phase across loop_count
        boundaries while still letting `Typewriter` retype.

        Does NOT clear the pause flag — pause/resume are
        transition-scoped, reset is visit-scoped, the two are
        independent."""
        self._frame_count = 0
        for attr_name, effect in self._iter_effects():
            if getattr(effect, "restart_on_visit", True):
                self._effect_frames[attr_name] = 0

    def frame_for(self, attr_name: str) -> int:
        """Return the per-effect frame counter, or `_frame_count` as
        a fallback for unknown / unset entries.

        Widget code calls this when invoking an effect API:
        `border.paint(canvas, self.frame_for("border"))`. The
        fallback to `_frame_count` covers the lazy-init case where
        a test sets `_frame_count` directly without going through
        `advance_frame`."""
        return self._effect_frames.get(attr_name, self._frame_count)

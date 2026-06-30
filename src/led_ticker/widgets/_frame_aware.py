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

from typing import ClassVar

import attrs


@attrs.define
class FrameAwareBase:
    """Per-widget + per-effect frame counters for animated ``font_color`` /
    ``border`` effects.

    **Subclass contract (for plugin widgets):**

    - Inherit ``FrameAwareBase`` and decorate the class with ``@attrs.define``.
    - When painting an animated effect, read its counter with
      ``self.frame_for(name)`` — e.g.
      ``border.paint(canvas, self.frame_for("border"))`` or
      ``font_color.color_for(self.frame_for("font_color"), char_idx, total)``.
      ``name`` is the effect's field name (``"font_color"``, ``"border"``, … —
      the set in ``_EFFECT_ATTRS``).
    - Do NOT call ``advance_frame`` / ``pause_frame`` / ``resume_frame`` /
      ``reset_frame`` yourself — the engine drives those each tick and around
      transitions.
    - Plugin widgets use the standard effect fields above (``font_color``,
      ``border``, …), which already have counters. Defining brand-new effect
      *types* isn't part of the plugin contract yet — stick to the standard
      fields.
    """

    _EFFECT_ATTRS: ClassVar[frozenset[str]] = frozenset(
        {
            "font_color",
            "font_color_temp",
            "time_color",
            "top_color",
            "bottom_color",
            "highlight_color",
            "border",
            "animation",
            "text_separator_color",
            "bottom_text_separator_color",
        }
    )

    _frame_count: int = attrs.field(init=False, default=0)
    _frame_paused: bool = attrs.field(init=False, default=False)
    _effect_frames: dict[str, int] = attrs.field(init=False, factory=dict)
    _visit_owner: int | None = attrs.field(init=False, default=None)
    # Inline-value-token resolution freeze (parallel to the frame-counter
    # freeze above). When True, a token-bearing widget must NOT re-resolve
    # its text against the live source registry — it reuses its cached
    # substituted string. The freeze keeps content width stable during
    # scroll / transition compositing / typewriter reveal, where a
    # mid-flight value change would strand the scroll math (constraints
    # #6/#7) or corrupt a composited frame. Held redraws keep this False
    # so a live clock updates during a hold. Set by pause_frame() and the
    # engine's scroll-branch lock; cleared by resume_frame(). Widgets
    # without tokens ignore it entirely.
    _resolution_locked: bool = attrs.field(init=False, default=False)

    def __new__(cls, *args: object, **kwargs: object) -> FrameAwareBase:
        if cls is not FrameAwareBase and "__attrs_attrs__" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} inherits FrameAwareBase but is not decorated with "
                "@attrs.define — frame-counter fields will not be initialized "
                "correctly."
            )
        return super().__new__(cls)

    def _iter_effects(self):
        """Yield (attr_name, effect_instance) for each non-None
        effect on the widget. Centralized so `advance_frame`,
        `reset_frame`, and any future callers can't drift."""
        for attr in self._EFFECT_ATTRS:
            effect = getattr(self, attr, None)
            if effect is not None:
                yield attr, effect

    def advance_frame(self, *, visit_id: int | None = None) -> None:
        """Increment the primary counter AND all per-effect counters.
        No-op if paused.

        When *visit_id* is given, records the first caller as the owner
        and raises ``RuntimeError`` if a different ``visit_id`` calls before
        ``reset_frame()`` clears the claim. Callers that omit *visit_id*
        bypass the ownership check.
        """
        if self._frame_paused:
            return
        if visit_id is not None:
            if self._visit_owner is not None and self._visit_owner != visit_id:
                raise RuntimeError(
                    f"{type(self).__name__} frame counter is claimed by visit_id "
                    f"{self._visit_owner!r}, but advance_frame called with "
                    f"{visit_id!r}. The same widget instance appears to be "
                    "advancing in two concurrent section visits."
                )
            self._visit_owner = visit_id
        self._frame_count += 1
        for attr_name, _ in self._iter_effects():
            self._effect_frames[attr_name] = self._effect_frames.get(attr_name, 0) + 1

    def pause_frame(self) -> None:
        """Stop advancing the frame counters — used by `run_transition`
        so an outgoing widget mid-typewriter (etc.) doesn't keep
        ticking while it's only being re-rendered for compositing.

        Also FREEZES inline-value-token resolution (`_resolution_locked`)
        so the 1 Hz source ticker can't change a participating widget's
        content width while it is being composited for a transition
        (the C1 hole). Rides the existing pause/resume seam — no new
        call sites in `run_transition` / `_scroll_between`."""
        self._frame_paused = True
        self._resolution_locked = True

    def resume_frame(self) -> None:
        self._frame_paused = False
        self._resolution_locked = False

    def reset_frame(self) -> None:
        """Visit-entry reset. The primary counter always resets;
        per-effect counters reset only for effects that opted in
        via `restart_on_visit = True` (the default). Effects with
        `restart_on_visit = False` keep their counter — that's what
        gives `RainbowChaseBorder` continuous phase across loop_count
        boundaries while still letting `Typewriter` retype.

        Clears the visit ownership claim so a new visit_id can take over.

        Does NOT clear the pause flag — pause/resume are
        transition-scoped, reset is visit-scoped, the two are
        independent."""
        self._frame_count = 0
        self._visit_owner = None
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

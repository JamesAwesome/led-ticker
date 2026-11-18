"""`random` / `auto`: pick one child transition per firing from a pool.

Design: ``docs/superpowers/specs/2026-11-17-random-transition-design.md``.

The wrapper holds PRE-BUILT children (the factory builds them once per
wrapper instance, never here) and ``_current``, the index of the child the
NEXT firing will run. ``run_transition`` reads ``min_frames``,
``scale_switch_at`` and ``duration_override`` ONCE before its frame loop, so
the pick must already be made by then: it is chosen at construction and
re-chosen by :meth:`end_firing`, which the runner calls once per firing in
its ``finally``. ``frame_at`` is pure delegation. The pick is deliberately
NOT keyed on ``t`` (``t >= 1.0`` / ``t == 0.0`` rules): plugin easings join
the same ``EASING`` table and their endpoints are not guaranteed.

A caller that drives ``frame_at`` itself, outside ``run_transition``, must
call ``end_firing()`` when its firing ends or the same child replays.

Scope of "never back-to-back": per wrapper INSTANCE and by pool INDEX. A
section's entry and widget slots are separate instances (``_cached_trans_obj``),
``between_sections`` is a third, and two entries of the same type with
different knobs are distinct members.
"""

import logging
import random
from typing import Any

from led_ticker.transitions import (
    DEFAULT_SCALE_SWITCH_AT,
    Transition,
    list_transition_names,
    register_transition,
)

logger = logging.getLogger(__name__)

# Never pool members: `cut` (no-op), `scroll` (type-dispatched to
# `_scroll_between`, bypasses the runner), the two meta types (no nesting) and
# the four core variant wrappers (they pick inside `frame_at` on the older
# `t`-keyed rule and add nothing a pool does not).
HARD_EXCLUDED: frozenset[str] = frozenset(
    {
        "cut",
        "scroll",
        "random",
        "auto",
        "push_random",
        "push_alternating",
        "wipe_random",
        "wipe_alternating",
    }
)


def default_pool_names() -> list[str]:
    """Every registered NON-dotted (core) transition minus `HARD_EXCLUDED`,
    sorted. Grows automatically with new core transitions; plugin (dotted)
    transitions join only through an explicit `pool`."""
    return sorted(
        n for n in list_transition_names() if "." not in n and n not in HARD_EXCLUDED
    )


class _PickAhead:
    """Base for the pick-per-firing wrappers. Subclasses define `_first()`
    and `_advance()`; everything else is shared."""

    def __init__(
        self,
        children: list[Any],
        durations: list[float | None],
        names: list[str],
        *,
        rng: random.Random | None = None,
    ) -> None:
        if len(children) < 2:
            raise ValueError(
                f"random/auto pool needs at least 2 members; got {len(children)}"
            )
        if not (len(children) == len(durations) == len(names)):
            raise ValueError(
                "random/auto pool: children, durations and names must have the "
                f"same length; got {len(children)}, {len(durations)}, {len(names)}"
            )
        self._children = children
        self._durations = durations
        self._names = names
        self._rng = rng or random.Random()
        self._tag = f"{id(self) & 0xFFFF:04x}"
        self._current = self._first()
        self._log_pick()

    # -- the one-time runner reads -------------------------------------------

    @property
    def min_frames(self) -> int:
        return getattr(
            self._children[self._current], "min_frames", Transition.min_frames
        )

    @property
    def scale_switch_at(self) -> float:
        return getattr(
            self._children[self._current], "scale_switch_at", DEFAULT_SCALE_SWITCH_AT
        )

    @property
    def duration_override(self) -> float | None:
        return self._durations[self._current]

    @property
    def current_index(self) -> int:
        return self._current

    @property
    def current_name(self) -> str:
        return self._names[self._current]

    # -- firing ---------------------------------------------------------------

    def frame_at(
        self, t: float, canvas: Any, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Any:
        return self._children[self._current].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )

    def end_firing(self) -> None:
        """Called by `run_transition` once per firing (in its `finally`): pick
        the child the NEXT firing runs, ahead of the runner's reads."""
        self._current = self._advance()
        self._log_pick()

    def _first(self) -> int:  # pragma: no cover - overridden
        raise NotImplementedError

    def _advance(self) -> int:  # pragma: no cover - overridden
        raise NotImplementedError

    def _log_pick(self) -> None:
        d = self._durations[self._current]
        logger.debug(
            "transition %s[%s]: next = %s (index %d, duration %s)",
            type(self).KIND,
            self._tag,
            self._names[self._current],
            self._current,
            "section" if d is None else f"{d:.2f}s",
        )

    KIND: str = "meta"


@register_transition("random")
class RandomTransition(_PickAhead):
    """Uniform pick among the members, never the same INDEX twice in a row."""

    KIND = "random"

    def _first(self) -> int:
        return self._rng.randrange(len(self._children))

    def _advance(self) -> int:
        return self._rng.choice(
            [i for i in range(len(self._children)) if i != self._current]
        )


@register_transition("auto")
class AutoTransition(_PickAhead):
    """Cycle the members in pool order, starting at the first."""

    KIND = "auto"

    def _first(self) -> int:
        return 0

    def _advance(self) -> int:
        return (self._current + 1) % len(self._children)

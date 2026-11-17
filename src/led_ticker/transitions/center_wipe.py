"""Center wipes: erase-style sweeps whose fronts start or end at the panel center.

``wipe_in`` / ``wipe_in_vertical``: two sweep fronts start at the panel edges
and move toward the center, erasing the outgoing widget behind them (Alpha
"roll in from both sides", Huidu "close up and down").

``wipe_out`` / ``wipe_out_vertical``: a black band opens at the center and its
two fronts move toward the edges (Alpha "roll out from the middle", Huidu
"open from middle"). ``split`` is the fixed-magenta-edged twin of ``wipe_out``.

Same visual language as :mod:`led_ticker.transitions.wipe`: the outgoing is
drawn in place, black ``SubFill`` regions grow from the fronts, a colored sweep
line ``2 * scale`` thick sits on the KEPT side of each front, and ``t >= 1.0``
cuts to the incoming. All geometry is in PHYSICAL pixels via ``_phys`` so the
letterbox bands of a banded ``ScaledCanvas`` are erased too.

Odd-center rule: for an odd extent the single center pixel belongs to the
``out`` band from the first erasing frame, and the two ``in`` fronts merge
into one span once they meet, so the fronts can never leave a 1-px gap or
overlap. The front travel is capped (:func:`front_cap`) one step before the
fronts would swallow the whole axis, so the frame before the cut shows the
sweep color where they nearly meet rather than a black panel. Pinned by the
partition and cap tests in ``tests/test_center_wipe.py``.
"""

from typing import Any

from led_ticker._types import Canvas, ColorTuple
from led_ticker.transitions import _phys, register_transition
from led_ticker.transitions.wipe import _BaseWipe

Span = tuple[int, int]  # half-open [lo, hi) along the swept axis


def front_cap(n: int, inward: bool) -> int:
    """Largest front travel at which a 1-2 px sliver of the axis is still
    kept: ``(n - 1) // 2`` inward, ``n // 2 - 1`` outward.

    The fronts never swallow the whole axis. At the cap the kept sliver is
    entirely covered by the sweep lines, so the last frame before the cut is
    black + sweep color, never a fully black panel (cycle-1 review finding:
    with the cap at ``half`` the vertical variants spent the final third of
    an ``ease_out`` run on an all-black panel).
    """
    return (n - 1) // 2 if inward else n // 2 - 1


def progress_to_b(t: float, n: int, inward: bool) -> int:
    """Front travel in pixels for progress ``t`` over extent ``n``.

    Linear in ``t`` with a ``cap + 1`` multiplier so ``b == cap`` for any
    ``t`` close to 1.0: no outgoing pixel survives at ``t = 0.999``.
    """
    cap = front_cap(n, inward)
    if cap <= 0:
        return 0
    return min(int(t * (cap + 1)), cap)


def center_spans(n: int, b: int, inward: bool) -> tuple[list[Span], list[Span]]:
    """Return ``(erased, kept)`` half-open spans partitioning ``[0, n)``.

    ``b == 0`` erases nothing. Inward erases ``[0, b)`` and ``[n - b, n)``.
    Outward erases the center band ``[n // 2 - b, n // 2 + b + n % 2)``
    clamped to the panel. Total over ``b`` up to ``(n + 1) // 2`` for direct
    callers: the fully-erased results (``2 * b >= n`` inward, a full-width
    band outward) are never reached from ``frame_at``, which caps ``b`` at
    :func:`front_cap`.
    """
    if b <= 0 or n <= 0:
        return [], ([(0, n)] if n > 0 else [])
    if inward:
        if 2 * b >= n:
            return [(0, n)], []
        return [(0, b), (n - b, n)], [(b, n - b)]
    lo = max(0, n // 2 - b)
    hi = min(n, n // 2 + b + n % 2)
    kept = [s for s in ((0, lo), (hi, n)) if s[1] > s[0]]
    return [(lo, hi)], kept


def sweep_line_spans(n: int, b: int, inward: bool, thick: int) -> list[Span]:
    """Spans of the colored sweep lines: up to ``thick`` pixels of each kept
    span adjacent to an erased edge, never overlapping an erased span.

    At ``b == 0`` (nothing erased yet) the lines sit where the fronts will
    start. Empty when nothing is kept, which only direct callers past
    :func:`front_cap` can produce.
    """
    if thick <= 0 or n <= 0:
        return []
    erased, kept = center_spans(n, b, inward)
    if not erased:
        # Frame 0: nothing erased yet; show the lines where the fronts will
        # start (edges for inward, center for outward), like wipe_left/right/
        # up/down show their line at the edge on frame 0.
        thick = min(thick, n)
        if inward:
            spans = [(0, thick), (n - thick, n)]
            return [(0, n)] if 2 * thick >= n else spans
        c = n // 2
        return [(max(0, c - thick), min(n, c + thick))]
    if not kept:
        return []
    lines: list[Span] = []
    for lo, hi in kept:
        # The kept span touches an erased edge on the left when lo > 0 and
        # on the right when hi < n (the kept span is bounded by an erased
        # span on that side, since erased ∪ kept == [0, n)).
        if lo > 0:
            lines.append((lo, min(hi, lo + thick)))
        if hi < n:
            lines.append((max(lo, hi - thick), hi))
    # Merge overlapping line spans inside a very narrow kept span.
    lines.sort()
    merged: list[Span] = []
    for lo, hi in lines:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


class _CenterWipe(_BaseWipe):
    """Shared frame logic for the four center wipes. Not registered.

    Subclasses set ``AXIS`` (``"x"`` sweeps columns, ``"y"`` sweeps rows),
    ``INWARD`` (fronts move toward the center when true), ``DEFAULT_COLOR``
    and ``min_frames``.
    """

    AXIS: str = "x"
    INWARD: bool = True

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        real, rw, rh, scale, _yo = _phys(canvas)
        outgoing_scroll_pos: int = kwargs.get("outgoing_scroll_pos", 0)

        if t >= 1.0:
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        outgoing.draw(canvas, cursor_pos=outgoing_scroll_pos)

        along_x = self.AXIS == "x"
        n = rw if along_x else rh
        b = progress_to_b(t, n, self.INWARD)
        erased, _kept = center_spans(n, b, self.INWARD)

        # Black out the erased spans across the FULL physical cross extent so
        # letterbox bands on banded wrappers are cleared too.
        for lo, hi in erased:
            if along_x:
                real.SubFill(lo, 0, hi - lo, rh, 0, 0, 0)
            else:
                real.SubFill(0, lo, rw, hi - lo, 0, 0, 0)

        # Sweep lines (2 * scale thick) on the kept side of each front. Each
        # line is a full-cross-extent rectangle: one SubFill per span, not a
        # per-pixel loop (cycle-2 review: 4096 SetPixel/frame at scale 4).
        r, g, bl = self.color
        for lo, hi in sweep_line_spans(n, b, self.INWARD, 2 * scale):
            if along_x:
                real.SubFill(lo, 0, hi - lo, rh, r, g, bl)
            else:
                real.SubFill(0, lo, rw, hi - lo, r, g, bl)
        return canvas


@register_transition("wipe_in")
class WipeIn(_CenterWipe):
    """Both side edges sweep toward the center column (Alpha roll-in geometry)."""

    AXIS = "x"
    INWARD = True
    DEFAULT_COLOR: ColorTuple = (255, 255, 0)
    min_frames: int = 20


@register_transition("wipe_out")
class WipeOut(_CenterWipe):
    """A band opens at the center column and sweeps to both side edges
    (Alpha roll-out geometry; ``split`` is its fixed-magenta twin)."""

    AXIS = "x"
    INWARD = False
    DEFAULT_COLOR: ColorTuple = (255, 0, 0)
    min_frames: int = 20


@register_transition("wipe_in_vertical")
class WipeInVertical(_CenterWipe):
    """Top and bottom edges sweep toward the center row (Huidu "close up and down")."""

    AXIS = "y"
    INWARD = True
    DEFAULT_COLOR: ColorTuple = (255, 255, 0)
    min_frames: int = 16


@register_transition("wipe_out_vertical")
class WipeOutVertical(_CenterWipe):
    """A band opens at the center row and sweeps to top and bottom
    (Huidu "vertically open from middle")."""

    AXIS = "y"
    INWARD = False
    DEFAULT_COLOR: ColorTuple = (255, 0, 0)
    min_frames: int = 16

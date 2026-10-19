"""Animations — frame-aware position/visibility behaviors for
TickerMessage.

Replaces the legacy `WidgetPresenter`-wrapped Typewriter with a
widget-level animation instance bound to TickerMessage's `animation`
field. Each tick TickerMessage asks the animation for an
`AnimationFrame` describing what to render this frame.

Color providers are orthogonal — animations control position and
visibility, providers control color. The two compose freely.
"""

import dataclasses
import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from led_ticker.constants import ENGINE_TICK_MS

_LENS_PROFILES = ("cosine",)


@dataclasses.dataclass(frozen=True)
class LensSpec:
    """Stationary fisheye-lens descriptor for scroll animations.

    magnify:      Vertical + horizontal scale factor at the panel center
                  (> 1 → bulge; == edge_squeeze → degenerate flat lens).
    edge_squeeze: Scale factor at the panel edges. Must be > 0 and <=
                  magnify (edge scale never exceeds center scale).
    profile:      Falloff curve from center to edge. Currently "cosine"
                  only; a "spherical" slot is reserved for a future phase.

    Frozen + hashable: safe as a @functools.cache key in build_lens_maps.
    """

    magnify: float = 1.3
    edge_squeeze: float = 0.6
    profile: str = "cosine"

    def __post_init__(self) -> None:
        if not isinstance(self.magnify, (int, float)) or isinstance(self.magnify, bool):
            raise ValueError(f"magnify must be a number; got {self.magnify!r}")
        if not isinstance(self.edge_squeeze, (int, float)) or isinstance(
            self.edge_squeeze, bool
        ):
            raise ValueError(
                f"edge_squeeze must be a number; got {self.edge_squeeze!r}"
            )
        if self.edge_squeeze <= 0:
            raise ValueError(f"edge_squeeze must be > 0; got {self.edge_squeeze}")
        if self.magnify < self.edge_squeeze:
            raise ValueError("magnify must be >= edge_squeeze")
        if self.profile not in _LENS_PROFILES:
            raise ValueError(
                f"profile must be one of {_LENS_PROFILES}; got {self.profile!r}"
            )


@dataclass
class AnimationFrame:
    """What the widget should render at the current frame.

    visible_text: The slice (or full text) to draw. Typewriter returns
                  growing prefixes.
    rotation:     In-plane rotation of the rendered text in degrees,
                  clockwise-positive. 0.0 (the default) means no rotation
                  and takes the widget's normal draw path. Non-zero routes
                  the text through an offscreen buffer + rotate_blit
                  (see led_ticker.rotate). Emitted by rotation-capable
                  animations (e.g. the flair plugin's propeller).
    lens:         A :class:`LensSpec` describing a stationary fisheye lens
                  centered on the panel. ``None`` (the default) skips the
                  lens branch entirely and preserves every existing draw path
                  unchanged. When set, the text buffer is rendered fresh
                  each tick (keeping colors live) and blitted through the
                  lens maps via ``lens_blit`` (see led_ticker.rotate).
                  Emitted by lens-capable animations (e.g. the flair plugin's
                  fisheye). Duck-typed marker for validate rule 64:
                  ``emits_lens = True`` on the animation class.
    """

    visible_text: str
    rotation: float = 0.0
    lens: LensSpec | None = None


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
    transition doesn't chop the animation mid-flight. ``total_chars`` is
    whatever :func:`animation_total_chars` reports for the text — raw
    ``len`` unless the animation defines ``count_units(text)``.

    See ``Typewriter`` for the canonical implementation.

    Rotation-capable animations set ``rotation`` (degrees, clockwise-
    positive) on the frames they return, and declare the class attribute
    ``emits_rotation = True`` — a duck-typed marker validate rule 63
    reads to warn about hires-font widgets (whose text cannot rotate
    until physical-resolution rotation ships). Animations without the
    attribute never rotate.

    Lens-capable animations set ``lens`` on the frames they return (a
    :class:`LensSpec` describing the stationary fisheye lens), and declare
    the class attribute ``emits_lens = True`` — a duck-typed marker
    validate rule 64 reads to warn about hires-font widgets at scale 1
    (the unwarped fallback; same policy as rule 63). Animations without
    the attribute never activate the lens branch.
    """

    def frame_for(
        self,
        frame: int,
        full_text: str,
        canvas_width: int,
        text_width: int,
    ) -> AnimationFrame: ...


def _reveal_unit_ends(text: str, inline_emoji: bool = True) -> list[int]:
    """Raw end offset of each typewriter reveal unit in ``text``.

    A unit is one plain character, one renderable ``:slug:`` token, or
    one Unicode-emoji run — so ``text[:ends[k]]`` never splits a token
    the renderer would draw as a sprite (a half-typed ``:jack_o_lan``
    renders as literal text, then snaps to the sprite on the closing
    colon). Segmentation is ``_parse_segments`` — the renderer's own
    gate — so an UNrenderable ``:nope:`` stays per-char, typing the
    same literal text it draws. Falls back to per-char if the segments
    ever stop reassembling to ``text`` (never a mis-slice).

    ``inline_emoji=False`` is the widget saying its draw path renders this
    text as LITERAL characters (message / image single-row gate on the raw
    template, so a token value that looks like a slug draws literally) —
    then every character is its own unit."""
    if not inline_emoji:
        return list(range(1, len(text) + 1))
    from led_ticker.pixel_emoji import _parse_segments  # noqa: PLC0415

    ends: list[int] = []
    pos = 0
    for seg_type, value in _parse_segments(text):
        if seg_type == "text":
            ends.extend(range(pos + 1, pos + len(value) + 1))
            pos += len(value)
        else:
            raw_len = len(value) + 2 if seg_type == "emoji" else len(value)
            pos += raw_len
            ends.append(pos)
    if pos != len(text):
        return list(range(1, len(text) + 1))
    return ends


def animation_total_chars(
    animation: object, text: str, *, inline_emoji: bool = True
) -> int:
    """The ``total_chars`` to feed ``animation.frames_to_rest`` for
    ``text``: the animation's own ``count_units(text)`` when it defines
    one (Typewriter: emoji count as ONE), else raw ``len(text)``. The
    ONE home of this choice — the widget settle counts and validate
    rules 61/62 all route through it so they can't drift from the reveal.
    ``inline_emoji`` is the widget's draw-path emoji gate (see
    :func:`animation_frame`); only Typewriter consumes it."""
    if isinstance(animation, Typewriter):
        return animation.count_units(text, inline_emoji=inline_emoji)
    count = getattr(animation, "count_units", None)
    if count is None:
        return len(text)
    return int(count(text))


def animation_frame(
    animation: Animation,
    frame: int,
    full_text: str,
    canvas_width: int,
    text_width: int,
    *,
    inline_emoji: bool,
) -> AnimationFrame:
    """Call ``animation.frame_for`` from a widget, forwarding the widget's
    draw-path emoji gate to Typewriter (whose reveal units must match
    what the widget actually draws). Other animations get the plain
    protocol call — ``inline_emoji`` is not part of the protocol."""
    if isinstance(animation, Typewriter):
        return animation.frame_for(
            frame, full_text, canvas_width, text_width, inline_emoji=inline_emoji
        )
    return animation.frame_for(frame, full_text, canvas_width, text_width)


class Typewriter:
    """Slice grows one reveal unit per `frames_per_char` frames.

    A unit is a character, or a whole renderable emoji (``:slug:`` or a
    Unicode-emoji run) — an emoji types in as a single keystroke.

    At the default ENGINE_TICK_MS=50ms, frames_per_char=3 means each
    char is on screen for ~150ms (~7 chars/sec) — fast enough to feel
    snappy, slow enough to read the typing.
    """

    def __init__(self, chars_per_frame: int = 1, frames_per_char: int = 3) -> None:
        # A non-positive step mis-slices (IndexError in draw) or divides
        # by zero in frames_to_rest — reject at construction, which is
        # config-load for TOML.
        for name, value in (
            ("chars_per_frame", chars_per_frame),
            ("frames_per_char", frames_per_char),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(
                    f"typewriter {name} must be a positive integer; got {value!r}"
                )
        self.chars_per_frame = chars_per_frame
        self.frames_per_char = frames_per_char

    def frame_for(
        self,
        frame: int,
        full_text: str,
        canvas_width: int,
        text_width: int,
        *,
        inline_emoji: bool = True,
    ) -> AnimationFrame:
        # Effective progress: each frames_per_char ticks advances by
        # chars_per_frame characters. With defaults (1, 3): advance 1
        # char every 3 frames.
        ends = _reveal_unit_ends(full_text, inline_emoji)
        if not ends:
            return AnimationFrame(visible_text=full_text)
        progress = (frame // self.frames_per_char) + 1
        units_visible = min(len(ends), progress * self.chars_per_frame)
        return AnimationFrame(visible_text=full_text[: ends[units_visible - 1]])

    def count_units(self, text: str, *, inline_emoji: bool = True) -> int:
        """Reveal units in ``text`` — the count ``frames_to_rest`` /
        ``typing_duration_seconds`` take (call via
        :func:`animation_total_chars`)."""
        return len(_reveal_unit_ends(text, inline_emoji))

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        """Frames until the reveal completes (one-shot rest: 0 forever
        once fully typed).

        total_chars MUST be ``count_units(full_text)`` (via
        :func:`animation_total_chars`) — the unit count ``frame_for``
        steps through, where each renderable emoji is ONE unit. Neither
        raw ``len`` (over-counts slug characters → reports mid-type long
        after the reveal finished) nor the emoji-EXCLUDED
        ``count_text_chars`` (a color-provider quantity; under-counts →
        reports done mid-type) is right.
        """
        if total_chars <= 0:
            return 0
        done_frame = self.frames_per_char * (
            math.ceil(total_chars / self.chars_per_frame) - 1
        )
        return max(0, done_frame - frame)

    def typing_duration_seconds(self, total_chars: int) -> float:
        """Wall-clock seconds to fully reveal ``total_chars`` units
        (``count_units``) at engine cadence. The ONLY home of the typing-
        duration formula — validate rule 61 imports and calls this;
        it must never re-implement the math."""
        return self.frames_to_rest(0, total_chars) * ENGINE_TICK_MS / 1000.0


_ANIMATION_REGISTRY: dict[str, type] = {
    "typewriter": Typewriter,
}

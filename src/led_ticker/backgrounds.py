"""Background effects — full-panel animations painted BEHIND a widget's content.

Sibling of `borders.py` with the same shape (``paint(canvas, frame_count)`` +
a ``frame_invariant`` flag) but a different z-order: a host widget paints its
``background`` first, then its ``border``, then its text (image widgets paint
the background under the image, so it shows through transparent / skipped-
black regions and is hidden behind an opaque image). Having two slots is the
whole point — a rainbow ``border`` ring and a fireworks ``background`` can
run on the same widget.

Core ships NO built-in styles: ``_BACKGROUND_REGISTRY`` starts empty and is
populated by plugins via ``api.background(name)`` (committed by the loader
under ``namespace.name``). Config: ``background = "flair.fireworks"`` or
``background = {style = "flair.fireworks", ...kwargs}``.

Contract (mirrors ``BorderEffect``, see that module for the rationale):

- ``paint`` is called every render tick with the host's per-effect counter
  ``frame_for("background")`` — transitions pause it, visit resets honor
  ``restart_on_visit``. Paint MUST be a pure function of ``(canvas dims,
  frame_count)`` per instance: transitions re-render the host repeatedly at
  the same paused frame while compositing.
- ``frame_invariant`` gates the image widgets' static fast path exactly like
  ``border.frame_invariant`` does (``False`` = force per-tick redraws).
- Paint at physical resolution via ``unwrap_to_real`` when the effect wants
  LED-grain output on a scaled sign.
- Never raise from ``paint`` — it runs inside the render loop.
- Prefer not to paint pure black: a background sits on top of the host's
  ``bg_color`` fill and under its image; black writes erase those.
"""

from typing import Protocol

from led_ticker._types import Canvas


class BackgroundEffectBase:
    """Optional base for BackgroundEffect implementations.

    Enforces that every subclass declares ``frame_invariant`` explicitly
    (class attribute or ``@property``) so the image widgets' fast-path
    predicate cannot silently freeze an animated background — same rule
    as ``BorderEffectBase`` / ``ColorProviderBase``.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "frame_invariant" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must define 'frame_invariant' as a class "
                "attribute or property. Set True if paint() output is "
                "frame-independent; False if it varies per frame."
            )


class BackgroundEffect(Protocol):
    """Paints a full-panel background on `canvas` at frame-aware state."""

    @property
    def frame_invariant(self) -> bool: ...

    def paint(self, canvas: Canvas, frame_count: int) -> None: ...


# Plugin-populated: ``api.background(name)`` → ``"<namespace>.<name>"`` → class.
# Deliberately empty in core (no built-in styles yet).
_BACKGROUND_REGISTRY: dict[str, type] = {}

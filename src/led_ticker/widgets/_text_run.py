"""Shared three-branch text-run draw dispatch.

`draw_text_run` is the single implementation of the emoji / per-char /
whole-string draw dispatch that renders a run of text with an optional
per-char color override (a colored value token). It was extracted VERBATIM
from `TickerMessage.draw`'s three inline branches so that `two_row` and the
image text overlay can adopt the SAME logic in Phase 2 and can't drift from
message's subtle per-char override semantics.

The three branches (identical to message's reference behavior):

- ``has_emoji`` — draw through :func:`pixel_emoji.draw_with_emoji`, forwarding
  an ``color_override`` callable that returns ``override[i]`` (possibly
  ``None`` ⇒ defer to the host provider) in ``draw_with_emoji``'s
  emoji-EXCLUDING char space.
- ``provider.per_char`` (rainbow/gradient) and NOT ``has_emoji`` — draw
  through :func:`text_render.draw_text_per_char` with an override-aware
  callback (``override[idx]`` when set-and-non-None, else
  ``provider.color_for(frame, idx, total)``).
- else (whole-string / constant host) — when an override is present, FORCE
  the per-char path so the override can win on individual chars while literals
  keep the host constant; otherwise the plain ``draw_text`` fast path.

``total_chars`` is threaded EXPLICITLY so the caller controls the per-char /
emoji-excluding count anchor (message anchors to the FULL text so a typewriter
mid-reveal doesn't shift each char's hue). When ``None`` the helper falls back
to a ``visible_text``-derived count that matches each branch: emoji uses
:func:`pixel_emoji.count_text_chars` (emoji-excluding), per-char uses ``len``.

No ``from __future__ import annotations`` (PEP 649 / project rule). Imports are
core-internal only (``pixel_emoji`` + ``text_render``, neither of which imports
the widgets package at module scope) so this module is cycle-free.
"""

from typing import Any

from led_ticker._types import Canvas, Font
from led_ticker.color_providers import ColorProvider
from led_ticker.pixel_emoji import count_text_chars, draw_with_emoji
from led_ticker.text_render import draw_text, draw_text_per_char


def draw_text_run(
    canvas: Canvas,
    font: Font,
    x: int,
    baseline_y: int,
    provider: ColorProvider,
    visible_text: str,
    frame: int,
    *,
    override: list[Any] | None = None,
    has_emoji: bool,
    total_chars: int | None = None,
    y_offset: int = 0,
    emoji_y: int | None = None,
    max_emoji_height: int | None = None,
    hires_downscale: float = 1.0,
) -> int:
    """Draw ``visible_text`` at ``x`` through the three-branch dispatch.

    Returns the cursor advance in logical pixels (what the caller adds to
    ``cursor_pos``).

    ``override`` is a per-char list of ``Color``-or-``None`` aligned to the
    DRAW PATH's char space (emoji-excluding when the emoji branch renders
    sprites). ``None`` entries defer to ``provider``. ``None`` for the whole
    argument means "no colored token" — the branches are byte-identical to the
    pre-override paths.

    ``emoji_y`` / ``max_emoji_height`` are forwarded to ``draw_with_emoji``
    ONLY when not ``None`` (message does not supply them; two_row / image do,
    for per-row band placement). ``hires_downscale`` (default ``1.0`` = no
    change) is forwarded to ``draw_with_emoji`` in the emoji branch only —
    the image single-row overlay and message's fisheye lens box-downsample
    hi-res sprites; the plain-text branches do not take it.
    """
    if has_emoji:
        total = (
            total_chars if total_chars is not None else count_text_chars(visible_text)
        )
        # The emoji override callable indexes `draw_with_emoji`'s
        # emoji-EXCLUDING char space and returns override[i] directly —
        # possibly None, which `draw_with_emoji` reads as "defer to the
        # provider". (Matches message: no `is not None` element guard here.)
        emoji_override = (
            (lambda i, _ov=override: _ov[i] if i < len(_ov) else None)
            if override is not None
            else None
        )
        emoji_kwargs: dict[str, Any] = {}
        if emoji_y is not None:
            emoji_kwargs["emoji_y"] = emoji_y
        if max_emoji_height is not None:
            emoji_kwargs["max_emoji_height"] = max_emoji_height
        return draw_with_emoji(
            canvas,
            font,
            x,
            baseline_y,
            provider,
            visible_text,
            y_offset=y_offset,
            frame=frame,
            total_chars=total,
            color_override=emoji_override,
            hires_downscale=hires_downscale,
            **emoji_kwargs,
        )

    if provider.per_char:
        total = total_chars if total_chars is not None else len(visible_text)

        def _per_char_color(
            idx: int,
            total_: int,
            _ov: list[Any] | None = override,
            _p: ColorProvider = provider,
            _f: int = frame,
        ) -> Any:
            if _ov is not None and idx < len(_ov) and _ov[idx] is not None:
                return _ov[idx]
            return _p.color_for(_f, idx, total_)

        return draw_text_per_char(
            canvas,
            font,
            x,
            baseline_y + y_offset,
            visible_text,
            _per_char_color,
            total_chars=total,
        )

    # Whole-string / constant host color.
    if override is not None:
        # A colored token forces the per-char path even for a whole-string /
        # constant host color so the override can win on individual chars;
        # literal chars keep the host constant. Geometry is unchanged (BDF
        # per-char advance sums to the whole-string advance; hires
        # ceil-divides once). host_const anchors to len(visible_text) — the
        # whole-string color of the CURRENTLY drawn run (matches message).
        total = total_chars if total_chars is not None else len(visible_text)
        host_const = provider.color_for(frame, 0, len(visible_text))

        def _ws_color(
            idx: int,
            total_: int,
            _ov: list[Any] = override,
            _h: Any = host_const,
        ) -> Any:
            if idx < len(_ov) and _ov[idx] is not None:
                return _ov[idx]
            return _h

        return draw_text_per_char(
            canvas,
            font,
            x,
            baseline_y + y_offset,
            visible_text,
            _ws_color,
            total_chars=total,
        )

    color = provider.color_for(frame, 0, len(visible_text))
    return draw_text(canvas, font, x, baseline_y + y_offset, color, visible_text)

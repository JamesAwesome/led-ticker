"""Shared base for image-display widgets (gif, still).

Both `GifPlayer` and `StillImage` subclass `_BaseImageWidget` to inherit
the text-overlay surface (fields + validation + render helpers) plus
the per-tick scroll loop. Subclasses provide:

  - `_paint_full(canvas)` — paint the current image/frame
  - `_paint_skip_black(canvas)` — paint non-black pixels only (skip-black
    compositing for the scroll-under text path)
  - `_load(panel_w, panel_h)` — decode the underlying source
  - `_pick_frame_for_elapsed(elapsed_ms)` — advance per-frame state
    (default no-op for single-frame stills)

Subclasses also add their own type-specific fields (`path`, `fit`,
`image_align`, plus `gif_loops` / `hold_seconds` for per-visit
duration).
"""

from __future__ import annotations

import asyncio
import re
import warnings
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, Font
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.text_render import draw_text
from led_ticker.widgets._image_fit import VALID_GIF_ALIGNS, validate_choice

VALID_TEXT_ALIGNS: frozenset[str] = frozenset(
    {"left", "right", "scroll", "scroll_over"}
)
VALID_TEXT_VALIGNS: frozenset[str] = frozenset({"top", "center", "bottom"})
VALID_SCROLL_DIRECTIONS: frozenset[str] = frozenset({"left", "right"})

# `text_align="auto"` resolves to the side opposite the image so they don't
# overlap. Centered image → scroll_over (always paints over, no overlap).
AUTO_TEXT_ALIGN_FOR_IMAGE: dict[str, str] = {
    "left": "right",
    "right": "left",
    "center": "scroll_over",
}
EMOJI_PATTERN = re.compile(r":[a-z_]+:")

TEXT_EDGE_PADDING_PX: int = 2
MIN_SCROLL_SPEED_MS: int = 20
HOLD_SECONDS_FLOOR: float = 0.05


@attrs.define
class _BaseImageWidget:
    """Shared text-overlay state + render helpers for image widgets."""

    # All fields kw_only so subclasses can declare their own required
    # positional/keyword fields freely (esp. `path`).
    text: str = attrs.field(default="", kw_only=True)
    text_align: str = attrs.field(default="auto", kw_only=True)
    text_valign: str = attrs.field(default="center", kw_only=True)
    text_y_offset: int = attrs.field(default=0, kw_only=True)
    text_x_offset: int = attrs.field(default=0, kw_only=True)
    scroll_direction: str = attrs.field(default="left", kw_only=True)
    font_color: Color = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR), kw_only=True
    )
    scroll_speed_ms: int = attrs.field(default=50, kw_only=True)
    text_scale: int = attrs.field(default=1, kw_only=True)
    text_loops: int = attrs.field(default=0, kw_only=True)

    # Framework-internal — not user-facing TOML.
    font: Font = attrs.field(init=False, default=FONT_DEFAULT)
    padding: int = attrs.field(init=False, default=0)

    # Panel dims; set by subclass `_load()`.
    _panel_w: int = attrs.field(init=False, default=0)
    _panel_h: int = attrs.field(init=False, default=0)

    # ------------------------------------------------------------------
    # Subclass hooks — must be implemented by subclasses
    # ------------------------------------------------------------------

    def _paint_full(self, canvas: Canvas) -> None:
        raise NotImplementedError

    def _paint_skip_black(self, canvas: Canvas) -> None:
        raise NotImplementedError

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        raise NotImplementedError

    def _pick_frame_for_elapsed(self, elapsed_ms: int) -> None:
        """Advance per-frame state. No-op for single-frame stills;
        gif overrides to update `_current_frame_idx`."""

    # ------------------------------------------------------------------
    # Shared validation — call from subclass __attrs_post_init__
    # ------------------------------------------------------------------

    def _validate_common(self, image_align: str, fit: str) -> None:
        """Validate the text-overlay fields + cross-field footguns.

        Subclasses pass their `image_align` and `fit` so we can catch
        combinations like `text_align="scroll"` + `fit="stretch"` that
        produce silent no-text rendering.
        """
        validate_choice("image_align", image_align, VALID_GIF_ALIGNS)
        # Resolve text_align="auto" based on image_align so text doesn't
        # overlap the image by default. Authors can pin any value.
        if self.text_align == "auto":
            self.text_align = AUTO_TEXT_ALIGN_FOR_IMAGE[image_align]
        # Always validate text_align even when text=""; an explicit bogus
        # value should still surface during config-load, not silently sit
        # there until someone adds text.
        validate_choice("text_align", self.text_align, VALID_TEXT_ALIGNS)
        validate_choice("text_valign", self.text_valign, VALID_TEXT_VALIGNS)
        validate_choice(
            "scroll_direction", self.scroll_direction, VALID_SCROLL_DIRECTIONS
        )
        if self.text_scale < 1:
            raise ValueError(f"text_scale must be >= 1, got {self.text_scale!r}")
        if self.text_loops < 0:
            raise ValueError(f"text_loops must be >= 0, got {self.text_loops!r}")
        if self.scroll_speed_ms < MIN_SCROLL_SPEED_MS:
            raise ValueError(
                f"scroll_speed_ms must be >= {MIN_SCROLL_SPEED_MS}, "
                f"got {self.scroll_speed_ms!r}"
            )
        # Footgun: text_loops > 0 with static alignment is a silent no-op
        # in the per-tick loop (the floor formula gates on `scrolling`).
        if self.text_loops > 0 and self.text_align in ("left", "right"):
            raise ValueError(
                f"text_loops > 0 only applies when text_align is 'scroll' "
                f"or 'scroll_over'; got text_align={self.text_align!r}"
            )
        # Footgun: text_x_offset is a static-text knob; for scrolling it
        # would just skew the trajectory by a constant — confusing.
        if self.text_x_offset != 0 and self.text_align in ("scroll", "scroll_over"):
            raise ValueError(
                f"text_x_offset is only meaningful for static text_align "
                f"(left/right); got text_align={self.text_align!r}"
            )
        # Footgun: text_align="scroll" + fit="stretch" → no transparent
        # regions for skip-black to expose, so text is invisible.
        if self.text and self.text_align == "scroll" and fit == "stretch":
            raise ValueError(
                "text_align='scroll' needs transparent / pillarbox regions "
                "to show through; got fit='stretch' (whole panel is opaque). "
                "Use text_align='scroll_over' for marquee on a fullscreen image."
            )

    # ------------------------------------------------------------------
    # Shared text-rendering helpers
    # ------------------------------------------------------------------

    def _baseline_y(self, h: int) -> int:
        """BDF baseline anchored per `text_valign`, plus `text_y_offset`.

        FONT_DEFAULT is 6×12 with 10 ascent + 2 descent. The valign
        modes give logical-pixel anchors; `text_y_offset` shifts further
        (negative=up, positive=down).
        """
        if self.text_valign == "top":
            base = 10
        elif self.text_valign == "bottom":
            base = h - 2
        else:  # "center"
            base = (h - 12) // 2 + 10
        return base + self.text_y_offset

    def _has_emoji(self) -> bool:
        return bool(EMOJI_PATTERN.search(self.text))

    def _measure_text(self, canvas: Canvas) -> int:
        if self._has_emoji():
            from led_ticker.pixel_emoji import measure_width

            return measure_width(self.font, self.text, canvas=canvas)
        return get_text_width(self.font, self.text, padding=0)

    def _draw_text(self, canvas: Canvas, x: int, baseline_y: int, color: Color) -> int:
        """Route to draw_with_emoji when text contains slugs; otherwise
        plain BDF rasterizer. Emoji's 8-px sprite is anchored so its
        bottom row sits on the text baseline (works for any valign/scale)."""
        if self._has_emoji():
            from led_ticker.pixel_emoji import draw_with_emoji

            return draw_with_emoji(
                canvas,
                self.font,
                x,
                baseline_y,
                color,
                self.text,
                emoji_y=baseline_y - 8,
            )
        return draw_text(canvas, self.font, x, baseline_y, color, self.text)

    def _render_tick(
        self,
        canvas: Canvas,
        text_canvas: Canvas,
        scroll_pos: int,
        baseline_y: int,
        text_x_left: int,
        text_x_right: int,
    ) -> None:
        """Compose one frame: clear + paint image + paint text in the
        right order for the current `text_align`."""
        canvas.Clear()

        if self.text_align == "scroll":
            self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
            self._paint_skip_black(canvas)
        elif self.text_align == "scroll_over":
            self._paint_full(canvas)
            self._draw_text(text_canvas, scroll_pos, baseline_y, self.font_color)
        else:
            self._paint_full(canvas)
            text_x = text_x_left if self.text_align == "left" else text_x_right
            self._draw_text(text_canvas, text_x, baseline_y, self.font_color)

    # ------------------------------------------------------------------
    # Shared text playback loop
    # ------------------------------------------------------------------

    async def _play_with_text(
        self,
        real_canvas: Canvas,
        frame: Any,
        n_ticks: int,
    ) -> Canvas:
        """Per-tick text scroll loop. Subclass computes `n_ticks` (gif:
        from sum(durations)*loops; still: from hold_seconds), then calls
        this. Single-frame stills inherit `_pick_frame_for_elapsed` as
        a no-op; gif overrides it to advance `_current_frame_idx` per
        tick from the elapsed time."""
        canvas = real_canvas

        # text_canvas content_height spans the full panel (`panel_h //
        # scale`) so text_valign references the panel edge, not a
        # letterboxed sub-region.
        text_canvas: Canvas = (
            ScaledCanvas(
                canvas,
                scale=self.text_scale,
                content_height=canvas.height // self.text_scale,
            )
            if self.text_scale > 1
            else canvas
        )
        text_w = text_canvas.width
        text_h = text_canvas.height
        baseline_y = self._baseline_y(text_h)

        tick_ms = max(MIN_SCROLL_SPEED_MS, self.scroll_speed_ms)
        tick_seconds = tick_ms / 1000

        text_width = self._measure_text(text_canvas)
        text_x_left = TEXT_EDGE_PADDING_PX + self.text_x_offset
        text_x_right = (
            max(
                TEXT_EDGE_PADDING_PX,
                text_w - text_width - TEXT_EDGE_PADDING_PX,
            )
            + self.text_x_offset
        )

        scrolling = self.text_align in ("scroll", "scroll_over")
        if not scrolling:
            scroll_pos = 0
            scroll_step = 0
        elif self.scroll_direction == "right":
            scroll_pos = -text_width
            scroll_step = 1
        else:  # "left"
            scroll_pos = text_w
            scroll_step = -1

        # Marquee-traversal floor extends n_ticks if needed.
        if scrolling and self.text_loops > 0:
            ticks_per_text_loop = text_w + text_width
            n_ticks = max(n_ticks, self.text_loops * ticks_per_text_loop)

        # Static-text fast path: image + text are constant across ticks,
        # so paint once and hold instead of redrawing N times.
        if not scrolling and self.text_loops == 0:
            self._render_tick(
                canvas,
                text_canvas,
                scroll_pos,
                baseline_y,
                text_x_left,
                text_x_right,
            )
            canvas = frame.matrix.SwapOnVSync(canvas)
            await asyncio.sleep(n_ticks * tick_seconds)
            return canvas

        text_is_wrapped = isinstance(text_canvas, ScaledCanvas)

        for tick in range(n_ticks):
            self._pick_frame_for_elapsed(tick * tick_ms)
            self._render_tick(
                canvas,
                text_canvas,
                scroll_pos,
                baseline_y,
                text_x_left,
                text_x_right,
            )
            canvas = frame.matrix.SwapOnVSync(canvas)
            # Follow the new back-buffer so next tick paints to the
            # correct canvas (CLAUDE.md hardware constraint #10).
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(tick_seconds)

            if scrolling:
                scroll_pos += scroll_step
                if scroll_step < 0 and scroll_pos + text_width <= 0:
                    scroll_pos = text_w
                elif scroll_step > 0 and scroll_pos >= text_w:
                    scroll_pos = -text_width

        return canvas


def warn_deprecated_gif_align() -> None:
    """One-shot warning that the `gif_align` config field is deprecated."""
    warnings.warn(
        "`gif_align` is deprecated; use `image_align` instead. "
        "`gif_align` will be removed in a future release.",
        DeprecationWarning,
        stacklevel=3,
    )

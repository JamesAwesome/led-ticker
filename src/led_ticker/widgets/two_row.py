"""Two-row widget for tall LED canvases (mainly the Pi 5 bigsign).

Renders TWO independent text strings on the same canvas:
- Top row stays at a fixed position (held)
- Bottom row scrolls left when its content overflows the canvas width

Best in `swap` mode: each `TwoRowMessage` is its own display unit. The
top-row string is meant for a stable identifier (handle, headline, brand
tag) and the bottom row for promotional copy that can be longer than
the canvas width.

Layout: by default the widget splits `canvas.height` 50/50 between top
and bottom; each row's baseline is centered within its band. Override
the split with `top_row_height = N` (logical rows) to give the bottom
a larger band for a bigger font:

  canvas.height = 16, top_row_height = None  →  top: 8 rows, bottom: 8 rows
  canvas.height = 16, top_row_height = 4     →  top: 4 rows, bottom: 12 rows
  canvas.height = 16, top_row_height = 6     →  top: 6 rows, bottom: 10 rows

The asymmetric mode is the path to "small tag on top + larger marquee
below" — pair `top_row_height = 4` with FONT_SMALL on top + Beloved
Sans Bold @ ~22 on the bottom row.

**Hard ceiling**: `canvas.height * scale ≤ panel_h_real`. On bigsign
(scale=4, panel=64 real rows) the cap is `content_height = 16`.
Higher values overflow the wrapper into negative `_y_offset`
territory; rows near the top/bottom logical edges clip silently.
This is most visible with hi-res `:instagram:` etc. emoji where 4-8
real px of the sprite get cut off at the panel edge. For per-row
breathing room, prefer `text_y_offset` on TickerMessage or a smaller
`font_size` instead of over-spec'ing `content_height`.

Caller controls per-row horizontal alignment via `top_align` and
`bottom_align` (`"left"`, `"center"`, `"right"`). Both default to
`"center"` for visual symmetry. The bottom row's alignment only takes
effect when the text fits without scrolling — if it overflows, the
framework scrolls it left regardless.

Inline emoji slugs (`:instagram:`, `:email:`, etc.) work in both rows.
"""

from __future__ import annotations

from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import get_text_width, safe_scale
from led_ticker.fonts import FONT_SMALL, font_line_height_logical
from led_ticker.pixel_emoji import EMOJI_PATTERN, draw_with_emoji, measure_width
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import _FrameAware
from led_ticker.widgets._image_fit import fill_band
from led_ticker.widgets._row_layout import (
    EMOJI_ROW_CAP,
    aligned_x,
    resolve_band_heights,
    row_layout,
)

# Layout primitives moved to `widgets/_row_layout.py` so the same
# helpers serve both this widget and the two-row text-overlay path
# on `_BaseImageWidget`. Re-bind aliases for back-compat with any
# tests that import the underscore names from this module.
_EMOJI_ROW_CAP = EMOJI_ROW_CAP
_row_layout = row_layout
_aligned_x = aligned_x


@register("two_row")
@attrs.define
class TwoRowMessage(_FrameAware):
    """Two-row display: held top, scrolling bottom."""

    top_text: str
    bottom_text: str
    font: Font = attrs.Factory(lambda: FONT_SMALL)
    # Per-row font overrides. Default `None` falls back to `font`, so
    # legacy configs that set only `font` keep working unchanged. Set
    # `top_font` and/or `bottom_font` in TOML for split fonts (e.g.
    # bold handle on top + lighter promo line below).
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    bottom_font: Font | None = attrs.field(default=None, kw_only=True)
    top_color: Color | ColorProvider = attrs.Factory(lambda: DEFAULT_COLOR)
    bottom_color: Color | ColorProvider = attrs.Factory(lambda: DEFAULT_COLOR)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    top_bg_color: Color | None = attrs.field(default=None, kw_only=True)
    bottom_bg_color: Color | None = attrs.field(default=None, kw_only=True)
    # Horizontal alignment per row: "left", "center", or "right". The
    # bottom row's alignment only matters when its text fits — when it
    # overflows, the framework scrolls it from cursor_pos regardless.
    top_align: str = "center"
    bottom_align: str = "center"
    padding: int = 6
    # Backwards-compat: top_center=True is the same as top_align="center".
    # If you set top_center=False, top_align="left" is used (legacy default).
    top_center: bool | None = None
    # Asymmetric row split. Default `None` means 50/50 — top and bottom
    # each get `canvas.height // 2` logical rows. Override with an int
    # to give the top a different (typically smaller) band so the
    # bottom can fit a larger font. E.g. `top_row_height = 4` on a
    # 16-row canvas leaves 12 rows for the bottom — enough room for
    # Beloved Sans Bold @ ~22 (line_height ~10 logical) on the bottom
    # row while the top stays compact for a 5×8 BDF tag.
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    # Per-row text and emoji nudges in logical rows. Default 0 keeps
    # them at their computed positions. Negative shifts up (text
    # ascender may clip the panel edge), positive shifts down
    # (descender may bleed into the next band's space). Set
    # text + emoji to the same value to shift the entire row
    # together, or use them independently to tune emoji-text vertical
    # alignment when the emoji sprite is taller than the band.
    top_text_y_offset: int = attrs.field(default=0, kw_only=True)
    bottom_text_y_offset: int = attrs.field(default=0, kw_only=True)
    top_emoji_y_offset: int = attrs.field(default=0, kw_only=True)
    bottom_emoji_y_offset: int = attrs.field(default=0, kw_only=True)

    # Optional perimeter border effect — same contract as
    # `TickerMessage.border` (see borders.py). Paints before either
    # row's text at PHYSICAL panel resolution (bypasses ScaledCanvas
    # block expansion via `unwrap_to_real`), so a 1-px border on
    # bigsign at scale=2 traces the actual 256x64 panel edge — not
    # the 128x32 logical canvas edge. Border frames the SIGN, text
    # floats inside. Reads its per-effect counter via
    # `frame_for("border")` for animation; transitions freeze the
    # chase via `pause_frame`.
    border: Any | None = attrs.field(default=None, kw_only=True)

    # Two-row wrap (v2). Applies to the bottom row only — top stays
    # held. When True, the bottom row chases itself continuously with
    # a separator between copies, regardless of whether bottom_text
    # fits the canvas. Engine cooperation: `wraps_forever` property
    # below tells ticker._swap_and_scroll to skip its cursor_pos-based
    # stop condition.
    bottom_text_wrap: bool = attrs.field(default=False, kw_only=True)
    bottom_text_separator: str | None = attrs.field(default=None, kw_only=True)
    bottom_text_separator_color: Any | None = attrs.field(default=None, kw_only=True)

    # Minimum wrap cycles the bottom row must complete before the section
    # can end. 0 (default) preserves today's behavior — engine timing is
    # controlled by section `hold_time` alone. > 0 raises the floor:
    # engine runs at least `bottom_text_loops × cycle_width` ticks
    # (one cycle = bottom_text + separator). Mirrors `text_loops` on
    # `_BaseImageWidget` two-row mode. Only meaningful when
    # `bottom_text_wrap = True`; rule 28 rejects otherwise.
    bottom_text_loops: int = attrs.field(default=0, kw_only=True)

    # Bottom-row scroll style enum. Default "marquee" preserves all
    # legacy behavior (held-when-fits + cursor-driven scroll-on-overflow,
    # or seamless tile when paired with bottom_text_wrap=True). Set
    # "scroll_through" to force a single-pass offscreen-to-offscreen
    # scroll on every visit — text starts at bottom_x = canvas.width
    # (fully off the right) and ends past bottom_x + bottom_width < 0
    # (fully off the left). bottom_align is ignored in scroll_through
    # mode. Mutually exclusive with bottom_text_wrap=True.
    bottom_text_scroll: str = attrs.field(default="marquee", kw_only=True)

    _top_width: int = attrs.field(init=False, default=-1)
    _bottom_width: int = attrs.field(init=False, default=-1)

    @property
    def wraps_forever(self) -> bool:
        """Engine cooperation signal: when True, ticker.py's
        _swap_and_scroll skips its cursor_pos-based stop condition
        and runs the widget's draw loop for hold_time instead.
        Bottom row in wrap mode is intrinsically continuous —
        only section duration / loop_count terminates it."""
        return self.bottom_text_wrap and bool(self.bottom_text)

    @property
    def forces_offscreen_scroll(self) -> bool:
        """Engine cooperation signal — parallel to `wraps_forever`. When
        True, `_swap_and_scroll` skips its pre/post-scroll holds and runs
        a single-pass loop that decrements `pos` from 0 down past
        `-(canvas.width + bottom_width)` — driving the bottom row from
        fully off the right to fully off the left."""
        return self.bottom_text_scroll == "scroll_through" and bool(self.bottom_text)

    def __attrs_post_init__(self) -> None:
        # Wrap raw Color → _ConstantColor for uniform provider dispatch in draw().
        if not hasattr(self.top_color, "color_for"):
            self.top_color = _ConstantColor(self.top_color)
        if not hasattr(self.bottom_color, "color_for"):
            self.bottom_color = _ConstantColor(self.bottom_color)
        if self.top_center is not None:
            # `top_center` is a backwards-compat alias for `top_align`. Old
            # configs used `top_center=True/False` before `top_align` existed.
            # Warn so existing setups still work but the canonical knob
            # surfaces. When both are set, `top_center` silently overrides
            # `top_align` — preserving prior behavior, but the warning
            # makes the override visible.
            import warnings

            warnings.warn(
                "TwoRowMessage `top_center` is deprecated; use "
                "`top_align='center'` (or 'left'). For now `top_center` "
                "still overrides `top_align` if both are set.",
                DeprecationWarning,
                stacklevel=2,
            )
            if self.top_center is False:
                self.top_align = "left"
            elif self.top_center is True:
                self.top_align = "center"
        if self.top_row_height is not None and self.top_row_height <= 0:
            raise ValueError(
                f"top_row_height must be > 0; got {self.top_row_height!r}. "
                f"Drop the field or set None to use the default 50/50 split."
            )

        if self.bottom_text_wrap and not self.bottom_text:
            raise ValueError("bottom_text_wrap=True requires non-empty bottom_text.")
        if self.bottom_text_separator is not None and not self.bottom_text_wrap:
            raise ValueError(
                f"bottom_text_separator={self.bottom_text_separator!r} "
                f"requires bottom_text_wrap=True."
            )
        if self.bottom_text_separator_color is not None and not self.bottom_text_wrap:
            raise ValueError(
                "bottom_text_separator_color requires bottom_text_wrap=True."
            )

        # Reject bool before any int comparisons — bool is a subclass of
        # int in Python (`isinstance(True, int)` is True), so a TOML user
        # who writes `bottom_text_loops = true` would otherwise silently
        # get loops=1. Mirrors the explicit bool guard CLAUDE.md calls
        # out for `font_threshold`.
        if isinstance(self.bottom_text_loops, bool):
            raise ValueError(
                f"bottom_text_loops must be an integer, got bool "
                f"({self.bottom_text_loops!r}). Use 0, 1, 2, … not true/false."
            )
        if self.bottom_text_loops < 0:
            raise ValueError(
                f"bottom_text_loops must be >= 0, got {self.bottom_text_loops!r}"
            )
        if (
            self.bottom_text_loops > 0
            and not self.bottom_text_wrap
            and self.bottom_text_scroll != "scroll_through"
        ):
            raise ValueError(
                f"bottom_text_loops={self.bottom_text_loops} requires "
                f"either bottom_text_wrap=True (seamless tiled marquee) "
                f"or bottom_text_scroll='scroll_through' (repeat the "
                f"offscreen pass N times). Without one of these, the "
                f"bottom row has no cycle to count."
            )

        # bottom_text_scroll enum: validate value + mutex with wrap.
        _valid_scroll = ("marquee", "scroll_through")
        if self.bottom_text_scroll not in _valid_scroll:
            raise ValueError(
                f"bottom_text_scroll={self.bottom_text_scroll!r} is not a "
                f"valid value. Pick one of: {', '.join(_valid_scroll)}."
            )
        if self.bottom_text_scroll == "scroll_through":
            if self.bottom_text_wrap:
                raise ValueError(
                    "bottom_text_scroll='scroll_through' and "
                    "bottom_text_wrap=True are mutually exclusive — "
                    "the former is a one-pass offscreen-to-offscreen "
                    "scroll, the latter is a seamless tiled marquee. "
                    "Pick one."
                )
            if not self.bottom_text:
                raise ValueError(
                    "bottom_text_scroll='scroll_through' requires "
                    "non-empty bottom_text — there's nothing to scroll."
                )

        # Defensive coercion to ColorProvider (mirrors top_color /
        # bottom_color handling). app.py's _coerce_widget_colors path
        # normally does this at config-load; this covers direct
        # construction in tests.
        if self.bottom_text_separator_color is not None and not hasattr(
            self.bottom_text_separator_color, "color_for"
        ):
            self.bottom_text_separator_color = _ConstantColor(
                self.bottom_text_separator_color
            )

    def _font_for_row(self, row_index: int) -> Font:
        """Resolve the font for a row, falling back to `self.font`."""
        if row_index == 0:
            return self.top_font if self.top_font is not None else self.font
        return self.bottom_font if self.bottom_font is not None else self.font

    def _resolved_separator_text(self) -> str:
        """Mirror of `_BaseImageWidget._resolved_separator_text` for the
        bottom-row separator.
          - None  : " • "  (default visual gap)
          - ""    : "  "   (two spaces — minimum gap)
          - else  : as-is.
        Keeps the separator-literal contract identical to the v1
        forever_scroll and image two-row wrap paths."""
        if self.bottom_text_separator is None:
            return " • "
        if self.bottom_text_separator == "":
            return "  "
        return self.bottom_text_separator

    def _measure_separator_width(self, canvas: Canvas, font: Font, sep: str) -> int:
        """Width of the resolved separator in logical px on `canvas`."""
        if not sep:
            return 0
        if EMOJI_PATTERN.search(sep):
            return measure_width(font, sep, canvas=canvas)
        return get_text_width(font, sep, padding=0, canvas=canvas)

    def _draw_row_text_at(
        self,
        canvas: Canvas,
        font: Font,
        x: int,
        baseline_y: int,
        emoji_y: int,
        text: str,
        provider: Any,
        frame_key: str,
        emoji_cap: int,
    ) -> None:
        """Render a single row of text at (x, baseline_y) in wrap mode.

        Routes plain text through `draw_text` (in this module's namespace
        so tests can patch `tr_mod.draw_text`) and emoji-containing text
        through `draw_with_emoji`. Per-char providers iterate via
        `draw_text_per_char`; whole-string providers materialize a single
        color per call."""
        frame_count = self.frame_for(frame_key)
        if EMOJI_PATTERN.search(text):
            draw_with_emoji(
                canvas,
                font,
                x,
                baseline_y,
                provider,
                text,
                emoji_y=emoji_y,
                max_emoji_height=emoji_cap,
                frame=frame_count,
            )
            return
        # Plain text path — dispatch per-char vs whole-string.
        if hasattr(provider, "color_for") and getattr(provider, "per_char", False):
            draw_text_per_char(
                canvas,
                font,
                x,
                baseline_y,
                text,
                lambda idx, total: provider.color_for(frame_count, idx, total),
            )
            return
        if hasattr(provider, "color_for"):
            color = provider.color_for(frame_count, 0, len(text) or 1)
        else:
            color = provider
        draw_text(canvas, font, x, baseline_y, color, text)

    def _draw_bottom_separator(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
        font: Font,
        sep: str,
    ) -> None:
        """Whole-string color call. Inherits `bottom_color` when
        `bottom_text_separator_color` is None (mirrors the
        `_image_base._draw_separator` inherit-fallback contract)."""
        if not sep:
            return
        if self.bottom_text_separator_color is not None:
            provider = self.bottom_text_separator_color
            frame_key = "bottom_text_separator_color"
        else:
            provider = self.bottom_color
            frame_key = "bottom_color"
        frame_count = self.frame_for(frame_key)
        if hasattr(provider, "color_for"):
            color = provider.color_for(frame_count, 0, 1)
        else:
            color = provider
        if EMOJI_PATTERN.search(sep):
            draw_with_emoji(
                canvas,
                font,
                x,
                baseline_y,
                color,
                sep,
                emoji_y=baseline_y - 8,
                frame=frame_count,
                total_chars=1,
            )
        else:
            draw_text(canvas, font, x, baseline_y, color, sep)

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        del (
            y_offset,
            font_color,
        )  # widget is meant for swap mode; y_offset/transitions ignored

        canvas_height = getattr(canvas, "height", 16)

        top_h, bottom_h = resolve_band_heights(canvas_height, self.top_row_height)

        top_font = self._font_for_row(0)
        bottom_font = self._font_for_row(1)

        # Validate each row's font fits within its band (logical units).
        # `font_line_height_logical` handles the BDF-vs-HiresFont
        # branch (BDF returns logical px, HiresFont ceil-divs by scale).
        scale = safe_scale(canvas)
        for row_label, row_font, band_h in (
            ("top", top_font, top_h),
            ("bottom", bottom_font, bottom_h),
        ):
            font_lh_logical = font_line_height_logical(row_font, scale)
            if font_lh_logical > band_h:
                raise ValueError(
                    f"{row_label} font line-height ({font_lh_logical} logical "
                    f"rows) exceeds the per-row band ({band_h} rows on a "
                    f"{canvas_height}-tall canvas). Pick a smaller font_size, "
                    f"increase the section's content_height, adjust "
                    f"top_row_height for an asymmetric split, or use a BDF "
                    f"alias (5x8, 6x12)."
                )

        if self.top_bg_color is not None:
            fill_band(canvas, 0, top_h, self.top_bg_color)
        if self.bottom_bg_color is not None:
            fill_band(canvas, top_h, canvas_height, self.bottom_bg_color)

        # Cap each row's emoji height so a hi-res sprite doesn't overflow
        # into the other row. When the band is taller than the default
        # `_EMOJI_ROW_CAP`, raise the cap to match — a hi-res sprite that
        # fits the band visually is allowed to render at hi-res. Default
        # 50/50 split with content_height=16 produces band=8 = cap, so
        # existing demos behave identically; bumping content_height or
        # top_row_height enables hi-res emoji on the affected row.
        top_emoji_cap = max(_EMOJI_ROW_CAP, top_h)
        bottom_emoji_cap = max(_EMOJI_ROW_CAP, bottom_h)

        top_text_y, top_emoji_y = _row_layout(
            canvas,
            top_font,
            band_height=top_h,
            band_offset=0,
            sprite_logical_height=top_emoji_cap,
        )
        bottom_text_y, bottom_emoji_y = _row_layout(
            canvas,
            bottom_font,
            band_height=bottom_h,
            band_offset=top_h,
            sprite_logical_height=bottom_emoji_cap,
        )
        # Apply per-row text + emoji nudges. Negative shifts up
        # (may clip the panel edge), positive shifts down. Setting
        # text + emoji offsets to the same value moves the whole row
        # together; using them independently tunes emoji-text
        # vertical alignment when the emoji sprite is taller than
        # the band.
        top_text_y += self.top_text_y_offset
        bottom_text_y += self.bottom_text_y_offset
        top_emoji_y += self.top_emoji_y_offset
        bottom_emoji_y += self.bottom_emoji_y_offset

        # Measure widths now that we have the canvas + row cap (so hi-res
        # vs. low-res fallback matches what `draw_with_emoji` will do).
        if self._top_width < 0:
            self._top_width = measure_width(
                top_font, self.top_text, canvas, top_emoji_cap
            )
        if self._bottom_width < 0:
            self._bottom_width = measure_width(
                bottom_font, self.bottom_text, canvas, bottom_emoji_cap
            )

        # Pass providers (not materialized colors) to draw_with_emoji
        # so per-char effects (rainbow / gradient) sweep continuously
        # across emoji boundaries within each row. draw_with_emoji
        # detects ColorProvider via duck-typing on `color_for` and
        # iterates per-char text segments when `provider.per_char` is
        # True; otherwise it materializes a single Color per segment.

        # Paint border BEFORE either row's text so text overlaps the
        # border on collision (border frames the panel; text floats
        # inside). Same contract as `TickerMessage.border`. Border
        # paints at PHYSICAL panel resolution via `unwrap_to_real`,
        # so at scale=2 (logical canvas 128x32) the border traces
        # the real 256x64 panel edge — frames the SIGN, not the
        # logical canvas.
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        # Top row at a fixed x — held while the bottom scrolls.
        top_x = _aligned_x(canvas.width, self._top_width, self.top_align)

        # Wrap mode: bottom row chases itself with separator. Engine's
        # cursor_pos is treated modularly; widget renders n_copies of
        # (bottom_text + separator) per draw call. Top row stays held
        # above (single draw, NOT duplicated across copies).
        #
        # The wrap branch fully handles BOTH rows (rather than letting
        # the existing non-wrap top/bottom draw run after) so tests can
        # observe per-row draw calls through a single patched code path
        # in this module's namespace. Returns `(canvas, cycle_width)`
        # so the engine has a sane stride; `wraps_forever` (Task 2)
        # gates the engine's stop-on-cursor logic in Task 7.
        if self.bottom_text_wrap:
            sep_text = self._resolved_separator_text()
            sep_width = self._measure_separator_width(canvas, bottom_font, sep_text)
            cycle_width = self._bottom_width + sep_width
            if cycle_width <= 0:
                # Defensive — validation rejects empty bottom_text and
                # measure_width returns ≥ 0, so this should be unreachable.
                # Fail soft (single draw) rather than divide-by-zero below.
                cycle_width = max(1, self._bottom_width)

            # Draw the held top row once.
            self._draw_row_text_at(
                canvas,
                top_font,
                top_x,
                top_text_y,
                top_emoji_y,
                self.top_text,
                self.top_color,
                "top_color",
                top_emoji_cap,
            )

            # Bottom row: n_copies of (bottom_text + separator). Python's
            # `%` on negative dividends keeps `scroll_pos` in [0, cycle_width),
            # so the engine can drive `cursor_pos` in either direction.
            scroll_pos = cursor_pos % cycle_width
            canvas_w = canvas.width
            n_copies = (canvas_w + cycle_width - 1) // cycle_width + 1
            start_x = scroll_pos - cycle_width

            for i in range(n_copies):
                x = start_x + i * cycle_width
                self._draw_row_text_at(
                    canvas,
                    bottom_font,
                    x,
                    bottom_text_y,
                    bottom_emoji_y,
                    self.bottom_text,
                    self.bottom_color,
                    "bottom_color",
                    bottom_emoji_cap,
                )
                if sep_width > 0:
                    self._draw_bottom_separator(
                        canvas,
                        x + self._bottom_width,
                        bottom_text_y,
                        bottom_font,
                        sep_text,
                    )

            return canvas, cycle_width

        draw_with_emoji(
            canvas,
            top_font,
            top_x,
            top_text_y,
            self.top_color,
            self.top_text,
            emoji_y=top_emoji_y,
            max_emoji_height=top_emoji_cap,
            frame=self.frame_for("top_color"),
        )

        # Bottom row: cursor_pos is supplied by the framework. Three
        # branches:
        #   * scroll_through mode forces offscreen-to-offscreen travel.
        #     The engine drives cursor_pos from 0 downward; bottom_x
        #     is computed modularly so each loop iteration wraps the
        #     text back to canvas.width after it exits the left edge.
        #     `bottom_text_loops` controls how many full passes run
        #     before the section exits.
        #   * Default (marquee) fit branch holds at bottom_align.
        #   * Default (marquee) overflow branch lets cursor_pos drive.
        if self.bottom_text_scroll == "scroll_through":
            cycle_width = canvas.width + self._bottom_width
            # `-cursor_pos % cycle_width` keeps the offset in [0, cycle_width).
            # cycle_width is >= 1 (canvas.width > 0; _bottom_width >= 0
            # though scroll_through requires non-empty bottom_text via
            # validation, so _bottom_width > 0 in practice).
            elapsed_in_cycle = (-cursor_pos) % cycle_width
            bottom_x = canvas.width - elapsed_in_cycle
        elif self._bottom_width <= canvas.width and cursor_pos == 0:
            bottom_x = _aligned_x(canvas.width, self._bottom_width, self.bottom_align)
        else:
            bottom_x = cursor_pos

        draw_with_emoji(
            canvas,
            bottom_font,
            bottom_x,
            bottom_text_y,
            self.bottom_color,
            self.bottom_text,
            emoji_y=bottom_emoji_y,
            max_emoji_height=bottom_emoji_cap,
            frame=self.frame_for("bottom_color"),
        )

        # Report cursor at the bottom-row's right edge so `_swap_and_scroll`
        # knows whether to scroll, and where to stop.
        #
        # scroll_through: the engine's dedicated loop (forces_offscreen_scroll
        # branch in _swap_and_scroll) overrides cursor_pos with its own
        # max-of computation — n_passes = max(loops_or_1,
        # ceil(hold_time_ticks / cycle_width)) — so the returned cursor
        # here is used only to signal "overflow" (cursor > canvas.width)
        # and is not used as the scroll stop-position on this path.
        # The value returned still encodes loops*cycle_width to keep the
        # old stop-math path consistent for any caller that reads it directly.
        if self.bottom_text_scroll == "scroll_through":
            loops = max(1, self.bottom_text_loops)
            cycle_width = canvas.width + self._bottom_width
            return canvas, canvas.width + loops * cycle_width + self.padding
        return canvas, cursor_pos + self._bottom_width + self.padding

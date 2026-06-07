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
`image_align`, plus `play_count` / `hold_time` for per-visit
duration).

When `bg_color` is set on the widget, `_paint_image()` dispatches to
`_paint_skip_black` instead of `_paint_full` so pillarbox / letterbox
bands and alpha-transparent regions reveal the bg color filled by the
caller's `reset_canvas`. With `bg_color = None`, `_paint_image` uses
the `_paint_full` fast path (single SetImage call). Subclasses don't
need to be aware of `bg_color` — they just implement both paint
methods and the base class picks.
"""

import asyncio
from enum import StrEnum
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, Font
from led_ticker.color_providers import _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, get_text_width, safe_scale
from led_ticker.fonts import (
    FONT_DEFAULT,
    block_scale_for_font_size,
    font_line_height,
    font_line_height_logical,
)
from led_ticker.fonts.hires_loader import HiresFont as _HiresFont
from led_ticker.pixel_emoji import EMOJI_PATTERN
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets._frame_aware import FrameAwareBase
from led_ticker.widgets._image_fit import (
    VALID_IMAGE_ALIGNS,
    reset_canvas,
    validate_choice,
)
from led_ticker.widgets._row_layout import (
    EMOJI_ROW_CAP,
    aligned_x,
    resolve_band_heights,
    row_layout,
)


class TextAlign(StrEnum):
    """Valid horizontal text alignment modes."""

    LEFT = "left"
    RIGHT = "right"
    SCROLL = "scroll"
    SCROLL_OVER = "scroll_over"


class TextValign(StrEnum):
    """Valid vertical text alignment modes."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class ScrollDirection(StrEnum):
    """Valid scroll direction modes."""

    LEFT = "left"
    RIGHT = "right"


# Backward-compatibility aliases
VALID_TEXT_ALIGNS: frozenset[str] = frozenset(TextAlign)
VALID_TEXT_VALIGNS: frozenset[str] = frozenset(TextValign)
VALID_SCROLL_DIRECTIONS: frozenset[str] = frozenset(ScrollDirection)

# `text_align="auto"` resolves to the side opposite the image so they don't
# overlap. Centered image → scroll_over (always paints over, no overlap).
AUTO_TEXT_ALIGN_FOR_IMAGE: dict[str, str] = {
    "left": "right",
    "right": "left",
    "center": "scroll_over",
}

TEXT_EDGE_PADDING_PX: int = 2
MIN_SCROLL_SPEED_MS: int = 20
HOLD_TIME_FLOOR: float = 0.05


@attrs.define
class _BaseImageWidget(FrameAwareBase):
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
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    scroll_speed_ms: int = attrs.field(default=50, kw_only=True)
    text_loops: int = attrs.field(default=0, kw_only=True)

    # Wrap-mode marquee: continuous text + separator chase across the
    # panel. Only valid with `text_align in ("scroll", "scroll_over")`.
    # When True, the per-tick scroll loop runs at modular cycle width
    # (text + separator) so the text never fully leaves the panel.
    # `text_loops` reinterprets as "minimum cycle traversals" instead
    # of the off-right-to-off-left definition used by the default
    # marquee. Two-row mode (`bottom_text` set) refuses `text_wrap` —
    # the bottom row already auto-scrolls on overflow with different
    # semantics; conflating the two would be confusing.
    text_wrap: bool = attrs.field(default=False, kw_only=True)

    # The text inserted between repeats in `text_wrap` mode. None = use
    # the default " • " when wrap is on (matching forever_scroll's
    # default separator). Explicit "" → "  " (two-space gap, matching
    # forever_scroll's empty-separator semantics). Any other value is
    # rendered as-is.
    text_separator: str | None = attrs.field(default=None, kw_only=True)

    # Color for the separator in wrap mode. None = inherit `font_color`.
    # The separator is rendered as a single "blob" — even when the
    # value is a per-char provider (rainbow/gradient), it's called
    # with `color_for(frame, 0, 1)` to pick one hue per frame. Its
    # frame counter is registered in `FrameAwareBase._EFFECT_ATTRS` so
    # continuous-phase providers stay in phase with the main text.
    text_separator_color: Any | None = attrs.field(default=None, kw_only=True)

    # Two-row wrap (v2). Mirrors text_wrap / text_separator /
    # text_separator_color but applies to the BOTTOM row in two-row
    # mode (bottom_text set). The top row never wraps. When True,
    # the bottom row chases itself continuously with the separator
    # between copies — even when bottom_text fits the canvas.
    # v1's single-row text_wrap stays single-row-only and is refused
    # in two-row mode.
    bottom_text_wrap: bool = attrs.field(default=False, kw_only=True)

    # Glyph(s) between bottom-row repeats in wrap mode. None → " • "
    # default (matches v1 + forever_scroll). "" → "  " (two-space gap).
    bottom_text_separator: str | None = attrs.field(default=None, kw_only=True)

    # Color for the bottom separator. None inherits bottom_color
    # (NOT font_color — separator is a piece of the bottom row).
    # When set, gets its own per-effect frame counter via
    # FrameAwareBase._EFFECT_ATTRS so continuous-phase Rainbow stays
    # in phase with bottom_color.
    bottom_text_separator_color: Any | None = attrs.field(default=None, kw_only=True)

    # Bottom-row scroll style — parallel to TwoRowMessage's field. See
    # the docstring there for the contract; in short:
    #   "marquee"        Default. Held when fits + cursor-driven scroll
    #                    on overflow (or wrap when bottom_text_wrap=True).
    #   "scroll_through" Force the offscreen marquee branch even when
    #                    bottom_text fits. Bottom row starts at scroll_pos
    #                    = canvas_w (off the right edge) and scrolls left
    #                    every tick. Mutually exclusive with
    #                    bottom_text_wrap=True. Only valid in two-row
    #                    mode (bottom_text non-empty).
    bottom_text_scroll: str = attrs.field(default="marquee", kw_only=True)

    # Animation effect (currently Typewriter only). When set, text
    # types out one character per `frames_per_char` ticks. Single-row
    # only — `_validate_common` raises if `bottom_text` is set or
    # `text_align ∈ ("scroll", "scroll_over")`. Composes with
    # `font_color` (rainbow / gradient) and `border` (rainbow /
    # constant) on independent per-effect counters from PR #12.
    animation: Any | None = attrs.field(default=None, kw_only=True)

    # User-facing via TOML `font = "..."` / `font_size = N`. The CLI's
    # `_build_widget` resolves the name into a font object before
    # construction (BDF or HiresFont) and passes it here. Defaults to
    # FONT_DEFAULT (BDF 6x12) so existing configs that don't mention
    # font keep their look.
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)

    # Real-pixel size knob — unifies BDF (block-scales via the wrapper)
    # and HiresFont (rasterizer target). None = smart default at first
    # paint (BDF: cell_h × _logical_scale). HiresFont with None falls
    # back to the font's natural size baked in at construction.
    font_size: int | None = attrs.field(default=None, kw_only=True)

    # ------------------------------------------------------------------
    # Two-row text overlay (optional; mirrors `TwoRowMessage` semantics).
    # When `bottom_text` is non-empty, switch to two-row mode: held top
    # row + scroll-on-overflow bottom row, both painted over the image.
    # Most fields fall back to the single-row knobs (`text` → top text,
    # `font_color` → top color, `font` → top font) so a config that
    # only adds `bottom_text` works without renaming everything else.
    #
    # NOT included by design: per-row bg color. Image widgets'
    # `bg_color` is the whole-canvas / letterbox fill — adding band-
    # specific bg knobs would conflict semantically with the image
    # painted underneath. Per-row band fills aren't a meaningful
    # concept on top of an image; leave them out.
    # ------------------------------------------------------------------
    top_text: str = attrs.field(default="", kw_only=True)
    bottom_text: str = attrs.field(default="", kw_only=True)
    top_color: Color | None = attrs.field(default=None, kw_only=True)
    bottom_color: Color | None = attrs.field(default=None, kw_only=True)
    top_align: str = attrs.field(default="center", kw_only=True)
    bottom_align: str = attrs.field(default="center", kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    bottom_font: Font | None = attrs.field(default=None, kw_only=True)
    top_text_y_offset: int = attrs.field(default=0, kw_only=True)
    bottom_text_y_offset: int = attrs.field(default=0, kw_only=True)
    top_emoji_y_offset: int = attrs.field(default=0, kw_only=True)
    bottom_emoji_y_offset: int = attrs.field(default=0, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)

    # Optional perimeter border effect — same contract as
    # `TickerMessage.border` and `TwoRowMessage.border` (see
    # borders.py). Paints AFTER the image and BEFORE any text overlay
    # so the border frames the panel and text overlaps it on
    # collision. None = no border (no perf cost). Coerced from
    # TOML at config-load via `_coerce_border` in app.py.
    border: Any | None = attrs.field(default=None, kw_only=True)

    # Framework-internal — not user-facing TOML.
    padding: int = attrs.field(init=False, default=0)

    # Panel dims; set by subclass `_load()`.
    _panel_w: int = attrs.field(init=False, default=0)
    _panel_h: int = attrs.field(init=False, default=0)

    # Logical-canvas scale of the section we were dispatched into. Set
    # by `ticker._play_widget` from the wrapper's `.scale` BEFORE the
    # ScaledCanvas is unwrapped (since `play()` receives the raw real
    # canvas). Used to interpret `top_row_height` in logical units —
    # matches `TwoRowMessage`'s convention so a config that uses
    # `top_row_height = 5` reads the same on both widgets.
    _logical_scale: int = attrs.field(init=False, default=1)

    # Cached at validation time (text is invariant for the widget's
    # lifetime); avoids re-running EMOJI_PATTERN.search per tick.
    _has_emoji_cached: bool = attrs.field(init=False, default=False)

    # ------------------------------------------------------------------
    # Subclass hooks — must be implemented by subclasses
    # ------------------------------------------------------------------

    def _paint_full(self, canvas: Canvas) -> None:
        raise NotImplementedError

    def _paint_skip_black(self, canvas: Canvas) -> None:
        raise NotImplementedError

    def _paint_image(self, canvas: Canvas) -> None:
        """Dispatch to the right paint path for the current `bg_color`.

        With no bg, use the subclass `_paint_full` fast path (SetImage in
        a single C call). With bg set, use `_paint_skip_black` so
        pillarbox / letterbox / transparent regions reveal the bg
        instead of being painted black.
        """
        if self.bg_color is None:
            self._paint_full(canvas)
        else:
            self._paint_skip_black(canvas)

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        raise NotImplementedError

    def _pick_frame_for_elapsed(self, elapsed_ms: int) -> None:
        """Advance per-frame state. No-op for single-frame stills;
        gif overrides to update `_current_frame_idx`."""

    def _is_static(self) -> bool:
        """Whether the source has only one renderable frame. Drives the
        static-text fast path: when True AND text is non-scrolling AND
        text_loops==0, the rendered output is identical every tick so
        we paint once + sleep cumulative duration. False (default)
        forces the per-tick loop to run so animated sources keep
        advancing frames even alongside static text. GifPlayer
        overrides to `len(self._frames) <= 1`."""
        return True

    # ------------------------------------------------------------------
    # Shared validation — call from subclass __attrs_post_init__
    # ------------------------------------------------------------------

    def _validate_common(self, image_align: str, fit: str) -> None:
        """Validate the text-overlay fields + cross-field pitfalls.

        Subclasses pass their `image_align` and `fit` so we can catch
        combinations like `text_align="scroll"` + `fit="stretch"` that
        produce silent no-text rendering.
        """
        # Wrap raw Color → _ConstantColor for uniform provider dispatch.
        if self.font_color is not None and not hasattr(self.font_color, "color_for"):
            self.font_color = _ConstantColor(self.font_color)
        if self.top_color is not None and not hasattr(self.top_color, "color_for"):
            self.top_color = _ConstantColor(self.top_color)
        if self.bottom_color is not None and not hasattr(
            self.bottom_color, "color_for"
        ):
            self.bottom_color = _ConstantColor(self.bottom_color)
        if self.text_separator_color is not None and not hasattr(
            self.text_separator_color, "color_for"
        ):
            self.text_separator_color = _ConstantColor(self.text_separator_color)
        if self.bottom_text_separator_color is not None and not hasattr(
            self.bottom_text_separator_color, "color_for"
        ):
            self.bottom_text_separator_color = _ConstantColor(
                self.bottom_text_separator_color
            )

        validate_choice("image_align", image_align, VALID_IMAGE_ALIGNS)
        # Resolve text_align="auto" based on image_align so text doesn't
        # overlap the image by default. Authors can pin any value. In
        # two-row mode the single-row text_align is irrelevant — the
        # widget uses top_align/bottom_align — so leave "auto" as-is.
        # Track whether the user wrote "auto" so the wrap-mode
        # text_align check below can produce a more actionable error
        # — without this flag the message reports the RESOLVED value
        # (e.g. "right") which obscures the user's intent.
        text_align_was_auto = self.text_align == "auto"
        if self.text_align == "auto" and not self.bottom_text:
            self.text_align = AUTO_TEXT_ALIGN_FOR_IMAGE[image_align]
        # Always validate text_align even when text="" (in single-row
        # mode); an explicit bogus value should surface during config-
        # load. Skip in two-row mode where text_align is unused.
        if not self.bottom_text:
            validate_choice("text_align", self.text_align, VALID_TEXT_ALIGNS)
        validate_choice("text_valign", self.text_valign, VALID_TEXT_VALIGNS)
        validate_choice(
            "scroll_direction", self.scroll_direction, VALID_SCROLL_DIRECTIONS
        )
        if self.font_size is not None and self.font_size <= 0:
            raise ValueError(f"font_size must be > 0; got {self.font_size!r}.")
        if self.text_loops < 0:
            raise ValueError(f"text_loops must be >= 0, got {self.text_loops!r}")
        if self.scroll_speed_ms < MIN_SCROLL_SPEED_MS:
            raise ValueError(
                f"scroll_speed_ms must be >= {MIN_SCROLL_SPEED_MS}, "
                f"got {self.scroll_speed_ms!r}"
            )
        # Pitfall: text_loops > 0 with static alignment is a silent no-op
        # in the per-tick loop (the floor formula gates on `scrolling`).
        if self.text_loops > 0 and self.text_align in ("left", "right"):
            raise ValueError(
                f"text_loops > 0 only applies when text_align is 'scroll' "
                f"or 'scroll_over'; got text_align={self.text_align!r}"
            )
        # Pitfall: text_x_offset is a static-text knob; for scrolling it
        # would just skew the trajectory by a constant — confusing.
        if self.text_x_offset != 0 and self.text_align in ("scroll", "scroll_over"):
            raise ValueError(
                f"text_x_offset is only meaningful for static text_align "
                f"(left/right); got text_align={self.text_align!r}"
            )
        # Pitfall: text_align="scroll" + fit="stretch" → no transparent
        # regions for skip-black to expose, so text is invisible.
        if self.text and self.text_align == "scroll" and fit == "stretch":
            raise ValueError(
                "text_align='scroll' needs transparent / pillarbox regions "
                "to show through; got fit='stretch' (whole panel is opaque). "
                "Use text_align='scroll_over' for marquee on a fullscreen image."
            )

        # Animation field validation (single-row typewriter only).
        # All three checks raise at config-load so the user sees the
        # conflict immediately instead of getting a silent surprise
        # on the panel. Bottom_text check fires first because two-row
        # mode is the most likely accidental conflict.
        if self.animation is not None:
            if self.bottom_text:
                raise ValueError(
                    "animation is not supported in two-row mode "
                    "(set on a single-row image widget; remove bottom_text)"
                )
            if self.text_align in ("scroll", "scroll_over"):
                raise ValueError(
                    f"animation is not compatible with "
                    f"text_align={self.text_align!r} "
                    "(typewriter on a moving marquee is incoherent; "
                    "use text_align=auto/left/right)"
                )
            if not self.text:
                raise ValueError(
                    "animation requires non-empty text "
                    "(typewriter has nothing to type out)"
                )

        # text_wrap validation. Wrap is a marquee variation, so it
        # only makes sense with the scrolling alignments. It also
        # composes oddly with two-row mode (the bottom row already
        # auto-scrolls with different semantics) — refuse outright.
        # Two-row check fires first so users with both violations get
        # the more actionable diagnostic (text_align is meaningless in
        # two-row mode anyway).
        if self.text_wrap:
            if self.bottom_text:
                raise ValueError(
                    "text_wrap is single-row only; in two-row mode use "
                    "bottom_text_wrap (the separator + color knobs use "
                    "the bottom_text_* prefix too)."
                )
            # Empty-text check: text_wrap=True with text="" would
            # render an endless chain of separators on the panel —
            # almost certainly a user typo. Refuse with a clear
            # message. Skip when bottom_text is set so the two-row
            # branch (above) is the single source of truth there.
            if not self.text and not self.bottom_text:
                raise ValueError(
                    "text_wrap=True requires non-empty text (otherwise "
                    "the marquee is just a chain of separators)."
                )
            if self.text_align not in ("scroll", "scroll_over"):
                # If the user wrote text_align="auto", the resolution
                # above already replaced it with the side opposite the
                # image — but "auto" never resolves to a scroll mode
                # for image_align in {"left", "right"} (it resolves to
                # "right" / "left"). Report the user-facing value so
                # the diagnostic is actionable.
                auto_hint = (
                    " (text_align='auto' was resolved based on "
                    "image_align before this check; pin "
                    "text_align='scroll_over' or text_align='scroll' "
                    "explicitly when using text_wrap)"
                    if text_align_was_auto
                    else ""
                )
                raise ValueError(
                    f"text_wrap=True requires text_align in "
                    f"('scroll', 'scroll_over'); got "
                    f"text_align={self.text_align!r}. "
                    f"Wrap is a marquee variation; on static alignments "
                    f"it has nothing to wrap."
                    f"{auto_hint}"
                )

        # Separator fields require text_wrap=True. Without wrap, the
        # separator has nowhere to render — silent no-op would mask
        # a misconfiguration.
        if self.text_separator is not None and not self.text_wrap:
            raise ValueError(
                f"text_separator={self.text_separator!r} requires "
                f"text_wrap=True. The separator only renders in wrap "
                f"mode."
            )
        if self.text_separator_color is not None and not self.text_wrap:
            raise ValueError(
                "text_separator_color requires text_wrap=True. The "
                "separator only renders in wrap mode."
            )

        # bottom_text_wrap validation. Only valid in two-row mode
        # (bottom_text non-empty). Always-wrap when set — even when
        # bottom_text fits the canvas. The single ValueError covers
        # both "two-row required" and "non-empty bottom_text required"
        # because they fire on the same condition.
        if self.bottom_text_wrap and not self.bottom_text:
            raise ValueError(
                "bottom_text_wrap=True requires non-empty bottom_text. "
                "For single-row marquees use text_wrap."
            )

        # Separator fields require bottom_text_wrap.
        if self.bottom_text_separator is not None and not self.bottom_text_wrap:
            raise ValueError(
                f"bottom_text_separator={self.bottom_text_separator!r} "
                f"requires bottom_text_wrap=True."
            )
        if self.bottom_text_separator_color is not None and not self.bottom_text_wrap:
            raise ValueError(
                "bottom_text_separator_color requires bottom_text_wrap=True."
            )

        # bottom_text_scroll enum: validate value + mutex with wrap.
        # Mirrors TwoRowMessage's validation contract exactly.
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
                # Pointing the user at text_align (the single-row scroll
                # knob) is more useful than telling them to add a
                # bottom_text they probably don't want.
                raise ValueError(
                    "bottom_text_scroll='scroll_through' is only valid "
                    "in two-row mode (bottom_text non-empty). For "
                    "single-row scrolling on this widget, use "
                    "text_align='scroll' or 'scroll_over' instead."
                )

        # Two-row mode validation. `bottom_text != ""` switches the
        # widget to held-top + scrolling-bottom semantics (mirrors
        # `TwoRowMessage`), so the single-row knobs that would conflict
        # are refused. `text` becomes a back-compat alias for
        # `top_text`; setting both is ambiguous.
        if self.bottom_text:
            if self.text and self.top_text:
                raise ValueError(
                    "Cannot set both `text` and `top_text` in two-row mode "
                    "(when `bottom_text` is non-empty). `text` is a "
                    "back-compat alias for `top_text` — use one or the other."
                )
            if self.text_align != "auto":
                raise ValueError(
                    f"text_align={self.text_align!r} is unused in two-row "
                    f"mode (bottom_text non-empty). Two-row uses TwoRow's "
                    f"auto-scroll-on-overflow contract — use top_align / "
                    f"bottom_align (left / center / right) instead, and "
                    f"the bottom row scrolls when its text overflows."
                )
            if self.text_valign != "center":
                raise ValueError(
                    f"text_valign={self.text_valign!r} is meaningless in "
                    f"two-row mode — row positions come from the split "
                    f"(top_row_height) and per-row text_y_offset. Drop "
                    f"text_valign or use the per-row offset knobs."
                )
            if self.text_x_offset != 0:
                raise ValueError(
                    f"text_x_offset={self.text_x_offset!r} is meaningless "
                    f"in two-row mode — use top_align / bottom_align for "
                    f"horizontal positioning."
                )
            if self.font_size is not None:
                raise ValueError(
                    f"font_size={self.font_size!r} is the single-row knob; "
                    f"in two-row mode use top_font_size and bottom_font_size."
                )
            if self.top_row_height is not None and self.top_row_height <= 0:
                raise ValueError(
                    f"top_row_height must be > 0; got {self.top_row_height!r}"
                )

        # Cache emoji-presence so the per-tick paint loop doesn't re-run
        # the regex against an invariant string. In two-row mode check
        # both rows; single-row mode just checks `text`.
        scan_text = self.text + self.top_text + self.bottom_text
        self._has_emoji_cached = bool(EMOJI_PATTERN.search(scan_text))

    # ------------------------------------------------------------------
    # Shared text-rendering helpers
    # ------------------------------------------------------------------

    def _baseline_y(self, canvas: Canvas) -> int:
        """Font-aware baseline anchored per `text_valign`, plus `text_y_offset`.

        Delegates to `drawing.compute_baseline`, which handles BDF and
        HiresFont uniformly: figures out the canvas scale, derives the
        ascent / line_height in real pixels, and returns the logical-y
        baseline value to pass to `draw_text`. `text_y_offset` shifts
        further (negative=up, positive=down) on top of the computed
        baseline.
        """
        return (
            compute_baseline(self.font, canvas, valign=self.text_valign)
            + self.text_y_offset
        )

    def _has_emoji(self) -> bool:
        return self._has_emoji_cached

    def _is_two_row(self) -> bool:
        """True when `bottom_text` is non-empty — switches the widget
        to held-top + scrolling-bottom layout."""
        return bool(self.bottom_text)

    def _has_text_content(self) -> bool:
        """True when ANY text field is set — `text`, `top_text`, or
        `bottom_text`. Used by subclass `play()` methods to decide
        whether to take the text-overlay code path. Without this,
        `play()` checking only `self.text` would silently skip the
        overlay when the user set `top_text` + `bottom_text` (two-row
        mode) and left `text` empty.
        """
        return bool(self.text or self.top_text or self.bottom_text)

    def _resolved_font_size(self) -> int:
        """Return the effective font_size in real pixels. Hot-path
        method (called once per visit, cached in a local).

        If `self.font_size` is set, returned as-is. Otherwise:
        - BDF: `cell_h × _logical_scale` (smart default that preserves
          bd61140 panel-scale behavior).
        - HiresFont: the font's own `size` attribute (set by the
          loader at construction time).
        """
        if self.font_size is not None:
            return self.font_size
        if isinstance(self.font, _HiresFont):
            return self.font.size
        # BDF: smart default = cell_h × _logical_scale.
        cell_h = font_line_height(self.font)
        return cell_h * self._logical_scale

    def _row_text(self, row: int) -> str:
        """Resolve per-row text content. Top row falls back to `text`
        (the single-row alias) when `top_text` isn't explicitly set,
        so configs that only add `bottom_text` keep working."""
        if row == 0:
            return self.top_text or self.text
        return self.bottom_text

    def _row_font(self, row: int) -> Any:
        """Per-row font with fallback to `self.font`."""
        per_row = self.top_font if row == 0 else self.bottom_font
        return per_row if per_row is not None else self.font

    def _row_color(self, row: int) -> Color:
        """Per-row color with fallback to `self.font_color`."""
        per_row = self.top_color if row == 0 else self.bottom_color
        return per_row if per_row is not None else self.font_color

    def _row_color_attr(self, row: int) -> str:
        """Which `_EFFECT_ATTRS` key to look up `frame_for` against,
        matching `_row_color`'s fallback. Per-row knob takes precedence;
        fall back to `font_color` so a continuous-phase rainbow set via
        `font_color` (with no per-row override) reads its own per-effect
        counter — not the primary `_frame_count` (which resets per visit
        and would silently restart the chase).

        TwoRowMessage doesn't need this helper because its
        `top_color` / `bottom_color` are required `Color | ColorProvider`
        fields (default `DEFAULT_COLOR`), never `None` — the per-effect
        keys are always registered. If TwoRowMessage ever gains
        `Color | None` defaults, this helper's pattern needs to be
        replicated there or the same silent-restart bug returns.
        """
        per_row = self.top_color if row == 0 else self.bottom_color
        if per_row is not None:
            return "top_color" if row == 0 else "bottom_color"
        return "font_color"

    def _row_align(self, row: int) -> str:
        return self.top_align if row == 0 else self.bottom_align

    def _row_text_y_offset(self, row: int) -> int:
        return self.top_text_y_offset if row == 0 else self.bottom_text_y_offset

    def _row_emoji_y_offset(self, row: int) -> int:
        return self.top_emoji_y_offset if row == 0 else self.bottom_emoji_y_offset

    def _visible_text(self, frame_count: int, canvas: Canvas) -> str:
        """Apply animation to text. Returns full text when no animation
        is configured. Layout (cursor position, alignment math) operates
        against `self.text` regardless — the anchored layout uses the
        eventual full-text width while only the visible slice gets
        drawn. This is what makes typewriter feel 'anchored' under
        right-align: the partial text appears in the position the
        final text will occupy.

        Mirrors `TickerMessage.draw`'s animation branch: calls
        `Typewriter.frame_for(frame, full_text, canvas_width, text_width)`
        and reads `.visible_text` from the returned `AnimationFrame`.
        cursor position is controlled via `text_align`.
        """
        if self.animation is None:
            return self.text
        text_width = self._measure_text(canvas)
        anim_frame = self.animation.frame_for(
            frame_count, self.text, canvas.width, text_width
        )
        return anim_frame.visible_text

    def _measure_text(self, canvas: Canvas) -> int:
        if self._has_emoji():
            from led_ticker.pixel_emoji import measure_width

            return measure_width(self.font, self.text, canvas=canvas)
        return get_text_width(self.font, self.text, padding=0, canvas=canvas)

    def _resolved_separator_text(self, separator: str | None = None) -> str:
        """Resolve the separator string per wrap-mode semantics:
          - None (default): " • "
          - "" (explicit empty): "  " (two spaces — minimum gap so
            adjacent copies don't visually butt up)
          - any other value: as-is.

        When `separator` is None the helper reads `self.text_separator`
        (v1 single-row default). v2 two-row callers pass
        `self.bottom_text_separator` explicitly — that field's own
        default of None still resolves to " • " here.

        Mirrors `forever_scroll`'s separator literal-text rules so a
        user moving from per-section to per-widget wraps gets the
        same defaults."""
        if separator is None:
            separator = self.text_separator
        if separator is None:
            return " • "
        if separator == "":
            return "  "
        return separator

    def _measure_separator(
        self,
        canvas: Canvas,
        font: Any = None,
        separator: str | None = None,
    ) -> int:
        """Width of the resolved separator in logical px on `canvas`.

        Defaults match v1 single-row behavior (self.font +
        self.text_separator). Two-row callers pass
        `font=self.bottom_font_or_fallback` and
        `separator=self.bottom_text_separator`."""
        sep = self._resolved_separator_text(separator)
        if not sep:
            return 0
        if font is None:
            font = self.font
        if EMOJI_PATTERN.search(sep):
            from led_ticker.pixel_emoji import measure_width

            return measure_width(font, sep, canvas=canvas)
        return get_text_width(font, sep, padding=0, canvas=canvas)

    def _draw_separator(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
        font: Any = None,
        separator: str | None = None,
        explicit_provider: Any = None,
        explicit_frame_key: str = "",
        inherit_provider: Any = None,
        inherit_frame_key: str = "",
    ) -> None:
        """Draw the resolved separator at (x, baseline_y) with the
        right color. Whole-string color call so even a Rainbow on
        the dedicated-separator-color provider paints the separator
        as one hue per frame.

        Callers pick "explicit" (the dedicated separator color knob)
        and "inherit" (the row's main color used as fallback):
          - v1 single-row default (no kwargs passed):
            explicit = self.text_separator_color / "text_separator_color"
            inherit  = self.font_color / "font_color"
          - v2 two-row (Task 5 callers):
            explicit = self.bottom_text_separator_color /
                       "bottom_text_separator_color"
            inherit  = self.bottom_color / "bottom_color"
        """
        sep = self._resolved_separator_text(separator)
        if not sep:
            return
        if font is None:
            font = self.font

        # No-override path: preserve v1 single-row behavior exactly.
        if explicit_provider is None and not explicit_frame_key:
            explicit_provider = self.text_separator_color
            explicit_frame_key = "text_separator_color"
        if inherit_provider is None and not inherit_frame_key:
            inherit_provider = self.font_color
            inherit_frame_key = "font_color"

        if explicit_provider is not None:
            provider = explicit_provider
            frame_key = explicit_frame_key
        else:
            provider = inherit_provider
            frame_key = inherit_frame_key

        frame_count = self.frame_for(frame_key)
        if provider is not None and hasattr(provider, "color_for"):
            color = provider.color_for(frame_count, 0, 1)
        else:
            color = provider

        if EMOJI_PATTERN.search(sep):
            from led_ticker.pixel_emoji import draw_with_emoji

            draw_with_emoji(
                canvas,
                font,
                x,
                baseline_y,
                color,
                sep,
                frame=frame_count,
                total_chars=1,
            )
        else:
            draw_text(canvas, font, x, baseline_y, color, sep)

    def _draw_text(
        self,
        canvas: Canvas,
        x: int,
        baseline_y: int,
        color: Any,
        text_override: str | None = None,
    ) -> int:
        """Route to draw_with_emoji when text contains slugs; otherwise
        plain BDF/HiresFont rasterizer. Emoji's 8-px sprite is anchored
        so its bottom row sits on the text baseline (works for any
        valign/scale).

        `color` accepts a Color or a ColorProvider. For text with emoji,
        the provider passes through to `draw_with_emoji` which dispatches
        on `provider.per_char` — per-char providers iterate text segments
        with continuous char_index across emoji boundaries. Plain text
        with a per-char provider iterates via `draw_text_per_char` so
        rainbow/gradient render with per-character hue offsets; whole-
        string providers materialize once and use `draw_text`.

        `text_override`: when set (typewriter mid-cycle), draws this
        string instead of `self.text`. Per-char providers receive
        `total_chars=len(self.text)` (the eventual full length) so a
        char that types in at position N gets the same hue mid-type
        as it will at completion — anchors hue to char identity, not
        to current visible position.
        """
        text = text_override if text_override is not None else self.text
        # Per-char total: the eventual full-text length, so hue stays
        # anchored to char identity across typewriter's reveal.
        per_char_total = len(self.text) if self.text else 1
        if self._has_emoji():
            from led_ticker.pixel_emoji import count_text_chars, draw_with_emoji

            # Anchor per-char hue to the FULL text's char count so a
            # char's hue is stable as typewriter reveals more chars.
            # Without this, a rainbow on `text="Hi :star:"` mid-type
            # would re-distribute hues across the visible slice
            # ("Hi", "Hi ", "Hi :", ...) instead of the eventual 3
            # text chars — char 0's hue would drift as the reveal grows.
            full_total_chars = count_text_chars(self.text)
            return draw_with_emoji(
                canvas,
                self.font,
                x,
                baseline_y,
                color,
                text,
                frame=self.frame_for("font_color"),
                total_chars=full_total_chars,
            )
        # Plain-text per-char path: rainbow / gradient iterate chars so
        # each character renders with its own hue. Mirrors
        # `TickerMessage.draw`'s per-char branch.
        if hasattr(color, "color_for") and color.per_char:
            return draw_text_per_char(
                canvas,
                self.font,
                x,
                baseline_y,
                text,
                lambda idx, total: color.color_for(
                    self.frame_for("font_color"), idx, per_char_total
                ),
            )
        # Whole-string provider or constant Color.
        if hasattr(color, "color_for"):
            color = color.color_for(self.frame_for("font_color"), 0, per_char_total)
        return draw_text(canvas, self.font, x, baseline_y, color, text)

    def _measure_row_text(
        self, canvas: Canvas, row: int, max_emoji_height: int = EMOJI_ROW_CAP
    ) -> int:
        """Width of one row's text in two-row mode. Uses per-row font
        and emoji-aware measurement when the row's text contains
        `:slug:` tokens; otherwise the plain `get_text_width` path.

        `max_emoji_height` controls the hi-res / low-res fallback for
        any inline emoji slugs. Caller passes the row's band height
        so a hi-res sprite that fits the band visually is allowed
        through; defaults to the static `EMOJI_ROW_CAP` for back-compat.
        """
        font = self._row_font(row)
        text = self._row_text(row)
        if self._has_emoji() and EMOJI_PATTERN.search(text):
            from led_ticker.pixel_emoji import measure_width

            return measure_width(
                font, text, canvas=canvas, max_emoji_height=max_emoji_height
            )
        return get_text_width(font, text, padding=0, canvas=canvas)

    def _draw_row_text(
        self,
        canvas: Canvas,
        font: Any,
        text: str,
        color: Any,
        x: int,
        baseline_y: int,
        emoji_y: int,
        frame_count: int,
        max_emoji_height: int = EMOJI_ROW_CAP,
    ) -> None:
        """Draw one row's text given pre-resolved font / text / color.
        Caller (`_render_two_row_tick`) resolves these once outside the
        tick loop so per-row attribute lookups don't run every frame.
        Mirrors `_draw_text` but accepts an explicit `emoji_y` so the
        emoji can be nudged independently of the text baseline.

        `color` accepts a Color or a ColorProvider. Provider + emoji
        flows through `draw_with_emoji` for per-char rainbow support.
        `frame_count` is the per-effect counter the caller looked up
        via `self.frame_for(self._row_color_attr(row))` — falls back
        to `font_color`'s key when the per-row knob is unset, so a
        continuous-phase rainbow set on `font_color` keeps its phase
        across visits instead of reading the primary engine tick
        counter. Passed explicitly because this helper doesn't know
        which row it's drawing for.
        """
        if self._has_emoji() and EMOJI_PATTERN.search(text):
            from led_ticker.pixel_emoji import draw_with_emoji

            draw_with_emoji(
                canvas,
                font,
                x,
                baseline_y,
                color,
                text,
                emoji_y=emoji_y,
                max_emoji_height=max_emoji_height,
                frame=frame_count,
            )
        elif hasattr(color, "color_for") and color.per_char:
            # Plain-text per-char path: rainbow / gradient iterate chars.
            draw_text_per_char(
                canvas,
                font,
                x,
                baseline_y,
                text,
                lambda idx, total: color.color_for(frame_count, idx, total),
            )
        else:
            # Whole-string provider or constant Color.
            if hasattr(color, "color_for"):
                color = color.color_for(frame_count, 0, len(text) if text else 1)
            draw_text(canvas, font, x, baseline_y, color, text)

    def _wrap_for_text(self, canvas: Canvas, scale: int) -> Canvas:
        """Return `canvas` wrapped in a ScaledCanvas at the given scale,
        or `canvas` itself when `scale <= 1`. Single point of truth for
        the wrap rule used by both `_play_with_text` (single-row) and
        `_play_with_two_row_text`. The wrapper exists for two reasons,
        which apply differently per font type:

          - HiresFont path: the renderer paints to the unwrapped real
            canvas via `_draw_hires_text`, so the wrapper has no glyph-
            size impact. Its only role is to flip
            `pixel_emoji.draw_with_emoji`'s `isinstance(c, ScaledCanvas)`
            gate so hires emoji (e.g. `:instagram:` 32×32) fires.

          - BDF path: the wrapper's `scale × scale` block-expansion
            renders cells at panel-readable size on bigsign instead of
            native 12 px. Hires emoji gating applies here too as a
            side benefit.

        `content_height = canvas.height // scale` so `text_valign`
        references the panel edge, not a letterboxed sub-region.
        """
        if scale <= 1:
            return canvas
        return ScaledCanvas(canvas, scale=scale, content_height=canvas.height // scale)

    def _render_tick(
        self,
        canvas: Canvas,
        text_canvas: Canvas,
        scroll_pos: int,
        baseline_y: int,
        text_x_left: int,
        text_x_right: int,
    ) -> None:
        """Compose one frame: reset canvas (Clear or Fill bg) + paint
        image + paint border + paint text in the right order for the
        current `text_align`. Border lands AFTER image (to overlay
        image edges — frames the panel) and BEFORE text in the modes
        where text paints on top of image. In skip-black scroll mode
        text walks BEHIND the image silhouette (existing semantics);
        border lands LAST in that path so it stays visible over both
        image silhouette and any scrolled text at the panel edges."""
        reset_canvas(canvas, self.bg_color)

        # Pass the provider (not a materialized Color) so per-char
        # effects survive emoji boundaries. _draw_text materializes
        # internally for the non-emoji path; the emoji path forwards
        # the provider to draw_with_emoji.
        provider = self.font_color

        if self.text_align == "scroll":
            self._draw_text(text_canvas, scroll_pos, baseline_y, provider)
            self._paint_skip_black(canvas)
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
        elif self.text_align == "scroll_over":
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
            self._draw_text(text_canvas, scroll_pos, baseline_y, provider)
        else:
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
            text_x = text_x_left if self.text_align == "left" else text_x_right
            # Apply animation to the visible text. `_visible_text`
            # returns `self.text` when animation is None (no extra
            # work for non-animated widgets) and the typewriter
            # slice when set. Layout (text_x, baseline_y) is already
            # computed against the FULL text width by the caller —
            # we only override the rendered string here.
            text_override = self._visible_text(self.frame_for("animation"), text_canvas)
            self._draw_text(
                text_canvas,
                text_x,
                baseline_y,
                provider,
                text_override=text_override,
            )

    def _render_wrap_tick(
        self,
        canvas: Canvas,
        text_canvas: Canvas,
        scroll_pos: int,
        baseline_y: int,
        text_width: int,
        sep_width: int,
        cycle_width: int,
    ) -> None:
        """Compose one wrap-mode frame: reset → image / border / text
        in the right order for the current text_align, drawing
        ceil(canvas_w / cycle_width) + 1 copies of (text + separator)
        so the panel is never empty.

        `scroll_pos` is the normalized leading-copy x-position in
        [0, cycle_width). Copies render at
        `scroll_pos - cycle_width + i * cycle_width` for
        i in [0, n_copies)."""
        reset_canvas(canvas, self.bg_color)
        provider = self.font_color
        canvas_w = text_canvas.width

        n_copies = (canvas_w + cycle_width - 1) // cycle_width + 1
        start_x = scroll_pos - cycle_width

        def _draw_text_chain() -> None:
            for i in range(n_copies):
                x = start_x + i * cycle_width
                self._draw_text(text_canvas, x, baseline_y, provider)
                if sep_width > 0:
                    self._draw_separator(text_canvas, x + text_width, baseline_y)

        if self.text_align == "scroll":
            _draw_text_chain()
            self._paint_skip_black(canvas)
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
        else:  # scroll_over
            self._paint_image(canvas)
            if self.border is not None:
                self.border.paint(canvas, self.frame_for("border"))
            _draw_text_chain()

    def _render_two_row_tick(
        self,
        real_canvas: Canvas,
        text_canvas: Canvas,
        top: tuple[Any, str, Color, int, int, int],
        bottom: tuple[Any, str, Color, int, int, int],
        top_emoji_cap: int = EMOJI_ROW_CAP,
        bottom_emoji_cap: int = EMOJI_ROW_CAP,
    ) -> None:
        """Compose one two-row frame: reset canvas → paint image to the
        real canvas (native pixels) → paint each row to the text canvas
        (a ScaledCanvas wrapper when `_logical_scale > 1`, else the
        same real canvas).

        `top` / `bottom` are pre-resolved tuples of
        ``(font, text, color, x, baseline_y, emoji_y)`` — caller
        resolves these once outside the tick loop so per-row attribute
        lookups (`_row_font` / `_row_text` / `_row_color`) don't run
        every frame.

        Text/emoji draw via the wrapper so:
          - hires emoji (`isinstance(canvas, ScaledCanvas)` gate in
            `pixel_emoji.draw_with_emoji`) fires correctly,
          - BDF text gets the wrapper's `scale × scale` block expansion
            instead of rendering at tiny native size on bigsign.

        Image still paints to `real_canvas` (unwrapped) so each pixel
        of the source maps to one LED — this is the whole reason image
        widgets exist as a separate path.
        """
        reset_canvas(real_canvas, self.bg_color)
        self._paint_image(real_canvas)
        if self.border is not None:
            self.border.paint(real_canvas, self.frame_for("border"))
        self._draw_row_text(
            text_canvas,
            *top,
            frame_count=self.frame_for(self._row_color_attr(0)),
            max_emoji_height=top_emoji_cap,
        )
        self._draw_row_text(
            text_canvas,
            *bottom,
            frame_count=self.frame_for(self._row_color_attr(1)),
            max_emoji_height=bottom_emoji_cap,
        )

    def _render_two_row_wrap_tick(
        self,
        real_canvas: Canvas,
        text_canvas: Canvas,
        top: tuple[Any, str, Any, int, int, int],
        bottom_font: Any,
        bottom_text: str,
        bottom_color: Any,
        bottom_baseline: int,
        bottom_emoji_y: int,
        scroll_pos: int,
        bottom_width: int,
        sep_width: int,
        cycle_width: int,
        top_emoji_cap: int = EMOJI_ROW_CAP,
        bottom_emoji_cap: int = EMOJI_ROW_CAP,
    ) -> None:
        """One wrap-mode tick: image + top (held) + bottom (multi-copy).

        Mirrors `_render_two_row_tick` but the bottom row renders as
        n_copies of (bottom_text + separator) at
        `scroll_pos - cycle_width + i * cycle_width` — same pattern as
        the v1 single-row `_render_wrap_tick`.

        Top tuple shape matches `_render_two_row_tick`:
            (font, text, color, x, baseline_y, emoji_y)
        """
        reset_canvas(real_canvas, self.bg_color)
        self._paint_image(real_canvas)
        if self.border is not None:
            self.border.paint(real_canvas, self.frame_for("border"))

        # Top row: single draw, held at its alignment x.
        self._draw_row_text(
            text_canvas,
            *top,
            frame_count=self.frame_for(self._row_color_attr(0)),
            max_emoji_height=top_emoji_cap,
        )

        # Bottom row: n_copies of (text + separator).
        canvas_w = text_canvas.width
        n_copies = (canvas_w + cycle_width - 1) // cycle_width + 1
        start_x = scroll_pos - cycle_width

        for i in range(n_copies):
            x = start_x + i * cycle_width
            # bottom_text body
            self._draw_row_text(
                text_canvas,
                bottom_font,
                bottom_text,
                bottom_color,
                x,
                bottom_baseline,
                bottom_emoji_y,
                frame_count=self.frame_for(self._row_color_attr(1)),
                max_emoji_height=bottom_emoji_cap,
            )
            # separator (whole-string, parameterized helper)
            if sep_width > 0:
                self._draw_separator(
                    text_canvas,
                    x + bottom_width,
                    bottom_baseline,
                    font=bottom_font,
                    separator=self.bottom_text_separator,
                    explicit_provider=self.bottom_text_separator_color,
                    explicit_frame_key="bottom_text_separator_color",
                    inherit_provider=bottom_color,
                    inherit_frame_key=self._row_color_attr(1),
                )

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
        from sum(durations)*play_count; still: from hold_time), then calls
        this. Single-frame stills inherit `_pick_frame_for_elapsed` as
        a no-op; gif overrides it to advance `_current_frame_idx` per
        tick from the elapsed time.

        Dispatches on `_is_two_row()` — when `bottom_text` is set, the
        widget runs a held-top + scrolling-bottom loop that mirrors
        TwoRowMessage's contract. Otherwise the existing single-row
        path applies (unchanged for back-compat).
        """
        if self._is_two_row():
            return await self._play_with_two_row_text(real_canvas, frame, n_ticks)
        canvas = real_canvas

        # Resolve the wrap scale. Two concerns share this knob:
        #   - BDF glyph size: the wrapper block-expands BDF cells by
        #     `wrap_scale`, so it must equal `block_scale_for_font_size`.
        #   - Hi-res emoji gate: `pixel_emoji.draw_with_emoji` checks
        #     `isinstance(canvas, ScaledCanvas)` to decide whether to
        #     paint hires sprites. Any wrap > 1 satisfies it.
        # For BDF: `block_scale` handles both (wraps the cell to match
        # font_size; emoji gate fires if scale > 1).
        # For HiresFont: glyphs paint to the unwrapped real canvas via
        # `_draw_hires_text` regardless of wrap; `block_scale` is always
        # 1 (no glyph effect). Wrap at `_logical_scale` so the emoji
        # gate fires on bigsign — that's the whole point of this path.
        font_size = self._resolved_font_size()
        block_scale = block_scale_for_font_size(self.font, font_size)
        wrap_scale = (
            self._logical_scale if isinstance(self.font, _HiresFont) else block_scale
        )
        text_canvas: Canvas = self._wrap_for_text(canvas, wrap_scale)
        text_w = text_canvas.width
        text_h = text_canvas.height
        # The logical text_canvas must accommodate the font's line
        # height. Raise early instead of silently clipping glyphs
        # (which surfaces as missing/cut text). `safe_scale` returns
        # the wrapper scale when wrapped, 1 otherwise — same primitive
        # used by `TwoRowMessage` and friends.
        font_scale = safe_scale(text_canvas)
        font_lh_logical = font_line_height_logical(self.font, font_scale)
        if text_h < font_lh_logical:
            raise ValueError(
                f"font_size={font_size} (block_scale={block_scale}, "
                f"section logical scale={self._logical_scale}) leaves "
                f"text_canvas only {text_h} rows on a {canvas.height}-tall "
                f"panel — font requires {font_lh_logical} logical rows. "
                f"Reduce font_size or use a taller panel."
            )
        baseline_y = self._baseline_y(text_canvas)

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
        wrap_mode = scrolling and self.text_wrap

        # Wrap-mode constants: cycle_width is one full (text+sep)
        # repeat; sep_width is needed by `_render_wrap_tick` to
        # place the separator after each text copy.
        sep_width = self._measure_separator(text_canvas) if wrap_mode else 0
        cycle_width = (text_width + sep_width) if wrap_mode else 0

        if not scrolling:
            scroll_pos = 0
            scroll_step = 0
        elif wrap_mode:
            # Initial scroll_pos in [0, cycle_width): the leading copy
            # starts flush-left. Direction is the step sign.
            scroll_pos = 0
            scroll_step = 1 if self.scroll_direction == "right" else -1
        elif self.scroll_direction == "right":
            scroll_pos = -text_width
            scroll_step = 1
        else:  # "left"
            scroll_pos = text_w
            scroll_step = -1

        # Marquee-traversal floor: extend n_ticks so the marquee
        # always completes at least one full pass (off-right → off-
        # left or vice-versa). Without this, the source's natural
        # duration (play_count × loop_ms, or hold_time for stills)
        # could end mid-marquee — which got worse when hi-res fonts
        # arrived because the same string is 2-3× wider per char than
        # BDF, so a duration that fit the BDF marquee no longer fits
        # the hi-res one. `text_loops` raises the floor further (e.g.
        # text_loops=2 → at least two traversals); the implicit
        # minimum is now 1 instead of 0. Set scroll_speed_ms to
        # control marquee pace; the underlying duration extends to
        # match. To opt out (rare), reduce font_size so the text
        # naturally fits.
        if scrolling:
            # In wrap mode, one "loop" = one cycle (text + sep)
            # rather than one full off-right→off-left traversal.
            ticks_per_text_loop = cycle_width if wrap_mode else text_w + text_width
            min_loops = max(1, self.text_loops)
            n_ticks = max(n_ticks, min_loops * ticks_per_text_loop)

        # Static-text fast path: image + text are constant across ticks,
        # so paint once and hold instead of redrawing N times. Only
        # safe when the source itself is static (`_is_static()`) — for
        # animated sources (multi-frame gifs) we'd freeze the gif on
        # frame 0 by skipping the per-tick `_pick_frame_for_elapsed`.
        # Also bypass when `font_color` is not frame_invariant
        # (Rainbow / ColorCycle): the rendered output changes per
        # frame even though image + text geometry are static, so the
        # per-tick loop must run to advance the provider's frame
        # counter — otherwise the rainbow looks like a frozen gradient.
        # `frame_invariant` is set on each ColorProvider class:
        # _ConstantColor, Random, Gradient = True; Rainbow, ColorCycle
        # = False. New providers default to False (conservative — opt
        # in via the class attribute) for safety.
        text_is_wrapped = isinstance(text_canvas, ScaledCanvas)
        color_is_static = getattr(self.font_color, "frame_invariant", False)
        border_is_static = (
            getattr(self.border, "frame_invariant", True) if self.border else True
        )

        if (
            not scrolling
            and self.text_loops == 0
            and self._is_static()
            and color_is_static
            and border_is_static
            and self.animation is None
        ):
            self._render_tick(
                canvas,
                text_canvas,
                scroll_pos,
                baseline_y,
                text_x_left,
                text_x_right,
            )
            canvas = frame.swap(canvas)
            # Even though we return immediately, follow the new back-
            # buffer so the wrapper identity stays in sync — guards
            # against a future change adding work after the swap and
            # silently regressing CLAUDE.md constraint #10.
            if text_is_wrapped:
                text_canvas.real = canvas
            await asyncio.sleep(n_ticks * tick_seconds)
            return canvas

        loop = asyncio.get_running_loop()
        for tick in range(n_ticks):
            t0 = loop.time()
            self._pick_frame_for_elapsed(tick * tick_ms)
            # Advance the widget's own frame counter so ColorProviders
            # (rainbow, color_cycle) animate over time. Without this,
            # the provider sees `_frame_count` stuck at its visit
            # initial value and the rainbow renders as a static
            # gradient. Mirrors `ticker._advance_frame_if_supported`'s
            # placement in `_swap_and_scroll` (advance BEFORE draw).
            self.advance_frame()
            if wrap_mode:
                self._render_wrap_tick(
                    canvas,
                    text_canvas,
                    scroll_pos,
                    baseline_y,
                    text_width,
                    sep_width,
                    cycle_width,
                )
            else:
                self._render_tick(
                    canvas,
                    text_canvas,
                    scroll_pos,
                    baseline_y,
                    text_x_left,
                    text_x_right,
                )
            canvas = frame.swap(canvas)
            # Follow the new back-buffer so next tick paints to the
            # correct canvas (CLAUDE.md hardware constraint #10).
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))

            if scrolling:
                scroll_pos += scroll_step
                if wrap_mode:
                    # Python's % on negative numbers with positive
                    # divisor returns a non-negative result — works
                    # for both scroll_direction values. Defensive
                    # `if cycle_width:` guard: validation rejects
                    # `text_wrap=True` with empty text (fix #5), so
                    # cycle_width should always be > 0 here. Keep the
                    # guard so a future code path that produces a
                    # zero cycle doesn't crash with ZeroDivisionError.
                    if cycle_width:
                        scroll_pos %= cycle_width
                elif scroll_step < 0 and scroll_pos + text_width <= 0:
                    scroll_pos = text_w
                elif scroll_step > 0 and scroll_pos >= text_w:
                    scroll_pos = -text_width

        return canvas

    async def _play_with_two_row_text(
        self,
        real_canvas: Canvas,
        frame: Any,
        n_ticks: int,
    ) -> Canvas:
        """Two-row text-overlay loop: held top row + scroll-on-overflow
        bottom row, painted over the image.

        Mirrors `TwoRowMessage`'s contract: the top row is held at its
        chosen alignment and never scrolls; the bottom row is held if
        it fits the canvas width, otherwise auto-scrolls left with the
        marquee auto-floor (at least one full traversal even if the
        source's natural duration is shorter). The image always paints
        underneath the text (image-on-bottom; the text never disappears
        behind a transparent silhouette in two-row mode — that's the
        single-row `text_align="scroll"` mode's job).
        """
        canvas = real_canvas

        # Wrap once via `_wrap_for_text` (shared with single-row path)
        # so band-height / baseline / aligned_x math operates in LOGICAL
        # units against `text_canvas` — same coordinate system as
        # `TwoRowMessage`. Image painting still goes to `real_canvas`
        # (unwrapped) via `_paint_image`. See `_wrap_for_text` for why
        # the wrap exists per font type. Read scale from the wrapper
        # afterwards via `safe_scale` so we use the same primitive as
        # `TwoRowMessage` (instead of the `_logical_scale` stash, which
        # is kept narrowly as the wrap-construction signal).
        text_canvas: Canvas = self._wrap_for_text(canvas, self._logical_scale)
        scale = safe_scale(text_canvas)
        canvas_w = text_canvas.width
        canvas_h = text_canvas.height

        top_h, bottom_h = resolve_band_heights(canvas_h, self.top_row_height)

        # Validate each row's font fits its band, in LOGICAL units —
        # `font_line_height_logical` ceil-divides hires real-px metrics
        # by scale, BDF metrics pass through. Same check shape as
        # `TwoRowMessage.draw`.
        for row, label, band_h in ((0, "top", top_h), (1, "bottom", bottom_h)):
            font = self._row_font(row)
            font_lh = font_line_height_logical(font, scale)
            if font_lh > band_h:
                raise ValueError(
                    f"{label} font line-height ({font_lh} logical rows) "
                    f"exceeds the per-row band ({band_h} rows on a "
                    f"{canvas_h}-tall canvas). Pick a smaller font_size, "
                    f"raise top_row_height (current {self.top_row_height!r}), "
                    f"or use a BDF alias (5x8, 6x12)."
                )

        # Resolve all per-row attributes ONCE (font / text / color /
        # alignment / offsets) — these are invariant for the widget's
        # lifetime, so the per-tick loop reads from local tuples
        # instead of calling `_row_*` methods every frame.
        top_font = self._row_font(0)
        bottom_font = self._row_font(1)
        top_text = self._row_text(0)
        bottom_text = self._row_text(1)
        # Resolve providers for both rows. _row_color() returns a
        # provider (already coerced in _validate_common); pass it
        # through to _draw_row_text without materializing so per-char
        # effects survive emoji boundaries within each row. The
        # defensive _ConstantColor wrap covers any path that bypasses
        # _validate_common.
        top_color = self._row_color(0)
        if not hasattr(top_color, "color_for"):
            top_color = _ConstantColor(top_color)

        bottom_color = self._row_color(1)
        if not hasattr(bottom_color, "color_for"):
            bottom_color = _ConstantColor(bottom_color)

        # Per-row emoji caps. When the band is taller than the static
        # EMOJI_ROW_CAP (8 logical), raise the cap so a hi-res emoji
        # that fits the band visually is allowed to render at hi-res.
        # Default content_height = 16 with 50/50 split → band = 8 = cap,
        # so existing demos behave identically; bumping content_height
        # or top_row_height enables hi-res emoji on the affected row.
        # Computed BEFORE row_layout so each call receives the correct cap
        # as sprite_logical_height (mirrors two_row.py's ordering).
        top_emoji_cap = max(EMOJI_ROW_CAP, top_h)
        bottom_emoji_cap = max(EMOJI_ROW_CAP, bottom_h)

        top_baseline, top_emoji_y = row_layout(
            text_canvas,
            top_font,
            band_height=top_h,
            band_offset=0,
            sprite_logical_height=top_emoji_cap,
        )
        bottom_baseline, bottom_emoji_y = row_layout(
            text_canvas,
            bottom_font,
            band_height=bottom_h,
            band_offset=top_h,
            sprite_logical_height=bottom_emoji_cap,
        )
        top_baseline += self._row_text_y_offset(0)
        bottom_baseline += self._row_text_y_offset(1)
        top_emoji_y += self._row_emoji_y_offset(0)
        bottom_emoji_y += self._row_emoji_y_offset(1)

        # Measure both rows once (logical px); drives alignment + scroll.
        top_width = self._measure_row_text(
            text_canvas, 0, max_emoji_height=top_emoji_cap
        )
        bottom_width = self._measure_row_text(
            text_canvas, 1, max_emoji_height=bottom_emoji_cap
        )

        top_x = aligned_x(canvas_w, top_width, self._row_align(0))

        # Wrap mode forces the scroll branch regardless of overflow.
        # cycle_width is one full (bottom_text + separator) repeat; the
        # marquee auto-floor reinterprets as N cycle traversals (mirrors
        # v1 single-row wrap).
        wrap_mode = self.bottom_text_wrap
        sep_width = (
            self._measure_separator(
                text_canvas,
                font=bottom_font,
                separator=self.bottom_text_separator,
            )
            if wrap_mode
            else 0
        )
        cycle_width = (bottom_width + sep_width) if wrap_mode else 0

        # scroll_through forces the offscreen marquee branch regardless of
        # whether bottom_text overflows. Mutex with wrap_mode is enforced
        # at config-load, so the wrap branch below remains independent.
        force_scroll_through = self.bottom_text_scroll == "scroll_through"
        bottom_scrolls = bottom_width > canvas_w or wrap_mode or force_scroll_through
        if wrap_mode:
            scroll_pos = 0
            ticks_per_loop = cycle_width
            min_loops = max(1, self.text_loops)
            n_ticks = max(n_ticks, min_loops * ticks_per_loop)
        elif bottom_scrolls:
            scroll_pos = canvas_w  # start off-right, scroll left
            # Marquee auto-floor — same contract as the single-row path.
            ticks_per_loop = canvas_w + bottom_width
            min_loops = max(1, self.text_loops)
            n_ticks = max(n_ticks, min_loops * ticks_per_loop)
        else:
            scroll_pos = aligned_x(canvas_w, bottom_width, self._row_align(1))

        tick_ms = max(MIN_SCROLL_SPEED_MS, self.scroll_speed_ms)
        tick_seconds = tick_ms / 1000

        # Top tuple is fully invariant — bottom changes per tick when
        # scrolling, so we rebuild it inside the loop with the current
        # `scroll_pos`. Tuple shape:
        # (font, text, color, x, baseline_y, emoji_y).
        top_tuple = (top_font, top_text, top_color, top_x, top_baseline, top_emoji_y)

        # Track the innermost wrapper's `.real` so we can re-anchor it
        # after each SwapOnVSync (constraint #10 in CLAUDE.md). Without
        # this, the 2nd tick paints to the displayed front buffer.
        text_is_wrapped = isinstance(text_canvas, ScaledCanvas)
        # Same fast-path gate as the single-row path: bypass when EITHER
        # row uses a non-frame-invariant provider so animated colors
        # (rainbow / color_cycle) keep ticking.
        colors_are_static = getattr(top_color, "frame_invariant", False) and getattr(
            bottom_color, "frame_invariant", False
        )
        border_is_static = (
            getattr(self.border, "frame_invariant", True) if self.border else True
        )

        if (
            not bottom_scrolls
            and self._is_static()
            and self.text_loops == 0
            and colors_are_static
            and border_is_static
        ):
            bottom_tuple = (
                bottom_font,
                bottom_text,
                bottom_color,
                scroll_pos,
                bottom_baseline,
                bottom_emoji_y,
            )
            self._render_two_row_tick(
                canvas,
                text_canvas,
                top_tuple,
                bottom_tuple,
                top_emoji_cap=top_emoji_cap,
                bottom_emoji_cap=bottom_emoji_cap,
            )
            canvas = frame.swap(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(n_ticks * tick_seconds)
            return canvas

        loop = asyncio.get_running_loop()
        for tick in range(n_ticks):
            t0 = loop.time()
            self._pick_frame_for_elapsed(tick * tick_ms)
            # Advance the per-widget frame counter so ColorProviders
            # animate. See single-row path for rationale.
            self.advance_frame()
            if wrap_mode:
                self._render_two_row_wrap_tick(
                    canvas,
                    text_canvas,
                    top_tuple,
                    bottom_font,
                    bottom_text,
                    bottom_color,
                    bottom_baseline,
                    bottom_emoji_y,
                    scroll_pos,
                    bottom_width,
                    sep_width,
                    cycle_width,
                    top_emoji_cap=top_emoji_cap,
                    bottom_emoji_cap=bottom_emoji_cap,
                )
            else:
                bottom_tuple = (
                    bottom_font,
                    bottom_text,
                    bottom_color,
                    scroll_pos,
                    bottom_baseline,
                    bottom_emoji_y,
                )
                self._render_two_row_tick(
                    canvas,
                    text_canvas,
                    top_tuple,
                    bottom_tuple,
                    top_emoji_cap=top_emoji_cap,
                    bottom_emoji_cap=bottom_emoji_cap,
                )
            canvas = frame.swap(canvas)
            if text_is_wrapped:
                text_canvas.real = canvas
            else:
                text_canvas = canvas
            await asyncio.sleep(max(0.0, tick_seconds - (loop.time() - t0)))
            if wrap_mode:
                scroll_pos -= 1
                if cycle_width:
                    scroll_pos %= cycle_width
            elif bottom_scrolls:
                scroll_pos -= 1
                if scroll_pos + bottom_width <= 0:
                    scroll_pos = canvas_w

        return canvas

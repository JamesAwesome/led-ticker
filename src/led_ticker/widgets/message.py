"""Static text widgets: TickerMessage and SegmentMessage.

TickerCountdown has moved to ``widgets/count.py``; it is re-exported from
here for backwards compatibility.
"""

import logging
from typing import Any

import attrs

from led_ticker._types import Canvas, Color, DrawResult, Font
from led_ticker.color_providers import ColorProvider, _ConstantColor
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.drawing import compute_baseline, compute_cursor, get_text_width
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.fonts.hires_loader import HiresFont
from led_ticker.pixel_emoji import EMOJI_PATTERN
from led_ticker.rotate import make_rotation_surface
from led_ticker.scaled_canvas import is_scaled
from led_ticker.sources import TokenizedField, get_data_registry
from led_ticker.text_render import draw_text, draw_text_per_char
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase


def _coerce_font_color(value: Any) -> ColorProvider:
    """Coerce a raw Color or ColorProvider to a ColorProvider.

    Wraps ``graphics.Color`` in ``_ConstantColor`` so ``draw()`` can
    always call ``provider.color_for(...)``.  Handles direct construction
    (test paths, or data-widget plugins building TickerMessages with
    ``font_color=Color(...)``) as well as the already-coerced TOML path.
    """
    if not hasattr(value, "color_for"):
        return _ConstantColor(value)
    return value


@register("message")
@attrs.define
class TickerMessage(FrameAwareBase):
    """A static text message for the LED display."""

    text: str
    font: Font = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: ColorProvider = attrs.field(
        default=attrs.Factory(lambda: DEFAULT_COLOR),
        converter=_coerce_font_color,
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    center: bool = True
    padding: int = 6
    hold_time: float = 0.0
    animation: Any | None = attrs.field(default=None, kw_only=True)
    # Optional perimeter border effect (rainbow chase, constant color,
    # etc.). When set, paints a 1-px ring around the panel perimeter
    # at PHYSICAL resolution (bypasses ScaledCanvas block expansion)
    # before the text is drawn. None = no border (default behavior).
    # The widget passes `self.frame_for("border")` so the effect's
    # per-effect counter advances independently — transitions freeze
    # the chase and visit-resets honor `restart_on_visit`. See
    # `borders.py` for available effects.
    border: Any | None = attrs.field(default=None, kw_only=True)
    _content_width: int = attrs.field(init=False, default=-1)
    _has_emoji: bool = attrs.field(init=False, default=False)
    _baseline_y: int = attrs.field(init=False, default=-1)
    # Inline-value-token state. `_token` scans `self.text` once at
    # construction for `:source.id:` tokens (emoji slugs are skipped by
    # TokenizedField). `_resolved_text` caches the substituted string
    # the last time we resolved against the live registry. A field with
    # no source tokens reports `has_tokens == False` and the widget is
    # byte-identical to today (every token step is gated on it).
    _token: TokenizedField | None = attrs.field(init=False, default=None)
    _resolved_text: str = attrs.field(init=False, default="")
    # True for the duration of a typewriter reveal so resolution stays
    # frozen across the reveal (stable slice length + stable per-char
    # hue anchor). Cleared at visit reset and when the reveal completes.
    _anim_resolution_lock: bool = attrs.field(init=False, default=False)
    # Guard for the hires-font rotation warning: emitted once per instance
    # so the log doesn't flood on every tick. Set True after the first
    # warning; subsequent draws skip the log call.
    _warned_hires_rotation: bool = attrs.field(init=False, default=False)
    # Cached RotationSurface (construct-once per widget; rebuilt when
    # scale/dims/content_height change via .matches()). None until the
    # first rotating draw.
    _rotation_surface: Any = attrs.field(init=False, default=None)

    def __attrs_post_init__(self) -> None:
        # `_has_emoji` is computed on the RAW text — emoji slugs survive
        # token substitution, so the emoji render path must still fire.
        self._has_emoji = bool(EMOJI_PATTERN.search(self.text))
        self._token = TokenizedField(self.text)
        self._resolved_text = self.text

    def _resolve_into_full_text(self) -> str:
        """Return the display string, resolving tokens against the live
        registry unless resolution is currently frozen.

        Freeze sources: `_resolution_locked` (scroll / transition, set on
        the FrameAwareBase) and `_anim_resolution_lock` (an in-flight
        typewriter reveal). While frozen we reuse the cached substituted
        string so content width / slice length / hue anchor stay stable.
        """
        if self._token is None or not self._token.has_tokens:
            return self.text
        frozen = self._resolution_locked or self._anim_resolution_lock
        if not frozen:
            resolved, changed = self._token.resolve(get_data_registry())
            if changed:
                # Invalidate the width cache so the next measure
                # re-decides hold-vs-scroll / re-centers (held re-center).
                self._content_width = -1
            self._resolved_text = resolved
        return self._resolved_text

    def resolve_tokens_now(self) -> None:
        """Force a token resolve and invalidate the width cache.

        Called by the engine immediately BEFORE a scroll's `stop_pos` is
        computed so the scroll measures the current value, then resolution
        is locked for the scroll loop. No-op for non-token widgets."""
        if self._token is None or not self._token.has_tokens:
            return
        resolved, _ = self._token.resolve(get_data_registry())
        self._resolved_text = resolved
        self._content_width = -1

    def _effect_total_chars(self, attr_name: str) -> int:
        """Per-effect-kind counts mirroring TickerMessage.draw's anchors:
        animation → raw len (frame_for slices the raw string); color
        providers → count_text_chars on the emoji path (matching the
        draw_with_emoji total_chars anchor), else len."""
        full_text = self._resolve_into_full_text()
        if attr_name == "animation":
            return max(1, len(full_text))
        if self._has_emoji:
            from led_ticker.pixel_emoji import count_text_chars  # noqa: PLC0415

            return max(1, count_text_chars(full_text))
        return max(1, len(full_text))

    def reset_frame(self) -> None:
        # Visit entry: drop any typewriter resolution lock so the next
        # visit's reveal re-resolves from the current value.
        super().reset_frame()
        self._anim_resolution_lock = False
        # Invalidate the snapshot so the next spin re-draws the artifact.
        # This is the ONLY invalidation site (spec R3 lifecycle H3): the
        # artifact is NOT invalidated by rotation==0 mid-spin so a passing
        # zero-angle frame can't discard an artifact that will be needed
        # on the very next frame.
        if self._rotation_surface is not None:
            self._rotation_surface.invalidate()

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        # Allow callers to override font_color, but coerce raw Color to
        # provider for uniform handling below.
        if font_color is not None and not hasattr(font_color, "color_for"):
            font_color = _ConstantColor(font_color)
        provider: ColorProvider = font_color or self.font_color

        # Resolve inline value tokens (when not frozen). For a non-token
        # message this returns `self.text` unchanged — byte-identical to
        # today. For a typewriter reveal we lock resolution for the whole
        # reveal so the sliced string length stays stable; the lock is set
        # BEFORE the first resolve of the visit so the reveal runs against
        # a single substituted string.
        if (
            self.animation is not None
            and self._token is not None
            and self._token.has_tokens
            and not self._anim_resolution_lock
        ):
            # Resolve once at the start of the reveal, then freeze.
            self.resolve_tokens_now()
            self._anim_resolution_lock = True
        full_text = self._resolve_into_full_text()

        # If animation is set, ask it for the slice. Animations don't
        # currently override cursor position (Bounce was removed); if a
        # future animation needs that, re-add the override branch.
        if self.animation is not None:
            if self._content_width < 0:
                # Measure once for animation use; emoji path measures below.
                if self._has_emoji:
                    from led_ticker.pixel_emoji import measure_width

                    self._content_width = measure_width(self.font, full_text, canvas)
                else:
                    self._content_width = get_text_width(
                        self.font, full_text, padding=0, canvas=canvas
                    )
            anim_frame = self.animation.frame_for(
                self.frame_for("animation"),
                full_text,
                canvas.width,
                self._content_width,
            )
            visible_text = anim_frame.visible_text
            rotation = getattr(anim_frame, "rotation", 0.0)
        else:
            visible_text = full_text
            rotation = 0.0

        if self._content_width < 0:
            if self._has_emoji:
                from led_ticker.pixel_emoji import measure_width

                self._content_width = measure_width(
                    self.font,
                    full_text,
                    canvas,
                )
            else:
                self._content_width = get_text_width(
                    self.font, full_text, padding=0, canvas=canvas
                )
        content_width = self._content_width
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, center=self.center
        )
        # Capture the start position BEFORE the draw_* branches mutate
        # cursor_pos. Used below to recompute the returned cursor_pos
        # against full content_width when an animation is sliced
        # `visible_text` shorter than the full message.
        start_pos = cursor_pos

        if self._baseline_y < 0:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
        baseline_y = self._baseline_y

        # Paint border BEFORE text so text overlaps the border on
        # collision (border frames the panel; text floats inside).
        # Reads its per-effect counter via `frame_for("border")` for
        # animation — transitions freeze it (no chase phase drift)
        # and visit resets honor `restart_on_visit`. Painted at
        # physical resolution so a 1-px border on bigsign is 1 LED,
        # not a 4×4 block.
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        # Rotation seam (propeller spec): non-zero rotation redirects the
        # text branches into a cached RotationSurface, then blits at
        # physical resolution. The border above stays unrotated on purpose
        # (it frames the panel, not the text).
        # Guard (rule 59/63): scale-1 + HiresFont can't rotate — a bare
        # PixelBuffer can't host real-pixel glyphs and produces garbage.
        # On scaled canvases hires fonts flow through the surface like BDF.
        #
        # Snapshot-once lifecycle (spec R2.4 + R3, resolution H3):
        #   - First rotating frame this visit: surface.clear() + draw
        #     branches + surface.snapshot().
        #   - Subsequent rotating frames: skip the branches entirely;
        #     blit the cached artifact.
        #   - rotation == 0 frames (including exact-0 mid-spin): live
        #     draw to canvas; artifact NOT invalidated (H3 fix — the
        #     post-mod angle can pass through 0 each revolution).
        #   - Invalidation: reset_frame() only (visit boundary).
        rotate_surface = None
        _snapshot_needed = False
        if rotation % 360 != 0:
            if not is_scaled(canvas) and isinstance(self.font, HiresFont):
                # scale-1 + hires: the bare buffer can't host real-pixel
                # glyphs (rule 59 territory); draw unrotated + warn once.
                if not self._warned_hires_rotation:
                    logging.warning(
                        "%s: rotation animation ignored — hires fonts don't "
                        "rotate on scale-1 displays (see validate rules 59 "
                        "and 63); switch to a BDF font to spin this widget",
                        type(self).__name__,
                    )
                    self._warned_hires_rotation = True
            else:
                if self._rotation_surface is None or not self._rotation_surface.matches(
                    canvas
                ):
                    # A mismatched surface has no valid snapshot — the new
                    # surface starts with has_snapshot=False, so the branch
                    # draw will happen this frame.
                    self._rotation_surface = make_rotation_surface(canvas)
                rotate_surface = self._rotation_surface
                if not rotate_surface.has_snapshot:
                    # First rotating frame this spin: prepare for branch draw.
                    rotate_surface.clear()
                    _snapshot_needed = True
                # else: artifact is valid; branches are skipped this frame.

        draw_canvas: Any = (
            rotate_surface.target if rotate_surface is not None else canvas
        )

        # Run the text paint branches only when we are either on a live
        # (non-rotating) draw or on the FIRST rotating frame of a spin
        # (_snapshot_needed). On subsequent rotating frames (_snapshot_needed
        # is False) the artifact is already in the surface; skip the branches.
        _run_branches = rotate_surface is None or _snapshot_needed
        if _run_branches:
            if self._has_emoji:
                from led_ticker.pixel_emoji import count_text_chars, draw_with_emoji

                # Per-char providers (rainbow/gradient) survive emoji
                # segments: draw_with_emoji takes the provider directly,
                # renders sprites for emoji slugs, and runs the per-char
                # path on text segments — char_index advances continuously
                # across segments so the rainbow sweep doesn't reset at
                # each :slug:. `total_chars` is anchored to the FULL
                # message's text-char count (excluding emoji slugs) so
                # typewriter mid-cycle doesn't shift each char's hue as
                # more chars reveal — char N's hue at frame=t is the same
                # hue char N will have when typewriter completes. Mirrors
                # the image-widget contract in `_BaseImageWidget._draw_text`.
                cursor_pos += draw_with_emoji(
                    draw_canvas,
                    self.font,
                    cursor_pos,
                    baseline_y,
                    provider,
                    visible_text,
                    y_offset=y_offset,
                    frame=self.frame_for("font_color"),
                    total_chars=count_text_chars(full_text),
                )
            elif provider.per_char:
                # Per-char rendering: iterate visible_text, draw each char
                # with its own color (rainbow / gradient). The shared
                # `draw_text_per_char` helper handles the HiresFont
                # real-pixel cursor tracking that avoids the per-char
                # ceil-divide drift. `total_chars=len(self.text)`
                # anchors each char's hue to its position in the FULL
                # text — typewriter mid-cycle reveals char N at the
                # hue char N will have at completion, not a hue
                # compressed to the visible slice. Mirrors the image-
                # widget contract in `_BaseImageWidget._draw_text`.
                cursor_pos += draw_text_per_char(
                    draw_canvas,
                    self.font,
                    cursor_pos,
                    baseline_y + y_offset,
                    visible_text,
                    lambda idx, total: provider.color_for(
                        self.frame_for("font_color"), idx, total
                    ),
                    total_chars=len(full_text),
                )
            else:
                color = provider.color_for(
                    self.frame_for("font_color"), 0, len(visible_text)
                )
                cursor_pos += draw_text(
                    draw_canvas,
                    self.font,
                    cursor_pos,
                    baseline_y + y_offset,
                    color,
                    visible_text,
                )
        cursor_pos += end_padding

        if rotate_surface is not None:
            if _snapshot_needed:
                # Freeze the artifact: one-time per spin after branch draw.
                rotate_surface.snapshot()
            # Pivot on the VISIBLE text extent, not the nominal content
            # center. The buffer holds only the clipped on-canvas window,
            # so for overflowing text (content_width > canvas.width) the
            # naive `start_pos + content_width / 2` lands off-canvas and
            # the rotation swings everything off-screen — the panel goes
            # black for most of the spin (caught in gif validation). For
            # fitting text the clamp is a no-op: visible extent == text
            # extent, pivot == text center.
            visible_left = max(0.0, float(start_pos))
            visible_right = min(
                float(canvas.width), float(start_pos) + float(content_width)
            )
            rotate_surface.blit(canvas, rotation, (visible_left + visible_right) / 2)

        # When an animation is sliced (typewriter at frame=0 shows just
        # "R"), the engine in `_swap_and_scroll` checks
        # `cursor_pos > canvas.width` ONCE to decide hold vs scroll.
        # If cursor_pos reflects only the slice, the engine picks the
        # held-text path and the message overflows the right edge
        # without ever scrolling. Override cursor_pos to reflect FULL
        # content width so the engine sees the eventual overflow and
        # picks the scroll path; typewriter then completes during the
        # pre-scroll hold and the scroll runs afterwards.
        if self.animation is not None:
            cursor_pos = start_pos + content_width + end_padding

        return canvas, cursor_pos


class SegmentMessage:
    """A line of color-coded text segments, optionally centered.

    Segments are drawn through `draw_with_emoji` so any segment text
    can contain `:flower:` / `:star:` / etc. slugs that render as
    inline pixel-art icons.

    `font_color` is an optional `ColorProvider` override. When set it
    replaces the per-segment colors, allowing a `color_cycle` effect to
    animate the whole message. `advance_frame()` increments the frame
    counter so `_advance_frame_if_supported` in the engine picks it up.
    """

    def __init__(
        self,
        segments: list[tuple[str, Color]],
        padding: int = 6,
        center: bool = False,
        bg_color: Color | None = None,
        font: Font | None = None,
        font_color: Color | ColorProvider | None = None,
    ) -> None:
        self.segments: list[tuple[str, Color]] = segments
        self.padding: int = padding
        self.center: bool = center
        self.bg_color: Color | None = bg_color
        self.font: Font = font if font is not None else FONT_DEFAULT
        self.font_color: Color | ColorProvider | None = font_color
        self._content_width: int = -1
        self._frame_count: int = 0

    def advance_frame(self, *, visit_id: int | None = None) -> None:
        self._frame_count += 1

    def pause_frame(self) -> None:
        pass

    def resume_frame(self) -> None:
        pass

    def reset_frame(self) -> None:
        self._frame_count = 0

    def draw(
        self,
        canvas: Canvas,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        from led_ticker.pixel_emoji import draw_with_emoji, measure_width

        if self._content_width < 0:
            self._content_width = sum(
                measure_width(self.font, text, canvas) for text, _ in self.segments
            )

        content_width = self._content_width
        cursor_pos, end_padding = compute_cursor(
            canvas.width,
            content_width,
            cursor_pos,
            self.padding,
            center=self.center,
        )

        # If a color provider override is set, use it for all segments.
        # This enables color_cycle / rainbow effects on game messages.
        override_color: Color | None = None
        if self.font_color is not None and hasattr(self.font_color, "color_for"):
            override_color = self.font_color.color_for(self._frame_count, 0, 1)

        baseline_y = compute_baseline(self.font, canvas, valign="center")
        for text, seg_color in self.segments:
            color = override_color if override_color is not None else seg_color
            cursor_pos += draw_with_emoji(
                canvas,
                self.font,
                int(cursor_pos),
                y=baseline_y,
                color=color,
                text=text,
                y_offset=y_offset,
            )

        cursor_pos += end_padding
        return canvas, cursor_pos


# TickerCountdown moved to widgets/count.py; keep the historical import path.
from led_ticker.widgets.count import TickerCountdown  # noqa: E402, F401

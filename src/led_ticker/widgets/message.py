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
from led_ticker.lens_render import LensTextRenderer
from led_ticker.pixel_emoji import has_renderable_emoji
from led_ticker.rotate import lens_blit, make_rotation_surface
from led_ticker.scaled_canvas import is_scaled
from led_ticker.sources import (
    TokenizedField,
    build_token_color_override,
    get_data_registry,
)
from led_ticker.widgets import register
from led_ticker.widgets._frame_aware import FrameAwareBase
from led_ticker.widgets._text_run import draw_text_run


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
    # Geometry the cached baseline was computed against (logical height,
    # scale). compute_baseline depends on both; keying the cache means an
    # in-place canvas change on a live widget recomputes instead of
    # reusing a stale baseline. Same guard shape as RotationSurface.matches().
    _baseline_key: tuple[int, int] | None = attrs.field(init=False, default=None)
    # Inline-value-token state. `_token` scans `self.text` once at
    # construction for `:source.id:` tokens (emoji slugs are skipped by
    # TokenizedField). `_resolved_text` caches the substituted string
    # the last time we resolved against the live registry. A field with
    # no source tokens reports `has_tokens == False` and the widget is
    # byte-identical to today (every token step is gated on it).
    _token: TokenizedField | None = attrs.field(init=False, default=None)
    _resolved_text: str = attrs.field(init=False, default="")
    # Frozen snapshot of `resolve_segments` taken at the SAME registry read
    # as `_resolved_text`. The colored-token override is built from this (not
    # a live re-resolve) so its length stays consistent with the frozen
    # `_resolved_text` — a value that changes length under a scroll /
    # transition / typewriter freeze can't skew the override off the rendered
    # text (M1). None until the first resolve of a token widget.
    _resolved_segments: list[tuple[Any, Any, bool]] | None = attrs.field(
        init=False, default=None
    )
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
    # Guard for the hires-font lens warning (scale-1 unwarped fallback):
    # emitted once per instance so the log doesn't flood. Same shape as
    # `_warned_hires_rotation`.
    _warned_hires_lens: bool = attrs.field(init=False, default=False)
    # Stationary-lens renderer (fisheye spec §2-§3): owns the construct-once
    # strip buffer, draw target, and blit wrapper. Shared with image/gif
    # widgets via `led_ticker.lens_render.LensTextRenderer` — one instance
    # per widget, geometry lives entirely in the renderer.
    _lens_renderer: LensTextRenderer = attrs.field(init=False, factory=LensTextRenderer)

    def __attrs_post_init__(self) -> None:
        # `_has_emoji` is computed on the RAW text — emoji slugs survive
        # token substitution, so the emoji render path must still fire.
        self._has_emoji = has_renderable_emoji(self.text)
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
            # Read segments from the SAME registry object as resolve() so the
            # override snapshot can't diverge from the resolved string.
            registry = get_data_registry()
            resolved, changed = self._token.resolve(registry)
            if changed:
                # Invalidate the width cache so the next measure
                # re-decides hold-vs-scroll / re-centers (held re-center).
                self._content_width = -1
            self._resolved_text = resolved
            self._resolved_segments = self._token.resolve_segments(registry)
        return self._resolved_text

    def resolve_tokens_now(self) -> None:
        """Force a token resolve and invalidate the width cache.

        Called by the engine immediately BEFORE a scroll's `stop_pos` is
        computed so the scroll measures the current value, then resolution
        is locked for the scroll loop. No-op for non-token widgets."""
        if self._token is None or not self._token.has_tokens:
            return
        registry = get_data_registry()
        resolved, _ = self._token.resolve(registry)
        self._resolved_text = resolved
        self._resolved_segments = self._token.resolve_segments(registry)
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
            lens = getattr(anim_frame, "lens", None)
        else:
            visible_text = full_text
            rotation = 0.0
            lens = None

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

        baseline_key = (canvas.height, getattr(canvas, "scale", 1))
        if self._baseline_key != baseline_key:
            self._baseline_y = compute_baseline(self.font, canvas, valign="center")
            self._baseline_key = baseline_key
        baseline_y = self._baseline_y

        # Lens seam (fisheye spec §3): a stationary fisheye lens redirects the
        # text through a render-resolution strip buffer + `lens_blit`, rendered
        # FRESH every tick so colors stay live (no snapshot). Sibling of the
        # rotation branch below. Precedence: rotation WINS when both are set
        # (`rotation % 360 == 0` gate) — a spinning lens is undefined, so the
        # rotation branch takes it. Guard (rule 64): scale-1 + HiresFont can't
        # warp a bare buffer's real-pixel glyphs, so warn once and fall through
        # to the normal unwarped draw path below.
        if lens is not None and rotation % 360 == 0:
            if not is_scaled(canvas) and isinstance(self.font, HiresFont):
                if not self._warned_hires_lens:
                    logging.warning(
                        "%s: fisheye lens ignored — hires fonts don't warp on "
                        "scale-1 displays (see validate rule 64); the text "
                        "draws normally. Use a BDF font, or a scaled (bigsign) "
                        "display.",
                        type(self).__name__,
                    )
                    self._warned_hires_lens = True
                # fall through to the normal unwarped draw path.
            else:
                return self._draw_lensed(
                    canvas,
                    lens,
                    provider,
                    visible_text,
                    full_text,
                    start_pos,
                    content_width,
                    baseline_y,
                    end_padding,
                    y_offset,
                )

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

        # Per-token color override (inline-value-token feature). When any
        # `:id:` token declares a `color` on its source, build a
        # per-visible-text-char list of Color-or-None so token chars render
        # in the source color while literal chars keep `provider`. `None`
        # (no colored token) leaves all three branches byte-identical.
        #
        # Built from the FROZEN `_resolved_segments` snapshot (M1) and scoped
        # to the ACTUAL `visible_text` with emoji-aware char counting (M2) so
        # the override lands in `draw_with_emoji`'s exact emoji-excluding
        # `char_index` space — for both the full string and a typewriter
        # prefix. This makes the old typewriter/emoji drift guard unnecessary:
        # a cut slug (`":su"`) now parses as a text run that reads the None
        # colors the `:sun:` segment contributed, so no leak — and a token
        # revealed past its leading emoji colorizes correctly mid-reveal.
        token_override: list[Any] | None = None
        if self._token is not None and self._token.has_tokens:
            segments = (
                self._resolved_segments
                if self._resolved_segments is not None
                else self._token.resolve_segments(get_data_registry())
            )
            token_override = build_token_color_override(
                segments, visible_text, self.frame_for("font_color"), self._has_emoji
            )

        # Run the text paint branches only when we are either on a live
        # (non-rotating) draw or on the FIRST rotating frame of a spin
        # (_snapshot_needed). On subsequent rotating frames (_snapshot_needed
        # is False) the artifact is already in the surface; skip the branches.
        _run_branches = rotate_surface is None or _snapshot_needed
        if _run_branches:
            # Shared three-branch draw dispatch (emoji / per-char /
            # whole-string) with the optional colored-token override, lifted
            # into `draw_text_run` so two_row + image (Phase 2) share ONE
            # implementation of the subtle per-char override semantics.
            #
            # `total_chars` preserves message's PER-BRANCH anchor exactly: the
            # emoji branch used `count_text_chars(full_text)` (draw_with_emoji's
            # emoji-EXCLUDING space), the per-char / forced-per-char branches
            # used `len(full_text)`, and the plain branch ignores it. Only ONE
            # branch runs per draw (selected by `has_emoji` / `per_char`), so
            # the matching count computed here is threaded explicitly — the
            # helper does NOT recompute from `visible_text` (which is a slice
            # under typewriter, and would shift each char's hue mid-reveal).
            if self._has_emoji:
                from led_ticker.pixel_emoji import count_text_chars  # noqa: PLC0415

                run_total = count_text_chars(full_text)
            else:
                run_total = len(full_text)
            cursor_pos += draw_text_run(
                draw_canvas,
                self.font,
                cursor_pos,
                baseline_y,
                provider,
                visible_text,
                self.frame_for("font_color"),
                override=token_override,
                has_emoji=self._has_emoji,
                total_chars=run_total,
                y_offset=y_offset,
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

    def _draw_lensed(
        self,
        canvas: Canvas,
        lens: Any,
        provider: ColorProvider,
        visible_text: str,
        full_text: str,
        cursor_pos: int,
        content_width: int,
        baseline_y: int,
        end_padding: int,
        y_offset: int,
    ) -> DrawResult:
        """Render the text through a stationary fisheye lens (spec §2–§3).

        Geometry lives in the shared `LensTextRenderer` (`lens_render.py`),
        which image/gif widgets reuse. Returns the UNWARPED cursor_pos (full
        content width) so the engine's overflow gate is unaffected — the lens
        never changes traversal arithmetic.
        """
        # Border paints FIRST, un-warped, directly to the canvas (it frames
        # the panel, not the text). Moved before the renderer call (was
        # previously painted between the strip render and the blit) —
        # canvas-equivalent, since the strip renders to an offscreen buffer
        # and only touches the canvas at blit time, which still happens
        # after this paint either way.
        if self.border is not None:
            self.border.paint(canvas, self.frame_for("border"))

        def _paint_strip_adapter(
            target: Any, x_logical: int, baseline: int, hires_downscale: float
        ) -> None:
            self._paint_strip(
                target,
                x_logical,
                baseline,
                y_offset,
                provider,
                visible_text,
                full_text,
                hires_downscale,
            )

        # `blit=lens_blit` forwards THIS module's own (patchable) name —
        # `LensTextRenderer.draw` reads it at call time rather than binding
        # its own import, so the pre-extraction test suite's
        # `monkeypatch.setattr(message, "lens_blit", spy)` still intercepts
        # the real blit call.
        self._lens_renderer.draw(
            canvas,
            lens,
            font=self.font,
            cursor_pos=cursor_pos,
            owner_name=type(self).__name__,
            paint_strip=_paint_strip_adapter,
            blit=lens_blit,
        )

        return canvas, cursor_pos + content_width + end_padding

    def _paint_strip(
        self,
        target: Any,
        x_logical: int,
        baseline: int,
        y_offset: int,
        provider: ColorProvider,
        visible_text: str,
        full_text: str,
        hires_downscale: float = 1.0,
    ) -> None:
        """Render ``visible_text`` into the lens strip at ``x_logical``.

        The same three paint branches as the normal draw path (emoji /
        per-char / whole-string), but targeting the strip and anchored at the
        lens-shifted origin. The per-char / emoji totals anchor to
        ``full_text``'s char count so a mid-reveal hue is stable (mirrors the
        normal branch's ``total_chars`` contract)."""
        # Route the lens strip through the SAME `draw_text_run` dispatch the
        # normal draw path uses, WITH the colored-token override built from the
        # frozen `_resolved_segments` snapshot — so a colored value token
        # colorizes under `flair.fisheye` too (previously the lens painted it
        # in the host color: the one message-vs-image fisheye asymmetry). The
        # `has_emoji` basis is the RAW `self._has_emoji` cache (matching the
        # normal draw); `total_chars` uses the same per-branch anchor
        # (`count_text_chars(full_text)` for emoji, `len(full_text)` else).
        token_override: list[Any] | None = None
        if self._token is not None and self._token.has_tokens:
            segments = (
                self._resolved_segments
                if self._resolved_segments is not None
                else self._token.resolve_segments(get_data_registry())
            )
            token_override = build_token_color_override(
                segments, visible_text, self.frame_for("font_color"), self._has_emoji
            )
        if self._has_emoji:
            from led_ticker.pixel_emoji import count_text_chars  # noqa: PLC0415

            run_total = count_text_chars(full_text)
        else:
            run_total = len(full_text)
        draw_text_run(
            target,
            self.font,
            x_logical,
            baseline,
            provider,
            visible_text,
            self.frame_for("font_color"),
            override=token_override,
            has_emoji=self._has_emoji,
            total_chars=run_total,
            y_offset=y_offset,
            hires_downscale=hires_downscale,
        )


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

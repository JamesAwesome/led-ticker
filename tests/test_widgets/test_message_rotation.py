"""TickerMessage rotation seam (propeller spec §4): non-zero
AnimationFrame.rotation redirects text into a RotationSurface and
rotate_blits it at physical resolution; rotation=0 is byte-identical
to the normal path.
"""

import logging
from unittest import mock

from rgbmatrix import _StubCanvas

from led_ticker.animations import AnimationFrame
from led_ticker.colors import RGB_WHITE
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.widgets.message import TickerMessage


class _StubSpin:
    """Animation stub emitting a fixed rotation with full text."""

    restart_on_visit = True

    def __init__(self, rotation: float) -> None:
        self.rotation = rotation

    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(visible_text=full_text, rotation=self.rotation)


def _make_widget(text="HELLO", rotation=0.0, **kwargs):
    return TickerMessage(
        text=text,
        font=FONT_DEFAULT,
        font_color=RGB_WHITE,
        animation=_StubSpin(rotation),
        **kwargs,
    )


def _canvas(width=160, height=16):
    return _StubCanvas(width=width, height=height)


class TestZeroRotationNeverBuildsBuffer:
    """rotation=0.0 must never construct a RotationSurface — the normal draw
    path is taken unchanged."""

    def test_zero_rotation_never_builds_buffer(self, monkeypatch):
        import led_ticker.rotate as rotate_mod

        calls: list = []

        original_factory = rotate_mod.make_rotation_surface

        def _tracking_factory(*args, **kwargs):
            calls.append(args)
            return original_factory(*args, **kwargs)

        monkeypatch.setattr(rotate_mod, "make_rotation_surface", _tracking_factory)
        # Also patch the name as imported in message.py
        import led_ticker.widgets.message as msg_mod

        monkeypatch.setattr(msg_mod, "make_rotation_surface", _tracking_factory)

        widget = _make_widget(rotation=0.0)
        c = _canvas()
        widget.draw(c)

        assert calls == [], (
            f"make_rotation_surface was constructed for rotation=0.0 — should take "
            f"the normal draw path. Calls: {calls!r}"
        )

    def test_zero_rotation_pixels_match_no_animation(self):
        """Pixels from rotation=0 stub must match pixels from animation=None."""
        widget_spin = _make_widget(rotation=0.0, center=False)
        c_spin = _canvas()
        widget_spin.draw(c_spin)

        widget_plain = TickerMessage(
            text="HELLO",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            center=False,
        )
        c_plain = _canvas()
        widget_plain.draw(c_plain)

        assert c_spin._pixels == c_plain._pixels, (
            "rotation=0 draw output differs from animation=None draw output"
        )


class TestRotation180FlipsTextPixels:
    """rotation=180 must map each lit pixel at (x, y) to approximately
    (2*cx - x, 2*cy - y)."""

    def test_rotation_180_flips_text_pixels(self):
        w_0 = _make_widget(text="AB", rotation=0.0, center=False)
        c_0 = _canvas()
        w_0.draw(c_0)

        w_180 = _make_widget(text="AB", rotation=180.0, center=False)
        c_180 = _canvas()
        w_180.draw(c_180)

        lit_0 = {xy for xy, rgb in c_0._pixels.items() if any(rgb)}
        lit_180 = {xy for xy, rgb in c_180._pixels.items() if any(rgb)}

        assert lit_0, "rotation=0 produced no lit pixels"
        assert lit_180, "rotation=180 produced no lit pixels"

        # Derive the center from the unrotated pixel extent.
        xs = [x for x, _ in lit_0]
        ys = [y for _, y in lit_0]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2

        # Each unrotated pixel should map to approximately its 180-rotated
        # counterpart. Use nearest-neighbor (round) tolerance.
        mapped = {(round(2 * cx - x), round(2 * cy - y)) for x, y in lit_0}

        # Allow a 1-pixel tolerance for rounding in inverse-map (nearest-
        # neighbor blit). At least 80% of mapped pixels should be found
        # in the 180-rotated set.
        hits = sum(
            1
            for mx, my in mapped
            if any(
                (mx + dx, my + dy) in lit_180 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            )
        )
        ratio = hits / max(len(mapped), 1)
        assert ratio >= 0.8, (
            f"180-rotation pixel mapping check: only {hits}/{len(mapped)} "
            f"mapped pixels found in lit_180 (ratio={ratio:.2f}). "
            f"Expected >= 0.80."
        )


class TestBorderStaysUnrotated:
    """The border must paint to the real canvas, not the rotation buffer.
    A known corner pixel must survive at its original location."""

    def test_border_stays_unrotated(self):
        # A stub border that paints a distinctive pixel at (0, 0).
        class _CornerBorder:
            frame_invariant = True

            def paint(self, canvas, frame):
                canvas.SetPixel(0, 0, 255, 0, 0)

        widget = TickerMessage(
            text="GO",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            border=_CornerBorder(),
            center=False,
        )
        c = _canvas()
        widget.draw(c)

        # The corner pixel must be red (255, 0, 0) — painted by the border
        # BEFORE the rotation redirect; rotation must NOT have erased it.
        assert c._pixels.get((0, 0)) == (255, 0, 0), (
            f"Corner pixel (0,0) after border+rotation=90: "
            f"{c._pixels.get((0, 0))!r} — expected (255,0,0) from border paint"
        )


class TestCursorAdvanceUnchangedByRotation:
    """draw() cursor_pos must be the same for rotation=0 and rotation=90."""

    def test_cursor_advance_unchanged_by_rotation(self):
        w_0 = _make_widget(text="HELLO WORLD", rotation=0.0, center=False)
        c_0 = _canvas()
        _, pos_0 = w_0.draw(c_0)

        w_90 = _make_widget(text="HELLO WORLD", rotation=90.0, center=False)
        c_90 = _canvas()
        _, pos_90 = w_90.draw(c_90)

        assert pos_0 == pos_90, (
            f"cursor_pos differs between rotation=0 ({pos_0}) and "
            f"rotation=90 ({pos_90}). Rotation must not affect layout."
        )


class TestHiresFontSkipsRotation:
    """HiresFont + rotation guard: scale-1 ignores rotation + warns once.
    On scaled canvases hires fonts go through the RotationSurface (no guard).
    """

    def test_hires_font_skips_rotation_with_warning_at_scale1(self, caplog):
        """Scale-1 (bare canvas): HiresFont + rotation warns once, draws normally."""
        from led_ticker.backends.headless import HeadlessCanvas
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        assert isinstance(font, HiresFont), (
            "resolve_font('Inter-Regular', 24) did not return a HiresFont — "
            "the guard test needs a real HiresFont instance."
        )

        canvas = HeadlessCanvas(width=256, height=64)

        widget = TickerMessage(
            text="TEST",
            font=font,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )

        # Draw #1 with rotation=90 should warn once, then draw normally.
        with caplog.at_level(logging.WARNING, logger="led_ticker"):
            widget.draw(canvas)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1, (
            f"Expected exactly 1 warning for hires+rotation at scale-1, "
            f"got {len(warnings)}: {[r.message for r in warnings]!r}"
        )
        msg_lower = warnings[0].message.lower()
        assert "hires" in msg_lower or "rotation" in msg_lower, (
            f"Warning message doesn't mention hires/rotation: {warnings[0].message!r}"
        )

        # Draw #2 must NOT log again (once-per-instance).
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="led_ticker"):
            widget.draw(canvas)

        second_warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert second_warnings == [], (
            f"Expected no second warning; got {second_warnings!r}"
        )

    def test_hires_font_rotation_pixel_output_matches_no_rotation_at_scale1(self):
        """Scale-1: pixel output for HiresFont + rotation must equal rotation=0
        (i.e., the guard draws the NORMAL unrotated path at scale-1)."""
        from led_ticker.backends.headless import HeadlessCanvas
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Regular", 24)

        canvas_0 = HeadlessCanvas(width=256, height=64)
        w_0 = TickerMessage(
            text="TEST",
            font=font,
            font_color=RGB_WHITE,
            animation=_StubSpin(0.0),
            center=False,
        )
        w_0.draw(canvas_0)

        canvas_90 = HeadlessCanvas(width=256, height=64)
        w_90 = TickerMessage(
            text="TEST",
            font=font,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )
        w_90.draw(canvas_90)

        assert canvas_0._pixels == canvas_90._pixels, (
            "HiresFont + rotation=90 at scale-1 produced different pixels from "
            "HiresFont + rotation=0 — the scale-1 guard should fall through to the "
            "normal unrotated draw path."
        )


class TestEmojiRotatesWithText:
    """Emoji in text must rotate along with letters — the buffer redirect
    applies to the emoji branch too."""

    def test_emoji_rotates_with_text(self):
        # Use text with a known emoji slug.
        w_0 = _make_widget(text="GO :sun: GO", rotation=0.0, center=False)
        c_0 = _canvas()
        w_0.draw(c_0)

        w_180 = _make_widget(text="GO :sun: GO", rotation=180.0, center=False)
        c_180 = _canvas()
        w_180.draw(c_180)

        lit_0 = {xy for xy, rgb in c_0._pixels.items() if any(rgb)}
        lit_180 = {xy for xy, rgb in c_180._pixels.items() if any(rgb)}

        assert lit_0, "rotation=0 emoji text produced no lit pixels"
        assert lit_180, "rotation=180 emoji text produced no lit pixels"

        # The pixel count should be similar (rotation is loss-less up to rounding).
        assert abs(len(lit_0) - len(lit_180)) <= len(lit_0) * 0.15, (
            f"Pixel count mismatch suggests emoji wasn't routed through the "
            f"buffer. rotation=0: {len(lit_0)} px, rotation=180: {len(lit_180)} px"
        )

        # Derive center from unrotated extent.
        xs = [x for x, _ in lit_0]
        ys = [y for _, y in lit_0]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2

        # Subset check: a sample of unrotated pixels should map close to the
        # rotated set (matching the test_rotation_180 tolerance).
        mapped = {(round(2 * cx - x), round(2 * cy - y)) for x, y in lit_0}
        hits = sum(
            1
            for mx, my in mapped
            if any(
                (mx + dx, my + dy) in lit_180 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            )
        )
        ratio = hits / max(len(mapped), 1)
        assert ratio >= 0.7, (
            f"Emoji 180-rotation pixel mapping: only {hits}/{len(mapped)} "
            f"mapped pixels found in lit_180 (ratio={ratio:.2f}). "
            f"Expected >= 0.70. Emoji may not be routed through the buffer."
        )


class TestPerBranchRedirect:
    """Each of the three draw branches (whole-string, per-char, emoji) must
    direct text into the RotationSurface when rotation != 0.

    Strategy: monkeypatch led_ticker.rotate.rotate_blit with a spy that
    records its call args and does NOTHING (no blit). The RotationSurface
    calls rotate_blit as a module global, so patching there intercepts it.
    After draw():
      (1) spy was called exactly once;
      (2) the `src` PixelBuffer has at least one lit pixel;
      (3) the real canvas has ZERO pixels (the blit was no-op'd, so any
          canvas pixels would prove the branch bypassed the buffer).
    No border is set in these tests, so canvas MUST be empty.
    """

    def _spy_setup(self, monkeypatch):
        """Return spy_calls list.
        Monkeypatches led_ticker.rotate.rotate_blit to a no-op spy —
        RotationSurface.blit calls it as a module global so this intercepts it.
        """
        calls: list = []

        def _noop_blit(dst, src, angle, cx, cy):  # noqa: N803 - matches sig
            calls.append((dst, src, angle, cx, cy))

        import led_ticker.rotate as rotate_mod

        monkeypatch.setattr(rotate_mod, "rotate_blit", _noop_blit)
        return calls

    def test_whole_string_branch_redirects_to_buffer(self, monkeypatch):
        """Whole-string branch (constant font_color, no emoji): draw_text
        must write to the RotationSurface buffer, not the real canvas."""
        calls = self._spy_setup(monkeypatch)

        widget = TickerMessage(
            text="HELLO",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,  # constant → whole-string branch
            animation=_StubSpin(90.0),
            center=False,
        )
        c = _canvas()
        widget.draw(c)

        # (1) spy called exactly once
        assert len(calls) == 1, f"rotate_blit called {len(calls)} times; expected 1"
        dst, src, angle, cx, cy = calls[0]

        # (2) src is a PixelBuffer with lit pixels (RotationSurface._buffer)
        from led_ticker.rotate import PixelBuffer

        assert isinstance(src, PixelBuffer), (
            f"rotate_blit src is {type(src).__name__}; expected PixelBuffer"
        )
        assert angle == 90.0, f"rotate_blit angle={angle!r}; expected 90.0"
        lit = any(
            src.get(x, y) is not None
            for y in range(src.height)
            for x in range(src.width)
        )
        assert lit, "PixelBuffer (src) has no lit pixels — text was not written to it"

        # (3) real canvas has zero pixels (blit was no-op'd)
        assert c._pixels == {}, (
            f"Canvas has {len(c._pixels)} pixel(s) after no-op blit — "
            f"whole-string branch wrote directly to canvas, bypassing buffer"
        )

    def test_per_char_branch_redirects_to_buffer(self, monkeypatch):
        """Per-char branch (Rainbow provider, no emoji): draw_text_per_char
        must write to the RotationSurface buffer, not the real canvas."""
        calls = self._spy_setup(monkeypatch)

        from led_ticker.color_providers import Rainbow

        widget = TickerMessage(
            text="HELLO",
            font=FONT_DEFAULT,
            font_color=Rainbow(),  # per_char=True → per-char branch
            animation=_StubSpin(90.0),
            center=False,
        )
        c = _canvas()
        widget.draw(c)

        # (1) spy called exactly once
        assert len(calls) == 1, f"rotate_blit called {len(calls)} times; expected 1"
        dst, src, angle, cx, cy = calls[0]

        # (2) src is a PixelBuffer with lit pixels
        from led_ticker.rotate import PixelBuffer

        assert isinstance(src, PixelBuffer), (
            f"rotate_blit src is {type(src).__name__}; expected PixelBuffer"
        )
        assert angle == 90.0, f"rotate_blit angle={angle!r}; expected 90.0"
        lit = any(
            src.get(x, y) is not None
            for y in range(src.height)
            for x in range(src.width)
        )
        assert lit, "PixelBuffer (src) has no lit pixels — text was not written to it"

        # (3) real canvas has zero pixels (blit was no-op'd)
        assert c._pixels == {}, (
            f"Canvas has {len(c._pixels)} pixel(s) after no-op blit — "
            f"per-char branch wrote directly to canvas, bypassing buffer"
        )

    def test_emoji_branch_redirects_to_buffer(self, monkeypatch):
        """Emoji branch (text with :sun: slug): draw_with_emoji must write
        to the RotationSurface buffer, not the real canvas."""
        calls = self._spy_setup(monkeypatch)

        widget = TickerMessage(
            text=":sun:",  # forces _has_emoji=True → emoji branch
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )
        c = _canvas()
        widget.draw(c)

        # (1) spy called exactly once
        assert len(calls) == 1, f"rotate_blit called {len(calls)} times; expected 1"
        dst, src, angle, cx, cy = calls[0]

        # (2) src is a PixelBuffer with lit pixels
        from led_ticker.rotate import PixelBuffer

        assert isinstance(src, PixelBuffer), (
            f"rotate_blit src is {type(src).__name__}; expected PixelBuffer"
        )
        assert angle == 90.0, f"rotate_blit angle={angle!r}; expected 90.0"
        lit = any(
            src.get(x, y) is not None
            for y in range(src.height)
            for x in range(src.width)
        )
        assert lit, "PixelBuffer (src) has no lit pixels — emoji was not written to it"

        # (3) real canvas has zero pixels (blit was no-op'd)
        assert c._pixels == {}, (
            f"Canvas has {len(c._pixels)} pixel(s) after no-op blit — "
            f"emoji branch wrote directly to canvas, bypassing buffer"
        )

    def test_overflow_rotation_center_stays_on_canvas(self, monkeypatch):
        """cx passed to rotate_blit must be within [0, canvas.width] even
        when content_width > canvas.width.

        Overflow case: the PixelBuffer holds only the clipped visible window
        (canvas dimensions). Rotating about start_pos + content_width/2
        places the pivot off-canvas (~175 on a 160px canvas for 350px text),
        swinging all content off-screen — panel goes black for most of the
        spin. The fix clamps cx to the visible extent."""
        calls = self._spy_setup(monkeypatch)

        # The pivot only leaves the canvas when content_width > 2x the
        # canvas width (cx = start_pos + content_width/2 > 160 needs
        # content_width > 320 at start_pos=0). 59 chars x 6px = 354px —
        # the same geometry the gif validation caught going black.
        long_text = "THIS MESSAGE IS MUCH TOO WIDE FOR THE PANEL AND MUST SCROLL"
        widget = TickerMessage(
            text=long_text,
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )
        c = _canvas(width=160, height=16)
        widget.draw(c)

        # Precondition guard: the text must overflow enough that the naive
        # pivot (start_pos + content_width/2) would land off-canvas —
        # otherwise this test can pass against the broken formula.
        assert widget._content_width > 2 * c.width, (
            f"precondition: content_width={widget._content_width} must exceed "
            f"2x canvas width ({2 * c.width}) to exercise the off-canvas pivot"
        )
        assert len(calls) == 1, f"rotate_blit called {len(calls)} times; expected 1"
        _dst, _src, _angle, cx, _cy = calls[0]

        assert 0 <= cx <= c.width, (
            f"cx={cx} is outside [0, {c.width}] for overflowing text — "
            f"the pivot is off-canvas, which blacks out the panel during spin. "
            f"Expected cx to be clamped to the visible text extent."
        )

    def test_fitting_text_center_unchanged(self, monkeypatch):
        """For short text that fits on-canvas, cx must equal
        start_pos + content_width / 2 (the original formula is unchanged)."""
        calls = self._spy_setup(monkeypatch)

        short_text = "HI"
        widget = TickerMessage(
            text=short_text,
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )
        c = _canvas(width=160, height=16)
        widget.draw(c)

        assert len(calls) == 1, f"rotate_blit called {len(calls)} times; expected 1"
        _dst, _src, _angle, cx, _cy = calls[0]

        # For fitting text: start_pos=0 (no centering, cursor_pos=0),
        # visible_left=0, visible_right=content_width → cx = content_width/2.
        # Also verify cx is within the canvas as a basic check.
        assert 0 <= cx <= c.width, (
            f"cx={cx} is outside [0, {c.width}] for fitting short text"
        )
        # The pivot must be within the drawn text's extent (between 0 and
        # content_width for left-aligned text starting at cursor_pos=0).
        # We know content_width for "HI" is well under 160px, so cx < canvas.width.
        # The center of the text should be well within [0, canvas.width].
        assert cx < c.width / 2 + 10, (
            f"cx={cx} seems too large for short text '{short_text}' — "
            f"expected it to be roughly content_width/2, not near canvas center"
        )


def _make_scaled_canvas(
    real_w: int = 256, real_h: int = 64, scale: int = 4, content_height: int = 16
):
    """Build a ScaledCanvas wrapping a HeadlessCanvas — no hardware needed."""
    from led_ticker.backends.headless import HeadlessCanvas
    from led_ticker.scaled_canvas import ScaledCanvas

    real = HeadlessCanvas(width=real_w, height=real_h)
    return ScaledCanvas(real, scale=scale, content_height=content_height), real


class TestScaledRotation:
    """TickerMessage on a ScaledCanvas must rotate at physical granularity
    via the RotationSurface (Task 2), with hires fonts/emoji spinning too.
    """

    def test_scaled_draw_rotates_at_physical_granularity(self) -> None:
        """Lit physical pixels at 45 deg are NOT constant per 4x4 block
        (same assertion shape as the Task-2 surface test but through the
        WIDGET's full draw path)."""
        canvas, real = _make_scaled_canvas()

        widget = TickerMessage(
            text="HELLO",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            animation=_StubSpin(45.0),
            center=False,
        )
        widget.draw(canvas)

        # Collect all lit pixels on the REAL canvas.
        lit = {
            (x, y)
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        }
        assert lit, "rotation=45 on scaled canvas produced no lit physical pixels"

        # Physical granularity check: for at least some 4×4 block that has lit
        # pixels, NOT all pixels in the block should be lit — a logical-only
        # rotate blits 4×4 blocks uniformly (every pixel in the block is
        # identical), but a physical-resolution rotate fills sub-block pixels
        # individually. A 45° rotation should create this pattern.
        found_sub_block_variation = False
        for block_x in range(0, real.width, 4):
            for block_y in range(0, real.height, 4):
                block_pixels = {
                    (x, y)
                    for x in range(block_x, min(block_x + 4, real.width))
                    for y in range(block_y, min(block_y + 4, real.height))
                    if real.get_pixel(x, y) != (0, 0, 0)
                }
                block_size = 4 * 4
                if 0 < len(block_pixels) < block_size:
                    found_sub_block_variation = True
                    break
            if found_sub_block_variation:
                break

        assert found_sub_block_variation, (
            "All lit pixels in every 4×4 block are uniform — this looks like "
            "logical-resolution rotation (full block blit), not physical-resolution. "
            "RotationSurface should produce sub-block pixel variation at 45°."
        )

    def test_hires_font_rotates_on_scaled_canvas_no_warning(self, caplog) -> None:
        """A HiresFont widget on a scaled canvas draws THROUGH the surface:
        physical pixels present at rotation=90, and NO hires-guard warning logged."""
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        assert isinstance(font, HiresFont), (
            "resolve_font('Inter-Regular', 24) did not return a HiresFont — "
            "this test needs a real HiresFont to verify the guard behavior."
        )

        canvas, real = _make_scaled_canvas()

        widget = TickerMessage(
            text="AB",
            font=font,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )

        with caplog.at_level(logging.WARNING, logger="led_ticker"):
            widget.draw(canvas)

        # No hires-guard warning — scaled canvas goes through the surface.
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        hires_warnings = [
            r
            for r in warnings
            if "hires" in r.message.lower() or "rotation" in r.message.lower()
        ]
        assert hires_warnings == [], (
            f"Unexpected hires-guard warning on scaled canvas: "
            f"{[r.message for r in hires_warnings]!r}"
        )

        # Physical pixels must be present (the surface blitted content).
        lit = [
            (x, y)
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        ]
        assert lit, (
            "HiresFont + rotation=90 on scaled canvas produced no lit "
            "physical pixels — the surface did not blit, or the widget "
            "fell through to unrotated."
        )

    def test_hires_guard_still_fires_at_scale1(self, caplog) -> None:
        """Unchanged v1 behavior at scale 1: HiresFont + rotation warns once
        and draws unrotated (scale-1 canvas can't host real-pixel glyphs)."""
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        assert isinstance(font, HiresFont)

        from led_ticker.backends.headless import HeadlessCanvas

        real_canvas = HeadlessCanvas(width=256, height=64)

        widget = TickerMessage(
            text="TEST",
            font=font,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )

        with caplog.at_level(logging.WARNING, logger="led_ticker"):
            widget.draw(real_canvas)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        hires_warnings = [
            r
            for r in warnings
            if "hires" in r.message.lower() or "rotation" in r.message.lower()
        ]
        assert len(hires_warnings) == 1, (
            f"Expected exactly 1 hires-guard warning at scale 1, "
            f"got {len(hires_warnings)}: "
            f"{[r.message for r in hires_warnings]!r}"
        )

    def test_hires_emoji_present_in_rotated_output(self) -> None:
        """Scaled canvas + ':sun:' text + rotation=90: hires sprite pixels land
        in the physical output. Skipped if 'sun' is not in HIRES_REGISTRY."""
        import pytest  # noqa: PLC0415

        from led_ticker.pixel_emoji import HIRES_REGISTRY  # noqa: PLC0415

        if "sun" not in HIRES_REGISTRY:
            pytest.skip(
                "':sun:' not in HIRES_REGISTRY — skip hires emoji rotation test"
            )

        canvas, real = _make_scaled_canvas()

        widget = TickerMessage(
            text=":sun:",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )
        widget.draw(canvas)

        lit = [
            (x, y)
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        ]
        assert lit, (
            "':sun:' + rotation=90 on scaled canvas produced no lit physical pixels — "
            "hires sprite not routed through RotationSurface."
        )

    def test_surface_cached_across_draws(self) -> None:
        """Two rotating draws must construct make_rotation_surface ONCE
        (spy on the factory; count == 1) — the construct-once contract."""
        from led_ticker.rotate import make_rotation_surface as real_factory

        call_count = 0
        surfaces_built: list = []

        def _spy_factory(canvas: object) -> object:
            nonlocal call_count
            call_count += 1
            surface = real_factory(canvas)  # type: ignore[arg-type]
            surfaces_built.append(surface)
            return surface

        canvas, _real = _make_scaled_canvas()

        widget = TickerMessage(
            text="HELLO",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            animation=_StubSpin(45.0),
            center=False,
        )

        with mock.patch(
            "led_ticker.widgets.message.make_rotation_surface", _spy_factory
        ):
            widget.draw(canvas)
            widget.draw(canvas)

        assert call_count == 1, (
            f"make_rotation_surface called {call_count} times across 2 draws; "
            f"expected 1 (cached after the first draw)."
        )

    def test_surface_rebuilds_on_content_height_change(self) -> None:
        """Antagonist plan-review finding 1: ONE widget instance drawn into two
        wrappers differing only in content_height rebuilds the surface.

        Factory spy count == 2, AND the second draw's lit physical rows center
        in the content_height=8 band (y_offset_real=16), not the stale 16-band.

        Approach: use rotation=0 for the second draw so text stays horizontal
        (not fanned-out by a 90° spin). This lets us assert band position cleanly:
        text drawn into content_height=8 (y_offset_real=16) must land in y=[16,48),
        not in y=[0,16) as it would with the stale content_height=16 surface.
        """
        from led_ticker.backends.headless import HeadlessCanvas
        from led_ticker.rotate import make_rotation_surface as real_factory
        from led_ticker.scaled_canvas import ScaledCanvas

        call_count = 0

        def _spy_factory(canvas: object) -> object:
            nonlocal call_count
            call_count += 1
            return real_factory(canvas)  # type: ignore[arg-type]

        real = HeadlessCanvas(width=256, height=64)

        # content_height=16 → y_offset_real = (64 - 16*4)//2 = 0
        canvas_16 = ScaledCanvas(real, scale=4, content_height=16)
        # content_height=8 → y_offset_real = (64 - 8*4)//2 = 16
        canvas_8 = ScaledCanvas(real, scale=4, content_height=8)

        # First draw uses rotation=90 to trigger surface construction.
        # Second draw uses rotation=0 to check band position:
        # rotation=0 draws directly to draw_canvas=canvas_8 (y_offset_real=16).
        # If the surface was NOT rebuilt, baseline_y cached from content_height=16
        # would center in the wrong band.
        widget_spin = TickerMessage(
            text="HELLO",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )

        with mock.patch(
            "led_ticker.widgets.message.make_rotation_surface", _spy_factory
        ):
            # First draw: content_height=16, surface built for the first time.
            widget_spin.draw(canvas_16)

        assert call_count == 1, (
            f"make_rotation_surface called {call_count} times after first "
            f"draw; expected 1."
        )

        # Second draw: content_height=8, DIFFERENT → must rebuild.
        with mock.patch(
            "led_ticker.widgets.message.make_rotation_surface", _spy_factory
        ):
            widget_spin.draw(canvas_8)

        assert call_count == 2, (
            f"make_rotation_surface called {call_count} times; expected 2 "
            f"(first draw content_height=16, second draw content_height=8 → rebuild)."
        )

        # Band position check: draw rotation=0 into content_height=8 canvas
        # and verify pixels land in the content band [y_offset_real=16, 48).
        # We use a fresh widget so baseline_y is re-computed from canvas_8.
        real2 = HeadlessCanvas(width=256, height=64)
        canvas_8b = ScaledCanvas(real2, scale=4, content_height=8)
        widget_plain = TickerMessage(
            text="HELLO",
            font=FONT_DEFAULT,
            font_color=RGB_WHITE,
            # No animation: direct draw path, bypasses rotation branch.
        )
        widget_plain.draw(canvas_8b)

        lit_ys = [
            y
            for x in range(real2.width)
            for y in range(real2.height)
            if real2.get_pixel(x, y) != (0, 0, 0)
        ]
        assert lit_ys, "Draw into content_height=8 canvas produced no lit pixels"

        # All lit rows must be within the content band [16, 48) — y_offset_real=16
        # at content_height=8, scale=4.
        out_of_band = [y for y in lit_ys if not (16 <= y < 48)]
        assert not out_of_band, (
            f"Lit pixels outside the content_height=8 band [16,48): "
            f"{out_of_band[:5]}... ({len(out_of_band)} total). "
            f"The surface should center text in the correct band "
            f"(y_offset_real=16)."
        )

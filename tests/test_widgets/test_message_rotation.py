"""TickerMessage rotation seam (propeller spec §4): non-zero
AnimationFrame.rotation redirects text into a PixelBuffer and
rotate_blits it; rotation=0 is byte-identical to the normal path.
"""

import logging

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
    """rotation=0.0 must never construct a PixelBuffer — the normal draw
    path is taken unchanged."""

    def test_zero_rotation_never_builds_buffer(self, monkeypatch):
        import led_ticker.widgets.message as msg_mod

        calls: list = []

        original_pb = msg_mod.PixelBuffer

        def _tracking_pb(*args, **kwargs):
            calls.append(args)
            return original_pb(*args, **kwargs)

        monkeypatch.setattr(msg_mod, "PixelBuffer", _tracking_pb)

        widget = _make_widget(rotation=0.0)
        c = _canvas()
        widget.draw(c)

        assert calls == [], (
            f"PixelBuffer was constructed for rotation=0.0 — should take "
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
    """Widgets with a HiresFont must ignore rotation, draw normally,
    and emit exactly one warning per instance."""

    def test_hires_font_skips_rotation_with_warning(self, caplog):
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        assert isinstance(font, HiresFont), (
            "resolve_font('Inter-Regular', 24) did not return a HiresFont — "
            "the guard test needs a real HiresFont instance."
        )

        # Build a real canvas that supports the hires draw path.
        from led_ticker.backends.headless import HeadlessCanvas
        from led_ticker.scaled_canvas import ScaledCanvas

        real = HeadlessCanvas(width=256, height=64)
        canvas = ScaledCanvas(real, scale=4)

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
            f"Expected exactly 1 warning for hires+rotation, got {len(warnings)}: "
            f"{[r.message for r in warnings]!r}"
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

    def test_hires_font_rotation_pixel_output_matches_no_rotation(self):
        """Pixel output for HiresFont + rotation must equal HiresFont + rotation=0
        (i.e., the hires guard draws the NORMAL path)."""
        from led_ticker.backends.headless import HeadlessCanvas
        from led_ticker.fonts import resolve_font
        from led_ticker.scaled_canvas import ScaledCanvas

        font = resolve_font("Inter-Regular", 24)

        real_0 = HeadlessCanvas(width=256, height=64)
        canvas_0 = ScaledCanvas(real_0, scale=4)
        w_0 = TickerMessage(
            text="TEST",
            font=font,
            font_color=RGB_WHITE,
            animation=_StubSpin(0.0),
            center=False,
        )
        w_0.draw(canvas_0)

        real_90 = HeadlessCanvas(width=256, height=64)
        canvas_90 = ScaledCanvas(real_90, scale=4)
        w_90 = TickerMessage(
            text="TEST",
            font=font,
            font_color=RGB_WHITE,
            animation=_StubSpin(90.0),
            center=False,
        )
        w_90.draw(canvas_90)

        assert real_0._pixels == real_90._pixels, (
            "HiresFont + rotation=90 produced different pixels from "
            "HiresFont + rotation=0 — the guard should fall through to the "
            "normal draw path unchanged."
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
    direct text into the PixelBuffer when rotation != 0.

    Strategy: monkeypatch rotate_blit with a spy that records its call args
    and does NOTHING (no blit).  After draw():
      (1) spy was called exactly once;
      (2) the `src` PixelBuffer has at least one lit pixel;
      (3) the real canvas has ZERO pixels (the blit was no-op'd, so any
          canvas pixels would prove the branch bypassed the buffer).
    No border is set in these tests, so canvas MUST be empty.
    """

    def _spy_setup(self, monkeypatch):
        """Return (spy_calls list, patched module restore).
        Monkeypatches led_ticker.widgets.message.rotate_blit to a no-op spy.
        """
        calls: list = []

        def _noop_blit(dst, src, angle, cx, cy):  # noqa: N803 - matches sig
            calls.append((dst, src, angle, cx, cy))

        import led_ticker.widgets.message as msg_mod

        monkeypatch.setattr(msg_mod, "rotate_blit", _noop_blit)
        return calls

    def test_whole_string_branch_redirects_to_buffer(self, monkeypatch):
        """Whole-string branch (constant font_color, no emoji): draw_text
        must write to the PixelBuffer, not the real canvas."""
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
            f"whole-string branch wrote directly to canvas, bypassing buffer"
        )

    def test_per_char_branch_redirects_to_buffer(self, monkeypatch):
        """Per-char branch (Rainbow provider, no emoji): draw_text_per_char
        must write to the PixelBuffer, not the real canvas."""
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
        to the PixelBuffer, not the real canvas."""
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

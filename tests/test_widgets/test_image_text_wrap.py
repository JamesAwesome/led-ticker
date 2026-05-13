"""Tests for text_wrap on image widgets (gif + still).

Validates field defaults, validation errors, and (in later tasks)
the seamless wrap render math. Single-row image widgets only —
two-row mode + TwoRowMessage wrap is intentionally out of scope
for v1 and validated to refuse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from led_ticker.widgets.still import StillImage

# Reuse the shared 16×16 RGBA fixture used by other image-widget
# tests. Path is conventional; if it doesn't exist locally, this
# import-line failure surfaces the issue at test collection time.
FIXTURE = Path(__file__).parent / "fixtures" / "test_16x16.png"


def _still(**kwargs):
    """Build a StillImage with the shared fixture and kw overrides."""
    defaults = dict(path=str(FIXTURE), text="hello")
    defaults.update(kwargs)
    return StillImage(**defaults)


class TestTextWrapFieldDefaults:
    def test_text_wrap_defaults_false(self):
        w = _still()
        assert w.text_wrap is False

    def test_text_separator_defaults_none(self):
        w = _still()
        assert w.text_separator is None

    def test_text_separator_color_defaults_none(self):
        w = _still()
        assert w.text_separator_color is None


class TestTextWrapValidation:
    def test_wrap_requires_scroll_align(self):
        with pytest.raises(ValueError, match="text_wrap.*requires.*text_align"):
            _still(text_wrap=True, text_align="left")

    def test_wrap_refuses_two_row(self):
        with pytest.raises(ValueError, match="text_wrap.*not supported.*two-row"):
            _still(
                text_wrap=True,
                top_text="top",
                bottom_text="bottom",
            )

    def test_separator_without_wrap_refused(self):
        with pytest.raises(ValueError, match="text_separator.*requires.*text_wrap"):
            _still(text_separator=" * ", text_align="scroll")

    def test_separator_color_without_wrap_refused(self):
        with pytest.raises(
            ValueError, match="text_separator_color.*requires.*text_wrap"
        ):
            _still(text_separator_color=(255, 0, 0), text_align="scroll")

    def test_wrap_with_scroll_align_accepted(self):
        # text_align="scroll" needs transparent regions, so use
        # text_align="scroll_over" which doesn't impose that.
        w = _still(text_wrap=True, text_align="scroll_over")
        assert w.text_wrap is True

    def test_wrap_with_explicit_scroll_and_pillarbox_accepted(self):
        # text_align="scroll" + non-stretch fit is fine.
        w = _still(text_wrap=True, text_align="scroll", fit="fit")
        assert w.text_wrap is True


class TestSeparatorColorCoercion:
    def test_separator_color_in_provider_keys(self):
        """text_separator_color must be in _PROVIDER_COLOR_KEYS so
        the app.py coercion path wraps raw [r,g,b] into a
        ColorProvider before the widget sees it."""
        from led_ticker.app import _PROVIDER_COLOR_KEYS

        assert "text_separator_color" in _PROVIDER_COLOR_KEYS

    def test_separator_color_in_effect_attrs(self):
        """text_separator_color must be in _FrameAware._EFFECT_ATTRS
        so it gets its own per-effect frame counter (matters for
        continuous-phase providers like Rainbow)."""
        from led_ticker.widgets._frame_aware import _FrameAware

        assert "text_separator_color" in _FrameAware._EFFECT_ATTRS

    def test_separator_color_string_coerced(self):
        """When the app loader sees text_separator_color = 'rainbow',
        _coerce_widget_colors must convert it to a Rainbow provider."""
        from led_ticker.app import _coerce_widget_colors

        cfg = {"text_separator_color": "rainbow"}
        _coerce_widget_colors(cfg)
        provider = cfg["text_separator_color"]
        assert hasattr(provider, "color_for")
        # Rainbow is per-char by default.
        assert provider.per_char is True


# ---------------------------------------------------------------------------
# Wrap render math (Task 3)
# ---------------------------------------------------------------------------

from PIL import Image  # noqa: E402


def _make_png(tmp_path, color=(200, 30, 40), size=(32, 32), name="img.png"):
    """Build a tiny PNG fixture (mirrors test_still.py:_make_png)."""
    img = Image.new("RGB", size, color=color)
    p = tmp_path / name
    img.save(p, format="PNG")
    return p


def _bigsign_real_canvas():
    """Bigsign 2x4 vertical-serpentine canvas (mirrors test_still.py)."""
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


class TestWrapRendersMultipleCopies:
    """The defining test: in wrap mode, the per-tick loop draws
    multiple copies of (text + separator) so the panel is never
    empty.

    We capture every draw_text call and assert that the total
    number of main-text draws exceeds the number of ticks — that
    can only happen if a single tick draws more than one copy."""

    @pytest.mark.asyncio
    async def test_wrap_left_yields_multiple_text_copies(self, tmp_path, mocker):
        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            fit="stretch",
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            scroll_speed_ms=50,
            hold_seconds=0.5,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        # Capture every draw_text call. Need to import the real
        # function so the side_effect can call through.
        import led_ticker.widgets._image_base as base_mod

        real_draw = base_mod.draw_text
        draws = []

        def _capture(canvas, font, x, baseline_y, color, text):
            draws.append((x, text))
            return real_draw(canvas, font, x, baseline_y, color, text)

        mocker.patch.object(base_mod, "draw_text", side_effect=_capture)

        await widget.play(real, frame)

        # In wrap mode, every tick should draw (n_copies =
        # ceil(canvas_w / cycle_width) + 1) copies of main text +
        # the same number of separators. Even with the shortest cycle
        # (text="Hi" + sep=" * ") on a 256-wide canvas, n_copies > 1.
        ticks = frame.matrix.SwapOnVSync.call_count
        main_text_draws = [d for d in draws if d[1] == "Hi"]
        assert ticks > 0, "No ticks ran"
        assert len(main_text_draws) > ticks, (
            f"Wrap should draw >1 copy per tick: got "
            f"{len(main_text_draws)} main-text draws across {ticks} ticks."
        )

    @pytest.mark.asyncio
    async def test_wrap_right_direction_renders(self, tmp_path, mocker):
        """Same defining property as the left-direction test, but
        with scroll_direction='right'. Confirms Python's modular-%
        on negative numbers wraps cleanly for both directions
        without needing a special case."""
        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            fit="stretch",
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            scroll_direction="right",
            scroll_speed_ms=50,
            hold_seconds=0.5,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        # Capture every draw_text call. Need to import the real
        # function so the side_effect can call through.
        import led_ticker.widgets._image_base as base_mod

        real_draw = base_mod.draw_text
        draws = []

        def _capture(canvas, font, x, baseline_y, color, text):
            draws.append((x, text))
            return real_draw(canvas, font, x, baseline_y, color, text)

        mocker.patch.object(base_mod, "draw_text", side_effect=_capture)

        await widget.play(real, frame)

        ticks = frame.matrix.SwapOnVSync.call_count
        main_text_draws = [d for d in draws if d[1] == "Hi"]
        assert ticks > 0, "No ticks ran"
        assert len(main_text_draws) > ticks, (
            f"Wrap should draw >1 copy per tick: got "
            f"{len(main_text_draws)} main-text draws across {ticks} ticks."
        )


# ---------------------------------------------------------------------------
# text_loops floors to N cycle traversals in wrap mode (Task 5)
# ---------------------------------------------------------------------------


class TestTextLoopsTraversalFloor:
    """In wrap mode, `text_loops` reinterprets as the minimum number
    of `cycle_width` traversals (one cycle = text + separator),
    rather than one full off-right→off-left traversal. Locks in the
    `ticks_per_text_loop = cycle_width if wrap_mode else ...` block
    in `_image_base._play_with_text`."""

    @pytest.mark.asyncio
    async def test_wrap_short_duration_floors_to_one_cycle(self, tmp_path, mocker):
        """`hold_seconds=0.5` would naturally run only 10 ticks (50ms
        cadence). With `text_wrap=True`, the floor must push `n_ticks`
        up to at least one `cycle_width`."""
        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            fit="stretch",
            text="X",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            scroll_speed_ms=50,
            hold_seconds=0.5,  # 10 ticks naturally
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        await widget.play(real, frame)

        # text="X" + sep=" * " in BDF 6×12 — cycle_width is some
        # value > 10. Assert it exceeds the natural duration without
        # pinning the exact width (font advance is implementation-
        # sensitive).
        count = frame.matrix.SwapOnVSync.call_count
        assert count > 10, (
            f"text_wrap should floor n_ticks to >=1 cycle "
            f"(>10 ticks for this 0.5s/50ms config); got {count}"
        )

    @pytest.mark.asyncio
    async def test_wrap_text_loops_2_runs_twice_cycles(self, tmp_path, mocker):
        """`text_loops=2` runs ~2× the ticks of `text_loops=1`.
        Compare two widgets identical except for `text_loops`."""

        async def _ticks_for_loops(loops):
            path = _make_png(tmp_path, color=(0, 0, 0))
            widget = StillImage(
                path=str(path),
                fit="stretch",
                text="X",
                text_wrap=True,
                text_align="scroll_over",
                text_separator=" * ",
                text_loops=loops,
                scroll_speed_ms=50,
                hold_seconds=0.5,
            )
            real = _bigsign_real_canvas()
            frame = mocker.MagicMock()
            frame.matrix.SwapOnVSync.side_effect = lambda c: c
            await widget.play(real, frame)
            return frame.matrix.SwapOnVSync.call_count

        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        ticks_1 = await _ticks_for_loops(1)
        ticks_2 = await _ticks_for_loops(2)
        # Allow some implementation slack (±2 ticks) but enforce ~2x ratio.
        assert ticks_2 >= 2 * ticks_1 - 2, (
            f"text_loops=2 should run ~2x ticks of text_loops=1; "
            f"got ticks_1={ticks_1}, ticks_2={ticks_2}"
        )


# ---------------------------------------------------------------------------
# Separator color inheritance + override (Task 6)
# ---------------------------------------------------------------------------


class TestSeparatorColorInheritance:
    @pytest.mark.asyncio
    async def test_separator_inherits_font_color_when_unset(self, tmp_path, mocker):
        """text_separator_color=None should make the separator paint
        with font_color resolved at its current frame."""
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            fit="stretch",
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            font_color=graphics.Color(255, 0, 0),  # red
            scroll_speed_ms=50,
            hold_seconds=0.1,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        import led_ticker.widgets._image_base as base_mod

        real_draw = base_mod.draw_text
        captured: list = []

        def _capture(canvas, font, x, baseline_y, color, text):
            # Only capture separator draws — text=" * " or any of the
            # default resolved values from _resolved_separator_text.
            if text in (" • ", " * ", "  "):
                captured.append(color)
            return real_draw(canvas, font, x, baseline_y, color, text)

        mocker.patch.object(base_mod, "draw_text", side_effect=_capture)

        await widget.play(real, frame)

        assert captured, "Expected at least one separator draw"
        for c in captured:
            assert (c.red, c.green, c.blue) == (255, 0, 0), (
                f"Separator should inherit font_color=red; got "
                f"({c.red},{c.green},{c.blue})"
            )

    @pytest.mark.asyncio
    async def test_separator_uses_own_color_when_set(self, tmp_path, mocker):
        """Explicit text_separator_color overrides font_color
        inheritance for the separator."""
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            fit="stretch",
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            font_color=graphics.Color(255, 0, 0),  # red
            text_separator_color=graphics.Color(0, 0, 255),  # blue
            scroll_speed_ms=50,
            hold_seconds=0.1,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        import led_ticker.widgets._image_base as base_mod

        real_draw = base_mod.draw_text
        captured: list = []

        def _capture(canvas, font, x, baseline_y, color, text):
            if text in (" • ", " * ", "  "):
                captured.append(color)
            return real_draw(canvas, font, x, baseline_y, color, text)

        mocker.patch.object(base_mod, "draw_text", side_effect=_capture)

        await widget.play(real, frame)

        assert captured, "Expected at least one separator draw"
        for c in captured:
            assert (c.red, c.green, c.blue) == (0, 0, 255), (
                f"Separator should use text_separator_color=blue; "
                f"got ({c.red},{c.green},{c.blue})"
            )

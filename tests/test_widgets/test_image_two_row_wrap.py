"""Tests for bottom_text_wrap on image widgets in two-row mode.

Mirrors test_image_text_wrap.py's structure. Single-row image
(no bottom_text) refuses bottom_text_wrap; two-row image
(bottom_text set) accepts it. Top row never wraps.
"""

from __future__ import annotations

import pytest
from PIL import Image

from led_ticker.widgets.still import StillImage


def _make_png(tmp_path, color=(0, 0, 0), size=(32, 32), name="img.png"):
    img = Image.new("RGB", size, color=color)
    p = tmp_path / name
    img.save(p, format="PNG")
    return p


def _still_two_row(tmp_path, **kwargs):
    """Build a two-row StillImage with reasonable defaults."""
    defaults = dict(
        path=str(_make_png(tmp_path)),
        top_text="TOP",
        bottom_text="bottom marquee",
    )
    defaults.update(kwargs)
    return StillImage(**defaults)


class TestBottomTextWrapDefaults:
    def test_bottom_text_wrap_defaults_false(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_wrap is False

    def test_bottom_text_separator_defaults_none(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_separator is None

    def test_bottom_text_separator_color_defaults_none(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_separator_color is None


class TestBottomTextWrapValidation:
    def test_wrap_requires_two_row_mode(self, tmp_path):
        """bottom_text_wrap on a single-row image widget (no bottom_text)
        is refused. Error suggests text_wrap as the right knob."""
        with pytest.raises(
            ValueError,
            match="bottom_text_wrap=True requires non-empty bottom_text",
        ):
            StillImage(
                path=str(_make_png(tmp_path)),
                text="single row",
                bottom_text_wrap=True,
            )

    def test_wrap_requires_non_empty_bottom_text(self, tmp_path):
        """bottom_text_wrap=True with bottom_text='' is refused even in
        two-row mode."""
        with pytest.raises(
            ValueError,
            match="bottom_text_wrap=True requires non-empty bottom_text",
        ):
            StillImage(
                path=str(_make_png(tmp_path)),
                top_text="TOP",
                bottom_text="",
                bottom_text_wrap=True,
            )

    def test_separator_without_wrap_refused(self, tmp_path):
        with pytest.raises(
            ValueError, match="bottom_text_separator.*requires bottom_text_wrap"
        ):
            _still_two_row(tmp_path, bottom_text_separator=" * ")

    def test_separator_color_without_wrap_refused(self, tmp_path):
        with pytest.raises(
            ValueError,
            match="bottom_text_separator_color.*requires bottom_text_wrap",
        ):
            _still_two_row(tmp_path, bottom_text_separator_color=(255, 0, 0))

    def test_wrap_in_two_row_mode_accepted(self, tmp_path):
        w = _still_two_row(tmp_path, bottom_text_wrap=True)
        assert w.bottom_text_wrap is True

    def test_v1_text_wrap_still_refused_in_two_row(self, tmp_path):
        """v1's text_wrap stays single-row-only — refused when
        bottom_text is set. Sharpened message points at bottom_text_wrap."""
        with pytest.raises(ValueError, match="text_wrap.*single-row.*bottom_text_wrap"):
            StillImage(
                path=str(_make_png(tmp_path)),
                top_text="TOP",
                bottom_text="bottom",
                text_wrap=True,
            )


class TestBottomSeparatorColorRegistration:
    def test_in_provider_keys(self):
        from led_ticker.app import _PROVIDER_COLOR_KEYS

        assert "bottom_text_separator_color" in _PROVIDER_COLOR_KEYS

    def test_in_effect_attrs(self):
        from led_ticker.widgets._frame_aware import _FrameAware

        assert "bottom_text_separator_color" in _FrameAware._EFFECT_ATTRS

    def test_rainbow_coerced(self):
        from led_ticker.app import _coerce_widget_colors

        cfg = {"bottom_text_separator_color": "rainbow"}
        _coerce_widget_colors(cfg)
        provider = cfg["bottom_text_separator_color"]
        assert hasattr(provider, "color_for")
        assert provider.per_char is True


class TestBottomTextWrapOnWrongWidgetType:
    """Same guard pattern v1 uses: drop falsy defaults silently,
    raise on truthy values when the widget type can't accept the field."""

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_on_message_rejected(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(ValueError, match="bottom_text_wrap.*only valid"):
                await _build_widget(
                    {
                        "type": "message",
                        "text": "hi",
                        "bottom_text_wrap": True,
                    },
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_bottom_text_separator_on_message_rejected(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(ValueError, match="bottom_text_separator.*only valid"):
                await _build_widget(
                    {
                        "type": "message",
                        "text": "hi",
                        "bottom_text_separator": " * ",
                    },
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_false_on_message_dropped_silently(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(
                {
                    "type": "message",
                    "text": "hi",
                    "bottom_text_wrap": False,
                },
                session=session,
            )
        assert widget is not None

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_on_two_row_accepted(self):
        """two_row is a NEW addition to the allowed types in v2."""
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(
                {
                    "type": "two_row",
                    "top_text": "TOP",
                    "bottom_text": "bottom",
                    "bottom_text_wrap": True,
                },
                session=session,
            )
        assert widget.bottom_text_wrap is True


class TestSeparatorHelpersParameterized:
    """Verify _measure_separator / _draw_separator accept explicit
    font + separator + provider args."""

    def test_measure_separator_accepts_font_kwarg(self, tmp_path):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.fonts import FONT_DEFAULT

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 16
        opts.chain_length = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        w = _still_two_row(tmp_path, bottom_text_wrap=True)
        width = w._measure_separator(canvas, font=FONT_DEFAULT)
        assert width > 0

    def test_measure_separator_accepts_separator_kwarg(self, tmp_path):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker.fonts import FONT_DEFAULT

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 16
        opts.chain_length = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()

        w = _still_two_row(tmp_path, bottom_text_wrap=True)
        # Pass an explicit separator — should override self.text_separator
        width_default = w._measure_separator(canvas, font=FONT_DEFAULT)
        width_custom = w._measure_separator(canvas, font=FONT_DEFAULT, separator=" ** ")
        # " ** " is wider than " • "
        assert width_custom > width_default


def _bigsign_real_canvas():
    """Bigsign 2x4 vertical-serpentine canvas (mirrors test_image_text_wrap.py)."""
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 32
    opts.chain_length = 8
    opts.parallel = 1
    opts.pixel_mapper_config = "U-mapper"
    return RGBMatrix(options=opts).CreateFrameCanvas()


_SWAP_SENTINEL = ("__SWAP__", None)


def _capture_draws_per_tick(mocker, frame):
    """Wrap draw_text + SwapOnVSync to capture (x, text) per tick.
    Mirrors the v1 single-row helper in test_image_text_wrap.py."""
    import led_ticker.widgets._image_base as base_mod

    real_draw = base_mod.draw_text
    draws: list = []

    def _capture(canvas, font, x, baseline_y, color, text):
        draws.append((x, text))
        return real_draw(canvas, font, x, baseline_y, color, text)

    mocker.patch.object(base_mod, "draw_text", side_effect=_capture)

    def _swap(c):
        draws.append(_SWAP_SENTINEL)
        return c

    frame.matrix.SwapOnVSync.side_effect = _swap
    return draws


def _split_into_ticks(draws):
    """Group draws by SwapOnVSync sentinel; drop trailing empty group."""
    ticks: list[list[tuple]] = [[]]
    for item in draws:
        if item == _SWAP_SENTINEL:
            ticks.append([])
        else:
            ticks[-1].append(item)
    return [t for t in ticks if t]


class TestImageTwoRowWrapRenders:
    """Defining tests for Task 5: in wrap mode, every tick paints
    multiple bottom-row copies at cycle_width-spaced positions, while
    the top row stays held at a single x.

    Strengthened similarly to the v1 single-row wrap defining test:
      - per-tick analysis (≥2 main-text copies per tick)
      - arithmetic-progression copy positions (real wrap, not stacked)
      - top row drawn exactly once per tick, never drifting"""

    @pytest.mark.asyncio
    async def test_bottom_wrap_renders_multiple_copies_per_tick(self, tmp_path, mocker):
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            scroll_speed_ms=50,
            hold_seconds=1.0,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        assert len(ticks) > 0, "Expected at least one tick"

        # For each of the first 5 ticks, verify ≥2 copies of "Hi"
        # at arithmetic-progression-spaced x positions.
        for tick_idx, tick in enumerate(ticks[:5]):
            hi_xs = sorted(x for (x, t) in tick if t == "Hi")
            assert len(hi_xs) >= 2, (
                f"Tick {tick_idx}: expected >=2 copies of 'Hi'; "
                f"got {len(hi_xs)} at xs={hi_xs}"
            )
            diffs = [hi_xs[i + 1] - hi_xs[i] for i in range(len(hi_xs) - 1)]
            median = sorted(diffs)[len(diffs) // 2]
            for d in diffs:
                assert abs(d - median) <= 2, (
                    f"Tick {tick_idx}: copy spacing not arithmetic. "
                    f"xs={hi_xs}, diffs={diffs}"
                )
            assert median > 0

    @pytest.mark.asyncio
    async def test_top_row_held_during_bottom_wrap(self, tmp_path, mocker):
        """Top row stays at its top_align position even while bottom
        wraps. The top row should be drawn at a SINGLE x per tick."""
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            top_align="left",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            scroll_speed_ms=50,
            hold_seconds=0.5,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        # Collect top x positions across the first 5 ticks.
        top_xs_per_tick = []
        for tick in ticks[:5]:
            top_xs = [x for (x, t) in tick if t == "TOP"]
            assert len(top_xs) == 1, (
                f"Top row should draw exactly once per tick; " f"got xs={top_xs}"
            )
            top_xs_per_tick.append(top_xs[0])

        # All top x's should be the same (held).
        assert (
            len(set(top_xs_per_tick)) == 1
        ), f"Top row drifted across ticks: {top_xs_per_tick}"


class TestBottomSeparatorColorInheritance:
    @pytest.mark.asyncio
    async def test_separator_inherits_bottom_color_when_unset(self, tmp_path, mocker):
        """text_separator_color=None makes the separator paint with
        bottom_color (NOT font_color — separator is part of the
        bottom row)."""
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            font_color=graphics.Color(255, 0, 0),  # red — NOT used for separator
            bottom_color=graphics.Color(0, 255, 0),  # green — separator should be this
            scroll_speed_ms=50,
            hold_seconds=0.2,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        # Capture draw_text calls; filter for separator.
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
            assert (c.red, c.green, c.blue) == (0, 255, 0), (
                f"Separator should inherit bottom_color=green; got "
                f"({c.red}, {c.green}, {c.blue})"
            )

    @pytest.mark.asyncio
    async def test_separator_explicit_overrides_bottom_color(self, tmp_path, mocker):
        """Setting bottom_text_separator_color overrides inheritance."""
        from led_ticker._compat import require_graphics

        graphics = require_graphics()
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            bottom_color=graphics.Color(0, 255, 0),  # green
            bottom_text_separator_color=graphics.Color(0, 0, 255),  # blue
            scroll_speed_ms=50,
            hold_seconds=0.2,
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
                f"Separator should use blue (bottom_text_separator_color); "
                f"got ({c.red}, {c.green}, {c.blue})"
            )


class TestImageTwoRowWrapWithBorder:
    @pytest.mark.asyncio
    async def test_wrap_with_border_no_crash(self, tmp_path, mocker):
        """Border + bottom wrap compose without exception. Assert
        the wrap loop still runs (bottom-row copies drawn per tick)."""
        from led_ticker.borders import RainbowChaseBorder

        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            border=RainbowChaseBorder(speed=4, char_offset=6, thickness=1),
            scroll_speed_ms=50,
            hold_seconds=0.2,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        hi_total = sum(len([d for d in tick if d[1] == "Hi"]) for tick in ticks)
        assert hi_total > len(ticks), "Border did not block bottom-row wrap"


class TestGifPlayerTwoRowWrap:
    @pytest.mark.asyncio
    async def test_gif_two_row_wrap_renders_multiple_copies(self, tmp_path, mocker):
        """Multi-frame gif + bottom wrap. Exercises the interaction
        between _pick_frame_for_elapsed and the wrap render path."""
        from led_ticker.widgets.gif import GifPlayer

        gif_path = tmp_path / "x.gif"
        from PIL import Image

        frames = [
            Image.new("RGB", (32, 32), (200, 0, 0)),
            Image.new("RGB", (32, 32), (0, 200, 0)),
            Image.new("RGB", (32, 32), (0, 0, 200)),
        ]
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )

        widget = GifPlayer(
            path=str(gif_path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
            scroll_speed_ms=50,
            gif_loops=2,
        )

        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        hi_total = sum(len([d for d in tick if d[1] == "Hi"]) for tick in ticks)
        assert hi_total > len(ticks), (
            "GifPlayer two-row wrap should render multiple bottom " "copies per tick"
        )

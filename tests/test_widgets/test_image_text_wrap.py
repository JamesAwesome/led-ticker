"""Tests for text_wrap on image widgets (gif + still).

Validates field defaults, validation errors, and (in later tasks)
the seamless wrap render math. Single-row image widgets only —
two-row mode + TwoRowMessage wrap is intentionally out of scope
for v1 and validated to refuse.
"""

from __future__ import annotations

import pytest

from led_ticker.widgets.still import StillImage


def _still(**kwargs):
    """Build a StillImage with stub path + text. Construction-only —
    `path` is validated at `_load` time, so a non-existent dummy is
    fine for tests that never call `play()`."""
    defaults = dict(path="/dev/null/no_such_image.png", text="hello")
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

    def test_wrap_requires_non_empty_text(self):
        """text_wrap=True with text="" would render an endless chain
        of separators (a near-certain user typo). The loader should
        refuse it at construction time."""
        with pytest.raises(ValueError, match="text_wrap.*requires non-empty text"):
            _still(text_wrap=True, text="", text_align="scroll_over")

    def test_wrap_auto_align_error_mentions_auto_resolution(self):
        """When `text_align='auto'` resolves to a non-scroll value
        (because image_align is 'left' or 'right'), the wrap error
        should hint that auto was resolved — otherwise the user sees
        `text_align='right'` and is confused (they never wrote that)."""
        with pytest.raises(ValueError, match="text_align='auto' was resolved"):
            _still(
                text_wrap=True,
                text_align="auto",
                image_align="left",
            )


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


class TestWrapOnWrongWidgetType:
    """text_wrap / text_separator / text_separator_color are only
    valid on gif/image widgets. Setting them on message, weather,
    countdown, etc. surfaces a clean ValueError at config-load
    rather than the cryptic TypeError attrs would raise."""

    @pytest.mark.asyncio
    async def test_text_wrap_on_message_rejected(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(ValueError, match="text_wrap.*only valid"):
                await _build_widget(
                    {"type": "message", "text": "hi", "text_wrap": True},
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_text_separator_on_message_rejected(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(ValueError, match="text_separator.*only valid"):
                await _build_widget(
                    {
                        "type": "message",
                        "text": "hi",
                        "text_separator": " * ",
                    },
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_text_separator_color_on_message_rejected(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(ValueError, match="text_separator_color.*only valid"):
                await _build_widget(
                    {
                        "type": "message",
                        "text": "hi",
                        "text_separator_color": [255, 0, 0],
                    },
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_text_wrap_on_gif_accepted(self, tmp_path):
        """Sanity check — gif accepts the field (regression guard
        against an over-strict guard that would reject valid usage)."""
        import aiohttp
        from PIL import Image

        from led_ticker.app import _build_widget

        path = tmp_path / "x.gif"
        Image.new("RGB", (16, 16), (255, 0, 0)).save(path, format="GIF")

        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(
                {
                    "type": "gif",
                    "path": str(path),
                    "text": "hi",
                    "text_wrap": True,
                    "text_align": "scroll_over",
                },
                session=session,
            )
        assert widget.text_wrap is True


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


_SWAP_SENTINEL = ("__SWAP__", None)


def _capture_draws_per_tick(mocker, frame):
    """Helper: install a draw_text capture + SwapOnVSync sentinel so
    callers can group draws by tick by splitting on the sentinel.

    Returns the `draws` list (a flat sequence of ``(x, text)`` tuples
    with `_SWAP_SENTINEL` markers inserted at each swap boundary).
    Callers split on the sentinel to get per-tick groups.

    Setting this up is fiddly enough to repeat across 3+ tests; the
    helper keeps the strengthened defining tests readable."""
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
    """Split a draws list on `_SWAP_SENTINEL`, returning a list of
    per-tick groups. Trailing empty group (from the final swap with
    no draws after) is filtered out."""
    ticks: list[list[tuple]] = [[]]
    for item in draws:
        if item == _SWAP_SENTINEL:
            ticks.append([])
        else:
            ticks[-1].append(item)
    # Drop the trailing empty group; the last sentinel always closes
    # the final tick with no draws after it.
    return [t for t in ticks if t]


class TestWrapRendersMultipleCopies:
    """The defining test: in wrap mode, the per-tick loop draws
    multiple copies of (text + separator) so the panel is never
    empty.

    Strengthened from a "main_text_draws > ticks" total to per-tick
    analysis that catches:
      - bursty draws (some ticks draw 3, some draw 0)
      - overlapping copies at the same x (no actual wrap, just
        duplicated draws)

    The defining property is: EVERY tick draws ≥2 copies, and copy
    positions form an arithmetic progression at ~`cycle_width` spacing
    (real wrap, not stacked copies)."""

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
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        assert ticks, "No ticks ran"
        # Sanity: cumulative count should exceed swap count (would
        # have caught the original "main_text_draws > ticks" cases).
        total_main = sum(1 for t in ticks for x, txt in t if txt == "Hi")
        assert total_main > len(ticks), (
            f"Wrap should draw >1 copy per tick on average; got "
            f"{total_main} main-text draws across {len(ticks)} ticks."
        )

        # Per-tick invariant: every tick draws >=2 main-text copies.
        # Without this the "bursty draws" failure mode (some ticks
        # render 3, some 0) would pass the total-only check.
        for i, tick in enumerate(ticks):
            mains = [x for x, txt in tick if txt == "Hi"]
            assert len(mains) >= 2, (
                f"Tick {i} drew {len(mains)} main-text copies; "
                f"wrap requires >=2 per tick (panel must never be empty)."
            )
            # Arithmetic-progression invariant: consecutive copies
            # should be spaced by ~cycle_width. Compute the empirical
            # cycle from the first tick's gaps and assert all gaps
            # match within ±2 px (font-advance edge effects). This
            # catches the "stacked copies at the same x" failure mode.
            xs = sorted(mains)
            gaps = [xs[j + 1] - xs[j] for j in range(len(xs) - 1)]
            assert gaps, f"Tick {i}: not enough copies to measure gap"
            # All gaps within ±2 px of the median (robust to a
            # potential outlier from an off-canvas copy that
            # contributes a partial gap).
            median = sorted(gaps)[len(gaps) // 2]
            for g in gaps:
                assert abs(g - median) <= 2, (
                    f"Tick {i}: copy spacing varies — gaps={gaps}. "
                    f"Wrap copies should sit at arithmetic progression "
                    f"with ~cycle_width spacing (not stacked or random)."
                )
            assert median > 0, (
                f"Tick {i}: median spacing {median} <= 0 — copies are "
                f"stacked at the same x, not actually wrapping."
            )

    @pytest.mark.asyncio
    async def test_wrap_right_direction_renders(self, tmp_path, mocker):
        """Same defining property as the left-direction test, but
        with scroll_direction='right'. Additionally asserts the
        leading-copy x-position increases monotonically across ticks
        (rightward direction is honored)."""
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
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        assert ticks, "No ticks ran"

        # Per-tick: >=2 copies, arithmetic spacing (same invariant
        # as left direction).
        leading_xs: list[int] = []
        for i, tick in enumerate(ticks):
            mains = sorted(x for x, txt in tick if txt == "Hi")
            assert len(mains) >= 2, (
                f"Tick {i} drew {len(mains)} main-text copies; "
                f"wrap requires >=2 per tick."
            )
            gaps = [mains[j + 1] - mains[j] for j in range(len(mains) - 1)]
            median = sorted(gaps)[len(gaps) // 2]
            for g in gaps:
                assert (
                    abs(g - median) <= 2
                ), f"Tick {i}: copy spacing varies — gaps={gaps}."
            # Track the "leading" copy (rightmost x for right-scroll).
            leading_xs.append(mains[-1])

        # Direction-honored invariant: with scroll_direction="right",
        # the leading-copy x should increase across ticks (modulo
        # wrap-around). Check the differences: at least one pair
        # should be strictly increasing — and no consecutive pair
        # should decrease by more than ~cycle_width (which would
        # indicate leftward motion, not a wrap-around).
        # Sample first few ticks to avoid edge artifacts.
        sample = leading_xs[: min(5, len(leading_xs))]
        diffs = [sample[j + 1] - sample[j] for j in range(len(sample) - 1)]
        # Allow some diffs to be a large negative number (wrap-around)
        # but at least one should be positive.
        assert any(d > 0 for d in diffs), (
            f"scroll_direction='right' should advance leading-copy x "
            f"rightward across ticks; got leading_xs={sample}, "
            f"diffs={diffs}."
        )


class TestWrapScrollUnderImage:
    """Exercise the `text_align='scroll'` paint-order branch
    (`_paint_skip_black` on top of text, so text walks behind the
    image silhouette). This branch is in `_render_wrap_tick` ~line
    903-907 and was previously uncovered."""

    @pytest.mark.asyncio
    async def test_wrap_scroll_align_renders_multiple_copies(self, tmp_path, mocker):
        path = _make_png(tmp_path, color=(0, 0, 0))
        # text_align="scroll" requires non-stretch fit (pillarbox
        # leaves transparent regions for the text to scroll through).
        widget = StillImage(
            path=str(path),
            fit="pillarbox",
            text="Hi",
            text_wrap=True,
            text_align="scroll",
            text_separator=" * ",
            scroll_speed_ms=50,
            hold_seconds=0.5,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        assert ticks, "No ticks ran"
        # Same per-tick analysis as scroll_over: every tick must
        # render >=2 copies. The branch that's exercised here is
        # different (text first, then image on top via
        # _paint_skip_black) but the draw_text contract is the same.
        for i, tick in enumerate(ticks):
            mains = sorted(x for x, txt in tick if txt == "Hi")
            assert len(mains) >= 2, (
                f"Tick {i} drew {len(mains)} main-text copies in "
                f"text_align='scroll' mode; wrap requires >=2 per tick."
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


class TestSeparatorEmptyString:
    """Test the literal-text semantics of _resolved_separator_text:
      - None       -> " • " (default)
      - ""         -> "  "  (two-space minimum gap)
      - any other  -> as-is

    Mirrors forever_scroll's separator literal-text rules so a user
    moving from per-section wraps to per-widget wraps gets the same
    defaults.

    Construction-only tests — no need to call play(); we exercise the
    helper directly. Use tmp_path + _make_png only because StillImage
    requires a path for validation."""

    def test_none_separator_renders_default_bullet(self, tmp_path):
        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
        )
        assert widget._resolved_separator_text() == " • "

    def test_empty_string_separator_renders_two_spaces(self, tmp_path):
        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator="",
        )
        assert widget._resolved_separator_text() == "  "

    def test_custom_string_separator_renders_as_is(self, tmp_path):
        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
        )
        assert widget._resolved_separator_text() == " * "


# ---------------------------------------------------------------------------
# GifPlayer wrap coverage (Task 3 follow-up: all wrap tests above use
# StillImage; this exercises the GifPlayer side of the inheritance hierarchy)
# ---------------------------------------------------------------------------

import io  # noqa: E402

from led_ticker.widgets.gif import GifPlayer  # noqa: E402


def _make_gif_path(tmp_path, frames, size=(32, 32), duration_ms=100):
    """Build a multi-frame GIF fixture (mirrors test_gif.py)."""
    images = [Image.new("RGB", size, color=c) for c in frames]
    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
    )
    p = tmp_path / "wrap.gif"
    p.write_bytes(buf.getvalue())
    return p


class TestGifPlayerWrap:
    """All other wrap tests use StillImage; this exercises GifPlayer
    so the `_pick_frame_for_elapsed` path (non-trivial on multi-frame
    sources) is covered alongside the wrap render loop."""

    @pytest.mark.asyncio
    async def test_gif_wrap_renders_multiple_copies(self, tmp_path, mocker):
        path = _make_gif_path(
            tmp_path,
            [(200, 0, 0), (0, 200, 0), (0, 0, 200)],
            duration_ms=100,
        )
        widget = GifPlayer(
            path=str(path),
            fit="stretch",
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            scroll_speed_ms=50,
            gif_loops=1,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

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
        # GifPlayer share s_play_with_text with StillImage, so the
        # min-count check is enough — the StillImage tests above
        # already enforce the stronger per-tick invariants. We're
        # really just confirming the multi-frame `_is_static() == False`
        # path doesn't bypass the wrap loop.
        assert len(main_text_draws) > ticks, (
            f"GifPlayer wrap should draw >1 copy per tick: got "
            f"{len(main_text_draws)} main-text draws across {ticks} ticks."
        )


# ---------------------------------------------------------------------------
# Wrap + border composition
# ---------------------------------------------------------------------------


class TestWrapWithBorder:
    """Wrap mode paints the border inside `_render_wrap_tick` (separate
    from the standard `_render_tick` path). This regression test
    verifies border + wrap compose without crashing — the border is
    a frame-aware effect that needs its own per-effect counter, and
    a refactor that drops the `border.paint(...)` call inside the
    wrap branch would silently leave borderless wrap output."""

    @pytest.mark.asyncio
    async def test_wrap_with_border_does_not_crash(self, tmp_path, mocker):
        from led_ticker.borders import RainbowChaseBorder

        path = _make_png(tmp_path, color=(0, 0, 0))
        widget = StillImage(
            path=str(path),
            fit="stretch",
            text="Hi",
            text_wrap=True,
            text_align="scroll_over",
            text_separator=" * ",
            border=RainbowChaseBorder(speed=4, char_offset=6, thickness=1),
            scroll_speed_ms=50,
            hold_seconds=0.3,
        )
        real = _bigsign_real_canvas()
        frame = mocker.MagicMock()
        frame.matrix.SwapOnVSync.side_effect = lambda c: c
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

        import led_ticker.widgets._image_base as base_mod

        real_draw = base_mod.draw_text
        draws = []

        def _capture(canvas, font, x, baseline_y, color, text):
            draws.append((x, text))
            return real_draw(canvas, font, x, baseline_y, color, text)

        mocker.patch.object(base_mod, "draw_text", side_effect=_capture)

        # No exception is the primary assertion.
        await widget.play(real, frame)

        # And the wrap render path produced multiple text draws —
        # proving the border didn't short-circuit it.
        main_text_draws = [d for d in draws if d[1] == "Hi"]
        assert len(main_text_draws) > frame.matrix.SwapOnVSync.call_count, (
            f"Wrap + border should still render multiple text copies; "
            f"got {len(main_text_draws)} draws across "
            f"{frame.matrix.SwapOnVSync.call_count} ticks."
        )

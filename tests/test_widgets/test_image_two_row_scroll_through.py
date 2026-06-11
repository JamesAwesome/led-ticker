"""Tests for bottom_text_scroll on image widgets in two-row mode.

Mirrors test_two_row_scroll_through.py for the gif/still image
two-row text overlay (_BaseImageWidget._play_with_two_row_text).
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
    defaults = dict(
        path=str(_make_png(tmp_path)),
        top_text="TOP",
        bottom_text="bottom scrolling",
    )
    defaults.update(kwargs)
    return StillImage(**defaults)


class TestBottomTextScrollDefaultsOnImage:
    def test_field_defaults_to_marquee(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_scroll == "marquee"

    def test_scroll_through_accepted_in_two_row_mode(self, tmp_path):
        w = _still_two_row(tmp_path, bottom_text_scroll="scroll_through")
        assert w.bottom_text_scroll == "scroll_through"


class TestBottomTextScrollValidationOnImage:
    def test_unknown_value_raises_with_valid_options_listed(self, tmp_path):
        with pytest.raises(ValueError, match="bottom_text_scroll") as exc_info:
            _still_two_row(tmp_path, bottom_text_scroll="bogus")
        msg = str(exc_info.value)
        assert "marquee" in msg
        assert "scroll_through" in msg
        assert "bogus" in msg

    def test_scroll_through_with_wrap_true_refused(self, tmp_path):
        """Same mutex as TwoRowMessage — pick one of wrap or scroll_through."""
        with pytest.raises(
            ValueError,
            match=r"bottom_text_scroll=.scroll_through.*bottom_text_wrap=True",
        ):
            _still_two_row(
                tmp_path,
                bottom_text_scroll="scroll_through",
                bottom_text_wrap=True,
            )

    def test_scroll_through_on_single_row_points_at_text_align(self, tmp_path):
        """scroll_through with empty bottom_text is meaningless. The
        error message must point users at text_align (the single-row
        scroll knob) rather than just saying 'add bottom_text', because
        the latter steers them toward two-row mode they may not want."""
        with pytest.raises(
            ValueError,
            match=r"bottom_text_scroll.*single-row.*text_align",
        ):
            StillImage(
                path=str(_make_png(tmp_path)),
                text="single row",
                bottom_text_scroll="scroll_through",
            )

    def test_marquee_default_preserves_existing_behavior(self, tmp_path):
        """The default value of bottom_text_scroll must not block any
        existing valid config (held when fits, scroll on overflow,
        wrap when bottom_text_wrap=True). Note: explicit 'marquee' on
        a single-row image is silently accepted — attrs.define provides
        no clean way to distinguish 'user wrote default value' from
        'default value was inferred,' and marquee on single-row is
        functionally a no-op rather than an error."""
        w = _still_two_row(
            tmp_path,
            bottom_text_scroll="marquee",
            bottom_text_wrap=True,
            bottom_text_separator=" * ",
        )
        assert w.bottom_text_scroll == "marquee"
        assert w.bottom_text_wrap is True


_SWAP_SENTINEL = ("__SWAP__", None)


def _capture_draws_per_tick(mocker, frame):
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

    frame.swap.side_effect = _swap
    return draws


def _split_into_ticks(draws):
    ticks: list[list[tuple]] = [[]]
    for item in draws:
        if item == _SWAP_SENTINEL:
            ticks.append([])
        else:
            ticks[-1].append(item)
    return [t for t in ticks if t]


class TestImageScrollThroughForcesOffscreenScroll:
    """In scroll_through mode the bottom row must run the offscreen
    marquee branch even when the text fits the canvas. That means
    the first tick paints the bottom row starting at x = canvas.width
    (fully off the right edge), and subsequent ticks decrement x by
    one pixel per tick — same shape as the existing overflow path."""

    @pytest.mark.asyncio
    async def test_short_bottom_text_starts_offscreen_when_scroll_through(
        self, tmp_path, mocker, bigsign_canvas
    ):
        """A two-letter `bottom_text="Hi"` would normally be held at
        `bottom_align="center"` because it fits the 256-wide canvas.
        scroll_through forces it to enter the marquee branch — first
        tick puts it at x=canvas.width (256), not somewhere centered."""
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",  # short — would normally center
            bottom_align="center",
            bottom_text_scroll="scroll_through",
            scroll_speed_ms=50,
            hold_time=0.5,
        )
        real = bigsign_canvas
        frame = mocker.MagicMock()
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        assert len(ticks) >= 2, f"Need ≥2 ticks; got {len(ticks)}"

        first_tick = ticks[0]
        hi_draws = [(x, t) for (x, t) in first_tick if t == "Hi"]
        assert len(hi_draws) == 1, (
            f"scroll_through (non-wrap) draws ONE copy per tick; "
            f"got {len(hi_draws)} on first tick: {hi_draws}"
        )
        first_hi_x = hi_draws[0][0]
        # Production sets scroll_pos = canvas_w on first tick. Read the
        # widget's resolved text canvas width directly so the assertion
        # pins production behavior exactly, not a coincidence. A buggy
        # impl that ignored scroll_through and held at bottom_align
        # would produce x ≈ (canvas_w - bottom_w) / 2 ≈ 122 for "Hi"
        # on bigsign — far from canvas_w.
        text_canvas = widget._wrap_for_text(real, widget._logical_scale)
        expected_canvas_w = text_canvas.width
        assert first_hi_x == expected_canvas_w, (
            f"scroll_through must start bottom row at canvas_w "
            f"({expected_canvas_w}, fully off the right edge); "
            f"got first-tick x={first_hi_x}. A held-centered impl "
            f"would produce x ≈ {(expected_canvas_w - 12) // 2}."
        )
        second_tick = ticks[1]
        second_hi_draws = [(x, t) for (x, t) in second_tick if t == "Hi"]
        assert len(second_hi_draws) == 1
        second_hi_x = second_hi_draws[0][0]
        # x must move LEFT (scroll direction).
        assert second_hi_x < first_hi_x, (
            f"scroll_through must advance scroll_pos left across ticks. "
            f"tick0 x={first_hi_x}, tick1 x={second_hi_x}"
        )

    @pytest.mark.asyncio
    async def test_marquee_default_still_holds_short_bottom_text(
        self, tmp_path, mocker, bigsign_canvas
    ):
        """Regression guard: with the default `bottom_text_scroll=
        "marquee"`, a short bottom_text that fits still holds at its
        bottom_align position — the new field must not alter existing
        behavior."""
        path = _make_png(tmp_path)
        widget = StillImage(
            path=str(path),
            fit="stretch",
            top_text="TOP",
            bottom_text="Hi",
            bottom_align="center",
            scroll_speed_ms=50,
            hold_time=0.5,
        )
        real = bigsign_canvas
        frame = mocker.MagicMock()
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        draws = _capture_draws_per_tick(mocker, frame)

        await widget.play(real, frame)

        ticks = _split_into_ticks(draws)
        # Sample 5 ticks — short held text should have IDENTICAL bottom x.
        bottom_xs = []
        for tick in ticks[:5]:
            hi = [(x, t) for (x, t) in tick if t == "Hi"]
            if hi:
                bottom_xs.append(hi[0][0])
        assert len(set(bottom_xs)) == 1, (
            f"Default marquee mode must hold short text; xs={bottom_xs}"
        )

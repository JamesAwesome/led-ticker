"""Tests for led_ticker.ticker."""

import asyncio
import contextlib
import itertools
import unittest.mock as mock
from unittest.mock import MagicMock

import pytest

from led_ticker.color_providers import Rainbow
from led_ticker.colors import RGB_WHITE
from led_ticker.frame import LedFrame
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.ticker import (
    Ticker,
    _build_ticker_iter,
    _CircleBufferMsg,
    _draw_hires_circle,
    _enqueue_ticker_objects,
    _has_index,
    _maybe_wrap,
    _swap,
)


def test_maybe_wrap_skips_wrap_when_canvas_fits():
    # Smallsign: panel_h == content_height == 16, scale=1 → no wrap needed.
    frame = LedFrame(led_cols=32, led_chain_length=5)
    canvas = frame.get_clean_canvas()
    # The stub canvas height is 32; use content_height=canvas.height so it fits.
    result = _maybe_wrap(canvas, scale=1, content_height=canvas.height)
    assert result is canvas
    assert not isinstance(result, ScaledCanvas)


def test_maybe_wrap_engages_when_content_height_smaller_than_panel():
    # Bigsign running at scale=1: panel_h=64, content_height=16 → must wrap
    # so widgets see canvas.height == 16 and content is vertically centered.
    frame = LedFrame(
        led_rows=32, led_cols=64, led_chain_length=8, led_pixel_mapper_config="U-mapper"
    )
    canvas = frame.get_clean_canvas()
    assert canvas.height == 64  # sanity-check the test fixture
    result = _maybe_wrap(canvas, scale=1, content_height=16)
    assert isinstance(result, ScaledCanvas)
    assert result.scale == 1
    assert result.real is canvas
    assert result.height == 16


def test_maybe_wrap_returns_scaled_canvas_at_scale_4():
    frame = LedFrame(
        led_rows=32, led_cols=64, led_chain_length=8, led_pixel_mapper_config="U-mapper"
    )
    canvas = frame.get_clean_canvas()
    result = _maybe_wrap(canvas, scale=4)
    assert isinstance(result, ScaledCanvas)
    assert result.scale == 4
    assert result.real is canvas


def test_swap_handles_real_canvas():
    frame = LedFrame(led_cols=32, led_chain_length=5)
    canvas = frame.get_clean_canvas()
    new_canvas = _swap(canvas, frame)
    # Stub returns a different canvas object on swap
    assert new_canvas is not None


def test_swap_handles_scaled_canvas_in_place():
    frame = LedFrame(
        led_rows=32, led_cols=64, led_chain_length=8, led_pixel_mapper_config="U-mapper"
    )
    canvas = frame.get_clean_canvas()
    wrapper = ScaledCanvas(canvas, scale=4)
    original_real = wrapper.real
    result = _swap(wrapper, frame)
    # Returns the same wrapper object, but its `.real` was swapped
    assert result is wrapper
    assert wrapper.real is not original_real


def test_has_index_true():
    assert _has_index(0, [1, 2, 3]) is True
    assert _has_index(2, [1, 2, 3]) is True


def test_has_index_false():
    assert _has_index(5, [1, 2, 3]) is False
    assert _has_index(0, []) is False


class TestBuildTickerIter:
    def test_loop_count_1(self):
        items = [1, 2, 3]
        result = list(_build_ticker_iter(items, loop_count=1))
        assert result == [1, 2, 3]

    def test_loop_count_2(self):
        items = [1, 2, 3]
        result = list(_build_ticker_iter(items, loop_count=2))
        assert result == [1, 2, 3, 1, 2, 3]

    def test_loop_count_0_cycles(self):
        items = [1, 2, 3]
        it = _build_ticker_iter(items, loop_count=0)
        result = list(itertools.islice(it, 9))
        assert result == [1, 2, 3, 1, 2, 3, 1, 2, 3]

    def test_with_title(self):
        items = [1, 2]
        result = list(_build_ticker_iter(items, title="title", loop_count=1))
        assert result == ["title", 1, 2]

    def test_with_title_and_cycle(self):
        items = [1, 2]
        it = _build_ticker_iter(items, title="title", loop_count=0)
        result = list(itertools.islice(it, 5))
        assert result == ["title", 1, 2, 1, 2]


class TestEnqueueTickerObjects:
    async def test_enqueues_all(self):
        queue = asyncio.Queue()
        items = [1, 2, 3]
        it = iter(items)

        asyncio.create_task(_enqueue_ticker_objects(it, queue))
        results = []
        results.append(await queue.get())

        while not queue.empty():
            results.append(await queue.get())
            await asyncio.sleep(0.01)

        assert results == items

    async def test_enqueues_with_title(self):
        queue = asyncio.Queue()
        it = _build_ticker_iter([1, 2], title="T", loop_count=1)

        asyncio.create_task(_enqueue_ticker_objects(it, queue))
        results = []
        results.append(await queue.get())

        while not queue.empty():
            results.append(await queue.get())
            await asyncio.sleep(0.01)

        assert results == ["T", 1, 2]


def _make_widget(content_width: int = 40, end_padding: int = 6):
    """Mock widget that mimics TickerMessage's draw return contract:
    cursor_pos returned = pos + content_width + end_padding.
    """
    w = mock.Mock()
    w.draw.side_effect = lambda c, cursor_pos=0, **kw: (
        c,
        cursor_pos + content_width + end_padding,
    )
    return w


class TestScrollSideBySideBufferDrawn:
    """Regression test: when the queue serves a new monitor, the
    buffer_message must NOT be skipped on the first frame after the pull.

    Previously the inner loop's `mon_index += 1` jumped past the
    just-appended buffer's index, so the next_monitor was drawn at the
    title's end (no spacing) for one frame — visible as a single-column
    yellow bar at the right edge of the panel.
    """

    async def test_buffer_drawn_on_first_pull_frame(self, no_sleep):
        # Title that, after one decrement, leaves room for next widget.
        title = _make_widget(content_width=40)  # returns pos + 46
        next_monitor = _make_widget(content_width=20)
        buffer_msg = _make_widget(content_width=10)

        canvas = mock.Mock()
        canvas.width = 64
        canvas.Clear = mock.Mock()

        frame = mock.Mock()
        frame.swap = mock.Mock(return_value=canvas)

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put(title)
        await queue.put(next_monitor)

        ticker = Ticker(
            monitors=[], frame=frame, notif_queue=queue, buffer_msg=buffer_msg
        )

        # Run a few iterations then cancel
        async def runner():
            await ticker._scroll_side_by_side(
                canvas,
                cursor_pos=18,  # title at pos=18, end at 64; next iter end at 63
                hold_at_end=0,
            )

        task = asyncio.create_task(runner())
        # let a few iterations run
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # The buffer_message MUST have been drawn at least once.
        assert buffer_msg.draw.called, (
            "buffer_message was never drawn — the inner loop is skipping "
            "the just-appended buffer index, causing the 'yellow flash' bug."
        )


def test_draw_hires_circle_paints_filled_disk_on_scaled_canvas():
    """The disk fills a 32x32 physical bounding box centered in the
    content band, with the documented row-half-widths."""
    real = MagicMock()
    real.width = 256
    real.height = 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    # canvas._y_offset = (64 - 16*4) // 2 = 0

    out_canvas, cursor = _draw_hires_circle(canvas, cursor_pos=0, color=RGB_WHITE)

    assert out_canvas is canvas
    assert cursor == 10  # logical advance width

    # All SetPixel calls landed on the underlying real canvas
    # (constraint #11 — paint at physical resolution).
    assert real.SetPixel.called
    assert canvas is not None

    # Pixel set lives in a 32x32 physical bounding box. Cursor=0 puts
    # the circle at x=0 logical → x=4..36 physical (1px pad + 32px disk;
    # the disk extends from center-radius to center+radius, which is
    # (1*4)+16=20 ± 16 = [4,36]). y in [16, 48] physical (center at
    # 0 + (16*4)//2 = 32 ± 16 = [16,48]).
    coords = {(c.args[0], c.args[1]) for c in real.SetPixel.call_args_list}
    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    assert min(xs) >= 4 and max(xs) <= 36, f"x out of [4,36]: {min(xs)}..{max(xs)}"
    assert min(ys) >= 16 and max(ys) <= 48, f"y out of [16,48]: {min(ys)}..{max(ys)}"

    # Disk count is ~π * 16² ≈ 804. Allow ±5% for integer-math rounding.
    assert 760 <= len(coords) <= 850, f"disk pixel count {len(coords)} out of range"


def test_draw_hires_circle_color_applied_uniformly():
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    _draw_hires_circle(canvas, cursor_pos=0, color=(225, 48, 108))

    for call in real.SetPixel.call_args_list:
        _, _, r, g, b = call.args
        assert (r, g, b) == (225, 48, 108)


@pytest.mark.parametrize("scale", [1, 4])
def test_draw_hires_circle_advance_is_ten_at_any_scale(scale):
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=scale, content_height=16)
    _, cursor = _draw_hires_circle(canvas, cursor_pos=42, color=RGB_WHITE)
    assert cursor == 42 + 10


class TestScrollOneByOneReturnsLastPos:
    """Regression: `_scroll_one_by_one` must return the position at which
    the last widget was drawn, so `Ticker.last_scroll_pos` reflects reality
    instead of staying at its 0 default. Without this, the inter-section
    dissolve in app.py renders the outgoing widget at pos=0 (a one-frame
    flash-back of the widget reappearing center-canvas before the dissolve
    begins).
    """

    async def test_returns_negative_pos_after_widget_exits_left(self, no_sleep):
        widget = _make_widget(content_width=20)
        canvas = mock.Mock()
        canvas.width = 64
        canvas.Clear = mock.Mock()
        frame = mock.Mock()
        frame.swap = mock.Mock(return_value=canvas)

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put(widget)

        ticker = Ticker(monitors=[], frame=frame, notif_queue=queue)

        result = await ticker._scroll_one_by_one(
            canvas,
            cursor_pos=0,
        )
        # Widget exits left -> last_drawn_pos should be heavily negative
        # (specifically, at most -content_width so the widget is fully
        # off-canvas left).
        assert result < 0, (
            "Expected last_drawn_pos < 0 once the widget scrolls off the "
            f"left edge; got {result}. The dissolve will draw the outgoing "
            "widget at pos=0 (flash-back bug) instead of off-screen."
        )


def test_circle_buffer_msg_smallsign_delegates_to_super_draw():
    """On a plain Canvas (no ScaledCanvas wrap), _CircleBufferMsg
    must call TickerMessage.draw — pixel-identical to today's
    DEFAULT_BUFFER_MSG. Tripwire for zero-drift on smallsign."""
    from unittest.mock import patch

    plain_canvas = MagicMock()
    plain_canvas.width = 160
    plain_canvas.height = 16
    # Not a ScaledCanvas — isinstance(plain_canvas, ScaledCanvas) is False.

    msg = _CircleBufferMsg(text=" • ", center=False, font_color=RGB_WHITE)

    # Verify _draw_hires_circle is NOT called on the smallsign path
    with patch("led_ticker.ticker._draw_hires_circle") as mock_hires:
        out, cursor = msg.draw(plain_canvas, cursor_pos=0)
        assert not mock_hires.called, (
            "smallsign path must delegate to super().draw(), "
            "not call _draw_hires_circle"
        )

    # And that draw returned the canvas and an advance > 0
    # (TickerMessage's normal " • " advance depends on the default
    # font's bullet width plus end padding).
    assert out is plain_canvas
    assert cursor > 0


def test_circle_buffer_msg_hires_path_paints_circle():
    """On ScaledCanvas, _CircleBufferMsg.draw must paint the hi-res
    disk via _draw_hires_circle (not delegate to BDF)."""
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    msg = _CircleBufferMsg(text=" • ", center=False, font_color=RGB_WHITE)
    out, cursor = msg.draw(canvas, cursor_pos=0)

    assert out is canvas
    assert cursor == 10  # logical advance
    # Hires path painted SetPixel on the real canvas (not on the wrapper).
    assert real.SetPixel.called


def test_circle_buffer_msg_hires_rainbow_animates_per_frame():
    """Rainbow font_color produces different colors on successive
    draws once advance_frame() ticks the counter."""
    real = MagicMock()
    real.width, real.height = 256, 64
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    msg = _CircleBufferMsg(text=" • ", center=False, font_color=Rainbow())

    msg.draw(canvas, cursor_pos=0)
    first_color = real.SetPixel.call_args_list[0].args[2:5]

    # Advance several frames to ensure the rainbow hue moves past
    # any quantization plateau.
    for _ in range(30):
        msg.advance_frame()
    real.SetPixel.reset_mock()
    msg.draw(canvas, cursor_pos=0)
    second_color = real.SetPixel.call_args_list[0].args[2:5]

    assert (
        first_color != second_color
    ), f"rainbow did not animate: both frames painted {first_color}"


def test_default_buffer_msg_is_circle_buffer_msg():
    """DEFAULT_BUFFER_MSG must be a _CircleBufferMsg so bigsign sees
    the hi-res circle automatically. Tripwire against accidental
    revert to plain TickerMessage(' • ', ...)."""
    from led_ticker.ticker import DEFAULT_BUFFER_MSG

    assert isinstance(DEFAULT_BUFFER_MSG, _CircleBufferMsg)
    assert DEFAULT_BUFFER_MSG.text == " • "


class TestHasPlayDispatch:
    def test_returns_true_for_async_play(self):
        class AsyncWidget:
            async def play(self, canvas): ...

        assert Ticker._has_play(AsyncWidget()) is True

    def test_returns_false_for_no_play(self):
        class DrawOnlyWidget:
            def draw(self, canvas, cursor_pos=0): ...

        assert Ticker._has_play(DrawOnlyWidget()) is False

    def test_raises_for_sync_play(self):
        class SyncPlayWidget:
            def play(self, canvas): ...

        with pytest.raises(RuntimeError, match="play.*not.*coroutine"):
            Ticker._has_play(SyncPlayWidget())

    def test_mock_returns_false_not_raises(self):
        """MagicMock auto-creates .play on access — must not raise."""
        w = MagicMock()
        assert Ticker._has_play(w) is False


class TestTickerMethodsMigrated:
    """Verify that the engine operations are now Ticker instance/static methods."""

    def test_has_play_is_static_method(self):
        assert callable(Ticker._has_play)

    def test_set_logical_scale_is_static_method(self):
        assert callable(Ticker._set_logical_scale)

    def test_hold_ticks_method_exists(self):
        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._hold_ticks)

    def test_swap_and_scroll_is_instance_method(self):
        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._swap_and_scroll)

    def test_scroll_between_is_instance_method(self):
        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._scroll_between)

    def test_play_widget_is_instance_method(self):
        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._play_widget)

    def test_show_one_is_instance_method(self):
        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._show_one)

    def test_run_swap_is_instance_method(self):
        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._run_swap)

    def test_run_gif_is_instance_method(self):
        from unittest.mock import MagicMock

        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._run_gif)

    def test_scroll_and_delay_is_instance_method(self):
        from unittest.mock import MagicMock

        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._scroll_and_delay)

    def test_scroll_one_by_one_is_instance_method(self):
        from unittest.mock import MagicMock

        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._scroll_one_by_one)

    def test_scroll_side_by_side_is_instance_method(self):
        from unittest.mock import MagicMock

        ticker = Ticker(monitors=[], frame=MagicMock())
        assert callable(ticker._scroll_side_by_side)

    def test_advance_frame_if_supported_is_instance_method(self):
        from unittest.mock import MagicMock

        ticker = Ticker(monitors=[], frame=MagicMock())
        assert hasattr(ticker, "_advance_frame_if_supported")
        assert callable(ticker._advance_frame_if_supported)


class TestTickerVisitCounter:
    """_show_one increments _current_visit before each widget visit (Large #4)."""

    @pytest.mark.asyncio
    async def test_current_visit_increments_per_show_one(self, no_sleep):
        """_show_one increments _current_visit before each widget visit."""
        from unittest.mock import MagicMock

        frame = MagicMock()
        frame.get_clean_canvas.return_value = MagicMock(width=256, height=64)
        frame.swap.return_value = MagicMock(width=256, height=64)

        ticker = Ticker(monitors=[], frame=frame)
        assert ticker._current_visit == 0

        canvas = MagicMock(width=256, height=64)
        widget = MagicMock()
        widget.hold_time = 0.0
        widget.draw.return_value = (canvas, 0)
        widget.forces_offscreen_scroll = False
        widget.wraps_forever = False

        await ticker._show_one(canvas, widget, hold_time=0.05)
        assert ticker._current_visit == 1

        await ticker._show_one(canvas, widget, hold_time=0.05)
        assert ticker._current_visit == 2

    def test_visit_counter_starts_at_zero(self):
        from unittest.mock import MagicMock

        ticker = Ticker(monitors=[], frame=MagicMock())
        assert ticker._visit_counter == 0
        assert ticker._current_visit == 0

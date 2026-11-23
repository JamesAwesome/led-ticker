"""#525 on the image hosts: `_play_with_text` / `_play_with_two_row_text`
tick at ``scroll_speed_ms`` (floor 20) but a frame must still mean
ENGINE_TICK_MS of wall clock, and the settle extension (#526) must be
converted from frames back into this loop's ticks."""

import math

import attrs
import pytest

from led_ticker._types import Canvas
from led_ticker.animations import Typewriter
from led_ticker.color_providers import ColorProviderBase
from led_ticker.constants import ENGINE_TICK_MS, MAX_SETTLE_MS
from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL
from led_ticker.widgets._image_base import _BaseImageWidget


class _RestProvider(ColorProviderBase):
    frame_invariant = False
    per_char = False

    def __init__(self, remaining: int) -> None:
        self.remaining = remaining

    def color_for(self, frame, char_index, total_chars):
        from rgbmatrix.graphics import Color

        return Color(255, 255, 255)

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        return self.remaining


@attrs.define
class _Img(_BaseImageWidget):
    paints: int = attrs.field(init=False, default=0)

    def __attrs_post_init__(self) -> None:
        self._validate_common(image_align="center", fit="pillarbox")

    def _paint_full(self, canvas: Canvas) -> None:
        self.paints += 1

    def _paint_skip_black(self, canvas: Canvas) -> None:
        self.paints += 1

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        pass

    def _pick_frame_for_elapsed(self, elapsed_ms: int) -> None:
        pass


@pytest.fixture
def instant_sleep(monkeypatch):
    async def _instant(_):
        pass

    monkeypatch.setattr("led_ticker.widgets._image_base.asyncio.sleep", _instant)


def _canvas():
    from rgbmatrix import _StubCanvas

    return _StubCanvas(width=160, height=16)


def _single(**kw) -> _Img:
    kw.setdefault("font", FONT_DEFAULT)
    kw.setdefault("font_size", None)
    kw.setdefault("text_align", "left")
    w = _Img(**kw)
    w._logical_scale = 1
    return w


def _two_row(**kw) -> _Img:
    kw.setdefault("font", FONT_SMALL)
    kw.setdefault("font_size", None)
    w = _Img(**kw)
    w._logical_scale = 1
    return w


class TestSingleRowCadence:
    @pytest.mark.parametrize(
        ("tick_ms", "frames"),
        [(20, 10), (50, 25), (100, 50)],
        ids=["20ms→10", "50ms→25(parity)", "100ms→50"],
    )
    async def test_held_text_frames_track_wall_clock(
        self, swapping_frame, instant_sleep, tick_ms, frames
    ):
        """25 ticks: at 20 ms that is 500 ms = 10 frames, not 25."""
        w = _single(
            text="hi", font_color=_RestProvider(remaining=0), scroll_speed_ms=tick_ms
        )
        swapping_frame.swap.return_value = _canvas()
        await w._play_with_text(_canvas(), swapping_frame, n_ticks=25)
        assert w.paints == 25
        assert w._frame_count == frames

    async def test_typewriter_reveals_at_wall_clock_rate(
        self, swapping_frame, instant_sleep
    ):
        """'HELLO WOR' at frames_per_char=3 is done at frame 24 = 1.2 s.
        At 20 ms ticks a 25-tick hold is 10 frames; the settle seam then
        owes 14 frames = 700 ms = 35 ticks, and the reveal is complete."""
        w = _single(
            text="HELLO WOR",
            animation=Typewriter(frames_per_char=3),
            scroll_speed_ms=20,
        )
        swapping_frame.swap.return_value = _canvas()
        await w._play_with_text(_canvas(), swapping_frame, n_ticks=25)
        assert w.frames_to_transition_ready() == 0
        assert w.frame_for("animation") == 24
        assert w.paints == 25 + 35


class TestSettleConversion:
    """`frames_to_transition_ready` is in 50 ms frames; the loop owes
    ceil(frames × 50 / tick_ms) ticks, capped at MAX_SETTLE_MS of wall
    clock whatever the tick."""

    @pytest.mark.parametrize("tick_ms", [20, 50, 100])
    async def test_extension_is_wall_clock(
        self, swapping_frame, instant_sleep, tick_ms
    ):
        w = _single(
            text="hi", font_color=_RestProvider(remaining=15), scroll_speed_ms=tick_ms
        )
        swapping_frame.swap.return_value = _canvas()
        await w._play_with_text(_canvas(), swapping_frame, n_ticks=5)
        extra = math.ceil(15 * ENGINE_TICK_MS / tick_ms)
        assert w.paints == 5 + extra
        assert w._frame_count >= 5 * tick_ms // ENGINE_TICK_MS + 15

    async def test_carry_is_credited(self, swapping_frame, instant_sleep):
        """60 ms ticks × 5 = 300 ms = 6 frames exactly (carry 0); 7 ticks =
        420 ms = 8 frames with 20 ms banked, so 10 owed frames need only
        ceil((500 − 20) / 60) = 8 ticks, not 9."""
        w = _single(
            text="hi", font_color=_RestProvider(remaining=10), scroll_speed_ms=60
        )
        swapping_frame.swap.return_value = _canvas()
        await w._play_with_text(_canvas(), swapping_frame, n_ticks=7)
        assert w.paints == 7 + 8

    @pytest.mark.parametrize("tick_ms", [20, 100])
    async def test_cap_is_one_second_of_wall_clock(
        self, swapping_frame, instant_sleep, tick_ms
    ):
        over = MAX_SETTLE_MS // ENGINE_TICK_MS + 1  # 21 frames = 1.05 s
        w = _single(
            text="hi", font_color=_RestProvider(remaining=over), scroll_speed_ms=tick_ms
        )
        swapping_frame.swap.return_value = _canvas()
        await w._play_with_text(_canvas(), swapping_frame, n_ticks=5)
        assert w.paints == 5


class TestTwoRowCadence:
    async def test_held_rows_frames_track_wall_clock(
        self, swapping_frame, instant_sleep
    ):
        w = _two_row(
            top_text="A",
            bottom_text="B",
            top_color=_RestProvider(remaining=0),
            scroll_speed_ms=20,
        )
        swapping_frame.swap.return_value = _canvas()
        await w._play_with_two_row_text(_canvas(), swapping_frame, n_ticks=25)
        assert w.paints == 25
        assert w._frame_count == 10

    async def test_settle_extension_is_wall_clock(self, swapping_frame, instant_sleep):
        w = _two_row(
            top_text="A",
            bottom_text="B",
            top_color=_RestProvider(remaining=6),
            scroll_speed_ms=100,
        )
        swapping_frame.swap.return_value = _canvas()
        await w._play_with_two_row_text(_canvas(), swapping_frame, n_ticks=4)
        assert w.paints == 4 + 3  # 6 frames = 300 ms = 3 ticks

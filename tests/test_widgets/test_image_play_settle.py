"""Settle-to-rest on play()-style image widgets (#526).

`_BaseImageWidget._play_with_text` / `_play_with_two_row_text` own their
render loop, so the engine's `_swap_and_scroll` settle seam (#305) never
sees them. Without a settle of their own, a typewriter reveal can end
unfinished and a blink can hand the transition its OFF frame. These tests
pin the parity: after the natural tick count, the loop appends exactly
`frames_to_transition_ready()` extra ticks — all-or-nothing against a
~1 s wall-clock cap in THIS loop's tick units — and only for held text.
"""

import attrs
import pytest

from led_ticker._types import Canvas
from led_ticker.animations import Typewriter
from led_ticker.color_providers import ColorProviderBase
from led_ticker.constants import ENGINE_TICK_MS, MAX_SETTLE_MS, MAX_SETTLE_TICKS
from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL
from led_ticker.widgets._image_base import _BaseImageWidget


class _RestProvider(ColorProviderBase):
    """Whole-string provider reporting a fixed frames-to-rest. Stands in
    for Shimmer so the tests don't depend on its sweep geometry."""

    frame_invariant = False
    per_char = False

    def __init__(self, remaining: int) -> None:
        self.remaining = remaining
        self.ready_calls = 0

    def color_for(self, frame, char_index, total_chars):
        from rgbmatrix.graphics import Color

        return Color(255, 255, 255)

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        self.ready_calls += 1
        return self.remaining


@attrs.define
class _Img(_BaseImageWidget):
    paint_full_calls: list = attrs.field(factory=list)
    elapsed_seen: list = attrs.field(factory=list)

    def __attrs_post_init__(self) -> None:
        self._validate_common(image_align="center", fit="pillarbox")

    def _paint_full(self, canvas: Canvas) -> None:
        self.paint_full_calls.append(canvas)

    def _paint_skip_black(self, canvas: Canvas) -> None:
        self.paint_full_calls.append(canvas)

    def _load(self, panel_w: int = 0, panel_h: int = 0) -> None:
        pass

    def _pick_frame_for_elapsed(self, elapsed_ms: int) -> None:
        self.elapsed_seen.append(elapsed_ms)


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


class TestConstants:
    def test_cap_is_one_second_of_engine_ticks(self):
        assert MAX_SETTLE_MS == 1000
        assert MAX_SETTLE_TICKS == MAX_SETTLE_MS // ENGINE_TICK_MS

    def test_ticker_still_reexports(self):
        from led_ticker import ticker

        assert ticker.MAX_SETTLE_TICKS is MAX_SETTLE_TICKS

    def test_api_minor_guarantees_image_host_settle(self):
        """Plugins gate on this: `flair.blink` may rely on image hosts
        settling once `API_VERSION >= (1, 4)`."""
        from led_ticker import plugin

        assert plugin.API_VERSION >= (1, 4)


class TestSingleRowSettle:
    async def test_typewriter_finishes_before_return(
        self, swapping_frame, instant_sleep
    ):
        """9 reveal units × 3 frames/unit → done at frame 24. A 10-tick
        hold leaves 14 frames; the loop must run them (14 ≤ cap 20) so
        the transition composites the completed reveal."""
        w = _single(text="HELLO WOR", animation=Typewriter(frames_per_char=3))
        swapping_frame.swap.return_value = _canvas()

        await w._play_with_text(_canvas(), swapping_frame, n_ticks=10)

        assert w.frames_to_transition_ready() == 0
        assert len(w.paint_full_calls) == 24

    async def test_extends_by_exactly_remaining(self, swapping_frame, instant_sleep):
        prov = _RestProvider(remaining=7)
        w = _single(text="hi", font_color=prov)
        swapping_frame.swap.return_value = _canvas()

        await w._play_with_text(_canvas(), swapping_frame, n_ticks=5)

        assert len(w.paint_full_calls) == 5 + 7
        assert w._frame_count == 5 + 7
        # Consulted once at the handoff; a settled loop never re-asks.
        assert prov.ready_calls == 1

    async def test_over_cap_extends_zero(self, swapping_frame, instant_sleep):
        """All-or-nothing: remaining > cap → no extension (mirrors
        _swap_and_scroll)."""
        cap = MAX_SETTLE_MS // 50  # default scroll_speed_ms is 50
        w = _single(text="hi", font_color=_RestProvider(remaining=cap + 1))
        swapping_frame.swap.return_value = _canvas()

        await w._play_with_text(_canvas(), swapping_frame, n_ticks=5)

        assert len(w.paint_full_calls) == 5

    async def test_cap_is_wall_clock_in_this_loops_tick_units(
        self, swapping_frame, instant_sleep
    ):
        """This loop ticks at scroll_speed_ms, not ENGINE_TICK_MS, so the
        ~1 s budget is MAX_SETTLE_MS // tick_ms frames. At 100 ms ticks
        15 frames is 1.5 s → refused; at 50 ms it is 0.75 s → granted."""
        slow = _single(
            text="hi", font_color=_RestProvider(remaining=15), scroll_speed_ms=100
        )
        swapping_frame.swap.return_value = _canvas()
        await slow._play_with_text(_canvas(), swapping_frame, n_ticks=5)
        assert len(slow.paint_full_calls) == 5

        fast = _single(
            text="hi", font_color=_RestProvider(remaining=15), scroll_speed_ms=50
        )
        await fast._play_with_text(_canvas(), swapping_frame, n_ticks=5)
        assert len(fast.paint_full_calls) == 5 + 15

    async def test_scrolling_text_never_settles(self, swapping_frame, instant_sleep):
        """A marquee has no rest point; extra ticks would start a partial
        re-entry before the transition. n_ticks=400 clears the one-
        traversal floor (160 + text width) so the paint count is exact."""
        prov = _RestProvider(remaining=5)
        w = _single(text="hi", text_align="scroll_over", font_color=prov)
        swapping_frame.swap.return_value = _canvas()

        await w._play_with_text(_canvas(), swapping_frame, n_ticks=400)

        assert len(w.paint_full_calls) == 400
        assert prov.ready_calls == 0

    async def test_zero_remaining_is_byte_identical(
        self, swapping_frame, instant_sleep
    ):
        w = _single(text="hi", font_color=_RestProvider(remaining=0))
        swapping_frame.swap.return_value = _canvas()

        await w._play_with_text(_canvas(), swapping_frame, n_ticks=6)

        assert len(w.paint_full_calls) == 6

    async def test_elapsed_stays_monotonic_through_settle(
        self, swapping_frame, instant_sleep
    ):
        """A gif must keep advancing during the settle ticks, not snap
        back to frame 0: `_pick_frame_for_elapsed` sees one strictly
        increasing series across the whole extended loop."""
        w = _single(text="hi", font_color=_RestProvider(remaining=4))
        swapping_frame.swap.return_value = _canvas()

        await w._play_with_text(_canvas(), swapping_frame, n_ticks=5)

        assert w.elapsed_seen == [t * 50 for t in range(5 + 4)]

    async def test_settle_ticks_follow_the_back_buffer(
        self, swapping_frame, instant_sleep
    ):
        """Constraint #1/#10 on the settle ticks: each extra tick paints
        the canvas the previous swap handed back, so the painted canvases
        alternate rather than sticking on one buffer."""
        w = _single(text="hi", font_color=_RestProvider(remaining=4))
        canvas_a, canvas_b = _canvas(), _canvas()
        swapping_frame.swap.side_effect = [canvas_b, canvas_a] * 10

        await w._play_with_text(canvas_a, swapping_frame, n_ticks=2)

        settle_paints = w.paint_full_calls[2:]
        assert len(settle_paints) == 4
        assert len({id(c) for c in settle_paints}) == 2


class TestTwoRowSettle:
    async def test_held_rows_extend_by_remaining(self, swapping_frame, instant_sleep):
        prov = _RestProvider(remaining=6)
        w = _two_row(top_text="A", bottom_text="B", top_color=prov)
        swapping_frame.swap.return_value = _canvas()

        await w._play_with_two_row_text(_canvas(), swapping_frame, n_ticks=4)

        assert len(w.paint_full_calls) == 4 + 6
        assert prov.ready_calls == 1

    async def test_scrolling_bottom_never_settles(self, swapping_frame, instant_sleep):
        prov = _RestProvider(remaining=6)
        w = _two_row(top_text="A", bottom_text="B" * 80, top_color=prov)
        swapping_frame.swap.return_value = _canvas()

        # n_ticks=600 clears the bottom-row traversal floor (160 + 80×5).
        await w._play_with_two_row_text(_canvas(), swapping_frame, n_ticks=600)

        assert len(w.paint_full_calls) == 600
        assert prov.ready_calls == 0

    async def test_over_cap_extends_zero(self, swapping_frame, instant_sleep):
        cap = MAX_SETTLE_MS // 50
        w = _two_row(
            top_text="A", bottom_text="B", bottom_color=_RestProvider(remaining=cap + 1)
        )
        swapping_frame.swap.return_value = _canvas()

        await w._play_with_two_row_text(_canvas(), swapping_frame, n_ticks=4)

        assert len(w.paint_full_calls) == 4


class TestEffectTotalChars:
    """The char count fed to `frames_to_rest` must match what the draw
    path hands `color_for`, or a Shimmer settles off its pause."""

    def test_font_color_counts_resolved_single_row_text(self):
        w = _single(text="hello")
        assert w._effect_total_chars("font_color") == 5

    def test_font_color_excludes_emoji_slugs(self):
        from led_ticker.pixel_emoji import count_text_chars

        w = _single(text="hi :sun: there")
        assert w._effect_total_chars("font_color") == count_text_chars("hi :sun: there")
        assert w._effect_total_chars("font_color") < len("hi :sun: there")

    def test_top_and_bottom_color_count_their_own_rows(self):
        w = _two_row(top_text="AB", bottom_text="CDEFG")
        assert w._effect_total_chars("top_color") == 2
        assert w._effect_total_chars("bottom_color") == 5


class _Blink:
    """Core-only stand-in for flair.blink: text is ON for the first
    `on_frames` of every `period`, blank otherwise. `frames_to_rest`
    reports the frames until the next ON phase."""

    emits_lens = False
    locks_resolution = False
    period = 20
    on_frames = 15

    def __init__(self, *, settles: bool = True) -> None:
        self.settles = settles

    def frame_for(self, frame, full_text, canvas_width, text_width):
        from led_ticker.animations import AnimationFrame

        on = frame % self.period < self.on_frames
        return AnimationFrame(visible_text=full_text if on else "")

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        if not self.settles:
            return 0
        t = frame % self.period
        return 0 if t < self.on_frames else self.period - t


def _white_pixels(canvas) -> int:
    return sum(1 for v in canvas._pixels.values() if v == (255, 255, 255))


class TestStillImagePlayEndToEnd:
    """The issue's repro (#526) through the real `StillImage.play()`:
    `hold_time=0.8` is 16 ticks at 50 ms, so a 20-frame / 75 %-duty
    blink ends its hold in the OFF phase. The last swapped frame — the
    one a transition composites — must carry lit text."""

    def _still(self, tmp_path, **kw):
        from PIL import Image
        from rgbmatrix.graphics import Color

        from led_ticker.widgets.still import StillImage

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        return StillImage(
            path=img_path,
            text="SALE",
            text_align="left",
            font=FONT_DEFAULT,
            font_color=Color(255, 255, 255),
            hold_time=0.8,
            **kw,
        )

    async def _run(self, widget, mocker):
        swapped: list = []
        buffers = [_canvas(), _canvas()]

        def _swap(c):
            swapped.append(c)
            return buffers[len(swapped) % 2]

        frame = mocker.MagicMock()
        frame.swap.side_effect = _swap
        mocker.patch("asyncio.sleep", new=mocker.AsyncMock())
        await widget.play(buffers[0], frame)
        return swapped

    async def test_last_frame_has_lit_text(self, tmp_path, mocker):
        widget = self._still(tmp_path, animation=_Blink())

        swapped = await self._run(widget, mocker)

        assert len(swapped) == 16 + 4
        assert widget.frames_to_transition_ready() == 0
        assert _white_pixels(swapped[-1]) > 0

    async def test_control_without_rest_report_ends_blank(self, tmp_path, mocker):
        """Documents the bug shape: an animation that reports no rest
        gets no settle and the hold ends on the OFF frame."""
        widget = self._still(tmp_path, animation=_Blink(settles=False))

        swapped = await self._run(widget, mocker)

        assert len(swapped) == 16
        assert _white_pixels(swapped[-1]) == 0

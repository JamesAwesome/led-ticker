"""FrameAwareBase.frames_to_transition_ready: max frames_to_rest across a
widget's animated effects, per-effect-kind char counts, never raises."""

import attrs
from rgbmatrix.graphics import Color

from led_ticker.animations import Typewriter
from led_ticker.color_providers import Shimmer
from led_ticker.widgets._frame_aware import FrameAwareBase
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.two_row import TwoRowMessage

# RGB_BLUE does not exist in led_ticker.colors — construct directly.
_WHITE = Color(255, 255, 255)
_BLUE = Color(40, 100, 255)


class _StubEffect:
    """Effect stub reporting a fixed frames_to_rest."""

    frame_invariant = False
    restart_on_visit = True

    def __init__(self, remaining: int) -> None:
        self.remaining = remaining
        self.seen_chars: list[int] = []

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        self.seen_chars.append(total_chars)
        return self.remaining


class _RaisingEffect:
    frame_invariant = False
    restart_on_visit = True

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        raise RuntimeError("boom")


@attrs.define
class _Widget(FrameAwareBase):
    text: str = "HELLO WORLD"
    font_color: object = None
    border: object = None
    animation: object = None


class TestFramesToTransitionReady:
    def test_no_effects_returns_zero(self) -> None:
        assert _Widget().frames_to_transition_ready() == 0

    def test_takes_max_across_effects(self) -> None:
        w = _Widget(font_color=_StubEffect(5), animation=_StubEffect(11))
        assert w.frames_to_transition_ready() == 11

    def test_effect_without_method_contributes_zero(self) -> None:
        class _NoRest:
            frame_invariant = True
            restart_on_visit = True

        w = _Widget(font_color=_NoRest(), animation=_StubEffect(4))
        assert w.frames_to_transition_ready() == 4

    def test_raising_effect_returns_zero_never_propagates(self) -> None:
        w = _Widget(font_color=_RaisingEffect(), animation=_StubEffect(9))
        assert w.frames_to_transition_ready() == 0

    def test_uses_per_effect_frame_counter(self) -> None:
        w = _Widget(font_color=_StubEffect(0))
        for _ in range(7):
            w.advance_frame()
        seen_frames: list[int] = []
        orig = w.font_color.frames_to_rest

        def spy(frame: int, total_chars: int) -> int:
            seen_frames.append(frame)
            return orig(frame, total_chars)

        w.font_color.frames_to_rest = spy
        w.frames_to_transition_ready()
        assert seen_frames == [7]


class TestEffectTotalChars:
    def test_ticker_message_animation_gets_raw_len(self) -> None:
        """Critical finding 1: the animation attr must see the RAW string
        length including :slug: chars."""
        w = TickerMessage(text="GO :sun: GO", animation=Typewriter())
        assert w._effect_total_chars("animation") == len("GO :sun: GO")  # 11

    def test_ticker_message_color_gets_emoji_excluded_count(self) -> None:
        """Color providers see the draw-path anchor: count_text_chars on
        the emoji path (":sun:" collapses to one emoji, contributing 0
        text chars)."""
        from led_ticker.pixel_emoji import count_text_chars

        w = TickerMessage(
            text="GO :sun: GO",
            font_color=Shimmer(_WHITE, _BLUE),
        )
        assert w._effect_total_chars("font_color") == count_text_chars("GO :sun: GO")

    def test_ticker_message_plain_text_color_gets_len(self) -> None:
        w = TickerMessage(text="HELLO", font_color=Shimmer(_WHITE, _BLUE))
        assert w._effect_total_chars("font_color") == 5

    def test_two_row_per_row_counts(self) -> None:
        w = TwoRowMessage(
            top_text="TOP",
            bottom_text="BOTTOM ROW",
            top_color=Shimmer(_WHITE, _BLUE),
            bottom_color=Shimmer(_WHITE, _BLUE),
        )
        assert w._effect_total_chars("top_color") == 3
        assert w._effect_total_chars("bottom_color") == 10

    def test_base_default_falls_back_to_text_attr(self) -> None:
        w = _Widget(text="ABCD")
        assert w._effect_total_chars("font_color") == 4

    def test_base_default_floor_is_one(self) -> None:
        w = _Widget(text="")
        assert w._effect_total_chars("font_color") == 1

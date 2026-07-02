"""frames_to_rest seam: providers report frames until their next natural
rest point (0 = at rest / no rest concept). Spec:
docs/superpowers/specs/2026-07-01-defer-to-rest-transitions-design.md
"""

import math

import pytest
from rgbmatrix.graphics import Color

from led_ticker.animations import Typewriter
from led_ticker.color_providers import (
    _SHIMMER_FPS,
    ColorCycle,
    Gradient,
    Rainbow,
    Random,
    Shimmer,
    _ConstantColor,
)
from led_ticker.constants import ENGINE_TICK_MS

# Default Shimmer width (used in _shimmer() factory below)
_DEFAULT_WIDTH = 8.0

_WHITE = Color(255, 255, 255)
_BLUE = Color(40, 100, 255)


def _shimmer(pause: float = 0.5, speed: float = 14.0) -> Shimmer:
    return Shimmer(_WHITE, _BLUE, speed=speed, pause=pause)


class TestShimmerFramesToRest:
    def test_mid_sweep_returns_exact_remaining(self) -> None:
        s = _shimmer()
        chars = 20
        travel = chars + s.width  # travel = chars + width (glide-in/out envelope)
        sweep = travel / s.speed * _SHIMMER_FPS
        # frame 10 is mid-sweep (travel=28, sweep=28/14*20=40 frames)
        assert s.frames_to_rest(10, chars) == math.ceil(sweep - 10)

    def test_pause_window_returns_zero(self) -> None:
        s = _shimmer(pause=1.0)
        chars = 20
        travel = chars + s.width
        sweep = travel / s.speed * _SHIMMER_FPS
        cycle = sweep + 1.0 * _SHIMMER_FPS
        # every integer frame inside [sweep, cycle) is at rest
        for frame in range(math.ceil(sweep), math.floor(cycle)):
            assert s.frames_to_rest(frame, chars) == 0, f"frame {frame}"

    def test_wraparound_beyond_one_cycle(self) -> None:
        s = _shimmer(pause=1.0)
        chars = 20
        travel = chars + s.width
        sweep = travel / s.speed * _SHIMMER_FPS
        cycle = sweep + 1.0 * _SHIMMER_FPS
        frame = math.floor(cycle) + 10  # 10 frames into the SECOND sweep
        t = float(frame) % cycle
        assert s.frames_to_rest(frame, chars) == math.ceil(sweep - t)

    def test_zero_pause_never_defers(self) -> None:
        s = _shimmer(pause=0.0)
        for frame in range(0, 200, 7):
            assert s.frames_to_rest(frame, 20) == 0

    def test_subframe_pause_never_defers(self) -> None:
        """pause=0.02 -> pause_frames=0.02*20=0.4 < 1: no landable rest tick
        exists; advancing would overshoot into the next sweep."""
        s = _shimmer(pause=0.02)
        for frame in range(0, 200, 7):
            assert s.frames_to_rest(frame, 20) == 0

    @pytest.mark.parametrize("frame", list(range(0, 120, 3)))
    @pytest.mark.parametrize("chars", [5, 20, 61])
    def test_advancing_by_result_lands_in_pause(self, frame: int, chars: int) -> None:
        """Property: advancing by frames_to_rest always lands inside the
        pause window. pause=0.5 -> pause_frames=0.5*20=10 >= 1, so a landable
        rest tick always exists: delta == 0 must mean we're ALREADY in
        the pause, and delta > 0 must land in it."""
        s = _shimmer(pause=0.5)
        delta = s.frames_to_rest(frame, chars)
        travel = chars + s.width
        sweep = travel / s.speed * _SHIMMER_FPS
        cycle = sweep + 0.5 * _SHIMMER_FPS
        if delta == 0:
            t = float(frame) % cycle
            assert t >= sweep, f"frame={frame}: delta=0 but mid-sweep (t={t})"
        else:
            landed_t = float(frame + delta) % cycle
            assert landed_t >= sweep, (
                f"frame={frame} delta={delta} landed_t={landed_t} sweep={sweep}"
            )

    def test_color_for_and_frames_to_rest_agree_on_geometry(self) -> None:
        """The pause window frames_to_rest reports must be exactly where
        color_for returns base for every char (the flat rest state)."""
        s = _shimmer(pause=1.0)
        chars = 10
        for frame in range(0, 150):
            at_rest = s.frames_to_rest(frame, chars) == 0
            travel = chars + s.width
            sweep = travel / s.speed * _SHIMMER_FPS
            cycle = sweep + 1.0 * _SHIMMER_FPS
            in_pause = (float(frame) % cycle) >= sweep
            if in_pause:
                assert at_rest, f"frame {frame}: in pause but not at rest"


class TestProviderDefaults:
    @pytest.mark.parametrize(
        "provider",
        [
            _ConstantColor(_WHITE),
            Random(),
            Gradient(_WHITE, _BLUE),
            Rainbow(),
            ColorCycle(),
        ],
        ids=["constant", "random", "gradient", "rainbow", "color_cycle"],
    )
    def test_default_never_defers(self, provider) -> None:
        for frame in (0, 17, 500):
            assert provider.frames_to_rest(frame, 20) == 0


class TestTypewriterFramesToRest:
    def test_mid_type_exact_remaining(self) -> None:
        tw = Typewriter()  # frames_per_char=3, chars_per_frame=1
        total = 10
        # done at frame 3 * (ceil(10/1) - 1) = 27
        assert tw.frames_to_rest(0, total) == 27
        assert tw.frames_to_rest(20, total) == 7
        assert tw.frames_to_rest(27, total) == 0

    def test_done_stays_zero_forever(self) -> None:
        tw = Typewriter()
        for frame in (27, 28, 100, 10_000):
            assert tw.frames_to_rest(frame, 10) == 0

    def test_done_frame_matches_frame_for_reveal(self) -> None:
        """The frame frames_to_rest declares 'done' is exactly the first
        frame at which frame_for reveals the full text — the two formulas
        must agree."""
        tw = Typewriter(frames_per_char=3)
        text = "HELLO WORLD!!"
        total = len(text)
        done = 3 * (math.ceil(total / 1) - 1)
        assert tw.frame_for(done, text, 160, 80).visible_text == text
        assert tw.frame_for(done - 1, text, 160, 80).visible_text != text
        assert tw.frames_to_rest(done - 1, total) == 1
        assert tw.frames_to_rest(done, total) == 0

    def test_chars_per_frame_above_one(self) -> None:
        tw = Typewriter(chars_per_frame=2, frames_per_char=3)
        total = 10
        # done at 3 * (ceil(10/2) - 1) = 12
        assert tw.frames_to_rest(0, total) == 12
        assert tw.frames_to_rest(12, total) == 0

    def test_emoji_text_uses_raw_length(self) -> None:
        """Guard for Critical finding 1: rest math must consume raw
        len(full_text) INCLUDING :slug: characters. With the raw length
        the reveal is still in progress at the frame where the
        emoji-excluded count would claim done."""
        tw = Typewriter()
        text = "GO :sun: GO"  # len = 11 raw; emoji-excluded count = 6
        raw = len(text)
        wrong_done = 3 * (math.ceil(6 / 1) - 1)  # 15 — the WRONG answer
        assert tw.frames_to_rest(wrong_done, raw) > 0
        right_done = 3 * (math.ceil(raw / 1) - 1)  # 30
        assert tw.frames_to_rest(right_done, raw) == 0

    def test_zero_or_negative_chars(self) -> None:
        tw = Typewriter()
        assert tw.frames_to_rest(0, 0) == 0
        assert tw.frames_to_rest(0, -3) == 0


class TestTypingDurationSeconds:
    def test_matches_frames_to_rest_from_zero(self) -> None:
        """Formula-equality tripwire: the duration helper and
        frames_to_rest must be the same math — validate rule 61 depends
        on this staying true."""
        for total in (1, 7, 10, 40):
            for fpc in (1, 3, 6):
                tw = Typewriter(frames_per_char=fpc)
                expected = tw.frames_to_rest(0, total) * ENGINE_TICK_MS / 1000.0
                assert tw.typing_duration_seconds(total) == pytest.approx(expected)

    def test_forty_chars_at_defaults_is_about_six_seconds(self) -> None:
        tw = Typewriter()
        assert tw.typing_duration_seconds(40) == pytest.approx(
            3 * 39 * ENGINE_TICK_MS / 1000.0
        )  # 5.85 s

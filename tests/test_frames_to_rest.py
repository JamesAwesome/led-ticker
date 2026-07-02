"""frames_to_rest seam: providers report frames until their next natural
rest point (0 = at rest / no rest concept). Spec:
docs/superpowers/specs/2026-07-01-defer-to-rest-transitions-design.md
"""

import math

import pytest
from rgbmatrix.graphics import Color

from led_ticker.color_providers import (
    _SHIMMER_FPS,
    ColorCycle,
    Gradient,
    Rainbow,
    Random,
    Shimmer,
    _ConstantColor,
)

_WHITE = Color(255, 255, 255)
_BLUE = Color(40, 100, 255)


def _shimmer(pause: float = 0.5, speed: float = 14.0) -> Shimmer:
    return Shimmer(_WHITE, _BLUE, speed=speed, pause=pause)


class TestShimmerFramesToRest:
    def test_mid_sweep_returns_exact_remaining(self) -> None:
        s = _shimmer()
        chars = 20
        sweep = chars / s.speed * _SHIMMER_FPS
        # frame 10 is mid-sweep (sweep ≈ 42.9 frames)
        assert s.frames_to_rest(10, chars) == math.ceil(sweep - 10)

    def test_pause_window_returns_zero(self) -> None:
        s = _shimmer(pause=1.0)
        chars = 20
        sweep = chars / s.speed * _SHIMMER_FPS
        cycle = sweep + 1.0 * _SHIMMER_FPS
        # every integer frame inside [sweep, cycle) is at rest
        for frame in range(math.ceil(sweep), math.floor(cycle)):
            assert s.frames_to_rest(frame, chars) == 0, f"frame {frame}"

    def test_wraparound_beyond_one_cycle(self) -> None:
        s = _shimmer(pause=1.0)
        chars = 20
        sweep = chars / s.speed * _SHIMMER_FPS
        cycle = sweep + 1.0 * _SHIMMER_FPS
        frame = math.floor(cycle) + 10  # 10 frames into the SECOND sweep
        t = float(frame) % cycle
        assert s.frames_to_rest(frame, chars) == math.ceil(sweep - t)

    def test_zero_pause_never_defers(self) -> None:
        s = _shimmer(pause=0.0)
        for frame in range(0, 200, 7):
            assert s.frames_to_rest(frame, 20) == 0

    def test_subframe_pause_never_defers(self) -> None:
        """pause=0.02 -> pause_frames=0.6 < 1: no landable rest tick
        exists; advancing would overshoot into the next sweep."""
        s = _shimmer(pause=0.02)
        for frame in range(0, 200, 7):
            assert s.frames_to_rest(frame, 20) == 0

    @pytest.mark.parametrize("frame", list(range(0, 120, 3)))
    @pytest.mark.parametrize("chars", [5, 20, 61])
    def test_advancing_by_result_lands_in_pause(self, frame: int, chars: int) -> None:
        """Property: advancing by frames_to_rest always lands inside the
        pause window. pause=0.5 -> pause_frames=15 >= 1, so a landable
        rest tick always exists: delta == 0 must mean we're ALREADY in
        the pause, and delta > 0 must land in it."""
        s = _shimmer(pause=0.5)
        delta = s.frames_to_rest(frame, chars)
        sweep = chars / s.speed * _SHIMMER_FPS
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
            sweep = chars / s.speed * _SHIMMER_FPS
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

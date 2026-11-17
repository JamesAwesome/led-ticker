from pathlib import Path

import pytest
from tools.film.analyze import BBox, Footage, GrayFrames, Interval
from tools.film.clip import (
    LADDER,
    ClipSettings,
    CountMismatch,
    emit_gif_within_budget,
    gif_argv,
    mp4_argv,
    plan_clips,
)
from tools.film.runner import FakeRunner, Result


def _footage(n_segments: int) -> Footage:
    frames = GrayFrames(32, 18, 10.0, [bytes(32 * 18)] * 200)
    segs = [Interval(10 + 40 * i, 40 + 40 * i) for i in range(n_segments)]
    return Footage(frames, BBox(4, 6, 24, 4), [], [], segs)


def test_plan_clips_zips_names_in_order():
    f = _footage(2)
    assert plan_clips(f, ["a", "b"]) == [("a", f.segments[0]), ("b", f.segments[1])]


def test_plan_clips_count_mismatch_lists_both():
    with pytest.raises(CountMismatch) as e:
        plan_clips(_footage(3), ["a", "b"])
    msg = str(e.value)
    assert "3 segment" in msg and "2 name" in msg and "'a', 'b'" in msg


def test_gif_argv_has_two_pass_palette_and_scaled_crop():
    argv = gif_argv(
        Path("in.mp4"),
        Path("o.gif"),
        Interval(10, 50),
        10.0,
        BBox(10, 20, 100, 10),
        320,
        3840,
        ClipSettings(),
    )
    vf = argv[argv.index("-filter_complex") + 1]
    assert "crop=1200:120:120:240" in vf
    assert "fps=20" in vf and "scale=800:-1" in vf
    assert "palettegen=stats_mode=diff" in vf
    assert "paletteuse=dither=bayer:bayer_scale=3" in vf
    assert argv[argv.index("-ss") + 1] == "1.100"  # 1 frame trimmed at 10 fps
    assert argv[argv.index("-t") + 1] == "3.800"
    assert argv[-1] == "o.gif" and "-y" in argv


def test_mp4_argv_full_frame_when_bbox_none():
    argv = mp4_argv(
        Path("in.mp4"), Path("o.mp4"), Interval(10, 50), 10.0, None, 320, 3840
    )
    assert "-vf" not in argv
    assert "libx264" in argv and "+faststart" in argv


def test_mp4_argv_crops_when_bbox_given():
    argv = mp4_argv(
        Path("in.mp4"),
        Path("o.mp4"),
        Interval(10, 50),
        10.0,
        BBox(10, 20, 100, 10),
        320,
        3840,
    )
    assert argv[argv.index("-vf") + 1].startswith("crop=1200:120:120:240")


def _emit(sizes, settings=None):
    settings = settings or ClipSettings()
    it = iter(sizes)
    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 0, b"", b"")})
    out = emit_gif_within_budget(
        Path("in.mp4"),
        Path("o.gif"),
        Interval(10, 50),
        10.0,
        BBox(0, 0, 32, 18),
        320,
        3840,
        runner=runner,
        size_of=lambda p: next(it),
        settings=settings,
    )
    return out, runner


def test_emit_gif_walks_ladder_until_under_budget():
    (w, fps, n), runner = _emit([5_000_000, 3_000_000, 2_000_000])
    assert (w, fps, n) == (640, 15, 2_000_000)
    assert len(runner.calls) == 3


def test_emit_gif_stops_at_first_rung_that_fits():
    (w, fps, n), runner = _emit([1_000_000])
    assert (w, fps, n) == (800, 20, 1_000_000) and len(runner.calls) == 1


def test_emit_gif_over_budget_after_ladder_returns_last_rung():
    (w, fps, n), runner = _emit([9_000_000, 8_000_000, 7_000_000])
    assert (w, fps, n) == (640, 15, 7_000_000) and len(runner.calls) == len(LADDER)


def test_emit_gif_failed_ffmpeg_raises():
    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", b"boom")})
    with pytest.raises(RuntimeError, match="boom"):
        emit_gif_within_budget(
            Path("in.mp4"),
            Path("o.gif"),
            Interval(10, 50),
            10.0,
            BBox(0, 0, 32, 18),
            320,
            3840,
            runner=runner,
            size_of=lambda p: 0,
            settings=ClipSettings(),
        )

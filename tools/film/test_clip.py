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
    return Footage(frames, BBox(4, 6, 24, 4), [], [], segs, 255.0)


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
    assert vf.index("hqdn3d") < vf.index("fps=20")  # denoise real footage first
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
    sizes = [9_000_000 - i for i in range(len(LADDER))]
    (w, fps, n), runner = _emit(sizes)
    assert (w, fps) == LADDER[-1] and n == sizes[-1]
    assert len(runner.calls) == len(LADDER)


def test_ladder_descends_to_real_footage_rungs():
    assert LADDER[:3] == ((800, 20), (640, 20), (640, 15))
    assert (640, 12) in LADDER and LADDER[-1] == (480, 10)
    widths = [w for w, _ in LADDER]
    assert widths == sorted(widths, reverse=True)


def test_web_mp4_argv_is_small_denoised_and_cropped():
    from tools.film.clip import web_mp4_argv

    argv = web_mp4_argv(
        Path("in.mp4"),
        Path("o.web.mp4"),
        Interval(10, 50),
        10.0,
        BBox(10, 20, 120, 10),  # 1440 source px wide: wider than the docs width
        320,
        3840,
    )
    vf = argv[argv.index("-vf") + 1]
    assert "crop=1440:120:120:240" in vf and "hqdn3d" in vf and "scale=1280:-2" in vf
    assert argv[argv.index("-crf") + 1] == "24" and "+faststart" in argv
    assert "-an" in argv and argv[-1] == "o.web.mp4"


def test_web_mp4_argv_never_upscales_a_narrow_crop():
    """At zoom 100 the panel is ~900 source px wide; stretching that to 1280
    only blurs it. The web mp4 scales down to WEB_WIDTH, never up."""
    from tools.film.clip import web_mp4_argv

    argv = web_mp4_argv(
        Path("in.mp4"),
        Path("o.web.mp4"),
        Interval(10, 50),
        10.0,
        BBox(122, 79, 74, 8),  # 888 source px wide
        320,
        3840,
    )
    vf = argv[argv.index("-vf") + 1]
    assert "crop=888:96:1464:948" in vf
    assert "scale=888:-2" in vf and "scale=1280" not in vf


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


def _runner_ok():
    return FakeRunner(
        {
            "ffprobe": Result(["ffprobe"], 0, b"3840,2160\n", b""),
            "ffmpeg": lambda argv: Result(
                argv, 0, bytes(320 * 180 * 60) if "rawvideo" in argv else b"", b""
            ),
        }
    )


def _patch_analysis(monkeypatch):
    from tools.film import clip as clipmod

    frames = GrayFrames(320, 180, 10.0, [bytes(320 * 180)] * 60)
    footage = Footage(frames, BBox(10, 20, 100, 10), [], [], [Interval(5, 25)], 255.0)
    monkeypatch.setattr(clipmod, "decode_gray", lambda *a, **k: frames)
    monkeypatch.setattr(clipmod, "analyze_footage", lambda *a, **k: footage)
    monkeypatch.setattr(clipmod, "contact_sheet", lambda *a, **k: None)
    return footage


def test_clip_footage_full_frame_mp4_only_skips_gif_and_crop(tmp_path, monkeypatch):
    _patch_analysis(monkeypatch)
    manifest = tmp_path / "m.toml"
    manifest.write_text("[[playlist.section]] # film: youtube\n")
    runner = _runner_ok()
    from tools.film.clip import clip_footage

    written = clip_footage(
        Path("in.mp4"),
        manifest,
        tmp_path / "out",
        runner=runner,
        crop=None,
        take=1,
        mp4_names={"youtube"},
        hero_budget_names=set(),
        settings=ClipSettings(),
        full_frame=True,
        gif=False,
        size_of=lambda p: 1,
    )
    assert [p.name for p in written] == ["youtube.mp4"]
    encodes = [c for c in runner.calls if c[0] == "ffmpeg" and "rawvideo" not in c]
    assert (
        len(encodes) == 1
        and "-vf" not in encodes[0]
        and encodes[0][-1].endswith("youtube.mp4")
    )


def test_clip_footage_prints_detected_bbox_in_source_pixels(
    tmp_path, monkeypatch, capsys
):
    _patch_analysis(monkeypatch)
    manifest = tmp_path / "m.toml"
    manifest.write_text("[[playlist.section]] # film: a\n")
    from tools.film.clip import clip_footage

    clip_footage(
        Path("in.mp4"),
        manifest,
        tmp_path / "out",
        runner=_runner_ok(),
        crop=None,
        take=1,
        mp4_names=set(),
        hero_budget_names=set(),
        settings=ClipSettings(),
        size_of=lambda p: 1,
    )
    out = capsys.readouterr().out
    assert "bbox 10:20:100:10 (analysis)" in out and "120:240:1200:120 (source)" in out
    assert "peak luma 255" in out


def test_contact_sheet_argv_pulls_color_frames_from_source():
    from tools.film.clip import contact_sheet_argv

    argv = contact_sheet_argv(
        Path("in.mp4"),
        Path("a.contact.png"),
        Interval(10, 50),
        10.0,
        BBox(10, 20, 100, 10),
        320,
        3840,
    )
    vf = argv[argv.index("-filter_complex") + 1]
    assert "crop=1200:120:120:240" in vf and "tile=1x3" in vf
    assert argv[-1] == "a.contact.png"


def test_clip_footage_mp4_names_also_get_a_web_mp4_in_docs_mode(tmp_path, monkeypatch):
    _patch_analysis(monkeypatch)
    manifest = tmp_path / "m.toml"
    manifest.write_text("[[playlist.section]] # film: hero\n")
    from tools.film.clip import clip_footage

    written = clip_footage(
        Path("in.mp4"),
        manifest,
        tmp_path / "out",
        runner=_runner_ok(),
        crop=None,
        take=1,
        mp4_names={"hero"},
        hero_budget_names={"hero"},
        settings=ClipSettings(),
        size_of=lambda p: 1,
    )
    assert [p.name for p in written] == ["hero.gif", "hero.mp4", "hero.web.mp4"]

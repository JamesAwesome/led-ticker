from pathlib import Path

import pytest
from tools.film.analyze import (
    BBox,
    GrayFrames,
    IncompleteLoopError,
    Interval,
    NoSlateError,
    _dense_run,
    analyze_footage,
    decode_gray,
    find_panel_bbox,
    find_slates,
    mean_luma,
    saturated_fraction,
    segments_between,
)
from tools.film.runner import FakeRunner, Result


def gray(w: int, h: int, fill: int) -> bytearray:
    return bytearray([fill]) * (w * h)


def rect(frame: bytearray, w: int, box: BBox, value: int) -> None:
    for y in range(box.y, box.y + box.h):
        frame[y * w + box.x : y * w + box.x + box.w] = bytes([value]) * box.w


def test_find_slates_two_slates_min_length():
    # per-frame fraction of the panel box that is saturated
    frac = (
        [0.05] * 20
        + [0.97] * 10
        + [0.1] * 40
        + [0.97] * 2
        + [0.1] * 8
        + [0.95] * 10
        + [0.0] * 10
    )
    assert find_slates(frac, fps=10.0) == [Interval(20, 30), Interval(80, 90)]


def test_find_slates_none_raises():
    with pytest.raises(NoSlateError):
        find_slates([0.3] * 50, fps=10.0)


def test_saturated_fraction_counts_only_inside_the_box():
    f = gray(10, 10, 0)
    rect(f, 10, BBox(0, 0, 5, 10), 250)  # left half saturated
    assert saturated_fraction(bytes(f), BBox(0, 0, 10, 10), 10) == 0.5
    assert saturated_fraction(bytes(f), BBox(0, 0, 5, 10), 10) == 1.0
    assert saturated_fraction(bytes(f), BBox(5, 0, 5, 10), 10) == 0.0


def test_segments_between_excludes_tail():
    slates = [Interval(0, 10), Interval(50, 60), Interval(90, 100)]
    assert segments_between(slates, 120) == [Interval(10, 50), Interval(60, 90)]


def test_find_panel_bbox_ignores_static_bright_objects_and_pads():
    base = gray(320, 180, 0)
    rect(base, 320, BBox(0, 0, 60, 180), 255)  # blown-out window, static
    rect(base, 320, BBox(90, 80, 10, 10), 240)  # white plush touching the panel, static
    f1 = bytearray(base)
    rect(f1, 320, BBox(100, 80, 100, 10), 255)  # panel lit (slate)
    f2 = bytearray(base)
    rect(f2, 320, BBox(100, 80, 100, 10), 20)  # panel showing dark content
    b = find_panel_bbox([bytes(f1), bytes(f2), bytes(f1)], 320, 180)
    assert (b.x, b.w) == (96, 108)  # pad 4% of w=100 → 4 px each side
    assert (b.y, b.h) == (80, 10)  # 4% of h=10 rounds to 0


def test_find_panel_bbox_nothing_changes_raises():
    with pytest.raises(NoSlateError):
        find_panel_bbox([bytes(gray(32, 18, 200))] * 5, 32, 18)


def test_mean_luma_inside_bbox_only():
    f = gray(10, 10, 0)
    rect(f, 10, BBox(0, 0, 5, 10), 200)
    assert mean_luma(bytes(f), BBox(0, 0, 5, 10), 10) == 200.0
    assert mean_luma(bytes(f), None, 10) == 100.0


def test_decode_gray_builds_ffmpeg_argv_and_splits_frames():
    probe = Result(["ffprobe"], 0, b"1920,1080\n", b"")
    raw = Result(["ffmpeg"], 0, bytes(320 * 180 * 3), b"")
    runner = FakeRunner({"ffprobe": probe, "ffmpeg": raw})
    frames = decode_gray(Path("x.mp4"), runner)
    assert (frames.width, frames.height, len(frames.frames)) == (320, 180, 3)
    assert frames.fps == 10.0
    assert "fps=10.0,scale=320:-2,format=gray" in " ".join(runner.calls[-1])


# --- analyze_footage: synthetic 32x18 footage, panel at (4,6) 24x4, fps 10 ---


def _panel_frames():
    dark = gray(32, 18, 10)
    slate = bytearray(dark)
    rect(slate, 32, BBox(4, 6, 24, 4), 255)
    content = bytearray(dark)
    rect(content, 32, BBox(4, 6, 24, 4), 40)  # dim content: the panel must go dark
    return bytes(slate), bytes(content)


def _loop(content: bytes, slate: bytes) -> list[bytes]:
    # anchor 2.0 s, content A 2.0 s, inner slate 1.0 s, content B 3.0 s
    return [slate] * 20 + [content] * 20 + [slate] * 10 + [content] * 30


@pytest.fixture
def mid_loop_footage() -> GrayFrames:
    slate, content = _panel_frames()
    seq = (
        [content] * 15 + [slate] * 10 + [content] * 30
    )  # starts inside a previous loop's B
    seq += _loop(content, slate) + _loop(content, slate) + [slate] * 20
    return GrayFrames(32, 18, 10.0, seq)


def test_analyze_footage_no_bright_frame_is_no_slate_error():
    frames = GrayFrames(32, 18, 10.0, [bytes(gray(32, 18, 40))] * 30)
    with pytest.raises(NoSlateError, match="aimed"):
        analyze_footage(frames)


def test_analyze_footage_recording_starts_mid_loop_anchors_to_long_slate(
    mid_loop_footage,
):
    f = analyze_footage(mid_loop_footage)
    assert f.bbox == BBox(
        3, 6, 26, 4
    )  # 4% of w=24 → 1 px pad each side; h pad rounds to 0
    assert len(f.anchors) == 3
    assert f.segments == [Interval(75, 95), Interval(105, 135)]


def test_analyze_footage_take_2_selects_second_loop(mid_loop_footage):
    f = analyze_footage(mid_loop_footage, take=2)
    assert f.segments == [Interval(155, 175), Interval(185, 215)]


def test_analyze_footage_incomplete_loop_is_error():
    slate, content = _panel_frames()
    frames = GrayFrames(
        32, 18, 10.0, [slate] * 20 + [content] * 20 + [slate] * 10 + [content] * 30
    )
    with pytest.raises(IncompleteLoopError, match="record longer"):
        analyze_footage(frames)


def test_analyze_footage_explicit_crop_skips_detection(mid_loop_footage):
    f = analyze_footage(mid_loop_footage, crop=BBox(4, 6, 24, 4))
    assert f.bbox == BBox(4, 6, 24, 4)  # exact box, not the padded detected one


def test_find_panel_bbox_ignores_dim_glow_that_changes():
    # Slate light spilling onto the shelf swings by > threshold but never gets bright.
    dark = gray(320, 180, 0)
    lit = gray(320, 180, 0)
    rect(lit, 320, BBox(80, 70, 140, 30), 110)  # glow footprint, peaks at 110
    rect(lit, 320, BBox(100, 80, 100, 10), 255)  # the panel itself
    b = find_panel_bbox([bytes(dark), bytes(lit), bytes(dark)], 320, 180)
    assert (b.x, b.y, b.w, b.h) == (96, 80, 108, 10)


def test_analyze_footage_thresholds_are_tunable(mid_loop_footage):
    # The padded crop is ~93 % panel, so a 0.9 slate fraction still works and
    # an impossible 1.1 finds nothing.
    assert analyze_footage(mid_loop_footage, slate_fraction=0.9).segments
    with pytest.raises(NoSlateError):
        analyze_footage(mid_loop_footage, slate_fraction=1.1)


def test_analyze_footage_bright_but_unsaturated_flash_is_not_a_slate():
    """Hero footage: fireworks + cream text and the splitflap entry pushed the
    crop MEAN over 180 for ~2 s, but only the real slate saturates the panel."""
    slate, content = _panel_frames()
    flash = bytearray(gray(32, 18, 10))
    rect(flash, 32, BBox(4, 6, 24, 4), 220)
    seq = [slate] * 20 + [content] * 20 + [bytes(flash)] * 20 + [content] * 20
    seq = seq * 2 + [slate] * 20
    f = analyze_footage(GrayFrames(32, 18, 10.0, seq))
    assert [(s.start, s.end) for s in f.slates] == [(0, 20), (80, 100), (160, 180)]


def test_analyze_footage_take_must_be_positive(mid_loop_footage):
    with pytest.raises(ValueError, match="take"):
        analyze_footage(mid_loop_footage, take=0)


def test_footage_reports_peak_luma(mid_loop_footage):
    f = analyze_footage(mid_loop_footage)
    assert 230 < f.peak_luma <= 255  # slate mean over the padded crop


def test_find_panel_bbox_when_content_never_goes_dark():
    """YouTube loop: colored bg_color sections keep the panel lit the whole
    recording; the box must come from where the slate saturates, not from
    where pixels go black."""
    room = gray(320, 180, 60)
    slate = bytearray(room)
    rect(slate, 320, BBox(100, 80, 100, 10), 255)
    content = bytearray(room)
    rect(content, 320, BBox(100, 80, 100, 10), 150)
    frames = [bytes(slate)] * 3 + [bytes(content)] * 30
    b = find_panel_bbox(frames, 320, 180)
    assert (b.x, b.w, b.y, b.h) == (96, 108, 80, 10)


def test_find_panel_bbox_ignores_small_flickering_clutter():
    """Real footage (2026-11-17 probe): a flickering candle lamp top-right,
    a figurine left of the panel and a leaf garland below all change AND
    get bright, but each is a small blob; the panel is the one dense band."""
    dark = gray(320, 180, 0)
    rect(dark, 320, BBox(300, 40, 15, 30), 255)  # candle lamp: saturated always
    lit = bytearray(dark)
    rect(lit, 320, BBox(100, 80, 100, 10), 255)  # the panel
    rect(lit, 320, BBox(70, 78, 12, 14), 255)  # figurine, gap of 18 px to panel
    rect(lit, 320, BBox(120, 120, 40, 8), 255)  # garland below
    b = find_panel_bbox([bytes(dark), bytes(lit), bytes(dark), bytes(lit)], 320, 180)
    assert (b.x, b.w) == (96, 108)
    assert (b.y, b.h) == (80, 10)


def test_dense_run_tie_goes_to_first_and_gap_bridges():
    assert _dense_run([5, 5, 0, 5, 5]) == (0, 1)  # tie → first run
    assert _dense_run([5, 5, 0, 5, 5], gap=1) == (0, 4)  # one miss bridged
    assert _dense_run([5, 5, 0, 0, 5, 5, 5], gap=1) == (4, 6)  # two misses split
    assert _dense_run([0, 5, 5, 0]) == (1, 2)  # trailing miss excluded


def test_find_panel_bbox_warns_when_a_rival_run_is_close(capsys):
    dark = gray(320, 180, 0)
    lit = bytearray(dark)
    rect(lit, 320, BBox(20, 80, 100, 10), 255)  # panel
    rect(lit, 320, BBox(160, 80, 90, 10), 255)  # a rival nearly as wide
    warned: list[str] = []
    find_panel_bbox([bytes(dark), bytes(lit)], 320, 180, on_ambiguous=warned.append)
    assert warned and "CROP" in warned[0]


def test_find_panel_bbox_ignores_auto_exposure_drift_of_the_room():
    """13-minute real recording (2026-11-17): auto-exposure swung the whole
    room between ~90 and ~210, so every pixel changed by > 60 and got
    'bright' > 200 — the old mask covered the frame. The panel is the only
    thing that both SATURATES (slate) and goes nearly BLACK (content)."""
    dim = gray(320, 180, 90)
    bright_room = gray(320, 180, 210)
    slate = bytearray(dim)
    rect(slate, 320, BBox(100, 80, 100, 10), 255)
    content = bytearray(bright_room)
    rect(content, 320, BBox(100, 80, 100, 10), 10)
    b = find_panel_bbox(
        [bytes(dim), bytes(slate), bytes(content), bytes(bright_room)], 320, 180
    )
    assert (b.x, b.w) == (96, 108)
    assert (b.y, b.h) == (80, 10)

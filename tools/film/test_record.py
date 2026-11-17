from pathlib import Path

import pytest
from tools.film.record import (
    DEFAULT_DEVICE,
    DeviceNotFound,
    list_devices,
    record,
    record_argv,
)
from tools.film.runner import FakeRunner, Result

LIST = (
    b"[AVFoundation indev @ 0x1] AVFoundation video devices:\n"
    b"[AVFoundation indev @ 0x1] [0] Insta360 Link\n"
    b"[AVFoundation indev @ 0x1] [1] FaceTime HD Camera\n"
    b"[AVFoundation indev @ 0x1] AVFoundation audio devices:\n"
    b"[AVFoundation indev @ 0x1] [0] Mic\n"
)


def test_default_device_is_the_insta360():
    assert DEFAULT_DEVICE == "Insta360 Link"


def test_list_devices_parses_video_section_only():
    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST)})
    assert list_devices(runner) == ["Insta360 Link", "FaceTime HD Camera"]
    assert "-list_devices" in runner.calls[0]


def test_record_unknown_device_raises_with_list():
    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST)})
    with pytest.raises(DeviceNotFound, match="FaceTime HD Camera"):
        record("Insta 360", Path("o.mp4"), 5, runner)


def test_record_argv_uses_index_and_4k30():
    argv = record_argv(0, Path("o.mp4"), 12.5)
    assert argv[argv.index("-i") + 1] == "0:none"
    assert argv[argv.index("-video_size") + 1] == "3840x2160"
    assert argv[argv.index("-framerate") + 1] == "30"
    assert argv[argv.index("-t") + 1] == "12.5"
    assert "libx264" in argv and argv[-1] == "o.mp4"


def test_record_resolves_index_then_records():
    runner = FakeRunner(
        {
            "ffmpeg": lambda argv: Result(
                argv, 1 if "-list_devices" in argv else 0, b"", LIST
            )
        }
    )
    out = record("Insta360 Link", Path("o.mp4"), 3, runner)
    assert out == Path("o.mp4")
    rec = runner.calls[1]
    assert rec[rec.index("-i") + 1] == "0:none"


def test_record_failed_ffmpeg_raises():
    runner = FakeRunner(
        {
            "ffmpeg": lambda argv: Result(
                argv, 1, b"", LIST if "-list_devices" in argv else b"busy"
            )
        }
    )
    with pytest.raises(RuntimeError, match="busy"):
        record("Insta360 Link", Path("o.mp4"), 3, runner)

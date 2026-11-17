from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from tools.film.camera import (
    SMALLSIGN_SHELF,
    CameraPreset,
    aim,
    preset_commands,
    stream_argv,
    uvcc_argv,
)
from tools.film.record import DeviceNotFound
from tools.film.runner import FakeRunner, Result

LIST = (
    b"[AVFoundation indev @ 0x1] AVFoundation video devices:\n"
    b"[AVFoundation indev @ 0x1] [0] Insta360 Link\n"
    b"[AVFoundation indev @ 0x1] AVFoundation audio devices:\n"
)


def test_uvcc_argv_pins_the_link_by_vendor_and_product():
    argv = uvcc_argv("set", "absolute_zoom", "350")
    assert argv[:3] == ["npx", "-y", "uvcc@latest"]
    assert argv[argv.index("--vendor") + 1] == "11802"
    assert argv[argv.index("--product") + 1] == "19457"
    assert argv[-3:] == ["set", "absolute_zoom", "350"]


def test_preset_commands_order_and_manual_modes():
    cmds = preset_commands(CameraPreset(pan=-27720, tilt=36000, zoom=350))
    assert cmds == [
        ["set", "absolute_pan_tilt", "-27720", "36000"],
        ["set", "absolute_zoom", "350"],
        ["set", "auto_white_balance_temperature", "0"],
        ["set", "white_balance_temperature", "5000"],
    ]
    with_focus = preset_commands(
        CameraPreset(pan=0, tilt=0, zoom=100, white_balance=None, focus=40)
    )
    assert with_focus == [
        ["set", "absolute_pan_tilt", "0", "0"],
        ["set", "absolute_zoom", "100"],
        ["set", "auto_focus", "0"],
        ["set", "absolute_focus", "40"],
    ]


def test_smallsign_shelf_preset_is_the_measured_framing():
    assert (SMALLSIGN_SHELF.pan, SMALLSIGN_SHELF.tilt, SMALLSIGN_SHELF.zoom) == (
        -27720,
        36000,
        350,
    )
    assert SMALLSIGN_SHELF.white_balance == 5000


def test_stream_argv_is_a_null_sink_at_the_recording_mode():
    argv = stream_argv(0, seconds=12.0)
    assert argv[argv.index("-i") + 1] == "0:none"
    assert argv[argv.index("-video_size") + 1] == "3840x2160"
    assert argv[-2:] == ["null", "-"] and "-f" in argv


def _export(pan: int, tilt: int, zoom: int) -> bytes:
    return (
        b'{"absolute_pan_tilt": [%d, %d], "absolute_zoom": %d, '
        b'"white_balance_temperature": 5000, "auto_focus": 1}' % (pan, tilt, zoom)
    )


def _fake_hold(log: list[str]):
    @contextmanager
    def hold(argv: list[str]) -> Iterator[None]:
        log.append("open:" + argv[0])
        yield
        log.append("close")

    return hold


def test_aim_sets_controls_only_while_the_stream_is_open():
    log: list[str] = []
    slept: list[float] = []

    def fake_npx(argv: list[str]) -> Result:
        log.append(" ".join(argv[argv.index("--product") + 2 :]))
        if argv[-1] == "export":
            return Result(argv, 0, _export(-27720, 36000, 350), b"")
        return Result(argv, 0, b"", b"")

    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST), "npx": fake_npx})
    state = aim(SMALLSIGN_SHELF, runner, hold=_fake_hold(log), sleep=slept.append)
    assert log[0] == "open:ffmpeg"
    assert log[-1] == "close"
    assert "set absolute_zoom 350" in log and "export" in log
    assert log.index("set absolute_pan_tilt -27720 36000") < log.index("export")
    assert state["absolute_zoom"] == 350
    assert slept and slept[0] >= 2.0  # let the Link wake before the first set


def test_aim_raises_when_the_camera_did_not_take_the_framing():
    def fake_npx(argv: list[str]) -> Result:
        if argv[-1] == "export":
            return Result(argv, 0, _export(0, 0, 100), b"")  # asleep: ignored
        return Result(argv, 0, b"", b"")

    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST), "npx": fake_npx})
    with pytest.raises(RuntimeError, match="zoom"):
        aim(SMALLSIGN_SHELF, runner, hold=_fake_hold([]), sleep=lambda s: None)


def test_aim_unknown_device_raises_before_touching_uvcc():
    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST)})
    with pytest.raises(DeviceNotFound):
        aim(
            SMALLSIGN_SHELF,
            runner,
            device="Nope",
            hold=_fake_hold([]),
            sleep=lambda s: None,
        )
    assert all(c[0] == "ffmpeg" for c in runner.calls)

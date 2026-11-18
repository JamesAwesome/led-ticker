from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from tools.film.camera import (
    SMALLSIGN_SHELF,
    CameraPreset,
    StreamHandle,
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
    assert argv[:2] == ["npx", "-y"]
    assert argv[2].startswith("uvcc@") and argv[2] != "uvcc@latest"  # pinned
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
        ["set", "auto_focus", "1"],
    ]
    with_focus = preset_commands(
        CameraPreset(pan=0, tilt=0, zoom=100, white_balance=None, focus=40)
    )
    assert with_focus == [
        ["set", "absolute_pan_tilt", "0", "0"],
        ["set", "absolute_zoom", "100"],
        ["set", "auto_white_balance_temperature", "1"],
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
    assert "-nostdin" in argv
    assert argv[argv.index("-i") + 1] == "0:none"
    assert argv[argv.index("-video_size") + 1] == "3840x2160"
    assert argv[-2:] == ["null", "-"] and "-f" in argv


def _export(
    pan: int, tilt: int, zoom: int, *, auto_wb: int = 0, wb: int = 5000
) -> bytes:
    return (
        b'{"absolute_pan_tilt": [%d, %d], "absolute_zoom": %d, '
        b'"auto_white_balance_temperature": %d, "white_balance_temperature": %d, '
        b'"auto_focus": 1, "absolute_focus": 0}' % (pan, tilt, zoom, auto_wb, wb)
    )


class _Handle:
    def __init__(self, alive_for: int = 10**6) -> None:
        self.polls = 0
        self.alive_for = alive_for

    def alive(self) -> bool:
        self.polls += 1
        return self.polls <= self.alive_for

    def diagnostics(self) -> str:
        return "ffmpeg: device busy"


def _fake_hold(log: list[str], handle: _Handle | None = None):
    @contextmanager
    def hold(argv: list[str]) -> Iterator[StreamHandle]:
        log.append("open:" + argv[0])
        yield handle or _Handle()
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


def test_aim_raises_when_the_hold_stream_died():
    runner = FakeRunner(
        {
            "ffmpeg": Result(["ffmpeg"], 1, b"", LIST),
            "npx": lambda argv: Result(argv, 0, _export(-27720, 36000, 350), b""),
        }
    )
    with pytest.raises(RuntimeError, match="stream ended.*device busy"):
        aim(
            SMALLSIGN_SHELF,
            runner,
            hold=_fake_hold([], _Handle(alive_for=0)),
            sleep=lambda s: None,
        )
    assert not any(c[0] == "npx" for c in runner.calls)  # dead before any set


def test_aim_verifies_white_balance_lock():
    def fake_npx(argv: list[str]) -> Result:
        if argv[-1] == "export":
            return Result(argv, 0, _export(-27720, 36000, 350, auto_wb=1), b"")
        return Result(argv, 0, b"", b"")

    runner = FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST), "npx": fake_npx})
    with pytest.raises(RuntimeError, match="white balance"):
        aim(SMALLSIGN_SHELF, runner, hold=_fake_hold([]), sleep=lambda s: None)


def test_stream_is_held_for_minutes_not_seconds():
    argv = stream_argv(0, seconds=600)
    assert float(argv[argv.index("-t") + 1]) >= 600


def test_popen_hold_reports_liveness_and_terminates_on_exit():
    from tools.film.camera import popen_hold

    with popen_hold(["/bin/sleep", "30"]) as h:
        assert h.alive()
        held = h
    assert not held.alive()  # terminated by the context exit, no zombie

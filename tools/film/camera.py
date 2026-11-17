"""Aim the Insta360 Link over UVC (``uvcc`` via npx).

The Link only applies pan/tilt/zoom while a video stream is open — set
while idle, the values read back but the gimbal never moves and zoom is
rejected — so ``aim`` holds a throwaway ffmpeg stream to the null muxer
while it sends the controls, then reads them back to prove they took.
Exposure is not exposed over UVC on this camera; lock it in the Insta360
Link Controller app if auto-exposure pumping becomes a problem.
"""

import json
import subprocess
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from time import sleep as _sleep
from typing import Protocol

from tools.film.record import (
    DEFAULT_DEVICE,
    DEFAULT_FPS,
    DEFAULT_SIZE,
    DeviceNotFound,
    list_devices,
)
from tools.film.runner import Runner, ToolMissing

VENDOR = 11802  # 0x2e1a Insta360 — must be the same camera as record.DEFAULT_DEVICE
PRODUCT = 19457  # 0x4c01 Link
UVCC = "uvcc@8.0.0"  # the version session 0 ran; its control list/export shape
UVCC_TIMEOUT = 60.0
SETTLE_SECONDS = 3.0  # stream-open → camera awake; set → gimbal in place
HOLD_SECONDS = 600.0  # ffmpeg -t for the held stream; teardown terminates it anyway


@dataclass(frozen=True)
class CameraPreset:
    pan: int  # arc-seconds; +right
    tilt: int  # arc-seconds; +up
    zoom: int  # 100 = 1x … 400 = 4x (digital)
    white_balance: int | None = 5000  # kelvin, locked; None = explicit auto
    focus: int | None = None  # 0–100, locked; None = explicit auto


# Measured 2026-11-17: camera on the desk, sign on the top shelf. Panel fills
# ~77% of the frame width (≈18 camera px per LED at 4K).
SMALLSIGN_SHELF = CameraPreset(pan=-27720, tilt=36000, zoom=350)


def uvcc_argv(*args: str) -> list[str]:
    return [
        "npx",
        "-y",
        UVCC,
        "--vendor",
        str(VENDOR),
        "--product",
        str(PRODUCT),
        *args,
    ]


def preset_commands(preset: CameraPreset) -> list[list[str]]:
    cmds = [
        ["set", "absolute_pan_tilt", str(preset.pan), str(preset.tilt)],
        ["set", "absolute_zoom", str(preset.zoom)],
    ]
    if preset.white_balance is None:
        cmds.append(["set", "auto_white_balance_temperature", "1"])
    else:
        cmds.append(["set", "auto_white_balance_temperature", "0"])
        cmds.append(["set", "white_balance_temperature", str(preset.white_balance)])
    if preset.focus is None:
        cmds.append(["set", "auto_focus", "1"])
    else:
        cmds.append(["set", "auto_focus", "0"])
        cmds.append(["set", "absolute_focus", str(preset.focus)])
    return cmds


def stream_argv(
    device_index: int,
    *,
    seconds: float,
    size: str = DEFAULT_SIZE,
    fps: int = DEFAULT_FPS,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-f",
        "avfoundation",
        "-framerate",
        str(fps),
        "-video_size",
        size,
        "-pixel_format",
        "nv12",
        "-i",
        f"{device_index}:none",
        "-t",
        str(seconds),
        "-f",
        "null",
        "-",
    ]


class StreamHandle(Protocol):
    def alive(self) -> bool: ...

    def diagnostics(self) -> str: ...


Hold = Callable[[list[str]], AbstractContextManager[StreamHandle]]


class _PopenHandle:
    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self._proc = proc

    def alive(self) -> bool:
        return self._proc.poll() is None

    def diagnostics(self) -> str:
        if self._proc.stderr is None:
            return ""
        return self._proc.stderr.read().decode(errors="replace").strip()


@contextmanager
def popen_hold(argv: list[str]) -> Iterator[StreamHandle]:
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv is built by this package
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ToolMissing(argv[0]) from exc
    try:
        yield _PopenHandle(proc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _uvcc(runner: Runner, *args: str) -> bytes:
    res = runner.run(uvcc_argv(*args), timeout=UVCC_TIMEOUT)
    if res.returncode != 0:
        raise RuntimeError(
            f"uvcc {' '.join(args)} failed: {res.stderr.decode(errors='replace')}"
        )
    return res.stdout


def export(runner: Runner) -> dict[str, object]:
    return json.loads(_uvcc(runner, "export"))


def aim(
    preset: CameraPreset,
    runner: Runner,
    *,
    device: str = DEFAULT_DEVICE,
    size: str = DEFAULT_SIZE,
    fps: int = DEFAULT_FPS,
    settle: float = SETTLE_SECONDS,
    hold: Hold = popen_hold,
    sleep: Callable[[float], None] = _sleep,
) -> dict[str, object]:
    devices = list_devices(runner)
    if device not in devices:
        listing = ", ".join(repr(d) for d in devices) or "(none)"
        raise DeviceNotFound(f"video device {device!r} not found; available: {listing}")
    idx = devices.index(device)
    with hold(stream_argv(idx, seconds=HOLD_SECONDS, size=size, fps=fps)) as stream:
        sleep(settle)
        _require_alive(stream)  # set while idle reads back fine but does nothing
        for cmd in preset_commands(preset):
            _uvcc(runner, *cmd)
        sleep(settle)
        _require_alive(stream)
        state = export(runner)
    _verify(preset, state)
    return state


def _require_alive(stream: StreamHandle) -> None:
    if not stream.alive():
        raise RuntimeError(
            "camera stream ended early, controls would not apply: "
            f"{stream.diagnostics() or 'no ffmpeg output'}"
        )


def _verify(preset: CameraPreset, state: dict[str, object]) -> None:
    got = (state.get("absolute_pan_tilt"), state.get("absolute_zoom"))
    want = ([preset.pan, preset.tilt], preset.zoom)
    if got != want:
        raise RuntimeError(
            f"camera did not take the framing (pan/tilt, zoom): got {got}, "
            f"wanted {want}; is another app holding the Insta360 Link?"
        )
    auto_wb = state.get("auto_white_balance_temperature")
    if preset.white_balance is None:
        if auto_wb != 1:
            raise RuntimeError("camera did not return white balance to auto")
    elif auto_wb != 0 or state.get("white_balance_temperature") != preset.white_balance:
        raise RuntimeError(
            f"camera did not lock white balance at {preset.white_balance} K "
            f"(auto={auto_wb}, value={state.get('white_balance_temperature')})"
        )
    auto_focus = state.get("auto_focus")
    if preset.focus is None:
        if auto_focus != 1:
            raise RuntimeError("camera did not return focus to auto")
    elif auto_focus != 0 or state.get("absolute_focus") != preset.focus:
        raise RuntimeError(
            f"camera did not lock focus at {preset.focus} "
            f"(auto={auto_focus}, value={state.get('absolute_focus')})"
        )

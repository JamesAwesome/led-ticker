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

from tools.film.record import (
    DEFAULT_DEVICE,
    DEFAULT_FPS,
    DEFAULT_SIZE,
    DeviceNotFound,
    list_devices,
)
from tools.film.runner import Runner, ToolMissing

VENDOR = 11802  # 0x2e1a Insta360
PRODUCT = 19457  # 0x4c01 Link
UVCC_TIMEOUT = 60.0
SETTLE_SECONDS = 3.0  # stream-open → camera awake; set → gimbal in place


@dataclass(frozen=True)
class CameraPreset:
    pan: int  # arc-seconds; +right
    tilt: int  # arc-seconds; +up
    zoom: int  # 100 = 1x … 400 = 4x (digital)
    white_balance: int | None = 5000  # kelvin; None keeps auto
    focus: int | None = None  # 0–100; None keeps auto


# Measured 2026-11-17: camera on the desk, sign on the top shelf. Panel fills
# ~77% of the frame width (≈18 camera px per LED at 4K).
SMALLSIGN_SHELF = CameraPreset(pan=-27720, tilt=36000, zoom=350)


def uvcc_argv(*args: str) -> list[str]:
    return [
        "npx",
        "-y",
        "uvcc@latest",
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
    if preset.white_balance is not None:
        cmds.append(["set", "auto_white_balance_temperature", "0"])
        cmds.append(["set", "white_balance_temperature", str(preset.white_balance)])
    if preset.focus is not None:
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


Hold = Callable[[list[str]], AbstractContextManager[None]]


@contextmanager
def popen_hold(argv: list[str]) -> Iterator[None]:
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv is built by this package
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except FileNotFoundError as exc:
        raise ToolMissing(argv[0]) from exc
    try:
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


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
    with hold(stream_argv(idx, seconds=settle * 3 + 30, size=size, fps=fps)):
        sleep(settle)
        for cmd in preset_commands(preset):
            _uvcc(runner, *cmd)
        sleep(settle)
        state = export(runner)
    got = (state.get("absolute_pan_tilt"), state.get("absolute_zoom"))
    want = ([preset.pan, preset.tilt], preset.zoom)
    if got != want:
        raise RuntimeError(
            f"camera did not take the framing (pan/tilt, zoom): got {got}, "
            f"wanted {want}; is another app holding the Insta360 Link?"
        )
    return state

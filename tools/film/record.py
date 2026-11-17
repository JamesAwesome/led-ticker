"""Record the webcam with ffmpeg's avfoundation input. Camera settings
(zoom, exposure, white balance, focus) are NOT touched here; they are set
once per session in the Insta360 Link Controller app (see the runbook)."""

import re
from pathlib import Path

from tools.film.runner import Runner

DEFAULT_DEVICE = "Insta360 Link"
DEFAULT_SIZE = "3840x2160"  # the Link's top UVC mode; 30 fps is its ceiling
DEFAULT_FPS = 30

_DEVICE_LINE = re.compile(r"\[(\d+)\] (.+?)\s*$")


class DeviceNotFound(RuntimeError):
    pass


def _list_argv() -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-f",
        "avfoundation",
        "-list_devices",
        "true",
        "-i",
        "",
    ]


def list_devices(runner: Runner) -> list[str]:
    """Video device names, in index order (ffmpeg prints them to stderr and exits 1)."""
    res = runner.run(_list_argv())
    names: list[str] = []
    in_video = False
    for line in res.stderr.decode(errors="replace").splitlines():
        if "video devices:" in line:
            in_video = True
            continue
        if "audio devices:" in line:
            break
        m = _DEVICE_LINE.search(line)
        if in_video and m:
            names.append(m.group(2))
    return names


def record_argv(
    device_index: int,
    out: Path,
    seconds: float,
    *,
    size: str = DEFAULT_SIZE,
    fps: int = DEFAULT_FPS,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-f",
        "avfoundation",
        "-framerate",
        str(fps),
        "-video_size",
        size,
        "-i",
        f"{device_index}:none",
        "-t",
        str(seconds),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]


def record(
    device: str,
    out: Path,
    seconds: float,
    runner: Runner,
    *,
    size: str = DEFAULT_SIZE,
    fps: int = DEFAULT_FPS,
) -> Path:
    devices = list_devices(runner)
    if device not in devices:
        listing = ", ".join(repr(d) for d in devices) or "(none)"
        raise DeviceNotFound(f"video device {device!r} not found; available: {listing}")
    out.parent.mkdir(parents=True, exist_ok=True)
    res = runner.run(
        record_argv(devices.index(device), out, seconds, size=size, fps=fps)
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"ffmpeg recording failed: {res.stderr.decode(errors='replace')}"
        )
    return out

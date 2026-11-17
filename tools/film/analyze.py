"""Footage analysis for the clip tool: decode to low-res grayscale, find the
panel (the only thing in frame that changes), find white slates, and anchor
segments to one complete loop so clips never zip one slot late."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.film.runner import Runner

ANCHOR_SECONDS = 1.5  # slates at least this long are loop anchors (2.0 s top slate)
_NO_SLATE_MSG = "no slate found; is the camera aimed at the sign?"


@dataclass(frozen=True)
class GrayFrames:
    width: int
    height: int
    fps: float
    frames: list[bytes]  # each len == width*height, 8-bit gray


@dataclass(frozen=True)
class BBox:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Interval:
    start: int  # frame index, inclusive
    end: int  # frame index, exclusive


@dataclass(frozen=True)
class Footage:
    frames: GrayFrames
    bbox: BBox
    slates: list[Interval]
    anchors: list[Interval]
    segments: list[Interval]


class NoSlateError(RuntimeError):
    pass


class IncompleteLoopError(RuntimeError):
    pass


def decode_gray(
    path: Path, runner: Runner, *, fps: float = 10.0, width: int = 320
) -> GrayFrames:
    probe = runner.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ]
    )
    if probe.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed on {path}: {probe.stderr.decode(errors='replace')}"
        )
    src_w, src_h = (int(v) for v in probe.stdout.decode().strip().split(",")[:2])
    out = runner.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"fps={fps},scale={width}:-2,format=gray",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    if out.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed on {path}: {out.stderr.decode(errors='replace')}"
        )
    if not out.stdout:
        raise RuntimeError(f"ffmpeg produced no frames from {path}")
    height = _even_height(src_w, src_h, width, len(out.stdout))
    size = width * height
    frames = [bytes(out.stdout[i : i + size]) for i in range(0, len(out.stdout), size)]
    return GrayFrames(width, height, fps, frames)


def _even_height(src_w: int, src_h: int, width: int, nbytes: int) -> int:
    guess = round(src_h * width / src_w)
    guess += guess % 2
    for h in (guess, guess - 2, guess + 2):
        if h > 0 and nbytes % (width * h) == 0:
            return h
    raise RuntimeError(
        f"cannot infer frame height from {nbytes} bytes at width {width}"
    )


def mean_luma(frame: bytes, bbox: BBox | None, width: int) -> float:
    if bbox is None:
        return sum(frame) / len(frame)
    total = 0
    for y in range(bbox.y, bbox.y + bbox.h):
        row = y * width + bbox.x
        total += sum(frame[row : row + bbox.w])
    return total / (bbox.w * bbox.h)


def find_slates(
    luma: Sequence[float],
    fps: float,
    *,
    threshold: float = 180.0,
    min_seconds: float = 0.5,
) -> list[Interval]:
    min_len = max(1, round(min_seconds * fps))
    slates: list[Interval] = []
    start: int | None = None
    for i, v in enumerate([*luma, -1.0]):  # sentinel closes a trailing run
        if v > threshold and start is None:
            start = i
        elif v <= threshold and start is not None:
            if i - start >= min_len:
                slates.append(Interval(start, i))
            start = None
    if not slates:
        raise NoSlateError(_NO_SLATE_MSG)
    return slates


def find_panel_bbox(
    frames: list[bytes],
    width: int,
    height: int,
    *,
    threshold: int = 60,
    pad_frac: float = 0.04,
) -> BBox:
    hi = bytearray(frames[0])
    lo = bytearray(frames[0])
    for f in frames[1:]:
        hi = bytearray(max(a, b) for a, b in zip(hi, f, strict=True))
        lo = bytearray(min(a, b) for a, b in zip(lo, f, strict=True))
    x0, y0, x1, y1 = width, height, -1, -1
    for i, (a, b) in enumerate(zip(hi, lo, strict=True)):
        if a - b > threshold:
            y, x = divmod(i, width)
            x0, x1 = min(x0, x), max(x1, x)
            y0, y1 = min(y0, y), max(y1, y)
    if x1 < 0:
        raise NoSlateError(_NO_SLATE_MSG)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    px, py = round(w * pad_frac), round(h * pad_frac)
    x0, y0 = max(0, x0 - px), max(0, y0 - py)
    x1, y1 = min(width - 1, x1 + px), min(height - 1, y1 + py)
    return BBox(x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def segments_between(slates: list[Interval], total_frames: int) -> list[Interval]:
    return [Interval(a.end, b.start) for a, b in zip(slates, slates[1:], strict=False)]


def analyze_footage(
    frames: GrayFrames, *, crop: BBox | None = None, take: int = 1
) -> Footage:
    bbox = crop or find_panel_bbox(frames.frames, frames.width, frames.height)
    luma = [mean_luma(f, bbox, frames.width) for f in frames.frames]
    slates = find_slates(luma, frames.fps)
    min_anchor = round(ANCHOR_SECONDS * frames.fps)
    anchors = [s for s in slates if s.end - s.start >= min_anchor]
    if len(anchors) < take + 1:
        raise IncompleteLoopError(
            f"recording holds {max(0, len(anchors) - 1)} complete loop(s); "
            f"take={take} needs {take + 1} anchors — record longer"
        )
    first, last = anchors[take - 1], anchors[take]
    inner = [s for s in slates if first.end <= s.start and s.end <= last.start]
    segments = segments_between([first, *inner, last], len(frames.frames))
    return Footage(frames, bbox, slates, anchors, segments)

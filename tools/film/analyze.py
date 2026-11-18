"""Footage analysis for the clip tool: decode to low-res grayscale, find the
panel (the one region the white slate saturates), time the slates by how
much of that box saturates, and anchor segments to one complete loop so
clips never zip one slot late."""

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.film.runner import Runner

ANCHOR_SECONDS = 1.5  # slates at least this long are loop anchors (2.0 s top slate)
SATURATED = 245  # 8-bit luma a white-slate LED pixel reaches on camera
SLATE_FRACTION = 0.6  # of the panel box saturated → this frame is a slate
_SAMPLE = 200  # frames sampled for per-pixel statistics (pure-Python budget)
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
    peak_luma: float  # brightest crop-mean seen; a slate should sit near 255


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
        ],
        timeout=60.0,
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
        ],
        timeout=1800.0,
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


def _sat_table(bright: int) -> bytes:
    return bytes(1 if v > bright else 0 for v in range(256))


def saturated_fraction(
    frame: bytes, bbox: BBox, width: int, *, bright: int = SATURATED
) -> float:
    """Share of the box's pixels above `bright` — ~1.0 on a white slate, well
    below 0.5 for any content (even cream text over fireworks), unlike the
    crop MEAN, which bright-but-not-white content pushes past a luma cut."""
    table = _sat_table(bright)
    n = 0
    for y in range(bbox.y, bbox.y + bbox.h):
        row = y * width + bbox.x
        n += frame[row : row + bbox.w].translate(table).count(b"\x01")
    return n / (bbox.w * bbox.h)


def find_slates(
    values: Sequence[float],
    fps: float,
    *,
    threshold: float = SLATE_FRACTION,
    min_seconds: float = 0.5,
) -> list[Interval]:
    """Runs of frames whose value exceeds `threshold` for at least
    `min_seconds`; `values` is the per-frame saturated fraction of the box."""
    luma = values
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


def _dense_runs(
    counts: list[int], *, frac: float = 0.5, gap: int = 0
) -> list[tuple[int, int]]:
    """Runs of indices whose count is >= frac*max(counts), tolerating up to
    `gap` consecutive sub-threshold indices inside a run; each (first, last)
    inclusive, longest first (ties keep input order). All-zero input yields
    one run spanning everything (0 >= 0); find_panel_bbox guards that."""
    cut = max(counts) * frac
    runs: list[tuple[int, int]] = []
    start = None
    miss = 0
    last_hit = -1
    for i, c in enumerate(counts):
        if c >= cut:
            if start is None:
                start = i
            last_hit = i
            miss = 0
        elif start is not None:
            miss += 1
            if miss > gap:
                runs.append((start, last_hit))
                start = None
                miss = 0
    if start is not None:
        runs.append((start, last_hit))
    return sorted(runs, key=lambda r: r[0] - r[1])  # stable: longest first


def _dense_run(
    counts: list[int], *, frac: float = 0.5, gap: int = 0
) -> tuple[int, int]:
    return _dense_runs(counts, frac=frac, gap=gap)[0]


def _warn_stderr(msg: str) -> None:
    print(f"film: warning: {msg}", file=sys.stderr)


AMBIGUITY_RATIO = 0.7  # rival run at least this long vs the winner → warn


def find_panel_bbox(
    frames: list[bytes],
    width: int,
    height: int,
    *,
    bright: int = SATURATED,
    slate_frac: float = SLATE_FRACTION,
    pad_frac: float = 0.04,
    on_ambiguous: Callable[[str], None] = _warn_stderr,
) -> BBox:
    """Box of the panel, found from the slate: the frames with the most
    saturated pixels are the white slates, and the panel is what saturates in
    them but not in ordinary frames. Pixels saturated in every sampled frame
    (a window, a lamp) are static and dropped first; nothing else in the room
    saturates only when the slate is up. This survives auto-exposure drift
    (a long clip swings the whole room by 60+ luma) and content that never
    goes dark (bg_color sections), both of which broke change-based masks on
    real footage. Residual clutter the slate glow lights up is dropped by
    projection: the panel is the densest contiguous band of qualifying rows,
    then the densest contiguous run of columns within that band, then rows
    again within those columns."""
    table = _sat_table(bright)
    n = width * height
    step = max(1, len(frames) // _SAMPLE)
    sampled = frames[::step]
    static = int.from_bytes(sampled[0].translate(table), "big")
    for f in sampled[1:]:
        static &= int.from_bytes(f.translate(table), "big")
    live = ~static & ((1 << (8 * n)) - 1)
    counts = [
        (int.from_bytes(f.translate(table), "big") & live).bit_count() for f in frames
    ]
    peak = max(counts)
    if peak == 0:
        raise NoSlateError(_NO_SLATE_MSG)
    cut = slate_frac * peak
    cand = [i for i, c in enumerate(counts) if c >= cut]
    rest = [i for i, c in enumerate(counts) if c < cut]
    cand = cand[:: max(1, len(cand) // _SAMPLE)]
    rest = rest[:: max(1, len(rest) // _SAMPLE)]

    def freq(idx: list[int]) -> list[int]:
        acc = [0] * n
        for i in idx:
            m = frames[i].translate(table)
            for p in range(n):
                if m[p]:
                    acc[p] += 1
        return acc

    in_slate = freq(cand)
    in_rest = freq(rest)
    live_bytes = live.to_bytes(n, "big")
    mask = bytes(
        1
        if live_bytes[p]
        and in_slate[p] * 2 >= len(cand)
        and in_rest[p] * 2 < max(1, len(rest))
        else 0
        for p in range(n)
    )
    if not any(mask):
        raise NoSlateError(_NO_SLATE_MSG)
    gap_x = max(1, round(width * 0.01))
    gap_y = max(1, round(height * 0.01))

    def rows(x0: int, x1: int) -> list[int]:
        return [sum(mask[y * width + x0 : y * width + x1 + 1]) for y in range(height)]

    def cols(y0: int, y1: int) -> list[int]:
        return [
            sum(mask[y * width + x] for y in range(y0, y1 + 1)) for x in range(width)
        ]

    y0, y1 = _dense_run(rows(0, width - 1), gap=gap_y)
    col_runs = _dense_runs(cols(y0, y1), gap=gap_x)
    x0, x1 = col_runs[0]
    if len(col_runs) > 1:
        rx0, rx1 = col_runs[1]
        if (rx1 - rx0 + 1) >= AMBIGUITY_RATIO * (x1 - x0 + 1):
            on_ambiguous(
                f"panel pick is ambiguous: columns {x0}-{x1} chosen over "
                f"{rx0}-{rx1} (analysis px); check the contact sheet or pass CROP="
            )
    y0, y1 = _dense_run(rows(x0, x1), gap=gap_y)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    px, py = round(w * pad_frac), round(h * pad_frac)
    x0, y0 = max(0, x0 - px), max(0, y0 - py)
    x1, y1 = min(width - 1, x1 + px), min(height - 1, y1 + py)
    return BBox(x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def segments_between(slates: list[Interval], total_frames: int) -> list[Interval]:
    return [Interval(a.end, b.start) for a, b in zip(slates, slates[1:], strict=False)]


def analyze_footage(
    frames: GrayFrames,
    *,
    crop: BBox | None = None,
    take: int = 1,
    bright_threshold: int = SATURATED,
    slate_fraction: float = SLATE_FRACTION,
) -> Footage:
    if take < 1:
        raise ValueError(f"take must be >= 1, got {take}")
    bbox = crop or find_panel_bbox(
        frames.frames,
        frames.width,
        frames.height,
        bright=bright_threshold,
        slate_frac=slate_fraction,
    )
    frac = [
        saturated_fraction(f, bbox, frames.width, bright=bright_threshold)
        for f in frames.frames
    ]
    slates = find_slates(frac, frames.fps, threshold=slate_fraction)
    luma = [mean_luma(f, bbox, frames.width) for f in frames.frames]
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
    return Footage(frames, bbox, slates, anchors, segments, max(luma))

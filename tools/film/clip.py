"""Cut analyzed footage into named GIFs (two-pass palette, size-budgeted) and
mp4s, plus a contact sheet per clip for review without opening every GIF."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tools.film.analyze import (
    BBox,
    Footage,
    GrayFrames,
    Interval,
    analyze_footage,
    decode_gray,
)
from tools.film.manifest import film_names
from tools.film.runner import Runner

HERO_MAX_BYTES = 4_000_000
LADDER: tuple[tuple[int, int], ...] = ((800, 20), (640, 20), (640, 15))  # (width, fps)


@dataclass(frozen=True)
class ClipSettings:
    width: int = 800
    fps: int = 20
    max_bytes: int = 2_500_000
    trim_frames: int = (
        1  # analysis frames dropped at each end so slate fade never shows
    )


class CountMismatch(RuntimeError):
    pass


def plan_clips(footage: Footage, names: list[str]) -> list[tuple[str, Interval]]:
    if len(footage.segments) != len(names):
        secs = [
            f"{s.start / footage.frames.fps:.1f}-{s.end / footage.frames.fps:.1f}s"
            for s in footage.segments
        ]
        quoted = ", ".join(repr(n) for n in names)
        raise CountMismatch(
            f"{len(footage.segments)} segment(s) detected ({', '.join(secs)}) "
            f"but {len(names)} name(s) in manifest ({quoted})"
        )
    return list(zip(names, footage.segments, strict=True))


def _crop_filter(bbox: BBox, analysis_width: int, src_width: int) -> str:
    k = src_width / analysis_width
    w, h, x, y = (round(v * k) for v in (bbox.w, bbox.h, bbox.x, bbox.y))
    w -= w % 2
    h -= h % 2
    return f"crop={w}:{h}:{x}:{y}"


def _window(seg: Interval, fps_src: float, trim: int) -> tuple[str, str]:
    start = (seg.start + trim) / fps_src
    dur = max(seg.end - seg.start - 2 * trim, 1) / fps_src
    return f"{start:.3f}", f"{dur:.3f}"


def gif_argv(
    src: Path,
    out: Path,
    seg: Interval,
    fps_src: float,
    bbox: BBox,
    analysis_width: int,
    src_width: int,
    settings: ClipSettings,
) -> list[str]:
    ss, t = _window(seg, fps_src, settings.trim_frames)
    chain = (
        f"{_crop_filter(bbox, analysis_width, src_width)},fps={settings.fps},"
        f"scale={settings.width}:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=3"
    )
    return [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-ss",
        ss,
        "-t",
        t,
        "-i",
        str(src),
        "-filter_complex",
        chain,
        str(out),
    ]


def mp4_argv(
    src: Path,
    out: Path,
    seg: Interval,
    fps_src: float,
    bbox: BBox | None,
    analysis_width: int,
    src_width: int,
) -> list[str]:
    ss, t = _window(seg, fps_src, 1)
    argv = ["ffmpeg", "-v", "error", "-y", "-ss", ss, "-t", t, "-i", str(src)]
    if bbox is not None:
        argv += ["-vf", _crop_filter(bbox, analysis_width, src_width)]
    argv += [
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(out),
    ]
    return argv


def emit_gif_within_budget(
    src: Path,
    out: Path,
    seg: Interval,
    fps_src: float,
    bbox: BBox,
    analysis_width: int,
    src_width: int,
    *,
    runner: Runner,
    size_of: Callable[[Path], int],
    settings: ClipSettings,
) -> tuple[int, int, int]:
    """Try each LADDER rung until the GIF fits settings.max_bytes.

    Returns (width, fps, bytes) of the GIF left on disk; if no rung fits, the
    last (smallest) rung is kept and the caller reports it as over budget.
    """
    result = (settings.width, settings.fps, 0)
    for width, fps in LADDER:
        rung = ClipSettings(width, fps, settings.max_bytes, settings.trim_frames)
        res = runner.run(
            gif_argv(src, out, seg, fps_src, bbox, analysis_width, src_width, rung)
        )
        if res.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed writing {out}: {res.stderr.decode(errors='replace')}"
            )
        size = size_of(out)
        result = (width, fps, size)
        if size <= settings.max_bytes:
            break
    return result


def contact_sheet(frames: GrayFrames, seg: Interval, bbox: BBox, out: Path) -> None:
    from PIL import Image  # Pillow is a core dep; imported lazily to keep the CLI light

    picks = [seg.start, (seg.start + seg.end) // 2, max(seg.start, seg.end - 1)]
    tiles = []
    for i in picks:
        img = Image.frombytes("L", (frames.width, frames.height), frames.frames[i])
        img = img.crop((bbox.x, bbox.y, bbox.x + bbox.w, bbox.y + bbox.h))
        tiles.append(img.resize((bbox.w * 4, bbox.h * 4), Image.Resampling.NEAREST))
    sheet = Image.new("L", (bbox.w * 4, bbox.h * 4 * 3 + 8), 60)
    for n, tile in enumerate(tiles):
        sheet.paste(tile, (0, n * (bbox.h * 4 + 4)))
    sheet.save(out)


def _probe_width(src: Path, runner: Runner) -> int:
    res = runner.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width",
            "-of",
            "csv=p=0",
            str(src),
        ]
    )
    return int(res.stdout.decode().strip().split(",")[0])


def clip_footage(
    src: Path,
    manifest: Path,
    out_dir: Path,
    *,
    runner: Runner,
    crop: BBox | None,
    take: int,
    mp4_names: set[str],
    hero_budget_names: set[str],
    settings: ClipSettings,
    size_of: Callable[[Path], int] = lambda p: p.stat().st_size,
) -> list[Path]:
    frames = decode_gray(src, runner)
    footage = analyze_footage(frames, crop=crop, take=take)
    names = film_names(manifest.read_text())
    plan = plan_clips(footage, names)
    src_width = _probe_width(src, runner)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, seg in plan:
        budget = HERO_MAX_BYTES if name in hero_budget_names else settings.max_bytes
        s = ClipSettings(settings.width, settings.fps, budget, settings.trim_frames)
        gif = out_dir / f"{name}.gif"
        w, fps, size = emit_gif_within_budget(
            src,
            gif,
            seg,
            frames.fps,
            footage.bbox,
            frames.width,
            src_width,
            runner=runner,
            size_of=size_of,
            settings=s,
        )
        flag = "  OVER BUDGET" if size > budget else ""
        print(f"{name:32s} {w}x{fps}fps {size / 1e6:5.2f} MB{flag}")
        written.append(gif)
        if name in mp4_names:
            mp4 = out_dir / f"{name}.mp4"
            res = runner.run(
                mp4_argv(
                    src, mp4, seg, frames.fps, footage.bbox, frames.width, src_width
                )
            )
            if res.returncode != 0:
                err = res.stderr.decode(errors="replace")
                raise RuntimeError(f"ffmpeg failed writing {mp4}: {err}")
            written.append(mp4)
        contact_sheet(frames, seg, footage.bbox, out_dir / f"{name}.contact.png")
    return written

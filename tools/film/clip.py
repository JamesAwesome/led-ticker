"""Cut analyzed footage into named GIFs (two-pass palette, size-budgeted) and
mp4s, plus a contact sheet per clip for review without opening every GIF."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tools.film.analyze import BBox, Footage, Interval, analyze_footage, decode_gray
from tools.film.manifest import film_names
from tools.film.runner import Runner

HERO_MAX_BYTES = 4_000_000
ENCODE_TIMEOUT = 1800.0  # one two-pass palette encode of a long 4K segment
# (width, fps). Real footage compresses 4-6x worse than renders (LED dot
# grid + sensor noise), hence the rungs below the plan's three.
LADDER: tuple[tuple[int, int], ...] = (
    (800, 20),
    (640, 20),
    (640, 15),
    (640, 12),
    (560, 12),
    (480, 10),
)
DENOISE = "hqdn3d=4:3:6:4.5"  # temporal+spatial; tames sensor noise before palette
WEB_WIDTH = 1280
WEB_CRF = "24"  # ~2 MB for a 30 s hero at 1280 wide


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
        f"{_crop_filter(bbox, analysis_width, src_width)},{DENOISE},fps={settings.fps},"
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


def web_mp4_argv(
    src: Path,
    out: Path,
    seg: Interval,
    fps_src: float,
    bbox: BBox,
    analysis_width: int,
    src_width: int,
) -> list[str]:
    """Docs-sized h264: the hero loop is a video on the docs site, not a GIF."""
    ss, t = _window(seg, fps_src, 1)
    crop = _crop_filter(bbox, analysis_width, src_width)
    vf = f"{crop},{DENOISE},scale={WEB_WIDTH}:-2"
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
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        WEB_CRF,
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(out),
    ]


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
            gif_argv(src, out, seg, fps_src, bbox, analysis_width, src_width, rung),
            timeout=ENCODE_TIMEOUT,
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


def contact_sheet_argv(
    src: Path,
    out: Path,
    seg: Interval,
    fps_src: float,
    bbox: BBox | None,
    analysis_width: int,
    src_width: int,
) -> list[str]:
    """Three COLOR frames (start / middle / end of the window) from the source,
    cropped like the GIF, stacked vertically — for judging exposure and color."""
    ss, t = _window(seg, fps_src, 1)
    crop = f"{_crop_filter(bbox, analysis_width, src_width)}," if bbox else ""
    chain = f"{crop}fps={3 / float(t):.6f},scale=800:-1:flags=lanczos,tile=1x3"
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
        "-frames:v",
        "1",
        str(out),
    ]


def contact_sheet(
    src: Path,
    out: Path,
    seg: Interval,
    fps_src: float,
    bbox: BBox | None,
    analysis_width: int,
    src_width: int,
    runner: Runner,
) -> None:
    res = runner.run(
        contact_sheet_argv(src, out, seg, fps_src, bbox, analysis_width, src_width),
        timeout=ENCODE_TIMEOUT,
    )
    if res.returncode != 0:
        err = res.stderr.decode(errors="replace")
        raise RuntimeError(f"ffmpeg failed writing {out}: {err}")


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
        ],
        timeout=60.0,
    )
    if res.returncode != 0 or not res.stdout.strip():
        err = res.stderr.decode(errors="replace")
        raise RuntimeError(f"ffprobe could not read {src}: {err}")
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
    full_frame: bool = False,
    gif: bool = True,
    slate_threshold: float = 180.0,
    change_threshold: int = 60,
    size_of: Callable[[Path], int] = lambda p: p.stat().st_size,
) -> list[Path]:
    frames = decode_gray(src, runner)
    footage = analyze_footage(
        frames,
        crop=crop,
        take=take,
        slate_threshold=slate_threshold,
        change_threshold=change_threshold,
    )
    names = film_names(manifest.read_text())
    plan = plan_clips(footage, names)
    src_width = _probe_width(src, runner)
    b = footage.bbox
    k = src_width / frames.width
    print(
        f"bbox {b.x}:{b.y}:{b.w}:{b.h} (analysis) = "
        f"{round(b.x * k)}:{round(b.y * k)}:{round(b.w * k)}:{round(b.h * k)} "
        "(source); "
        f"peak luma {footage.peak_luma:.0f}; {len(footage.anchors)} anchor(s), "
        f"{len(plan)} clip(s)"
    )
    crop_for_mp4 = None if full_frame else footage.bbox
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, seg in plan:
        if gif:
            budget = HERO_MAX_BYTES if name in hero_budget_names else settings.max_bytes
            s = ClipSettings(settings.width, settings.fps, budget, settings.trim_frames)
            gif_path = out_dir / f"{name}.gif"
            w, fps, size = emit_gif_within_budget(
                src,
                gif_path,
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
            written.append(gif_path)
        if name in mp4_names:
            mp4 = out_dir / f"{name}.mp4"
            res = runner.run(
                mp4_argv(
                    src, mp4, seg, frames.fps, crop_for_mp4, frames.width, src_width
                ),
                timeout=ENCODE_TIMEOUT,
            )
            if res.returncode != 0:
                err = res.stderr.decode(errors="replace")
                raise RuntimeError(f"ffmpeg failed writing {mp4}: {err}")
            print(f"{name:32s} mp4 {'full frame' if full_frame else 'cropped'}")
            written.append(mp4)
            if gif:  # docs mode: also a web-sized cropped mp4 for the hero
                web = out_dir / f"{name}.web.mp4"
                res = runner.run(
                    web_mp4_argv(
                        src, web, seg, frames.fps, footage.bbox, frames.width, src_width
                    ),
                    timeout=ENCODE_TIMEOUT,
                )
                if res.returncode != 0:
                    err = res.stderr.decode(errors="replace")
                    raise RuntimeError(f"ffmpeg failed writing {web}: {err}")
                print(f"{name:32s} web mp4 {WEB_WIDTH}w crf {WEB_CRF}")
                written.append(web)
        contact_sheet(
            src,
            out_dir / f"{name}.contact.png",
            seg,
            frames.fps,
            crop_for_mp4,
            frames.width,
            src_width,
            runner,
        )
    return written

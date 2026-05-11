#!/usr/bin/env python3
"""Render a led-ticker config TOML to a gif at panel resolution.

Drives the existing ticker engine against the test stub canvas; captures
each `SwapOnVSync` frame; encodes to gif. Generates placeholder assets
on the fly for any image/gif paths that don't resolve.

Usage:
    uv run python tools/render_demo/render.py <config.toml> -o out.gif \\
        [--duration 5] [--upscale 4] [--fps 20] [--start-section 0]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import tempfile
import time
import tomllib
from pathlib import Path

# Ensure the rgbmatrix test stub is importable BEFORE any led_ticker import.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "stubs"))
sys.path.insert(0, str(_REPO_ROOT))

import imageio.v2 as imageio  # noqa: E402
import tomli_w  # noqa: E402
from PIL import Image  # noqa: E402
from tools.render_demo.placeholder import (  # noqa: E402
    rewrite_config_for_missing_assets,
)
from tools.render_demo.recording import RecordingMatrix  # noqa: E402


def _load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def _trim_to_section(config: dict, start_section: int) -> dict:
    """Drop sections before `start_section` so a long config jumps to
    the selected section."""
    sections = (config.get("playlist") or {}).get("section") or []
    if start_section <= 0 or start_section >= len(sections):
        return config
    config["playlist"]["section"] = sections[start_section:]
    return config


def _upscale(img: Image.Image, factor: int) -> Image.Image:
    if factor == 1:
        return img
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


async def _drive_engine(
    rewritten_cfg_path: Path,
    duration_s: float,
    recorder_holder: list,
    original_cfg_path: Path | None = None,
) -> float:
    """Start the led-ticker app on the rewritten config; substitute a
    RecordingMatrix for the real RGBMatrix; cancel after `duration_s`.

    Patches `led_ticker.frame.RGBMatrix` so when LedFrame instantiates the
    matrix, it gets a `RecordingMatrix` wrapping the stub. The recorder
    is appended to `recorder_holder` so the caller can read frames after
    the run ends. Returns the engine's stop-time (`time.monotonic()`)
    so the encoder can credit the LAST captured frame with the time
    that elapsed between its swap and the engine cancellation.

    `original_cfg_path` — if supplied, anchors the hi-res font search
    directory to ``<original_cfg_path.parent>/fonts/`` BEFORE the engine
    starts. This lets demos that live outside the repo root (e.g. in
    ``docs/site/demos-long/``) supply their own fonts in a local
    ``fonts/`` subdirectory without those fonts needing to be in the
    system ``config/fonts/`` or the engine's temp rewrite directory.
    """
    from led_ticker import app as app_mod
    from led_ticker import frame as frame_mod

    original_rgbmatrix = frame_mod.RGBMatrix
    original_configure = app_mod._configure_user_font_dir

    def patched_rgbmatrix(*args, **kwargs):
        real = original_rgbmatrix(*args, **kwargs)
        rec = RecordingMatrix(real)
        recorder_holder.append(rec)
        return rec

    # When the caller supplied the original config path, pre-anchor the
    # hi-res font directory to that file's sibling ``fonts/`` dir.  We
    # then suppress the app's own ``_configure_user_font_dir`` call so it
    # doesn't re-anchor to the temp-dir copy (which has no fonts/).
    if original_cfg_path is not None:
        original_configure(original_cfg_path)
        app_mod._configure_user_font_dir = lambda _path: None  # type: ignore[method-assign]

    frame_mod.RGBMatrix = patched_rgbmatrix
    try:
        task = asyncio.create_task(app_mod.run(rewritten_cfg_path))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=duration_s)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        frame_mod.RGBMatrix = original_rgbmatrix
        app_mod._configure_user_font_dir = original_configure
    return time.monotonic()


def render(
    config_path: Path,
    out_path: Path,
    *,
    duration: float = 5.0,
    upscale: int = 4,
    fps: int = 20,
    start_section: int = 0,
) -> None:
    config = _load_config(config_path)
    config = _trim_to_section(config, start_section)

    with tempfile.TemporaryDirectory(prefix="led-ticker-render-") as tmp:
        tmp_dir = Path(tmp)
        rewritten = rewrite_config_for_missing_assets(
            config,
            config_dir=config_path.parent,
            placeholder_dir=tmp_dir / "placeholders",
        )

        # Write rewritten config to a temp file the engine can load.
        rewritten_path = tmp_dir / "rewritten.toml"
        rewritten_path.write_bytes(tomli_w.dumps(rewritten).encode("utf-8"))

        recorder_holder: list = []
        end_time = asyncio.run(
            _drive_engine(
                rewritten_path,
                duration,
                recorder_holder,
                original_cfg_path=config_path,
            )
        )

        if not recorder_holder:
            raise RuntimeError(
                "Renderer never instantiated a matrix; engine may have crashed."
            )
        rec = recorder_holder[0]
        if not rec.frames:
            raise RuntimeError(
                "No frames captured; the engine started but never swapped a canvas."
            )

        upscaled = [_upscale(f, upscale) for f in rec.frames]
        # Per-frame durations come from the wall-clock interval between
        # consecutive swaps (last frame: between its swap and engine
        # cancellation). Without measured intervals, a static-fast-path
        # widget — one swap then `await asyncio.sleep(hold)` — gets
        # encoded as a single 50 ms frame even when the engine intended
        # a 4 sec hold. With them, the encoder credits the lone frame
        # with the actual hold time. Multi-frame renders also benefit:
        # any tick that took longer than 50 ms (capture overhead, GC
        # pause) gets its real duration rather than a flat tick_ms.
        #
        # Collapse runs of identical consecutive frames into a single
        # kept frame whose duration sums the interval of each. Without
        # this, imageio.mimsave's silent identical-frame dedupe would
        # discard the cumulative display time anyway.
        #
        # imageio quirk: scalar `duration` is seconds; list `duration`
        # is milliseconds. We use ms in both shapes for consistency.
        intervals_ms = _intervals_ms(rec.timestamps, end_time)
        kept: list[Image.Image] = []
        durations: list[float] = []
        prev_bytes: bytes | None = None
        for f, interval in zip(upscaled, intervals_ms, strict=True):
            cur_bytes = f.tobytes()
            if cur_bytes == prev_bytes:
                durations[-1] += interval
            else:
                kept.append(f)
                durations.append(interval)
                prev_bytes = cur_bytes
        # PIL's single-frame gif writer rejects list `duration` (expects
        # a scalar); pass the sum as a scalar in that case so a fully-
        # static render still encodes the engine's wall-clock hold.
        encode_duration = durations[0] if len(kept) == 1 else durations
        imageio.mimsave(out_path, kept, format="GIF", duration=encode_duration, loop=0)


def _intervals_ms(timestamps: list[float], end_time: float) -> list[float]:
    """Compute the wall-clock duration each captured frame should hold.

    Frame `i`'s duration is the time between its swap and the next
    swap (or `end_time` for the last frame). Returns milliseconds.
    """
    intervals: list[float] = []
    for i, t in enumerate(timestamps):
        next_t = timestamps[i + 1] if i + 1 < len(timestamps) else end_time
        intervals.append(max(0.0, (next_t - t) * 1000.0))
    return intervals


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a led-ticker config to a gif")
    parser.add_argument("config", type=Path, help="Path to TOML config")
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output gif path"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Capture duration in seconds (default 5)",
    )
    parser.add_argument(
        "--upscale", type=int, default=4, help="Pixel upscale factor (default 4)"
    )
    parser.add_argument(
        "--fps", type=int, default=20, help="Output gif fps (default 20)"
    )
    parser.add_argument(
        "--start-section",
        type=int,
        default=0,
        help="Start at this section index (default 0)",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Config not found: {args.config}", file=sys.stderr)
        sys.exit(2)

    render(
        args.config,
        args.output,
        duration=args.duration,
        upscale=args.upscale,
        fps=args.fps,
        start_section=args.start_section,
    )


if __name__ == "__main__":
    main()

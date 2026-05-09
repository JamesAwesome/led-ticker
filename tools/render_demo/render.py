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
    rewritten_cfg_path: Path, duration_s: float, recorder_holder: list
) -> None:
    """Start the led-ticker app on the rewritten config; substitute a
    RecordingMatrix for the real RGBMatrix; cancel after `duration_s`.

    Patches `led_ticker.frame.RGBMatrix` so when LedFrame instantiates the
    matrix, it gets a `RecordingMatrix` wrapping the stub. The recorder
    is appended to `recorder_holder` so the caller can read frames after
    the run ends.
    """
    from led_ticker import frame as frame_mod
    from led_ticker.app import run as app_run

    original_rgbmatrix = frame_mod.RGBMatrix

    def patched_rgbmatrix(*args, **kwargs):
        real = original_rgbmatrix(*args, **kwargs)
        rec = RecordingMatrix(real)
        recorder_holder.append(rec)
        return rec

    frame_mod.RGBMatrix = patched_rgbmatrix
    try:
        task = asyncio.create_task(app_run(rewritten_cfg_path))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=duration_s)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        frame_mod.RGBMatrix = original_rgbmatrix


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
        asyncio.run(_drive_engine(rewritten_path, duration, recorder_holder))

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
        imageio.mimsave(out_path, upscaled, format="GIF", duration=1.0 / fps, loop=0)


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

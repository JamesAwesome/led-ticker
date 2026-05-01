"""Test that gif widget paths are resolved relative to the config dir."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from led_ticker.app import _build_widget


async def _build(cfg, config_dir):
    import aiohttp

    async with aiohttp.ClientSession() as s:
        return await _build_widget(cfg, s, config_dir=config_dir)


def _write_tiny_gif(path: Path) -> None:
    img = Image.new("RGB", (4, 4), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    path.write_bytes(buf.getvalue())


async def test_gif_relative_path_resolves_against_config_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    assets = config_dir / "assets"
    assets.mkdir()
    gif_path = assets / "tiny.gif"
    _write_tiny_gif(gif_path)

    cfg = {"type": "gif", "path": "assets/tiny.gif", "fit": "stretch"}
    widget = await _build(cfg, config_dir=config_dir)

    assert Path(widget.path) == gif_path.resolve()


async def test_gif_absolute_path_left_alone(tmp_path):
    gif_path = tmp_path / "abs.gif"
    _write_tiny_gif(gif_path)

    cfg = {"type": "gif", "path": str(gif_path.resolve()), "fit": "stretch"}
    widget = await _build(cfg, config_dir=tmp_path / "elsewhere")

    assert Path(widget.path) == gif_path.resolve()

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


async def test_gif_text_kwarg_not_renamed_to_message(tmp_path):
    """Regression: _build_widget renames `text` → `message` for the
    TickerMessage widget but must skip it for GifPlayer, which accepts
    `text` natively for its alongside-text feature."""
    gif_path = tmp_path / "tiny.gif"
    _write_tiny_gif(gif_path)

    cfg = {
        "type": "gif",
        "path": str(gif_path.resolve()),
        "fit": "pillarbox",
        "text": "PIKACHU!",
        "text_align": "right",
    }
    widget = await _build(cfg, config_dir=tmp_path)

    assert widget.text == "PIKACHU!"
    assert widget.text_align == "right"


async def test_gif_accepts_font_kwarg(tmp_path):
    """Regression: _BaseImageWidget originally declared `font` with
    `init=False`, so a config like `font = "Inter-Regular"` raised
    `TypeError: __init__() got an unexpected keyword argument 'font'`
    inside _build_widget when the resolved font object was passed
    through. Drives the full _build_widget path that broke on hardware.
    """
    from led_ticker.fonts.hires_loader import HiresFont

    gif_path = tmp_path / "tiny.gif"
    _write_tiny_gif(gif_path)

    cfg = {
        "type": "gif",
        "path": str(gif_path.resolve()),
        "fit": "pillarbox",
        "text": "@firebird",
        "font": "Inter-Regular",
        "font_size": 24,
    }
    widget = await _build(cfg, config_dir=tmp_path)

    assert isinstance(widget.font, HiresFont)
    assert widget.font.size == 24


async def test_image_accepts_font_kwarg(tmp_path):
    """Same regression applies to the StillImage widget (`type = "image"`)
    — both share `_BaseImageWidget`."""
    import io as _io

    from PIL import Image as _Image

    from led_ticker.fonts.hires_loader import HiresFont

    img_path = tmp_path / "tiny.png"
    img = _Image.new("RGB", (4, 4), color=(255, 255, 255))
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    img_path.write_bytes(buf.getvalue())

    cfg = {
        "type": "image",
        "path": str(img_path.resolve()),
        "fit": "pillarbox",
        "text": "hi",
        "font": "Inter-Bold",
        "font_size": 28,
    }
    widget = await _build(cfg, config_dir=tmp_path)

    assert isinstance(widget.font, HiresFont)
    assert widget.font.size == 28


async def test_gif_two_row_text_overlay_via_build_widget(tmp_path):
    """End-to-end: TOML config sets `bottom_text` on a gif → _build_widget
    constructs in two-row mode without raising. Pin per-row fields land
    on the widget. (Smoke test for the full path: TOML → resolve_font
    → widget construction → two-row mode.)
    """
    from led_ticker.fonts.hires_loader import HiresFont

    gif_path = tmp_path / "tiny.gif"
    _write_tiny_gif(gif_path)

    cfg = {
        "type": "gif",
        "path": str(gif_path.resolve()),
        "fit": "pillarbox",
        "top_text": "@firebird",
        "bottom_text": "Follow us! :instagram:",
        "top_font": "Inter-Bold",
        "top_font_size": 14,
        "bottom_font": "Inter-Regular",
        "bottom_font_size": 12,
        "top_color": [255, 220, 70],
        "bottom_color": [255, 150, 190],
        "top_row_height": 5,
    }
    widget = await _build(cfg, config_dir=tmp_path)

    assert widget._is_two_row()
    assert widget.top_text == "@firebird"
    assert widget.bottom_text == "Follow us! :instagram:"
    assert isinstance(widget.top_font, HiresFont)
    assert widget.top_font.name == "Inter-Bold"
    assert widget.top_font.size == 14
    assert isinstance(widget.bottom_font, HiresFont)
    assert widget.bottom_font.name == "Inter-Regular"
    assert widget.top_row_height == 5

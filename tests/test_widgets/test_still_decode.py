"""Tests for the pure decode_still helper. Mirrors test_gif_decode.py."""

from __future__ import annotations

import pytest
from PIL import Image

from led_ticker.widgets._still_decode import decode_still


def _write_png(path, color=(200, 30, 40), size=(32, 32), alpha=None):
    if alpha is not None:
        img = Image.new("RGBA", size, color=(*color, alpha))
    else:
        img = Image.new("RGB", size, color=color)
    img.save(path, format="PNG")


def test_returns_panel_sized_rgb_bytes(tmp_path):
    p = tmp_path / "x.png"
    _write_png(p, color=(50, 100, 150))
    pixels = decode_still(p, panel_w=256, panel_h=64, fit="stretch")
    assert isinstance(pixels, bytes)
    assert len(pixels) == 256 * 64 * 3


def test_stretch_fills_full_canvas(tmp_path):
    p = tmp_path / "red.png"
    _write_png(p, color=(200, 30, 40))
    pixels = decode_still(p, panel_w=256, panel_h=64, fit="stretch")
    assert pixels[0:3] == bytes((200, 30, 40))
    assert pixels[-3:] == bytes((200, 30, 40))


def test_pillarbox_centers_with_black_bands(tmp_path):
    p = tmp_path / "sq.png"
    _write_png(p, color=(255, 255, 255), size=(32, 32))
    pixels = decode_still(p, panel_w=256, panel_h=64, fit="pillarbox")

    def px(x, y):
        i = (y * 256 + x) * 3
        return (pixels[i], pixels[i + 1], pixels[i + 2])

    assert px(0, 32) == (0, 0, 0)
    assert px(255, 32) == (0, 0, 0)
    assert px(128, 32) == (255, 255, 255)


def test_alpha_zero_becomes_black(tmp_path):
    """Fully transparent PNGs decode to black so the skip-black scroll
    path treats them as see-through."""
    p = tmp_path / "transparent.png"
    _write_png(p, color=(255, 0, 0), size=(32, 32), alpha=0)
    pixels = decode_still(p, panel_w=256, panel_h=64, fit="stretch")
    # Sample anywhere — should be black
    assert pixels[0:3] == bytes((0, 0, 0))
    mid = (32 * 256 + 128) * 3
    assert pixels[mid : mid + 3] == bytes((0, 0, 0))


def test_jpg_decodes(tmp_path):
    p = tmp_path / "x.jpg"
    Image.new("RGB", (64, 32), color=(120, 200, 255)).save(p, format="JPEG")
    pixels = decode_still(p, panel_w=256, panel_h=64, fit="stretch")
    # JPEG roundtrips with slight color drift; just check non-black + size
    assert len(pixels) == 256 * 64 * 3
    assert pixels[0:3] != bytes((0, 0, 0))


def test_unknown_fit_raises(tmp_path):
    p = tmp_path / "x.png"
    _write_png(p)
    with pytest.raises(ValueError, match="fit"):
        decode_still(p, panel_w=256, panel_h=64, fit="weird")


def test_unknown_gif_align_raises(tmp_path):
    p = tmp_path / "x.png"
    _write_png(p)
    with pytest.raises(ValueError, match="gif_align"):
        decode_still(p, panel_w=256, panel_h=64, fit="pillarbox", gif_align="up")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        decode_still(tmp_path / "nope.png", panel_w=256, panel_h=64, fit="stretch")


def test_animated_gif_uses_first_frame_only(tmp_path):
    """If a multi-frame GIF is fed to decode_still, it should pin to
    frame 0 — use the gif widget for animation."""
    import io

    img1 = Image.new("RGB", (32, 32), color=(255, 0, 0))
    img2 = Image.new("RGB", (32, 32), color=(0, 255, 0))
    buf = io.BytesIO()
    img1.save(
        buf,
        format="GIF",
        save_all=True,
        append_images=[img2],
        duration=100,
        loop=0,
    )
    p = tmp_path / "anim.gif"
    p.write_bytes(buf.getvalue())

    pixels = decode_still(p, panel_w=256, panel_h=64, fit="stretch")
    # Frame 0 is red; frame 1 is green. We must see red.
    assert pixels[0] > 200  # red dominant
    assert pixels[1] < 50

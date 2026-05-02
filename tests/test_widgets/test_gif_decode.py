"""Tests for the pure decode_gif helper."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from led_ticker.widgets._gif_decode import decode_gif


def _make_gif(
    frames: list[tuple[int, int, int]],
    size: tuple[int, int] = (32, 32),
    duration_ms: int = 100,
) -> io.BytesIO:
    """Build an in-memory GIF with `len(frames)` solid-color frames."""
    images = [Image.new("RGB", size, color=c) for c in frames]
    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
    )
    buf.seek(0)
    return buf


def test_decode_returns_one_entry_per_frame(tmp_path):
    path = tmp_path / "two.gif"
    path.write_bytes(_make_gif([(255, 0, 0), (0, 255, 0)]).getvalue())

    frames = decode_gif(path, panel_w=256, panel_h=64, fit="stretch")

    assert len(frames) == 2
    for pixels, duration in frames:
        assert isinstance(pixels, bytes)
        assert len(pixels) == 256 * 64 * 3  # rgb
        assert duration == 100


def test_stretch_fills_full_canvas_with_input_color(tmp_path):
    path = tmp_path / "red.gif"
    path.write_bytes(_make_gif([(200, 30, 40)]).getvalue())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="stretch")

    # Every pixel should be the source red
    assert pixels[0:3] == bytes((200, 30, 40))
    assert pixels[-3:] == bytes((200, 30, 40))


def test_pillarbox_centers_square_with_black_bands(tmp_path):
    # Square 32×32 GIF in pillarbox mode: scale by height to 64, gives
    # 64×64 centered horizontally on the 256×64 canvas.
    path = tmp_path / "sq.gif"
    path.write_bytes(_make_gif([(255, 255, 255)], size=(32, 32)).getvalue())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="pillarbox")

    def px(x: int, y: int) -> tuple[int, int, int]:
        i = (y * 256 + x) * 3
        return (pixels[i], pixels[i + 1], pixels[i + 2])

    # Left/right pillars are black
    assert px(0, 32) == (0, 0, 0)
    assert px(255, 32) == (0, 0, 0)
    # Center area is white
    assert px(128, 32) == (255, 255, 255)


def test_letterbox_centers_wide_with_black_bands(tmp_path):
    # 256×32 GIF in letterbox: scale by width to 256, gives 256×32
    # centered vertically (black bands top + bottom).
    path = tmp_path / "wide.gif"
    path.write_bytes(_make_gif([(120, 200, 255)], size=(256, 32)).getvalue())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="letterbox")

    def px(x: int, y: int) -> tuple[int, int, int]:
        i = (y * 256 + x) * 3
        return (pixels[i], pixels[i + 1], pixels[i + 2])

    # Top + bottom rows are black
    assert px(128, 0) == (0, 0, 0)
    assert px(128, 63) == (0, 0, 0)
    # Middle row is the input color
    assert px(128, 32) == (120, 200, 255)


def test_crop_fills_canvas_with_no_black(tmp_path):
    # Square 64×64 source in crop mode covers 256×64 by scaling to
    # 256×256 then cropping vertically. Every output pixel is white.
    path = tmp_path / "sq.gif"
    path.write_bytes(_make_gif([(255, 255, 255)], size=(64, 64)).getvalue())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="crop")

    # No pixel should be black
    for i in range(0, len(pixels), 3):
        assert (pixels[i], pixels[i + 1], pixels[i + 2]) == (255, 255, 255)


def test_zero_duration_is_clamped(tmp_path):
    path = tmp_path / "fast.gif"
    path.write_bytes(_make_gif([(0, 0, 0)], duration_ms=0).getvalue())

    frames = decode_gif(path, panel_w=256, panel_h=64, fit="stretch")
    assert frames[0][1] >= 50  # clamped to ≥50 ms


def test_unknown_fit_raises(tmp_path):
    path = tmp_path / "x.gif"
    path.write_bytes(_make_gif([(0, 0, 0)]).getvalue())

    with pytest.raises(ValueError, match="fit"):
        decode_gif(path, panel_w=256, panel_h=64, fit="weird")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        decode_gif(tmp_path / "nope.gif", panel_w=256, panel_h=64, fit="stretch")


def test_pillarbox_h_align_left_anchors_at_x_zero(tmp_path):
    """h_align='left' positions a 64×64 pillarboxed frame at x=0..63;
    the right side (cols 64..255) is the black pillar."""
    path = tmp_path / "sq.gif"
    path.write_bytes(_make_gif([(255, 255, 255)], size=(32, 32)).getvalue())

    [(pixels, _)] = decode_gif(
        path, panel_w=256, panel_h=64, fit="pillarbox", h_align="left"
    )

    def px(x: int, y: int) -> tuple[int, int, int]:
        i = (y * 256 + x) * 3
        return (pixels[i], pixels[i + 1], pixels[i + 2])

    # Left edge has gif content
    assert px(0, 32) == (255, 255, 255)
    assert px(63, 32) == (255, 255, 255)
    # Right side is the black pillar
    assert px(64, 32) == (0, 0, 0)
    assert px(255, 32) == (0, 0, 0)


def test_pillarbox_h_align_right_anchors_at_panel_edge(tmp_path):
    """h_align='right' positions the 64×64 frame at cols 192..255 with
    the black pillar covering cols 0..191."""
    path = tmp_path / "sq.gif"
    path.write_bytes(_make_gif([(255, 255, 255)], size=(32, 32)).getvalue())

    [(pixels, _)] = decode_gif(
        path, panel_w=256, panel_h=64, fit="pillarbox", h_align="right"
    )

    def px(x: int, y: int) -> tuple[int, int, int]:
        i = (y * 256 + x) * 3
        return (pixels[i], pixels[i + 1], pixels[i + 2])

    # Left side is the black pillar
    assert px(0, 32) == (0, 0, 0)
    assert px(191, 32) == (0, 0, 0)
    # Right side has gif content
    assert px(192, 32) == (255, 255, 255)
    assert px(255, 32) == (255, 255, 255)


def test_unknown_h_align_raises(tmp_path):
    path = tmp_path / "x.gif"
    path.write_bytes(_make_gif([(0, 0, 0)]).getvalue())

    with pytest.raises(ValueError, match="h_align"):
        decode_gif(path, panel_w=256, panel_h=64, fit="pillarbox", h_align="weird")


def _make_transparent_gif_bytes() -> bytes:
    """Build a P-mode GIF with palette index 0 marked transparent.
    Top-left quadrant is transparent (idx 0, palette color = green to
    prove convert("RGB") would NOT give black there); rest are red.

    Uses a 64×16 source so a 4× upscale to 256×64 doesn't blow up
    Lanczos kernel bleed across the transparent/opaque boundary."""
    img = Image.new("P", (64, 16))
    img.putpalette(
        [
            0,
            255,
            0,  # idx 0: GREEN — transparent, must not appear in output
            255,
            0,
            0,  # idx 1: red
        ]
    )
    for y in range(16):
        for x in range(64):
            transparent_zone = x < 32 and y < 8
            img.putpixel((x, y), 0 if transparent_zone else 1)
    buf = io.BytesIO()
    img.save(buf, format="GIF", transparency=0)
    return buf.getvalue()


def test_transparent_pixels_become_black_not_palette_color(tmp_path):
    """convert('RGB') resolves transparent palette index to its raw color
    (green here), which would mask scrolling text underneath. The decoder
    must instead composite via alpha so transparent → (0,0,0)."""
    path = tmp_path / "t.gif"
    path.write_bytes(_make_transparent_gif_bytes())

    [(pixels, _)] = decode_gif(path, panel_w=256, panel_h=64, fit="stretch")

    def px(x: int, y: int) -> tuple[int, int, int]:
        i = (y * 256 + x) * 3
        return (pixels[i], pixels[i + 1], pixels[i + 2])

    # Source 64×16 → output 256×64 (4× scale). Transparent zone covers
    # source cols 0..31, rows 0..7 → output cols 0..127, rows 0..31.
    # Sample at the very corner — Lanczos kernel bleed across the
    # transparent/opaque boundary can tint the inner-edge pixels by a
    # few units of red even ~5 px in, so we keep this far from any
    # transition. PIL Lanczos coefficients are stable, but a future
    # PIL upgrade could shift edge weights — corner sampling is robust.
    assert px(2, 2) == (0, 0, 0)  # NOT (0, 255, 0) palette green
    # Opaque red zone covers source cols 32+, rows 0..7 → output cols 128+
    assert px(200, 5) == (255, 0, 0)

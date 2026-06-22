from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "config" / "assets"

# The source sprite is 20×20; the derived assets are 220×220 (11× upscale).
# Nearest-neighbor scaling produces uniform 11×11 blocks: every pixel in a
# block equals the block's top-left pixel.  Bilinear or Lanczos interpolation
# blurs block edges and breaks this invariant.
_SOURCE_SIZE = 20
_TARGET_SIZE = 220
_BLOCK = _TARGET_SIZE // _SOURCE_SIZE  # 11


def _assert_nearest_neighbor(img: Image.Image, name: str) -> None:
    """Assert that the image was upscaled with nearest-neighbor (not blurred).

    Samples every 11×11 block in the 220×220 image; within each block every
    pixel must equal the top-left corner pixel.  Bilinear or smooth rescaling
    produces intermediate values along block edges and fails this check.
    """
    rgb = img.convert("RGB")
    px = rgb.load()
    mismatches: list[str] = []
    for by in range(_SOURCE_SIZE):
        for bx in range(_SOURCE_SIZE):
            anchor = px[bx * _BLOCK, by * _BLOCK]
            for dy in range(_BLOCK):
                for dx in range(_BLOCK):
                    got = px[bx * _BLOCK + dx, by * _BLOCK + dy]
                    if got != anchor:
                        mismatches.append(
                            f"block({bx},{by}) offset({dx},{dy}): "
                            f"expected {anchor} got {got}"
                        )
            if mismatches:
                break
        if mismatches:
            break
    assert not mismatches, (
        f"{name}: nearest-neighbor invariant violated (blurry upscale? {mismatches[0]})"
    )


def test_five_phoenix_assets_exist_and_are_correct():
    expected = {
        "phoenix.gif": ("GIF", ("RGB", "P", "L"), True),
        "phoenix_transparent.gif": ("GIF", ("P",), True),
        "phoenix.png": ("PNG", ("RGB", "P"), False),
        "phoenix_transparent.png": ("PNG", ("RGBA",), False),
        "phoenix.webp": ("WEBP", ("RGBA", "RGB"), True),
    }
    for name, (fmt, modes, animated) in expected.items():
        p = ASSETS / name
        assert p.exists(), f"missing derived asset {name}"
        im = Image.open(p)
        assert im.format == fmt, f"{name}: format {im.format} != {fmt}"
        assert im.mode in modes, f"{name}: mode {im.mode} not in {modes}"
        assert im.size == (220, 220), f"{name}: size {im.size} != (220, 220)"
        if animated:
            assert getattr(im, "n_frames", 1) > 1, f"{name}: expected animation"


def test_phoenix_png_is_nearest_neighbor():
    """Assert phoenix.png was upscaled with nearest-neighbor (not bilinear/smooth).

    The source is 20×20; the derived PNG is 220×220 (11× upscale).
    Nearest-neighbor produces uniform 11×11 blocks; any blurring algorithm
    introduces intermediate colors at block edges and fails this check.
    """
    im = Image.open(ASSETS / "phoenix.png")
    _assert_nearest_neighbor(im, "phoenix.png")


def test_transparent_png_has_alpha():
    im = Image.open(ASSETS / "phoenix_transparent.png")
    assert im.mode == "RGBA"
    assert im.getchannel("A").getextrema()[0] == 0  # has fully-transparent pixels


def test_transparent_gif_has_transparency():
    im = Image.open(ASSETS / "phoenix_transparent.gif")
    assert im.mode == "P"
    assert "transparency" in im.info, (
        "phoenix_transparent.gif missing transparency info"
    )
    # Verify first frame contains transparent pixels (index == transparency value)
    t_idx = im.info["transparency"]
    first_frame_data = list(im.get_flattened_data())
    assert any(px == t_idx for px in first_frame_data), (
        "phoenix_transparent.gif frame 0 has no transparent pixels"
    )

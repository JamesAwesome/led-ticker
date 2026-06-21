from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "config" / "assets"


def test_five_phoenix_assets_exist_and_are_correct():
    expected = {
        "phoenix.gif": ("GIF", "RGB_or_P", True),
        "phoenix_transparent.gif": ("GIF", "P", True),
        "phoenix.png": ("PNG", "RGB", False),
        "phoenix_transparent.png": ("PNG", "RGBA", False),
        "phoenix.webp": ("WEBP", "RGBA", True),
    }
    for name, (fmt, _mode, animated) in expected.items():
        p = ASSETS / name
        assert p.exists(), f"missing derived asset {name}"
        im = Image.open(p)
        assert im.format == fmt, f"{name}: format {im.format} != {fmt}"
        assert im.size == (220, 220), f"{name}: size {im.size} != (220, 220)"
        if animated:
            assert getattr(im, "n_frames", 1) > 1, f"{name}: expected animation"


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

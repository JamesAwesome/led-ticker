"""Tests for placeholder asset generation."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure tools.render_demo is importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from PIL import Image  # noqa: E402
from tools.render_demo.placeholder import (  # noqa: E402
    make_gif_placeholder,
    make_image_placeholder,
    rewrite_config_for_missing_assets,
)


def test_image_placeholder_has_correct_dimensions(tmp_path):
    out = tmp_path / "ph.png"
    make_image_placeholder(out, width=64, height=64, missing_path="assets/foo.png")
    img = Image.open(out)
    assert img.size == (64, 64)


def test_image_placeholder_is_dark_lavender(tmp_path):
    out = tmp_path / "ph.png"
    make_image_placeholder(out, width=32, height=32, missing_path="x.png")
    img = Image.open(out).convert("RGB")
    # Bottom-right corner is solid background (no text overlay there).
    r, g, b = img.getpixel((30, 30))
    # Rough check: dark-lavender range.
    assert 30 <= r <= 90
    assert 25 <= g <= 80
    assert 60 <= b <= 130


def test_gif_placeholder_has_three_frames(tmp_path):
    out = tmp_path / "ph.gif"
    make_gif_placeholder(out, width=32, height=32, missing_path="x.gif")
    img = Image.open(out)
    img.seek(0)
    frame_count = 0
    while True:
        frame_count += 1
        try:
            img.seek(img.tell() + 1)
        except EOFError:
            break
    assert frame_count == 3


def test_rewrite_config_substitutes_missing_image(tmp_path):
    cfg = {
        "playlist": {
            "section": [
                {
                    "widget": [
                        {"type": "image", "path": "assets/missing.png"},
                    ],
                }
            ]
        }
    }
    rewritten = rewrite_config_for_missing_assets(
        cfg,
        config_dir=tmp_path,
        placeholder_dir=tmp_path / "ph",
    )
    new_path = rewritten["playlist"]["section"][0]["widget"][0]["path"]
    # Must point at a real file (the placeholder) AND no longer be the
    # original missing path.
    assert new_path != "assets/missing.png"
    assert (tmp_path / new_path).exists() or Path(new_path).exists()


def test_rewrite_config_resolves_existing_relative_paths_to_absolute(tmp_path):
    """The renderer writes the rewritten config to a temp dir before
    invoking the engine. Relative paths that resolved fine against the
    ORIGINAL config_dir would break against the temp dir, so we resolve
    them to absolute on the way through. (Bug fix from PR adding gif
    demo support.)"""
    real_png = tmp_path / "real.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(real_png)

    cfg = {
        "playlist": {"section": [{"widget": [{"type": "image", "path": "real.png"}]}]}
    }
    rewritten = rewrite_config_for_missing_assets(
        cfg,
        config_dir=tmp_path,
        placeholder_dir=tmp_path / "ph",
    )
    new_path = rewritten["playlist"]["section"][0]["widget"][0]["path"]
    # Path is now absolute and points at the original file (NOT a placeholder).
    assert Path(new_path).is_absolute()
    assert Path(new_path).resolve() == real_png.resolve()


def test_rewrite_config_substitutes_missing_gif(tmp_path):
    cfg = {
        "playlist": {
            "section": [{"widget": [{"type": "gif", "path": "assets/missing.gif"}]}]
        }
    }
    rewritten = rewrite_config_for_missing_assets(
        cfg,
        config_dir=tmp_path,
        placeholder_dir=tmp_path / "ph",
    )
    new_path = rewritten["playlist"]["section"][0]["widget"][0]["path"]
    assert new_path != "assets/missing.gif"
    # Verify the file actually got created
    full_path = (
        (tmp_path / new_path) if not Path(new_path).is_absolute() else Path(new_path)
    )
    assert full_path.exists()

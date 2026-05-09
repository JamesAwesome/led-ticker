"""Smoke test for the gif renderer CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure tools.render_demo is importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from PIL import Image  # noqa: E402

_RENDERER = _REPO_ROOT / "tools" / "render_demo" / "render.py"


_MINIMAL_CONFIG = """\
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 2.0

# Rainbow font_color produces per-tick color changes so successive
# captured frames are distinct (the GIF encoder collapses identical
# consecutive frames to one entry, which would defeat the multi-
# frame assertion below).
[[playlist.section.widget]]
type = "message"
text = "Hi"
font_color = "rainbow"
"""


def test_renderer_produces_a_gif_for_a_minimal_config(tmp_path):
    cfg = tmp_path / "demo.toml"
    cfg.write_text(_MINIMAL_CONFIG)
    out = tmp_path / "out.gif"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(_RENDERER),
            str(cfg),
            "-o",
            str(out),
            "--duration",
            "1",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )

    assert (
        result.returncode == 0
    ), f"renderer failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert out.exists()

    img = Image.open(out)
    # Native panel is 160x16; default upscale is 4 -> 640x64.
    assert img.size == (640, 64)
    # Multi-frame gif (1 sec at 20fps ~= 20 frames; tolerate 18-22).
    n = 0
    img.seek(0)
    while True:
        n += 1
        try:
            img.seek(img.tell() + 1)
        except EOFError:
            break
    assert 15 <= n <= 25, f"expected ~20 frames, got {n}"


def test_renderer_substitutes_placeholder_for_missing_image(tmp_path):
    cfg = tmp_path / "demo.toml"
    cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 0.5

[[playlist.section.widget]]
type = "image"
path = "assets/does-not-exist.png"
fit = "pillarbox"
hold_seconds = 0.5
""")
    out = tmp_path / "out.gif"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(_RENDERER),
            str(cfg),
            "-o",
            str(out),
            "--duration",
            "1",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )

    assert (
        result.returncode == 0
    ), f"renderer failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert out.exists()

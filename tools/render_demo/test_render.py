"""Smoke test for the gif renderer CLI."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Ensure tools.render_demo is importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "stubs"))
sys.path.insert(0, str(_REPO_ROOT))

import pytest  # noqa: E402

pytest.importorskip("tomli_w")

from PIL import Image  # noqa: E402

_RENDERER = _REPO_ROOT / "tools" / "render_demo" / "render.py"


_MINIMAL_CONFIG = """\
[display]
rows = 16
cols = 32
chain_length = 5
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

    assert result.returncode == 0, (
        f"renderer failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
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
chain_length = 5
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
hold_time = 0.5
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

    assert result.returncode == 0, (
        f"renderer failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert out.exists()


_STATIC_HOLD_CONFIG = """\
[display]
rows = 16
cols = 32
chain_length = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 2.0

# Constant color — successive captured frames are byte-identical, so
# imageio.mimsave's silent dedupe path triggers. With the duration-
# preserving encoder the output gif still plays for ~2 sec; without
# it, identical frames collapse to a single 50 ms frame and the gif
# is ~40x shorter than the engine's wall-clock intent.
[[playlist.section.widget]]
type = "message"
text = "Hi"
font_color = [255, 255, 255]
"""


def test_renderer_preserves_engine_wallclock_when_frames_repeat(tmp_path):
    cfg = tmp_path / "demo.toml"
    cfg.write_text(_STATIC_HOLD_CONFIG)
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
            "2",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )

    assert result.returncode == 0, (
        f"renderer failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )

    img = Image.open(out)
    total_ms = 0
    for i in range(img.n_frames):
        img.seek(i)
        total_ms += img.info.get("duration", 0)
    # The dedupe-with-duration encoder preserves engine wall-clock in
    # the output gif regardless of how many distinct frames were
    # captured. Without the fix, identical frames collapse and total
    # playback is < 100 ms. Tolerate 1.0-2.5 s to cover renderer
    # capture-overhead jitter.
    total_s = total_ms / 1000
    assert 1.0 <= total_s <= 2.5, f"expected gif playback ~1.5-2.0s, got {total_s:.2f}s"


# Static-fast-path tripwire. A widget that hits `_play_with_text`'s
# static fast path (image widget at hold_time with no scrolling
# text and no animation) only triggers ONE SwapOnVSync, then sleeps
# for the full hold. Before the timestamp-based encoder, the lone
# captured frame got tick_ms (50ms) as its duration regardless of
# how long the engine intended to hold. Now: the encoder credits
# the frame with the time between its swap and engine cancellation.
_STATIC_FAST_PATH_CONFIG = """\
[display]
rows = 16
cols = 32
chain_length = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "Hi"
font_color = [255, 255, 255]
"""


def test_renderer_static_fast_path_credits_single_frame_with_hold(tmp_path):
    """Single-swap static-fast-path renders should encode the FULL
    engine hold in the gif duration, not just one tick_ms.

    Pre-fix: lone captured frame → durations = [50 ms] → 0.05 sec
    output gif (visually fine for a still image, but metadata wrong).

    Post-fix: lone captured frame → durations = [end_time - swap_t]
    → ~hold_time output gif.
    """
    cfg = tmp_path / "demo.toml"
    cfg.write_text(_STATIC_FAST_PATH_CONFIG)
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
            "3",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"renderer failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )

    img = Image.open(out)
    total_ms = 0
    for i in range(img.n_frames):
        img.seek(i)
        total_ms += img.info.get("duration", 0)
    total_s = total_ms / 1000
    # Pre-fix this would be ~0.05s. Post-fix: must be at least 1s
    # (the engine's hold runs to completion within the wall-clock cap).
    assert total_s >= 1.0, (
        f"expected single-frame static gif to encode the engine's hold "
        f"(>= 1.0s), got {total_s:.2f}s — pre-fix bug returned"
    )


# ---------------------------------------------------------------------------
# Tripwire: render tool must honor the demo's <config_dir>/fonts/ directory.
#
# Root cause guarded against: render.py patched app_mod._configure_user_font_dir
# but run.py imports _configure_user_font_dir via a module-local binding
# (``from led_ticker.app.factories import _configure_user_font_dir``), so
# run.py's call at line 436 hit the UNPATCHED original and re-anchored the
# font dir to the temp-dir config copy (no fonts/).  A custom-font widget
# then silently fell back and rendered blank.
# ---------------------------------------------------------------------------

_ATKINSON_FONT_NAME = "AtkinsonHyperlegible-Bold.ttf"
# Committed OFL test fixture (NOT the gitignored docs-demo font) so this
# regression guard actually runs in CI instead of skipping. See fixtures/OFL.txt.
_FONT_SRC = Path(__file__).parent / "fixtures" / _ATKINSON_FONT_NAME

_CUSTOM_FONT_CONFIG = """\
[display]
rows = 16
cols = 32
chain_length = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 0.4

[[playlist.section.widget]]
type = "message"
text = "AB"
font = "AtkinsonHyperlegible-Bold"
font_size = 16
"""


def test_render_honors_user_font_dir(tmp_path: Path) -> None:
    """Regression: the render tool must keep the demo's <config_dir>/fonts/ active.

    Before the run_mod._configure_user_font_dir fix, run.py's local binding
    re-anchored the font dir to the temp config copy (no fonts/), so a custom
    font silently fell back / rendered blank.  This renders a hires-font widget
    and asserts lit pixels appear in the output gif.
    """
    assert _FONT_SRC.exists(), f"committed test font fixture missing: {_FONT_SRC}"

    pytest.importorskip("tomli_w")
    from tools.render_demo.render import render  # noqa: PLC0415

    # Place the config in its own subdir so the sibling ``fonts/`` dir is
    # unambiguously <cfg_dir>/fonts/ — the path render() passes as
    # original_cfg_path so _configure_user_font_dir anchors there.
    cfg_dir = tmp_path / "cfg"
    fonts_dir = cfg_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    shutil.copy(_FONT_SRC, fonts_dir / _FONT_SRC.name)

    cfg = cfg_dir / "c.toml"
    cfg.write_text(_CUSTOM_FONT_CONFIG)

    out = tmp_path / "out.gif"
    render(cfg, out, duration=0.4, upscale=1)

    assert out.exists(), "Renderer produced no output file"

    img = Image.open(out)
    # Check every frame for at least one non-black pixel.  A blank render
    # (font dir not honoured → fallback → no glyphs) produces all-black frames.
    # getbbox() returns None for an all-black image and a bounding box otherwise.
    has_lit_pixel = False
    for frame_idx in range(img.n_frames):
        img.seek(frame_idx)
        if img.convert("RGB").getbbox() is not None:
            has_lit_pixel = True
            break

    assert has_lit_pixel, (
        "custom-font widget rendered all-black — user font dir was not honoured "
        "(run_mod._configure_user_font_dir binding re-anchored font dir to temp copy)"
    )

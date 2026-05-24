"""Tripwire: render output for an animated widget must produce a
multi-frame gif with visually distinct first and last frames.

Catches two regression classes:
  - Engine produces 1 frame total (would mean the engine isn't
    swapping the canvas, e.g. a tick-loop regression)
  - Engine swaps but every frame is identical (would mean the widget
    isn't advancing its animated state, OR imageio mis-encodes).

Fixture is a minimal synthetic message widget with
`font_color = "rainbow"` — per-character hue advances every 50 ms
engine tick, which produces visually distinct canvases without
needing network / API keys / live data. If this test ever fails,
something between RecordingMatrix.SwapOnVSync and
imageio.mimsave's frame ordering broke.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# Make rgbmatrix test stub available before importing led_ticker, and put
# the repo root on sys.path so `tools.render_demo.render` resolves when
# pytest is invoked directly against this file.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "stubs"))
sys.path.insert(0, str(_REPO_ROOT))

import pytest  # noqa: E402

pytest.importorskip("tomli_w")
pytest.importorskip("imageio")

from PIL import Image  # noqa: E402
from tools.render_demo.render import render  # noqa: E402

FIXTURE_TOML = """
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 4.0

[[playlist.section.widget]]
type = "message"
text = "Hello"
font_color = "rainbow"
"""


def test_render_animated_widget_produces_multiframe_gif(tmp_path: Path) -> None:
    """A rainbow-text message rendered for 4 sec must produce a
    multi-frame gif (rainbow hue cycles every 50 ms tick → 80 distinct
    frames in 4 sec; some get deduped if identical, but at least
    several distinct frames remain)."""
    cfg = tmp_path / "fixture.toml"
    cfg.write_text(FIXTURE_TOML)
    out = tmp_path / "out.gif"

    render(cfg, out, duration=4.0, upscale=1, fps=20)

    assert out.exists(), "Renderer produced no output file"
    im = Image.open(out)
    assert im.n_frames > 1, (
        f"Renderer produced single-frame gif ({out.stat().st_size} bytes). "
        f"Either the engine isn't swapping (RecordingMatrix.frames empty) "
        f"or every captured frame is byte-identical (widget isn't varying "
        f"its canvas, OR imageio dedupe collapsed them). See "
        f"tools/render_demo/test_renderer_multiframe.py docstring for the "
        f"two regression classes this test guards against."
    )


def test_render_first_and_last_frames_differ(tmp_path: Path) -> None:
    """Stronger assertion: first-frame and last-frame of the rendered
    gif must differ. Catches the case where n_frames > 1 but the
    encoder writes a sequence like [A, A, A, A] that PIL still reports
    as multi-frame because of how the gif structure is stored."""
    cfg = tmp_path / "fixture.toml"
    cfg.write_text(FIXTURE_TOML)
    out = tmp_path / "out.gif"

    render(cfg, out, duration=4.0, upscale=1, fps=20)

    im = Image.open(out)
    im.seek(0)
    first = hashlib.md5(im.convert("RGB").tobytes()).hexdigest()
    im.seek(im.n_frames - 1)
    last = hashlib.md5(im.convert("RGB").tobytes()).hexdigest()

    assert first != last, (
        f"First and last frames of rendered gif have identical content "
        f"(both hash to {first[:8]}). The widget isn't varying its canvas "
        f"across the {im.n_frames}-frame capture. Confirm the rainbow "
        f"text animation is working: drop into a Python REPL and call "
        f"`message.draw()` at successive frame counts on a TickerMessage "
        f"with font_color='rainbow' — colors should cycle."
    )

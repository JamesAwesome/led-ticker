"""Proof that a plugin can drive the hi-res transition renderer with its
own sprite, with no entry in the core HIRES_REGISTRY (P2)."""

from PIL import Image

# The exact symbols a plugin author imports — must be on the public surface.
from led_ticker.plugin import HiresSpec, ScaledCanvas, render_hires_frame
from led_ticker.transitions._hires_registry import HIRES_REGISTRY


class _StubCanvas:
    def __init__(self, w, h):
        self.width = w
        self.height = h
        self.pixels = {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(x, y)] = (r, g, b)


class _StubWidget:
    def draw(self, canvas, cursor_pos=0, **kwargs):
        return canvas, 0


def _make_sprite(path):
    # bright green so painted sprite pixels are unmistakably non-black
    frames = [Image.new("RGBA", (8, 8), (0, 255, 0, 255)) for _ in range(2)]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=50, loop=0)
    return path


def test_public_surface_exposes_hires_symbols():
    # The import above is the real assertion; this pins the contract.
    assert HiresSpec is not None
    assert callable(render_hires_frame)


def test_plugin_sprite_renders_hires_without_registry_entry(tmp_path):
    sprite = _make_sprite(tmp_path / "plugin_sprite.gif")
    spec = HiresSpec(sprite_path=sprite, flip_horizontal=False, trail="black")
    assert "myplugin.zoom" not in HIRES_REGISTRY  # never registered in core

    real = _StubCanvas(64, 32)
    canvas = ScaledCanvas(real, scale=4, content_height=8)

    # mid-transition so the sprite is on-panel
    result = render_hires_frame(0.5, canvas, _StubWidget(), _StubWidget(), spec)
    assert result is not None
    # The hi-res path paints to the REAL canvas; a black trail + green
    # sprite means non-black pixels were written at physical resolution.
    assert real.pixels, "render_hires_frame painted nothing"
    assert any(rgb == (0, 255, 0) for rgb in real.pixels.values()), (
        "expected the plugin sprite's green pixels on the real canvas"
    )

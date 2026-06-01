import pytest

from led_ticker import _plugin_loader as L
from led_ticker.app.coercion import _coerce_animation


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_builtin_typewriter_still_coerces():
    anim = _coerce_animation("typewriter")
    assert hasattr(anim, "frame_for")
    anim2 = _coerce_animation({"style": "typewriter", "frames_per_char": 6})
    assert hasattr(anim2, "frame_for")


def test_plugin_animation_coerces(tmp_path):
    src = '''
import attrs
from led_ticker.plugin import Animation

@attrs.define
class Scramble:
    speed: int = 2
    def frame_for(self, frame, full_text, canvas_width, text_width):
        from led_ticker.animations import AnimationFrame
        return AnimationFrame(visible_text=full_text)

def register(api):
    api.animation("scramble")(Scramble)
'''
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)
    anim = _coerce_animation({"style": "acme.scramble", "speed": 4})
    assert hasattr(anim, "frame_for")

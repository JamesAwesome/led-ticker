import pytest

from led_ticker import _plugin_loader as L
from led_ticker.app.coercion import _coerce_border


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


@pytest.mark.parametrize(
    "spec",
    [
        "rainbow",
        "color_cycle",
        "lightbulbs",
        [255, 0, 0],
        {"style": "rainbow", "speed": 4, "thickness": 2},
        {"style": "constant", "color": [0, 255, 0], "thickness": 1},
    ],
)
def test_builtin_borders_still_coerce(spec):
    b = _coerce_border(spec)
    assert hasattr(b, "paint")


def test_color_cycle_border_hue_range_from_to():
    b = _coerce_border(
        {
            "style": "color_cycle",
            "from": [255, 176, 240],
            "to": [189, 169, 234],
            "speed": 3,
        }
    )
    assert hasattr(b, "paint")


def test_color_cycle_border_speed_zero_rejected():
    with pytest.raises(ValueError, match="speed=0|static color"):
        _coerce_border({"style": "color_cycle", "speed": 0})


def test_plugin_border_coerces(tmp_path):
    src = '''
import attrs
from led_ticker.plugin import BorderEffectBase

@attrs.define
class Neon(BorderEffectBase):
    frame_invariant = False
    speed: int = 3
    def paint(self, canvas, frame_count):
        return None

def register(api):
    api.border("neon")(Neon)
'''
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)
    b = _coerce_border({"style": "acme.neon", "speed": 6})
    assert hasattr(b, "paint")


def test_plugin_border_resolves_via_string_shorthand(tmp_path):
    # border = "acme.neon" (string form) must resolve a plugin border, matching
    # the animation string-form behavior.
    import textwrap

    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import BorderEffectBase
            def register(api):
                @api.border("neon")
                class Neon(BorderEffectBase):
                    frame_invariant = False
                    def paint(self, canvas, frame_count):
                        return None
            """
        )
    )
    L.load_plugins(pdir, entry_points_enabled=False)
    border = _coerce_border("acme.neon")  # string form
    assert border is not None
    assert hasattr(border, "paint")

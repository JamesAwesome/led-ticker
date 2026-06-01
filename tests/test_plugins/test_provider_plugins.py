import pytest

from led_ticker import _plugin_loader as L
from led_ticker.app.coercion import _coerce_color_provider


@pytest.mark.parametrize(
    "spec",
    [
        "rainbow",
        "color_cycle",
        "random",
        {"style": "rainbow", "speed": 5, "char_offset": 3},
        {"style": "color_cycle", "speed": 2},
        {"style": "gradient", "from": [255, 0, 0], "to": [0, 0, 255]},
        {"style": "shimmer", "base": [255, 255, 255], "shimmer": [0, 200, 255]},
    ],
)
def test_builtin_providers_still_coerce(spec):
    provider = _coerce_color_provider(spec)
    assert hasattr(provider, "color_for")


def test_unknown_style_lists_available():
    with pytest.raises(ValueError, match="unknown font_color style"):
        _coerce_color_provider({"style": "nope"})


@pytest.fixture
def _clean_plugins():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_plugin_color_provider_coerces(_clean_plugins, tmp_path):
    src = '''
import attrs
from led_ticker.plugin import ColorProviderBase

@attrs.define
class Fire(ColorProviderBase):
    frame_invariant = True
    intensity: int = 5
    def color_for(self, frame, char_index, total_chars):
        from led_ticker._compat import require_graphics
        return require_graphics().Color(self.intensity, 0, 0)

def register(api):
    api.color_provider("fire")(Fire)
'''
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)

    from led_ticker.app.coercion import _coerce_color_provider

    provider = _coerce_color_provider({"style": "acme.fire", "intensity": 9})
    assert provider.color_for(0, 0, 1) is not None

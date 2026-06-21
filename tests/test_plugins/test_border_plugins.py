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
            "from": [255, 92, 38],
            "to": [255, 183, 3],
            "speed": 3,
        }
    )
    assert hasattr(b, "paint")


def test_color_cycle_border_speed_zero_rejected():
    with pytest.raises(ValueError, match="speed=0|static color"):
        _coerce_border({"style": "color_cycle", "speed": 0})


def test_plugin_border_coerces(tmp_path):
    src = """
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
"""
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


async def test_plugin_widget_declaring_border_field_can_host_border(tmp_path):
    import textwrap

    from led_ticker import _plugin_loader as L
    from led_ticker.app.factories import validate_widget_cfg

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            from led_ticker.plugin import BorderEffectBase
            def register(api):
                @api.border("neon")
                class Neon(BorderEffectBase):
                    frame_invariant = False
                    def paint(self, canvas, frame_count):
                        return None
                @api.widget("banner")
                @attrs.define
                class Banner:
                    text: str = ""
                    border: object = None
                    def draw(self, canvas, cursor_pos=0, **kw):
                        return canvas, cursor_pos
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        cfg = {"type": "acme.banner", "border": {"style": "acme.neon"}}
        await validate_widget_cfg(cfg, session=None)  # must NOT raise
    finally:
        L.reset_plugins()


async def test_plugin_widget_without_border_field_rejects_border(tmp_path):
    import textwrap

    import pytest

    from led_ticker import _plugin_loader as L
    from led_ticker.app.factories import validate_widget_cfg

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            def register(api):
                @api.widget("plain")
                @attrs.define
                class Plain:
                    text: str = ""
                    def draw(self, canvas, cursor_pos=0, **kw):
                        return canvas, cursor_pos
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        with pytest.raises(ValueError, match="border is only valid"):
            await validate_widget_cfg(
                {"type": "acme.plain", "border": {"style": "x"}}, session=None
            )
    finally:
        L.reset_plugins()

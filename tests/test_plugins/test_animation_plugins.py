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
    src = """
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
"""
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)
    anim = _coerce_animation({"style": "acme.scramble", "speed": 4})
    assert hasattr(anim, "frame_for")


def test_animationframe_is_public():
    from led_ticker.plugin import AnimationFrame

    assert AnimationFrame is not None


async def test_plugin_widget_declaring_animation_field_can_host_animation(tmp_path):
    import textwrap

    from led_ticker import _plugin_loader as L
    from led_ticker.app.factories import validate_widget_cfg

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            from led_ticker.plugin import AnimationFrame
            def register(api):
                @api.animation("scramble")
                class Scramble:
                    def frame_for(self, frame, full_text, canvas_width, text_width):
                        return AnimationFrame(visible_text=full_text)
                @api.widget("banner")
                @attrs.define
                class Banner:
                    text: str = ""
                    animation: object = None
                    def draw(self, canvas, cursor_pos=0, **kw):
                        return canvas, cursor_pos
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        cfg = {"type": "acme.banner", "animation": {"style": "acme.scramble"}}
        await validate_widget_cfg(cfg, session=None)  # must NOT raise
    finally:
        L.reset_plugins()


async def test_plugin_widget_without_animation_field_rejects_animation(tmp_path):
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
        with pytest.raises(ValueError, match="animation is only valid"):
            await validate_widget_cfg(
                {"type": "acme.plain", "animation": {"style": "x"}}, session=None
            )
    finally:
        L.reset_plugins()

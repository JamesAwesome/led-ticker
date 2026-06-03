import pytest

from led_ticker.plugin import API_VERSION, PluginAPI


def test_widget_decorator_buffers_under_namespace():
    api = PluginAPI("acme")

    @api.widget("clock")
    class Clock:
        pass

    assert api._widgets == {"acme.clock": Clock}
    assert api._transitions == {}


def test_transition_decorator_buffers_under_namespace():
    api = PluginAPI("acme")

    @api.transition("swoosh")
    class Swoosh:
        pass

    assert api._transitions == {"acme.swoosh": Swoosh}


def test_decorator_returns_the_class_unchanged():
    api = PluginAPI("acme")

    class W:
        pass

    assert api.widget("w")(W) is W


def test_api_version_is_major_minor_tuple():
    assert isinstance(API_VERSION, tuple) and len(API_VERSION) == 2


def test_public_surface_exports_protocols():
    import led_ticker.plugin as p

    for name in ("PluginAPI", "API_VERSION", "Widget", "Transition", "Canvas",
                 "spawn_tracked"):
        assert hasattr(p, name), f"missing public export: {name}"


def test_make_color_builds_a_color():
    from led_ticker.plugin import make_color

    c = make_color(255, 0, 0)
    assert c is not None


def test_emoji_and_hires_emoji_buffer_under_namespace():
    api = PluginAPI("acme")
    api.emoji("spark", [(0, 0, 255, 0, 0)])
    api.hires_emoji("glow", object())  # API does not validate sprite shape
    assert api._buffers["emojis"] == {"acme.spark": [(0, 0, 255, 0, 0)]}
    assert "acme.glow" in api._buffers["hires_emojis"]


def test_font_buffers_resolved_absolute_path(tmp_path):
    api = PluginAPI("acme", root=tmp_path)
    api.font("Brand", "fonts/Brand.ttf")
    stored = api._buffers["fonts"]["acme.Brand"]
    assert stored.is_absolute()
    assert stored == (tmp_path / "fonts/Brand.ttf").resolve()


def test_font_without_root_raises():
    api = PluginAPI("acme")  # root defaults to None
    with pytest.raises(ValueError, match="needs a plugin root"):
        api.font("Brand", "fonts/Brand.ttf")


def test_public_surface_exports_emoji_and_font_helpers():
    import led_ticker.plugin as p

    for name in (
        "PixelData",
        "HiResEmoji",
        "draw_emoji_at",
        "measure_emoji_at",
        "get_text_width",
        "compute_baseline",
        "colors",
    ):
        assert hasattr(p, name), f"missing public export: {name}"


def test_overlay_buffers_into_overlays_list():
    api = PluginAPI("acme")

    def paint(canvas):
        pass

    api.overlay(paint)
    assert api._overlays == [paint]


def test_on_startup_and_on_shutdown_buffer_into_lists():
    api = PluginAPI("acme")

    def boot(ctx):
        pass

    async def teardown():
        pass

    api.on_startup(boot)
    api.on_shutdown(teardown)
    assert api._startup_hooks == [boot]
    assert api._shutdown_hooks == [teardown]


def test_startup_context_is_exported_and_constructible():
    from led_ticker.plugin import StartupContext

    ctx = StartupContext(frame="F", session="S", config="C")
    assert (ctx.frame, ctx.session, ctx.config) == ("F", "S", "C")


def test_startup_context_is_frozen():
    import dataclasses

    from led_ticker.plugin import StartupContext

    ctx = StartupContext(frame="F", session="S", config="C")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.frame = "mutated"


def test_hook_lists_are_independent_of_buffers():
    # Hooks are NOT registry surfaces — they must not appear in _buffers.
    api = PluginAPI("acme")
    assert "overlays" not in api._buffers
    assert "startup_hooks" not in api._buffers
    assert "shutdown_hooks" not in api._buffers


def test_font_accessor_and_draw_text_are_exported():
    import led_ticker.plugin as p

    for name in ("resolve_font", "Font", "HiresFont", "draw_text"):
        assert hasattr(p, name), f"missing public export: {name}"
        assert name in p.__all__, f"{name} missing from __all__"

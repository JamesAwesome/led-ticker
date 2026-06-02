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
    assert api._buffers["fonts"]["acme.Brand"] == (tmp_path / "fonts/Brand.ttf").resolve()


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

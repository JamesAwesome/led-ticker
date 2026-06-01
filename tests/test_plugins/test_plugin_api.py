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

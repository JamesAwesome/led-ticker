def test_container_monitor_surface_is_exported():
    import led_ticker.plugin as p

    for name in ("Container", "Updatable", "run_monitor_loop"):
        assert hasattr(p, name), f"missing public export: {name}"
        assert name in p.__all__


def test_a_plugin_container_widget_expands_via_the_engine():
    # A widget with feed_stories is treated as a Container by the engine's
    # expansion — prove the public Container protocol matches what the engine
    # isinstance-checks.
    from led_ticker.plugin import Container
    from led_ticker.ticker import _expand_sources

    class Feed:
        def __init__(self):
            self.feed_stories = ["a", "b"]

    f = Feed()
    assert isinstance(f, Container)
    assert _expand_sources([f, "x"]) == ["a", "b", "x"]


def test_message_building_blocks_are_exported():
    from led_ticker.plugin import SegmentMessage, TwoRowMessage, Widget, make_color

    seg = SegmentMessage([("Hi", make_color(255, 255, 255))], center=True)
    two = TwoRowMessage(top_text="A", bottom_text="B")
    # both satisfy the Widget protocol (have draw)
    assert isinstance(seg, Widget)
    assert isinstance(two, Widget)


def test_plugin_monitor_widget_loads_and_is_a_container(tmp_path):
    import textwrap

    from led_ticker import _plugin_loader as L
    from led_ticker.plugin import Container
    from led_ticker.widgets import get_widget_class

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            from led_ticker.plugin import (
                SegmentMessage, make_color, run_monitor_loop, spawn_tracked,
            )

            def register(api):
                @api.widget("feed")
                @attrs.define
                class Feed:
                    feed_stories: list = attrs.field(init=False, factory=list)
                    async def update(self):
                        self.feed_stories = [
                            SegmentMessage([("hi", make_color(255, 255, 255))])
                        ]
                    @classmethod
                    async def start(cls, session, update_interval=300, **kw):
                        w = cls(**kw)
                        await w.update()
                        spawn_tracked(run_monitor_loop(w, update_interval))
                        return w
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        cls = get_widget_class("acme.feed")
        assert cls is not None
        inst = cls()
        assert isinstance(inst, Container)
    finally:
        L.reset_plugins()

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

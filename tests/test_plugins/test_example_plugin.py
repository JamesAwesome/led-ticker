from pathlib import Path

from led_ticker import _plugin_loader as L

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "plugins"


def test_example_plugin_registers_every_surface_and_hook():
    L.reset_plugins()
    try:
        result = L.load_plugins(EXAMPLES, entry_points_enabled=False)
        assert not result.failed, result.failed
        info = next(i for i in result.loaded if i.namespace == "acme")
        for surface in (
            "widgets",
            "transitions",
            "color_providers",
            "animations",
            "borders",
            "easing",
            "emojis",
            "hires_emojis",
            "fonts",
        ):
            assert info.counts.get(surface, 0) >= 1, f"missing {surface}: {info.counts}"
        assert any(ns == "acme" for ns, _ in result.overlays)
        assert any(ns == "acme" for ns, _ in result.startup_hooks)
        assert any(ns == "acme" for ns, _ in result.shutdown_hooks)
    finally:
        L.reset_plugins()


async def test_example_clock_accepts_font_color():
    from led_ticker.app.factories import validate_widget_cfg

    L.reset_plugins()
    try:
        L.load_plugins(EXAMPLES, entry_points_enabled=False)
        # acme.clock declares a font_color field, so the standard color-provider
        # knob (here the example's own acme.fire provider) is accepted.
        cfg = {"type": "acme.clock", "font_color": {"style": "acme.fire"}}
        await validate_widget_cfg(cfg, session=None)  # must not raise
    finally:
        L.reset_plugins()


def test_example_plugin_contributions_are_usable():
    # Test-only internal imports (resolve_font/get_widget_class). A plugin
    # itself imports ONLY from led_ticker.plugin — see acme/__init__.py.
    from led_ticker.fonts import resolve_font
    from led_ticker.widgets import get_widget_class

    L.reset_plugins()
    try:
        L.load_plugins(EXAMPLES, entry_points_enabled=False)
        assert get_widget_class("acme.clock") is not None
        font = resolve_font("acme.Brand", size=16)
        assert font.__class__.__name__ == "HiresFont"
    finally:
        L.reset_plugins()


def test_example_clock_actually_renders_text():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    from led_ticker.widgets import get_widget_class

    L.reset_plugins()
    try:
        L.load_plugins(EXAMPLES, entry_points_enabled=False)
        cls = get_widget_class("acme.clock")
        widget = cls(text="hi")
        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 4
        opts.parallel = 1
        canvas = RGBMatrix(options=opts).CreateFrameCanvas()
        _, end_x = widget.draw(canvas, cursor_pos=0)
        assert end_x > 0  # cursor advanced -> text was drawn
    finally:
        L.reset_plugins()

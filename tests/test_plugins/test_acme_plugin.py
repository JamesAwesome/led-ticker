from pathlib import Path

from led_ticker import _plugin_loader as L

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "plugins"


def test_example_swoosh_accepts_threshold_config():
    from led_ticker.app.factories import _build_trans_obj
    from led_ticker.config import TransitionConfig, _parse_transition

    L.reset_plugins()
    try:
        L.load_plugins(EXAMPLES, entry_points_enabled=False)
        obj = _build_trans_obj(
            _parse_transition(
                {"type": "acme.swoosh", "threshold": 0.3}, TransitionConfig()
            )
        )
        assert obj.threshold == 0.3
    finally:
        L.reset_plugins()


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


def test_example_swoosh_renders_to_canvas():
    """Guards the transition protocol: `frame_at` must DRAW the chosen frame
    onto `canvas` (the engine ignores its return value, mirroring the built-in
    `Cut.frame_at`). A transition that only RETURNED a frame would ship blank
    frames — this test would catch that regression in the reference plugin.
    """
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    from led_ticker.transitions import get_transition_class

    class _Frame:
        """Stub presenter that paints a recognizable pixel and records draws."""

        def __init__(self, color):
            self.color = color
            self.drawn = False

        def draw(self, canvas, cursor_pos=0):
            self.drawn = True
            canvas.SetPixel(0, 0, *self.color)
            return canvas, 0

    def _canvas():
        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 1
        opts.parallel = 1
        return RGBMatrix(options=opts).CreateFrameCanvas()

    L.reset_plugins()
    try:
        L.load_plugins(EXAMPLES, entry_points_enabled=False)
        swoosh = get_transition_class("acme.swoosh")()

        # t >= 0.5 -> the INCOMING frame is drawn to the canvas.
        canvas = _canvas()
        out_frame = _Frame((1, 2, 3))
        in_frame = _Frame((4, 5, 6))
        swoosh.frame_at(0.9, canvas, out_frame, in_frame)
        assert in_frame.drawn and not out_frame.drawn
        assert canvas.get_pixel(0, 0) == (4, 5, 6)  # rendered TO canvas

        # t < 0.5 -> the OUTGOING frame is drawn to the canvas.
        canvas = _canvas()
        out_frame = _Frame((1, 2, 3))
        in_frame = _Frame((4, 5, 6))
        swoosh.frame_at(0.1, canvas, out_frame, in_frame)
        assert out_frame.drawn and not in_frame.drawn
        assert canvas.get_pixel(0, 0) == (1, 2, 3)
    finally:
        L.reset_plugins()

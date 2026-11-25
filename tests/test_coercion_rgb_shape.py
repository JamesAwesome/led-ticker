"""`rgb_shape_error` / `rgb_list_shape_error`: the ONE colour-shape predicate
shared by validate rule 74 (transition slots) and, in the stacked random/auto
follow-up, the transition factory and rule 73 (pool entries). A shape that
passes here is safe to hand to `SetPixel`; anything else is a message, never
an exception."""

import pytest

from led_ticker.app.coercion import rgb_list_shape_error, rgb_shape_error


@pytest.mark.parametrize("good", [[255, 0, 0], (255, 0, 0), [0, 0, 0], (1, 2, 3)])
def test_rgb_shape_accepts_three_ints_list_or_tuple(good):
    assert rgb_shape_error(good) is None


@pytest.mark.parametrize(
    "bad",
    [
        "red",
        ("r", "e", "d"),
        [255, 0],
        [255, 0, 0, 0],
        [255.0, 0, 0],
        [True, False, True],
        [256, 0, 0],
        [-1, 0, 0],
        None,
        255,
        {"r": 1, "g": 2, "b": 3},
    ],
)
def test_rgb_shape_refuses_bad_shapes_with_a_message(bad):
    msg = rgb_shape_error(bad)
    assert isinstance(msg, str) and "0-255" in msg and repr(bad)[:8] in msg


@pytest.mark.parametrize("good", [[[1, 2, 3], [4, 5, 6]], ([255, 0, 0],), [(0, 0, 0)]])
def test_rgb_list_shape_accepts_lists_of_rgb(good):
    assert rgb_list_shape_error(good) is None


@pytest.mark.parametrize(
    "bad", [[], [[1, 2]], [1, 2, 3], "red", [[1, 2, 3], "red"], None]
)
def test_rgb_list_shape_refuses_bad_shapes_with_a_message(bad):
    msg = rgb_list_shape_error(bad)
    assert isinstance(msg, str) and "[r, g, b]" in msg


def test_rgb_shape_error_lives_in_colors_and_is_reexported():
    """Home is the leaf `led_ticker.colors` so a transition module can import
    it without a cycle through `led_ticker.app`; `app.coercion` re-exports."""
    from led_ticker import colors
    from led_ticker.app import coercion

    assert coercion.rgb_shape_error is colors.rgb_shape_error


# ---------------------------------------------------------------------------
# Runtime twin of validate rule 76: a bg key that is set but is NOT [r, g, b]
# must raise at config-load, not reach `reset_canvas` as a bare str/list and
# kill the render loop on the first hold.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["bg_color", "top_bg_color", "bottom_bg_color"])
@pytest.mark.parametrize("value", ["red", [255, 0], [255, 0, 0, 0], 255])
def test_coerce_widget_colors_rejects_non_triple_bg(key, value):
    from led_ticker.app.coercion import _coerce_widget_colors

    cfg = {"type": "message", "text": "hi", key: value}
    with pytest.raises(ValueError, match=key):
        _coerce_widget_colors(cfg)


@pytest.mark.parametrize("key", ["bg_color", "top_bg_color", "bottom_bg_color"])
def test_coerce_widget_colors_passes_through_color_and_none(key):
    from led_ticker._compat import require_graphics
    from led_ticker.app.coercion import _coerce_widget_colors

    graphics = require_graphics()
    already = graphics.Color(1, 2, 3)
    cfg = {"type": "message", key: already}
    _coerce_widget_colors(cfg)
    assert cfg[key] is already
    cfg = {"type": "message", key: None}
    _coerce_widget_colors(cfg)
    assert cfg[key] is None


# ---------------------------------------------------------------------------
# Boot-time twin for the SECTION-level bg (`app.run._refuse_malformed_section_bg`).
# ---------------------------------------------------------------------------


class _Sec:
    def __init__(self, bg):
        self.bg_color = bg


class _Cfg:
    def __init__(self, *bgs):
        self.sections = [_Sec(b) for b in bgs]


@pytest.mark.parametrize("bad", [("r", "e", "d"), (255, 0), (300, 0, 0), (255.0, 0, 0)])
def test_refuse_malformed_section_bg_raises_naming_the_section(bad):
    from led_ticker.app.run import _refuse_malformed_section_bg

    with pytest.raises(ValueError, match=r"playlist\.section\[1\]\.bg_color"):
        _refuse_malformed_section_bg(_Cfg(None, bad))


def test_refuse_malformed_section_bg_passes_none_and_triples():
    from led_ticker.app.run import _refuse_malformed_section_bg

    _refuse_malformed_section_bg(_Cfg(None, (0, 0, 0), (255, 244, 214)))

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

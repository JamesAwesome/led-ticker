"""Tripwire: RANDOM_COLOR lives in app.py with the 8-color palette."""

from led_ticker import app, colors


def test_random_color_is_in_app_module():
    assert hasattr(app, "RANDOM_COLOR")


def test_random_color_not_in_colors_module():
    assert not hasattr(colors, "RANDOM_COLOR")


def test_random_color_cycles_eight_colors():
    cycle = app.RANDOM_COLOR
    seen = [next(cycle) for _ in range(16)]
    # 8-element cycle: index N and N+8 must match
    assert seen[0] == seen[8]
    assert seen[1] == seen[9]
    assert seen[7] == seen[15]
    # First 8 are distinct
    distinct = {(c.red, c.green, c.blue) for c in seen[:8]}
    assert len(distinct) == 8

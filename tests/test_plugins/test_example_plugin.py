"""Tripwire for the authoring-guide worked example (examples/plugins/example).

The plugin authoring guide's code blocks are excerpts of this plugin; this test
keeps the shipped example (and therefore the docs) honest against the API.
"""

import shutil
from pathlib import Path

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY, get_widget_class

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "plugins" / "example"


@pytest.fixture
def counter_cls(tmp_path):
    """Load examples/plugins/example into an isolated dir; yield the widget class."""
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False)
        assert "example" in {i.namespace for i in result.loaded}, result.failed
        yield get_widget_class("example.counter")
    finally:
        L.reset_plugins()


def test_example_counter_registers(counter_cls):
    assert "example.counter" in _WIDGET_REGISTRY
    assert counter_cls.__name__ == "Counter"


def test_validate_config_accepts_a_past_date(counter_cls):
    assert counter_cls.validate_config({"since": "2020-01-01"}) == []


def test_validate_config_rejects_bad_and_future_dates(counter_cls):
    assert counter_cls.validate_config({"since": "not-a-date"})  # non-empty error list
    assert counter_cls.validate_config({"since": "2999-01-01"})  # future → error
    assert counter_cls.validate_config({})  # missing → error


def test_draw_returns_canvas_and_end_x(counter_cls, canvas):
    w = counter_cls(since="2020-01-01", label="DAY")
    out, end_x = w.draw(canvas)
    assert out is canvas
    assert isinstance(end_x, int)


def test_bg_color_fills_the_canvas(counter_cls, canvas):
    from led_ticker.plugin import make_color

    counter_cls(since="2020-01-01", bg_color=make_color(10, 20, 30)).draw(canvas)
    canvas.Fill.assert_called_once_with(10, 20, 30)


def test_no_bg_color_leaves_canvas_unfilled(counter_cls, canvas):
    counter_cls(since="2020-01-01").draw(canvas)
    canvas.Fill.assert_not_called()

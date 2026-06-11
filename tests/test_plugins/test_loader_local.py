import pytest

from led_ticker import _plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY, get_widget_class

PLUGIN_SRC = """
from led_ticker.plugin import Widget

def register(api):
    @api.widget("clock")
    class Clock:
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            return canvas, cursor_pos
"""


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_local_py_file_namespaced_by_stem(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "myclock.py").write_text(PLUGIN_SRC)

    result = L.load_plugins(pdir, entry_points_enabled=False)

    assert "myclock.clock" in _WIDGET_REGISTRY
    assert get_widget_class("myclock.clock").__name__ == "Clock"
    assert [i.namespace for i in result.loaded] == ["myclock"]


def test_underscore_files_and_missing_dir_are_skipped(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "_helper.py").write_text("x = 1\n")
    res1 = L.load_plugins(pdir, entry_points_enabled=False)
    assert res1.loaded == []
    L.reset_plugins()
    res2 = L.load_plugins(tmp_path / "nope", entry_points_enabled=False)
    assert res2.loaded == [] and res2.failed == []


def test_import_error_in_plugin_is_isolated(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "broken.py").write_text("import this_module_does_not_exist\n")
    (pdir / "good.py").write_text(PLUGIN_SRC)
    result = L.load_plugins(pdir, entry_points_enabled=False)
    assert "good.clock" in _WIDGET_REGISTRY
    assert any(ns == "broken" for ns, _ in result.failed)

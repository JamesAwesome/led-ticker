import pytest

from led_ticker import _plugin_loader as L

PLUGIN_SRC = '''
def register(api):
    @api.widget("clock")
    class Clock:
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            return canvas, cursor_pos
'''


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_run_loads_plugins_from_config_dir(tmp_path):
    cfg_dir = tmp_path
    pdir = cfg_dir / "plugins"
    pdir.mkdir()
    (pdir / "myclock.py").write_text(PLUGIN_SRC)

    from led_ticker.app.run import _load_plugins_for_config

    result = _load_plugins_for_config(cfg_dir / "config.toml")
    from led_ticker.widgets import get_widget_class

    assert get_widget_class("myclock.clock").__name__ == "Clock"
    assert [i.namespace for i in result.loaded] == ["myclock"]

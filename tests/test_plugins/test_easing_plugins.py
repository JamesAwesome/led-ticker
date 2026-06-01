import pytest

from led_ticker import _plugin_loader as L
from led_ticker.transitions import EASING


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_plugin_easing_registers_namespaced(tmp_path):
    src = '''
def register(api):
    api.easing("snap", lambda p: p * p)
'''
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)
    assert "acme.snap" in EASING
    assert EASING["acme.snap"](0.5) == 0.25


def test_builtin_easing_untouched():
    assert "linear" in EASING and "ease_out" in EASING

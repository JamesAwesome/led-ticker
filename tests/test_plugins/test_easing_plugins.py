import pytest

from led_ticker import _plugin_loader as L
from led_ticker.transitions import EASING


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_plugin_easing_registers_namespaced(tmp_path):
    src = """
def register(api):
    api.easing("snap", lambda p: p * p)
"""
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(src)
    L.load_plugins(pdir, entry_points_enabled=False)
    assert "acme.snap" in EASING
    assert EASING["acme.snap"](0.5) == 0.25


def test_builtin_easing_untouched():
    assert "linear" in EASING and "ease_out" in EASING


def test_plugin_easing_validates_through_load_config(tmp_path):
    # End-to-end: a plugin easing must pass load_config's [transitions] easing
    # validation. This only works if plugins load BEFORE load_config — the
    # order run() now uses. (The per-surface test above only checks the registry
    # commit, which masked this.)
    from led_ticker.config import load_config

    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(
        'def register(api):\n    api.easing("snap", lambda p: p * p)\n'
    )
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[transitions]\ndefault="cut"\neasing="acme.snap"\n\n'
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    L.load_plugins(pdir, entry_points_enabled=False)
    # Must NOT raise on easing="acme.snap":
    config = load_config(cfg)
    assert config is not None

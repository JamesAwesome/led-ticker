import pytest

from led_ticker import _plugin_loader as L
from led_ticker.transitions import _TRANSITION_REGISTRY
from led_ticker.widgets import _WIDGET_REGISTRY


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def _ok_register(api):
    @api.widget("clock")
    class Clock:
        pass

    @api.transition("swoosh")
    class Swoosh:
        pass


def test_clean_register_commits_namespaced():
    result = L.LoadedPlugins()
    L._load_one("acme", "test", _ok_register, None, set(), result)
    assert "acme.clock" in _WIDGET_REGISTRY
    assert "acme.swoosh" in _TRANSITION_REGISTRY
    assert result.loaded[0].namespace == "acme"
    assert result.loaded[0].counts["widgets"] == 1
    assert result.loaded[0].counts["transitions"] == 1
    assert not result.failed


def test_raising_register_is_isolated_and_atomic():
    def boom(api):
        @api.widget("ok")
        class Ok:
            pass

        raise RuntimeError("kaboom")

    result = L.LoadedPlugins()
    L._load_one("bad", "test", boom, None, set(), result)
    assert "bad.ok" not in _WIDGET_REGISTRY
    assert result.loaded == []
    assert result.failed and result.failed[0][0] == "bad"


def test_cannot_shadow_a_builtin_name():
    def reg(api):
        @api.widget("message")  # becomes "acme.message", NOT "message"
        class W:
            pass

    result = L.LoadedPlugins()
    L._load_one("acme", "test", reg, None, set(), result)
    assert "acme.message" in _WIDGET_REGISTRY
    assert _WIDGET_REGISTRY["message"].__name__ != "W"  # builtin untouched


def test_namespace_already_claimed_skipped():
    result = L.LoadedPlugins()
    seen = {"acme"}
    L._load_one("acme", "second", _ok_register, None, seen, result)
    assert result.loaded == []
    assert result.failed and "already claimed" in result.failed[0][1]


def test_api_version_mismatch_skipped():
    result = L.LoadedPlugins()
    L._load_one("acme", "src", _ok_register, 99, set(), result)
    assert result.loaded == []
    assert result.failed and "requires API" in result.failed[0][1]


def test_missing_register_skipped():
    result = L.LoadedPlugins()
    L._load_one("acme", "src", None, None, set(), result)
    assert result.loaded == []
    assert result.failed and "register" in result.failed[0][1]

import importlib.metadata

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def _register(api):
    @api.widget("clock")
    class Clock:
        pass


class _FakeEP:
    def __init__(self, name, fn):
        self.name = name
        self.value = "fake:register"
        self._fn = fn

    def load(self):
        return self._fn


def test_entry_point_plugin_namespaced_by_ep_name(monkeypatch):
    def fake_entry_points(*, group):
        assert group == L.ENTRY_POINT_GROUP
        return [_FakeEP("acme", _register)]

    monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
    result = L.load_plugins(None, entry_points_enabled=True)
    assert "acme.clock" in _WIDGET_REGISTRY
    assert [i.namespace for i in result.loaded] == ["acme"]

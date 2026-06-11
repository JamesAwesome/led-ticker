import importlib.metadata

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.widgets import _WIDGET_REGISTRY

FUTURE = """
requires_api = 99
def register(api):
    @api.widget("c")
    class C:
        pass
"""
OK = """
def register(api):
    @api.widget("w")
    class W:
        pass
"""


@pytest.fixture(autouse=True)
def _clean():
    L.reset_plugins()
    yield
    L.reset_plugins()


def test_requires_api_from_file_skipped(tmp_path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "fromfuture.py").write_text(FUTURE)
    result = L.load_plugins(pdir, entry_points_enabled=False)
    assert "fromfuture.c" not in _WIDGET_REGISTRY
    assert any(ns == "fromfuture" for ns, _ in result.failed)


def test_cross_channel_namespace_collision(tmp_path, monkeypatch):
    # A local plugin "acme" AND an entry-point also named "acme". Local is
    # processed first, so its widget loads; the entry-point "acme" collides and
    # is recorded as failed.
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "acme.py").write_text(OK)

    def _ep_register(api):
        @api.widget("other")
        class Other:
            pass

    class _EP:
        name = "acme"
        value = "fake:register"

        def load(self):
            return _ep_register

    monkeypatch.setattr(importlib.metadata, "entry_points", lambda *, group: [_EP()])
    result = L.load_plugins(pdir, entry_points_enabled=True)
    assert "acme.w" in _WIDGET_REGISTRY  # local won
    assert "acme.other" not in _WIDGET_REGISTRY  # entry-point dup rejected
    assert any(ns == "acme" for ns, _ in result.failed)

"""Tests for the api.source plugin surface (Task 4: inline-value-tokens v1)."""

import pytest


def test_polled_data_source_is_public():
    import led_ticker.plugin as plugin
    from led_ticker.plugin import PolledDataSource  # noqa: F401

    assert "PolledDataSource" in plugin.__all__


def test_api_source_registers_and_resolves():
    from led_ticker.plugin import PluginAPI
    from led_ticker.sources import DataSource

    api = PluginAPI(namespace="acme")

    @api.source("ticker")
    class _S(DataSource):
        def compute(self) -> str:
            return "x"

    assert "acme.ticker" in api._buffers["sources"]


def test_api_source_dup_rejected_at_commit():
    """Dup rejection matches sibling surfaces: _commit raises if name is already
    in the live registry (not at buffer-fill time, which silently overwrites)."""
    from led_ticker import _plugin_loader
    from led_ticker.plugin import PluginAPI
    from led_ticker.sources import DataSource

    _plugin_loader.reset_plugins()

    # First plugin registers acme.dup
    api1 = PluginAPI(namespace="acme")

    @api1.source("dup")
    class _A(DataSource):
        def compute(self) -> str:
            return "a"

    from led_ticker._plugin_loader import PluginInfo, _commit

    info1 = PluginInfo(namespace="acme", source="test1")
    _commit(api1, info1)

    # Second registration of the SAME qualified name must raise at commit time.
    api2 = PluginAPI(namespace="acme")

    @api2.source("dup")
    class _B(DataSource):
        def compute(self) -> str:
            return "b"

    info2 = PluginInfo(namespace="acme", source="test2")
    with pytest.raises(ValueError, match="already registered"):
        _commit(api2, info2)

    _plugin_loader.reset_plugins()


def test_api_source_buffer_key_is_sources():
    """The buffer surface must be 'sources' (loader commits by key)."""
    from led_ticker.plugin import PluginAPI

    api = PluginAPI(namespace="ns")
    assert "sources" in api._buffers


def test_data_source_exported_from_plugin():
    """DataSource must be importable from led_ticker.plugin."""
    import led_ticker.plugin as P

    assert "DataSource" in P.__all__
    assert hasattr(P, "DataSource")
    from led_ticker.sources import DataSource as CoreDS

    assert P.DataSource is CoreDS


def test_loader_commits_source_into_get_source_class():
    """After load, api.source registrations are resolvable via get_source_class."""
    from led_ticker import _plugin_loader
    from led_ticker.app.factories import get_source_class
    from led_ticker.plugin import PluginAPI
    from led_ticker.sources import DataSource

    _plugin_loader.reset_plugins()

    api = PluginAPI(namespace="acme")

    @api.source("ticker")
    class _S(DataSource):
        def compute(self) -> str:
            return "live"

    from led_ticker._plugin_loader import PluginInfo, _commit

    info = PluginInfo(namespace="acme", source="test")
    _commit(api, info)

    cls = get_source_class("acme.ticker")
    assert cls is _S

    _plugin_loader.reset_plugins()


def test_get_source_class_still_resolves_core_types():
    """Core clock/date/static must still resolve after the plugin merge hook."""
    from led_ticker.app.factories import get_source_class
    from led_ticker.sources import ClockSource, DateSource, StaticSource

    assert get_source_class("clock") is ClockSource
    assert get_source_class("date") is DateSource
    assert get_source_class("static") is StaticSource


def test_get_source_class_unknown_raises():
    from led_ticker.app.factories import get_source_class

    with pytest.raises(ValueError, match="Unknown source type"):
        get_source_class("no.such.source")

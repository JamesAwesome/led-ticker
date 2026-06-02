from led_ticker._plugin_loader import LoadedPlugins, PluginInfo
from led_ticker.app.cli import _format_plugins


def test_format_plugins_lists_loaded_and_counts():
    result = LoadedPlugins(
        loaded=[
            PluginInfo(namespace="acme", source="/cfg/plugins/acme.py",
                       counts={"widgets": 2, "transitions": 1}),
        ],
        failed=[],
    )
    out = _format_plugins(result)
    assert "acme" in out
    assert "/cfg/plugins/acme.py" in out
    assert "widgets: 2" in out or "widgets=2" in out or "2 widgets" in out


def test_format_plugins_reports_failures():
    result = LoadedPlugins(loaded=[], failed=[("bad", "boom")])
    out = _format_plugins(result)
    assert "bad" in out
    assert "boom" in out


def test_format_plugins_empty():
    out = _format_plugins(LoadedPlugins())
    assert "no plugins" in out.lower()


def test_format_plugins_hooks_only_plugin():
    result = LoadedPlugins(
        loaded=[PluginInfo(namespace="hook_only", source="/p/h.py", counts={})],
        failed=[],
    )
    out = _format_plugins(result)
    assert "hook_only" in out
    assert "(hooks only)" in out

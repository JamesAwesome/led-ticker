import subprocess
import textwrap

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


def test_plugins_cli_reports_a_failed_plugin(tmp_path):
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "boom.py").write_text(
        "def register(api):\n    raise RuntimeError('kaboom during register')\n"
    )
    (tmp_path / "config.toml").write_text("[display]\nrows=16\ncols=64\n")
    proc = subprocess.run(
        ["led-ticker", "--config", str(tmp_path / "config.toml"), "plugins"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    out = proc.stdout + proc.stderr
    assert "boom" in out
    assert "Failed" in out or "kaboom" in out


def test_list_fields_works_for_plugin_widget(tmp_path):
    from led_ticker import _plugin_loader as L
    from led_ticker.app.factories import _list_widget_fields

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            def register(api):
                @api.widget("clock")
                @attrs.define
                class Clock:
                    text: str = "12:00"
                    def draw(self, canvas, cursor_pos=0, **kw):
                        return canvas, cursor_pos
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        out = _list_widget_fields("acme.clock")
        assert "acme.clock" in out
        assert "text" in out
    finally:
        L.reset_plugins()


def test_list_fields_plugin_widget_hides_uninjected_shared_fields(tmp_path):
    import textwrap

    from led_ticker import _plugin_loader as L
    from led_ticker.app.factories import _list_widget_fields

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            def register(api):
                @api.widget("clock")
                @attrs.define
                class Clock:
                    text: str = "12:00"
                    def draw(self, canvas, cursor_pos=0, **kw):
                        return canvas, cursor_pos
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        out = _list_widget_fields("acme.clock")
        assert "text" in out  # the widget's own declared field
        # Built-in font knobs NOT injected into a plugin widget must not show:
        assert "font_size" not in out
        assert "font_threshold" not in out
    finally:
        L.reset_plugins()

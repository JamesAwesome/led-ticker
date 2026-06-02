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


def test_loaded_plugin_hooks_are_consumable_by_run(tmp_path):
    import asyncio
    import textwrap

    from led_ticker import _plugin_loader as L

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "svc.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import StartupContext
            STATE = {"started": False, "stopped": False}

            def register(api):
                api.overlay(lambda canvas: None)
                api.on_startup(lambda ctx: STATE.__setitem__("started", True))
                api.on_shutdown(lambda: STATE.__setitem__("stopped", True))
            """
        )
    )
    try:
        plugins = L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        wrapped = [L._guarded_overlay(ns, p) for ns, p in plugins.overlays]
        assert len(wrapped) == 1
        asyncio.run(L._run_startup_hooks(plugins.startup_hooks, object()))
        asyncio.run(L._run_shutdown_hooks(plugins.shutdown_hooks))
        # _import_from_path doesn't register the module in sys.modules, so
        # we retrieve STATE via the startup hook's __globals__ (the module ns).
        _, startup_fn = plugins.startup_hooks[0]
        state = startup_fn.__globals__["STATE"]
        assert state == {"started": True, "stopped": True}
    finally:
        L.reset_plugins()


def test_run_wires_lifecycle_hooks():
    # Tripwire: guards that run() actually wires the plugin lifecycle. The
    # behavioral hook logic is covered in test_hook_plugins.py; this catches
    # accidental removal of the wiring from run() (the full loop needs hardware,
    # so we assert the call sites exist in run()'s source).
    import importlib
    import inspect

    # `led_ticker.app.run` resolves to the re-exported run() function on the
    # app package, so reach the submodule explicitly to read its source.
    run_module = importlib.import_module("led_ticker.app.run")

    src = inspect.getsource(run_module.run)
    assert "_run_startup_hooks" in src
    assert "_run_shutdown_hooks" in src
    assert "_guarded_overlay" in src
    assert "StartupContext" in src

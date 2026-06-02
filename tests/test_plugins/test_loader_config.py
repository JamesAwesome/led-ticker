import textwrap

from led_ticker import _plugin_loader as L


def _write(plugin_dir, name, body="def register(api):\n    pass\n"):
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / f"{name}.py").write_text(textwrap.dedent(body))


def test_disable_skips_named_namespace(tmp_path):
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    _write(pdir, "keep")
    _write(pdir, "drop")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False, disable={"drop"})
        loaded = {info.namespace for info in result.loaded}
        assert loaded == {"keep"}
    finally:
        L.reset_plugins()


def test_read_plugins_config_reads_block(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """
            [display]
            rows = 16
            cols = 64

            [plugins]
            enabled = false
            dir = "addons"
            disable = ["x"]
            """
        )
    )
    pc = L.read_plugins_config(cfg_path)
    assert pc.enabled is False
    assert pc.dir == "addons"
    assert pc.disable == ["x"]


def test_read_plugins_config_defaults_on_unreadable(tmp_path):
    bad = tmp_path / "nope.toml"
    pc = L.read_plugins_config(bad)
    assert pc.enabled is True and pc.dir == "plugins" and pc.disable == []


def test_load_plugins_for_config_disabled_loads_nothing(tmp_path):
    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    _write(tmp_path / "plugins", "acme")
    (tmp_path / "config.toml").write_text(
        "[display]\nrows=16\ncols=64\n[plugins]\nenabled=false\n"
    )
    try:
        result = L.load_plugins_for_config(tmp_path / "config.toml")
        assert result.loaded == [] and result.failed == []
    finally:
        L.reset_plugins()


def test_load_plugins_for_config_honors_dir_and_disable(tmp_path):
    L.reset_plugins()
    addons = tmp_path / "addons"
    _write(addons, "keep")
    _write(addons, "drop")
    (tmp_path / "config.toml").write_text(
        '[display]\nrows=16\ncols=64\n[plugins]\ndir="addons"\ndisable=["drop"]\n'
    )
    try:
        result = L.load_plugins_for_config(tmp_path / "config.toml")
        assert {i.namespace for i in result.loaded} == {"keep"}
    finally:
        L.reset_plugins()

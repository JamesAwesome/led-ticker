import pytest

from led_ticker.config import PluginsConfig, _parse_plugins_block


def test_defaults_when_block_absent():
    cfg = _parse_plugins_block({})
    assert cfg == PluginsConfig(enabled=True, dir="plugins", disable=[])


def test_parses_all_fields():
    cfg = _parse_plugins_block(
        {"plugins": {"enabled": False, "dir": "addons", "disable": ["acme", "x"]}}
    )
    assert cfg.enabled is False
    assert cfg.dir == "addons"
    assert cfg.disable == ["acme", "x"]


def test_enabled_must_be_bool():
    with pytest.raises(ValueError, match="plugins.enabled must be a bool"):
        _parse_plugins_block({"plugins": {"enabled": "yes"}})


def test_dir_must_be_str():
    with pytest.raises(ValueError, match="plugins.dir must be a string"):
        _parse_plugins_block({"plugins": {"dir": 3}})


def test_disable_must_be_list_of_str():
    with pytest.raises(ValueError, match="plugins.disable must be a list of strings"):
        _parse_plugins_block({"plugins": {"disable": "acme"}})
    with pytest.raises(ValueError, match="plugins.disable must be a list of strings"):
        _parse_plugins_block({"plugins": {"disable": [1, 2]}})

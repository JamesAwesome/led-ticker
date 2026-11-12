"""One-shot CLI commands must see plugins installed in the Docker plugin volume.

`docker exec led-ticker led-ticker validate ...` runs the base interpreter; the
plugins live in /data/plugins/venv, which only the display process's boot
reconcile puts on sys.path. Without `apply_volume_visibility()` before the
plugin load, every `flair.*` / `nyancat.*` reference reads as an unknown style.
"""

import sys
from pathlib import Path

import pytest

from led_ticker import _plugin_loader, plugin_reconcile
from led_ticker._plugin_loader import LoadedPlugins
from led_ticker.app import cli


@pytest.fixture
def calls(monkeypatch):
    log: list[str] = []
    monkeypatch.setattr(
        plugin_reconcile, "apply_volume_visibility", lambda *a, **k: log.append("see")
    )

    def fake_load(_config):
        log.append("load")
        return LoadedPlugins()

    monkeypatch.setattr(_plugin_loader, "load_plugins_for_config", fake_load)
    return log


def _run(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["led-ticker", *argv])
    with pytest.raises(SystemExit):
        cli.main()


def test_validate_sees_volume_before_loading_plugins(monkeypatch, calls, tmp_path):
    import led_ticker.validate as validate_mod

    async def fake_validate(path, strict=False):
        _plugin_loader.load_plugins_for_config(path)
        return validate_mod.ValidationResult(path=Path(path))

    monkeypatch.setattr(validate_mod, "validate_config", fake_validate)
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    _run(monkeypatch, ["validate", str(cfg)])
    assert calls == ["see", "load"]


def test_validate_list_fields_sees_volume(monkeypatch, calls):
    _run(monkeypatch, ["validate", "--list-fields", "message"])
    assert calls == ["see", "load"]


@pytest.mark.parametrize("argv", [["plugin", "status"], ["plugins"]])
def test_plugin_status_sees_volume(monkeypatch, calls, argv):
    _run(monkeypatch, argv)
    assert calls == ["see", "load"]

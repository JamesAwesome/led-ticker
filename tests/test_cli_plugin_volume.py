"""One-shot CLI commands must see plugins installed in the Docker plugin volume.

`docker exec led-ticker led-ticker validate ...` runs the base interpreter; the
plugins live in /data/plugins/venv, which only the display process's boot
reconcile puts on sys.path. Without `apply_volume_visibility()` before the
plugin load, every `flair.*` / `nyancat.*` reference reads as an unknown style.
"""

import json
import logging
import sys
from pathlib import Path

import pytest

from led_ticker import _plugin_loader, plugin_reconcile
from led_ticker._plugin_loader import LoadedPlugins
from led_ticker.app import cli


@pytest.fixture(autouse=True)
def _root_logger_reset():
    """cli.main() adds a root StreamHandler and sets INFO; don't leak it."""
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    yield
    root.setLevel(level)
    for h in list(root.handlers):
        if h not in handlers:
            root.removeHandler(h)


@pytest.fixture
def calls(monkeypatch):
    log: list[str] = []

    def fake_see(*args, **kwargs):
        # Every call site must go through cli._PLUGIN_VOLUME_ROOT, never the
        # function's /data/plugins default.
        assert args == (cli._PLUGIN_VOLUME_ROOT,) and not kwargs
        log.append("see")

    monkeypatch.setattr(plugin_reconcile, "apply_volume_visibility", fake_see)

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


@pytest.mark.parametrize(
    ("argv", "verb"),
    [(["plugin", "list"], "cmd_list"), (["plugin", "search", "x"], "cmd_search")],
)
def test_plugin_list_and_search_see_volume(monkeypatch, calls, argv, verb):
    from led_ticker.app import plugin_cmd

    monkeypatch.setattr(plugin_cmd, verb, lambda *a, **k: calls.append("load") or 0)
    _run(monkeypatch, argv)
    assert calls == ["see", "load"]


def test_webui_sees_volume_before_serving(monkeypatch, calls, tmp_path):
    import led_ticker.config as config_mod
    import led_ticker.webui as webui_mod

    monkeypatch.setattr(config_mod, "read_web_config", lambda _p: object())

    async def fake_run_webui(*_a):
        calls.append("load")

    monkeypatch.setattr(webui_mod, "run_webui", fake_run_webui)
    _run(monkeypatch, ["--config", str(tmp_path / "c.toml"), "webui"])
    assert calls == ["see", "load"]


def test_see_plugin_volume_puts_volume_site_packages_on_path(monkeypatch, tmp_path):
    """Unstubbed: the CLI helper really targets its volume root."""
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    sp = tmp_path / "venv" / "lib" / f"python{py}" / "site-packages"
    sp.mkdir(parents=True)
    monkeypatch.setattr(cli, "_PLUGIN_VOLUME_ROOT", tmp_path)
    saved = list(sys.path)
    try:
        cli._see_plugin_volume()
        assert sys.path[0] == str(sp)
    finally:
        sys.path[:] = saved


def test_validate_json_stdout_is_pure_json(monkeypatch, calls, tmp_path, capsys):
    """Plugin-load logs AND a volume-visibility warning (emitted before any
    load) must not precede --json output on stdout."""
    import led_ticker.validate as validate_mod

    def warning_see(*_a, **_k):
        logging.getLogger("led_ticker.plugin_reconcile").warning("venv mismatch")

    monkeypatch.setattr(plugin_reconcile, "apply_volume_visibility", warning_see)

    async def fake_validate(path, strict=False):
        logging.getLogger("led_ticker._plugin_loader").info("plugin 'flair' loaded")
        return validate_mod.ValidationResult(path=Path(path))

    monkeypatch.setattr(validate_mod, "validate_config", fake_validate)
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    _run(monkeypatch, ["validate", "--json", str(cfg)])
    out, err = capsys.readouterr()
    json.loads(out)
    assert "venv mismatch" in err
    assert "plugin 'flair' loaded" in err

"""argv -> main() dispatch for the `plugin` subcommand + the `plugins` alias.

Drives the real argparse plumbing in cli.main() (in-process, hermetic via the
autouse entry-point stub) — the seam not covered by the cmd_* unit tests.
"""

import sys

import pytest

from led_ticker.app import cli


def _run(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["led-ticker", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


def _min_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[display]\nrows=16\ncols=64\n")
    return cfg


def test_plugins_alias_warns_and_runs_status(tmp_path, monkeypatch, capsys):
    cfg = _min_config(tmp_path)
    code = _run(monkeypatch, ["--config", str(cfg), "plugins"])
    captured = capsys.readouterr()
    assert code == 0
    assert "deprecated" in captured.err
    assert "plugin status" in captured.err
    assert "No plugins found." in captured.out  # hermetic -> empty


def test_plugin_status_matches_old_plugins(tmp_path, monkeypatch, capsys):
    cfg = _min_config(tmp_path)
    code = _run(monkeypatch, ["--config", str(cfg), "plugin", "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "No plugins found." in out


def test_bare_plugin_runs_status(tmp_path, monkeypatch, capsys):
    cfg = _min_config(tmp_path)
    code = _run(monkeypatch, ["--config", str(cfg), "plugin"])
    assert code == 0
    assert "No plugins found." in capsys.readouterr().out


def test_plugin_list_dispatches_to_catalog(monkeypatch, capsys):
    code = _run(monkeypatch, ["plugin", "list"])
    out = capsys.readouterr().out
    assert code == 0
    assert "pool" in out  # the bundled catalog


def test_plugin_search_dispatches(monkeypatch, capsys):
    code = _run(monkeypatch, ["plugin", "search", "pool"])
    assert code == 0
    assert "pool" in capsys.readouterr().out

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


def test_bare_plugin_prints_help_not_status(tmp_path, monkeypatch, capsys):
    # Bare `plugin` shows the subcommands, NOT status's "No plugins found."
    # (which would mislead a first-time user into thinking nothing's available).
    code = _run(monkeypatch, ["plugin"])
    out = capsys.readouterr().out
    assert code == 0
    assert "install" in out and "list" in out  # the help listing
    assert "No plugins found." not in out


def test_plugin_list_dispatches_to_catalog(monkeypatch, capsys):
    code = _run(monkeypatch, ["plugin", "list"])
    out = capsys.readouterr().out
    assert code == 0
    assert "pool" in out  # the bundled catalog


def test_plugin_search_dispatches(monkeypatch, capsys):
    code = _run(monkeypatch, ["plugin", "search", "pool"])
    assert code == 0
    assert "pool" in capsys.readouterr().out


def test_plugin_install_without_config_targets_config_dir(
    tmp_path, monkeypatch, capsys
):
    # No --config -> the dispatch passes config_explicit=False -> the requirements
    # file defaults to config/requirements-plugins.txt (dry-run, so nothing runs).
    monkeypatch.chdir(tmp_path)
    code = _run(monkeypatch, ["plugin", "install", "pool", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "config/requirements-plugins.txt" in out


def test_plugin_add_dispatch_writes_manifest(tmp_path, monkeypatch, capsys):
    cfg = _min_config(tmp_path)
    code = _run(monkeypatch, ["plugin", "add", "pool", "--config", str(cfg)])
    out = capsys.readouterr().out
    assert code == 0
    assert "rebuild" in out.lower()
    assert (
        (tmp_path / "requirements-plugins.txt").read_text().strip().startswith("git+")
    )


def test_plugin_remove_dispatch(tmp_path, monkeypatch, capsys):
    cfg = _min_config(tmp_path)
    (tmp_path / "requirements-plugins.txt").write_text(
        "git+https://github.com/JamesAwesome/led-ticker-pool.git@main\n"
    )
    code = _run(monkeypatch, ["plugin", "remove", "pool", "--config", str(cfg)])
    assert code == 0
    assert "led-ticker-pool" not in (tmp_path / "requirements-plugins.txt").read_text()


def test_plugin_uninstall_dry_run_dispatch(tmp_path, monkeypatch, capsys):
    cfg = _min_config(tmp_path)
    code = _run(
        monkeypatch, ["plugin", "uninstall", "pool", "--config", str(cfg), "--dry-run"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "pip uninstall" in out  # dry-run shows the command, runs nothing


def test_install_save_only_deprecation_routes_to_add(tmp_path, monkeypatch, capsys):
    # `install --save-only` warns and behaves like `add` (no pip).
    from led_ticker.app import plugin_cmd

    pip_calls = []
    monkeypatch.setattr(
        plugin_cmd.subprocess, "run", lambda cmd, **kw: pip_calls.append(cmd)
    )
    cfg = _min_config(tmp_path)
    code = _run(
        monkeypatch,
        ["plugin", "install", "pool", "--save-only", "--config", str(cfg)],
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "deprecated" in captured.err
    assert (tmp_path / "requirements-plugins.txt").exists()
    assert pip_calls == []  # routed to add — pip never invoked

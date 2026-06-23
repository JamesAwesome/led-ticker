import subprocess
import sys

from led_ticker.plugin_reconcile import (
    PluginAction,
    compute_diff,
    ensure_volume_venv,
    referenced_namespaces,
    resolve_target,
    uninstall_blocked_reason,
)


def test_compute_diff_install_and_uninstall():
    to_install, to_uninstall = compute_diff(
        declared={"pool", "rss"}, installed={"pool", "old"}
    )
    assert to_install == {"rss"}
    assert to_uninstall == {"old"}


def test_compute_diff_noop_when_matched():
    assert compute_diff(declared={"pool"}, installed={"pool"}) == (set(), set())


def test_plugin_action_is_frozen():
    a = PluginAction(namespace="pool", action="installed", detail="0.1.0")
    assert a.namespace == "pool" and a.action == "installed"


def test_resolve_target_local_when_no_volume(tmp_path):
    t = resolve_target(volume_root=tmp_path / "absent")
    assert (
        t.kind == "venv" and t.python_exe == sys.executable and t.site_packages is None
    )


def test_resolve_target_volume_when_present(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    t = resolve_target(volume_root=tmp_path)
    assert t.kind == "volume"
    expected_exe = str(tmp_path / "venv" / "bin" / "python")
    assert t.python_exe == expected_exe
    assert t.site_packages and t.site_packages.endswith("site-packages")


def test_ensure_creates_venv_when_missing(tmp_path):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        (tmp_path / "venv").mkdir(exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0)

    ensure_volume_venv(tmp_path / "venv", runner=fake_run)
    assert any("--system-site-packages" in c for c in calls)
    assert (tmp_path / "venv" / ".python-version").exists()


def test_ensure_noop_when_stamp_matches(tmp_path):
    venv = tmp_path / "venv"
    venv.mkdir()
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    (venv / ".python-version").write_text(py_version)
    calls = []

    def runner(c, **k):
        calls.append(c)
        return subprocess.CompletedProcess(c, 0)

    ensure_volume_venv(venv, runner=runner)
    assert calls == []  # no recreate


# ── Uninstall guards ──────────────────────────────────────────────────────────


def test_referenced_namespaces_reads_widget_types(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[[playlist.section]]\nmode="swap"\n'
        '[[playlist.section.widget]]\ntype="rss.feed"\n'
    )
    assert "rss" in referenced_namespaces(cfg)


def test_referenced_namespaces_missing_file_is_empty(tmp_path):
    assert referenced_namespaces(tmp_path / "absent.toml") == set()


def test_referenced_namespaces_malformed_toml_is_empty(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[[bad toml\n")
    assert referenced_namespaces(cfg) == set()


def test_blocked_when_config_references(monkeypatch):
    import led_ticker.plugin_reconcile as r

    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    assert uninstall_blocked_reason("rss", "led-ticker-rss", {"rss"}) is not None


def test_blocked_when_depended_on(monkeypatch):
    import led_ticker.plugin_reconcile as r

    monkeypatch.setattr(r, "is_depended_on", lambda d: True)
    reason = uninstall_blocked_reason("rss", "led-ticker-rss", set())
    assert reason and "depended" in reason


def test_not_blocked_when_safe(monkeypatch):
    import led_ticker.plugin_reconcile as r

    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    assert uninstall_blocked_reason("rss", "led-ticker-rss", set()) is None

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


# ── reconcile orchestrator ────────────────────────────────────────────────────


def test_reconcile_installs_missing_uninstalls_undeclared(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    # declared: rss ; installed: old
    manifest = tmp_path / "config" / "requirements-plugins.txt"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("led-ticker-rss\n")
    (tmp_path / "config" / "config.toml").write_text("")  # no widget refs
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"old": "led-ticker-old"})
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    installed, uninstalled = [], []

    def fake_install(ns, py):
        installed.append(ns)

    def fake_uninstall(dist, py):
        uninstalled.append(dist)

    monkeypatch.setattr(r, "_install_namespace", fake_install)
    monkeypatch.setattr(r, "_uninstall_dist", fake_uninstall)
    actions = r.reconcile(tmp_path / "config" / "config.toml")
    assert "rss" in installed and "led-ticker-old" in uninstalled
    assert any(a.action == "installed" and a.namespace == "rss" for a in actions)


def test_reconcile_blocks_uninstall_when_config_references(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text(
        '[[playlist.section]]\nmode="swap"\n[[playlist.section.widget]]\ntype="old.thing"\n'
    )
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"old": "led-ticker-old"})
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    monkeypatch.setattr(
        r,
        "_uninstall_dist",
        lambda *a: (_ for _ in ()).throw(AssertionError("should not uninstall")),
    )
    actions = r.reconcile(tmp_path / "config.toml")
    assert any(a.action == "blocked" and a.namespace == "old" for a in actions)


def test_reconcile_never_raises(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    monkeypatch.setattr(
        r, "resolve_target", lambda **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert r.reconcile(tmp_path / "config.toml") == []  # swallowed


def test_reconcile_records_failed_action_on_install_error(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-rss\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    def boom(ns, py):
        raise RuntimeError("pip exploded")

    monkeypatch.setattr(r, "_install_namespace", boom)
    actions = r.reconcile(tmp_path / "config.toml")
    assert any(a.action == "failed" and a.namespace == "rss" for a in actions)
    assert "pip exploded" in next(a.detail for a in actions if a.action == "failed")


def test_reconcile_records_failed_action_on_uninstall_error(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"old": "led-ticker-old"})
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)

    def boom(dist, py):
        raise RuntimeError("pip exploded")

    monkeypatch.setattr(r, "_uninstall_dist", boom)
    actions = r.reconcile(tmp_path / "config.toml")
    assert any(a.action == "failed" and a.namespace == "old" for a in actions)


def test_reconcile_calls_ensure_volume_venv_for_volume_target(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    calls = []
    monkeypatch.setattr(
        r,
        "resolve_target",
        lambda **k: r.Target("volume", "py", None),
    )
    monkeypatch.setattr(
        r, "ensure_volume_venv", lambda venv_dir: calls.append(venv_dir)
    )
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})
    r.reconcile(tmp_path / "config.toml", volume_root=tmp_path / "vol")
    assert calls  # ensure_volume_venv was called


def test_reconcile_noop_when_declared_matches_installed(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"rss": "led-ticker-rss"})
    installed, uninstalled = [], []
    monkeypatch.setattr(r, "_install_namespace", lambda ns, py: installed.append(ns))
    monkeypatch.setattr(r, "_uninstall_dist", lambda d, py: uninstalled.append(d))
    actions = r.reconcile(tmp_path / "config.toml")
    assert installed == [] and uninstalled == []
    assert actions == []


# ── _declared_namespaces ──────────────────────────────────────────────────────


def test_declared_namespaces_catalog_lookup(tmp_path):
    """A catalog-known package name resolves to the catalog namespace."""
    import led_ticker.plugin_reconcile as r

    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text("led-ticker-rss\n")
    config = tmp_path / "config.toml"
    config.write_text("")
    # "led-ticker-rss" -> key "led-ticker-rss"; catalog says namespace = "rss"
    ns = r._declared_namespaces(config)
    assert "rss" in ns


def test_declared_namespaces_fallback_to_key(tmp_path, monkeypatch):
    """An unknown requirement falls back to the dedup key as namespace."""
    import led_ticker.plugin_reconcile as r
    from led_ticker.plugins_catalog import Catalog

    monkeypatch.setattr(
        "led_ticker.plugin_reconcile.load_catalog",
        lambda: Catalog(entries=()),
        raising=False,
    )
    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text("my-custom-plugin\n")
    config = tmp_path / "config.toml"
    config.write_text("")
    ns = r._declared_namespaces(config)
    assert "my-custom-plugin" in ns


def test_declared_namespaces_missing_manifest(tmp_path):
    import led_ticker.plugin_reconcile as r

    config = tmp_path / "config.toml"
    config.write_text("")
    assert r._declared_namespaces(config) == set()


def test_declared_namespaces_skips_comment_lines(tmp_path):
    import led_ticker.plugin_reconcile as r

    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text("# This is a comment\nled-ticker-rss\n")
    config = tmp_path / "config.toml"
    config.write_text("")
    ns = r._declared_namespaces(config)
    assert "rss" in ns
    # The comment should not appear as a namespace
    assert not any(n.startswith("#") for n in ns)


# ── apply_to_syspath ──────────────────────────────────────────────────────────


def test_apply_to_syspath_inserts_when_exists(tmp_path):
    import sys

    import led_ticker.plugin_reconcile as r

    sp = str(tmp_path / "site-packages")
    (tmp_path / "site-packages").mkdir()
    target = r.Target("volume", "py", sp)
    # Remove if already present from a prior test run
    if sp in sys.path:
        sys.path.remove(sp)
    r.apply_to_syspath(target)
    assert sys.path[0] == sp
    # Cleanup
    sys.path.remove(sp)


def test_apply_to_syspath_idempotent(tmp_path):
    import sys

    import led_ticker.plugin_reconcile as r

    sp = str(tmp_path / "site-packages")
    (tmp_path / "site-packages").mkdir()
    target = r.Target("volume", "py", sp)
    if sp in sys.path:
        sys.path.remove(sp)
    r.apply_to_syspath(target)
    count_before = sys.path.count(sp)
    r.apply_to_syspath(target)
    assert sys.path.count(sp) == count_before
    # Cleanup
    while sp in sys.path:
        sys.path.remove(sp)


def test_apply_to_syspath_noop_when_no_site_packages(tmp_path):
    import sys

    import led_ticker.plugin_reconcile as r

    target = r.Target("venv", "py", None)
    old_path = sys.path[:]
    r.apply_to_syspath(target)
    assert sys.path == old_path


def test_apply_to_syspath_noop_when_dir_missing(tmp_path):
    import sys

    import led_ticker.plugin_reconcile as r

    sp = str(tmp_path / "nonexistent")
    target = r.Target("volume", "py", sp)
    old_path = sys.path[:]
    r.apply_to_syspath(target)
    assert sys.path == old_path

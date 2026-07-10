import subprocess
import sys

import pytest

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
        '[[playlist.section]]\nmode = "slideshow"\n'
        '[[playlist.section.widget]]\ntype="rss.feed"\n'
    )
    assert "rss" in referenced_namespaces(cfg)


def test_referenced_namespaces_missing_file_is_empty(tmp_path):
    assert referenced_namespaces(tmp_path / "absent.toml") == set()


def test_referenced_namespaces_reads_transition_keys(tmp_path):
    """A plugin used ONLY via a transition (never a widget type) must still be
    reported as referenced — otherwise the uninstall guard would let it be
    removed while config still uses it, breaking the next boot (finding #6)."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[[playlist.section]]\n"
        'mode = "slideshow"\n'
        'transition="nyancat.forward"\n'
        'entry_transition="pokeball.reverse"\n'
        'widget_transition="pacman.alternating"\n'
        "[[playlist.section.widget]]\n"
        'type="message"\n'  # core widget, no namespace
    )
    refs = referenced_namespaces(cfg)
    assert {"nyancat", "pokeball", "pacman"} <= refs


def test_transition_reference_blocks_uninstall(tmp_path, monkeypatch):
    """End-to-end: a plugin referenced ONLY via `transition=` is blocked from
    uninstall by the config-reference guard (finding #6)."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[[playlist.section]]\nmode = "slideshow"\ntransition="nyancat.forward"\n'
        '[[playlist.section.widget]]\ntype="message"\n'
    )
    (tmp_path / "requirements-plugins.txt").write_text("")  # declares nothing
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(
        r, "installed_plugin_dists", lambda: {"nyancat": "led-ticker-nyancat"}
    )
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    monkeypatch.setattr(
        r,
        "_uninstall_dist",
        lambda *a: (_ for _ in ()).throw(AssertionError("should not uninstall")),
    )
    actions = r.reconcile(cfg)
    assert any(a.action == "blocked" and a.namespace == "nyancat" for a in actions)


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

    def fake_install(ns, py, *, constraints=None, requirement_line=None):
        installed.append(ns)
        return 0

    def fake_uninstall(dist, py):
        uninstalled.append(dist)
        return 0

    monkeypatch.setattr(r, "_install_namespace", fake_install)
    monkeypatch.setattr(r, "_uninstall_dist", fake_uninstall)
    actions = r.reconcile(tmp_path / "config" / "config.toml")
    assert "rss" in installed and "led-ticker-old" in uninstalled
    assert any(a.action == "installed" and a.namespace == "rss" for a in actions)


def test_reconcile_blocks_uninstall_when_config_references(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text(
        "[[playlist.section]]\n"
        'mode = "slideshow"\n'
        "[[playlist.section.widget]]\n"
        'type="old.thing"\n'
    )
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
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

    def boom(ns, py, *, constraints=None, requirement_line=None):
        raise RuntimeError("pip exploded")

    monkeypatch.setattr(r, "_install_namespace", boom)
    actions = r.reconcile(tmp_path / "config.toml")
    assert any(a.action == "failed" and a.namespace == "rss" for a in actions)
    assert "pip exploded" in next(a.detail for a in actions if a.action == "failed")


def test_reconcile_records_failed_action_on_uninstall_error(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
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


def test_reconcile_failed_action_on_install_nonzero_exit(tmp_path, monkeypatch):
    """A non-zero pip exit code on install yields action='failed', not 'installed'."""
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-rss\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    def fake_install(ns, py, *, constraints=None, requirement_line=None):
        return 1  # non-zero exit — pip failed

    monkeypatch.setattr(r, "_install_namespace", fake_install)
    actions = r.reconcile(tmp_path / "config.toml")
    assert any(a.action == "failed" and a.namespace == "rss" for a in actions)
    assert not any(a.action == "installed" for a in actions)
    failed = next(a for a in actions if a.action == "failed")
    assert "pip exited 1" in failed.detail


def test_reconcile_failed_action_on_uninstall_nonzero_exit(tmp_path, monkeypatch):
    """Non-zero pip exit code on uninstall yields action='failed', not 'uninstalled'."""
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"old": "led-ticker-old"})
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)

    def fake_uninstall(dist, py):
        return 2  # non-zero exit — pip failed

    monkeypatch.setattr(r, "_uninstall_dist", fake_uninstall)
    actions = r.reconcile(tmp_path / "config.toml")
    assert any(a.action == "failed" and a.namespace == "old" for a in actions)
    assert not any(a.action == "uninstalled" for a in actions)
    failed = next(a for a in actions if a.action == "failed")
    assert "pip exited 2" in failed.detail


def test_reconcile_noop_when_declared_matches_installed(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    # A manifest MUST exist or reconcile early-returns on `not manifest.exists()`
    # before ever reaching the declared==installed noop path. Make it match the
    # monkeypatched declared/installed set so the noop branch is what runs.
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-rss==1.0.0\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(
        r, "_declared_requirements", lambda p: {"rss": "led-ticker-rss==1.0.0"}
    )
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"rss": "led-ticker-rss"})
    # Installed version matches the pin -> no pin-drift reinstall either.
    monkeypatch.setattr(r.importlib.metadata, "version", lambda dist: "1.0.0")
    installed, uninstalled = [], []
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda ns, py, *, constraints=None, requirement_line=None: (
            installed.append(ns) or 0
        ),
    )
    monkeypatch.setattr(r, "_uninstall_dist", lambda d, py: uninstalled.append(d) or 0)
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

    # load_catalog is imported inside the function body, so patch it at the
    # source module so the lazy import picks up the stub.
    monkeypatch.setattr(
        "led_ticker.plugins_catalog.load_catalog",
        lambda: Catalog(entries=()),
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


# ── shared-package declaration (led-ticker-flair) ─────────────────────────────

_FLAIR_NAMESPACES = {"nyancat", "pokeball", "pacman", "sailor_moon"}


def test_declared_requirements_shared_package_maps_all_namespaces(tmp_path):
    """A shared pip package (led-ticker-flair) declares EVERY namespace it ships.

    Regression: key_to_ns used to be a single-namespace map (last-write-wins), so
    a `led-ticker-flair` manifest line collapsed to whichever flair entry the
    catalog loop visited last (`sailor_moon`) — pacman/nyancat/pokeball never
    installed. Uses the real bundled catalog (the flair entries are real).
    """
    import led_ticker.plugin_reconcile as r

    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text("led-ticker-flair\n")
    config = tmp_path / "config.toml"
    config.write_text("")

    reqs = r._declared_requirements(config)
    for ns in _FLAIR_NAMESPACES:
        assert ns in reqs, f"{ns} should be declared by a led-ticker-flair line"
        assert reqs[ns] == "led-ticker-flair"


def test_declared_namespaces_shared_package_includes_all_siblings(tmp_path):
    """_declared_namespaces wraps _declared_requirements — all four flair names."""
    import led_ticker.plugin_reconcile as r

    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text("led-ticker-flair\n")
    config = tmp_path / "config.toml"
    config.write_text("")

    assert r._declared_namespaces(config) >= _FLAIR_NAMESPACES


def test_reconcile_shared_package_installs_once(tmp_path, monkeypatch):
    """A 4-namespace shared package installs the pip line ONCE, not 4×.

    With led-ticker-flair declared and nothing installed, to_install covers all
    four flair namespaces — but the actual pip install must run a single time for
    the shared package (correct-but-wasteful 4× installs are deduped). Every
    covered namespace still gets an "installed" action.
    """
    import led_ticker.plugin_reconcile as r

    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text("led-ticker-flair\n")
    cfg = tmp_path / "config.toml"
    cfg.write_text("")  # no widget refs

    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    calls: list[str | None] = []

    def fake_install(ns, py, *, constraints=None, requirement_line=None):
        calls.append(requirement_line)
        return 0

    monkeypatch.setattr(r, "_install_namespace", fake_install)
    actions = r.reconcile(cfg)

    # pacman (and its siblings) are installed.
    by_ns = {a.namespace: a.action for a in actions}
    for ns in _FLAIR_NAMESPACES:
        assert by_ns.get(ns) == "installed", f"{ns} should be installed"

    # The shared package's pip install ran exactly ONCE for led-ticker-flair.
    assert calls == ["led-ticker-flair"]


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


# ── cross-environment scan (finding #1) ────────────────────────────────────────


def _write_fake_plugin_distinfo(site_packages, dist_name, namespace):
    """Lay down a minimal *.dist-info with a led_ticker.plugins entry point so
    importlib.metadata can discover it once site_packages is on sys.path."""
    site_packages.mkdir(parents=True, exist_ok=True)
    di = site_packages / f"{dist_name.replace('-', '_')}-0.1.0.dist-info"
    di.mkdir()
    (di / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {dist_name}\nVersion: 0.1.0\n"
    )
    (di / "entry_points.txt").write_text(
        f"[led_ticker.plugins]\n{namespace} = {dist_name.replace('-', '_')}:register\n"
    )
    (di / "RECORD").write_text("")


def test_reconcile_observes_target_env_installed(tmp_path, monkeypatch):
    """Reconcile must scan the TARGET (volume) environment, not the base
    interpreter. A plugin present ONLY in the volume site-packages must be seen
    as `installed` so it isn't reinstalled and (when undeclared) is uninstalled.

    Non-monkeypatched on installed_plugin_dists/is_depended_on — it exercises the
    real cross-environment scan via apply_to_syspath inserting the volume
    site-packages before the diff. Regression for the wrong-environment bug.
    """
    import importlib.metadata
    import sys

    import led_ticker.plugin_reconcile as r

    site_packages = tmp_path / "vol" / "venv" / "lib" / "pyX" / "site-packages"
    _write_fake_plugin_distinfo(site_packages, "led-ticker-rss", "rss")

    # The autouse hermetic fixture stubs entry_points(group=...) to []. Restore a
    # REAL scan rooted at whatever is on sys.path (distributions() is NOT stubbed)
    # so this test exercises the genuine cross-environment lookup: the fake plugin
    # is only visible once apply_to_syspath has inserted `site_packages`.
    def real_scan(*args, **kwargs):
        group = kwargs.get("group")
        eps = []
        for dist in importlib.metadata.distributions():
            for ep in dist.entry_points:
                if group is None or ep.group == group:
                    eps.append(ep)
        return eps

    monkeypatch.setattr(importlib.metadata, "entry_points", real_scan)

    cfg = tmp_path / "config.toml"
    cfg.write_text("")  # no widget references -> rss is undeclared + unreferenced
    (tmp_path / "requirements-plugins.txt").write_text("")  # declared = empty

    # Force a volume target pointed at our fake site-packages; skip real venv
    # creation. resolve_target/ensure_volume_venv are infra, not under test here.
    monkeypatch.setattr(
        r,
        "resolve_target",
        lambda **k: r.Target("volume", "py", str(site_packages)),
    )
    monkeypatch.setattr(r, "ensure_volume_venv", lambda venv_dir: None)
    # is_depended_on is NOT patched — real scan. Capture the uninstall target.
    uninstalled = []
    monkeypatch.setattr(
        r, "_uninstall_dist", lambda dist, py: uninstalled.append(dist) or 0
    )
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda ns, py, *, constraints=None, requirement_line=None: (
            _ for _ in ()
        ).throw(AssertionError()),
    )

    inserted_before = str(site_packages) in sys.path
    try:
        actions = r.reconcile(cfg, volume_root=tmp_path / "vol")
    finally:
        while str(site_packages) in sys.path:
            sys.path.remove(str(site_packages))
        if inserted_before:
            sys.path.insert(0, str(site_packages))

    # rss was observed as installed in the volume env -> uninstalled (true sync),
    # NOT treated as missing-and-reinstalled.
    assert "led-ticker-rss" in uninstalled
    assert any(a.action == "uninstalled" and a.namespace == "rss" for a in actions)


def test_reconcile_invalidates_caches_after_install(tmp_path, monkeypatch):
    """After a successful install/uninstall, reconcile drops import caches so the
    immediately-following entry-point discovery sees the change (no 2nd restart)."""
    import importlib

    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-rss\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda ns, py, *, constraints=None, requirement_line=None: 0,
    )

    calls = []
    monkeypatch.setattr(importlib, "invalidate_caches", lambda: calls.append(1))
    r.reconcile(cfg)
    assert calls  # invalidate_caches fired after the install


def test_reconcile_no_invalidate_when_nothing_changed(tmp_path, monkeypatch):
    """A pure no-op pass must not pay for a cache invalidation."""
    import importlib

    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"rss": "led-ticker-rss"})
    calls = []
    monkeypatch.setattr(importlib, "invalidate_caches", lambda: calls.append(1))
    r.reconcile(cfg)
    assert calls == []


# ── ensure_volume_venv recreate path (finding #7) ──────────────────────────────


def test_ensure_recreates_venv_when_stamp_mismatches(tmp_path):
    """Stamp present but wrong Python version -> rmtree + recreate + new stamp."""
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "stale_marker").write_text("x")
    (venv / ".python-version").write_text("3.0")  # deliberately wrong

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        venv.mkdir(exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0)

    ensure_volume_venv(venv, runner=fake_run)
    assert any("--system-site-packages" in c for c in calls)  # recreated
    assert not (venv / "stale_marker").exists()  # old tree was removed
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert (venv / ".python-version").read_text() == py_version  # fresh stamp


# ── volume python_exe used for install/uninstall (finding #8) ──────────────────


def test_reconcile_uses_target_python_exe_for_install(tmp_path, monkeypatch):
    """Install must shell out via the volume venv's python, not sys.executable."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
    target_py = "/data/plugins/venv/bin/python"
    monkeypatch.setattr(
        r, "resolve_target", lambda **k: r.Target("volume", target_py, None)
    )
    monkeypatch.setattr(r, "ensure_volume_venv", lambda venv_dir: None)
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})
    seen_py = []
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda ns, py, *, constraints=None, requirement_line=None: (
            seen_py.append(py) or 0
        ),
    )
    r.reconcile(cfg, volume_root=tmp_path / "vol")
    assert seen_py == [target_py]
    assert sys.executable not in seen_py


def test_reconcile_uses_target_python_exe_for_uninstall(tmp_path, monkeypatch):
    """Uninstall must shell out via the volume venv's python, not sys.executable."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
    target_py = "/data/plugins/venv/bin/python"
    monkeypatch.setattr(
        r, "resolve_target", lambda **k: r.Target("volume", target_py, None)
    )
    monkeypatch.setattr(r, "ensure_volume_venv", lambda venv_dir: None)
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {"old": "led-ticker-old"})
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)
    seen_py = []
    monkeypatch.setattr(r, "_uninstall_dist", lambda dist, py: seen_py.append(py) or 0)
    r.reconcile(cfg, volume_root=tmp_path / "vol")
    assert seen_py == [target_py]
    assert sys.executable not in seen_py


# ── multi-plugin failure isolation (finding #9) ────────────────────────────────


def test_reconcile_one_install_failure_does_not_block_others(tmp_path, monkeypatch):
    """One plugin's install failure must not prevent the others from proceeding."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss", "baseball"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    def fake_install(ns, py, *, constraints=None, requirement_line=None):
        return 1 if ns == "baseball" else 0

    monkeypatch.setattr(r, "_install_namespace", fake_install)
    actions = r.reconcile(cfg)
    by_ns = {a.namespace: a.action for a in actions}
    assert by_ns.get("rss") == "installed"
    assert by_ns.get("baseball") == "failed"


def test_reconcile_one_install_raise_does_not_block_others(tmp_path, monkeypatch):
    """A raising install (e.g. pip TimeoutExpired) is isolated per-plugin."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss", "baseball"})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    def fake_install(ns, py, *, constraints=None, requirement_line=None):
        if ns == "baseball":
            raise RuntimeError("pip hung")
        return 0

    monkeypatch.setattr(r, "_install_namespace", fake_install)
    actions = r.reconcile(cfg)
    by_ns = {a.namespace: a.action for a in actions}
    assert by_ns.get("rss") == "installed"
    assert by_ns.get("baseball") == "failed"


# ── finding #1: missing manifest must skip the whole reconcile ─────────────────


def test_reconcile_missing_manifest_uninstalls_nothing(tmp_path, monkeypatch):
    """A missing manifest means 'not opted in' — it must NOT be read as 'declare
    nothing' and pip-uninstall every installed plugin. (The log said 'skipping'
    but there was no return.)"""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")  # no requirements-plugins.txt beside it
    assert not (tmp_path / "requirements-plugins.txt").exists()

    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(
        r,
        "installed_plugin_dists",
        lambda: {"rss": "led-ticker-rss", "old": "led-ticker-old"},
    )
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)

    def boom(*a, **k):
        raise AssertionError("missing manifest must not install/uninstall anything")

    monkeypatch.setattr(r, "_uninstall_dist", boom)
    monkeypatch.setattr(r, "_install_namespace", boom)

    actions = r.reconcile(cfg)
    assert actions == []


# ── finding #2: git-source line for a pypi-default catalog plugin ──────────────


def test_declared_namespaces_git_source_resolves_to_catalog_namespace(tmp_path):
    """A `--source git` manifest line for a plugin whose catalog default is pypi
    must still resolve to the catalog namespace (no churn / wrong uninstall)."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    manifest = tmp_path / "requirements-plugins.txt"
    git_line = (
        "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
        "@pool-v0.1.0#subdirectory=plugins/pool"
    )
    manifest.write_text(git_line + "\n")
    assert r._declared_namespaces(cfg) == {"pool"}

    # unpinned (@main) form resolves too
    manifest.write_text(
        "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
        "@main#subdirectory=plugins/pool\n"
    )
    assert r._declared_namespaces(cfg) == {"pool"}


# ── finding #3: env freeze happens once per pass, not once per install ─────────


def test_reconcile_freezes_env_once_per_pass(tmp_path, monkeypatch):
    """Installing N plugins in one pass must run `pip list --format=freeze` once,
    not N times (the redundant freezes were on the dark-panel first-boot path)."""
    import led_ticker.app.plugin_cmd as pc
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(
        r, "_declared_namespaces", lambda p: {"rss", "baseball", "crypto"}
    )
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    freeze_calls = {"n": 0}

    def fake_freeze(python_exe=sys.executable):
        freeze_calls["n"] += 1
        return ("/tmp/constraints-fake.txt", 0)

    monkeypatch.setattr(pc, "_freeze_to_constraints", fake_freeze)

    constraints_seen: list = []

    def fake_pip_install(requirement, *, python_exe=sys.executable, constraints=None):
        constraints_seen.append(constraints)
        return 0

    monkeypatch.setattr(pc, "_pip_install", fake_pip_install)
    # Avoid unlink of the fake path.
    monkeypatch.setattr(r.Path, "unlink", lambda self, missing_ok=False: None)

    actions = r.reconcile(cfg)
    assert {a.action for a in actions} == {"installed"}
    assert freeze_calls["n"] == 1  # ONE freeze for three installs
    # All three installs reused the single pass-level constraints file.
    assert constraints_seen == ["/tmp/constraints-fake.txt"] * 3


# ── finding #5: never-raises covers ensure_volume_venv / scan failures ─────────


def test_reconcile_never_raises_on_venv_creation_failure(tmp_path, monkeypatch):
    """A disk-full / bad-perms volume makes ensure_volume_venv raise
    CalledProcessError; reconcile must still return [] without raising."""
    import led_ticker.plugin_reconcile as r

    monkeypatch.setattr(
        r, "resolve_target", lambda **k: r.Target("volume", "py", "/sp")
    )

    def boom(venv_dir):
        raise subprocess.CalledProcessError(1, "venv")

    monkeypatch.setattr(r, "ensure_volume_venv", boom)
    assert r.reconcile(tmp_path / "config.toml") == []


def test_reconcile_never_raises_on_installed_scan_failure(tmp_path, monkeypatch):
    """installed_plugin_dists raising must be swallowed by the outer guard."""
    import led_ticker.plugin_reconcile as r

    (tmp_path / "config.toml").write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-rss\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))

    def boom():
        raise RuntimeError("metadata exploded")

    monkeypatch.setattr(r, "installed_plugin_dists", boom)
    assert r.reconcile(tmp_path / "config.toml") == []


# ── finding #6: multi-plugin uninstall failure isolation ──────────────────────


def test_reconcile_one_uninstall_failure_does_not_block_others(tmp_path, monkeypatch):
    """One plugin's uninstall failure (nonzero exit) must not stop the others."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # declares nothing
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(
        r,
        "installed_plugin_dists",
        lambda: {"rss": "led-ticker-rss", "old": "led-ticker-old"},
    )
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)

    def fake_uninstall(dist, py):
        return 1 if dist == "led-ticker-rss" else 0

    monkeypatch.setattr(r, "_uninstall_dist", fake_uninstall)
    actions = r.reconcile(cfg)
    by_ns = {a.namespace: a.action for a in actions}
    assert by_ns.get("rss") == "failed"
    assert by_ns.get("old") == "uninstalled"


def test_reconcile_one_uninstall_raise_does_not_block_others(tmp_path, monkeypatch):
    """A raising uninstall (e.g. pip TimeoutExpired) is isolated per-plugin."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: set())
    monkeypatch.setattr(
        r,
        "installed_plugin_dists",
        lambda: {"rss": "led-ticker-rss", "old": "led-ticker-old"},
    )
    monkeypatch.setattr(r, "is_depended_on", lambda d: False)

    def fake_uninstall(dist, py):
        if dist == "led-ticker-rss":
            raise RuntimeError("pip hung")
        return 0

    monkeypatch.setattr(r, "_uninstall_dist", fake_uninstall)
    actions = r.reconcile(cfg)
    by_ns = {a.namespace: a.action for a in actions}
    assert by_ns.get("rss") == "failed"
    assert by_ns.get("old") == "uninstalled"


# ── manifest pin/source is honored by the install path (findings #1/#3) ────────


def test_reconcile_honors_manifest_pin(tmp_path, monkeypatch):
    """A pinned manifest line (led-ticker-pool==0.1.0) must be pip-installed AS
    WRITTEN — not re-derived as the catalog default (unversioned latest). The
    manifest is the source of truth for the version/source dimension."""
    import led_ticker.app.plugin_cmd as pc
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")  # no widget refs
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-pool==0.1.0\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    # pool is missing -> to_install; the real _declared_namespaces /
    # _declared_requirements run against the manifest above.
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    seen: list[str] = []

    def fake_pip_install(requirement, *, python_exe=sys.executable, constraints=None):
        seen.append(requirement)
        return 0

    monkeypatch.setattr(pc, "_pip_install", fake_pip_install)
    # _freeze_to_constraints would shell out to real pip; stub it.
    monkeypatch.setattr(
        pc, "_freeze_to_constraints", lambda py=sys.executable: (None, 0)
    )

    actions = r.reconcile(cfg)
    assert any(a.action == "installed" and a.namespace == "pool" for a in actions)
    # The exact pinned line, NOT the catalog default ("led-ticker-pool").
    assert seen == ["led-ticker-pool==0.1.0"]


def test_reconcile_honors_git_source_manifest_line(tmp_path, monkeypatch):
    """A git+url manifest line (e.g. `plugin add --source git`) installs as the
    operator wrote it, not the catalog's PyPI default."""
    import led_ticker.app.plugin_cmd as pc
    import led_ticker.plugin_reconcile as r

    git_line = "git+https://github.com/JamesAwesome/led-ticker-pool.git@v0.1.0"
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text(git_line + "\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    seen: list[str] = []
    monkeypatch.setattr(
        pc,
        "_pip_install",
        lambda req, *, python_exe=sys.executable, constraints=None: (
            seen.append(req) or 0
        ),
    )
    monkeypatch.setattr(
        pc, "_freeze_to_constraints", lambda py=sys.executable: (None, 0)
    )

    r.reconcile(cfg)
    assert seen == [git_line]


# ── finding #1: changed version pin on an already-installed plugin ─────────────


def test_reconcile_pin_change_on_installed_plugin(tmp_path, monkeypatch):
    """Editing an exact pin (0.1.0 -> 0.2.0) on an ALREADY-INSTALLED plugin and
    restarting must reinstall it in place. compute_diff is version-blind, so this
    would otherwise be a silent no-op (finding #1)."""
    import importlib.metadata

    import led_ticker.app.plugin_cmd as pc
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")  # no widget refs
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-pool==0.2.0\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    # pool is BOTH declared and installed -> not in the set-difference to_install.
    monkeypatch.setattr(
        r, "installed_plugin_dists", lambda: {"pool": "led-ticker-pool"}
    )
    # Installed version differs from the manifest pin.
    monkeypatch.setattr(
        importlib.metadata,
        "version",
        lambda dist: "0.1.0" if dist == "led-ticker-pool" else "9.9.9",
    )

    seen: list[str] = []
    monkeypatch.setattr(
        pc,
        "_pip_install",
        lambda req, *, python_exe=sys.executable, constraints=None: (
            seen.append(req) or 0
        ),
    )
    monkeypatch.setattr(
        pc, "_freeze_to_constraints", lambda py=sys.executable: (None, 0)
    )

    actions = r.reconcile(cfg)
    # Reinstalled in place with the NEW pinned line, recorded as an install.
    assert seen == ["led-ticker-pool==0.2.0"]
    assert any(a.action == "installed" and a.namespace == "pool" for a in actions)


def test_reconcile_matching_pin_on_installed_plugin_not_reinstalled(
    tmp_path, monkeypatch
):
    """When the manifest pin equals the installed version, no reinstall (finding #1)."""
    import importlib.metadata

    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-pool==0.1.0\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(
        r, "installed_plugin_dists", lambda: {"pool": "led-ticker-pool"}
    )
    monkeypatch.setattr(importlib.metadata, "version", lambda dist: "0.1.0")
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not reinstall")),
    )
    actions = r.reconcile(cfg)
    assert actions == []


def test_reconcile_unpinned_installed_plugin_not_reinstalled(tmp_path, monkeypatch):
    """An UNPINNED already-installed plugin must NOT be churned on a restart — a
    restart can't tell whether the source moved (finding #1). Only a real INFO
    log is emitted; the install path is never touched."""
    import importlib.metadata

    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("led-ticker-pool\n")  # unpinned
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(
        r, "installed_plugin_dists", lambda: {"pool": "led-ticker-pool"}
    )
    # Even if the "installed" version differs from some hypothetical latest, an
    # unpinned line yields no pin to compare against -> no reinstall.
    monkeypatch.setattr(importlib.metadata, "version", lambda dist: "0.1.0")
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not reinstall")),
    )
    actions = r.reconcile(cfg)
    assert actions == []


def test_reconcile_git_source_installed_plugin_not_reinstalled(tmp_path, monkeypatch):
    """A git/URL already-installed plugin is not pin-comparable -> not churned."""
    import importlib.metadata

    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    git_line = (
        "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
        "@main#subdirectory=plugins/pool"
    )
    (tmp_path / "requirements-plugins.txt").write_text(git_line + "\n")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(
        r, "installed_plugin_dists", lambda: {"pool": "led-ticker-pool"}
    )
    monkeypatch.setattr(importlib.metadata, "version", lambda dist: "0.1.0")
    monkeypatch.setattr(
        r,
        "_install_namespace",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not reinstall")),
    )
    actions = r.reconcile(cfg)
    assert actions == []


def test_install_namespace_falls_back_to_catalog_without_line():
    """With no manifest line, _install_namespace re-derives from the catalog
    (back-compat: a namespace surfaced without an originating line)."""
    import led_ticker.app.plugin_cmd as pc
    import led_ticker.plugin_reconcile as r

    seen: list[str] = []
    orig = pc._pip_install
    try:
        pc._pip_install = lambda req, *, python_exe=sys.executable, constraints=None: (
            seen.append(req) or 0
        )
        r._install_namespace("pool", "py", requirement_line=None)
    finally:
        pc._pip_install = orig
    # Catalog default for pool is the bare PyPI name.
    assert seen == ["led-ticker-pool"]


# ── pass-level freeze failure falls back to per-install freeze (finding #7) ─────


def test_reconcile_freeze_nonzero_falls_back_to_per_install(tmp_path, monkeypatch):
    """When the pass-level freeze exits non-zero (returns (None, rc)), the pending
    installs still proceed, each with constraints=None (its own per-install freeze)."""
    import led_ticker.app.plugin_cmd as pc
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")  # manifest present
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss", "baseball"})
    monkeypatch.setattr(r, "_declared_requirements", lambda p: {})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})
    monkeypatch.setattr(
        pc, "_freeze_to_constraints", lambda py=sys.executable: (None, 1)
    )

    constraints_seen: list = []
    monkeypatch.setattr(
        pc,
        "_pip_install",
        lambda req, *, python_exe=sys.executable, constraints=None: (
            constraints_seen.append(constraints) or 0
        ),
    )

    actions = r.reconcile(cfg)
    assert {a.action for a in actions} == {"installed"}
    # Both installs proceeded with no pass-level constraints file.
    assert constraints_seen == [None, None]


def test_reconcile_freeze_raise_falls_back_to_per_install(tmp_path, monkeypatch):
    """When the pass-level freeze RAISES (e.g. TimeoutExpired), the except branch
    sets shared_constraints=None and the installs still proceed."""
    import led_ticker.app.plugin_cmd as pc
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text("")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "_declared_namespaces", lambda p: {"rss", "baseball"})
    monkeypatch.setattr(r, "_declared_requirements", lambda p: {})
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})

    def boom_freeze(py=sys.executable):
        raise subprocess.TimeoutExpired("pip", 1)

    monkeypatch.setattr(pc, "_freeze_to_constraints", boom_freeze)

    constraints_seen: list = []
    monkeypatch.setattr(
        pc,
        "_pip_install",
        lambda req, *, python_exe=sys.executable, constraints=None: (
            constraints_seen.append(constraints) or 0
        ),
    )

    actions = r.reconcile(cfg)
    assert {a.action for a in actions} == {"installed"}
    assert constraints_seen == [None, None]


# ── Finding A: non-UTF-8 files must not escape the never-raises contracts ───────


def _write_non_utf8(path):
    # 0xff is invalid as a UTF-8 start byte -> read_text(encoding="utf-8") raises
    # UnicodeDecodeError (a ValueError, NOT an OSError).
    path.write_bytes(b"\xff\xfe bad bytes not utf-8")


def test_referenced_namespaces_non_utf8_returns_empty(tmp_path, caplog):
    import logging

    cfg = tmp_path / "config.toml"
    _write_non_utf8(cfg)
    with caplog.at_level(logging.WARNING):
        assert referenced_namespaces(cfg) == set()
    assert any("not valid UTF-8" in record.message for record in caplog.records)


def test_declared_requirements_non_utf8_manifest_returns_empty(tmp_path, caplog):
    import logging

    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    _write_non_utf8(tmp_path / "requirements-plugins.txt")
    with caplog.at_level(logging.WARNING):
        assert r._declared_requirements(cfg) == {}
    assert any("unreadable" in record.message for record in caplog.records)


def test_reconcile_non_utf8_manifest_does_not_raise(tmp_path, monkeypatch, caplog):
    import logging

    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    _write_non_utf8(tmp_path / "requirements-plugins.txt")
    monkeypatch.setattr(r, "resolve_target", lambda **k: r.Target("venv", "py", None))
    monkeypatch.setattr(r, "installed_plugin_dists", lambda: {})
    # Must return [] (the bad-manifest path yields empty declared) and never raise.
    with caplog.at_level(logging.WARNING):
        assert r.reconcile(cfg) == []
    assert any("unreadable" in record.message for record in caplog.records)


# ── Finding D: _exact_pin parametrized contract ────────────────────────────────


@pytest.mark.parametrize(
    "line,expected",
    [
        ("led-ticker-pool==0.1.0", "0.1.0"),
        ("led-ticker-pool==0.1.0 ; python_version>='3.10'", "0.1.0"),
        ("led-ticker-pool", None),  # unpinned
        ("led-ticker-pool>=0.1.0", None),  # range, not exact
        ("git+https://example.com/p.git", None),  # vcs source
        ("led-ticker-pool==1.2.0,<2.0", None),  # compound — not an exact pin
        ("led-ticker-pool==", None),  # empty after ==
    ],
)
def test_exact_pin(line, expected):
    import led_ticker.plugin_reconcile as r

    assert r._exact_pin(line) == expected


# ── Finding B: apply_volume_visibility ─────────────────────────────────────────


def test_apply_volume_visibility_inserts_existing_site_packages(tmp_path, monkeypatch):
    import led_ticker.plugin_reconcile as r

    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    sp = tmp_path / "venv" / "lib" / f"python{py}" / "site-packages"
    sp.mkdir(parents=True)

    saved = list(sys.path)
    try:
        # Pin the invalidate_caches() call: monkeypatch it to count invocations.
        invalidate_calls = []
        monkeypatch.setattr(
            r.importlib, "invalidate_caches", lambda: invalidate_calls.append(1)
        )

        r.apply_volume_visibility(volume_root=tmp_path)
        assert str(sp) in sys.path
        assert len(invalidate_calls) == 1, (
            "invalidate_caches should be called once on first insert"
        )

        # Idempotent — a second call does not duplicate the entry and does NOT
        # call invalidate_caches.
        r.apply_volume_visibility(volume_root=tmp_path)
        assert sys.path.count(str(sp)) == 1
        assert len(invalidate_calls) == 1, (
            "invalidate_caches should NOT be called on idempotent second call"
        )
    finally:
        sys.path[:] = saved


def test_apply_volume_visibility_noop_when_absent(tmp_path):
    import led_ticker.plugin_reconcile as r

    saved = list(sys.path)
    try:
        r.apply_volume_visibility(volume_root=tmp_path)  # no venv dir present
        assert sys.path == saved
    finally:
        sys.path[:] = saved


# ── storefront flap regression (overlay-only plugin uninstalled every other
# boot) ─────────────────────────────────────────────────────────────────────
#
# Reproduction: a manifest line for the new `storefront` plugin resolved to the
# DIST name (`led-ticker-storefront`), not the entry-point namespace
# (`storefront`), because no catalog entry mapped it — so `_declared_namespaces`
# disagreed with `installed_plugin_dists()` (keyed by namespace) every boot.
# AND `referenced_namespaces` only walks widget/transition `type` strings, so a
# top-level `[storefront]` overlay block (no `type =` anywhere) was invisible to
# the uninstall guard. Both gaps let compute_diff emit the SAME plugin in both
# to_install and to_uninstall in one pass. Fix 1: catalog entry (namespace
# resolution). Fix 2: overlay blocks count as referenced (defense in depth).


def test_declared_namespaces_storefront_pep508_line_resolves_to_namespace(tmp_path):
    """The exact repro line: `name @ git+url#subdirectory=...` (PEP 508 direct
    reference form). Without the catalog entry this resolves to the dedup key
    `led-ticker-storefront` (the space before `@ git+` short-circuits
    `_requirement_key`'s pypi-branch parse) and stays UNMAPPED to the
    `storefront` namespace — the flap. With the catalog entry present, the pypi
    source's key is also `led-ticker-storefront`, so it now maps to `storefront`."""
    import led_ticker.plugin_reconcile as r

    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text(
        "led-ticker-storefront @ git+https://github.com/JamesAwesome/"
        "led-ticker-plugins.git@f41eeb7780d1a2726616385ccc5e690f5f3ca81e"
        "#subdirectory=plugins/storefront\n"
    )
    config = tmp_path / "config.toml"
    config.write_text("")

    assert "storefront" in r._declared_namespaces(config)


def test_declared_namespaces_storefront_bare_git_url_resolves_to_namespace(tmp_path):
    """The bare `git+url#subdirectory=...` form (no leading `name @`) parses via
    `_requirement_key`'s git branch to the dedup key
    `led-ticker-plugins#plugins/storefront` — this must ALSO map to `storefront`
    via the catalog's git source (not just the pypi source in the test above)."""
    import led_ticker.plugin_reconcile as r

    manifest = tmp_path / "requirements-plugins.txt"
    manifest.write_text(
        "git+https://github.com/JamesAwesome/led-ticker-plugins.git@main"
        "#subdirectory=plugins/storefront\n"
    )
    config = tmp_path / "config.toml"
    config.write_text("")

    assert "storefront" in r._declared_namespaces(config)


def test_referenced_namespaces_reads_top_level_overlay_block(tmp_path):
    """An overlay-only plugin's `[<namespace>]` config block (e.g. `[storefront]`)
    has no widget/transition `type` string ANYWHERE in the config — the existing
    dotted-value walk can never see it. The top-level-key scan must report it
    as referenced so the uninstall guard blocks pruning it."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text('[storefront]\ncorner = "top_right"\n')
    refs = r.referenced_namespaces(cfg)
    assert "storefront" in refs
    reason = r.uninstall_blocked_reason("storefront", "led-ticker-storefront", refs)
    assert reason is not None


def test_referenced_namespaces_core_owned_blocks_are_not_reported(tmp_path):
    """[display], [web], etc. are core-owned top-level tables — a plugin will
    never be named after one, so they must NOT count as referenced namespaces
    (that would make the guard block uninstalling a plugin actually named e.g.
    "web", which doesn't exist, but more importantly proves the exclusion set
    is honored rather than every top-level key being swept in unconditionally)."""
    import led_ticker.plugin_reconcile as r

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[display]\nrows = 16\n[web]\nenabled = true\n[busy_light]\nenabled = false\n"
    )
    refs = r.referenced_namespaces(cfg)
    assert refs.isdisjoint({"display", "web", "busy_light"})

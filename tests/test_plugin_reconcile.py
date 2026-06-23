import sys

from led_ticker.plugin_reconcile import PluginAction, compute_diff, resolve_target


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

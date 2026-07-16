import textwrap
import threading
import time

import pytest

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


def test_read_plugins_config_propagates_toml_syntax_error(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[[[ not valid toml")
    with pytest.raises(ValueError):  # tomllib.TOMLDecodeError is a ValueError subclass
        L.read_plugins_config(p)


def test_read_plugins_config_still_defaults_on_missing_file(tmp_path):
    pc = L.read_plugins_config(tmp_path / "nope.toml")
    assert pc.enabled is True and pc.dir == "plugins"


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


def test_read_plugins_config_propagates_structural_error(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[display]\nrows=16\ncols=64\n[plugins]\nenabled = 1\n")
    with pytest.raises(ValueError, match="plugins.enabled must be a bool"):
        L.read_plugins_config(p)


def test_load_plugins_concurrent_first_load_runs_once(tmp_path, monkeypatch):
    """Regression for the adversarial-review first-load race: two threads
    calling ``load_plugins`` concurrently on a cold ``_LOADED`` must run the
    discover+register+commit body exactly once and both must get back the
    same result object.

    Before the ``_LOAD_LOCK`` double-checked-locking fix, the lock-free
    ``if _LOADED is not None: return _LOADED`` guard did nothing to stop two
    near-simultaneous FIRST callers (e.g. two webui to_thread validates on a
    cold process) from both passing the check and racing the full body —
    reproduced symptoms were a partially-committed registry, "already
    registered" errors, a local plugin module exec'd twice, and a
    last-writer-wins ``_LOADED``.

    ``_discover_local`` is wrapped to (a) count invocations and (b) sleep
    briefly, widening the window between the lock-free peek and the
    lock-guarded body so two near-simultaneous callers reliably overlap
    instead of serializing by luck alone.
    """
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    _write(pdir, "acme")

    discover_calls: list[None] = []
    real_discover = L._discover_local

    def slow_discover(plugin_dir):
        discover_calls.append(None)
        time.sleep(0.05)
        return real_discover(plugin_dir)

    monkeypatch.setattr(L, "_discover_local", slow_discover)

    barrier = threading.Barrier(2)
    results: list[L.LoadedPlugins] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        try:
            result = L.load_plugins(pdir, entry_points_enabled=False)
        except BaseException as e:  # noqa: BLE001 - surfaced via assertion below
            with lock:
                errors.append(e)
            return
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, errors
        assert len(results) == 2
        assert len(discover_calls) == 1, (
            f"discover ran {len(discover_calls)} times; expected exactly one "
            "load under concurrent first-load callers"
        )
        assert results[0] is results[1], "both callers must see the same result"
        assert results[0].failed == []
        assert {info.namespace for info in results[0].loaded} == {"acme"}
    finally:
        L.reset_plugins()

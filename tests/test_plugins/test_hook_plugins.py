import asyncio
import logging
import textwrap

import pytest

from led_ticker import _plugin_loader as L


def _write_plugin(plugin_dir, name, body):
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / f"{name}.py").write_text(textwrap.dedent(body))


def test_loader_collects_hooks_tagged_with_namespace(tmp_path):
    L.reset_plugins()
    _write_plugin(
        tmp_path / "plugins",
        "acme",
        """
        def register(api):
            api.overlay(lambda canvas: None)
            api.on_startup(lambda ctx: None)
            api.on_shutdown(lambda: None)
        """,
    )
    try:
        result = L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        assert not result.failed, result.failed
        assert [ns for ns, _ in result.overlays] == ["acme"]
        assert [ns for ns, _ in result.startup_hooks] == ["acme"]
        assert [ns for ns, _ in result.shutdown_hooks] == ["acme"]
    finally:
        L.reset_plugins()


def test_failed_plugin_contributes_no_hooks(tmp_path):
    L.reset_plugins()
    _write_plugin(
        tmp_path / "plugins",
        "bad",
        """
        def register(api):
            api.overlay(lambda canvas: None)
            raise RuntimeError("boom")
        """,
    )
    try:
        result = L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        assert any(ns == "bad" for ns, _ in result.failed)
        assert result.overlays == []
    finally:
        L.reset_plugins()


def test_guarded_overlay_disables_and_logs_once_on_raise(caplog):
    calls = {"n": 0}

    def boom(canvas):
        calls["n"] += 1
        raise ValueError("nope")

    guarded = L._guarded_overlay("acme", boom)
    with caplog.at_level(logging.ERROR):
        guarded("canvas-1")  # raises internally -> caught, disabled, logged
        guarded("canvas-2")  # already disabled -> no-op, no call
        guarded("canvas-3")
        guarded("canvas-4")
    assert calls["n"] == 1  # the painter ran once, then was disabled
    msgs = [r.getMessage() for r in caplog.records]
    assert sum("overlay" in m and "acme" in m for m in msgs) == 1  # logged once


def test_guarded_overlay_passes_through_when_ok():
    seen = []
    guarded = L._guarded_overlay("acme", lambda canvas: seen.append(canvas))
    guarded("c1")
    guarded("c2")
    assert seen == ["c1", "c2"]


def test_run_startup_hooks_sync_and_async_and_isolated(caplog):
    order = []

    def sync_hook(ctx):
        order.append(("sync", ctx))

    async def async_hook(ctx):
        order.append(("async", ctx))

    def boom(ctx):
        raise RuntimeError("startup boom")

    hooks = [("a", sync_hook), ("b", async_hook), ("c", boom)]
    with caplog.at_level(logging.ERROR):
        asyncio.run(L._run_startup_hooks(hooks, "CTX"))
    assert order == [("sync", "CTX"), ("async", "CTX")]
    assert any("on_startup" in r.getMessage() and "c" in r.getMessage()
               for r in caplog.records)


def test_run_shutdown_hooks_sync_and_async_and_isolated(caplog):
    order = []

    def sync_hook():
        order.append("sync")

    async def async_hook():
        order.append("async")

    def boom():
        raise RuntimeError("shutdown boom")

    hooks = [("a", sync_hook), ("b", async_hook), ("c", boom)]
    with caplog.at_level(logging.ERROR):
        asyncio.run(L._run_shutdown_hooks(hooks))
    assert order == ["sync", "async"]
    assert any("on_shutdown" in r.getMessage() and "c" in r.getMessage()
               for r in caplog.records)


def test_run_shutdown_hooks_cancellederror_is_not_swallowed():
    async def bad_hook():
        raise asyncio.CancelledError("from plugin")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(L._run_shutdown_hooks([("bad", bad_hook)]))


def test_loader_collects_multiple_overlays_from_one_plugin(tmp_path):
    L.reset_plugins()
    _write_plugin(
        tmp_path / "plugins",
        "multi",
        """
        def register(api):
            api.overlay(lambda c: None)
            api.overlay(lambda c: None)
        """,
    )
    try:
        result = L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        assert [ns for ns, _ in result.overlays] == ["multi", "multi"]
    finally:
        L.reset_plugins()


def test_run_startup_hooks_async_failure_is_isolated(caplog):
    order = []

    async def async_boom(ctx):
        raise RuntimeError("async startup boom")

    async def ok_after(ctx):
        order.append("ok")

    hooks = [("bad", async_boom), ("after", ok_after)]
    with caplog.at_level(logging.ERROR):
        asyncio.run(L._run_startup_hooks(hooks, "CTX"))
    assert order == ["ok"]  # a raising async hook does not stop later hooks
    assert any("on_startup" in r.getMessage() and "bad" in r.getMessage()
               for r in caplog.records)


def test_run_shutdown_hooks_async_failure_is_isolated(caplog):
    order = []

    async def async_boom():
        raise RuntimeError("async shutdown boom")

    async def ok_after():
        order.append("ok")

    hooks = [("bad", async_boom), ("after", ok_after)]
    with caplog.at_level(logging.ERROR):
        asyncio.run(L._run_shutdown_hooks(hooks))
    assert order == ["ok"]
    assert any("on_shutdown" in r.getMessage() and "bad" in r.getMessage()
               for r in caplog.records)


def test_commit_failure_contributes_no_hooks(tmp_path):
    from led_ticker.widgets import _WIDGET_REGISTRY

    L.reset_plugins()
    # Pre-seed the registry so the plugin's widget commit collides, making
    # _commit raise AFTER register() already buffered an overlay + hooks.
    _WIDGET_REGISTRY["svc.thing"] = object()
    _write_plugin(
        tmp_path / "plugins",
        "svc",
        """
        def register(api):
            @api.widget("thing")
            class Thing:
                pass
            api.overlay(lambda canvas: None)
            api.on_startup(lambda ctx: None)
        """,
    )
    try:
        result = L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        assert any(ns == "svc" for ns, _ in result.failed), result.loaded
        assert result.overlays == []
        assert result.startup_hooks == []
    finally:
        _WIDGET_REGISTRY.pop("svc.thing", None)
        L.reset_plugins()

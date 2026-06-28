"""Tripwire test: load_plugins_for_config must precede build_frame_from_config.

This ensures that plugin-registered backends are available when the engine
selects/builds a backend (constraint: plugins must register before frame builds).
"""

import importlib
import inspect


def test_load_plugins_precedes_backend_build():
    """A plugin backend must be registered (load_plugins) before the engine
    selects/builds it (build_frame_from_config). Lock the source order so a
    refactor can't reverse it."""
    run_module = importlib.import_module("led_ticker.app.run")
    src = inspect.getsource(run_module.run)
    i_load = src.index("_load_plugins_for_config(")
    i_build = src.index("build_frame_from_config(")
    assert i_load < i_build, (
        "load_plugins must precede build_frame_from_config so a plugin-registered "
        "backend is available when the engine selects it"
    )

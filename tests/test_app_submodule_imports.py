"""Smoke tests: backward-compatible import paths from the Large #1 app.py split.

These verify that the re-exported symbols in led_ticker.app still work after
the split into app/cli.py, app/factories.py, app/coercion.py, app/run.py.
"""

import importlib
import inspect

import pytest


@pytest.mark.parametrize(
    "module, symbol, type_check",
    [
        # factories
        ("led_ticker.app.factories", "RANDOM_COLOR", "itertools.cycle"),
        ("led_ticker.app.factories", "RUN_MODES", "dict"),
        ("led_ticker.app.factories", "_build_widget", "callable"),
        ("led_ticker.app.factories", "build_frame_from_config", "callable"),
        # coercion
        ("led_ticker.app.coercion", "_COLOR_KEYS", "set"),
        ("led_ticker.app.coercion", "_WIDGET_INT_FIELDS", "frozenset"),
        ("led_ticker.app.coercion", "_coerce_color_provider", "callable"),
        ("led_ticker.app.coercion", "_validate_rgb", "callable"),
        # cli
        ("led_ticker.app.cli", "_setup_logging", "callable"),
        ("led_ticker.app.cli", "main", "callable"),
        # run
        ("led_ticker.app.run", "run", "coroutinefunction"),
    ],
)
def test_symbol_importable_from_submodule(module, symbol, type_check):
    """Verify each symbol is importable from its submodule and has the correct type."""
    mod = importlib.import_module(module)
    obj = getattr(mod, symbol)

    if type_check == "callable":
        assert callable(obj), f"{module}.{symbol} should be callable"
    elif type_check == "coroutinefunction":
        assert inspect.iscoroutinefunction(
            obj
        ), f"{module}.{symbol} should be a coroutinefunction"
    elif type_check == "itertools.cycle":
        import itertools

        assert isinstance(
            obj, itertools.cycle
        ), f"{module}.{symbol} should be itertools.cycle"
    elif type_check == "dict":
        assert isinstance(obj, dict), f"{module}.{symbol} should be a dict"
    elif type_check == "set":
        assert isinstance(obj, set), f"{module}.{symbol} should be a set"
    elif type_check == "frozenset":
        assert isinstance(obj, frozenset), f"{module}.{symbol} should be a frozenset"


@pytest.mark.parametrize(
    "symbol, type_check",
    [
        # factories re-exports on app
        ("_build_widget", "callable"),
        ("build_frame_from_config", "callable"),
        # coercion re-exports on app
        ("_COLOR_KEYS", "set"),
        ("_coerce_color_provider", "callable"),
        # cli re-exports on app
        ("main", "callable"),
        # run re-exports on app
        ("run", "coroutinefunction"),
    ],
)
def test_symbol_importable_from_app(symbol, type_check):
    """Verify backward-compat: symbols remain importable from led_ticker.app."""
    from led_ticker import app

    obj = getattr(app, symbol)

    if type_check == "callable":
        assert callable(obj), f"led_ticker.app.{symbol} should be callable"
    elif type_check == "coroutinefunction":
        assert inspect.iscoroutinefunction(
            obj
        ), f"led_ticker.app.{symbol} should be a coroutinefunction"
    elif type_check == "set":
        assert isinstance(obj, set), f"led_ticker.app.{symbol} should be a set"

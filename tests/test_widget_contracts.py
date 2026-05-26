"""Contract tests for widget interface invariants.

These tests use introspection to verify that every class in the led_ticker
package that implements a given method honours the engine's calling convention.
They catch hand-rolled implementations that deviate from the mixin contract
without requiring the class to be instantiated.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil


def _all_own_advance_frame_methods():
    """Yield (qualname, module, method) for every class in the led_ticker
    package that defines advance_frame directly in its own __dict__."""
    import led_ticker

    for _finder, modname, _ispkg in pkgutil.walk_packages(
        path=led_ticker.__path__,
        prefix=f"{led_ticker.__name__}.",
        onerror=lambda _name: None,
    ):
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        for _name, cls in inspect.getmembers(mod, inspect.isclass):
            if cls.__module__ != modname:
                continue  # skip re-exports; test each class in its home module only
            method = cls.__dict__.get("advance_frame")
            if method is None:
                continue  # inherited — parent already covered
            yield cls.__qualname__, modname, method


def test_advance_frame_accepts_visit_id_kwarg():
    """Every advance_frame implementation must accept *, visit_id: int | None = None.

    ticker._advance_frame_if_supported calls advance_frame(visit_id=N) on any
    object that has the method. A hand-rolled implementation without the kwarg
    raises TypeError on the first hold tick.
    """
    violations: list[str] = []
    for qualname, modname, method in _all_own_advance_frame_methods():
        try:
            sig = inspect.signature(method)
        except (ValueError, TypeError):
            continue  # can't inspect (e.g. C extension stub) — skip
        if "visit_id" not in sig.parameters:
            violations.append(f"{qualname}  ({modname})")

    assert not violations, (
        "advance_frame() must accept `*, visit_id: int | None = None`.\n"
        "ticker._advance_frame_if_supported passes visit_id=N on every call;\n"
        "missing in:\n  " + "\n  ".join(violations)
    )

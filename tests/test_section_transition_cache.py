"""A section's transition is built ONCE and reused across passes.

Regression: `app/run.py` used to call `_build_trans_obj_guarded(section.transition)`
on every section entry, so a stateful transition (`wipe_alternating`,
`push_alternating`, plugin `.alternating` / `.random` variants) was a fresh
instance each time and its variant counter reset — the section always entered
with the first variant. `[transitions] between_sections` was built once and
cycled correctly; section-level transitions now match it.
"""

import ast
import importlib
import inspect
from unittest.mock import MagicMock

from led_ticker.config import TransitionConfig
from led_ticker.transitions.wipe import WipeAlternating

run_mod = importlib.import_module("led_ticker.app.run")


def test_same_config_returns_same_instance():
    cache: dict = {}
    cfg = TransitionConfig(type="wipe_alternating")
    first = run_mod._cached_trans_obj(cache, cfg)
    second = run_mod._cached_trans_obj(cache, cfg)
    assert isinstance(first, WipeAlternating)
    assert second is first


def test_alternating_cycles_across_section_entries():
    """Two entries of the same section fire different wipe variants."""
    cache: dict = {}
    cfg = TransitionConfig(type="wipe_alternating")
    canvas = MagicMock(width=32, height=16)
    widget = MagicMock()
    widget.draw.return_value = (canvas, 0)
    picked = []
    for _ in range(2):  # two section entries
        trans = run_mod._cached_trans_obj(cache, cfg)
        for t in (0.0, 0.5, 1.0):  # one firing
            trans.frame_at(t, canvas, widget, widget)
        picked.append(type(trans._transitions[trans._index]).__name__)
    assert picked == ["WipeLeft", "WipeRight"]


def test_distinct_configs_get_distinct_instances():
    cache: dict = {}
    a = run_mod._cached_trans_obj(cache, TransitionConfig(type="wipe_alternating"))
    b = run_mod._cached_trans_obj(cache, TransitionConfig(type="wipe_alternating"))
    assert a is not b


def test_cut_caches_none():
    cache: dict = {}
    cfg = TransitionConfig(type="cut")
    assert run_mod._cached_trans_obj(cache, cfg) is None
    assert run_mod._cached_trans_obj(cache, cfg) is None


def test_run_loop_never_builds_section_transitions_uncached():
    """AST tripwire: inside `run()`, `_build_trans_obj_guarded` is only called
    on `between_sections` (built once). Every per-section build goes through
    `_cached_trans_obj`, or a stateful transition's counter resets per entry."""
    tree = ast.parse(inspect.getsource(run_mod.run))
    offenders = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_build_trans_obj_guarded"
        ):
            arg = ast.unparse(node.args[0]) if node.args else ""
            if not arg.endswith("between_sections"):
                offenders.append(arg)
    assert offenders == []

"""Meta-tripwire: every per-tick redraw loop in `ticker.py` must call
`_advance_frame_if_supported`.

The "rainbow renders as static gradient" bug class kept resurfacing
because each redraw loop in the engine is a separate site that
independently must remember to tick the frame counter. We've patched
six sites incrementally (`_swap_and_scroll`, `_scroll_and_delay` ×2,
`_scroll_one_by_one`, `_scroll_side_by_side`, `_play_with_text`).

This test prevents the next regression by AST-scanning `ticker.py`
itself: for every async function in the engine, find every loop body
containing a `widget.draw(...)` call. Assert the same loop body also
contains an `_advance_frame_if_supported(...)` call. Functions in
`ALLOW_LIST` are exempt with documented justification (only transition
compositors that explicitly pause frame instead).

If this test fails, EITHER:
  - Add `_advance_frame_if_supported(widget)` per tick in the loop, OR
  - Add the function to ALLOW_LIST with a comment explaining why pause
    is in effect (e.g. transition compositor with explicit pause/resume).
"""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE_PATH = Path(__file__).parent.parent / "src" / "led_ticker" / "ticker.py"


# Functions whose redraw loops are intentionally NOT frame-advancing
# because pause_frame is in effect for the duration. Keep this list
# short and well-justified — every entry should have a comment
# explaining the exemption.
ALLOW_LIST: dict[str, str] = {
    # Transition compositor — calls outgoing.pause_frame() /
    # incoming.pause_frame() at entry and resume_frame() in a finally
    # block. Frame is logically paused for the whole loop body, so
    # advancing inside would defeat the pause.
    "_scroll_between": (
        "transition compositor; explicit pause_frame at entry, "
        "resume_frame in finally"
    ),
}


_LoopNode = ast.While | ast.For | ast.AsyncFor


def _is_loop(node: ast.AST) -> bool:
    return isinstance(node, ast.While | ast.For | ast.AsyncFor)


def _has_advance_call(node: ast.AST) -> bool:
    """Whether `node`'s subtree calls `_advance_frame_if_supported(...)`."""
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_advance_frame_if_supported"
        for n in ast.walk(node)
    )


def _has_draw_call_direct(node: ast.AST) -> bool:
    """Whether `node`'s subtree calls `*.draw(...)` (an attribute call,
    not a function call). Used to identify redraw loops."""
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "draw"
        for n in ast.walk(node)
    )


def _enclosing_loops(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef, target: ast.AST
) -> list[ast.AST]:
    """Return all loop nodes in `func_node` that enclose `target`.

    A loop encloses `target` if `target` is inside one of the loop's
    body / orelse / handlers. The current node is NOT included.
    """
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(func_node):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    enclosing: list[ast.AST] = []
    cursor: ast.AST | None = parents.get(id(target))
    while cursor is not None and cursor is not func_node:
        if _is_loop(cursor):
            enclosing.append(cursor)
        cursor = parents.get(id(cursor))
    return enclosing


def _function_has_advance_in_loops(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    """Return a list of issues — empty means the function is compliant.

    A loop is compliant if EITHER it OR any enclosing loop in the same
    function calls `_advance_frame_if_supported`. Inner loops nested
    inside an advancing outer loop are exempt because they're part of
    the same tick — the outer loop's advance covers them.

    Loops without any `.draw(...)` call are skipped (not redraw loops).
    """
    issues: list[str] = []
    for node in ast.walk(func_node):
        if not _is_loop(node):
            continue
        if not _has_draw_call_direct(node):
            continue
        # Compliant if this loop advances OR any enclosing loop does.
        if _has_advance_call(node):
            continue
        if any(_has_advance_call(loop) for loop in _enclosing_loops(func_node, node)):
            continue
        issues.append(
            f"loop at line {node.lineno} draws but does not call "
            f"_advance_frame_if_supported (and no enclosing loop does)"
        )
    return issues


def test_every_redraw_loop_advances_frame():
    """Scan ticker.py AST. Every function with a redraw loop must
    advance the frame counter, OR be on the allow-list."""
    tree = ast.parse(ENGINE_PATH.read_text())
    failures: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name in ALLOW_LIST:
            continue
        for issue in _function_has_advance_in_loops(node):
            failures.append(f"{node.name}: {issue}")

    assert not failures, (
        "Engine redraw loops missing _advance_frame_if_supported calls:\n"
        "  - " + "\n  - ".join(failures) + "\n\nFix options:\n"
        "  1. Add `_advance_frame_if_supported(widget)` per tick in "
        "the loop (preferred — animated providers like rainbow will "
        "animate during the redraw).\n"
        "  2. If the loop is a transition compositor and frame should "
        "stay paused, add explicit pause_frame() at entry + "
        "resume_frame() in finally, then add the function name to "
        "ALLOW_LIST in this test file with a comment explaining why."
    )


def test_allow_list_entries_actually_pause_frame():
    """Allow-listed functions must call pause_frame on the widgets
    they redraw. Without this, the allow-list would be a foot-gun —
    naming a function "exempt" without it actually freezing frame.
    """
    tree = ast.parse(ENGINE_PATH.read_text())
    failures: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name not in ALLOW_LIST:
            continue
        # Look for pause_frame() calls anywhere in the function body.
        pause_calls = [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "pause_frame"
        ]
        if not pause_calls:
            failures.append(
                f"{node.name} is allow-listed but does not call "
                f"`pause_frame()`. Allow-list reason: {ALLOW_LIST[node.name]!r}. "
                f"Either add pause_frame at entry + resume_frame in finally, "
                f"or remove from ALLOW_LIST."
            )

    assert not failures, "\n  - ".join(["Allow-list violations:"] + failures)

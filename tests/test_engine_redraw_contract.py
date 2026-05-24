"""Meta-tripwire: every per-tick redraw loop in `ticker.py` must call
`_advance_frame_if_supported`.

The "rainbow renders as static gradient" bug class kept resurfacing
because each redraw loop in the engine is a separate site that
independently must remember to tick the frame counter. We've patched
six sites incrementally (`_swap_and_scroll`, `_scroll_and_delay` ×2,
`_scroll_one_by_one`, `_scroll_side_by_side`, `_play_with_text`).

This test prevents the next regression by AST-scanning `ticker.py`
itself: for every async function in the engine, find every loop body
containing a `_swap(...)` or `*.SwapOnVSync(...)` call. Assert the
same loop body also contains an `_advance_frame_if_supported(...)`
call. We use the swap call as the signal (rather than `widget.draw`)
because it's the canonical tick boundary — refactors that extract
draw+swap into a helper still surface the swap, while a `widget.draw`
scan would silently pass loops where the draw is hidden behind a
helper call.

Functions in `ALLOW_LIST` are exempt with documented justification
(only transition compositors that explicitly pause frame instead).

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
        "transition compositor; explicit pause_frame at entry, resume_frame in finally"
    ),
}


_LoopNode = ast.While | ast.For | ast.AsyncFor


def _is_loop(node: ast.AST) -> bool:
    return isinstance(node, ast.While | ast.For | ast.AsyncFor)


def _has_advance_call(node: ast.AST) -> bool:
    """Whether `node`'s subtree calls `_advance_frame_if_supported(...)`.

    Matches both the free-function form (`_advance_frame_if_supported(w)`)
    and the instance-method form (`self._advance_frame_if_supported(w)`)
    so the scanner stays green before and after the method migration.
    """
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        # Free function: _advance_frame_if_supported(...)
        if isinstance(n.func, ast.Name) and n.func.id == "_advance_frame_if_supported":
            return True
        # Instance method: self._advance_frame_if_supported(...)
        if (
            isinstance(n.func, ast.Attribute)
            and n.func.attr == "_advance_frame_if_supported"
        ):
            return True
    return False


def _has_swap_call(node: ast.AST) -> bool:
    """Whether `node`'s subtree calls `_swap(...)` or `*.SwapOnVSync(...)`.

    Every per-tick redraw loop in the engine ends with a swap to push
    the back-buffer to the panel — that's the signal we use to
    identify "this is a redraw loop." Using `widget.draw(...)` as the
    signal is fragile: a refactor that extracts draw + swap into a
    helper (e.g. `_draw_scroll_frame`) hides the draw from the AST
    scanner. The swap call is harder to hide because it's the
    boundary between back-buffer and front-buffer — every tick has
    exactly one.
    """
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        # `_swap(canvas, frame)` — Name call.
        if isinstance(n.func, ast.Name) and n.func.id == "_swap":
            return True
        # `frame.matrix.SwapOnVSync(canvas)` etc. — Attribute call.
        if isinstance(n.func, ast.Attribute) and n.func.attr == "SwapOnVSync":
            return True
    return False


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
        if not _has_swap_call(node):
            continue
        # Compliant if this loop advances OR any enclosing loop does.
        if _has_advance_call(node):
            continue
        if any(_has_advance_call(loop) for loop in _enclosing_loops(func_node, node)):
            continue
        issues.append(
            f"loop at line {node.lineno} swaps but does not call "
            f"_advance_frame_if_supported (and no enclosing loop does)"
        )
    return issues


def test_has_advance_call_detects_attribute_form():
    """_has_advance_call must match self._advance_frame_if_supported(...)."""
    code = "async def f(self): self._advance_frame_if_supported(w)"
    tree = ast.parse(code)
    func = tree.body[0]
    assert _has_advance_call(func)


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


def _count_method_calls(node: ast.AST, method_name: str) -> int:
    """Count `*.{method_name}(...)` attribute calls inside `node`."""
    return sum(
        1
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == method_name
    )


def test_allow_list_entries_actually_pause_and_resume_frame():
    """Allow-listed functions must call pause_frame AND resume_frame
    on the widgets they redraw. Pause without resume is a foot-gun —
    a function that pauses but never resumes leaves widget frame
    counters paused after the transition exits, surfacing as
    "rainbow froze after the first transition." Each pause must have
    a matching resume; for every widget paused N times, expect N
    resume calls.
    """
    tree = ast.parse(ENGINE_PATH.read_text())
    failures: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name not in ALLOW_LIST:
            continue

        n_pause = _count_method_calls(node, "pause_frame")
        n_resume = _count_method_calls(node, "resume_frame")

        if n_pause == 0:
            failures.append(
                f"{node.name} is allow-listed but does not call "
                f"`pause_frame()`. Allow-list reason: "
                f"{ALLOW_LIST[node.name]!r}. Either add pause_frame at "
                f"entry + resume_frame in finally, or remove from "
                f"ALLOW_LIST."
            )
            continue
        if n_resume != n_pause:
            failures.append(
                f"{node.name} calls `pause_frame()` {n_pause} time(s) "
                f"but `resume_frame()` {n_resume} time(s). Each pause "
                f"must have a matching resume — otherwise the widget's "
                f"frame counter stays paused after the transition exits, "
                f"freezing animated providers from then on. Wrap the "
                f"loop body in try/finally with resume_frame in finally."
            )

    assert not failures, "\n  - ".join(["Allow-list violations:"] + failures)

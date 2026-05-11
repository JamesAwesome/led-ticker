"""Tripwire: mlb.py uses lazy_palette() like colors.py does."""

import ast
import inspect

from led_ticker.widgets import mlb as mlb_mod


def test_mlb_has_no_eager_color_construction():
    source = inspect.getsource(mlb_mod)
    tree = ast.parse(source)

    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign | ast.Assign):
            value = node.value
            if isinstance(value, ast.Call):
                func_repr = ast.unparse(value.func)
                # Also catch indirect eager calls like `__getattr__("X")` or
                # `_team_palette("X")` at module scope — they materialize a
                # color at import time just as surely as make_color(...) does.
                if func_repr in {
                    "make_color",
                    "_color",
                    "__getattr__",
                    "_team_palette",
                }:
                    offenders.append(ast.unparse(node))

    assert not offenders, (
        "mlb.py has eager module-level color construction; "
        "convert to lazy_palette() and access via _team_palette(...) "
        "inside functions:\n" + "\n".join(offenders)
    )


def test_mlb_palette_still_resolves():
    """The colors must still be importable with their existing names."""
    from led_ticker.widgets.mlb import LIVE_COLOR, LOSS_COLOR, WIN_COLOR

    assert (WIN_COLOR.red, WIN_COLOR.green, WIN_COLOR.blue) == (46, 200, 46)
    assert (LOSS_COLOR.red, LOSS_COLOR.green, LOSS_COLOR.blue) == (220, 30, 30)
    assert (LIVE_COLOR.red, LIVE_COLOR.green, LIVE_COLOR.blue) == (255, 40, 40)

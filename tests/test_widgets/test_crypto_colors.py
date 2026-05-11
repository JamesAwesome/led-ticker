"""Tripwire: trend colors live in crypto, not the global palette."""

import ast
import inspect

from led_ticker.widgets.crypto import _colors as crypto_colors


def test_crypto_trend_colors_exist():
    assert (
        crypto_colors.UP_TREND_COLOR.red,
        crypto_colors.UP_TREND_COLOR.green,
        crypto_colors.UP_TREND_COLOR.blue,
    ) == (46, 200, 46)
    assert (
        crypto_colors.DOWN_TREND_COLOR.red,
        crypto_colors.DOWN_TREND_COLOR.green,
        crypto_colors.DOWN_TREND_COLOR.blue,
    ) == (194, 24, 7)
    assert (
        crypto_colors.NEUTRAL_TREND_COLOR.red,
        crypto_colors.NEUTRAL_TREND_COLOR.green,
        crypto_colors.NEUTRAL_TREND_COLOR.blue,
    ) == (180, 180, 180)


def test_crypto_colors_module_has_no_eager_color_construction():
    """Tripwire: importing crypto._colors must not call require_graphics()."""
    source = inspect.getsource(crypto_colors)
    tree = ast.parse(source)

    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign | ast.Assign):
            value = node.value
            if isinstance(value, ast.Call):
                func_repr = ast.unparse(value.func)
                if func_repr in {
                    "make_color",
                    "_color",
                    "__getattr__",
                    "_trend_palette",
                }:
                    offenders.append(ast.unparse(node))

    assert not offenders, (
        "widgets/crypto/_colors.py has eager module-level color construction; "
        "use lazy_palette() and access via _trend_palette(...) inside "
        "functions:\n" + "\n".join(offenders)
    )

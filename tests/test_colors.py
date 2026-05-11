"""Tests for led_ticker.colors."""

from led_ticker.colors import (
    DEFAULT_COLOR,
    RGB_WHITE,
)


def test_rgb_white():
    assert RGB_WHITE.red == 255
    assert RGB_WHITE.green == 255
    assert RGB_WHITE.blue == 255


def test_default_color_is_yellow():
    assert DEFAULT_COLOR.red == 255
    assert DEFAULT_COLOR.green == 255
    assert DEFAULT_COLOR.blue == 0


def test_new_palette_colors_exist_and_are_correct():
    from led_ticker.colors import (
        BLUE,
        CYAN,
        GREEN,
        ORANGE,
        PINK,
        PURPLE,
        RED,
        YELLOW,
    )

    assert (RED.red, RED.green, RED.blue) == (255, 40, 40)
    assert (GREEN.red, GREEN.green, GREEN.blue) == (46, 200, 46)
    assert (BLUE.red, BLUE.green, BLUE.blue) == (40, 100, 255)
    assert (YELLOW.red, YELLOW.green, YELLOW.blue) == (255, 220, 0)
    assert (ORANGE.red, ORANGE.green, ORANGE.blue) == (255, 140, 0)
    assert (PURPLE.red, PURPLE.green, PURPLE.blue) == (160, 60, 200)
    assert (CYAN.red, CYAN.green, CYAN.blue) == (0, 220, 220)
    assert (PINK.red, PINK.green, PINK.blue) == (240, 70, 200)


def test_make_color_public_helper():
    from led_ticker.colors import make_color

    c = make_color(10, 20, 30)
    assert c.red == 10
    assert c.green == 20
    assert c.blue == 30


def test_make_color_replaces_private_helper():
    import led_ticker.colors as colors_mod

    assert hasattr(colors_mod, "make_color")
    assert not hasattr(colors_mod, "_color")


def test_colors_module_has_no_eager_color_construction():
    """Tripwire: module-level constants must be lazy. No `make_color(...)`
    or `_color(...)` calls at module scope."""
    import ast
    import inspect

    import led_ticker.colors as colors_mod

    source = inspect.getsource(colors_mod)
    tree = ast.parse(source)

    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign | ast.Assign):
            value = node.value
            if isinstance(value, ast.Call):
                func_repr = ast.unparse(value.func)
                if func_repr in {"make_color", "_color"}:
                    offenders.append(ast.unparse(node))

    assert not offenders, (
        "colors.py has eager color construction at module scope — "
        "move these behind `__getattr__`:\n" + "\n".join(offenders)
    )


def test_colors_module_defines_getattr():
    import led_ticker.colors as colors_mod

    assert hasattr(colors_mod, "__getattr__")


def test_lazy_palette_helper_exists():
    from led_ticker.colors import lazy_palette

    assert callable(lazy_palette)


def test_lazy_palette_builds_getattr_function():
    from led_ticker.colors import lazy_palette

    getter = lazy_palette({"FOO_COLOR": (10, 20, 30)})
    foo = getter("FOO_COLOR")
    assert (foo.red, foo.green, foo.blue) == (10, 20, 30)

    try:
        getter("MISSING")
    except AttributeError:
        pass
    else:
        raise AssertionError("getter must raise AttributeError for unknown names")

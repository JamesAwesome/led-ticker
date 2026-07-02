"""ENGINE_TICK_MS lives in the constants leaf module; ticker.py re-exports
it for back-compat. Guards the defer-to-rest layering: validate.py and
animations.py import the leaf, never the engine."""


def test_constants_module_defines_engine_tick_ms() -> None:
    from led_ticker.constants import ENGINE_TICK_MS

    assert ENGINE_TICK_MS == 50


def test_ticker_reexports_engine_tick_ms() -> None:
    """Back-compat: existing importers use `from led_ticker.ticker import
    ENGINE_TICK_MS` — the re-export must stay."""
    from led_ticker import constants, ticker

    assert ticker.ENGINE_TICK_MS is constants.ENGINE_TICK_MS


def test_constants_is_a_leaf_module() -> None:
    """constants.py must not import anything from led_ticker (leaf-module
    contract — validate.py depends on this staying import-light)."""
    import ast
    from pathlib import Path

    src = Path("src/led_ticker/constants.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom | ast.Import):
            names = (
                [node.module]
                if isinstance(node, ast.ImportFrom)
                else [a.name for a in node.names]
            )
            for name in names:
                assert not (name or "").startswith("led_ticker"), (
                    f"constants.py imports {name} — it must stay a leaf"
                )

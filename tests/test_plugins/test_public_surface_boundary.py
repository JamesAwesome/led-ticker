import ast
from pathlib import Path

EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "examples" / "plugins" / "acme" / "__init__.py"
)


def test_reference_plugin_imports_only_public_led_ticker():
    tree = ast.parse(EXAMPLE.read_text())
    bad = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("led_ticker")
            and node.module != "led_ticker.plugin"
        ):
            bad.append(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name.startswith("led_ticker")
                    and alias.name != "led_ticker.plugin"
                ):
                    bad.append(alias.name)
    assert not bad, f"reference plugin imports non-public led_ticker modules: {bad}"

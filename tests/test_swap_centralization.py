"""AST tripwire: frame.py and backends/rgbmatrix.py are the only permitted
SwapOnVSync callers.

All other code must go through LedFrame.swap() or RgbMatrixBackend.swap()
so framerate_fraction is always forwarded and future overlay_hooks have
a single injection point.
"""

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "led_ticker"
ALLOWLIST = {"frame.py", "rgbmatrix.py"}


def test_no_bare_swaponvsync():
    """Scan for direct .SwapOnVSync() calls outside frame.py using AST."""
    violations = []
    for path in SRC.rglob("*.py"):
        if path.name in ALLOWLIST:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue

        # Find all attribute calls: .SwapOnVSync(...)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "SwapOnVSync"
            ):
                violations.append((path.relative_to(SRC), node.lineno))

    assert not violations, (
        "Direct SwapOnVSync calls found — use frame.swap() instead:\n"
        + "\n".join(f"  src/led_ticker/{path}:{lineno}" for path, lineno in violations)
    )

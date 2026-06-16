"""Extraction-readiness tripwire (P3).

For each planned-extraction candidate, every name it imports from
`led_ticker.*` must be reachable by a plugin: on the public
`led_ticker.plugin` surface, an attribute of the public `colors` module,
or a per-candidate ALLOWED name with a documented reason. A new internal
reach fails this test until it's exported or justified. This is the
extraction audit, made executable.
"""

import ast
from pathlib import Path

import led_ticker.plugin as plugin
from led_ticker import colors

SRC = Path(__file__).resolve().parent.parent / "src" / "led_ticker"

# Per-candidate allowlist: name -> reason it's OK to be internal.
# Anything imported from led_ticker.* and NOT public must appear here.
_ALLOWED = {
    "widgets/weather.py": {
        "register": "replaced by api.widget(name)",
        "_match_condition": "weather_icons moves with weather into the plugin",
    },
    "widgets/weather_icons.py": {},
    "transitions/nyancat.py": {
        "register_transition": "replaced by api.transition(name)",
        "HIRES_REGISTRY": "built-in dispatch only; extracted arcade uses the "
        "P2 HiresSpec + is_scaled pattern",
    },
    "transitions/pokeball.py": {
        "register_transition": "replaced by api.transition(name)",
        "HIRES_REGISTRY": "built-in dispatch only; P2 HiresSpec pattern on extraction",
    },
    "transitions/pacman.py": {
        "register_transition": "replaced by api.transition(name)",
    },
    "transitions/sailor_moon.py": {
        "register_transition": "replaced by api.transition(name)",
    },
}

_PUBLIC = set(plugin.__all__)


def _imported_led_ticker_names(path: Path) -> set[str]:
    """Names brought in via `from led_ticker... import X` (any depth, incl.
    function-local imports)."""
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "led_ticker" or node.module.startswith("led_ticker."))
        ):
            for alias in node.names:
                names.add(alias.name)
    return names


def _is_reachable(name: str, allowed: dict) -> bool:
    return name in _PUBLIC or hasattr(colors, name) or name in allowed


def test_candidates_are_extraction_ready():
    failures = []
    for rel, allowed in _ALLOWED.items():
        path = SRC / rel
        assert path.exists(), f"candidate file missing: {rel}"
        for name in sorted(_imported_led_ticker_names(path)):
            if not _is_reachable(name, allowed):
                failures.append(f"{rel}: {name!r} is not on the public surface")
    assert not failures, "Extraction-readiness GAPs:\n" + "\n".join(failures)


def test_tripwire_is_not_vacuous():
    # A bogus internal name must be classified a GAP (the test can fail).
    assert not _is_reachable("definitely_not_public_xyz", {})
    # And a public name must be reachable.
    assert _is_reachable("make_color", {})

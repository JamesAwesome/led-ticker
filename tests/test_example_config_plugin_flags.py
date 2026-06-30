import re
import subprocess
import sys
import tomllib
from pathlib import Path

from led_ticker._config_scan import (
    _load,
    _namespace_to_package,
    _referenced_namespaces,
    plugin_dependency_warning,
    required_plugins,
)


def _cfg(toml: str) -> dict:
    return tomllib.loads(toml)


def test_config_scan_imports_first_without_cycle():
    # Importing _config_scan BEFORE led_ticker.app used to hit a circular import
    # (_config_scan -> app.plugin_cmd -> app/__init__ -> cli -> run -> _config_scan).
    # run.py defers its _config_scan import to break it. Guard in a fresh process
    # because pytest's collection order can otherwise import app first and mask it.
    result = subprocess.run(
        [sys.executable, "-c", "import led_ticker._config_scan"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_plugin_free_is_empty():
    assert required_plugins(_cfg("[display]\nrows = 16\n")) == set()


def test_string_form_widget_and_transition():
    toml = """
[[playlist.section]]
transition = "nyancat.forward"
[[playlist.section.widget]]
type = "rss.feed"
"""
    assert required_plugins(_cfg(toml)) == {"led-ticker-rss", "led-ticker-flair"}


def test_table_form_transition():
    toml = """
[[playlist.section]]
[playlist.section.transition]
type = "pacman.forward"
[[playlist.section.widget]]
type = "message"
"""
    assert required_plugins(_cfg(toml)) == {"led-ticker-flair"}


def test_top_level_transitions_surface():
    toml = '[transitions]\nbetween_sections = "nyancat.alternating"\n'
    assert required_plugins(_cfg(toml)) == {"led-ticker-flair"}


def test_inline_emoji_dependency():
    toml = """
[[playlist.section]]
[[playlist.section.widget]]
type = "message"
text = "go :pokeball.ball: go"
"""
    assert required_plugins(_cfg(toml)) == {"led-ticker-flair"}


def test_plugin_backend_counts_builtin_does_not():
    assert required_plugins(_cfg('[display]\nbackend = "telnet"\n')) == {
        "led-ticker-telnet"
    }
    assert required_plugins(_cfg('[display]\nbackend = "headless"\n')) == set()


def test_commented_usage_and_non_plugin_dotted_are_empty():
    # weather is only in a comment; "1.5" and a core a.b are non-plugin dotted.
    toml = """
[display]
gpio_slowdown = 1
# [[playlist.section.widget]]
# type = "weather.current"
[[playlist.section]]
[[playlist.section.widget]]
type = "message"
text = "version 1.5"
"""
    assert required_plugins(_cfg(toml)) == set()


_RSS_CFG = {"playlist": {"section": [{"widget": [{"type": "rss.feed"}]}]}}


def test_warning_absent_plugin_names_package_and_remedy():
    msg = plugin_dependency_warning(
        _RSS_CFG, loaded_namespaces=[], failed_namespaces=[]
    )
    assert msg is not None
    assert "led-ticker-rss" in msg
    assert "aren't installed" in msg
    assert "docs.ledticker.dev/plugins" in msg


def test_warning_installed_but_failed_says_fix_not_install():
    msg = plugin_dependency_warning(
        _RSS_CFG, loaded_namespaces=[], failed_namespaces=["rss"]
    )
    assert msg is not None
    assert "failed to load" in msg
    assert "led-ticker-rss" in msg


def test_no_warning_when_required_plugin_is_loaded():
    assert (
        plugin_dependency_warning(
            _RSS_CFG, loaded_namespaces=["rss"], failed_namespaces=[]
        )
        is None
    )


def test_no_warning_for_plugin_free_config():
    assert plugin_dependency_warning({"display": {"rows": 16}}, [], []) is None


# ---------------------------------------------------------------------------
# Tripwire: # requires-plugins: header enforcement
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# User-facing starters: the line (incl. `none`) is mandatory. Dev fixtures are
# exempt unless they use plugins. An explicit list — a filename heuristic would
# misclassify config.gif_text.example.toml (contains "text", not a fixture marker).
STARTERS = {
    "config.example.toml",
    "config.bigsign.example.toml",
    "config.firebird.example.toml",
    "config.try.example.toml",
    "config.showroom-bigsign.example.toml",
    "config.bigsign.firebird.example.toml",
}

_LINE = re.compile(r"^#\s*requires-plugins:\s*(.*?)\s*$", re.MULTILINE)


def _declared(path: Path) -> set[str] | None:
    """Parsed `# requires-plugins:` set, or None if the line is absent. `none`
    -> empty set. Lenient: whitespace/trailing-comma/case-insensitive none."""
    matches = _LINE.findall(path.read_text(encoding="utf-8"))
    assert len(matches) <= 1, f"{path.name}: expected at most one requires-plugins line"
    if not matches:
        return None
    body = matches[0].strip()
    if body.lower() == "none" or body == "":
        return set() if body.lower() == "none" else _fail_empty(path)
    return {p.strip() for p in body.split(",") if p.strip()}


def _fail_empty(path: Path):
    raise AssertionError(f"{path.name}: empty `# requires-plugins:` — use `none`")


def _example_configs() -> list[Path]:
    return sorted(_CONFIG_DIR.glob("config.*.example.toml"))


def test_starters_header_matches_derived():
    for path in sorted(_CONFIG_DIR.glob("config.*.example.toml")):
        if path.name not in STARTERS:
            continue
        declared = _declared(path)
        derived = required_plugins(path)
        assert declared is not None, (
            f"{path.name}: missing `# requires-plugins:` line (starters require it, "
            f"`none` included). Set it to: # requires-plugins: "
            f"{', '.join(sorted(derived)) or 'none'}"
        )
        assert declared == derived, (
            f"{path.name}: header {sorted(declared)} != derived {sorted(derived)}. "
            f"missing {sorted(derived - declared)}; "
            f"stale {sorted(declared - derived)}. "
            f"Set the line to: # requires-plugins: "
            f"{', '.join(sorted(derived)) or 'none'}"
        )


def test_example_is_plugin_free():
    path = _CONFIG_DIR / "config.example.toml"
    assert required_plugins(path) == set()
    assert _declared(path) == set()  # declares `none`


def test_any_plugin_using_example_declares_it():
    for path in _example_configs():
        derived = required_plugins(path)
        if not derived:
            continue
        declared = _declared(path)
        assert declared is not None, (
            f"{path.name}: uses plugins but has no `# requires-plugins:` line. "
            f"Add: # requires-plugins: {', '.join(sorted(derived))}"
        )
        assert declared == derived, (
            f"{path.name}: header {sorted(declared)} != derived {sorted(derived)}"
        )


def test_catalog_covers_every_referenced_namespace():
    # Runs against the UNFILTERED namespace set (not required_plugins, which
    # already drops unknowns) so a config referencing an uncatalogued plugin
    # namespace fails loudly.
    known = set(_namespace_to_package())
    # Built-in backends are legal bare values that are not plugins.
    builtins = {"rgbmatrix", "headless"}
    for path in _example_configs():
        refs = _referenced_namespaces(_load(path))
        # Only namespaces that look like plugins (the walk also surfaces bare
        # backend names); a dotted ref to an unknown namespace is the real risk.
        unknown = {ns for ns in refs if ns not in known and ns not in builtins}
        # Filter to things that actually appeared as a dotted/plugin ref:
        # bare non-backend strings never enter refs except via backend, handled
        # by the builtins set above.
        assert not unknown, (
            f"{path.name} references namespaces not in the catalog: {sorted(unknown)}. "
            f"Add them to src/led_ticker/plugins_catalog.json or fix the typo."
        )

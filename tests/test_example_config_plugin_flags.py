import subprocess
import sys
import tomllib

from led_ticker._config_scan import plugin_dependency_warning, required_plugins


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
    assert required_plugins(_cfg('[display]\nrows = 16\n')) == set()


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
    assert required_plugins(
        _cfg('[display]\nbackend = "telnet"\n')
    ) == {"led-ticker-telnet"}
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

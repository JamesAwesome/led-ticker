import tomllib

from led_ticker._config_scan import required_plugins


def _cfg(toml: str) -> dict:
    return tomllib.loads(toml)


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

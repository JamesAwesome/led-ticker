"""The generic plugin-reference hint used by every registry's
unknown-name error path."""

from led_ticker._plugin_hint import plugin_hint


def test_bare_name_is_not_a_plugin_reference():
    assert plugin_hint("nyancat", "transition") is None
    assert plugin_hint("message", "widget") is None


def test_namespaced_name_names_the_plugin_and_kind():
    msg = plugin_hint("arcade.nyancat", "transition")
    assert msg is not None
    assert "arcade" in msg  # the namespace
    assert "transition" in msg  # the kind word
    assert "requirements-plugins.txt" in msg


def test_kind_word_varies_per_registry():
    assert "border" in plugin_hint("vegas.marquee", "border")
    assert "widget" in plugin_hint("baseball.scores", "widget")


def test_namespace_is_the_segment_before_the_first_dot():
    msg = plugin_hint("feeds.weather.extra", "widget")
    assert "feeds" in msg
    assert "feeds.weather.extra" in msg

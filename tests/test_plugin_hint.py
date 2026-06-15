"""The generic plugin-reference hint used by every registry's
unknown-name error path."""

from led_ticker._plugin_hint import plugin_hint


def test_bare_name_is_not_a_plugin_reference():
    assert plugin_hint("nyancat", "transition") is None
    assert plugin_hint("message", "widget") is None


def test_namespaced_name_names_the_plugin_and_kind():
    msg = plugin_hint("exampleplugin.thing", "transition")
    assert msg is not None
    assert "exampleplugin" in msg  # the namespace
    assert "transition" in msg  # the kind word
    assert "requirements-plugins.txt" in msg


def test_kind_word_varies_per_registry():
    assert "border" in plugin_hint("exampleplugin.marquee", "border")
    assert "widget" in plugin_hint("baseball.scores", "widget")


def test_namespace_is_the_segment_before_the_first_dot():
    msg = plugin_hint("exampleplugin.weather.extra", "widget")
    assert "exampleplugin" in msg
    assert "exampleplugin.weather.extra" in msg


def test_dotted_non_identifier_namespace_is_not_a_plugin_reference():
    # a malformed numeric/path-like value must not get a misleading hint
    assert plugin_hint("1.5", "color provider") is None
    assert plugin_hint(".", "transition") is None
    assert plugin_hint(".leading", "widget") is None

"""get_widget_class keeps its 'Unknown widget type' message but appends
the plugin hint for namespaced (uninstalled-plugin) names. The crypto
MigrationError path (scenario A) is unaffected — it runs earlier in
validate_widget_cfg."""

import pytest

from led_ticker.widgets import get_widget_class


def test_bare_unknown_keeps_plain_message():
    with pytest.raises(ValueError) as exc:
        get_widget_class("boguswidget")
    assert "Unknown widget type" in str(exc.value)
    assert "plugin" not in str(exc.value).lower()  # no hint for bare names


def test_namespaced_unknown_appends_plugin_hint():
    with pytest.raises(ValueError) as exc:
        get_widget_class("baseball.scores")
    msg = str(exc.value)
    assert "Unknown widget type" in msg  # prefix preserved
    assert "baseball" in msg  # the namespace
    assert "requirements-plugins.txt" in msg

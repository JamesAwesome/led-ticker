"""P1.1 follow-up to the plugin-aware unknown-name work (#214):
the `--list-fields <type>` widget introspection path appends the plugin
hint for namespaced names, matching the config-validation path.

(The companion fix — a dotted-but-unknown transition reporting once
instead of via both rule 39 and rule 53 — is tested in test_validate.py
alongside the other rule-39 tests, where the `conf` fixture lives.)
"""

import pytest

from led_ticker.app.factories import _list_widget_fields


class TestListFieldsWidgetPluginHint:
    def test_namespaced_unknown_widget_gets_plugin_hint(self):
        with pytest.raises(ValueError) as exc:
            _list_widget_fields("exampleplugin.gizmo")
        msg = str(exc.value)
        assert "Unknown widget type" in msg  # prefix preserved
        assert "exampleplugin" in msg
        assert "requirements-plugins.txt" in msg

    def test_bare_unknown_widget_has_no_plugin_hint(self):
        with pytest.raises(ValueError) as exc:
            _list_widget_fields("boguswidget")
        msg = str(exc.value)
        assert "Unknown widget type" in msg
        assert "requirements-plugins.txt" not in msg

"""`--list-fields` hint resolution (issue #438).

The global ``FIELD_HINTS`` table is keyed by bare field NAME, so a hint for a
field that only exists on plugin widgets (``layout``, ``label_color``) is
shown for EVERY widget declaring a field of that name — pool.monitor's
layout prose leaked onto weather.forecast / baseball / flight / stocks, whose
``layout`` enums differ. A user copying the printed enum got a hard
validation error.

Fix: core carries hints only for fields core widgets actually own; plugins
supply their own accurate per-field hints through the per-widget
``_LIST_FIELD_HINTS`` class attribute (resolved before the global table).
"""

import contextlib

import attrs
import pytest

from led_ticker.app.factories import FIELD_HINTS, _list_widget_fields


@contextlib.contextmanager
def _temp_widget(widget_type, cls):
    """Register ``cls`` under ``widget_type`` for the duration of the block."""
    from led_ticker.widgets import _WIDGET_REGISTRY

    prior = _WIDGET_REGISTRY.get(widget_type)
    _WIDGET_REGISTRY[widget_type] = cls
    try:
        yield
    finally:
        if prior is None:
            _WIDGET_REGISTRY.pop(widget_type, None)
        else:
            _WIDGET_REGISTRY[widget_type] = prior


class TestNoPluginOnlyNameHints:
    @pytest.mark.parametrize("field", ["layout", "label_color"])
    def test_core_field_hints_excludes_plugin_only_field(self, field):
        # No CORE widget declares these fields — a name-keyed global hint for
        # them can only ever describe ONE plugin's semantics while being shown
        # for all the others. Core must not carry them (issue #438).
        assert field not in FIELD_HINTS, (
            f"FIELD_HINTS must not carry {field!r}: it is a plugin-only field "
            f"name, so a global name-keyed hint is wrong for every plugin but "
            f"one. Plugins supply their own via _LIST_FIELD_HINTS."
        )


class TestPerWidgetHintOverride:
    def test_per_widget_hint_wins_over_annotation_fallback(self):
        @attrs.define
        class _Gizmo:
            layout: str = "auto"
            _LIST_FIELD_HINTS = {
                "layout": (
                    '"auto" | "strip" | "big" | "long"',
                    "gizmo render mode",
                    '"auto"',
                ),
            }

        with _temp_widget("plug.gizmo", _Gizmo):
            out = _list_widget_fields("plug.gizmo")
        assert '"auto" | "strip" | "big" | "long"' in out
        assert "gizmo render mode" in out
        # Pool's leaked prose must NOT appear.
        assert "trend arrow" not in out

    def test_plain_field_falls_back_to_annotation(self):
        # Without a per-widget hint AND without a (now-removed) global entry,
        # a plugin's `layout` field shows its plain annotation + default —
        # accurate-but-plain, never misleading.
        @attrs.define
        class _Bare:
            layout: str = "auto"

        with _temp_widget("plug.bare", _Bare):
            out = _list_widget_fields("plug.bare")
        assert "layout" in out
        assert "trend arrow" not in out  # no leaked pool prose

    def test_malformed_per_widget_hint_raises_clear_error(self):
        # A hint tuple of the wrong arity must fail loudly, naming the widget
        # and field, rather than surfacing a bare TypeError from FieldHint(*raw)
        # or silently mis-rendering.
        @attrs.define
        class _Bad:
            layout: str = "auto"
            _LIST_FIELD_HINTS = {"layout": ("only", "two")}  # arity 2, need 3

        with _temp_widget("plug.bad", _Bad), pytest.raises(ValueError) as exc:
            _list_widget_fields("plug.bad")
        msg = str(exc.value)
        assert "plug.bad" in msg and "layout" in msg
        assert "_LIST_FIELD_HINTS" in msg

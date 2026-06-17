"""Drift guard for _DISPATCH_APPLICABLE_TYPES.

Verifies that every (field, widget_type) entry in the dict actually
appears in the --list-fields output for that widget type. If someone
adds a new dispatch-level field and forgets the dict, or lists wrong
applicable types, this test fails loudly.
"""

from led_ticker.app.factories import _DISPATCH_APPLICABLE_TYPES, _list_widget_fields


def test_dispatch_fields_appear_in_list_fields_output():
    """Every field in _DISPATCH_APPLICABLE_TYPES appears in --list-fields
    output for each of its declared applicable widget types."""
    _SAMPLE_ALL_TYPES = ("message", "gif", "countdown", "two_row", "clock")

    for field_name, applicable_types in _DISPATCH_APPLICABLE_TYPES.items():
        if field_name == "type":
            continue  # "type" is filtered by _list_widget_fields itself
        check_types = (
            applicable_types if applicable_types is not None else _SAMPLE_ALL_TYPES
        )
        for widget_type in check_types:
            try:
                output = _list_widget_fields(widget_type)
            except ValueError:
                continue  # widget type not in registry (skip)
            assert field_name in output, (
                f"Field {field_name!r} declared applicable to {widget_type!r} "
                f"in _DISPATCH_APPLICABLE_TYPES but absent from "
                f"--list-fields {widget_type} output. "
                f"Add it to FIELD_HINTS or fix the applicable_types entry."
            )

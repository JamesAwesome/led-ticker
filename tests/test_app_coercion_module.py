"""Smoke test: coercion submodule is importable at its own path."""


def test_coercion_submodule_importable():
    from led_ticker.app.coercion import (
        _COLOR_KEYS,
        _WIDGET_INT_FIELDS,
        _coerce_color_provider,
        _validate_rgb,
    )

    assert callable(_coerce_color_provider)
    assert callable(_validate_rgb)
    assert isinstance(_COLOR_KEYS, set)
    assert isinstance(_WIDGET_INT_FIELDS, frozenset)


def test_coercion_names_still_on_app_module():
    """All coercion names remain importable from led_ticker.app (backwards compat)."""
    from led_ticker.app import (
        _COLOR_KEYS,
        _coerce_color_provider,
    )

    assert callable(_coerce_color_provider)
    assert isinstance(_COLOR_KEYS, set)

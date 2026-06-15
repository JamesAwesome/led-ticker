"""Namespaced-but-unknown border / animation / color-provider names get
the plugin hint appended to their coercion error."""

import pytest

from led_ticker.app.coercion import (
    _coerce_animation,
    _coerce_border,
    _provider_from_style,
)


def test_border_string_shorthand_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_border("exampleplugin.marquee")
    assert "exampleplugin" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_border_table_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_border({"style": "exampleplugin.marquee"})
    assert "exampleplugin" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_animation_string_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_animation("exampleplugin.sparkle")
    assert "exampleplugin" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_provider_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _provider_from_style("exampleplugin.glow", {})
    assert "exampleplugin" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_bare_unknown_border_has_no_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_border("bogus")
    assert "requirements-plugins.txt" not in str(exc.value)


def test_animation_table_plugin_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_animation({"style": "exampleplugin.sparkle"})
    assert "exampleplugin" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_bare_unknown_animation_has_no_hint():
    with pytest.raises(ValueError) as exc:
        _coerce_animation("bogus")
    assert "requirements-plugins.txt" not in str(exc.value)


def test_bare_unknown_provider_has_no_hint():
    with pytest.raises(ValueError) as exc:
        _provider_from_style("bogus", {})
    assert "requirements-plugins.txt" not in str(exc.value)

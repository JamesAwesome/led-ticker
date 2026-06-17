"""The public coerce_color_provider primitive for plugin color fields."""

from led_ticker.plugin import ColorProviderBase, coerce_color_provider


def test_constant_rgb_list_becomes_a_provider():
    p = coerce_color_provider([255, 200, 0], "font_color_temp")
    assert isinstance(p, ColorProviderBase)
    assert p.frame_invariant is True  # constant color is frame-invariant


def test_rainbow_string_becomes_a_per_frame_provider():
    p = coerce_color_provider("rainbow", "font_color_temp")
    assert isinstance(p, ColorProviderBase)
    assert p.frame_invariant is False  # rainbow animates per frame


def test_style_table_becomes_a_provider():
    p = coerce_color_provider(
        {"style": "gradient", "from": [255, 0, 0], "to": [0, 0, 255]},
        "font_color_temp",
    )
    assert isinstance(p, ColorProviderBase)


def test_already_a_provider_passes_through():
    first = coerce_color_provider("rainbow")
    assert coerce_color_provider(first) is first


def test_none_returns_none():
    assert coerce_color_provider(None) is None

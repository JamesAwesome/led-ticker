import pytest

from led_ticker.app.coercion import _coerce_color_provider


@pytest.mark.parametrize(
    "spec",
    [
        "rainbow",
        "color_cycle",
        "random",
        {"style": "rainbow", "speed": 5, "char_offset": 3},
        {"style": "color_cycle", "speed": 2},
        {"style": "gradient", "from": [255, 0, 0], "to": [0, 0, 255]},
        {"style": "shimmer", "base": [255, 255, 255], "shimmer": [0, 200, 255]},
    ],
)
def test_builtin_providers_still_coerce(spec):
    provider = _coerce_color_provider(spec)
    assert hasattr(provider, "color_for")


def test_unknown_style_lists_available():
    with pytest.raises(ValueError, match="unknown font_color style"):
        _coerce_color_provider({"style": "nope"})

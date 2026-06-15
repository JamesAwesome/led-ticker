"""P3 — the six symbols planned extractions need, on the public surface."""

import led_ticker.plugin as plugin


def test_new_symbols_importable_from_plugin():
    from led_ticker.plugin import (  # noqa: F401
        ColorTuple,
        as_color_provider,
        count_text_chars,
        draw_text_per_char,
        draw_with_emoji,
        format_clock,
    )


def test_new_symbols_in_all():
    for name in (
        "ColorTuple",
        "as_color_provider",
        "count_text_chars",
        "draw_text_per_char",
        "draw_with_emoji",
        "format_clock",
    ):
        assert name in plugin.__all__, name


def test_as_color_provider_wraps_a_color_uniformly():
    from led_ticker.plugin import as_color_provider, make_color

    c = make_color(10, 20, 30)
    prov = as_color_provider(c)
    assert hasattr(prov, "color_for")  # it's a ColorProvider
    got = prov.color_for(frame=0, char_index=0, total_chars=1)
    assert (got.red, got.green, got.blue) == (10, 20, 30)
    got2 = prov.color_for(frame=5, char_index=3, total_chars=8)
    assert (got2.red, got2.green, got2.blue) == (10, 20, 30)
    # A constant provider must declare the fast-path flags so image
    # widgets don't force per-tick / per-char redraws for it.
    assert prov.frame_invariant is True
    assert prov.per_char is False

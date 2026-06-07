"""Tests for small_font / small_font_size / small_font_threshold TOML coercion."""

import pytest


def test_resolve_fonts_coerces_small_font_bdf():
    """small_font = '5x8' resolves to the FONT_SMALL BDF object."""
    from led_ticker.app.factories import _resolve_fonts
    from led_ticker.fonts import FONT_SMALL

    cfg = {"small_font": "5x8"}
    _resolve_fonts(cfg, cls=None, panel_h_for_warning=None)
    assert cfg["small_font"] is FONT_SMALL


def test_resolve_fonts_small_font_hires_requires_size():
    """small_font with a hires name and no small_font_size raises ValueError."""
    from led_ticker.app.factories import _resolve_fonts
    from led_ticker.fonts import list_available_hires_fonts

    hires_names = list_available_hires_fonts()
    if not hires_names:
        pytest.skip("no hires fonts available in test environment")

    cfg = {"small_font": hires_names[0]}  # no small_font_size
    with pytest.raises(ValueError, match="small_font_size"):
        _resolve_fonts(cfg, cls=None, panel_h_for_warning=None)

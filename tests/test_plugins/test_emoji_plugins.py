import led_ticker.pixel_emoji as pe
from led_ticker import _plugin_loader as L


def test_plugin_emoji_commit_does_not_suppress_builtins():
    """A namespaced slug committed before the lazy build must NOT stop the
    built-ins from loading (regression for the `if not EMOJI_REGISTRY` gate)."""
    L.reset_plugins()
    # Force the un-built state, then simulate a plugin commit landing first.
    pe.EMOJI_REGISTRY.clear()
    pe._EMOJI_BUILTINS_LOADED = False
    pe.EMOJI_REGISTRY["acme.spark"] = pe.HEART  # any PixelData
    try:
        reg = pe._get_registry()
        assert "acme.spark" in reg, "plugin slug was dropped"
        assert "heart" in reg, "built-in emojis were suppressed by the plugin slug"
    finally:
        pe.EMOJI_REGISTRY.pop("acme.spark", None)


def test_registry_map_includes_emoji_and_font_surfaces():
    assert L._REGISTRY_MAP["emojis"] is pe.EMOJI_REGISTRY
    assert L._REGISTRY_MAP["hires_emojis"] is pe.HIRES_REGISTRY
    from led_ticker.fonts.hires_loader import _PLUGIN_FONTS

    assert L._REGISTRY_MAP["fonts"] is _PLUGIN_FONTS

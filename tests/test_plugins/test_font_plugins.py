import textwrap
from pathlib import Path

import pytest

import led_ticker.pixel_emoji as pe
from led_ticker import _plugin_loader as L
from led_ticker.fonts import (
    UnknownFontError,
    hires_loader,
    list_available_hires_fonts,
    resolve_font,
)
from led_ticker.fonts.hires_loader import BUNDLED_HIRES_DIR, HiresFont


def _a_bundled_font_path():
    for ext in ("*.otf", "*.ttf"):
        hits = sorted(BUNDLED_HIRES_DIR.glob(ext))
        if hits:
            return hits[0]
    pytest.skip("no bundled hi-res font available to copy")


def test_resolve_root_for_single_file_local_plugin():
    # source is the path to the .py file -> root is its parent dir.
    root = L._resolve_root("/tmp/cfg/plugins/myclock.py", lambda api: None)
    assert root == Path("/tmp/cfg/plugins")


def test_resolve_root_for_package_local_plugin(tmp_path):
    # source is the package dir itself -> root is that dir.
    pkg = tmp_path / "myclock"
    pkg.mkdir()
    root = L._resolve_root(str(pkg), lambda api: None)
    assert root == pkg


def test_resolve_root_for_entry_point_uses_module_file(tmp_path):
    # Entry-point source has no path; root comes from the register's module.
    mod_file = tmp_path / "acme_pkg" / "__init__.py"
    mod_file.parent.mkdir()
    mod_file.write_text("def register(api):\n    pass\n")
    import importlib.util

    spec = importlib.util.spec_from_file_location("acme_pkg_test", mod_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = L._resolve_root("entry-point:acme_pkg:register", module.register)
    assert root == mod_file.parent


def test_find_font_path_prefers_plugin_fonts(tmp_path):
    font = tmp_path / "Brand.ttf"
    font.write_bytes(b"not-a-real-font")  # presence is all _find_font_path checks
    hires_loader._PLUGIN_FONTS["acme.Brand"] = font.resolve()
    try:
        assert hires_loader._find_font_path("acme.Brand") == font.resolve()
        # A missing registered path resolves to None (not an exception).
        hires_loader._PLUGIN_FONTS["acme.Gone"] = tmp_path / "nope.ttf"
        assert hires_loader._find_font_path("acme.Gone") is None
    finally:
        hires_loader._PLUGIN_FONTS.pop("acme.Brand", None)
        hires_loader._PLUGIN_FONTS.pop("acme.Gone", None)


def test_reset_plugins_clears_font_cache(tmp_path):
    # A miss cached before the plugin registers must not survive reset.
    from led_ticker.fonts.hires_loader import load_hires_font

    assert load_hires_font("acme.NoSuch", 16) is None  # caches a miss
    assert load_hires_font.cache_info().currsize >= 1  # the miss is cached
    try:
        L.reset_plugins()  # must clear the cached miss
        assert load_hires_font.cache_info().currsize == 0  # cache was cleared
        # With the cache cleared, a freshly-registered plugin font path is
        # resolved instead of the stale cached None.
        font = tmp_path / "Brand.ttf"
        font.write_bytes(b"x")
        hires_loader._PLUGIN_FONTS["acme.NoSuch"] = font.resolve()
        # _find_font_path re-reads _PLUGIN_FONTS (presence-only check).
        assert hires_loader._find_font_path("acme.NoSuch") == font.resolve()
    finally:
        hires_loader._PLUGIN_FONTS.pop("acme.NoSuch", None)
        L.reset_plugins()


def test_local_plugin_contributes_emoji_hires_and_font(tmp_path):
    L.reset_plugins()

    plugin_dir = tmp_path / "plugins"
    fonts_dir = plugin_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    src_font = _a_bundled_font_path()
    (fonts_dir / "Brand.ttf").write_bytes(src_font.read_bytes())

    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import HiResEmoji

            def register(api):
                api.emoji("spark", [(0, 0, 255, 0, 0)])
                api.hires_emoji(
                    "glow",
                    HiResEmoji(pixels=((0, 0, 255, 255, 0),), physical_size=16),
                )
                api.font("Brand", "fonts/Brand.ttf")
            """
        )
    )

    try:
        result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed

        # Low-res emoji resolves through the production registry accessor.
        assert "acme.spark" in pe._get_registry()
        # Hi-res emoji landed in the hi-res registry...
        assert "acme.glow" in pe.HIRES_REGISTRY
        # ...and is hi-res-ONLY (no low-res fallback for it).
        assert "acme.glow" not in pe._get_registry()

        # Font resolves to a real rasterized HiresFont.
        font = resolve_font("acme.Brand", size=16)
        assert isinstance(font, HiresFont)
    finally:
        L.reset_plugins()


def test_missing_plugin_font_file_gives_clear_error(tmp_path):
    """resolve_font raises UnknownFontError with 'registered but its file is missing'
    when a plugin font name is in _PLUGIN_FONTS but the file does not exist."""
    hires_loader._PLUGIN_FONTS["acme.Ghost"] = tmp_path / "nope.ttf"
    try:
        with pytest.raises(
            UnknownFontError, match="registered but its file is missing"
        ):
            resolve_font("acme.Ghost", size=16)
    finally:
        hires_loader._PLUGIN_FONTS.pop("acme.Ghost", None)
        L.reset_plugins()


def test_draw_text_renders_via_public_surface():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    from led_ticker.plugin import draw_text, make_color, resolve_font

    font = resolve_font("6x12")  # built-in BDF alias; no size needed

    opts = RGBMatrixOptions()
    opts.cols = 64
    opts.rows = 16
    opts.chain_length = 1
    matrix = RGBMatrix(options=opts)
    canvas = matrix.CreateFrameCanvas()

    c = make_color(255, 255, 255)
    w0 = draw_text(canvas, font, "hi", x=0, y=10, color=c)  # == text width
    w50 = draw_text(canvas, font, "hi", x=50, y=10, color=c)  # == 50 + text width
    assert w0 > 0
    assert w50 == w0 + 50  # absolute end position, not relative advance


# --- plugin-declared default thresholds (API 1.3) --------------------------


@pytest.mark.parametrize("value", [0, 45, 255])
def test_default_threshold_prefers_plugin_value(value):
    hires_loader._PLUGIN_THRESHOLDS["acme.Brand"] = value
    try:
        assert hires_loader.default_threshold("acme.Brand") == value
    finally:
        hires_loader._PLUGIN_THRESHOLDS.pop("acme.Brand", None)


def test_default_threshold_without_plugin_value_keeps_loader_default():
    assert hires_loader.default_threshold("acme.Unlisted") == hires_loader.THRESHOLD
    # The core table still wins for core names.
    assert hires_loader.default_threshold("Inter-Regular") == 80


def test_plugin_font_names_appear_in_hires_listing(tmp_path):
    # Presence in the listing is what makes coercion._is_hires_font_name (and
    # so the factories' font_size hints and the two-row refusal) see the font.
    hires_loader._PLUGIN_FONTS["acme.Brand"] = tmp_path / "Brand.ttf"  # need not exist
    try:
        assert "acme.Brand" in list_available_hires_fonts()
        from led_ticker.app.coercion import _is_hires_font_name

        assert _is_hires_font_name("acme.Brand")
    finally:
        hires_loader._PLUGIN_FONTS.pop("acme.Brand", None)


def test_reset_plugins_clears_plugin_thresholds():
    hires_loader._PLUGIN_THRESHOLDS["acme.Brand"] = 45
    L.reset_plugins()
    assert "acme.Brand" not in hires_loader._PLUGIN_THRESHOLDS


def test_registry_map_routes_font_thresholds_and_commit_does_not_count_them():
    assert L._REGISTRY_MAP["font_thresholds"] is hires_loader._PLUGIN_THRESHOLDS
    api = L.PluginAPI("acme", root=None)
    api._buffers["font_thresholds"]["acme.Brand"] = 45
    info = L.PluginInfo(namespace="acme", source="test")
    try:
        L._commit(api, info)
        assert hires_loader._PLUGIN_THRESHOLDS["acme.Brand"] == 45
        # The threshold is an attribute of the font, not a contribution.
        assert "font_thresholds" not in info.counts
        assert "font_thresholds" not in info.names
    finally:
        L.reset_plugins()

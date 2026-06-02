from pathlib import Path

from led_ticker import _plugin_loader as L
from led_ticker.fonts import hires_loader


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

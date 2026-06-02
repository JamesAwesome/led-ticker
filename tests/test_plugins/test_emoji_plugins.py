import inspect
import logging
import textwrap

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


def test_emoji_pattern_admits_namespaced_and_builtin_slugs():
    assert pe.EMOJI_PATTERN.fullmatch(":acme.heart:")
    assert pe.EMOJI_PATTERN.fullmatch(":heart:")
    assert pe.EMOJI_PATTERN.fullmatch(":partly_cloudy:")
    # A clock time must NOT be treated as an emoji token.
    assert pe.EMOJI_PATTERN.search("score 12:30:45 final") is None


def test_parse_segments_uses_the_shared_pattern_and_parses_namespaced():
    src = inspect.getsource(pe._parse_segments)
    # Tripwire: confirms _parse_segments derives its split from EMOJI_PATTERN
    # (not a hardcoded copy that could drift). If this fails after a legitimate
    # refactor, delete this inspect assertion — the behavioral asserts below are
    # the real guard.
    assert "EMOJI_PATTERN.pattern" in src

    pe._get_registry()  # materialize built-ins
    pe.EMOJI_REGISTRY["acme.spark"] = pe.HEART
    try:
        segs = pe._parse_segments("hi :acme.spark: and :heart: ok")
        assert ("emoji", "acme.spark") in segs
        assert ("emoji", "heart") in segs
    finally:
        pe.EMOJI_REGISTRY.pop("acme.spark", None)


def test_plugin_hires_emoji_measures_on_scaled_canvas(tmp_path):
    import textwrap

    from rgbmatrix import _StubCanvas

    from led_ticker.pixel_emoji import measure_emoji_at
    from led_ticker.scaled_canvas import ScaledCanvas

    L.reset_plugins()
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import HiResEmoji

            def register(api):
                api.hires_emoji(
                    "glow",
                    HiResEmoji(pixels=((0, 0, 255, 255, 0),), physical_size=16),
                )
            """
        )
    )
    try:
        result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed
        scaled = ScaledCanvas(_StubCanvas(width=256, height=64), scale=2)
        width = measure_emoji_at(scaled, "acme.glow")
        assert isinstance(width, int) and width > 0
    finally:
        L.reset_plugins()


def test_unpaired_hires_emoji_warns(tmp_path, caplog):
    """A plugin that registers hires_emoji but no matching emoji warns at load time."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import HiResEmoji

            def register(api):
                api.hires_emoji(
                    "glow",
                    HiResEmoji(pixels=((0, 0, 255, 255, 0),), physical_size=16),
                )
            """
        )
    )
    L.reset_plugins()
    try:
        with caplog.at_level(logging.WARNING):
            result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed
        assert any(
            "no low-res counterpart" in r.getMessage() for r in caplog.records
        ), "expected a warning about missing low-res counterpart"
    finally:
        L.reset_plugins()


def test_paired_hires_emoji_does_not_warn(tmp_path, caplog):
    """A plugin registering both emoji and hires_emoji does not trigger the warning."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import HiResEmoji

            def register(api):
                api.emoji("glow", [(0, 0, 255, 0, 0)])
                api.hires_emoji(
                    "glow",
                    HiResEmoji(pixels=((0, 0, 255, 255, 0),), physical_size=16),
                )
            """
        )
    )
    L.reset_plugins()
    try:
        with caplog.at_level(logging.WARNING):
            result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed
        assert not any(
            "no low-res counterpart" in r.getMessage() for r in caplog.records
        ), "unexpected warning about missing low-res counterpart for a paired emoji"
    finally:
        L.reset_plugins()


def test_plugin_hires_only_emoji_raises_on_plain_canvas(tmp_path):
    """measure_emoji_at on a plain canvas raises KeyError for hires-only slugs."""
    import pytest
    from rgbmatrix import _StubCanvas

    from led_ticker.pixel_emoji import measure_emoji_at

    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import HiResEmoji

            def register(api):
                api.hires_emoji(
                    "glow",
                    HiResEmoji(pixels=((0, 0, 255, 255, 0),), physical_size=16),
                )
            """
        )
    )
    L.reset_plugins()
    try:
        result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed
        plain_canvas = _StubCanvas(width=160, height=16)
        with pytest.raises(KeyError):
            measure_emoji_at(plain_canvas, "acme.glow")
    finally:
        L.reset_plugins()


def test_hires_only_plugin_slug_parses_as_text_not_emoji(tmp_path):
    """_parse_segments treats an unregistered (hires-only) slug as plain text."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            """
            from led_ticker.plugin import HiResEmoji

            def register(api):
                api.hires_emoji(
                    "glow",
                    HiResEmoji(pixels=((0, 0, 255, 255, 0),), physical_size=16),
                )
            """
        )
    )
    L.reset_plugins()
    try:
        result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed
        segs = pe._parse_segments("hi :acme.glow: x")
        assert ("emoji", "acme.glow") not in segs
        assert ("text", ":acme.glow:") in segs
    finally:
        L.reset_plugins()


def test_draw_with_emoji_renders_plugin_low_res_slug(tmp_path):
    """A plugin-registered low-res emoji renders inline and advances the cursor."""
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    from led_ticker.fonts import FONT_SMALL
    from led_ticker.pixel_emoji import draw_with_emoji
    from led_ticker.scaled_canvas import ScaledCanvas

    # Build a minimal 8x8 pixel grid so the emoji has real pixels
    pixels = [(x, y, 255, 0, 0) for x in range(8) for y in range(8)]

    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "acme.py").write_text(
        textwrap.dedent(
            f"""
            def register(api):
                api.emoji("spark", {pixels!r})
            """
        )
    )
    L.reset_plugins()
    try:
        result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert not result.failed, result.failed

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        sc = ScaledCanvas(real, scale=4)

        advance_with = draw_with_emoji(
            sc, FONT_SMALL, cursor_pos=0, y=8,
            color=(255, 255, 255), text="hi :acme.spark:"
        )
        advance_without = draw_with_emoji(
            sc, FONT_SMALL, cursor_pos=0, y=8, color=(255, 255, 255), text="hi "
        )
        # The emoji slug should have consumed additional width
        assert advance_with > advance_without
    finally:
        L.reset_plugins()


def test_emoji_registration_is_atomic_on_raising_register(tmp_path):
    """A plugin whose register() raises must not leave partial state in registry."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "bad.py").write_text(
        textwrap.dedent(
            """
            def register(api):
                api.emoji("flash", [(0, 0, 1, 2, 3)])
                raise RuntimeError("boom")
            """
        )
    )
    L.reset_plugins()
    try:
        result = L.load_plugins(plugin_dir, entry_points_enabled=False)
        assert any(ns == "bad" for ns, _ in result.failed), (
            f"expected 'bad' in failed; got {result.failed}"
        )
        assert "bad.flash" not in pe.EMOJI_REGISTRY, (
            "partial emoji registration leaked despite raised exception"
        )
    finally:
        L.reset_plugins()

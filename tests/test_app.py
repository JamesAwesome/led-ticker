"""Tests for led_ticker.app — widget building from config dicts."""

import unittest.mock as mock
from datetime import date
from pathlib import Path

import pytest

from led_ticker.app import _build_title, _build_widget, build_frame_from_config
from led_ticker.config import DisplayConfig
from led_ticker.widget import Widget
from led_ticker.widgets.message import TickerCountdown, TickerMessage


def test_build_frame_passes_pixel_mapper_and_parallel():
    display = DisplayConfig(
        rows=32,
        cols=64,
        chain=8,
        parallel=1,
        pixel_mapper="U-mapper",
        default_scale=4,
    )
    frame = build_frame_from_config(display)
    assert frame.led_pixel_mapper == "U-mapper"
    assert frame.led_parallel == 1
    assert frame.led_chain == 8
    assert frame.led_rows == 32
    assert frame.led_cols == 64


def test_build_frame_existing_sign_defaults():
    display = DisplayConfig(
        rows=16,
        cols=32,
        chain=5,
        brightness=60,
        slowdown_gpio=2,
    )
    frame = build_frame_from_config(display)
    assert frame.led_pixel_mapper == ""
    assert frame.led_parallel == 1
    assert frame.led_brightness == 60
    assert frame.led_slowdown_gpio == 2


def test_build_frame_logs_show_refresh_explanation_when_enabled(caplog):
    """show_refresh=true makes the C library print Hz to stderr with
    backspaces — looks like log corruption to first-time readers. We
    log a one-time note pointing at where to look so it's not mistaken
    for a glitch."""
    import logging

    display = DisplayConfig(rows=32, cols=64, chain=8, show_refresh=True)
    with caplog.at_level(logging.INFO):
        build_frame_from_config(display)
    msgs = [r.message for r in caplog.records]
    assert any(
        "show_refresh=true" in m and "stderr" in m for m in msgs
    ), f"expected show_refresh explanation; got: {msgs}"


def test_build_frame_no_show_refresh_log_when_disabled(caplog):
    """No spurious explainer log when the user didn't ask for it."""
    import logging

    display = DisplayConfig(rows=16, cols=32, chain=5, show_refresh=False)
    with caplog.at_level(logging.INFO):
        build_frame_from_config(display)
    msgs = [r.message for r in caplog.records]
    assert not any(
        "live Hz updates" in m for m in msgs
    ), f"didn't expect show_refresh explainer; got: {msgs}"


class TestBuildWidget:
    """Test that _build_widget correctly maps config dicts to widget instances."""

    async def test_message_with_text_key(self):
        """Config uses 'text' — must map to 'message' param."""
        cfg = {"type": "message", "text": "Hello world"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerMessage)
        assert widget.message == "Hello world"

    async def test_message_with_message_key(self):
        """Config can also use 'message' directly."""
        cfg = {"type": "message", "message": "Hello world"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerMessage)
        assert widget.message == "Hello world"

    async def test_countdown_with_text_key(self):
        """Countdown config uses 'text' — must map to 'message'."""
        cfg = {
            "type": "countdown",
            "text": "Days Until Spring",
            "countdown_date": date(2026, 3, 20),
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerCountdown)
        assert widget.message == "Days Until Spring"

    async def test_countdown_with_message_key(self):
        cfg = {
            "type": "countdown",
            "message": "Days Until Spring",
            "countdown_date": date(2026, 3, 20),
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerCountdown)

    async def test_unknown_widget_type_raises(self):
        cfg = {"type": "nonexistent_widget"}
        with pytest.raises(ValueError, match="Unknown widget type"):
            await _build_widget(cfg, session=mock.Mock())

    async def test_text_key_does_not_override_message(self):
        """If both 'text' and 'message' are present, 'message' wins."""
        cfg = {
            "type": "message",
            "text": "from text",
            "message": "from message",
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert widget.message == "from message"

    async def test_built_widget_conforms_to_protocol(self):
        cfg = {"type": "message", "text": "test"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, Widget)

    async def test_config_dict_not_mutated(self):
        """_build_widget receives a copy, but verify the mapping works
        even when called multiple times with fresh dicts."""
        for _ in range(3):
            cfg = {"type": "message", "text": "repeat"}
            widget = await _build_widget(cfg, session=mock.Mock())
            assert widget.message == "repeat"


class TestBuildTitle:
    async def test_build_title_with_text(self):
        title = await _build_title({"text": "News", "color": "random"})
        assert isinstance(title, TickerMessage)
        assert title.message == "News"

    async def test_build_title_none(self):
        title = await _build_title(None)
        assert title is None

    async def test_build_title_no_color(self):
        title = await _build_title({"text": "Plain"})
        assert isinstance(title, TickerMessage)
        assert title.message == "Plain"

    async def test_build_title_empty_text(self):
        title = await _build_title({"text": ""})
        assert isinstance(title, TickerMessage)
        assert title.message == ""

    async def test_build_title_with_rgb_list_color(self):
        # TOML inline-tables and arrays come through as lists. The loader
        # should coerce a 3-int list into a graphics.Color (wrapped in
        # _ConstantColor after post_init). Access via color_for().
        title = await _build_title({"text": "Pink", "color": [255, 150, 190]})
        assert title is not None
        color = title.font_color.color_for(0, 0, 1)
        assert color.red == 255
        assert color.green == 150
        assert color.blue == 190


class TestColorCoercion:
    """Regression: configs can specify per-widget RGB colors as TOML
    arrays like `font_color = [255, 150, 190]`. Without coercion the
    widget would receive a Python list and the rasterizer would fail.

    font_color is now coerced to a ColorProvider (_ConstantColor wrapping
    a graphics.Color). Background colors (bg_color etc.) remain raw
    graphics.Color objects since they drive SetPixel fills.
    """

    async def test_widget_font_color_rgb_list_coerced_to_provider(self):
        from led_ticker.color_providers import _ConstantColor

        cfg = {"type": "message", "text": "Hi", "font_color": [255, 150, 190]}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.font_color, _ConstantColor)
        # Verify the wrapped color has the expected values.
        color = widget.font_color.color_for(0, 0, 1)
        assert color.red == 255
        assert color.green == 150
        assert color.blue == 190

    async def test_widget_font_color_tuple_coerced(self):
        from led_ticker.color_providers import _ConstantColor

        cfg = {"type": "message", "text": "Hi", "font_color": (180, 140, 230)}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.font_color, _ConstantColor)
        assert widget.font_color.color_for(0, 0, 1).red == 180

    async def test_widget_font_color_omitted_uses_default(self):
        from led_ticker.color_providers import _ConstantColor

        cfg = {"type": "message", "text": "Hi"}
        widget = await _build_widget(cfg, session=mock.Mock())
        # Default is DEFAULT_COLOR (yellow); font_color is now a
        # _ConstantColor provider wrapping the raw Color.
        assert isinstance(widget.font_color, _ConstantColor)
        # Verify the wrapped color is accessible via the provider interface.
        assert hasattr(widget.font_color.color_for(0, 0, 1), "red")


class TestExampleConfigWidgets:
    """Verify every widget in config.example.toml can be instantiated.

    This is the integration test that would have caught the text/message bug.
    """

    async def test_all_example_config_widgets_build(self):
        """Load config.example.toml and build every widget."""
        from led_ticker.config import load_config

        config_path = Path(__file__).resolve().parent.parent / "config.example.toml"
        if not config_path.exists():
            pytest.skip("config.example.toml not found")

        config = load_config(config_path)

        for section in config.sections:
            # Build title
            if section.title:
                title = await _build_title(section.title)
                assert isinstance(title, TickerMessage)

            # Build each widget
            for widget_cfg in section.widgets:
                cfg = dict(widget_cfg)
                widget_type = cfg.get("type")

                # Skip widgets that need network (rss_feed, weather, crypto)
                if widget_type in (
                    "rss_feed",
                    "weather",
                    "coinbase",
                    "coingecko",
                    "etherscan",
                ):
                    continue

                widget = await _build_widget(cfg, session=mock.Mock())
                assert isinstance(
                    widget, Widget
                ), f"Widget type={widget_type} did not produce a Widget"

    async def test_moonbunny_bigsign_config_widgets_build(self):
        """Load config.moonbunny.example.toml and build every widget.

        Exercises: TOML RGB color lists, inline :instagram: and :email:
        emoji slugs, multi-section forever_scroll layout.
        """
        from led_ticker.config import load_config

        config_path = (
            Path(__file__).resolve().parent.parent
            / "config"
            / "config.moonbunny.example.toml"
        )
        config = load_config(config_path)

        for section in config.sections:
            if section.title:
                title = await _build_title(section.title)
                assert isinstance(title, TickerMessage)

            from led_ticker.widgets.two_row import TwoRowMessage

            for widget_cfg in section.widgets:
                cfg = dict(widget_cfg)
                widget = await _build_widget(cfg, session=mock.Mock())
                assert isinstance(widget, TickerMessage | TwoRowMessage)
                if isinstance(widget, TickerMessage):
                    # font_color is now a ColorProvider (has color_for)
                    assert hasattr(widget.font_color, "color_for")
                else:
                    # two_row carries top_color + bottom_color as providers
                    assert hasattr(widget.top_color, "color_for")
                    assert hasattr(widget.bottom_color, "color_for")


class TestColorKeysExtended:
    def test_color_keys_includes_bg_keys(self):
        from led_ticker.app import _COLOR_KEYS

        assert "bg_color" in _COLOR_KEYS
        assert "top_bg_color" in _COLOR_KEYS
        assert "bottom_bg_color" in _COLOR_KEYS


class TestBuildWidgetSectionBgPropagation:
    @pytest.mark.asyncio
    async def test_section_bg_propagates_when_widget_omits_it(self):
        """When the section config has bg_color and the widget config
        doesn't, the widget receives the section bg as a default."""
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget_cfg = {"type": "message", "text": "hi"}
            widget = await _build_widget(
                widget_cfg,
                session,
                default_bg_color=(10, 20, 30),
            )
        assert widget.bg_color is not None
        assert widget.bg_color.red == 10
        assert widget.bg_color.green == 20
        assert widget.bg_color.blue == 30

    @pytest.mark.asyncio
    async def test_widget_bg_overrides_section_bg(self):
        """When both section and widget specify bg_color, widget wins."""
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "bg_color": [100, 100, 100],
            }
            widget = await _build_widget(
                widget_cfg,
                session,
                default_bg_color=(10, 20, 30),
            )
        assert widget.bg_color.red == 100  # widget value, not section

    @pytest.mark.asyncio
    async def test_no_section_bg_no_widget_bg_yields_none(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget_cfg = {"type": "message", "text": "hi"}
            widget = await _build_widget(widget_cfg, session)
        assert widget.bg_color is None


class TestBuildWidgetFontResolution:
    @pytest.mark.asyncio
    async def test_hires_font_name_resolves_to_HiresFont(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.fonts.hires_loader import HiresFont

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                "font_size": 28,
            }
            widget = await _build_widget(widget_cfg, session)
        assert isinstance(widget.font, HiresFont)
        assert widget.font.size == 28

    @pytest.mark.asyncio
    async def test_bdf_alias_resolves_to_C_font(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.fonts import FONT_DEFAULT

        async with aiohttp.ClientSession() as session:
            widget_cfg = {"type": "message", "text": "hi", "font": "6x12"}
            widget = await _build_widget(widget_cfg, session)
        assert widget.font is FONT_DEFAULT

    @pytest.mark.asyncio
    async def test_no_font_field_keeps_class_default(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.fonts import FONT_DEFAULT

        async with aiohttp.ClientSession() as session:
            widget_cfg = {"type": "message", "text": "hi"}
            widget = await _build_widget(widget_cfg, session)
        # TickerMessage's class default is FONT_DEFAULT.
        assert widget.font is FONT_DEFAULT

    @pytest.mark.asyncio
    async def test_unknown_font_name_raises(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.fonts import UnknownFontError

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "totally-not-a-font",
                "font_size": 24,
            }
            try:
                await _build_widget(widget_cfg, session)
            except UnknownFontError as e:
                assert "totally-not-a-font" in str(e)
                return
            raise AssertionError("expected UnknownFontError")

    @pytest.mark.asyncio
    async def test_hires_without_font_size_raises(self):
        """HiresFont in a TOML widget config without explicit
        font_size raises with the size-hint error message — caught at
        config-load via `_is_hires_font_name`."""
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                # no font_size
            }
            with pytest.raises(ValueError, match="HiresFont.*requires font_size"):
                await _build_widget(widget_cfg, session)

    @pytest.mark.asyncio
    async def test_font_threshold_plumbed_through_to_rasterizer(self):
        """`font_threshold` in TOML must reach the loader so thin-stroked
        fonts (Beloved Sans Regular) can override the 50% cutoff."""
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.fonts.hires_loader import HiresFont

        async with aiohttp.ClientSession() as session:
            cfg_default = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                "font_size": 24,
            }
            cfg_low_thr = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                "font_size": 24,
                "font_threshold": 64,
            }
            w_default = await _build_widget(cfg_default, session)
            w_low_thr = await _build_widget(cfg_low_thr, session)

        assert isinstance(w_default.font, HiresFont)
        assert isinstance(w_low_thr.font, HiresFont)
        # Distinct cache entries — lower threshold gives more lit pixels.
        assert w_default.font is not w_low_thr.font
        assert len(w_low_thr.font.glyphs["a"].lit) > len(w_default.font.glyphs["a"].lit)

    @pytest.mark.asyncio
    async def test_font_threshold_not_passed_as_widget_kwarg(self):
        """`font_threshold` is consumed by the resolver — must not leak
        through to the widget constructor (would fail with unexpected kwarg)."""
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                "font_size": 24,
                "font_threshold": 80,
            }
            # Would raise TypeError if font_threshold leaked into TickerMessage.
            widget = await _build_widget(widget_cfg, session)
        assert widget.message == "hi"
        assert not hasattr(widget, "font_threshold")


class TestSmallSignFontSizeGuard:
    """Hi-res renders at native physical pixels. On the small sign
    (default_scale=1, panel_h=16), a font_size > 14 will overflow
    vertically. Warn the user instead of silently clipping.
    """

    @pytest.mark.asyncio
    async def test_warns_when_font_size_overflows_small_sign(self, caplog):
        import logging

        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with caplog.at_level(logging.WARNING):
                widget_cfg = {
                    "type": "message",
                    "text": "hi",
                    "font": "Inter-Regular",
                    "font_size": 24,  # bigger than 16-2=14
                }
                await _build_widget(widget_cfg, session, panel_h_for_warning=16)
        assert any(
            "exceeds panel height" in r.message for r in caplog.records
        ), f"expected overflow warning, got: {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_no_warning_when_font_fits(self, caplog):
        import logging

        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with caplog.at_level(logging.WARNING):
                widget_cfg = {
                    "type": "message",
                    "text": "hi",
                    "font": "Inter-Regular",
                    "font_size": 12,  # fits in 16-2=14
                }
                await _build_widget(widget_cfg, session, panel_h_for_warning=16)
        assert not any("exceeds panel height" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_warning_when_panel_h_is_none(self, caplog):
        """Bigsign (default_scale > 1) passes panel_h_for_warning=None
        to skip the check — large hi-res font_sizes are intentional."""
        import logging

        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with caplog.at_level(logging.WARNING):
                widget_cfg = {
                    "type": "message",
                    "text": "hi",
                    "font": "Inter-Regular",
                    "font_size": 40,  # huge but bigsign-appropriate
                }
                await _build_widget(widget_cfg, session, panel_h_for_warning=None)
        assert not any("exceeds panel height" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_warning_for_bdf_alias_at_any_size(self, caplog):
        """BDF fonts ignore font_size (sized by FONTBOUNDINGBOX). The
        warning is hi-res-only — pre-validated BDF fonts shouldn't
        trip it even with a `font_size` in the config."""
        import logging

        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with caplog.at_level(logging.WARNING):
                widget_cfg = {
                    "type": "message",
                    "text": "hi",
                    "font": "6x12",
                    "font_size": 40,  # ignored — BDF is 12px regardless
                }
                await _build_widget(widget_cfg, session, panel_h_for_warning=16)
        assert not any("exceeds panel height" in r.message for r in caplog.records)


class TestConfigureUserFontDir:
    """Regression: under `pip install` / Docker the package lives in
    site-packages, so the import-time default `USER_FONT_DIR` points at
    `<site-packages>/../../config/fonts` — wrong dir. `run()` re-anchors
    it based on the user's config.toml location.
    """

    def test_anchors_user_font_dir_to_config_parent_fonts(self, tmp_path, monkeypatch):
        # Snapshot the original via monkeypatch so our reassignment
        # below doesn't leak a tmp_path reference past test teardown.
        from led_ticker.fonts import hires_loader

        monkeypatch.setattr(hires_loader, "USER_FONT_DIR", hires_loader.USER_FONT_DIR)
        from led_ticker.app import _configure_user_font_dir

        config_path = tmp_path / "config.toml"
        config_path.write_text("# minimal\n")

        _configure_user_font_dir(config_path)

        assert (tmp_path / "fonts").resolve() == hires_loader.USER_FONT_DIR

    def test_finds_user_font_after_reanchor(self, tmp_path, monkeypatch):
        """End-to-end: drop a fake font next to a config and verify
        `_find_font_path` picks it up after the runtime override."""
        import led_ticker.fonts.hires_loader as hl
        from led_ticker.app import _configure_user_font_dir

        # Start with USER_FONT_DIR pointing somewhere wrong (simulating
        # Docker install where the default is bogus).
        monkeypatch.setattr(hl, "USER_FONT_DIR", tmp_path / "wrong-place")

        config_dir = tmp_path / "user-deploy"
        config_dir.mkdir()
        config_path = config_dir / "config.toml"
        config_path.write_text("# minimal\n")

        fonts_dir = config_dir / "fonts"
        fonts_dir.mkdir()
        fake_font = fonts_dir / "beloved-sans.otf"
        fake_font.write_bytes(b"not really a font, but lookup is path-only")

        # Sanity: lookup fails before the override.
        assert hl._find_font_path("beloved-sans") is None

        _configure_user_font_dir(config_path)

        found = hl._find_font_path("beloved-sans")
        assert found == fake_font.resolve()

    def test_clears_load_cache(self, tmp_path, monkeypatch):
        """If a stale (None) lookup got cached before the override, the
        new directory wouldn't be consulted. Confirm cache_clear ran."""
        from led_ticker.fonts import hires_loader

        # Snapshot to ensure tmp_path doesn't outlive the test in the
        # module global.
        monkeypatch.setattr(hires_loader, "USER_FONT_DIR", hires_loader.USER_FONT_DIR)
        from led_ticker.app import _configure_user_font_dir
        from led_ticker.fonts.hires_loader import load_hires_font

        # Poison the cache with a None for a name we'll later make findable.
        assert load_hires_font("beloved-sans-cache-test", 24) is None
        # Re-anchoring should clear the cache so a subsequent lookup
        # re-hits _find_font_path rather than returning the cached None.
        config_path = tmp_path / "config.toml"
        config_path.write_text("# minimal\n")
        _configure_user_font_dir(config_path)
        assert load_hires_font.cache_info().currsize == 0


class TestFontSizeMigration:
    """`_build_widget` rejects stale `text_scale` configs with a clear
    migration message. Loud failure at config-load (vs. silent ignore
    or TypeError at construction)."""

    @pytest.mark.asyncio
    async def test_text_scale_in_config_raises_migration_error(self, tmp_path):
        """Any `text_scale` key in a widget config dict triggers the
        migration error. Message includes the conversion formula."""
        import aiohttp
        from PIL import Image

        from led_ticker.app import _build_widget

        # Real on-disk gif so path resolution doesn't error first.
        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "text_scale": 4,
        }

        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="text_scale removed"):
                await _build_widget(cfg, s, config_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_migration_message_includes_conversion_formula(self, tmp_path):
        """The error message must tell the user *how* to migrate, not
        just that they need to. Formula: font_size = N × cell_h."""
        import aiohttp
        from PIL import Image

        from led_ticker.app import _build_widget

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "text_scale": 2,
        }

        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError) as exc_info:
                await _build_widget(cfg, s, config_dir=tmp_path)

        msg = str(exc_info.value)
        # Must include the formula and concrete examples.
        assert "font_size" in msg
        assert "cell_h" in msg or "cell height" in msg
        assert "× 12" in msg or "* 12" in msg or "12" in msg

    @pytest.mark.asyncio
    async def test_hires_font_without_font_size_raises(self, tmp_path):
        """HiresFont (any TTF/OTF name resolved to a HiresFont) requires
        explicit `font_size` — the rasterizer needs a real-px target.
        BDF fonts get the smart default, but HiresFont cannot."""
        import aiohttp
        import pytest
        from PIL import Image

        from led_ticker.app import _build_widget

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "font": "Inter-Bold",
            # No font_size!
        }

        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="HiresFont.*requires font_size"):
                await _build_widget(cfg, s, config_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_bdf_without_font_size_succeeds(self, tmp_path):
        """BDF font without font_size is the natural case — smart
        default kicks in at first paint. _build_widget shouldn't
        complain."""
        import aiohttp
        from PIL import Image

        from led_ticker.app import _build_widget

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "font": "6x12",
            # No font_size — should resolve to default BDF, no error.
        }

        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, s, config_dir=tmp_path)

        assert widget.font_size is None  # smart default, not yet resolved

    async def test_per_row_hires_font_without_size_raises(self, tmp_path):
        """The HiresFont required-explicit guard applies to per-row
        fonts too: `top_font = "Inter-Bold"` without `top_font_size`
        raises with the prefix-aware error message. Mirrors the
        single-font path; the per-row branch is symmetric and a
        future refactor could silently drop the guard if no test
        covers it."""
        import aiohttp
        import pytest
        from PIL import Image

        from led_ticker.app import _build_widget

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "top_text": "@brand",
            "bottom_text": "follow us",
            "top_font": "Inter-Bold",
            # No top_font_size!
            "bottom_font": "Inter-Regular",
            "bottom_font_size": 14,
        }

        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="HiresFont.*requires top_font_size"):
                await _build_widget(cfg, s, config_dir=tmp_path)


class TestPresentationMigration:
    """`_build_widget` rejects stale `presentation = "..."` configs
    with a clear migration mapping. animation field on non-message
    widgets is also rejected."""

    async def test_presentation_in_config_raises_migration_error(self):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {
            "type": "message",
            "text": "hi",
            "presentation": "rainbow",
        }
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="presentation removed"):
                await _build_widget(cfg, session=s)

    async def test_migration_message_includes_mapping_table(self):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "presentation": "typewriter"}
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError) as exc:
                await _build_widget(cfg, session=s)

        msg = str(exc.value)
        assert "animation" in msg
        assert "font_color" in msg
        assert "rainbow" in msg
        assert "typewriter" in msg

    async def test_animation_on_weather_raises(self, tmp_path):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {
            "type": "weather",
            "message": "NYC",
            "location": "NYC",
            "animation": "typewriter",
        }
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match='only valid on type="message"'):
                await _build_widget(cfg, session=s)

    async def test_animation_on_message_succeeds(self):
        import aiohttp

        from led_ticker.animations import Typewriter
        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "animation": "typewriter"}
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.animation, Typewriter)


class TestColorProviderCoercion:
    """`font_color` accepts list (constant), 'random', 'rainbow' /
    'color_cycle' (provider strings), or {style = "...", ...} tables."""

    async def test_list_becomes_constant_color(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import _ConstantColor

        cfg = {"type": "message", "text": "hi", "font_color": [255, 0, 0]}
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, _ConstantColor)

    async def test_string_rainbow_becomes_rainbow_provider(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Rainbow

        cfg = {"type": "message", "text": "hi", "font_color": "rainbow"}
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Rainbow)

    async def test_table_with_style_and_kwargs(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Rainbow

        cfg = {
            "type": "message",
            "text": "hi",
            "font_color": {"style": "rainbow", "speed": 16},
        }
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Rainbow)
        assert widget.font_color.speed == 16

    async def test_unknown_style_string_raises(self):
        import aiohttp
        import pytest

        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "font_color": "unknownstyle"}
        async with aiohttp.ClientSession() as s:
            with pytest.raises(ValueError, match="unknown.*style"):
                await _build_widget(cfg, session=s)

    async def test_random_string_becomes_random_provider(self):
        import aiohttp

        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Random

        cfg = {"type": "message", "text": "hi", "font_color": "random"}
        async with aiohttp.ClientSession() as s:
            widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Random)

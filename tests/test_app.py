"""Tests for led_ticker.app — widget building from config dicts."""

import unittest.mock as mock
from datetime import date
from pathlib import Path

import pytest

from led_ticker.app import (
    _build_title,
    _build_trans_obj,
    _build_widget,
    build_frame_from_config,
)
from led_ticker.config import DisplayConfig
from led_ticker.widget import Widget
from led_ticker.widgets.message import TickerCountdown, TickerMessage


def test_build_frame_passes_pixel_mapper_and_parallel():
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend

    display = DisplayConfig(
        rows=32,
        cols=64,
        chain_length=8,
        parallel=1,
        pixel_mapper_config="U-mapper",
        default_scale=4,
    )
    frame = build_frame_from_config(display)
    assert isinstance(frame.backend, RgbMatrixBackend)
    assert frame.backend.led_pixel_mapper_config == "U-mapper"
    assert frame.backend.led_parallel == 1
    assert frame.backend.led_chain_length == 8
    assert frame.backend.led_rows == 32
    assert frame.backend.led_cols == 64


def test_build_frame_forwards_led_rgb_sequence():
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend

    display = DisplayConfig(led_rgb_sequence="BGR")
    frame = build_frame_from_config(display)
    assert isinstance(frame.backend, RgbMatrixBackend)
    assert frame.backend.led_rgb_sequence == "BGR"


def test_build_frame_existing_sign_defaults():
    from led_ticker.backends.rgbmatrix import RgbMatrixBackend

    display = DisplayConfig(
        rows=16,
        cols=32,
        chain_length=5,
        brightness=60,
        gpio_slowdown=2,
    )
    frame = build_frame_from_config(display)
    assert isinstance(frame.backend, RgbMatrixBackend)
    assert frame.backend.led_pixel_mapper_config == ""
    assert frame.backend.led_parallel == 1
    assert frame.backend._brightness == 60
    assert frame.backend.led_gpio_slowdown == 2


def test_build_frame_logs_show_refresh_explanation_when_enabled(caplog):
    """show_refresh_rate=true makes the C library print Hz to stderr with
    backspaces — looks like log corruption to first-time readers. We
    log a one-time note pointing at where to look so it's not mistaken
    for a glitch."""
    import logging

    display = DisplayConfig(rows=32, cols=64, chain_length=8, show_refresh_rate=True)
    with caplog.at_level(logging.INFO):
        build_frame_from_config(display)
    msgs = [r.message for r in caplog.records]
    assert any("show_refresh_rate=true" in m and "stderr" in m for m in msgs), (
        f"expected show_refresh_rate explanation; got: {msgs}"
    )


def test_build_frame_no_show_refresh_log_when_disabled(caplog):
    """No spurious explainer log when the user didn't ask for it."""
    import logging

    display = DisplayConfig(rows=16, cols=32, chain_length=5, show_refresh_rate=False)
    with caplog.at_level(logging.INFO):
        build_frame_from_config(display)
    msgs = [r.message for r in caplog.records]
    assert not any("live Hz updates" in m for m in msgs), (
        f"didn't expect show_refresh_rate explainer; got: {msgs}"
    )


class TestBuildWidget:
    """Test that _build_widget correctly maps config dicts to widget instances."""

    async def test_message_with_text_key(self):
        """Config uses 'text' — populates the text field directly."""
        cfg = {"type": "message", "text": "Hello world"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerMessage)
        assert widget.text == "Hello world"

    async def test_message_with_message_key_raises_migration_error(self):
        """Old 'message' key now raises MigrationError."""
        from led_ticker.validate import MigrationError

        cfg = {"type": "message", "message": "Hello world"}
        with pytest.raises(MigrationError, match="text"):
            await _build_widget(cfg, session=mock.Mock())

    async def test_countdown_with_text_key(self):
        """Countdown config uses 'text' — populates the text field directly."""
        cfg = {
            "type": "countdown",
            "text": "Days Until Spring",
            "countdown_date": date(2026, 3, 20),
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget, TickerCountdown)
        assert widget.text == "Days Until Spring"

    async def test_countdown_with_message_key_raises_migration_error(self):
        """Old 'message' key on countdown now raises MigrationError."""
        from led_ticker.validate import MigrationError

        cfg = {
            "type": "countdown",
            "message": "Days Until Spring",
            "countdown_date": date(2026, 3, 20),
        }
        with pytest.raises(MigrationError, match="text"):
            await _build_widget(cfg, session=mock.Mock())

    async def test_unknown_widget_type_raises(self):
        cfg = {"type": "nonexistent_widget"}
        with pytest.raises(ValueError, match="Unknown widget type"):
            await _build_widget(cfg, session=mock.Mock())

    async def test_both_text_and_message_keys_raise_migration_error(self):
        """Having both 'text' and 'message' raises MigrationError."""
        from led_ticker.validate import MigrationError

        cfg = {
            "type": "message",
            "text": "from text",
            "message": "from message",
        }
        with pytest.raises(MigrationError, match="text"):
            await _build_widget(cfg, session=mock.Mock())

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
            assert widget.text == "repeat"


class TestBuildTitle:
    async def test_build_title_with_text(self):
        title = await _build_title(
            {"text": "News", "font_color": "random"}, session=mock.Mock()
        )
        assert isinstance(title, TickerMessage)
        assert title.text == "News"

    async def test_build_title_none(self):
        title = await _build_title(None, session=mock.Mock())
        assert title is None

    async def test_build_title_no_color(self):
        title = await _build_title({"text": "Plain"}, session=mock.Mock())
        assert isinstance(title, TickerMessage)
        assert title.text == "Plain"

    async def test_build_title_empty_text(self):
        title = await _build_title({"text": ""}, session=mock.Mock())
        assert isinstance(title, TickerMessage)
        assert title.text == ""

    async def test_build_title_with_rgb_list_color(self):
        # TOML inline-tables and arrays come through as lists. The loader
        # should coerce a 3-int list into a graphics.Color (wrapped in
        # _ConstantColor after post_init). Access via color_for().
        title = await _build_title(
            {"text": "Pink", "font_color": [255, 150, 190]}, session=mock.Mock()
        )
        assert title is not None
        color = title.font_color.color_for(0, 0, 1)
        assert color.red == 255
        assert color.green == 150
        assert color.blue == 190

    async def test_build_title_with_provider_string(self):
        """Title `font_color = "rainbow"` should produce a Rainbow provider."""
        from led_ticker.color_providers import Rainbow

        title = await _build_title(
            {"text": "Hi", "font_color": "rainbow"}, session=mock.Mock()
        )
        assert title is not None
        assert isinstance(title.font_color, Rainbow)

    async def test_build_title_with_provider_table(self):
        """Title font_color with style="gradient" should produce a Gradient provider."""
        from led_ticker.color_providers import Gradient

        title = await _build_title(
            {
                "text": "Hi",
                "font_color": {
                    "style": "gradient",
                    "from": [255, 0, 0],
                    "to": [0, 0, 255],
                },
            },
            session=mock.Mock(),
        )
        assert title is not None
        assert isinstance(title.font_color, Gradient)

    async def test_build_title_with_font_field(self):
        """Regression: `font = "..."` on [playlist.section.title] was
        silently dropped. Docs say the title is "a regular message widget
        with all its knobs available" — that includes `font`."""
        from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL

        title = await _build_title({"text": "Hi", "font": "5x8"}, session=mock.Mock())
        assert title is not None
        assert title.font is FONT_SMALL
        assert title.font is not FONT_DEFAULT

    async def test_build_title_with_animation(self):
        """Contract lockdown: `animation = "typewriter"` reaches the
        title widget (previously dropped silently)."""
        title = await _build_title(
            {"text": "Hi", "animation": "typewriter"}, session=mock.Mock()
        )
        assert title is not None
        assert title.animation is not None

    async def test_build_title_with_border(self):
        """Contract lockdown: `border = "rainbow_chase"` reaches the
        title widget (previously dropped silently)."""
        from led_ticker.borders import RainbowChaseBorder

        title = await _build_title(
            {"text": "Hi", "border": "rainbow"}, session=mock.Mock()
        )
        assert title is not None
        assert isinstance(title.border, RainbowChaseBorder)

    async def test_build_title_with_bg_color(self):
        """Contract lockdown: `bg_color = [r, g, b]` reaches the title
        widget (previously dropped silently)."""
        title = await _build_title(
            {"text": "Hi", "bg_color": [10, 20, 30]}, session=mock.Mock()
        )
        assert title is not None
        assert title.bg_color is not None
        assert title.bg_color.red == 10
        assert title.bg_color.green == 20
        assert title.bg_color.blue == 30

    async def test_build_title_font_color_alias_for_color(self):
        """`font_color` works on titles too (docs list both spellings
        and they should be interchangeable for new configs)."""
        title = await _build_title(
            {"text": "Hi", "font_color": [200, 100, 50]}, session=mock.Mock()
        )
        assert title is not None
        c = title.font_color.color_for(0, 0, 1)
        assert (c.red, c.green, c.blue) == (200, 100, 50)


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
                title = await _build_title(section.title, session=mock.Mock())
                assert isinstance(title, TickerMessage)

            # Build each widget
            for widget_cfg in section.widgets:
                cfg = dict(widget_cfg)
                widget_type = cfg.get("type")

                widget = await _build_widget(cfg, session=mock.Mock())
                assert isinstance(widget, Widget), (
                    f"Widget type={widget_type} did not produce a Widget"
                )

    async def test_firebird_bigsign_config_widgets_build(self):
        """Load config.firebird.example.toml and build every widget.

        Exercises: TOML RGB color lists, inline :instagram: and :email:
        emoji slugs, multi-section layout, hires fonts, image/gif widgets
        with rainbow border, brand color palette.
        """
        from led_ticker.config import load_config
        from led_ticker.widgets.gif import GifPlayer
        from led_ticker.widgets.still import StillImage
        from led_ticker.widgets.two_row import TwoRowMessage

        config_path = (
            Path(__file__).resolve().parent.parent
            / "config"
            / "config.firebird.example.toml"
        )
        # The Firebird config references the licensed Beloved Sans font, which
        # lives in the gitignored config/fonts/ directory and is not available
        # in CI. Skip when the font file is missing rather than fail the build.
        beloved_font = config_path.parent / "fonts" / "beloved-sans-bold.otf"
        if not beloved_font.exists():
            pytest.skip(f"licensed font not available: {beloved_font}")
        config = load_config(config_path)

        for section in config.sections:
            if section.title:
                title = await _build_title(section.title, session=mock.Mock())
                assert isinstance(title, TickerMessage)

            for widget_cfg in section.widgets:
                cfg = dict(widget_cfg)
                widget = await _build_widget(cfg, session=mock.Mock())
                assert isinstance(
                    widget, TickerMessage | TwoRowMessage | StillImage | GifPlayer
                )
                if isinstance(widget, TickerMessage):
                    # font_color is a ColorProvider (has color_for)
                    assert hasattr(widget.font_color, "color_for")
                elif isinstance(widget, TwoRowMessage):
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

        from led_ticker.app import _build_widget

        session = mock.Mock()
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

        from led_ticker.app import _build_widget

        session = mock.Mock()
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
        from led_ticker.app import _build_widget

        session = mock.Mock()
        widget_cfg = {"type": "message", "text": "hi"}
        widget = await _build_widget(widget_cfg, session)
        assert widget.bg_color is None


class TestBuildWidgetFontResolution:
    @pytest.mark.asyncio
    async def test_hires_font_name_resolves_to_HiresFont(self):
        from led_ticker.app import _build_widget
        from led_ticker.fonts.hires_loader import HiresFont

        session = mock.Mock()
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
        from led_ticker.app import _build_widget
        from led_ticker.fonts import FONT_DEFAULT

        session = mock.Mock()
        widget_cfg = {"type": "message", "text": "hi", "font": "6x12"}
        widget = await _build_widget(widget_cfg, session)
        assert widget.font is FONT_DEFAULT

    @pytest.mark.asyncio
    async def test_no_font_field_keeps_class_default(self):
        from led_ticker.app import _build_widget
        from led_ticker.fonts import FONT_DEFAULT

        session = mock.Mock()
        widget_cfg = {"type": "message", "text": "hi"}
        widget = await _build_widget(widget_cfg, session)
        # TickerMessage's class default is FONT_DEFAULT.
        assert widget.font is FONT_DEFAULT

    @pytest.mark.asyncio
    async def test_unknown_font_name_raises(self):
        from led_ticker.app import _build_widget
        from led_ticker.fonts import UnknownFontError

        session = mock.Mock()
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
        import pytest

        from led_ticker.app import _build_widget

        session = mock.Mock()
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

        from led_ticker.app import _build_widget
        from led_ticker.fonts.hires_loader import HiresFont

        session = mock.Mock()
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

        from led_ticker.app import _build_widget

        session = mock.Mock()
        widget_cfg = {
            "type": "message",
            "text": "hi",
            "font": "Inter-Regular",
            "font_size": 24,
            "font_threshold": 80,
        }
        # Would raise TypeError if font_threshold leaked into TickerMessage.
        widget = await _build_widget(widget_cfg, session)
        assert widget.text == "hi"
        assert not hasattr(widget, "font_threshold")


class TestBuildWidgetCoerceNumeric:
    @pytest.mark.asyncio
    async def test_coerces_font_size_string(self):
        """font_size = "25" should coerce to int 25 and emit a warning,
        not crash with TypeError deep in resolve_font."""

        from led_ticker._coerce import CoercionWarning
        from led_ticker.app import _build_widget

        warnings: list[CoercionWarning] = []
        session = mock.Mock()
        widget_cfg = {
            "type": "message",
            "text": "hi",
            "font": "Inter-Bold",
            "font_size": "25",
        }
        widget = await _build_widget(
            widget_cfg,
            session,
            coercion_collector=warnings,
        )
        assert widget is not None
        assert any(w.field == "widget.font_size" for w in warnings)

    @pytest.mark.asyncio
    async def test_coerces_font_threshold_string(self):
        from led_ticker._coerce import CoercionWarning
        from led_ticker.app import _build_widget

        warnings: list[CoercionWarning] = []
        session = mock.Mock()
        widget_cfg = {
            "type": "message",
            "text": "hi",
            "font": "Inter-Bold",
            "font_size": 25,
            "font_threshold": "80",
        }
        widget = await _build_widget(
            widget_cfg,
            session,
            coercion_collector=warnings,
        )
        assert widget is not None
        assert any(w.field == "widget.font_threshold" for w in warnings)

    @pytest.mark.asyncio
    async def test_font_size_bool_still_rejected(self):
        """Bool stays a hard error — the existing rule 28 guard pattern."""

        from led_ticker.app import _build_widget

        session = mock.Mock()
        widget_cfg = {
            "type": "message",
            "text": "hi",
            "font": "Inter-Bold",
            "font_size": True,
        }
        with pytest.raises(ValueError, match="must be an int"):
            await _build_widget(widget_cfg, session)


class TestSmallSignFontSizeGuard:
    """Hi-res renders at native physical pixels. On the small sign
    (default_scale=1, panel_h=16), a font_size > 14 will overflow
    vertically. Warn the user instead of silently clipping.
    """

    @pytest.mark.asyncio
    async def test_warns_when_font_size_overflows_small_sign(self, caplog):
        import logging

        from led_ticker.app import _build_widget

        session = mock.Mock()
        with caplog.at_level(logging.WARNING):
            widget_cfg = {
                "type": "message",
                "text": "hi",
                "font": "Inter-Regular",
                "font_size": 24,  # bigger than 16-2=14
            }
            await _build_widget(widget_cfg, session, panel_h_for_warning=16)
        assert any("exceeds panel height" in r.message for r in caplog.records), (
            f"expected overflow warning, got: {[r.message for r in caplog.records]}"
        )

    @pytest.mark.asyncio
    async def test_no_warning_when_font_fits(self, caplog):
        import logging

        from led_ticker.app import _build_widget

        session = mock.Mock()
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

        from led_ticker.app import _build_widget

        session = mock.Mock()
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

        from led_ticker.app import _build_widget

        session = mock.Mock()
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

        _configure_user_font_dir(config_path.parent)

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

        # Check: lookup fails before the override.
        assert hl._find_font_path("beloved-sans") is None

        _configure_user_font_dir(config_path.parent)

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
        _configure_user_font_dir(config_path.parent)
        assert load_hires_font.cache_info().currsize == 0


class TestFontSizeMigration:
    """`_build_widget` rejects stale `text_scale` configs with a clear
    migration message. Loud failure at config-load (vs. silent ignore
    or TypeError at construction)."""

    @pytest.mark.asyncio
    async def test_text_scale_in_config_raises_migration_error(self, tmp_path):
        """Any `text_scale` key in a widget config dict triggers the
        migration error. Message includes the conversion formula."""
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

        from led_ticker.validate import MigrationError

        s = mock.Mock()
        with pytest.raises(MigrationError, match="text_scale removed"):
            await _build_widget(cfg, s, config_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_text_scale_raises_migration_error_not_value_error(self, tmp_path):
        from led_ticker.app import _build_widget
        from led_ticker.validate import MigrationError

        cfg = {"type": "message", "text": "hi", "text_scale": 2}
        with pytest.raises(MigrationError, match="text_scale removed"):
            await _build_widget(cfg, session=None, config_dir=tmp_path)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_migration_message_includes_conversion_formula(self, tmp_path):
        """The error message must tell the user *how* to migrate, not
        just that they need to. Formula: font_size = N × cell_h."""
        from PIL import Image

        from led_ticker.app import _build_widget
        from led_ticker.validate import MigrationError

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4)).save(gif_path, format="GIF")

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "fit": "stretch",
            "text": "hi",
            "text_scale": 2,
        }

        s = mock.Mock()
        with pytest.raises(MigrationError) as exc_info:
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

        s = mock.Mock()
        with pytest.raises(ValueError, match="HiresFont.*requires font_size"):
            await _build_widget(cfg, s, config_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_bdf_without_font_size_succeeds(self, tmp_path):
        """BDF font without font_size is the natural case — smart
        default kicks in at first paint. _build_widget shouldn't
        complain."""
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

        s = mock.Mock()
        widget = await _build_widget(cfg, s, config_dir=tmp_path)

        assert widget.font_size is None  # smart default, not yet resolved

    async def test_per_row_hires_font_without_size_raises(self, tmp_path):
        """The HiresFont required-explicit guard applies to per-row
        fonts too: `top_font = "Inter-Bold"` without `top_font_size`
        raises with the prefix-aware error message. Mirrors the
        single-font path; the per-row branch is symmetric and a
        future refactor could silently drop the guard if no test
        covers it."""
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

        s = mock.Mock()
        with pytest.raises(ValueError, match="HiresFont.*requires top_font_size"):
            await _build_widget(cfg, s, config_dir=tmp_path)


class TestPresentationMigration:
    """`_build_widget` rejects stale `presentation = "..."` configs
    with a clear migration mapping. animation field on non-message
    widgets is also rejected."""

    async def test_presentation_in_config_raises_migration_error(self):
        import pytest

        from led_ticker.app import _build_widget
        from led_ticker.validate import MigrationError

        cfg = {
            "type": "message",
            "text": "hi",
            "presentation": "rainbow",
        }
        s = mock.Mock()
        with pytest.raises(MigrationError, match="presentation removed"):
            await _build_widget(cfg, session=s)

    @pytest.mark.asyncio
    async def test_presentation_raises_migration_error_not_value_error(self):
        from led_ticker.app import _build_widget
        from led_ticker.validate import MigrationError

        cfg = {"type": "message", "text": "hi", "presentation": "rainbow"}
        with pytest.raises(MigrationError, match="presentation removed"):
            await _build_widget(cfg, session=None)  # type: ignore[arg-type]

    async def test_migration_message_includes_mapping_table(self):
        import pytest

        from led_ticker.app import _build_widget
        from led_ticker.validate import MigrationError

        cfg = {"type": "message", "text": "hi", "presentation": "typewriter"}
        s = mock.Mock()
        with pytest.raises(MigrationError) as exc:
            await _build_widget(cfg, session=s)

        msg = str(exc.value)
        assert "animation" in msg
        assert "font_color" in msg
        assert "rainbow" in msg
        assert "typewriter" in msg

    async def test_animation_on_message_succeeds(self):
        from led_ticker.animations import Typewriter
        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "animation": "typewriter"}
        s = mock.Mock()
        widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.animation, Typewriter)

    async def test_animation_field_accepted_on_image_widget(self, tmp_path):
        """`type = "image"` with `animation = "typewriter"` builds without
        error. Mirrors the existing TickerMessage animation acceptance.
        Uses a real PNG so _load() doesn't trip."""
        from PIL import Image

        from led_ticker.app import _build_widget

        img_path = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)

        cfg = {
            "type": "image",
            "path": str(img_path),
            "text": "Hello",
            "text_align": "left",
            "animation": "typewriter",
        }
        s = mock.Mock()
        widget = await _build_widget(cfg, session=s)
        assert widget.animation is not None

    async def test_animation_field_accepted_on_gif_widget(self, tmp_path):
        """`type = "gif"` with `animation = "typewriter"` builds. Same
        contract as image — the field lives on `_BaseImageWidget`."""
        from PIL import Image

        from led_ticker.app import _build_widget

        gif_path = tmp_path / "x.gif"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(gif_path)

        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "text": "Hello",
            "text_align": "left",
            "animation": "typewriter",
        }
        s = mock.Mock()
        widget = await _build_widget(cfg, session=s)
        assert widget.animation is not None


class TestColorProviderCoercion:
    """`font_color` accepts list (constant), 'random', 'rainbow' /
    'color_cycle' (provider strings), or {style = "...", ...} tables."""

    async def test_list_becomes_constant_color(self):
        from led_ticker.app import _build_widget
        from led_ticker.color_providers import _ConstantColor

        cfg = {"type": "message", "text": "hi", "font_color": [255, 0, 0]}
        s = mock.Mock()
        widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, _ConstantColor)

    async def test_string_rainbow_becomes_rainbow_provider(self):
        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Rainbow

        cfg = {"type": "message", "text": "hi", "font_color": "rainbow"}
        s = mock.Mock()
        widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Rainbow)

    async def test_table_with_style_and_kwargs(self):
        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Rainbow

        cfg = {
            "type": "message",
            "text": "hi",
            "font_color": {"style": "rainbow", "speed": 16},
        }
        s = mock.Mock()
        widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Rainbow)
        assert widget.font_color.speed == 16

    async def test_unknown_style_string_raises(self):
        import pytest

        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "font_color": "unknownstyle"}
        s = mock.Mock()
        with pytest.raises(ValueError, match="unknown.*style"):
            await _build_widget(cfg, session=s)

    async def test_random_string_becomes_random_provider(self):
        from led_ticker.app import _build_widget
        from led_ticker.color_providers import Random

        cfg = {"type": "message", "text": "hi", "font_color": "random"}
        s = mock.Mock()
        widget = await _build_widget(cfg, session=s)
        assert isinstance(widget.font_color, Random)


class TestBuildTransObj:
    """The `_build_trans_obj` helper constructs a transition instance
    from a `TransitionConfig`. Used for both the global
    `between_sections` and per-section `transition` overrides — the
    same factory drives both, keeping behavior consistent."""

    def test_cut_returns_none(self):
        from led_ticker.config import TransitionConfig

        cfg = TransitionConfig(type="cut")
        assert _build_trans_obj(cfg) is None

    def test_named_transition_returns_instance(self):
        from led_ticker.config import TransitionConfig
        from led_ticker.transitions import get_transition_class

        cfg = TransitionConfig(type="dissolve")
        obj = _build_trans_obj(cfg)
        assert obj is not None
        assert isinstance(obj, get_transition_class("dissolve"))

    def test_color_threaded(self):
        from led_ticker.config import TransitionConfig

        cfg = TransitionConfig(type="color_flash", color=(255, 100, 50))
        obj = _build_trans_obj(cfg)
        assert obj is not None


class TestBuildTransObjGuarded:
    """`_build_trans_obj_guarded` degrades an un-buildable transition (e.g. an
    uninstalled plugin transition referenced in `between_sections` or a section
    `transition`) to None (= cut) + a logged warning, instead of raising and
    crashing the sign — parity with `_build_widget_guarded`. The unguarded
    `_build_trans_obj` still raises so `led-ticker validate` can report it."""

    def test_unknown_plugin_transition_degrades_to_none_with_log(self, caplog):
        import logging

        from led_ticker.app.run import _build_trans_obj_guarded
        from led_ticker.config import TransitionConfig

        # The exact case from the field crash: a plugin transition whose plugin
        # isn't installed.
        cfg = TransitionConfig(type="arcade.nyancat_alternating")

        # Unguarded path raises (validate.py relies on this).
        with pytest.raises(ValueError):
            _build_trans_obj(cfg)

        # Guarded path degrades to None and logs which type failed.
        with caplog.at_level(logging.WARNING):
            assert _build_trans_obj_guarded(cfg) is None
        assert any("arcade.nyancat_alternating" in r.message for r in caplog.records), (
            "the failing transition type should be logged"
        )

    def test_cut_returns_none(self):
        from led_ticker.app.run import _build_trans_obj_guarded
        from led_ticker.config import TransitionConfig

        assert _build_trans_obj_guarded(TransitionConfig(type="cut")) is None

    def test_valid_transition_still_built(self):
        from led_ticker.app.run import _build_trans_obj_guarded
        from led_ticker.config import TransitionConfig
        from led_ticker.transitions import get_transition_class

        obj = _build_trans_obj_guarded(TransitionConfig(type="dissolve"))
        assert obj is not None
        assert isinstance(obj, get_transition_class("dissolve"))


class TestSectionTransitionFiresOnEntry:
    """Integration: when a section explicitly specifies `transition`,
    the engine uses that transition for the inter-section ENTRY (not
    just inter-widget). Tests inspect the engine's selection logic by
    running a single section iteration with mocked `run_transition` and
    verifying it received the section-specific transition object.
    """

    async def test_section_with_explicit_transition_uses_it_for_entry(
        self, tmp_path, monkeypatch
    ):
        from led_ticker import app
        from led_ticker.transitions import get_transition_class

        config_file = tmp_path / "c.toml"
        config_file.write_text(
            """[display]
rows = 16
cols = 32
chain_length = 5
default_scale = 1
[transitions]
between_sections = "dissolve"
[[playlist.section]]
mode = "slideshow"
transition = "wipe_left"
[[playlist.section.widget]]
type = "message"
text = "FIRST"
[[playlist.section]]
mode = "slideshow"
transition = "wipe_left"
[[playlist.section.widget]]
type = "message"
text = "SECOND"
"""
        )

        cfg = app.load_config(config_file)
        # Both sections explicitly specify wipe_left.
        assert cfg.sections[0].transition_specified is True
        assert cfg.sections[1].transition_specified is True

        # Simulate the entry-selection logic: section.transition_specified
        # → use _build_trans_obj(section.transition); else fall back.
        default_section_trans = _build_trans_obj(cfg.between_sections)
        entries = []
        for section in cfg.sections:
            if section.transition_specified:
                entries.append(_build_trans_obj(section.transition))
            else:
                entries.append(default_section_trans)

        # Both entries should be wipe_left instances, not dissolve.
        wipe_left_cls = get_transition_class("wipe_left")
        dissolve_cls = get_transition_class("dissolve")
        assert all(isinstance(t, wipe_left_cls) for t in entries)
        assert not any(isinstance(t, dissolve_cls) for t in entries)

    async def test_section_without_transition_falls_back_to_between_sections(
        self, tmp_path
    ):
        from led_ticker import app
        from led_ticker.transitions import get_transition_class

        config_file = tmp_path / "c.toml"
        config_file.write_text(
            """[display]
rows = 16
cols = 32
chain_length = 5
default_scale = 1
[transitions]
between_sections = "dissolve"
[[playlist.section]]
mode = "slideshow"
[[playlist.section.widget]]
type = "message"
text = "ONLY"
"""
        )

        cfg = app.load_config(config_file)
        assert cfg.sections[0].transition_specified is False

        # Selection should fall back to between_sections (dissolve).
        default_section_trans = _build_trans_obj(cfg.between_sections)
        section = cfg.sections[0]
        entry = (
            _build_trans_obj(section.transition)
            if section.transition_specified
            else default_section_trans
        )
        assert isinstance(entry, get_transition_class("dissolve"))


class TestCoerceBorder:
    """`_coerce_border` maps TOML shapes to BorderEffect instances.
    Mirrors the `_coerce_color_provider` / `_coerce_animation`
    surface."""

    def test_none_passes_through(self):
        from led_ticker.app import _coerce_border

        assert _coerce_border(None) is None

    def test_string_rainbow_returns_default_chase(self):
        from led_ticker.app import _coerce_border
        from led_ticker.borders import RainbowChaseBorder

        b = _coerce_border("rainbow")
        assert isinstance(b, RainbowChaseBorder)
        assert b.thickness == 1

    def test_inline_table_rainbow_with_kwargs(self):
        from led_ticker.app import _coerce_border
        from led_ticker.borders import RainbowChaseBorder

        b = _coerce_border(
            {"style": "rainbow", "speed": 12, "char_offset": 9, "thickness": 2}
        )
        assert isinstance(b, RainbowChaseBorder)
        assert b.speed == 12
        assert b.char_offset == 9
        assert b.thickness == 2

    def test_constant_inline_table(self):
        from led_ticker.app import _coerce_border
        from led_ticker.borders import ConstantBorder

        b = _coerce_border({"style": "constant", "color": [255, 0, 0]})
        assert isinstance(b, ConstantBorder)
        assert b._rgb == (255, 0, 0)

    def test_rgb_list_shorthand_returns_constant(self):
        from led_ticker.app import _coerce_border
        from led_ticker.borders import ConstantBorder

        b = _coerce_border([0, 200, 100])
        assert isinstance(b, ConstantBorder)
        assert b._rgb == (0, 200, 100)

    def test_already_a_border_passes_through(self):
        from led_ticker.app import _coerce_border
        from led_ticker.borders import RainbowChaseBorder

        existing = RainbowChaseBorder(speed=99)
        assert _coerce_border(existing) is existing

    def test_unknown_string_raises(self):
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="unknown border style"):
            _coerce_border("explode")

    def test_inline_table_unknown_style_raises(self):
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="unknown border style"):
            _coerce_border({"style": "neon"})

    def test_inline_table_missing_style_raises(self):
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="border table requires 'style'"):
            _coerce_border({"speed": 8})

    def test_constant_missing_color_raises(self):
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="requires 'color'"):
            _coerce_border({"style": "constant"})

    def test_unknown_kwarg_raises(self):
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="unknown keys"):
            _coerce_border({"style": "rainbow", "wobble": 5})

    def test_bool_list_rejected_not_treated_as_rgb(self):
        """[True, False, True] would silently coerce to (1, 0, 1)
        without the explicit bool rejection (bool is an int
        subclass). Hardening matches the `font_threshold` pattern
        documented in CLAUDE.md."""
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="components must be ints"):
            _coerce_border([True, False, True])

    def test_out_of_range_rgb_rejected(self):
        """RGB byte values must be 0..255. SetPixel takes bytes;
        passing 300 or -50 is undefined behavior. Reject loudly at
        config-load instead."""
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="0-255"):
            _coerce_border([300, 50, 100])
        with pytest.raises(ValueError, match="0-255"):
            _coerce_border([0, -1, 100])
        with pytest.raises(ValueError, match="0-255"):
            _coerce_border([255, 256, 0])

    def test_inline_constant_table_validates_color_range(self):
        """Range check applies to the inline-table `constant` form too."""
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="0-255"):
            _coerce_border({"style": "constant", "color": [256, 0, 0]})
        with pytest.raises(ValueError, match="components must be ints"):
            _coerce_border({"style": "constant", "color": [True, False, True]})

    def test_inline_rainbow_with_no_kwargs_uses_defaults(self):
        """`{style="rainbow"}` with no other keys must construct
        a default RainbowChaseBorder (no error, no missing-kwarg
        complaints — all kwargs have defaults)."""
        from led_ticker.app import _coerce_border
        from led_ticker.borders import RainbowChaseBorder

        b = _coerce_border({"style": "rainbow"})
        assert isinstance(b, RainbowChaseBorder)
        # Defaults preserved
        assert b.speed == 4
        assert b.char_offset == 6
        assert b.thickness == 1


class TestCoerceLightbulbsShorthand:
    def test_string_shorthand(self):
        """border = "lightbulbs" → LightbulbBorder with defaults."""
        from led_ticker.app import _coerce_border
        from led_ticker.borders import LightbulbBorder

        result = _coerce_border("lightbulbs")
        assert isinstance(result, LightbulbBorder)
        assert result.mode == "chase"
        assert result._bulb_size_override is None
        assert result.gap == 3


class TestCoerceLightbulbsTable:
    def test_minimal_table(self):
        """border = {style="lightbulbs"} → LightbulbBorder with defaults."""
        from led_ticker.app import _coerce_border
        from led_ticker.borders import LightbulbBorder

        result = _coerce_border({"style": "lightbulbs"})
        assert isinstance(result, LightbulbBorder)
        assert result.mode == "chase"

    def test_full_table(self):
        """All knobs round-trip through coercion."""
        from led_ticker.app import _coerce_border
        from led_ticker.borders import LightbulbBorder

        result = _coerce_border(
            {
                "style": "lightbulbs",
                "mode": "alternate",
                "bulb_size": 2,
                "gap": 4,
                "lit_color": [200, 100, 50],
                "unlit_color": [10, 5, 0],
                "speed_frames": 6,
                "chase_density": 2,
                "direction": "ccw",
            }
        )
        assert isinstance(result, LightbulbBorder)
        assert result.mode == "alternate"
        assert result._bulb_size_override == 2
        assert result.gap == 4
        assert result.lit_color == (200, 100, 50)
        assert result.unlit_color == (10, 5, 0)
        assert result.speed_frames == 6
        assert result.chase_density == 2
        assert result.direction == "ccw"

    def test_rejects_unknown_key(self):
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError, match="unknown keys"):
            _coerce_border(
                {
                    "style": "lightbulbs",
                    "mode": "chase",
                    "wattage": 60,  # not a real field
                }
            )

    def test_rgb_validation_lit_color(self):
        """lit_color = [r,g,b] must pass _validate_rgb."""
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError):
            _coerce_border(
                {
                    "style": "lightbulbs",
                    "lit_color": [300, 0, 0],  # > 255
                }
            )

    def test_rgb_validation_unlit_color(self):
        from led_ticker.app import _coerce_border

        with pytest.raises(ValueError):
            _coerce_border(
                {
                    "style": "lightbulbs",
                    "unlit_color": [-1, 0, 0],
                }
            )


class TestBuildWidgetWithBorder:
    """Integration: TickerMessage with `border = "rainbow"` builds
    cleanly. Border on non-message widget types is rejected loudly
    at config-load (mirrors the `animation` TickerMessage-only
    rule)."""

    async def test_message_with_border_rainbow_string(self):
        from led_ticker.borders import RainbowChaseBorder

        cfg = {"type": "message", "text": "HI", "border": "rainbow"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.border, RainbowChaseBorder)

    async def test_message_with_border_constant_table(self):
        from led_ticker.borders import ConstantBorder

        cfg = {
            "type": "message",
            "text": "HI",
            "border": {"style": "constant", "color": [255, 100, 50]},
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.border, ConstantBorder)
        assert widget.border._rgb == (255, 100, 50)

    async def test_countdown_with_border_string(self):
        """TickerCountdown also accepts `border` (extended in the
        followup PR). Field name + paint contract identical to
        TickerMessage."""
        from led_ticker.borders import RainbowChaseBorder

        cfg = {
            "type": "countdown",
            "text": "Days to NYE",
            "countdown_date": date(2027, 1, 1),
            "border": "rainbow",
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.border, RainbowChaseBorder)

    async def test_message_without_border_accepts_border(self):
        """All core widgets accept border — the guard only fires for plugin
        widgets that don't declare a border attrs field."""
        cfg = {"type": "message", "text": "HI", "border": "rainbow"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert widget.border is not None

    async def test_message_without_border_has_none(self):
        cfg = {"type": "message", "text": "HI"}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert widget.border is None

    async def test_countdown_without_border_has_none(self):
        cfg = {
            "type": "countdown",
            "text": "Days",
            "countdown_date": date(2027, 1, 1),
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert widget.border is None

    async def test_two_row_with_border_string(self):
        """TwoRowMessage accepts `border` with the same TOML
        vocabulary. Storefront-style brand layouts (held handle on
        top, scrolling tagline on bottom) wear a rainbow chase frame."""
        from led_ticker.borders import RainbowChaseBorder

        cfg = {
            "type": "two_row",
            "top_text": "@brand",
            "bottom_text": "tagline",
            "border": "rainbow",
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.border, RainbowChaseBorder)

    async def test_two_row_without_border_has_none(self):
        cfg = {
            "type": "two_row",
            "top_text": "@brand",
            "bottom_text": "tagline",
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert widget.border is None

    async def test_gif_with_border_string(self, tmp_path):
        """GifPlayer accepts `border` with the same TOML vocabulary."""
        from PIL import Image

        from led_ticker.borders import RainbowChaseBorder

        gif_path = tmp_path / "tiny.gif"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(
            gif_path,
            save_all=True,
            append_images=[
                Image.new("RGB", (4, 4), (0, 255, 0)),
            ],
            duration=100,
            loop=0,
        )
        cfg = {
            "type": "gif",
            "path": str(gif_path),
            "border": "rainbow",
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.border, RainbowChaseBorder)

    async def test_image_with_border_table(self, tmp_path):
        """StillImage accepts `border` as an inline table."""
        from PIL import Image

        from led_ticker.borders import ConstantBorder

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        cfg = {
            "type": "image",
            "path": str(img_path),
            "border": {"style": "constant", "color": [0, 255, 0]},
        }
        widget = await _build_widget(cfg, session=mock.Mock())
        assert isinstance(widget.border, ConstantBorder)

    async def test_image_without_border_has_none(self, tmp_path):
        from PIL import Image

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img_path)
        cfg = {"type": "image", "path": str(img_path)}
        widget = await _build_widget(cfg, session=mock.Mock())
        assert widget.border is None


class _StopApp(Exception):
    """Sentinel raised from a patched dependency to break out of
    `app.run`'s `while True` loop in tests."""


class TestAppRunDrainLoopTripwire:
    """Tripwire for the Task 11 shape-bug: the per-section runtime
    coerce-drain loop must NOT engulf the widget-expansion block. If
    it does (as in the commit that was caught at final verification),
    sections with no coerce warnings — the common case — get an empty
    widgets list and the engine hangs in `while True`.

    The test exercises run() on a section whose widget HAS a coerce
    warning (font_size = "25"), then asserts that Ticker was
    constructed with a non-empty monitors list. If the drain-and-expand
    blocks ever get re-tangled, this fails with len(monitors) == 0
    instead of hanging.
    """

    @staticmethod
    async def _run_one_section(widget_cfg: dict) -> list:
        """Helper: invoke app.run() with a single-section config until
        Ticker is constructed; return the kwargs Ticker received."""
        import sys

        # Import the module first to ensure it's in sys.modules
        import led_ticker.app.run  # noqa: F401
        from led_ticker.app import run as app_run
        from led_ticker.config import (
            AppConfig,
            DisplayConfig,
            SectionConfig,
            TransitionConfig,
        )

        run_module = sys.modules["led_ticker.app.run"]

        cfg = AppConfig(
            display=DisplayConfig(rows=16, cols=32, chain_length=5),
            sections=[
                SectionConfig(
                    mode="slideshow",
                    widgets=[widget_cfg],
                ),
            ],
            between_sections=TransitionConfig(type="cut"),
        )

        captured: list = []

        class _CapturingTicker:
            def __init__(self, *args, **kwargs):
                captured.append(kwargs)
                self.last_scroll_pos = 0
                raise _StopApp("captured monitors")

            async def run_slideshow(self, **kw):
                pass

        with (
            mock.patch.object(run_module, "load_config", return_value=cfg),
            mock.patch.object(
                run_module,
                "build_frame_from_config",
                return_value=mock.Mock(
                    **{"get_clean_canvas.return_value": mock.Mock(height=16, width=160)}
                ),
            ),
            mock.patch.object(run_module, "_configure_user_font_dir"),
            mock.patch.object(run_module, "Ticker", _CapturingTicker),
            pytest.raises(_StopApp),
        ):
            await app_run(Path("ignored.toml"))

        return captured

    async def test_widget_without_coerce_warning_still_reaches_ticker(self):
        """The load-bearing case: a widget with NO coercions needed must
        still be added to the section's monitors. The drain loop
        previously engulfed the expansion block, so when
        `runtime_coerce` was empty (the common case), `widgets` stayed
        empty and Ticker received `monitors=[]`."""
        captured = await self._run_one_section({"type": "message", "text": "hi"})
        assert len(captured) == 1
        monitors = captured[0].get("monitors")
        assert monitors and len(monitors) == 1, (
            f"section's widget never reached Ticker.monitors — the "
            f"runtime coerce-drain loop likely re-engulfed the widget "
            f"expansion block (the Task 11 shape-bug). Got: {monitors!r}"
        )

    async def test_widget_with_coerce_warning_still_reaches_ticker(self):
        """Correctness case: the SAME assertion must hold when a coerce
        warning DOES fire. Pre-fix this case worked even with the bug
        (because the engulfed expansion ran inside the drain loop), so
        this test catches a different regression — a future drain loop
        that fails to expand."""
        captured = await self._run_one_section(
            {
                "type": "message",
                "text": "hi",
                "font": "Inter-Bold",
                "font_size": "25",
            }
        )
        assert len(captured) == 1
        monitors = captured[0].get("monitors")
        assert monitors and len(monitors) == 1, (
            f"section's widget never reached Ticker.monitors. Got: {monitors!r}"
        )


class TestAppRunBgColorHandoff:
    """End-to-end threading test for `last_bg_color` → next section's
    `outgoing_bg_color` in `app.run`. The unit-level run_transition
    tests pin the function's behavior; this one pins the call site
    in `app.py` actually wires `last_bg_color` into the right
    parameter when the for-loop crosses a section boundary.

    Drives `app.run` with mocked LED hardware + a patched
    `run_transition` that captures kwargs and raises `_StopApp` so
    the otherwise-infinite loop exits.
    """

    async def test_section_to_section_transition_passes_previous_bg_as_outgoing(
        self,
    ):
        """After section 1 (bg=red) runs, entering section 2 (bg=green)
        must call `run_transition(outgoing_bg_color=red,
        incoming_bg_color=green)`. Catches a regression where
        `last_bg_color = section.bg_color` is dropped or moved
        before the `run_transition` call site uses it."""
        import sys

        # Import the module first to ensure it's in sys.modules
        import led_ticker.app.run  # noqa: F401
        from led_ticker.app import run as app_run
        from led_ticker.config import (
            AppConfig,
            DisplayConfig,
            SectionConfig,
            TransitionConfig,
        )

        run_module = sys.modules["led_ticker.app.run"]

        section_one_bg = (255, 0, 0)
        section_two_bg = (0, 255, 0)

        cfg = AppConfig(
            display=DisplayConfig(rows=16, cols=32, chain_length=5),
            sections=[
                SectionConfig(
                    mode="slideshow",
                    widgets=[{"type": "message", "text": "A"}],
                    bg_color=section_one_bg,
                ),
                SectionConfig(
                    mode="slideshow",
                    widgets=[{"type": "message", "text": "B"}],
                    bg_color=section_two_bg,
                ),
            ],
            # Non-cut between_sections so `_build_trans_obj` returns
            # a real Transition instance (cut returns None and skips
            # the run_transition call entirely).
            between_sections=TransitionConfig(type="dissolve"),
        )

        captured_calls: list[dict] = []

        async def fake_run_transition(*args, **kwargs):
            captured_calls.append(kwargs)
            # Raise on the first run_transition (it's the inter-section
            # entry on section 2 — section 1 skips because last_widget
            # is None on the first iteration). Breaks out of the
            # `while True` loop in `app.run`.
            raise _StopApp("captured the inter-section transition")

        class _FakeTicker:
            """Stand-in for `Ticker` that just records construction
            and is a no-op on run_slideshow. Section 1 runs through
            successfully; section 2's entry transition fires our
            `fake_run_transition` BEFORE Ticker is constructed, so
            this is only exercised by section 1."""

            instances: list = []

            def __init__(self, *args, **kwargs):
                type(self).instances.append(self)
                self.last_scroll_pos = 0
                self._enqueue_task = None

            async def run_slideshow(self, **kw):
                pass

            async def run_ticker(self, **kw):
                pass

            async def run_one_at_a_time(self, **kw):
                pass

        with (
            mock.patch.object(run_module, "load_config", return_value=cfg),
            mock.patch.object(
                run_module,
                "build_frame_from_config",
                return_value=mock.Mock(
                    **{"get_clean_canvas.return_value": mock.Mock(height=16, width=160)}
                ),
            ),
            mock.patch.object(run_module, "_configure_user_font_dir"),
            mock.patch.object(run_module, "Ticker", _FakeTicker),
            mock.patch.object(
                run_module, "run_transition", side_effect=fake_run_transition
            ),
            pytest.raises(_StopApp),
        ):
            await app_run(Path("ignored.toml"))

        assert len(captured_calls) == 1, (
            f"expected exactly one inter-section run_transition call "
            f"(section 2's entry); got {len(captured_calls)}"
        )
        kw = captured_calls[0]
        assert kw.get("outgoing_bg_color") == section_one_bg, (
            f"section 2's entry transition should receive section 1's "
            f"bg as outgoing_bg_color={section_one_bg!r}; "
            f"got {kw.get('outgoing_bg_color')!r}. last_bg_color "
            f"plumbing in app.py likely regressed."
        )
        assert kw.get("incoming_bg_color") == section_two_bg, (
            f"section 2's entry transition should receive its own bg "
            f"as incoming_bg_color={section_two_bg!r}; "
            f"got {kw.get('incoming_bg_color')!r}."
        )


def test_resolve_title_delay_inherits_when_none():
    """When section.start_hold is None, fall through to config.title_delay."""
    from led_ticker.app import _resolve_title_delay

    assert _resolve_title_delay(None, 5) == 5.0


def test_resolve_title_delay_zero_overrides():
    """0.0 explicitly set must NOT fall through to the global default.
    This is the load-bearing case for the whole feature.
    """
    from led_ticker.app import _resolve_title_delay

    assert _resolve_title_delay(0.0, 5) == 0.0


def test_resolve_title_delay_positive_overrides():
    """Positive section.start_hold overrides the global default."""
    from led_ticker.app import _resolve_title_delay

    assert _resolve_title_delay(1.5, 5) == 1.5


def test_resolve_buffer_msg_returns_none_when_all_fields_unset():
    """Unset everything → None → Ticker falls back to DEFAULT_BUFFER_MSG."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig

    section = SectionConfig(mode="ticker")
    assert _resolve_buffer_msg(section) is None


def test_resolve_buffer_msg_with_separator_text_only():
    """separator='*' → TickerMessage with message='*', default font/color."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig
    from led_ticker.widgets.message import TickerMessage

    section = SectionConfig(mode="ticker", separator="*")
    msg = _resolve_buffer_msg(section)
    assert isinstance(msg, TickerMessage)
    assert msg.text == "*"


def test_resolve_buffer_msg_empty_string_maps_to_two_spaces():
    """Load-bearing case for the 'no glyph but breathing room' semantic."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig

    section = SectionConfig(mode="ticker", separator="")
    msg = _resolve_buffer_msg(section)
    assert msg is not None
    assert msg.text == "  "


def test_resolve_buffer_msg_with_custom_font_inherits_default_text():
    """separator_font alone (no separator) → default '•' in custom font."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig

    section = SectionConfig(mode="ticker", separator_font="5x8")
    msg = _resolve_buffer_msg(section)
    assert msg is not None
    assert msg.text == "•"
    # TickerMessage wants a resolved Font, not a name string. The
    # previous implementation passed the raw name through as `font=`,
    # which attrs silently accepted but would render as a string at
    # draw time.
    assert not isinstance(msg.font, str), (
        f"font must be resolved to a Font object, not the raw name {msg.font!r}"
    )


def test_resolve_buffer_msg_with_hires_font_resolves_via_resolve_font():
    """Regression: hires separator_font + separator_font_size used to crash
    because TickerMessage has no `font_size` kwarg. _resolve_buffer_msg
    must call resolve_font(name, size) and pass a Font object.
    """
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig
    from led_ticker.fonts.hires_loader import HiresFont

    section = SectionConfig(
        mode="ticker",
        separator=" * ",
        separator_font="Inter-Bold",
        separator_font_size=24,
    )
    msg = _resolve_buffer_msg(section)
    assert msg is not None
    assert msg.text == " * "
    assert isinstance(msg.font, HiresFont), (
        f"expected HiresFont, got {type(msg.font).__name__}"
    )


def test_resolve_buffer_msg_with_constant_color():
    """separator_color = [r, g, b] → ColorProvider wraps the constant."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig

    section = SectionConfig(
        mode="ticker", separator="*", separator_color=[225, 48, 108]
    )
    msg = _resolve_buffer_msg(section)
    assert msg is not None
    # TickerMessage stores font_color as a ColorProvider. Assert the
    # provider returns the expected color when called. Exact attribute
    # path depends on TickerMessage internals — adapt if needed; the
    # invariant is that the requested RGB lands in the message somehow.
    color = msg.font_color.color_for(frame=0, char_index=0, total_chars=1)
    assert (color.red, color.green, color.blue) == (225, 48, 108)


def test_resolve_buffer_msg_color_only_returns_circle_buffer_msg():
    """separator_color set alone (no separator, no font) → _CircleBufferMsg
    routes through the hi-res circle path on bigsign."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig
    from led_ticker.ticker import _CircleBufferMsg

    section = SectionConfig(mode="ticker", separator_color=[225, 48, 108])
    msg = _resolve_buffer_msg(section)

    assert isinstance(msg, _CircleBufferMsg), (
        f"expected _CircleBufferMsg, got {type(msg).__name__}"
    )
    assert msg.text == " • "
    # Color provider returns the user's RGB.
    color = msg.font_color.color_for(0, 0, 1)
    assert (color.red, color.green, color.blue) == (225, 48, 108)


class TestBuildWidgetCoerceEnum:
    @pytest.mark.asyncio
    async def test_coerces_image_align_case(self, tmp_path):
        """image_align = 'Left' should coerce to 'left' and warn."""
        from PIL import Image

        from led_ticker._coerce import CoercionWarning
        from led_ticker.app import _build_widget

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (1, 1), (255, 0, 0)).save(img_path)

        warnings: list[CoercionWarning] = []
        session = mock.Mock()
        widget_cfg = {
            "type": "image",
            "path": "tiny.png",
            "image_align": "Left",
            "fit": "Letterbox",
        }
        widget = await _build_widget(
            widget_cfg,
            session,
            config_dir=tmp_path,
            coercion_collector=warnings,
        )
        assert widget is not None
        fields_warned = {w.field for w in warnings}
        assert "widget.image_align" in fields_warned
        assert "widget.fit" in fields_warned

    @pytest.mark.asyncio
    async def test_unknown_image_align_rejected(self, tmp_path):
        """'Middle' (after lowercase) still isn't a valid image_align."""
        from PIL import Image

        from led_ticker.app import _build_widget

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (1, 1), (255, 0, 0)).save(img_path)

        session = mock.Mock()
        widget_cfg = {
            "type": "image",
            "path": "tiny.png",
            "image_align": "Middle",
        }
        with pytest.raises(ValueError, match="not a valid choice"):
            await _build_widget(
                widget_cfg,
                session,
                config_dir=tmp_path,
            )

    @pytest.mark.asyncio
    async def test_coerces_text_align_case_on_image(self, tmp_path):
        """text_align on an image widget: 'Left' must coerce to 'left'
        and the widget must accept the canonical value."""
        from PIL import Image

        from led_ticker._coerce import CoercionWarning
        from led_ticker.app import _build_widget

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (1, 1), (255, 0, 0)).save(img_path)

        warnings: list[CoercionWarning] = []
        session = mock.Mock()
        widget_cfg = {
            "type": "image",
            "path": "tiny.png",
            "text": "hi",
            "text_align": "Left",
        }
        widget = await _build_widget(
            widget_cfg,
            session,
            config_dir=tmp_path,
            coercion_collector=warnings,
        )
        assert widget is not None
        assert widget.text_align == "left"
        assert any(w.field == "widget.text_align" for w in warnings)

    @pytest.mark.asyncio
    async def test_text_align_auto_still_accepted(self, tmp_path):
        """Regression: text_align='auto' is the documented default
        sentinel for image widgets — it resolves at draw time to a
        side opposite the image. The coerce frozenset MUST include
        'auto' even though VALID_TEXT_ALIGNS (the post-resolution
        strict set in _image_base) doesn't, or any explicit
        text_align='auto' / 'Auto' breaks at config load."""
        from PIL import Image

        from led_ticker.app import _build_widget

        img_path = tmp_path / "tiny.png"
        Image.new("RGB", (1, 1), (255, 0, 0)).save(img_path)

        for value in ("auto", "Auto", "AUTO"):
            session = mock.Mock()
            widget_cfg = {
                "type": "image",
                "path": "tiny.png",
                "text": "hi",
                "text_align": value,
            }
            widget = await _build_widget(
                widget_cfg,
                session,
                config_dir=tmp_path,
            )
            # Widget resolves 'auto' to a concrete side at construction;
            # the only contract is the build doesn't raise.
            assert widget is not None
            assert widget.text_align in {"left", "right", "scroll_over"}


class TestValidateRgb:
    """_validate_rgb is a module-level helper usable from all coerce paths."""

    def test_rejects_bool_components(self):
        from led_ticker.app import _validate_rgb

        with pytest.raises(ValueError, match="components must be ints"):
            _validate_rgb([True, False, 0], "font_color list")

    def test_rejects_out_of_range(self):
        from led_ticker.app import _validate_rgb

        with pytest.raises(ValueError, match="RGB values must be 0-255"):
            _validate_rgb([300, 0, 0], "font_color list")

    def test_rejects_wrong_length(self):
        from led_ticker.app import _validate_rgb

        with pytest.raises(ValueError, match=r"must be \[r,g,b\]"):
            _validate_rgb([1, 2], "font_color list")

    def test_accepts_valid_rgb(self):
        from led_ticker.app import _validate_rgb

        assert _validate_rgb([255, 128, 0], "font_color list") == (255, 128, 0)

    def test_context_appears_in_message(self):
        from led_ticker.app import _validate_rgb

        with pytest.raises(ValueError, match="bg_color"):
            _validate_rgb([True, 0, 0], "bg_color")


class TestCoerceColorProviderValidation:
    """_coerce_color_provider validates rgb lists via _validate_rgb."""

    def test_rejects_bool_component(self):
        from led_ticker.app import _coerce_color_provider

        with pytest.raises(ValueError, match="components must be ints"):
            _coerce_color_provider([True, 0, 0])

    def test_rejects_out_of_range(self):
        from led_ticker.app import _coerce_color_provider

        with pytest.raises(ValueError, match="RGB values must be 0-255"):
            _coerce_color_provider([256, 0, 0])


class TestCoerceWidgetColorsValidation:
    """_coerce_widget_colors validates raw color keys via _validate_rgb."""

    def test_bg_color_rejects_bool_component(self):
        from led_ticker.app import _coerce_widget_colors

        cfg = {"bg_color": [True, 0, 0]}
        with pytest.raises(ValueError, match="components must be ints"):
            _coerce_widget_colors(cfg)

    def test_bg_color_rejects_out_of_range(self):
        from led_ticker.app import _coerce_widget_colors

        cfg = {"bg_color": [256, 0, 0]}
        with pytest.raises(ValueError, match="RGB values must be 0-255"):
            _coerce_widget_colors(cfg)


class TestProviderFromStyleRgbValidation:
    """_provider_from_style validates rgb endpoints for gradient and color_cycle."""

    def test_gradient_from_rejects_bool(self):
        from led_ticker.app import _provider_from_style

        with pytest.raises(ValueError, match="components must be ints"):
            _provider_from_style(
                "gradient", {"from": [True, 0, 0], "to": [255, 255, 0]}
            )

    def test_gradient_to_rejects_out_of_range(self):
        from led_ticker.app import _provider_from_style

        with pytest.raises(ValueError, match="RGB values must be 0-255"):
            _provider_from_style("gradient", {"from": [255, 0, 0], "to": [0, 256, 0]})

    def test_color_cycle_from_rejects_bool(self):
        from led_ticker.app import _provider_from_style

        with pytest.raises(ValueError, match="components must be ints"):
            _provider_from_style(
                "color_cycle", {"from": [True, 0, 0], "to": [0, 255, 0]}
            )


class TestProviderFromStyleErrorMessages:
    """Unknown-key error messages show TOML-facing key names, not internal ones."""

    def test_gradient_unknown_key_shows_user_facing_allowed(self):
        from led_ticker.app import _provider_from_style

        with pytest.raises(ValueError) as exc_info:
            _provider_from_style(
                "gradient",
                {"from": [255, 0, 0], "to": [0, 255, 0], "wobble": 3},
            )
        msg = str(exc_info.value)
        assert "from_color" not in msg, f"internal name leaked into error: {msg}"
        assert "to_color" not in msg, f"internal name leaked into error: {msg}"
        assert "from" in msg

    def test_color_cycle_range_unknown_key_shows_user_facing_allowed(self):
        from led_ticker.app import _provider_from_style

        with pytest.raises(ValueError) as exc_info:
            _provider_from_style(
                "color_cycle",
                {"from": [255, 0, 0], "to": [0, 255, 0], "wobble": 3},
            )
        msg = str(exc_info.value)
        assert "from_hue" not in msg, f"internal name leaked into error: {msg}"
        assert "to_hue" not in msg, f"internal name leaked into error: {msg}"
        assert "from" in msg
        assert "to" in msg


class TestUnknownKwargAllowlist:
    """validate_widget_cfg raises a clear ValueError (not TypeError) for unknown
    widget fields, surfacing at validate-time instead of startup."""

    @pytest.mark.asyncio
    async def test_typo_field_raises_value_error(self):
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "message", "text": "hi", "text_color": [255, 0, 0]}
        with pytest.raises(ValueError, match="got unknown field"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_did_you_mean_suggestion_included(self):
        """font_clor → suggests font_color via difflib."""
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "message", "text": "hi", "font_clor": [255, 0, 0]}
        with pytest.raises(ValueError, match="did you mean 'font_color'"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_no_suggestion_for_random_garbage(self):
        """Completely unlike any field → error still raised, no suggestion."""
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "message", "text": "hi", "xyz_not_a_field": 1}
        with pytest.raises(ValueError, match="got unknown field"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_multiple_unknown_fields_all_reported(self):
        """Both bad keys appear in the error message."""
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {
            "type": "message",
            "text": "hi",
            "text_color": [255, 0, 0],
            "alignement": "left",
        }
        with pytest.raises(ValueError, match="got unknown fields"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_valid_fields_do_not_raise(self):
        """Correctness check: a well-formed message config passes the allowlist."""
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {
            "type": "message",
            "text": "hello",
            "font_color": [255, 255, 255],
            "center": True,
            "padding": 4,
        }
        result = await validate_widget_cfg(cfg, session=None)
        assert result is None  # validate_widget_cfg returns None on success

    @pytest.mark.asyncio
    async def test_fires_at_runtime_not_only_validate(self):
        """The check runs even during full _build_widget (before cls(**widget_cfg))."""
        from led_ticker.app import _build_widget

        cfg = {"type": "message", "text": "hi", "text_color": [255, 0, 0]}
        with pytest.raises(ValueError, match="got unknown field"):
            await _build_widget(cfg, session=None)  # type: ignore[arg-type]


class TestListWidgetFields:
    """_list_widget_fields grouped output and FIELD_HINTS rendering."""

    def test_message_has_required_section(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "Required:" in result

    def test_message_has_optional_section(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "Optional:" in result

    def test_message_no_two_row_section(self):
        """message widget has no two-row overlay fields."""
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "Two-row" not in result

    def test_gif_has_two_row_section(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("gif")
        assert "Two-row overlay" in result

    def test_message_hides_gif_only_dispatch_fields(self):
        """text_wrap (gif/image only) must not appear in message output."""
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "text_wrap" not in result

    def test_gif_shows_text_wrap(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("gif")
        assert "text_wrap" in result

    def test_gif_shows_valid_values_for_text_align(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("gif")
        assert '"auto" | "scroll"' in result

    def test_gif_shows_valid_values_for_fit(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("gif")
        assert '"pillarbox" | "letterbox"' in result

    def test_font_default_is_human_readable(self):
        """Font object repr must not appear; FIELD_HINTS override shows plain text."""
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "panel default font" in result
        assert "object at 0x" not in result

    def test_font_color_shows_provider_options(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert '"rainbow"' in result

    def test_font_not_duplicated_for_message(self):
        """font is an attrs field on TickerMessage; must not also appear in Shared."""
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        # font appears in Optional but NOT in Shared fields section
        assert "Optional:" in result
        sections = result.split("\n\n")
        shared_section = next(
            (s for s in sections if s.startswith("Shared fields")), ""
        )
        # shared section must not have a bare "font" line (font_size/font_threshold ok)
        shared_lines = [
            ln for ln in shared_section.splitlines() if ln.startswith("  font ")
        ]
        assert shared_lines == [], f"font appeared in Shared section: {shared_lines}"

    def test_animation_any_none_not_shown(self):
        """animation: Any | None must not appear; FIELD_HINTS gives readable type."""
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "Any | None" not in result

    def test_unknown_type_raises_value_error(self):
        from led_ticker.app import _list_widget_fields

        with pytest.raises(ValueError, match="Unknown widget type"):
            _list_widget_fields("nonexistent_widget")

    def test_unknown_type_includes_did_you_mean(self):
        from led_ticker.app import _list_widget_fields

        with pytest.raises(ValueError, match="Did you mean"):
            _list_widget_fields("mesage")

    def test_two_row_fields_included_for_two_row_type(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("two_row")
        assert "top_text" in result
        assert "bottom_text" in result

    def test_play_count_description_mentions_hold_time(self):
        from led_ticker.app import _list_widget_fields

        output = _list_widget_fields("gif")
        assert "play_count" in output
        assert "hold_time" in output.lower() or "hold" in output.lower()

    def test_text_loops_description_clarifies_zero_means_one(self):
        from led_ticker.app import _list_widget_fields

        output = _list_widget_fields("gif")
        assert "text_loops" in output
        # The description must not leave "0" ambiguous
        assert (
            "NOT zero" in output
            or "one loop" in output.lower()
            or "= one" in output.lower()
        )

    def test_hold_time_description_appears_on_image(self):
        from led_ticker.app import _list_widget_fields

        output = _list_widget_fields("image")
        assert "hold_time" in output
        assert "still" in output.lower() or "minimum" in output.lower()


class TestListWidgetFieldsDataWidgets:
    """FIELD_HINTS coverage for data widget fields."""

    def test_countdown_shows_countdown_date_description(self):
        from led_ticker.app import _list_widget_fields

        output = _list_widget_fields("countdown")
        assert "countdown_date" in output
        assert "count down to" in output.lower()


class TestListSectionFields:
    def test_returns_string(self):
        from led_ticker.app.factories import _list_section_fields

        output = _list_section_fields()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_shows_mode_as_required(self):
        from led_ticker.app.factories import _list_section_fields

        output = _list_section_fields()
        assert "mode" in output
        assert "required" in output

    def test_shows_loop_count_with_infinite_note(self):
        from led_ticker.app.factories import _list_section_fields

        output = _list_section_fields()
        assert "loop_count" in output
        assert "infinite" in output or "0 = " in output

    def test_shows_hold_time_with_seconds(self):
        from led_ticker.app.factories import _list_section_fields

        output = _list_section_fields()
        assert "hold_time" in output
        assert "3.0" in output or "seconds" in output

    def test_shows_scroll_step_ms(self):
        from led_ticker.app.factories import _list_section_fields

        output = _list_section_fields()
        assert "scroll_step_ms" in output
        assert "50" in output or "ms" in output

    def test_shows_content_height_with_rule_note(self):
        from led_ticker.app.factories import _list_section_fields

        output = _list_section_fields()
        assert "content_height" in output
        assert "rule 1" in output or "scale" in output

    def test_shows_transition_fields(self):
        from led_ticker.app.factories import _list_section_fields

        output = _list_section_fields()
        assert "entry_transition" in output
        assert "widget_transition" in output

    def test_cli_list_fields_section(self):
        """led-ticker validate --list-fields section prints section fields."""
        import os
        import subprocess
        import sys
        from pathlib import Path

        repo_root = str(Path(__file__).parent.parent)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "led_ticker.app.cli",
                "validate",
                "--list-fields",
                "section",
            ],
            env={
                **os.environ,
                "PYTHONPATH": f"{repo_root}/src:{repo_root}/tests/stubs",
            },
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert result.returncode == 0
        assert "hold_time" in result.stdout
        assert "loop_count" in result.stdout
        assert "scroll_step_ms" in result.stdout


class TestSingleRowColorGuard:
    """top_color / bottom_color are two-row-only on gif/image widgets.
    On a single-row widget they're silently ignored; the guard makes it loud.
    """

    @pytest.mark.asyncio
    async def test_top_color_on_single_row_gif_raises(self):
        """top_color on a gif without bottom_text must raise — not silently vanish."""
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {
            "type": "gif",
            "path": "/nonexistent/tiny.gif",
            "fit": "stretch",
            "top_color": [255, 220, 70],
        }
        with pytest.raises(ValueError, match="two-row mode"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_bottom_color_on_single_row_image_raises(self):
        """bottom_color on single-row image must raise — not silently ignored."""
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {
            "type": "image",
            "path": "/nonexistent/tiny.png",
            "fit": "stretch",
            "bottom_color": [255, 150, 190],
        }
        with pytest.raises(ValueError, match="two-row mode"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_top_color_on_two_row_gif_does_not_raise(self):
        """top_color is valid when bottom_text is set (two-row mode)."""
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {
            "type": "gif",
            "path": "/nonexistent/tiny.gif",
            "fit": "stretch",
            "top_text": "@firebird",
            "bottom_text": "Follow us!",
            "top_color": [255, 220, 70],
            "bottom_color": [255, 150, 190],
        }
        result = await validate_widget_cfg(cfg, session=None)
        assert result is None  # validate_widget_cfg returns None on success


class TestPerSectionQueue:
    """A fresh asyncio.Queue must be created per section visit, not reused
    across sections. Sharing queues allows a fast section's leftover items
    to be consumed by the next section's Ticker. (S3)
    """

    @pytest.mark.asyncio
    async def test_fresh_queue_per_section(self):
        """Verify that each section gets its own fresh asyncio.Queue."""
        import sys

        import led_ticker.app.run  # noqa: F401
        from led_ticker.app import run as app_run
        from led_ticker.config import (
            AppConfig,
            DisplayConfig,
            SectionConfig,
            TransitionConfig,
        )

        run_module = sys.modules["led_ticker.app.run"]

        # Create a config with 2 sections to exercise the per-section loop
        cfg = AppConfig(
            display=DisplayConfig(rows=16, cols=32, chain_length=5),
            sections=[
                SectionConfig(
                    mode="slideshow",
                    widgets=[{"type": "message", "text": "Section 1"}],
                ),
                SectionConfig(
                    mode="slideshow",
                    widgets=[{"type": "message", "text": "Section 2"}],
                ),
            ],
            between_sections=TransitionConfig(type="cut"),
        )

        received_queues: list = []

        OriginalTicker = __import__("led_ticker.ticker", fromlist=["Ticker"]).Ticker

        class _SpyTicker(OriginalTicker):
            def __init__(self, *args, **kwargs):
                received_queues.append(kwargs.get("notif_queue"))
                self.last_scroll_pos = 0
                self._enqueue_task = None
                # Only raise after we've seen both sections
                if len(received_queues) >= 2:
                    raise _StopApp("captured both sections")

            async def run_slideshow(self, **kw):
                pass

        with (
            mock.patch.object(run_module, "load_config", return_value=cfg),
            mock.patch.object(
                run_module,
                "build_frame_from_config",
                return_value=mock.Mock(
                    **{"get_clean_canvas.return_value": mock.Mock(height=16, width=160)}
                ),
            ),
            mock.patch.object(run_module, "_configure_user_font_dir"),
            mock.patch.object(run_module, "Ticker", _SpyTicker),
            pytest.raises(_StopApp),
        ):
            await app_run(Path("ignored.toml"))

        # We should have captured at least 2 Ticker instantiations (one per section)
        assert len(received_queues) >= 2, (
            f"Expected at least 2 Ticker instantiations (one per section), "
            f"got {len(received_queues)}"
        )

        # All queues should be distinct objects (fresh per section)
        queue_ids = [id(q) for q in received_queues]
        assert len(set(queue_ids)) == len(queue_ids), (
            f"Expected all queues to be distinct objects, but some were reused. "
            f"Queue IDs: {queue_ids}"
        )


class TestLoadConfigOffEventLoop:
    """load_config uses blocking file I/O; must run via asyncio.to_thread. (S21)"""

    async def test_load_config_called_via_to_thread(self, monkeypatch):
        """Verify that load_config is wrapped in asyncio.to_thread to avoid
        blocking the event loop during config file I/O operations."""
        import sys
        from pathlib import Path

        # Import the module to ensure it's in sys.modules
        import led_ticker.app.run  # noqa: F401
        from led_ticker.app import run as app_run
        from led_ticker.config import (
            AppConfig,
            DisplayConfig,
            SectionConfig,
            TransitionConfig,
        )

        run_module = sys.modules["led_ticker.app.run"]

        # Create a minimal config for testing
        cfg = AppConfig(
            display=DisplayConfig(rows=16, cols=32, chain_length=5),
            sections=[
                SectionConfig(
                    mode="slideshow",
                    widgets=[{"type": "message", "text": "test"}],
                ),
            ],
            between_sections=TransitionConfig(type="cut"),
        )

        # Track calls to asyncio.to_thread
        to_thread_calls: list = []

        async def _fake_to_thread(func, *args, **kwargs):
            # Store function name if available, otherwise use the func object
            func_name = getattr(func, "__name__", None)
            to_thread_calls.append((func_name, args))
            return func(*args, **kwargs)

        # Patch asyncio.to_thread
        import asyncio

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        # Also patch the other dependencies to stop early
        class _CapturingTicker:
            def __init__(self, *args, **kwargs):
                raise _StopApp("captured")

            async def run_slideshow(self, **kw):
                pass

        with (
            mock.patch.object(run_module, "load_config", return_value=cfg),
            mock.patch.object(
                run_module,
                "build_frame_from_config",
                return_value=mock.Mock(
                    **{"get_clean_canvas.return_value": mock.Mock(height=16, width=160)}
                ),
            ),
            mock.patch.object(run_module, "_configure_user_font_dir"),
            mock.patch.object(run_module, "Ticker", _CapturingTicker),
            pytest.raises(_StopApp),
        ):
            await app_run(Path("ignored.toml"))

        # Verify that asyncio.to_thread was called with load_config.
        # The mock object won't have __name__, so check that to_thread was
        # called with the mocked load_config and the config_path argument.
        assert len(to_thread_calls) > 0, (
            "asyncio.to_thread must be called to wrap load_config"
        )
        # Verify the call was with load_config (mocked) and config_path
        _, args = to_thread_calls[0]
        assert len(args) == 1
        assert str(args[0]) == "ignored.toml", (
            f"Expected load_config to be called with config_path, got: {args}"
        )


class TestResolveAssetPaths:
    def test_relative_path_resolved_to_absolute(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths

        cfg = {"path": "gifs/rainbow.gif"}
        config_dir = tmp_path / "config"
        _resolve_asset_paths(cfg, "gif", config_dir)
        assert cfg["path"] == str((config_dir / "gifs/rainbow.gif").resolve())

    def test_absolute_path_unchanged(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths

        absolute = "/home/pi/gifs/rainbow.gif"
        cfg = {"path": absolute}
        _resolve_asset_paths(cfg, "gif", tmp_path)
        assert cfg["path"] == absolute

    def test_non_gif_type_unchanged(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths

        cfg = {"path": "something.gif"}
        _resolve_asset_paths(cfg, "message", tmp_path)
        assert cfg["path"] == "something.gif"

    def test_no_path_key_is_noop(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths

        cfg = {"text": "hello"}
        _resolve_asset_paths(cfg, "gif", tmp_path)
        assert "path" not in cfg

    def test_none_config_dir_leaves_path_unchanged(self):
        from led_ticker.app.factories import _resolve_asset_paths

        cfg = {"path": "gifs/rainbow.gif"}
        _resolve_asset_paths(cfg, "gif", None)
        assert cfg["path"] == "gifs/rainbow.gif"

    def test_image_type_also_resolved(self, tmp_path):
        from led_ticker.app.factories import _resolve_asset_paths

        cfg = {"path": "images/bg.png"}
        config_dir = tmp_path / "config"
        _resolve_asset_paths(cfg, "image", config_dir)
        assert cfg["path"] == str((config_dir / "images/bg.png").resolve())


class TestResolveFonts:
    def test_no_font_key_is_noop(self):
        from led_ticker.app.factories import _resolve_fonts

        cfg = {"text": "hello"}
        _resolve_fonts(cfg, None, None)
        assert "font" not in cfg

    def test_bdf_font_name_resolved_to_object(self):
        from led_ticker.app.factories import _resolve_fonts
        from led_ticker.fonts.hires_loader import HiresFont

        cfg = {"font": "5x8"}
        _resolve_fonts(cfg, None, None)
        # BDF aliases resolve to the rgbmatrix Font object, not a HiresFont
        assert not isinstance(cfg["font"], str)
        assert not isinstance(cfg["font"], HiresFont)

    def test_hires_font_without_font_size_raises(self):
        from led_ticker.app.factories import _resolve_fonts

        cfg = {"font": "Inter-Bold"}
        with pytest.raises(ValueError, match="requires font_size"):
            _resolve_fonts(cfg, None, None)

    def test_hires_font_with_font_size_resolved(self):
        from led_ticker.app.factories import _resolve_fonts
        from led_ticker.fonts.hires_loader import HiresFont

        cfg = {"font": "Inter-Bold", "font_size": 24}
        _resolve_fonts(cfg, None, None)
        assert isinstance(cfg["font"], HiresFont)

    def test_per_row_fonts_resolved(self):
        from led_ticker.app.factories import _resolve_fonts
        from led_ticker.fonts.hires_loader import HiresFont

        cfg = {"top_font": "5x8", "bottom_font": "6x12"}
        _resolve_fonts(cfg, None, None)
        # BDF aliases resolve to rgbmatrix Font objects, not strings or HiresFont
        assert not isinstance(cfg["top_font"], str)
        assert not isinstance(cfg["top_font"], HiresFont)
        assert not isinstance(cfg["bottom_font"], str)
        assert not isinstance(cfg["bottom_font"], HiresFont)

    def test_per_row_hires_without_size_raises(self):
        from led_ticker.app.factories import _resolve_fonts

        cfg = {"top_font": "Inter-Bold"}
        with pytest.raises(ValueError, match="requires top_font_size"):
            _resolve_fonts(cfg, None, None)

    def test_font_size_passed_through_when_cls_accepts_it(self):
        from led_ticker.app.factories import _resolve_fonts
        from led_ticker.widgets.gif import GifPlayer

        cfg = {"font": "5x8", "font_size": 8}
        _resolve_fonts(cfg, GifPlayer, None)
        assert cfg.get("font_size") == 8

    def test_font_size_dropped_when_cls_does_not_accept_it(self):
        from led_ticker.app.factories import _resolve_fonts
        from led_ticker.widgets.message import TickerMessage

        cfg = {"font": "5x8", "font_size": 8}
        _resolve_fonts(cfg, TickerMessage, None)
        assert "font_size" not in cfg

    def test_panel_height_warning_emitted_when_hires_font_too_tall(self, caplog):
        import logging

        from led_ticker.app.factories import _resolve_fonts

        cfg = {"font": "Inter-Bold", "font_size": 16}
        with caplog.at_level(logging.WARNING):
            _resolve_fonts(cfg, None, panel_h_for_warning=14)
        assert any("clip vertically" in r.message for r in caplog.records)

    def test_no_warning_when_hires_font_fits(self, caplog):
        import logging

        from led_ticker.app.factories import _resolve_fonts

        cfg = {"font": "Inter-Bold", "font_size": 10}
        with caplog.at_level(logging.WARNING):
            _resolve_fonts(cfg, None, panel_h_for_warning=14)
        assert not any("clip vertically" in r.message for r in caplog.records)


class TestValidateCfgFields:
    def test_unknown_field_raises_with_name(self):
        from led_ticker.app.factories import _validate_cfg_fields
        from led_ticker.widgets.message import TickerMessage

        cfg = {"text": "hello", "unknown_field": "value"}
        with pytest.raises(ValueError, match="unknown_field"):
            _validate_cfg_fields(cfg, TickerMessage, "message")

    def test_did_you_mean_hint_included(self):
        from led_ticker.app.factories import _validate_cfg_fields
        from led_ticker.widgets.message import TickerMessage

        # "txet" is close to "text" — difflib should suggest "text"
        cfg = {"txet": "hello"}
        with pytest.raises(ValueError, match="did you mean"):
            _validate_cfg_fields(cfg, TickerMessage, "message")

    def test_error_uses_registry_name_not_class_name(self):
        from led_ticker.app.factories import _validate_cfg_fields
        from led_ticker.widgets.message import TickerMessage

        cfg = {"unknown_field": "value"}
        with pytest.raises(ValueError, match="type='message'"):
            _validate_cfg_fields(cfg, TickerMessage, "message")

    def test_valid_fields_do_not_raise(self):
        from led_ticker.app.factories import _validate_cfg_fields
        from led_ticker.widgets.message import TickerMessage

        cfg = {"text": "hello"}
        _validate_cfg_fields(cfg, TickerMessage, "message")  # must not raise


class TestValidateWidgetCfg:
    async def test_validate_raises_on_unknown_field(self, tmp_path):
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "message", "text": "hello", "invalid_field": "value"}
        with pytest.raises(ValueError, match="invalid_field"):
            await validate_widget_cfg(cfg, session=None, config_dir=tmp_path)

    async def test_validate_raises_on_migration_error(self, tmp_path):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError

        cfg = {"type": "message", "text": "hello", "text_scale": 2}
        with pytest.raises(MigrationError):
            await validate_widget_cfg(cfg, session=None, config_dir=tmp_path)

    async def test_validate_does_not_instantiate(self, tmp_path, monkeypatch):
        import led_ticker.widgets.message as msg_module
        from led_ticker.app.factories import validate_widget_cfg

        constructed = []
        original_init = msg_module.TickerMessage.__init__

        def _spy_init(self, *args, **kwargs):
            constructed.append(1)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(msg_module.TickerMessage, "__init__", _spy_init)

        cfg = {"type": "message", "text": "hello"}
        await validate_widget_cfg(cfg, session=None, config_dir=tmp_path)
        assert not constructed

    def test_build_widget_has_no_validate_only_parameter(self):
        import inspect

        from led_ticker.app.factories import _build_widget

        params = inspect.signature(_build_widget).parameters
        assert "validate_only" not in params


@pytest.mark.parametrize(
    "cfg,expected_cls",
    [
        ({"type": "message", "text": "hello"}, "TickerMessage"),
        (
            {"type": "two_row", "top_text": "hi", "bottom_text": "there"},
            "TwoRowMessage",
        ),
    ],
)
class TestBuildWidgetRoundtrip:
    """validate_widget_cfg passes → _build_widget constructs without error."""

    async def test_validate_then_build(self, cfg, expected_cls, tmp_path):
        import copy

        import aiohttp

        from led_ticker.app.factories import _build_widget, validate_widget_cfg

        validation_cfg = copy.deepcopy(cfg)
        result = await validate_widget_cfg(
            validation_cfg, session=None, config_dir=tmp_path
        )
        assert result is None

        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(cfg, session=session, config_dir=tmp_path)
        assert type(widget).__name__ == expected_cls


class TestMessageFieldRename:
    """message field renamed to text on TickerMessage and TickerCountdown."""

    @pytest.mark.asyncio
    async def test_message_key_raises_migration_error(self):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError

        cfg = {"type": "message", "message": "hello"}
        with pytest.raises(MigrationError, match="text"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_text_key_works_on_ticker_message(self):
        import aiohttp

        from led_ticker.app.factories import _build_widget

        cfg = {"type": "message", "text": "hello"}
        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(cfg.copy(), session=session)
        assert widget.text == "hello"

    @pytest.mark.asyncio
    async def test_message_key_raises_on_countdown(self):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError

        cfg = {
            "type": "countdown",
            "message": "Days Until Summer",
            "target_date": "2026-06-21",
        }
        with pytest.raises(MigrationError, match="text"):
            await validate_widget_cfg(cfg, session=None)

    def test_list_fields_message_type_shows_text_not_message(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("message")
        assert "  text " in result
        assert not any(
            line.strip().startswith("message") for line in result.splitlines()
        )


class TestTitleColorRename:
    """color field renamed to font_color on section titles."""

    @pytest.mark.asyncio
    async def test_title_color_raises_migration_error(self):
        """title color = ... raises MigrationError at build time."""
        from led_ticker.validate import MigrationError

        with pytest.raises(MigrationError, match='renamed from "color"'):
            await _build_title(
                {"type": "message", "text": "Hello", "color": "random"},
                session=None,
            )

    @pytest.mark.asyncio
    async def test_title_font_color_works(self):
        """title font_color = ... builds successfully."""
        widget = await _build_title(
            {"type": "message", "text": "Hello", "font_color": [255, 0, 0]},
            session=None,
        )
        assert widget is not None

    @pytest.mark.asyncio
    async def test_title_no_color_works(self):
        """title with no color field builds successfully."""
        widget = await _build_title({"type": "message", "text": "Hello"}, session=None)
        assert widget is not None


class TestGifLoopsRename:
    """gif_loops field renamed to play_count on GifPlayer (via loops)."""

    @pytest.mark.asyncio
    async def test_gif_loops_raises_migration_error(self):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError

        cfg = {"type": "gif", "path": "x.gif", "gif_loops": 2}
        with pytest.raises(MigrationError, match="play_count"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_loops_raises_migration_error(self):
        from led_ticker.app.factories import validate_widget_cfg
        from led_ticker.validate import MigrationError

        cfg = {"type": "gif", "path": "x.gif", "loops": 2}
        with pytest.raises(MigrationError, match="play_count"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_play_count_field_works_on_gif(self):
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "gif", "path": "x.gif", "play_count": 2}
        await validate_widget_cfg(cfg.copy(), session=None)  # must not raise

    def test_list_fields_gif_shows_play_count_not_loops(self):
        from led_ticker.app import _list_widget_fields

        result = _list_widget_fields("gif")
        assert "  play_count " in result or "play_count\n" in result
        assert "gif_loops" not in result
        assert "  loops " not in result


def _make_frame(width=64, height=32):
    """Helper: build a setup LedFrame backed by HeadlessBackend."""
    from led_ticker.backends.headless import HeadlessBackend
    from led_ticker.frame import LedFrame

    f = LedFrame(backend=HeadlessBackend(width, height))
    f.setup()
    return f


class TestStartBusyLight:
    async def test_file_source_registers_hook_and_reads_file(self, tmp_path):
        from led_ticker.app.run import _start_busy_light
        from led_ticker.config import BusyLightConfig

        f = tmp_path / ".busy"
        f.write_text("")
        cfg = BusyLightConfig(
            enabled=True, source="file", file_path=str(f), poll_interval=999
        )
        frame = _make_frame()
        busy = await _start_busy_light(cfg, frame)
        assert busy.paint in frame.overlay_hooks
        assert busy.is_busy is True  # initial update() read the existing file

    async def test_http_source_registers_hook_and_threads_ttl(self):
        import asyncio

        from led_ticker.app.run import _start_busy_light
        from led_ticker.config import BusyLightConfig

        before = asyncio.all_tasks()
        cfg = BusyLightConfig(
            enabled=True,
            source="http",
            http_host="127.0.0.1",
            http_port=0,
            ttl_seconds=120.0,
        )
        frame = _make_frame()
        busy = await _start_busy_light(cfg, frame)
        new_tasks = asyncio.all_tasks() - before
        try:
            assert busy.paint in frame.overlay_hooks
            assert busy.ttl_seconds == 120.0
            assert busy.is_busy is False  # http source starts not-busy
            names = {t.get_coro().__qualname__ for t in new_tasks}
            # http branch must have started the supervised listener...
            assert any("_serve_busy_supervised" in n for n in names)
            # ...and the ticker.
            assert any("_ttl_ticker" in n for n in names)
        finally:
            for t in new_tasks:
                t.cancel()
            await asyncio.gather(*new_tasks, return_exceptions=True)

    async def test_http_source_runs_ticker_even_without_config_ttl(self):
        # Per-request ?ttl= must be enforceable even when the config sets no
        # default, so the http source always starts the ticker.
        import asyncio

        from led_ticker.app.run import _start_busy_light
        from led_ticker.config import BusyLightConfig

        before = asyncio.all_tasks()
        cfg = BusyLightConfig(
            enabled=True,
            source="http",
            http_host="127.0.0.1",
            http_port=0,
            ttl_seconds=0.0,
        )
        frame = _make_frame()
        await _start_busy_light(cfg, frame)
        new_tasks = asyncio.all_tasks() - before
        try:
            names = {t.get_coro().__qualname__ for t in new_tasks}
            assert any("_ttl_ticker" in n for n in names)
        finally:
            for t in new_tasks:
                t.cancel()
            await asyncio.gather(*new_tasks, return_exceptions=True)

    async def test_http_server_task_survives_gc(self):
        # Regression: the HTTP server task suspends on `asyncio.Event().wait()`,
        # which forms a reference cycle anchored to no GC root. If the task
        # isn't strongly referenced, the cyclic collector reclaims it mid-flight
        # ("Task was destroyed but it is pending!" on Python 3.14). _start_busy_light
        # must keep a strong reference so a gc.collect() can't reap it.
        import asyncio
        import gc

        from led_ticker.app.run import _start_busy_light
        from led_ticker.config import BusyLightConfig

        cfg = BusyLightConfig(
            enabled=True, source="http", http_host="127.0.0.1", http_port=0
        )
        frame = _make_frame()
        await _start_busy_light(cfg, frame)
        # Let serve_busy() finish binding so the task reaches Event().wait()
        # (the rootless suspension point).
        await asyncio.sleep(0.05)

        gc.collect()  # would reap the server task if it weren't referenced

        live = {
            t.get_coro().__qualname__
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task()
        }
        assert any("_serve_busy_supervised" in n for n in live), (
            "busy-light HTTP server task was garbage-collected "
            "(not strongly referenced)"
        )

        others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in others:
            t.cancel()
        await asyncio.gather(*others, return_exceptions=True)


class TestPluginTransitionColorForwarding:
    """`transition_colors`/`transition_color` reach a PLUGIN transition's
    constructor when (and only when) it declares the matching explicit
    parameter — parity with the builtin path's colors-elif-color precedence.
    Regression for the fireworks-era gap where typed colors were silently
    dropped on the dotted-type branch."""

    @pytest.fixture()
    def fake_transitions(self):
        from led_ticker import transitions as tr

        class ColorfulTransition:  # explicit colors + color params
            def __init__(self, colors=None, color=None, zing=1):
                self.colors = colors
                self.color = color
                self.zing = zing

            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                return canvas

        class CatchallTransition:  # **kwargs only — must NOT receive injection
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
                return canvas

        tr._TRANSITION_REGISTRY.pop("fake.colorful", None)
        tr._TRANSITION_REGISTRY.pop("fake.catchall", None)
        tr.register_transition("fake.colorful")(ColorfulTransition)
        tr.register_transition("fake.catchall")(CatchallTransition)
        yield ColorfulTransition, CatchallTransition
        tr._TRANSITION_REGISTRY.pop("fake.colorful", None)
        tr._TRANSITION_REGISTRY.pop("fake.catchall", None)

    def test_colors_injected_when_ctor_accepts(self, fake_transitions):
        from led_ticker.config import TransitionConfig

        cfg = TransitionConfig(type="fake.colorful", colors=[(255, 0, 0), (0, 255, 0)])
        obj = _build_trans_obj(cfg)
        assert obj.colors == [(255, 0, 0), (0, 255, 0)]

    def test_colors_wins_over_color_like_builtins(self, fake_transitions):
        from led_ticker.config import TransitionConfig

        cfg = TransitionConfig(
            type="fake.colorful", colors=[(1, 2, 3)], color=(9, 9, 9)
        )
        obj = _build_trans_obj(cfg)
        assert obj.colors == [(1, 2, 3)]
        assert obj.color is None  # elif precedence — color NOT also injected

    def test_color_injected_when_colors_absent(self, fake_transitions):
        from led_ticker.config import TransitionConfig

        cfg = TransitionConfig(type="fake.colorful", color=(9, 9, 9))
        obj = _build_trans_obj(cfg)
        assert obj.color == (9, 9, 9)

    def test_extra_wins_over_typed_field(self, fake_transitions):
        from led_ticker.config import TransitionConfig

        cfg = TransitionConfig(
            type="fake.colorful",
            colors=[(1, 1, 1)],
            extra={"colors": [(7, 7, 7)]},
        )
        obj = _build_trans_obj(cfg)
        assert obj.colors == [(7, 7, 7)]  # the plugin-local key keeps meaning

    def test_catchall_ctor_gets_no_injection(self, fake_transitions):
        from led_ticker.config import TransitionConfig

        cfg = TransitionConfig(type="fake.catchall", colors=[(1, 2, 3)])
        obj = _build_trans_obj(cfg)
        assert "colors" not in obj.kwargs  # **kwargs is not an opt-in

    def test_no_colors_no_injection(self, fake_transitions):
        from led_ticker.config import TransitionConfig

        cfg = TransitionConfig(type="fake.colorful", extra={"zing": 3})
        obj = _build_trans_obj(cfg)
        assert obj.colors is None and obj.zing == 3

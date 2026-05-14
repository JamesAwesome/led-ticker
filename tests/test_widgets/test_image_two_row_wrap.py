"""Tests for bottom_text_wrap on image widgets in two-row mode.

Mirrors test_image_text_wrap.py's structure. Single-row image
(no bottom_text) refuses bottom_text_wrap; two-row image
(bottom_text set) accepts it. Top row never wraps.
"""

from __future__ import annotations

import pytest
from PIL import Image

from led_ticker.widgets.still import StillImage


def _make_png(tmp_path, color=(0, 0, 0), size=(32, 32), name="img.png"):
    img = Image.new("RGB", size, color=color)
    p = tmp_path / name
    img.save(p, format="PNG")
    return p


def _still_two_row(tmp_path, **kwargs):
    """Build a two-row StillImage with reasonable defaults."""
    defaults = dict(
        path=str(_make_png(tmp_path)),
        top_text="TOP",
        bottom_text="bottom marquee",
    )
    defaults.update(kwargs)
    return StillImage(**defaults)


class TestBottomTextWrapDefaults:
    def test_bottom_text_wrap_defaults_false(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_wrap is False

    def test_bottom_text_separator_defaults_none(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_separator is None

    def test_bottom_text_separator_color_defaults_none(self, tmp_path):
        w = _still_two_row(tmp_path)
        assert w.bottom_text_separator_color is None


class TestBottomTextWrapValidation:
    def test_wrap_requires_two_row_mode(self, tmp_path):
        """bottom_text_wrap on a single-row image widget (no bottom_text)
        is refused. Error suggests text_wrap as the right knob."""
        with pytest.raises(
            ValueError,
            match="bottom_text_wrap=True requires non-empty bottom_text",
        ):
            StillImage(
                path=str(_make_png(tmp_path)),
                text="single row",
                bottom_text_wrap=True,
            )

    def test_wrap_requires_non_empty_bottom_text(self, tmp_path):
        """bottom_text_wrap=True with bottom_text='' is refused even in
        two-row mode."""
        with pytest.raises(
            ValueError,
            match="bottom_text_wrap=True requires non-empty bottom_text",
        ):
            StillImage(
                path=str(_make_png(tmp_path)),
                top_text="TOP",
                bottom_text="",
                bottom_text_wrap=True,
            )

    def test_separator_without_wrap_refused(self, tmp_path):
        with pytest.raises(
            ValueError, match="bottom_text_separator.*requires bottom_text_wrap"
        ):
            _still_two_row(tmp_path, bottom_text_separator=" * ")

    def test_separator_color_without_wrap_refused(self, tmp_path):
        with pytest.raises(
            ValueError,
            match="bottom_text_separator_color.*requires bottom_text_wrap",
        ):
            _still_two_row(tmp_path, bottom_text_separator_color=(255, 0, 0))

    def test_wrap_in_two_row_mode_accepted(self, tmp_path):
        w = _still_two_row(tmp_path, bottom_text_wrap=True)
        assert w.bottom_text_wrap is True

    def test_v1_text_wrap_still_refused_in_two_row(self, tmp_path):
        """v1's text_wrap stays single-row-only — refused when
        bottom_text is set. Sharpened message points at bottom_text_wrap."""
        with pytest.raises(ValueError, match="text_wrap.*single-row.*bottom_text_wrap"):
            StillImage(
                path=str(_make_png(tmp_path)),
                top_text="TOP",
                bottom_text="bottom",
                text_wrap=True,
            )


class TestBottomSeparatorColorRegistration:
    def test_in_provider_keys(self):
        from led_ticker.app import _PROVIDER_COLOR_KEYS

        assert "bottom_text_separator_color" in _PROVIDER_COLOR_KEYS

    def test_in_effect_attrs(self):
        from led_ticker.widgets._frame_aware import _FrameAware

        assert "bottom_text_separator_color" in _FrameAware._EFFECT_ATTRS

    def test_rainbow_coerced(self):
        from led_ticker.app import _coerce_widget_colors

        cfg = {"bottom_text_separator_color": "rainbow"}
        _coerce_widget_colors(cfg)
        provider = cfg["bottom_text_separator_color"]
        assert hasattr(provider, "color_for")
        assert provider.per_char is True


class TestBottomTextWrapOnWrongWidgetType:
    """Same guard pattern v1 uses: drop falsy defaults silently,
    raise on truthy values when the widget type can't accept the field."""

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_on_message_rejected(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(ValueError, match="bottom_text_wrap.*only valid"):
                await _build_widget(
                    {
                        "type": "message",
                        "text": "hi",
                        "bottom_text_wrap": True,
                    },
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_bottom_text_separator_on_message_rejected(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            with pytest.raises(ValueError, match="bottom_text_separator.*only valid"):
                await _build_widget(
                    {
                        "type": "message",
                        "text": "hi",
                        "bottom_text_separator": " * ",
                    },
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_false_on_message_dropped_silently(self):
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(
                {
                    "type": "message",
                    "text": "hi",
                    "bottom_text_wrap": False,
                },
                session=session,
            )
        assert widget is not None

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_on_two_row_accepted(self):
        """two_row is a NEW addition to the allowed types in v2."""
        import aiohttp

        from led_ticker.app import _build_widget

        async with aiohttp.ClientSession() as session:
            widget = await _build_widget(
                {
                    "type": "two_row",
                    "top_text": "TOP",
                    "bottom_text": "bottom",
                    "bottom_text_wrap": True,
                },
                session=session,
            )
        assert widget.bottom_text_wrap is True

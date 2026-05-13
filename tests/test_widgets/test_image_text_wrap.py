"""Tests for text_wrap on image widgets (gif + still).

Validates field defaults, validation errors, and (in later tasks)
the seamless wrap render math. Single-row image widgets only —
two-row mode + TwoRowMessage wrap is intentionally out of scope
for v1 and validated to refuse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from led_ticker.widgets.still import StillImage

# Reuse the shared 16×16 RGBA fixture used by other image-widget
# tests. Path is conventional; if it doesn't exist locally, this
# import-line failure surfaces the issue at test collection time.
FIXTURE = Path(__file__).parent / "fixtures" / "test_16x16.png"


def _still(**kwargs):
    """Build a StillImage with the shared fixture and kw overrides."""
    defaults = dict(path=str(FIXTURE), text="hello")
    defaults.update(kwargs)
    return StillImage(**defaults)


class TestTextWrapFieldDefaults:
    def test_text_wrap_defaults_false(self):
        w = _still()
        assert w.text_wrap is False

    def test_text_separator_defaults_none(self):
        w = _still()
        assert w.text_separator is None

    def test_text_separator_color_defaults_none(self):
        w = _still()
        assert w.text_separator_color is None


class TestTextWrapValidation:
    def test_wrap_requires_scroll_align(self):
        with pytest.raises(ValueError, match="text_wrap.*requires.*text_align"):
            _still(text_wrap=True, text_align="left")

    def test_wrap_refuses_two_row(self):
        with pytest.raises(ValueError, match="text_wrap.*not supported.*two-row"):
            _still(
                text_wrap=True,
                top_text="top",
                bottom_text="bottom",
            )

    def test_separator_without_wrap_refused(self):
        with pytest.raises(ValueError, match="text_separator.*requires.*text_wrap"):
            _still(text_separator=" * ", text_align="scroll")

    def test_separator_color_without_wrap_refused(self):
        with pytest.raises(
            ValueError, match="text_separator_color.*requires.*text_wrap"
        ):
            _still(text_separator_color=(255, 0, 0), text_align="scroll")

    def test_wrap_with_scroll_align_accepted(self):
        # text_align="scroll" needs transparent regions, so use
        # text_align="scroll_over" which doesn't impose that.
        w = _still(text_wrap=True, text_align="scroll_over")
        assert w.text_wrap is True

    def test_wrap_with_explicit_scroll_and_pillarbox_accepted(self):
        # text_align="scroll" + non-stretch fit is fine.
        w = _still(text_wrap=True, text_align="scroll", fit="fit")
        assert w.text_wrap is True


class TestSeparatorColorCoercion:
    def test_separator_color_in_provider_keys(self):
        """text_separator_color must be in _PROVIDER_COLOR_KEYS so
        the app.py coercion path wraps raw [r,g,b] into a
        ColorProvider before the widget sees it."""
        from led_ticker.app import _PROVIDER_COLOR_KEYS

        assert "text_separator_color" in _PROVIDER_COLOR_KEYS

    def test_separator_color_in_effect_attrs(self):
        """text_separator_color must be in _FrameAware._EFFECT_ATTRS
        so it gets its own per-effect frame counter (matters for
        continuous-phase providers like Rainbow)."""
        from led_ticker.widgets._frame_aware import _FrameAware

        assert "text_separator_color" in _FrameAware._EFFECT_ATTRS

    def test_separator_color_string_coerced(self):
        """When the app loader sees text_separator_color = 'rainbow',
        _coerce_widget_colors must convert it to a Rainbow provider."""
        from led_ticker.app import _coerce_widget_colors

        cfg = {"text_separator_color": "rainbow"}
        _coerce_widget_colors(cfg)
        provider = cfg["text_separator_color"]
        assert hasattr(provider, "color_for")
        # Rainbow is per-char by default.
        assert provider.per_char is True

"""Tests for bottom_text_wrap on TwoRowMessage widget."""

from __future__ import annotations

import pytest

from led_ticker.widgets.two_row import TwoRowMessage


def _two_row(**kwargs):
    defaults = dict(top_text="TOP", bottom_text="bottom marquee")
    defaults.update(kwargs)
    return TwoRowMessage(**defaults)


class TestBottomTextWrapDefaults:
    def test_bottom_text_wrap_defaults_false(self):
        w = _two_row()
        assert w.bottom_text_wrap is False

    def test_bottom_text_separator_defaults_none(self):
        w = _two_row()
        assert w.bottom_text_separator is None

    def test_bottom_text_separator_color_defaults_none(self):
        w = _two_row()
        assert w.bottom_text_separator_color is None


class TestWrapsForeverProperty:
    """The cooperation contract with `_swap_and_scroll`. True only
    when bottom_text_wrap=True AND bottom_text is non-empty."""

    def test_wraps_forever_false_by_default(self):
        w = _two_row()
        assert w.wraps_forever is False

    def test_wraps_forever_true_when_wrap_enabled(self):
        w = _two_row(bottom_text_wrap=True)
        assert w.wraps_forever is True

    def test_wraps_forever_false_when_bottom_empty(self):
        """bottom_text='' is refused at validation, but defensively
        wraps_forever should be False if it slips through (e.g.,
        attribute set after construction)."""
        w = _two_row(bottom_text_wrap=True)
        w.bottom_text = ""
        assert w.wraps_forever is False


class TestBottomTextWrapValidation:
    def test_wrap_requires_non_empty_bottom_text(self):
        with pytest.raises(
            ValueError,
            match="bottom_text_wrap=True requires non-empty bottom_text",
        ):
            TwoRowMessage(top_text="TOP", bottom_text="", bottom_text_wrap=True)

    def test_separator_without_wrap_refused(self):
        with pytest.raises(
            ValueError, match="bottom_text_separator.*requires bottom_text_wrap"
        ):
            _two_row(bottom_text_separator=" * ")

    def test_separator_color_without_wrap_refused(self):
        with pytest.raises(
            ValueError,
            match="bottom_text_separator_color.*requires bottom_text_wrap",
        ):
            _two_row(bottom_text_separator_color=(255, 0, 0))

    def test_wrap_accepted_with_bottom_text(self):
        w = _two_row(bottom_text_wrap=True)
        assert w.bottom_text_wrap is True

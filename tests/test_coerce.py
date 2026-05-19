"""Tests for led_ticker._coerce — pure coercion helpers for config load."""

import pytest

from led_ticker._coerce import CoercionWarning, coerce_int


class TestCoerceInt:
    def test_int_passthrough_no_warning(self):
        value, warning = coerce_int(25, field="font_size")
        assert value == 25
        assert warning is None

    def test_string_of_digits_coerces_with_warning(self):
        value, warning = coerce_int("25", field="font_size")
        assert value == 25
        assert isinstance(warning, CoercionWarning)
        assert warning.field == "font_size"
        assert warning.original == "25"
        assert warning.coerced == 25
        assert "font_size" in warning.message
        assert '"25"' in warning.message

    def test_negative_string_coerces(self):
        value, warning = coerce_int("-5", field="text_y_offset")
        assert value == -5
        assert warning is not None

    def test_bool_rejected(self):
        # bool is an int subclass; coercing true→1 would reopen the
        # font_threshold / bottom_text_loops hole.
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int(True, field="font_size")

    def test_non_numeric_string_rejected(self):
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int("big", field="font_size")

    def test_float_rejected(self):
        # Floats should use coerce_float; rejecting here makes intent explicit.
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int(2.5, field="font_size")

    def test_float_string_rejected(self):
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int("2.5", field="font_size")

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="must be an int"):
            coerce_int(None, field="font_size")

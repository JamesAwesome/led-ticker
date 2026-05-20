"""Tests for led_ticker._coerce — pure coercion helpers for config load."""

import pytest

from led_ticker._coerce import CoercionWarning, coerce_choice, coerce_float, coerce_int


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

    def test_warning_carries_fix_string(self):
        """CoercionWarning.fix should be a one-line actionable instruction."""
        _, warning = coerce_int("25", field="font_size")
        assert warning is not None
        assert warning.fix  # non-empty
        assert "font_size" in warning.fix
        assert "25" in warning.fix


class TestCoerceFloat:
    def test_float_passthrough(self):
        value, warning = coerce_float(3.0, field="hold_time")
        assert value == 3.0
        assert warning is None

    def test_int_promotes_to_float_no_warning(self):
        # int → float promotion is standard Python; no coercion warning.
        value, warning = coerce_float(3, field="hold_time")
        assert value == 3.0
        assert isinstance(value, float)
        assert warning is None

    def test_string_of_decimal_coerces_with_warning(self):
        value, warning = coerce_float("3.0", field="hold_time")
        assert value == 3.0
        assert warning is not None
        assert warning.field == "hold_time"
        assert warning.original == "3.0"
        assert warning.coerced == 3.0

    def test_string_of_integer_coerces_to_float(self):
        value, warning = coerce_float("3", field="hold_time")
        assert value == 3.0
        assert warning is not None

    def test_bool_rejected(self):
        with pytest.raises(ValueError, match="must be a float"):
            coerce_float(True, field="hold_time")

    def test_non_numeric_string_rejected(self):
        with pytest.raises(ValueError, match="must be a float"):
            coerce_float("3s", field="hold_time")

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="must be a float"):
            coerce_float(None, field="hold_time")

    def test_warning_carries_fix_string(self):
        """Same convention as coerce_int — warnings include actionable fix."""
        _, warning = coerce_float("3.0", field="hold_time")
        assert warning is not None
        assert warning.fix
        assert "hold_time" in warning.fix


class TestCoerceChoice:
    VALID = frozenset({"left", "right", "center"})

    def test_canonical_value_passthrough(self):
        value, warning = coerce_choice("left", field="image_align", valid=self.VALID)
        assert value == "left"
        assert warning is None

    def test_uppercase_lowercases_with_warning(self):
        value, warning = coerce_choice("Left", field="image_align", valid=self.VALID)
        assert value == "left"
        assert warning is not None
        assert warning.field == "image_align"
        assert warning.original == "Left"
        assert warning.coerced == "left"

    def test_whitespace_stripped(self):
        value, warning = coerce_choice(
            "  right  ", field="image_align", valid=self.VALID
        )
        assert value == "right"
        assert warning is not None

    def test_mixed_case_lowercases(self):
        value, warning = coerce_choice("CENTER", field="image_align", valid=self.VALID)
        assert value == "center"
        assert warning is not None

    def test_unknown_value_after_normalize_rejected(self):
        with pytest.raises(ValueError, match="not a valid"):
            coerce_choice("Middle", field="image_align", valid=self.VALID)

    def test_unknown_value_passthrough_rejected(self):
        with pytest.raises(ValueError, match="not a valid"):
            coerce_choice("middle", field="image_align", valid=self.VALID)

    def test_non_string_rejected(self):
        with pytest.raises(ValueError, match="must be a string"):
            coerce_choice(42, field="image_align", valid=self.VALID)

    def test_warning_carries_fix_string(self):
        _, warning = coerce_choice("Left", field="image_align", valid=self.VALID)
        assert warning is not None
        assert warning.fix
        assert "image_align" in warning.fix
        assert "left" in warning.fix

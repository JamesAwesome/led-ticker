"""Tests for led_ticker.widgets.clock."""

from datetime import datetime

import pytest

from led_ticker.widgets.clock import format_clock


def _dt(h, m):
    return datetime(2026, 6, 13, h, m)


def test_12h_preset_no_leading_zero_pm():
    assert format_clock(_dt(15, 9), "12h") == "3:09 PM"


def test_12h_preset_midnight_is_12_am():
    assert format_clock(_dt(0, 9), "12h") == "12:09 AM"


def test_12h_preset_noon_is_12_pm():
    assert format_clock(_dt(12, 0), "12h") == "12:00 PM"


def test_24h_preset_pads_hour():
    assert format_clock(_dt(15, 9), "24h") == "15:09"
    assert format_clock(_dt(3, 9), "24h") == "03:09"


def test_custom_strftime_passthrough():
    # Any value containing % is a strftime template, rendered verbatim.
    assert format_clock(_dt(15, 9), "%H:%M") == "15:09"


def test_custom_date_format_one_line():
    # A date token in the format renders date + time inline (v1's "date line").
    assert format_clock(_dt(15, 9), "%Y-%m-%d %H:%M") == "2026-06-13 15:09"


def test_unknown_preset_raises():
    with pytest.raises(ValueError, match="12h"):
        format_clock(_dt(15, 9), "12hr")

"""A wrong-side count date surfaces as a non-blocking validation warning."""

from datetime import date, timedelta
from pathlib import Path

from led_ticker.app.factories import collect_validation_warnings
from led_ticker.plugin import ValidationContext


def _ctx():
    # ValidationContext fields (plugin.py): scale, content_height, panel_width,
    # panel_height, config_dir. The count hook ignores ctx, so values are nominal.
    return ValidationContext(
        scale=1,
        content_height=16,
        panel_width=160,
        panel_height=16,
        config_dir=Path("."),
    )


def test_future_countup_surfaces_warning():
    cfg = {
        "type": "countup",
        "text": "Since",
        "countup_date": date.today() + timedelta(days=30),
    }
    warnings = collect_validation_warnings(cfg, _ctx())
    assert any("future" in w for w in warnings)


def test_in_range_countup_no_warning():
    cfg = {
        "type": "countup",
        "text": "Since",
        "countup_date": date.today() - timedelta(days=30),
    }
    assert collect_validation_warnings(cfg, _ctx()) == []


def test_string_supplied_past_countdown_surfaces_warning():
    # a QUOTED (string) past date used to be masked by the isinstance guard
    cfg = {
        "type": "countdown",
        "text": "X",
        "countdown_date": (date.today() - timedelta(days=5)).isoformat(),
    }
    warnings = collect_validation_warnings(cfg, _ctx())
    assert any("past" in w for w in warnings)


# --- validate_config preflight date rule (validate never constructs widgets) ---

from led_ticker.widgets.count import TickerCountdown, TickerCountup  # noqa: E402


def test_validate_config_rejects_bad_date_string():
    errors = TickerCountdown.validate_config({"countdown_date": "not-a-date"})
    assert any("YYYY-MM-DD" in e for e in errors)


def test_validate_config_requires_date():
    assert any("required" in e for e in TickerCountup.validate_config({}))


def test_validate_config_accepts_string_and_native_date():
    assert TickerCountdown.validate_config({"countdown_date": "2099-01-01"}) == []
    assert TickerCountup.validate_config({"countup_date": date(2000, 1, 1)}) == []

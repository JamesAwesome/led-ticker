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

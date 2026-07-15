"""[display] timezone + section-level schedule parsing (strict)."""

import pytest

from led_ticker.config import load_config

BASE = """
[display]
rows = 16
cols = 32
{display_extra}

[[playlist.section]]
mode = "slideshow"
{section_extra}

[[playlist.section.widget]]
type = "message"
text = "hi"
"""


def _write(tmp_path, display_extra="", section_extra=""):
    p = tmp_path / "config.toml"
    p.write_text(BASE.format(display_extra=display_extra, section_extra=section_extra))
    return p


def test_display_timezone_default_empty(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.display.timezone == ""


def test_display_timezone_parsed(tmp_path):
    cfg = load_config(_write(tmp_path, display_extra='timezone = "America/New_York"'))
    assert cfg.display.timezone == "America/New_York"


def test_section_schedule_default_none(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.sections[0].schedule is None


def test_section_schedule_parsed(tmp_path):
    schedule_extra = (
        'schedule = { start = "09:00", end = "21:00", days = ["sat", "sun"] }'
    )
    cfg = load_config(_write(tmp_path, section_extra=schedule_extra))
    s = cfg.sections[0].schedule
    assert s is not None
    assert (s.window.start, s.window.end) == (9 * 60, 21 * 60)
    assert s.window.days == frozenset({5, 6})


def test_malformed_section_schedule_raises_with_location(tmp_path):
    with pytest.raises(ValueError, match=r"section\[0\]\.schedule"):
        load_config(
            _write(
                tmp_path, section_extra='schedule = { start = "9am", end = "17:00" }'
            )
        )


def test_brightness_tz_falls_back_to_display_timezone():
    from led_ticker.app.run import _schedule_tz_name
    from led_ticker.config import DisplayConfig, ScheduleConfig

    d = DisplayConfig(timezone="America/Chicago")
    assert _schedule_tz_name(d) == "America/Chicago"
    d2 = DisplayConfig(
        timezone="America/Chicago",
        schedule=ScheduleConfig(timezone="Europe/London"),
    )
    assert _schedule_tz_name(d2) == "Europe/London"
    assert _schedule_tz_name(DisplayConfig()) == ""

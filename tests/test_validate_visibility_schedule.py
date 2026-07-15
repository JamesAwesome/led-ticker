"""Preflight rules for visibility schedules: timezone, clock note, blank sweep."""

import asyncio

from led_ticker.validate import validate_config_text

BASE = """
[display]
rows = 16
cols = 32
backend = "headless"
{display_extra}

{sections}
"""

SECTION = """
[[playlist.section]]
mode = "slideshow"
{section_extra}
[[playlist.section.widget]]
type = "message"
text = "hi"
{widget_extra}
"""


def _run(display_extra="", sections=None):
    default_section = SECTION.format(section_extra="", widget_extra="")
    text = BASE.format(
        display_extra=display_extra,
        sections="\n".join(sections or [default_section]),
    )
    return asyncio.run(validate_config_text(text))


def test_bad_display_timezone_is_an_error():
    res = _run(display_extra='timezone = "Not/AZone"')
    assert any("display.timezone" in i.location for i in res.errors)


def test_valid_display_timezone_passes():
    res = _run(display_extra='timezone = "America/New_York"')
    assert not any("display.timezone" in i.location for i in res.errors)


def test_clock_note_printed_when_schedules_present():
    res = _run(
        display_extra='timezone = "America/New_York"',
        sections=[
            SECTION.format(
                section_extra='schedule = { start = "09:00", end = "17:00" }',
                widget_extra="",
            )
        ],
    )
    assert any("visibility schedules evaluate at" in n for n in res.notes)
    assert any("America/New_York" in n for n in res.notes)


def test_no_clock_note_without_schedules():
    res = _run()
    assert not any("visibility schedules evaluate" in n for n in res.notes)


def test_blank_interval_warning_when_sign_has_gaps():
    # One section, scheduled 09:00-17:00: the sign is blank 17:00-09:00 daily.
    res = _run(
        sections=[
            SECTION.format(
                section_extra='schedule = { start = "09:00", end = "17:00" }',
                widget_extra="",
            )
        ]
    )
    warning_texts = [i.message for i in res.warnings]
    assert any("blank" in t for t in warning_texts)


def test_no_blank_warning_when_windows_cover_the_week():
    open_w = SECTION.format(
        section_extra='schedule = { start = "09:00", end = "17:00" }', widget_extra=""
    )
    closed_w = SECTION.format(
        section_extra='schedule = { start = "17:00", end = "09:00" }', widget_extra=""
    )
    res = _run(sections=[open_w, closed_w])
    assert not any("blank" in i.message for i in res.warnings)


def test_unscheduled_section_means_never_blank():
    scheduled = SECTION.format(
        section_extra='schedule = { start = "09:00", end = "17:00" }', widget_extra=""
    )
    always_on = SECTION.format(section_extra="", widget_extra="")
    res = _run(sections=[scheduled, always_on])
    assert not any("blank" in i.message for i in res.warnings)


def test_widget_level_schedules_participate_in_sweep():
    # Single section, its ONLY widget scheduled 09:00-17:00 -> blank warning.
    res = _run(
        sections=[
            SECTION.format(
                section_extra="",
                widget_extra='schedule = { start = "09:00", end = "17:00" }',
            )
        ]
    )
    assert any("blank" in i.message for i in res.warnings)

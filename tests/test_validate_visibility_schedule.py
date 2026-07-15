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


def test_blank_interval_warning_exact_week_sweep_arithmetic():
    """Fix F.3a (2026-07-15): a single daily 09:00-17:00 window leaves the
    sign blank 17:00-09:00 every night. The week sweep (10,080 minutes)
    merges the Sun-tail/Mon-head wrap into one run and caps the shown list
    at 4, so there are 7 nightly gaps -> 4 shown + "(and 3 more)". Verified
    against the actual validate output (not guessed) before encoding."""
    res = _run(
        sections=[
            SECTION.format(
                section_extra='schedule = { start = "09:00", end = "17:00" }',
                widget_extra="",
            )
        ]
    )
    blank = [i for i in res.warnings if "blank" in i.message]
    assert blank
    assert blank[0].location == "playlist"
    assert "Mon 17:00-Tue 09:00" in blank[0].message
    assert "(and 3 more)" in blank[0].message


def test_blank_interval_warning_weekday_wrap_merge():
    """Fix F.3b: a mon-fri 09:00-17:00 window leaves the sign blank every
    weeknight PLUS the whole weekend — the sweep merges Friday evening
    through Monday morning into one run: "Fri 17:00-Mon 09:00"."""
    res = _run(
        sections=[
            SECTION.format(
                section_extra=(
                    'schedule = { start = "09:00", end = "17:00", '
                    'days = ["mon", "tue", "wed", "thu", "fri"] }'
                ),
                widget_extra="",
            )
        ]
    )
    blank = [i for i in res.warnings if "blank" in i.message]
    assert blank
    assert blank[0].location == "playlist"
    assert "Fri 17:00-Mon 09:00" in blank[0].message


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


def test_title_schedule_is_a_static_error():
    # Section titles are not schedulable (they bypass the engine's
    # visibility gate) — `_build_title` raises at build time, but the
    # static `validate` pass never calls `_build_title`, so without a
    # dedicated rule this misconfiguration passes preflight clean.
    title_with_schedule = (
        "[playlist.section.title]\n"
        'type = "message"\n'
        'text = "hi"\n'
        'schedule = { start = "09:00", end = "17:00" }'
    )
    res = _run(
        sections=[SECTION.format(section_extra=title_with_schedule, widget_extra="")]
    )
    title_errors = [i for i in res.errors if "title" in i.location]
    assert title_errors
    assert any("schedule" in i.message for i in title_errors)


def test_no_title_schedule_error_on_happy_path_config():
    # Existing happy-path config (no title at all) must not trip the new rule.
    res = _run()
    assert not any(
        "title" in i.location and "schedule" in i.message for i in res.errors
    )


# ---------------------------------------------------------------------------
# Fix E: the blank sweep must respect a present title. `run._section_has_content`
# treats ANY title dict as content regardless of the widget rotation — the
# static sweep must mirror that or it warns "blank" for windows that are, in
# fact, showing the section's title.
# ---------------------------------------------------------------------------

_SECTION_WITH_TITLE_ALL_WIDGETS_OUT = """
[[playlist.section]]
mode = "slideshow"

[playlist.section.title]
type = "message"
text = "Always Visible"

[[playlist.section.widget]]
type = "message"
text = "hi"
schedule = { start = "09:00", end = "17:00" }
"""

_SECTION_NO_TITLE_ALL_WIDGETS_OUT = SECTION.format(
    section_extra="",
    widget_extra='schedule = { start = "09:00", end = "17:00" }',
)


def test_title_present_with_all_widgets_scheduled_out_suppresses_blank_warning():
    res = _run(sections=[_SECTION_WITH_TITLE_ALL_WIDGETS_OUT])
    assert not any("blank" in i.message for i in res.warnings)


def test_same_section_without_title_still_warns_blank():
    # Same widget-level schedule, no title: the section IS blank 17:00-09:00.
    res = _run(sections=[_SECTION_NO_TITLE_ALL_WIDGETS_OUT])
    assert any("blank" in i.message for i in res.warnings)


# ---------------------------------------------------------------------------
# Fix D: `loop_count = 0` (forever) + a section-level `schedule` never
# re-checks the schedule after entry, so `validate` warns.
# ---------------------------------------------------------------------------


def _forever_scheduled_message(res):
    return [i.message for i in res.warnings if i.location == "section[0]"]


def test_forever_section_with_schedule_warns():
    res = _run(
        sections=[
            SECTION.format(
                section_extra=(
                    'loop_count = 0\nschedule = { start = "09:00", end = "17:00" }'
                ),
                widget_extra="",
            )
        ]
    )
    msgs = _forever_scheduled_message(res)
    assert any("loop_count = 0" in m and "cycles forever" in m for m in msgs)


def test_finite_loop_count_section_with_schedule_does_not_warn():
    res = _run(
        sections=[
            SECTION.format(
                section_extra=(
                    'loop_count = 1\nschedule = { start = "09:00", end = "17:00" }'
                ),
                widget_extra="",
            )
        ]
    )
    assert not any("cycles forever" in m for m in _forever_scheduled_message(res))


def test_default_loop_count_section_with_schedule_does_not_warn():
    # loop_count omitted -> default 1 (finite), not 0 (forever).
    res = _run(
        sections=[
            SECTION.format(
                section_extra='schedule = { start = "09:00", end = "17:00" }',
                widget_extra="",
            )
        ]
    )
    assert not any("cycles forever" in m for m in _forever_scheduled_message(res))


def test_forever_section_with_only_widget_level_schedule_does_not_warn():
    # loop_count = 0 with NO section-level schedule (widget-level schedule
    # only, which _expand_sources re-checks every pass regardless of
    # loop_count) must not trip this rule.
    res = _run(
        sections=[
            SECTION.format(
                section_extra="loop_count = 0",
                widget_extra='schedule = { start = "09:00", end = "17:00" }',
            )
        ]
    )
    assert not any("cycles forever" in m for m in _forever_scheduled_message(res))

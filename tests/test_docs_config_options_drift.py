"""Tripwire test for docs/site/.../reference/config-options.mdx drift.

The reference page hand-curates a table of every TOML knob in each top-
level config section ([display], [title], [transitions], [[playlist.section]]).
The hand curation buys helpful contextual notes (e.g. "smallsign uses 5;
bigsign uses 8") that pure auto-generation would lose, but it's also a
drift risk — when src/led_ticker/config.py grows a new field, the docs
page has no built-in pressure to keep up.

This test is that pressure. Per section it asserts:
- Every key in the documented set appears as a row in the page's table
- Every row in the page's table is in the documented set

The DOCUMENTED_KEYS registry below is the source of truth for "what we
intentionally surface on the reference page". When the loader gains a
new TOML key:
  - if you want it documented: add it here AND to the .mdx page
  - if it's intentionally omitted (e.g. plugin-owned knobs like
    show_pikachu/show_pokeball that flow through TransitionConfig.extra):
    leave it out of DOCUMENTED_KEYS

The test will fail loudly either way until the registry and page agree.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from led_ticker.config import BusyLightConfig, DisplayConfig, WebConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE_PATH = (
    REPO_ROOT
    / "docs"
    / "site"
    / "src"
    / "content"
    / "docs"
    / "reference"
    / "config-options.mdx"
)


# Keys we intentionally document on the reference page, per section.
# Compare against the actual TOML key surface read by config.py.
DOCUMENTED_KEYS: dict[str, set[str]] = {
    # [display] surfaces every DisplayConfig field — they map 1:1 to
    # TOML keys via load_config's display_raw.get(...) calls.
    "display": {f.name for f in fields(DisplayConfig)},
    # [title] has just one knob.
    "title": {"delay"},
    # [transitions] surfaces the common knobs. show_pikachu/show_pokeball are
    # arcade-plugin knobs that flow through TransitionConfig.extra — they are
    # not built-in [transitions] fields and are not documented here.
    "transitions": {
        "default",
        "duration",
        "easing",
        "between_sections",
        "transition_fps",
        "separator_color",
        "separator",
        "separator_font",
        "separator_font_size",
        "separator_size",
    },
    # [[playlist.section]] — covers the user-facing knobs.
    # transition_specified is on the SectionConfig dataclass but not a
    # TOML key the user writes (the loader sets it based on whether
    # `transition` was present); documenting it explains why the field
    # exists.
    "section": {
        "mode",
        "loop_count",
        "hold_time",
        "continuous_scroll",
        "transition",
        "entry_transition",
        "widget_transition",
        "transition_duration",
        "transition_color",
        "transition_colors",
        "transition_fps",
        "scale",
        "content_height",
        "bg_color",
        "scroll_step_ms",
        "separator",
        "separator_color",
        "separator_font",
        "separator_font_size",
        "separator_size",
        "start_hold",
        "transition_specified",
    },
    # [busy_light] surfaces every BusyLightConfig field — 1:1 TOML keys.
    "busy_light": {f.name for f in fields(BusyLightConfig)},
    # [web] surfaces every WebConfig field — 1:1 TOML keys.
    "web": {f.name for f in fields(WebConfig)},
}


# Map [section] heading text -> DOCUMENTED_KEYS key. The page's section
# headings on the .mdx file vs the registry's keys.
SECTION_HEADINGS: dict[str, str] = {
    "## `[display]`": "display",
    "## `[title]`": "title",
    "## `[transitions]`": "transitions",
    "## `[[playlist.section]]`": "section",
    "## `[busy_light]`": "busy_light",
    "## `[web]`": "web",
}


_FIELD_NAME_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def _parse_section_field_names(page_text: str, heading: str) -> set[str]:
    """Return the set of `field_name` entries from the markdown table
    that follows the given heading on the page.

    Looks for the heading line, then walks forward through any blank
    lines + paragraphs until it finds a markdown table. Reads rows
    until the table ends (blank line or end of file) and extracts the
    first column when it's wrapped in backticks.
    """
    lines = page_text.splitlines()
    try:
        heading_idx = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration as e:
        raise AssertionError(f"Heading not found in page: {heading!r}") from e

    field_names: set[str] = set()
    in_table = False
    for line in lines[heading_idx + 1 :]:
        stripped = line.strip()

        # Stop once we hit the next H2 — don't bleed into another section.
        if stripped.startswith("## "):
            break

        # Detect table start: a row that begins with `|`.
        if not in_table:
            if stripped.startswith("|"):
                in_table = True
            else:
                continue

        # Inside a table — blank line or non-pipe line ends it.
        if in_table and not stripped.startswith("|"):
            break

        # Skip the header row (no backticks) and the separator row.
        match = _FIELD_NAME_RE.match(line)
        if match:
            field_names.add(match.group(1))

    if not field_names:
        raise AssertionError(
            f"No field rows parsed from the table after {heading!r} in {PAGE_PATH}"
        )

    return field_names


def test_docs_page_exists() -> None:
    """Correctness check: the page is where the test expects it."""
    assert PAGE_PATH.exists(), f"Reference page not found at {PAGE_PATH}"


def test_display_section_field_set_matches_docs() -> None:
    """Every DisplayConfig field appears in the page's [display] table,
    and the table doesn't list any fabricated fields."""
    page_text = PAGE_PATH.read_text()
    documented = DOCUMENTED_KEYS["display"]
    on_page = _parse_section_field_names(page_text, "## `[display]`")
    missing = documented - on_page
    extra = on_page - documented
    assert not missing, (
        f"DisplayConfig fields missing from [display] docs table: {sorted(missing)}.\n"
        "Add a row in docs/site/src/content/docs/reference/config-options.mdx,"
        " or remove the field from DOCUMENTED_KEYS['display'] if it shouldn't"
        " be documented."
    )
    assert not extra, (
        f"[display] docs table lists fields not in DisplayConfig: {sorted(extra)}.\n"
        "Either add them to src/led_ticker/config.py:DisplayConfig, "
        "or drop the row from the docs table."
    )


def test_busy_light_section_field_set_matches_docs() -> None:
    """Every BusyLightConfig field appears in the page's [busy_light] table,
    and the table doesn't list any fabricated fields."""
    page_text = PAGE_PATH.read_text()
    documented = DOCUMENTED_KEYS["busy_light"]
    on_page = _parse_section_field_names(page_text, "## `[busy_light]`")
    missing = documented - on_page
    extra = on_page - documented
    assert not missing, (
        "BusyLightConfig fields missing from [busy_light] docs table: "
        f"{sorted(missing)}.\n"
        "Add a row in docs/site/src/content/docs/reference/config-options.mdx,"
        " or remove the field from DOCUMENTED_KEYS['busy_light']."
    )
    assert not extra, (
        "[busy_light] docs table lists fields not in BusyLightConfig: "
        f"{sorted(extra)}.\n"
        "Either add them to src/led_ticker/config.py:BusyLightConfig, "
        "or drop the row from the docs table."
    )


def test_web_section_field_set_matches_docs() -> None:
    """Every WebConfig field appears in the page's [web] table,
    and the table doesn't list any fabricated fields."""
    page_text = PAGE_PATH.read_text()
    documented = DOCUMENTED_KEYS["web"]
    on_page = _parse_section_field_names(page_text, "## `[web]`")
    missing = documented - on_page
    extra = on_page - documented
    assert not missing, (
        "WebConfig fields missing from [web] docs table: "
        f"{sorted(missing)}.\n"
        "Add a row in docs/site/src/content/docs/reference/config-options.mdx,"
        " or remove the field from DOCUMENTED_KEYS['web']."
    )
    assert not extra, (
        "[web] docs table lists fields not in WebConfig: "
        f"{sorted(extra)}.\n"
        "Either add them to src/led_ticker/config.py:WebConfig, "
        "or drop the row from the docs table."
    )


def test_title_section_field_set_matches_docs() -> None:
    """[title] has just `delay` — assert that's all the docs page lists."""
    page_text = PAGE_PATH.read_text()
    documented = DOCUMENTED_KEYS["title"]
    on_page = _parse_section_field_names(page_text, "## `[title]`")
    assert on_page == documented, (
        f"[title] docs table drift.\n"
        f"  documented (in DOCUMENTED_KEYS['title']): {sorted(documented)}\n"
        f"  on page: {sorted(on_page)}"
    )


def test_transitions_section_field_set_matches_docs() -> None:
    """[transitions] common knobs match between docs and registry."""
    page_text = PAGE_PATH.read_text()
    documented = DOCUMENTED_KEYS["transitions"]
    on_page = _parse_section_field_names(page_text, "## `[transitions]`")
    assert on_page == documented, (
        f"[transitions] docs table drift.\n"
        f"  documented: {sorted(documented)}\n"
        f"  on page: {sorted(on_page)}\n"
        "If a new key was added to the loader and you want it surfaced on "
        "the docs page, add it to DOCUMENTED_KEYS['transitions'] AND the "
        ".mdx table. If it's intentionally niche and omitted, leave it out "
        "of both."
    )


def test_section_field_set_matches_docs() -> None:
    """[[playlist.section]] field surface matches between docs and registry."""
    page_text = PAGE_PATH.read_text()
    documented = DOCUMENTED_KEYS["section"]
    on_page = _parse_section_field_names(page_text, "## `[[playlist.section]]`")
    assert on_page == documented, (
        f"[[playlist.section]] docs table drift.\n"
        f"  documented: {sorted(documented)}\n"
        f"  on page: {sorted(on_page)}"
    )


def test_display_defaults_match_dataclass() -> None:
    """Defaults shown in the [display] table track the DisplayConfig dataclass.

    The table column reads e.g. ``| `pwm_bits` | int | `11` | ...``. Strip
    backticks from the third column and compare to the dataclass default.
    """
    page_text = PAGE_PATH.read_text()
    lines = page_text.splitlines()
    heading_idx = next(
        i for i, line in enumerate(lines) if line.strip() == "## `[display]`"
    )

    # Build (field_name, default_str) pairs from the table.
    row_re = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*[^|]+\|\s*`?([^`|]*?)`?\s*\|")
    table_defaults: dict[str, str] = {}
    in_table = False
    for line in lines[heading_idx + 1 :]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if not in_table:
            if stripped.startswith("|"):
                in_table = True
            else:
                continue
        if in_table and not stripped.startswith("|"):
            break
        match = row_re.match(line)
        if match:
            table_defaults[match.group(1)] = match.group(2).strip()

    # Compare to dataclass defaults.
    from dataclasses import MISSING

    drift = []
    for f in fields(DisplayConfig):
        if f.name not in table_defaults:
            continue  # field-set mismatch is caught by the field-set test
        # Skip nested-config fields that use default_factory — their "default"
        # is an instance of the sub-dataclass, not a scalar we can compare.
        if f.default is MISSING:
            continue
        page_default = table_defaults[f.name]
        # Normalize: strip wrapping quotes so `"adafruit-hat"` matches
        # the Python string "adafruit-hat", and lowercase True/False so
        # they match the markdown's `false` convention.
        actual = repr(f.default)
        if isinstance(f.default, bool):
            page_norm = page_default.lower()
            actual_norm = "true" if f.default else "false"
        elif isinstance(f.default, str):
            page_norm = page_default.strip('"')
            actual_norm = f.default
        else:
            page_norm = page_default
            actual_norm = str(f.default)
        if page_norm != actual_norm:
            drift.append(
                f"  - `{f.name}`: dataclass default = {actual!r},"
                f" page shows `{page_default}`"
            )

    assert not drift, (
        "Default value drift between DisplayConfig and the [display] docs table:\n"
        + "\n".join(drift)
    )

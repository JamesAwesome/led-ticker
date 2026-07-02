"""Rule 61: typewriter typing duration exceeds the effective hold —
the reveal gets chopped mid-type. Warning, not error.

Harness mirrors tests/test_validate.py: write TOML to tmp_path,
call validate_config (async), filter issues by rule == 61.
"""

import textwrap
from pathlib import Path

import pytest

from led_ticker.animations import Typewriter
from led_ticker.validate import _format_human, validate_config

_LONG_TEXT = "THIS MESSAGE IS WAY TOO LONG TO TYPE IN THREE SECONDS"  # 53 chars


def _toml(section_hold: float, widget_lines: str) -> str:
    """Build a minimal valid config TOML with one section + one message widget."""
    return textwrap.dedent(f"""\
        [display]
        rows = 32
        cols = 64
        chain_length = 8
        default_scale = 1

        [[playlist.section]]
        mode = "slideshow"
        hold_time = {section_hold}

        [[playlist.section.widget]]
        type = "message"
        text = "{_LONG_TEXT}"
        {widget_lines}
    """)


TOML_FIRES = _toml(3.0, 'animation = "typewriter"')
# fpc=3, 53 chars -> 7.8 s > 3.0 s -> rule 61 warning

TOML_SUFFICIENT_HOLD = _toml(10.0, 'animation = "typewriter"')
# 7.8 s < 10.0 s -> no rule 61

TOML_WIDGET_HOLD_SMALLER = _toml(10.0, 'animation = "typewriter"\nhold_time = 1.0')
# effective = max(10.0, 1.0) = 10.0 s -> no rule 61 (max semantics)

TOML_WIDGET_HOLD_RESCUES = _toml(3.0, 'animation = "typewriter"\nhold_time = 10.0')
# effective = max(3.0, 10.0) = 10.0 s -> no rule 61

TOML_DICT_FORM = _toml(3.0, 'animation = {style = "typewriter", frames_per_char = 6}')
# fpc=6 -> 15.6 s > 3.0 -> fires

TOML_NO_ANIMATION = _toml(3.0, "")
# same long text, no animation -> no rule 61


@pytest.fixture
def conf(tmp_path: Path):
    """Write a TOML string to a temp file and return its Path."""

    def _write(toml_str: str) -> Path:
        p = tmp_path / "config.toml"
        p.write_text(toml_str)
        return p

    return _write


async def test_rule61_fires_when_typing_exceeds_hold(conf) -> None:
    """Default typewriter on a short hold — warning fires with correct numbers."""
    result = await validate_config(conf(TOML_FIRES))
    issues = [w for w in result.warnings if w.rule == 61]
    assert len(issues) == 1, f"Expected 1 rule-61 warning, got: {result.warnings}"
    issue = issues[0]
    assert issue.severity == "warning"
    assert issue.location == "section[0].widget[0]"

    expected_duration = Typewriter().typing_duration_seconds(len(_LONG_TEXT))
    assert f"{expected_duration:.1f}" in issue.message, (
        f"Expected duration {expected_duration:.1f} in message: {issue.message}"
    )
    assert "3.0" in issue.message, f"Expected hold '3.0' in message: {issue.message}"
    assert "hold_time" in issue.fix, f"Expected 'hold_time' in fix: {issue.fix}"
    assert f"{expected_duration:.1f}" in issue.fix, (
        f"Expected duration in fix: {issue.fix}"
    )


async def test_rule61_no_fire_when_hold_sufficient(conf) -> None:
    """Hold time of 10 s covers the 7.8 s reveal — no warning."""
    result = await validate_config(conf(TOML_SUFFICIENT_HOLD))
    issues = [w for w in result.warnings if w.rule == 61]
    assert issues == [], f"Unexpected rule-61 warnings: {issues}"


async def test_rule61_no_fire_widget_hold_smaller_than_section(conf) -> None:
    """Widget hold_time=1.0 is SMALLER than section hold_time=10.0.
    Effective = max(10.0, 1.0) = 10.0 s -> no warning (must not invert engine math).
    """
    result = await validate_config(conf(TOML_WIDGET_HOLD_SMALLER))
    issues = [w for w in result.warnings if w.rule == 61]
    assert issues == [], (
        f"False fire: widget hold < section hold should not trigger rule 61. "
        f"Got: {issues}"
    )


async def test_rule61_no_fire_widget_hold_rescues(conf) -> None:
    """Widget hold_time=10.0 rescues a short section hold_time=3.0.
    Effective = max(3.0, 10.0) = 10.0 s -> no warning.
    """
    result = await validate_config(conf(TOML_WIDGET_HOLD_RESCUES))
    issues = [w for w in result.warnings if w.rule == 61]
    assert issues == [], f"Unexpected rule-61 warnings: {issues}"


async def test_rule61_dict_form_with_frames_per_char(conf) -> None:
    """Dict animation form {style = 'typewriter', frames_per_char = 6} fires."""
    result = await validate_config(conf(TOML_DICT_FORM))
    issues = [w for w in result.warnings if w.rule == 61]
    assert len(issues) == 1, f"Expected 1 rule-61 warning, got: {result.warnings}"
    issue = issues[0]

    expected_duration = Typewriter(frames_per_char=6).typing_duration_seconds(
        len(_LONG_TEXT)
    )
    assert f"{expected_duration:.1f}" in issue.message, (
        f"Expected duration {expected_duration:.1f} in message: {issue.message}"
    )


async def test_rule61_no_fire_when_no_animation(conf) -> None:
    """Same long text but no animation field — no rule-61 warning."""
    result = await validate_config(conf(TOML_NO_ANIMATION))
    issues = [w for w in result.warnings if w.rule == 61]
    assert issues == [], f"Unexpected rule-61 warnings: {issues}"


async def test_rule61_appears_in_human_report(conf) -> None:
    """Startup surfacing: _format_human output includes rule-61 message text.
    app/run.py logs validate's human report at config load — rule 61 flows
    through automatically via _log_validation_report.
    """
    result = await validate_config(conf(TOML_FIRES))
    human = _format_human(result)

    expected_duration = Typewriter().typing_duration_seconds(len(_LONG_TEXT))
    assert f"{expected_duration:.1f}" in human, (
        f"Expected duration {expected_duration:.1f} in human report:\n{human}"
    )
    assert "hold_time" in human, f"Expected 'hold_time' in human report:\n{human}"
    assert "⚠ WARNING" in human, f"Expected WARNING marker in human report:\n{human}"

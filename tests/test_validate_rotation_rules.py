"""Rules 62 + 63: animation duration vs hold, rotation on hires fonts.

Rule 62 — a non-Typewriter animation whose run time exceeds the effective
hold will be cut mid-animation (warning). Generalises rule 61's mechanism
via duck-typed ``frames_to_rest``.

Rule 63 — a rotation-emitting animation on a hires font: the spin silently
won't apply until physical-resolution rotation ships.

Harness mirrors tests/test_validate_typewriter_hold.py: write TOML to
tmp_path, call validate_config (async), filter issues by rule number.
The stub animation is registered into _ANIMATION_REGISTRY by fixture
and cleaned up in teardown — no plugin install required.
"""

import textwrap
from pathlib import Path

import pytest

from led_ticker.animations import _ANIMATION_REGISTRY, AnimationFrame
from led_ticker.constants import ENGINE_TICK_MS
from led_ticker.validate import validate_config

# ---------------------------------------------------------------------------
# Stub animation — stands in for a rotation-emitting, frames_to_rest-bearing
# animation (e.g. flair.propeller). Never installed in the test venv.
# ---------------------------------------------------------------------------


class _StubPropeller:
    """Stands in for flair's Propeller: rotation-emitting, one-shot."""

    restart_on_visit = True
    emits_rotation = True

    def __init__(self, spin_seconds: float = 1.0) -> None:
        self.total_frames = max(1, int(spin_seconds * 1000) // ENGINE_TICK_MS)

    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(visible_text=full_text)

    def frames_to_rest(self, frame, total_chars):
        return max(0, self.total_frames - frame)


@pytest.fixture
def stub_propeller_registered():
    _ANIMATION_REGISTRY["teststub.propeller"] = _StubPropeller
    yield
    del _ANIMATION_REGISTRY["teststub.propeller"]


# ---------------------------------------------------------------------------
# TOML builder
# ---------------------------------------------------------------------------

_LONG_TEXT = "THIS MESSAGE IS WAY TOO LONG FOR A SHORT HOLD"  # 46 chars


def _toml(
    section_hold: float,
    widget_extra: str,
    font_line: str = "",
    font_size_line: str = "",
) -> str:
    """Build a minimal valid config TOML with one section + one message widget.

    font_size_line is needed when font_line names a hires font (rule 5 requires
    an explicit font_size for hires fonts; without it validate raises a hard error
    that blocks soft-rule phase 2 from running).
    """
    font_part = f"\n        {font_line}" if font_line else ""
    size_part = f"\n        {font_size_line}" if font_size_line else ""
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
        text = "{_LONG_TEXT}"{font_part}{size_part}
        {widget_extra}
    """)


# ---------------------------------------------------------------------------
# Shared path fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def conf(tmp_path: Path):
    """Write a TOML string to a temp file and return its Path."""

    def _write(toml_str: str) -> Path:
        p = tmp_path / "config.toml"
        p.write_text(toml_str)
        return p

    return _write


# ===========================================================================
# Rule 62: generic animation duration vs hold
# ===========================================================================


async def test_rule62_fires_when_animation_exceeds_hold(
    conf, stub_propeller_registered
) -> None:
    """spin_seconds=5.0 > hold_time=2.0 → one rule-62 warning with both numbers."""
    toml = _toml(2.0, 'animation = {style = "teststub.propeller", spin_seconds = 5.0}')
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 62]
    assert len(issues) == 1, f"Expected 1 rule-62 warning, got: {result.warnings}"
    issue = issues[0]
    assert issue.severity == "warning"
    assert issue.location == "section[0].widget[0]"
    # Message must contain the computed duration ~5.0 s and the effective hold 2.0
    assert "~5.0" in issue.message, f"Expected '~5.0' in message: {issue.message}"
    assert "2.0" in issue.message, f"Expected '2.0' in message: {issue.message}"


async def test_rule62_no_fire_when_duration_le_hold(
    conf, stub_propeller_registered
) -> None:
    """spin_seconds=1.0 ≤ hold_time=3.0 → no rule-62 warning."""
    toml = _toml(3.0, 'animation = {style = "teststub.propeller", spin_seconds = 1.0}')
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 62]
    assert issues == [], f"Unexpected rule-62 warnings: {issues}"


async def test_rule62_excludes_typewriter(conf) -> None:
    """Typewriter is owned by rule 61 — rule 62 must not fire a duplicate.

    A long text on a short hold triggers rule 61. Rule 62 must not also
    fire for Typewriter (that would be a double-warning for the same cause).
    """
    # Long enough that Typewriter overruns hold_time=3.0
    toml = _toml(3.0, 'animation = "typewriter"')
    result = await validate_config(conf(toml))
    rule61 = [w for w in result.warnings if w.rule == 61]
    rule62 = [w for w in result.warnings if w.rule == 62]
    assert rule61, "Expected rule 61 to fire as a baseline"
    assert rule62 == [], f"Rule 62 must not duplicate rule 61 for Typewriter: {rule62}"


async def test_rule62_best_effort_unknown_animation_does_not_crash(conf) -> None:
    """Unknown animation 'flair.propeller' (not registered) → rules 62/63 skip.

    The unknown-style error from widget validation owns the messaging.
    The run must not crash. Some issue must mention the unknown animation
    (from the existing per-widget coercion error — not from rule 62).
    """
    toml = _toml(2.0, 'animation = "flair.propeller"')
    # Must not raise
    result = await validate_config(conf(toml))
    rule62 = [w for w in result.warnings if w.rule == 62]
    rule63 = [w for w in result.warnings if w.rule == 63]
    assert rule62 == [], f"Rule 62 must not fire for unknown animation: {rule62}"
    assert rule63 == [], f"Rule 63 must not fire for unknown animation: {rule63}"
    # Some error/warning should mention the unknown animation
    all_messages = [str(e) for e in result.errors] + [
        str(w.message) for w in result.warnings
    ]
    assert any("flair.propeller" in m for m in all_messages), (
        f"Expected 'flair.propeller' to appear somewhere in issues; got: {all_messages}"
    )


# ===========================================================================
# Rule 63: rotation-emitting animation on a hires font
# ===========================================================================


async def test_rule63_fires_for_rotation_animation_on_hires_font(
    conf, stub_propeller_registered
) -> None:
    """emits_rotation=True + hires font → rule-63 warning mentioning 'BDF'."""
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml(
        5.0,
        'animation = {style = "teststub.propeller", spin_seconds = 1.0}',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 63]
    assert len(issues) == 1, f"Expected 1 rule-63 warning, got: {result.warnings}"
    issue = issues[0]
    assert issue.severity == "warning"
    # "BDF" appears in the fix (switch to BDF font); message names the hires font
    assert "BDF" in issue.fix, f"Expected 'BDF' in fix: {issue.fix}"
    assert hires_name in issue.message, (
        f"Expected hires font name in message: {issue.message}"
    )


async def test_rule63_no_fire_bdf_font(conf, stub_propeller_registered) -> None:
    """emits_rotation=True + no font (default BDF) → no rule-63 warning."""
    toml = _toml(5.0, 'animation = {style = "teststub.propeller", spin_seconds = 1.0}')
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 63]
    assert issues == [], f"Unexpected rule-63 warnings: {issues}"


async def test_rule63_no_fire_typewriter_plus_hires(conf) -> None:
    """Typewriter has no emits_rotation → rule 63 must not fire even with hires font."""
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml(
        10.0,
        'animation = "typewriter"',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 63]
    assert issues == [], (
        f"Rule 63 must not fire for Typewriter (no emits_rotation): {issues}"
    )

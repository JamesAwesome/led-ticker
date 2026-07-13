"""Rules 62 + 63: animation duration vs hold, rotation on hires fonts.

Rule 62 — a non-Typewriter animation whose run time exceeds the effective
hold will be cut mid-animation (warning). Generalises rule 61's mechanism
via duck-typed ``frames_to_rest``.

Rule 63 — a rotation-emitting animation on a hires font: the spin silently
won't apply until physical-resolution rotation ships.

Rule 64 — a lens-emitting animation on a hires font: fisheye twin of rule
63. The raw-dict scan is type-agnostic (no ``type ==`` gate), so it already
fires equivalently for gif/image widgets as well as message — the gif/image
cases below pin that parity explicitly.

Rule 65 — a lens-emitting animation combined with a gif/image-only
conflict (``bottom_text`` set, non-center ``text_valign``, or
``text_wrap``). These are the same refusals `_BaseImageWidget._validate_common`
raises at widget construction time (Task 2); rule 65 is the config-load
raw-dict twin so `led-ticker validate` catches them before the app crashes
at startup (`_build_widget` constructs the widget; `validate_widget_cfg`
alone never does — see `docs/site` fisheye section for the user-facing
version). Message widgets have no `bottom_text`/`text_valign`/`text_wrap`
surface, so this rule is gif/image-only by construction (no twin needed on
message). The magnify × font-line-height fit check (`LensTextRenderer.draw`)
has NO config-load preflight for message either — draw-time only — so gif/
image intentionally matches that gap rather than inventing new preflight
surface for it.

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


class _StubFisheye:
    """Stands in for flair's Fisheye: lens-emitting, stateless."""

    restart_on_visit = False
    emits_lens = True

    def __init__(self, magnify: float = 1.3, edge_squeeze: float = 0.6) -> None:
        self.magnify = magnify
        self.edge_squeeze = edge_squeeze

    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(visible_text=full_text)


@pytest.fixture
def stub_fisheye_registered():
    _ANIMATION_REGISTRY["teststub.fisheye"] = _StubFisheye
    yield
    del _ANIMATION_REGISTRY["teststub.fisheye"]


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


async def test_rule62_widget_hold_rescues_short_section_hold(
    conf, stub_propeller_registered
) -> None:
    """effective hold is max(section, widget): a 5 s spin on a 2 s section
    does NOT fire when the widget's own hold_time is 8 s. Pins the max()
    at the rule-62 site directly — a min()/section-only mutation fails here."""
    toml = _toml(
        2.0,
        'animation = {style = "teststub.propeller", spin_seconds = 5.0}\n'
        "hold_time = 8.0",
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 62]
    assert issues == [], f"Unexpected rule-62 warnings: {issues}"


async def test_rule62_small_widget_hold_does_not_shrink_section_hold(
    conf, stub_propeller_registered
) -> None:
    """The mirror pin: a 5 s spin on an 8 s section does NOT fire even when
    the widget carries a smaller hold_time (1 s) — max(8, 1) = 8 governs."""
    toml = _toml(
        8.0,
        'animation = {style = "teststub.propeller", spin_seconds = 5.0}\n'
        "hold_time = 1.0",
    )
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


# ---------------------------------------------------------------------------
# Helpers for scale-aware rule-63 tests
# ---------------------------------------------------------------------------


def _toml_scaled(
    section_hold: float,
    widget_extra: str,
    font_line: str = "",
    font_size_line: str = "",
    display_scale: int = 1,
    section_scale: int | None = None,
) -> str:
    """TOML builder that accepts display-level and section-level scale overrides.

    ``section_scale`` inserts a ``scale = N`` key on the section block so
    we can test the per-section gate (config.py ~514 reads ``"scale"`` from
    the section table, defaulting to ``display.default_scale``).

    Panel rows is sized to ``content_height * display_scale`` (= 16 * scale)
    so that rule 1 (content_height × scale ≤ panel_h) never fires — that
    hard-error would suppress the phase-2 soft rules before rule 63 can run.
    """
    font_part = f"\n        {font_line}" if font_line else ""
    size_part = f"\n        {font_size_line}" if font_size_line else ""
    sec_scale_part = f"\nscale = {section_scale}" if section_scale is not None else ""
    # content_height defaults to 16; rows must be >= content_height * display_scale
    rows = 16 * display_scale
    return textwrap.dedent(f"""\
        [display]
        rows = {rows}
        cols = 64
        chain_length = 8
        default_scale = {display_scale}

        [[playlist.section]]
        mode = "slideshow"
        hold_time = {section_hold}{sec_scale_part}

        [[playlist.section.widget]]
        type = "message"
        text = "{_LONG_TEXT}"{font_part}{size_part}
        {widget_extra}
    """)


# ===========================================================================
# Rule 63: per-section scale gate
# ===========================================================================


async def test_rule63_no_fire_on_scaled_section(
    conf, stub_propeller_registered
) -> None:
    """default_scale=4 display + rotation stub + hires font → rule 63 silent.

    Hires fonts now rotate correctly on ScaledCanvas sections (Tasks 1–3),
    so the warning must be suppressed when section.scale != 1.
    """
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml_scaled(
        5.0,
        'animation = {style = "teststub.propeller", spin_seconds = 1.0}',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
        display_scale=4,
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 63]
    assert issues == [], (
        f"Rule 63 must not fire when section.scale=4 (hires fonts rotate on "
        f"ScaledCanvas); got: {issues}"
    )


async def test_rule63_fires_on_scale1_default(conf, stub_propeller_registered) -> None:
    """Scale-1 (default) + rotation stub + hires font → rule-63 fires.

    Pins the existing scale-1 behaviour explicitly alongside the new
    per-section-scale tests so a regression is immediately visible.
    """
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml_scaled(
        5.0,
        'animation = {style = "teststub.propeller", spin_seconds = 1.0}',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
        display_scale=1,  # explicit: default_scale = 1
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 63]
    assert len(issues) == 1, (
        f"Expected rule-63 warning on scale-1 section, got: {result.warnings}"
    )


async def test_rule63_fires_for_section_scale1_override_under_scaled_display(
    conf, stub_propeller_registered
) -> None:
    """Section-level scale=1 override under a default_scale=4 display → rule 63 fires.

    Even if the display default is 4, a section that explicitly sets ``scale = 1``
    gets a scale-1 ScaledCanvas; the hires font won't rotate there, so the
    warning must fire for that specific section.
    """
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml_scaled(
        5.0,
        'animation = {style = "teststub.propeller", spin_seconds = 1.0}',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
        display_scale=4,
        section_scale=1,  # explicit per-section override back to scale-1
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 63]
    assert len(issues) == 1, (
        f"Expected rule-63 warning for scale-1 section override under scale-4 display; "
        f"got: {result.warnings}"
    )


# ===========================================================================
# Rule 64: lens-emitting animation on a hires font (fisheye twin of rule 63)
# ===========================================================================


async def test_rule64_fires_for_lens_animation_on_hires_font(
    conf, stub_fisheye_registered
) -> None:
    """emits_lens=True + hires font at scale 1 → rule-64 warning."""
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml(
        5.0,
        'animation = {style = "teststub.fisheye", magnify = 1.3}',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 64]
    assert len(issues) == 1, f"Expected 1 rule-64 warning, got: {result.warnings}"
    issue = issues[0]
    assert issue.severity == "warning"
    assert issue.location == "section[0].widget[0]"
    assert hires_name in issue.message, (
        f"Expected hires font name in message: {issue.message}"
    )
    assert "BDF" in issue.fix, f"Expected 'BDF' in fix: {issue.fix}"


async def test_rule64_no_fire_bdf_font(conf, stub_fisheye_registered) -> None:
    """emits_lens=True + default BDF font → no rule-64 warning."""
    toml = _toml(5.0, 'animation = {style = "teststub.fisheye", magnify = 1.3}')
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 64]
    assert issues == [], f"Unexpected rule-64 warnings: {issues}"


async def test_rule64_no_fire_typewriter_plus_hires(conf) -> None:
    """Typewriter has no emits_lens → rule 64 must not fire with a hires font."""
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
    issues = [w for w in result.warnings if w.rule == 64]
    assert issues == [], (
        f"Rule 64 must not fire for Typewriter (no emits_lens): {issues}"
    )


async def test_rule64_no_fire_on_scaled_section(conf, stub_fisheye_registered) -> None:
    """default_scale=4 + lens stub + hires font → rule 64 silent (the lens
    warps hires fonts correctly on a ScaledCanvas section)."""
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml_scaled(
        5.0,
        'animation = {style = "teststub.fisheye", magnify = 1.3}',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
        display_scale=4,
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 64]
    assert issues == [], f"Rule 64 must not fire when section.scale=4; got: {issues}"


async def test_rule64_fires_on_scale1_default(conf, stub_fisheye_registered) -> None:
    """Scale-1 (default) + lens stub + hires font → rule-64 fires."""
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml_scaled(
        5.0,
        'animation = {style = "teststub.fisheye", magnify = 1.3}',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
        display_scale=1,
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 64]
    assert len(issues) == 1, (
        f"Expected rule-64 warning on scale-1 section, got: {result.warnings}"
    )


async def test_rule64_best_effort_unknown_animation_does_not_crash(conf) -> None:
    """Unknown animation 'flair.fisheye' (not registered) → rule 64 skips,
    no crash."""
    toml = _toml(5.0, 'animation = "flair.fisheye"')
    result = await validate_config(conf(toml))  # must not raise
    issues = [w for w in result.warnings if w.rule == 64]
    assert issues == [], f"Rule 64 must not fire for unknown animation: {issues}"


async def test_rule64_no_fire_without_animation(conf) -> None:
    """A hires-font widget with no animation → no rule-64 warning."""
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml(
        5.0,
        "",
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 64]
    assert issues == [], f"Unexpected rule-64 warnings without animation: {issues}"


# ===========================================================================
# Rule 64 parity: gif/image widgets (type-agnostic raw-dict scan)
# ===========================================================================


def _toml_image(
    widget_type: str,
    widget_extra: str,
    font_line: str = "",
    font_size_line: str = "",
) -> str:
    """TOML builder for a single-row gif/image widget (rule 64/65 parity
    tests). Mirrors ``_toml`` but for gif/image types — these widgets use
    unprefixed ``font``/``font_size`` (single-row text-overlay surface) same
    as message, so `_check_lens_hires_font`'s raw-dict scan applies unchanged.
    """
    font_part = f"\n        {font_line}" if font_line else ""
    size_part = f"\n        {font_size_line}" if font_size_line else ""
    path_line = 'path = "x.gif"' if widget_type == "gif" else 'path = "x.png"'
    return textwrap.dedent(f"""\
        [display]
        rows = 32
        cols = 64
        chain_length = 8
        default_scale = 1

        [[playlist.section]]
        mode = "slideshow"
        hold_time = 5.0

        [[playlist.section.widget]]
        type = "{widget_type}"
        {path_line}
        text = "Hi"{font_part}{size_part}
        {widget_extra}
    """)


@pytest.mark.parametrize("widget_type", ["gif", "image"])
async def test_rule64_fires_for_lens_animation_on_hires_font_image_widgets(
    conf, stub_fisheye_registered, widget_type
) -> None:
    """Parity: `_check_lens_hires_font` never gates on `type`, so a gif/image
    widget with a lens animation + hires font at scale 1 fires rule 64 the
    same as message does. No code change needed to make this pass — the
    raw-dict scan (`widget_cfg.get("animation")` / `widget_cfg.get("font")`)
    has no type check at all."""
    from led_ticker.fonts import list_available_hires_fonts

    hires_fonts = list_available_hires_fonts()
    if not hires_fonts:
        pytest.skip("No bundled hires fonts available in this environment")

    hires_name = hires_fonts[0]
    toml = _toml_image(
        widget_type,
        'animation = {style = "teststub.fisheye", magnify = 1.3}',
        font_line=f'font = "{hires_name}"',
        font_size_line="font_size = 12",
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 64]
    assert len(issues) == 1, (
        f"Expected 1 rule-64 warning for type={widget_type!r}, got: {result.warnings}"
    )
    assert hires_name in issues[0].message


@pytest.mark.parametrize("widget_type", ["gif", "image"])
async def test_rule64_no_fire_bdf_font_image_widgets(
    conf, stub_fisheye_registered, widget_type
) -> None:
    """Parity mirror: no hires font → no rule-64 warning on gif/image."""
    toml = _toml_image(
        widget_type, 'animation = {style = "teststub.fisheye", magnify = 1.3}'
    )
    result = await validate_config(conf(toml))
    issues = [w for w in result.warnings if w.rule == 64]
    assert issues == [], f"Unexpected rule-64 warnings: {issues}"


# ===========================================================================
# Rule 65: lens animation + gif/image-only structural conflicts
# ===========================================================================
#
# These mirror the refusals `_BaseImageWidget._validate_common` raises at
# widget construction time (bottom_text / non-center text_valign / text_wrap
# combined with a lens animation). `validate_widget_cfg` (what `led-ticker
# validate` runs) never constructs the widget — only `_build_widget` does —
# so without a dedicated raw-dict rule these mistakes pass static validation
# clean and only crash at real app startup. Rule 65 closes that gap, the
# same way rule 14 closes it for typewriter's own two-row/scroll refusals.


@pytest.mark.parametrize("widget_type", ["gif", "image"])
async def test_rule65_fires_for_lens_plus_bottom_text(
    conf, stub_fisheye_registered, widget_type
) -> None:
    toml = _toml_image(
        widget_type,
        'animation = {style = "teststub.fisheye", magnify = 1.3}\n'
        '        bottom_text = "there"',
    )
    result = await validate_config(conf(toml))
    issues = [e for e in result.errors if e.rule == 65]
    assert len(issues) == 1, f"Expected 1 rule-65 error, got: {result.errors}"
    assert "two-row" in issues[0].message
    assert issues[0].severity == "error"


@pytest.mark.parametrize("widget_type", ["gif", "image"])
async def test_rule65_fires_for_lens_plus_noncenter_valign(
    conf, stub_fisheye_registered, widget_type
) -> None:
    toml = _toml_image(
        widget_type,
        'animation = {style = "teststub.fisheye", magnify = 1.3}\n'
        '        text_valign = "top"',
    )
    result = await validate_config(conf(toml))
    issues = [e for e in result.errors if e.rule == 65]
    assert len(issues) == 1, f"Expected 1 rule-65 error, got: {result.errors}"
    assert "text_valign" in issues[0].message


@pytest.mark.parametrize("widget_type", ["gif", "image"])
async def test_rule65_fires_for_lens_plus_text_wrap(
    conf, stub_fisheye_registered, widget_type
) -> None:
    toml = _toml_image(
        widget_type,
        'animation = {style = "teststub.fisheye", magnify = 1.3}\n'
        "        text_wrap = true",
    )
    result = await validate_config(conf(toml))
    issues = [e for e in result.errors if e.rule == 65]
    assert len(issues) == 1, f"Expected 1 rule-65 error, got: {result.errors}"
    assert "text_wrap" in issues[0].message


@pytest.mark.parametrize("widget_type", ["gif", "image"])
async def test_rule65_no_fire_for_clean_lens_config(
    conf, stub_fisheye_registered, widget_type
) -> None:
    """A lens animation with none of the conflicting fields → no rule 65."""
    toml = _toml_image(
        widget_type,
        'animation = {style = "teststub.fisheye", magnify = 1.3}\n'
        '        text_align = "scroll_over"',
    )
    result = await validate_config(conf(toml))
    issues = [e for e in result.errors if e.rule == 65]
    assert issues == [], f"Unexpected rule-65 errors: {issues}"


@pytest.mark.parametrize("widget_type", ["gif", "image"])
async def test_rule65_no_fire_for_typewriter_plus_bottom_text(
    conf, widget_type
) -> None:
    """Typewriter has no emits_lens — its own two-row conflict is rule 14's
    territory, not rule 65's. (Rule 14 only string-matches the bare
    ``animation = "typewriter"`` form, so use that form here.)"""
    toml = _toml_image(
        widget_type, 'animation = "typewriter"\n        bottom_text = "there"'
    )
    result = await validate_config(conf(toml))
    rule14 = [e for e in result.errors if e.rule == 14]
    rule65 = [e for e in result.errors if e.rule == 65]
    assert rule14, "Expected rule 14 to fire as a baseline"
    assert rule65 == [], f"Rule 65 must not duplicate rule 14: {rule65}"


async def test_rule65_no_fire_for_message_widget(conf, stub_fisheye_registered) -> None:
    """Message widgets have no bottom_text/text_valign/text_wrap surface —
    rule 65 is gif/image-only by construction; confirm it never fires for
    type='message' even given a lens animation."""
    toml = _toml(5.0, 'animation = {style = "teststub.fisheye", magnify = 1.3}')
    result = await validate_config(conf(toml))
    issues = [e for e in result.errors if e.rule == 65]
    assert issues == [], f"Rule 65 must not fire for message widgets: {issues}"


@pytest.mark.parametrize("widget_type", ["gif", "image"])
async def test_rule65_best_effort_unknown_animation_does_not_crash(
    conf, widget_type
) -> None:
    """Unknown animation (plugin not installed) → rule 65 skips, no crash."""
    toml = _toml_image(
        widget_type, 'animation = "flair.fisheye"\n        bottom_text = "there"'
    )
    result = await validate_config(conf(toml))  # must not raise
    issues = [e for e in result.errors if e.rule == 65]
    assert issues == [], f"Rule 65 must not fire for unknown animation: {issues}"

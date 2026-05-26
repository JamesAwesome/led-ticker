import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from led_ticker.app.factories import validate_widget_cfg
from led_ticker.validate import ValidationIssue, ValidationResult, validate_config


def test_valid_when_no_errors():
    r = ValidationResult(path=Path("x.toml"), errors=[], warnings=[])
    assert r.valid is True


def test_invalid_when_errors_present():
    issue = ValidationIssue(
        rule=1, location="section[0]", message="bad", fix="fix it", severity="error"
    )
    r = ValidationResult(path=Path("x.toml"), errors=[issue], warnings=[])
    assert r.valid is False


def test_valid_with_only_warnings():
    w = ValidationIssue(
        rule=21,
        location="section[0]",
        message="slow",
        fix="speed up",
        severity="warning",
    )
    r = ValidationResult(path=Path("x.toml"), errors=[], warnings=[w])
    assert r.valid is True


async def test_validate_widget_cfg_returns_none_for_valid_widget():
    cfg = {"type": "message", "text": "hello"}
    result = await validate_widget_cfg(cfg, session=None)
    assert result is None


async def test_validate_widget_cfg_raises_on_text_scale():
    from led_ticker.validate import MigrationError

    cfg = {"type": "message", "text": "hi", "text_scale": 2}
    with pytest.raises(MigrationError, match="text_scale"):
        await validate_widget_cfg(cfg, session=None)


async def test_validate_widget_cfg_raises_on_animation_wrong_type():
    cfg = {"type": "weather", "location": "NYC", "animation": "typewriter"}
    with pytest.raises(ValueError, match="animation is only valid"):
        await validate_widget_cfg(cfg, session=None)


@pytest.mark.asyncio
async def test_validate_widget_cfg_rss_feed_font_fields_do_not_crash():
    """font/font_size/font_threshold on rss_feed must not raise 'unknown field'.

    Regression for: _resolve_fonts unconditionally re-inserted the resolved
    font object even for widgets without a `font` attrs field.
    """
    cfg = {
        "type": "rss_feed",
        "feed_url": "https://example.com/rss",
        "font": "Inter-Regular",
        "font_size": 16,
        "font_threshold": 80,
    }
    # Should not raise; font fields are consumed by _resolve_fonts.
    result = await validate_widget_cfg(cfg, session=None)
    assert result is None


@pytest.fixture
def conf(tmp_path):
    """Write a TOML string to a temp file and return its Path."""

    def _write(toml_str: str) -> Path:
        p = tmp_path / "config.toml"
        p.write_text(textwrap.dedent(toml_str))
        return p

    return _write


GOOD_CONFIG = """\
    [display]
    rows = 32
    cols = 64
    chain = 8
    default_scale = 1

    [[playlist.section]]
    mode = "swap"
    hold_time = 3

    [[playlist.section.widget]]
    type = "message"
    text = "hello"
    """


async def test_happy_path_returns_valid(conf):
    result = await validate_config(conf(GOOD_CONFIG))
    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


async def test_toml_syntax_error_returns_error(conf):
    result = await validate_config(conf("[display\n"))
    assert not result.valid
    assert len(result.errors) == 1
    assert result.errors[0].location == "config"


async def test_unknown_widget_type_returns_error(conf):
    result = await validate_config(
        conf(GOOD_CONFIG + '\n[[playlist.section.widget]]\ntype = "banana"\n')
    )
    assert not result.valid
    assert any("section[0].widget[1]" in e.location for e in result.errors)


async def test_text_scale_migration_error(conf):
    cfg = GOOD_CONFIG.replace('text = "hello"', 'text = "hello"\ntext_scale = 2')
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 20 for e in result.errors)


async def test_animation_on_wrong_widget_type(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "weather"
        location = "NYC"
        animation = "typewriter"
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 12 for e in result.errors)


async def test_border_on_wrong_widget_type(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "weather"
        location = "NYC"
        border = "rainbow"
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 15 for e in result.errors)


async def test_rule3_scroll_plus_stretch(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "image"
        path = "x.png"
        text_align = "scroll"
        fit = "stretch"
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 3 for e in result.errors)


async def test_rule24_missing_font_is_warning_not_error(conf):
    # A font that doesn't exist in the bundle or in config/fonts/ used to
    # hard-error. The validator now downgrades this to a warning so a
    # config can be drafted on a machine that doesn't have the font yet,
    # and shipped to a sign that does.
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        font = "Some-Brand-Font"
        font_size = 24
        """
    result = await validate_config(conf(cfg))
    assert result.valid is True  # warnings allowed; CLI exits 0
    assert any(w.rule == 24 for w in result.warnings), (
        f"expected rule 24 warning; got {[w.rule for w in result.warnings]}; "
        f"errors: {[(e.rule, e.message) for e in result.errors]}"
    )
    # Existing rule 5 message ("font requires font_size") and BDF size
    # errors stay as ERRORS — they're real config bugs, not asset gaps.
    assert all(e.rule != 24 for e in result.errors)


async def test_rule5_missing_font_size_still_hard_errors(conf):
    # Sibling check: `font = "Inter-Bold"` without `font_size` is still
    # a hard error (rule 5), not a warning. The new rule-24 path is
    # specific to "font name not resolved".
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        font = "Inter-Bold"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 5 for e in result.errors)


async def test_rule3_scroll_over_plus_stretch_is_allowed(conf):
    # `scroll_over` paints text ON TOP of the image — opaque `stretch`
    # is the intended pairing. The runtime widget accepts this combo;
    # the validator must not flag it.
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "image"
        path = "x.png"
        text = "marquee"
        text_align = "scroll_over"
        fit = "stretch"
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert all(e.rule != 3 for e in result.errors), (
        f"scroll_over + stretch is valid; got errors: "
        f"{[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule7_text_x_offset_with_scroll(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "image"
        path = "x.png"
        text_align = "scroll"
        text_x_offset = 5
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 7 for e in result.errors)


async def test_rule8_hold_seconds_too_short(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "image"
        path = "x.png"
        hold_seconds = 0.001
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 8 for e in result.errors)


async def test_rule14_typewriter_on_gif_two_row(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        animation = "typewriter"
        bottom_text = "hello"
        text = "world"
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 14 for e in result.errors)


async def test_rule14_typewriter_on_gif_single_row_ok(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        animation = "typewriter"
        text = "world"
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    # single-row with non-empty text — typewriter is allowed on gif
    assert all(e.rule != 14 for e in result.errors)


async def test_missing_config_file_raises():
    with pytest.raises(FileNotFoundError):
        await validate_config(Path("/tmp/does_not_exist_xyz.toml"))


async def test_rule1_content_height_overflow(conf):
    # panel_h=32*1=32; content_height=20 × scale=1=20 ≤ 32 — no overflow at scale=1
    # Use scale=4 explicitly: 20 * 4 = 80 > 32 → triggers rule 1 (promoted to error)
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 4

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        content_height = 20

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert result.valid is False  # now an error, not a warning
    assert any(e.rule == 1 for e in result.errors)
    assert all(w.rule != 1 for w in result.warnings)


async def test_rule1_no_warning_when_within_limits(conf):
    # scale=1, content_height=16: 16 * 1 = 16 ≤ 32 — no overflow
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 1 for w in result.warnings)


async def test_rule1_does_not_fire_at_exact_boundary(conf):
    """Rule 1 uses strict `>` — equality is fine, only exceedance is an
    error. Boundary test: content_height × scale == panel_h_real should
    NOT fire (the panel exactly fits)."""
    # panel_h = rows * parallel = 32 * 1 = 32; content_height=8, scale=4
    # → 8 × 4 = 32 = panel_h. Boundary case.
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 4

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        content_height = 8

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 1 for e in result.errors), (
        f"rule 1 must not fire at exact boundary; "
        f"got {[(e.rule, e.message) for e in result.errors]}"
    )
    assert all(w.rule != 1 for w in result.warnings)


async def test_rule2_font_threshold_mismatch(conf):
    cfg = GOOD_CONFIG + textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "message"
        text = "bold"
        font = "Inter-Bold"
        font_size = 24
        font_threshold = 128

        [[playlist.section.widget]]
        type = "message"
        text = "regular"
        font = "Inter-Regular"
        font_size = 24
        font_threshold = 80
        """)
    result = await validate_config(conf(cfg))
    assert any(w.rule == 2 for w in result.warnings)


async def test_rule2_no_warning_when_thresholds_match(conf):
    cfg = GOOD_CONFIG + textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "message"
        text = "bold"
        font = "Inter-Bold"
        font_size = 24
        font_threshold = 80

        [[playlist.section.widget]]
        type = "message"
        text = "regular"
        font = "Inter-Regular"
        font_size = 24
        font_threshold = 80
        """)
    result = await validate_config(conf(cfg))
    assert all(w.rule != 2 for w in result.warnings)


async def test_rule6_two_row_at_scale4(conf):
    # Bigsign config: pixel_mapper gives panel_h_real=64; scale=4 × content_height=16
    # = 64 ≤ 64 — no rule 1 error, so soft warnings can surface.
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 4
        pixel_mapper = "Remap:256,64|U-mapper"

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        scale = 4

        [[playlist.section.widget]]
        type = "message"
        text = "hello"

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "@handle"
        bottom_text = "promo"
        """
    result = await validate_config(conf(cfg))
    assert any(w.rule == 6 for w in result.warnings)


async def test_rule21_duration_too_large(conf):
    cfg = GOOD_CONFIG.replace(
        "[[playlist.section]]",
        "[[playlist.section]]\ntransition_duration = 500.0\n",
    )
    result = await validate_config(conf(cfg))
    assert any(w.rule == 21 for w in result.warnings)


async def test_rule21_duration_too_small(conf):
    cfg = GOOD_CONFIG.replace(
        "[[playlist.section]]",
        "[[playlist.section]]\ntransition_duration = 0.001\n",
    )
    result = await validate_config(conf(cfg))
    assert any(w.rule == 21 for w in result.warnings)


async def test_rule21_normal_duration_no_warning(conf):
    # default transition.duration is 0.5 — no warning
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 21 for w in result.warnings)


async def test_json_output_valid_config(conf):
    from led_ticker.validate import _format_json

    path = conf(GOOD_CONFIG)
    result = await validate_config(path)
    data = json.loads(_format_json(result))
    assert data["valid"] is True
    assert data["errors"] == []
    assert data["warnings"] == []
    assert data["path"] == str(path)


def test_json_output_with_error():
    from led_ticker.validate import _format_json

    issue = ValidationIssue(
        rule=5,
        location="section[0].widget[0]",
        message="bad",
        fix="fix",
        severity="error",
    )
    result = ValidationResult(path=Path("x.toml"), errors=[issue], warnings=[])
    data = json.loads(_format_json(result))
    assert data["valid"] is False
    assert len(data["errors"]) == 1
    assert data["errors"][0]["rule"] == 5
    assert data["errors"][0]["location"] == "section[0].widget[0]"
    assert data["errors"][0]["message"] == "bad"
    assert data["errors"][0]["fix"] == "fix"


@pytest.mark.slow
def test_validate_cli_smoke_subprocess(conf):
    """End-to-end smoke: the CLI binary exits 0 on a valid config."""
    import shutil

    if not shutil.which("uv"):
        pytest.skip("uv not in PATH")
    path = conf(GOOD_CONFIG)
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0


async def test_cli_exit_code_0_on_valid(conf):
    """Valid config produces a valid result (exit 0 equivalent)."""
    result = await validate_config(conf(GOOD_CONFIG))
    assert result.valid is True


async def test_cli_exit_code_1_on_error(conf):
    """Config with unknown widget type produces an error (exit 1 equivalent)."""
    path = conf(GOOD_CONFIG + '\n[[playlist.section.widget]]\ntype = "banana"\n')
    result = await validate_config(path)
    assert result.valid is False


async def test_cli_exit_code_2_on_missing_file(tmp_path):
    """Missing config file raises FileNotFoundError (exit 2 equivalent)."""
    with pytest.raises(FileNotFoundError):
        await validate_config(tmp_path / "missing.toml")


async def test_cli_json_flag_produces_parseable_output(conf):
    """_format_json produces valid JSON with a 'valid' key."""
    from led_ticker.validate import _format_json

    result = await validate_config(conf(GOOD_CONFIG))
    assert result.valid is True
    data = json.loads(_format_json(result))
    assert data["valid"] is True


def test_format_human_output():
    from led_ticker.validate import _format_human

    err = ValidationIssue(
        rule=5,
        location="section[0].widget[0]",
        message="bad font",
        fix="add font_size",
        severity="error",
    )
    warn = ValidationIssue(
        rule=21,
        location="section[0]",
        message="500s duration",
        fix="divide by 1000",
        severity="warning",
    )
    result = ValidationResult(path=Path("x.toml"), errors=[err], warnings=[warn])
    output = _format_human(result)
    assert "✗ ERROR" in output
    assert "⚠ WARNING" in output
    assert "bad font" in output
    assert "divide by 1000" in output
    assert "2 issue(s)" in output
    # Rule numbers are internal — they stay on the JSON output (programmatic
    # consumers like the creating-a-config skill use them) but don't surface
    # in the human-readable text output. Make sure we don't regress to
    # printing them.
    assert "[rule" not in output
    assert "rule 5" not in output


async def test_rule14_typewriter_on_gif_scroll_align(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        animation = "typewriter"
        text = "world"
        text_align = "scroll"
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 14 for e in result.errors)


async def test_rule23_two_row_top_text_overflows(conf):
    # Smallsign 160-wide, scale=1: FONT_SMALL (5px advance) × 33 'M' = 165
    # logical → 5px overflow. Held top row clips silently — warn.
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM"
        bottom_text = "scrolls fine"
        """
    result = await validate_config(conf(cfg))
    assert result.valid is True  # warning, not error
    assert any(
        w.rule == 23 for w in result.warnings
    ), f"expected rule 23 warning; got {[w.rule for w in result.warnings]}"


async def test_rule23_two_row_top_text_fits(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "fits fine"
        bottom_text = "ok"
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 23 for w in result.warnings)


async def test_rule23_two_row_at_scale2_bigsign_clip(conf):
    # Bigsign 256×64 real, section scale=2, content_height=32 →
    # logical 128×32. FONT_SMALL (5px) × 30 'M' = 150 logical, canvas 128 → 22 overflow.
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 4
        pixel_mapper = "Remap:256,64|U-mapper"

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        scale = 2
        content_height = 32

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "MMMMMMMMMMMMMMMMMMMMMMMMMMMMMM"
        bottom_text = "scrolls"
        """
    result = await validate_config(conf(cfg))
    assert any(
        w.rule == 23 for w in result.warnings
    ), f"expected rule 23 warning; got {[w.rule for w in result.warnings]}"


async def test_rule23_gif_with_bottom_text_overflows(conf):
    # gif + bottom_text → two-row mode, top is held. Use font=5x8 so
    # the line-height fits the 8-tall band (otherwise rule 22 fires and
    # suppresses warnings). 5×33 = 165 > 160 canvas → overflow.
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        top_font = "5x8"
        bottom_font = "5x8"
        top_text = "MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM"
        bottom_text = "scrolls"
        """
    result = await validate_config(conf(cfg))
    assert any(w.rule == 23 for w in result.warnings), (
        f"expected rule 23 warning; got {[w.rule for w in result.warnings]}; "
        f"errors: {[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule23_image_with_bottom_text_overflows(conf):
    # Same as gif case but for the image widget.
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "image"
        path = "x.png"
        top_font = "5x8"
        bottom_font = "5x8"
        top_text = "MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM"
        bottom_text = "scrolls"
        """
    result = await validate_config(conf(cfg))
    assert any(w.rule == 23 for w in result.warnings), (
        f"expected rule 23 warning; got {[w.rule for w in result.warnings]}; "
        f"errors: {[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule23_gif_single_row_does_not_warn(conf):
    # No bottom_text → single-row mode. The top text would scroll, not clip.
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        text = "MMMMMMMMMMMMMMMMMMMMMMMMMMM"
        text_align = "scroll"
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 23 for w in result.warnings)


async def test_rule23_message_widget_does_not_warn(conf):
    # message widget scrolls on overflow — rule 23 is two-row only.
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "message"
        text = "MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM"
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 23 for w in result.warnings)


async def test_rule14_typewriter_on_gif_empty_text(conf):
    extra = textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        animation = "typewriter"
        text = ""
        """)
    result = await validate_config(conf(GOOD_CONFIG + extra))
    assert not result.valid
    assert any(e.rule == 14 for e in result.errors)


# Rule 22: per-row band-layout — fonts must fit their row band.
# Catches at config-load what previously only fired at first draw.

_BIGSIGN_CONFIG = """\
    [display]
    rows = 64
    cols = 256
    chain = 1
    default_scale = 4
    """


async def test_rule22_two_row_inter_bold_too_tall_for_band(conf):
    """At scale=2, content_height=16 → per-row band = 8 logical.
    Inter-Bold@18 has line_height = 12 logical (23 real / 2). Doesn't fit.
    Same shape as the bug found in two_row-font-hierarchy.toml."""
    extra = textwrap.dedent("""\

        [[playlist.section]]
        mode = "swap"
        scale = 2
        content_height = 16
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "@hi"
        top_font = "Inter-Bold"
        top_font_size = 18
        bottom_text = "world"
        """)
    result = await validate_config(conf(_BIGSIGN_CONFIG + extra))
    assert not result.valid, "config-load validate should catch font-too-tall"
    assert any(
        e.rule == 22 for e in result.errors
    ), f"expected rule=22 in {[(e.rule, e.message) for e in result.errors]}"


async def test_rule22_image_two_row_default_font_too_tall(conf):
    """Image/gif two-row mode: default font is FONT_DEFAULT (6x12 = 12
    logical). Doesn't fit an 8-logical band on smallsign at scale=1
    + content_height=16. Catches the same shape against image widgets."""
    smallsign = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1
        """)
    extra = textwrap.dedent("""\

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "image"
        path = "x.png"
        top_text = "hi"
        bottom_text = "world"
        """)
    result = await validate_config(conf(smallsign + extra))
    assert not result.valid
    assert any(e.rule == 22 for e in result.errors)


async def test_rule22_passes_when_band_fits(conf):
    """Inverse: 5x8 BDF on a content_height=16 50/50 split fits
    exactly (line_height=8 logical, band=8). No issue raised."""
    extra = textwrap.dedent("""\

        [[playlist.section]]
        mode = "swap"
        scale = 2
        content_height = 16
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "@hi"
        bottom_text = "world"
        """)
    result = await validate_config(conf(_BIGSIGN_CONFIG + extra))
    assert (
        result.valid
    ), f"5x8 BDF should fit; got: {[(e.rule, e.message) for e in result.errors]}"


async def test_rule25_start_hold_on_swap_section_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(
        e.rule == 25 for e in result.errors
    ), f"expected rule 25 error; got {[(e.rule, e.message) for e in result.errors]}"


async def test_rule25_start_hold_on_gif_section_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "gif"
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 25 for e in result.errors)


async def test_rule25_start_hold_on_forever_scroll_is_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 25 for e in result.errors), (
        f"start_hold on forever_scroll must validate clean; got errors: "
        f"{[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule25_start_hold_on_infini_scroll_is_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "infini_scroll"
        start_hold = 2.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 25 for e in result.errors)


async def test_rule25_negative_start_hold_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = -1.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 25 for e in result.errors)


async def test_rule25_zero_start_hold_is_allowed(conf):
    # Exact zero is the load-bearing case for the whole feature — must NOT trip
    # the negative-value error path.
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert result.valid is True
    assert all(e.rule != 25 for e in result.errors)


async def test_rule26_separator_on_swap_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        separator = "*"

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)


async def test_rule26_separator_on_gif_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "gif"
        separator = "*"

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)


async def test_rule26_separator_on_infini_scroll_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "infini_scroll"
        separator = "*"

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)


async def test_rule26_separator_on_forever_scroll_is_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        separator = "*"
        separator_color = [225, 48, 108]

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 26 for e in result.errors)


async def test_rule26_separator_font_alone_on_swap_errors(conf):
    """Rule 26 fires on ANY of the four fields, not just `separator`."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        separator_font = "Inter-Bold"

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)


async def test_rule24_separator_font_missing_emits_warning(conf):
    """A separator_font that isn't bundled / in config/fonts/ must flow
    through rule 24 (warning) — same treatment as widget fonts.
    """
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        separator_font = "Some-Custom-Font"
        separator_font_size = 24

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    # Warnings allowed → result.valid is True
    assert result.valid is True
    assert any(w.rule == 24 for w in result.warnings), (
        f"expected rule 24 warning for unknown separator_font; got "
        f"warnings={[w.rule for w in result.warnings]}, "
        f"errors={[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule28_bottom_text_loops_without_wrap_errors(conf):
    """bottom_text_loops > 0 requires bottom_text_wrap=True."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        bottom_text_loops = 4
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 28 and "wrap" in e.message.lower() for e in result.errors), (
        f"expected rule 28 error about wrap; "
        f"got {[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule28_bottom_text_loops_negative_errors(conf):
    """bottom_text_loops < 0 is always an error."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        bottom_text_loops = -1
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 28 and ">=" in e.message for e in result.errors), (
        f"expected rule 28 error about >= 0; "
        f"got {[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule28_bottom_text_loops_with_wrap_is_allowed(conf):
    """bottom_text_loops > 0 with bottom_text_wrap=True is allowed."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        bottom_text_wrap = true
        bottom_text_loops = 4
        """
    result = await validate_config(conf(cfg))
    rule_28_errors = [e for e in result.errors if e.rule == 28]
    assert (
        not rule_28_errors
    ), f"expected no rule 28 error with wrap enabled; got {rule_28_errors}"


async def test_rule28_bottom_text_loops_zero_is_allowed(conf):
    """bottom_text_loops = 0 (default) is always allowed."""
    cfg = GOOD_CONFIG + textwrap.dedent("""\

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        bottom_text_loops = 0
        """)
    result = await validate_config(conf(cfg))
    assert result.valid is True


async def test_rule28_bottom_text_loops_bool_errors(conf):
    """bool is an int subclass — without an explicit guard, `true`/`false`
    would silently behave as 1/0. Validator rejects to surface the typo."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        bottom_text_wrap = true
        bottom_text_loops = true
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 28 and "bool" in e.message.lower() for e in result.errors), (
        f"expected rule 28 bool error; got "
        f"{[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule29_text_loops_on_two_row_is_did_you_mean_bridge(conf):
    """The image-widget field `text_loops` is a common copy-paste typo on
    two_row. Rule 29 surfaces it with a "did you mean bottom_text_loops?"
    hint instead of letting it slip through to a runtime TypeError."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        text_loops = 4
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(
        e.rule == 29 and "bottom_text_loops" in e.message for e in result.errors
    ), (
        f"expected rule 29 did-you-mean error; got "
        f"{[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule29_text_loops_on_gif_widget_does_not_fire(conf):
    """Rule 29 is two_row-specific. `text_loops` on a gif widget is
    a legitimate field — must not trigger the bridge."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        text = "marquee"
        text_align = "scroll_over"
        text_loops = 4
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 29 for e in result.errors), (
        f"rule 29 must not fire for gif widgets; got "
        f"{[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule30_hold_time_plus_bottom_text_loops_warns(conf):
    """When hold_time is EXPLICITLY set alongside bottom_text_loops > 0
    on a two_row widget, surface a warning that the two interact via
    max() — whichever produces more ticks wins, and the other is
    silently ignored. Common confusion: user sets loops=3 expecting
    exact-3-loops, doesn't realize their hold_time can override it."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 8.0

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        bottom_text_wrap = true
        bottom_text_loops = 3
        """
    result = await validate_config(conf(cfg))
    # Warning, not error: config is valid; user just gets a heads-up.
    assert result.valid is True
    assert any(w.rule == 30 for w in result.warnings), (
        f"expected rule 30 warning; got "
        f"warnings={[(w.rule, w.message) for w in result.warnings]}"
    )


async def test_rule30_does_not_fire_on_gif_widget(conf):
    """Rule 30 is scoped to `two_row` ONLY. On gif/image widgets the
    `text_loops` field controls marquee traversal count INSIDE the
    widget's own `play()` loop — it interacts with the gif's own
    timing logic, not with `hold_time` directly. A warning here would
    be misleading."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 8.0

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        text = "marquee"
        text_align = "scroll_over"
        text_loops = 3
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 30 for w in result.warnings), (
        "rule 30 must not fire on gif "
        f"(text_loops is a marquee knob, not a hold_time interaction); "
        f"got warnings={[(w.rule, w.message) for w in result.warnings]}"
    )


async def test_rule30_default_hold_time_does_not_warn(conf):
    """The default hold_time = 3.0 (when user omits it from TOML)
    must NOT trip rule 30 — only EXPLICITLY-set hold_time counts.
    Otherwise every section that uses bottom_text_loops would warn,
    contradicting the tutorial's "omit hold_time for exact loops"
    pattern."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        bottom_text_wrap = true
        bottom_text_loops = 3
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 30 for w in result.warnings), (
        f"rule 30 must not fire when hold_time is at its default; "
        f"got warnings={[(w.rule, w.message) for w in result.warnings]}"
    )


async def test_rule30_hold_time_alone_does_not_warn(conf):
    """hold_time without any loop count is fine — that's the
    default swap-mode pattern from before this PR."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 8.0

        [[playlist.section.widget]]
        type = "two_row"
        top_text = "TOP"
        bottom_text = "marquee"
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 30 for w in result.warnings)


async def test_rule31_scroll_step_ms_zero_errors(conf):
    """scroll_step_ms = 0 would ZeroDivisionError at startup
    (ticker.py:_swap_and_scroll divides by it). Reject at validate time."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        scroll_step_ms = 0

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 31 for e in result.errors), (
        f"expected rule 31 error; got "
        f"{[(e.rule, e.message) for e in result.errors]}"
    )


async def test_rule31_scroll_step_ms_negative_errors(conf):
    """Negative scroll_step_ms is nonsensical. Reject."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        scroll_step_ms = -10

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 31 for e in result.errors)


async def test_rule31_scroll_step_ms_omitted_is_allowed(conf):
    """Default (None / unset) inherits the engine default; no error."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 31 for e in result.errors)


async def test_rule31_scroll_step_ms_positive_is_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        scroll_step_ms = 35

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 31 for e in result.errors)


async def test_rule34a_scroll_speed_ms_at_section_level_errors(conf):
    """scroll_speed_ms is a widget-level field. At section level it is
    silently ignored. The validator catches it and points at scroll_step_ms."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        scroll_speed_ms = 40

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(
        e.rule == 34 and "scroll_speed_ms" in e.location for e in result.errors
    ), (
        f"expected rule 34 error at section.scroll_speed_ms; "
        f"got {[(e.rule, e.location, e.message) for e in result.errors]}"
    )


async def test_rule34b_scroll_step_ms_on_gif_widget_errors(conf):
    """scroll_step_ms on a gif widget would be passed as an unknown kwarg and
    crash at startup. The validator catches it and points at scroll_speed_ms."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        text = "marquee"
        text_align = "scroll_over"
        scroll_step_ms = 40
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(
        e.rule == 34 and "scroll_step_ms" in e.location for e in result.errors
    ), (
        f"expected rule 34 error at widget.scroll_step_ms; "
        f"got {[(e.rule, e.location, e.message) for e in result.errors]}"
    )


async def test_rule34b_scroll_step_ms_on_image_widget_errors(conf):
    """Same as gif case but for the image widget type."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "image"
        path = "x.png"
        text = "caption"
        scroll_step_ms = 40
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(
        e.rule == 34 and "scroll_step_ms" in e.location for e in result.errors
    ), (
        f"expected rule 34 error at widget.scroll_step_ms; "
        f"got {[(e.rule, e.location, e.message) for e in result.errors]}"
    )


async def test_rule34_scroll_step_ms_on_message_widget_does_not_fire(conf):
    """Rule 34b is scoped to gif/image only — those are the widget types that
    have a scroll_speed_ms to be confused with. A message widget with
    scroll_step_ms is a different kind of error (unknown kwarg, deferred),
    not a cross-scope confusion."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        scroll_step_ms = 40
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 34 for e in result.errors), (
        f"rule 34 must not fire for message widgets; "
        f"got {[(e.rule, e.location) for e in result.errors]}"
    )


async def test_rule33_mode_gif_warns(conf):
    """mode='gif' is the legacy dedicated-gif section mode. The validator
    surfaces a warning so authors know to migrate to mode='swap' + gif
    widget, which gives access to the full section feature set."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "gif"

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        """
    result = await validate_config(conf(cfg))
    # Warning only — the config is still valid; ticker can start.
    assert result.valid is True
    assert any(
        w.rule == 33 for w in result.warnings
    ), f"expected rule 33 warning; got warnings={[w.rule for w in result.warnings]}"


async def test_rule33_mode_swap_does_not_warn(conf):
    """mode='swap' is the recommended pattern — must not trip rule 33."""
    result = await validate_config(conf(GOOD_CONFIG))
    assert all(w.rule != 33 for w in result.warnings)


async def test_rule36_gif_loops_zero_in_mode_gif_warns(conf):
    """play_count = 0 in mode = "gif" silently plays 1 loop (legacy path
    doesn't thread hold_time). Surface as a warning so the user knows
    the semantics don't propagate from mode='swap'."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "gif"
        hold_time = 8.0

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        play_count = 0
        """
    result = await validate_config(conf(cfg))
    # Rule 33 also fires (mode='gif' legacy) — that's expected. We just
    # need rule 36 in there too.
    assert any(w.rule == 36 for w in result.warnings), (
        f"expected rule 36 warning; got "
        f"{[(w.rule, w.message) for w in result.warnings]}"
    )


async def test_rule36_gif_loops_zero_in_mode_swap_does_not_warn(conf):
    """In mode='swap' the semantics ARE plumbed through — no warning."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 8.0

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        play_count = 0
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 36 for w in result.warnings)


async def test_rule36_gif_loops_positive_in_mode_gif_does_not_warn(conf):
    """play_count = 5 (or any positive int) plays as a fixed count
    regardless of mode — no warning needed."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "gif"

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        play_count = 5
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 36 for w in result.warnings)


async def test_rule35_default_inside_section_warns(conf):
    """`default = '...'` written inside a [[playlist.section]] block is
    silently ignored — it's a [transitions] key. The validator surfaces
    this so the user knows to rename it to `transition = '...'`."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        default = "wipe_left"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    # Warning only — the config is valid; ticker can start.
    assert result.valid is True
    assert any(
        w.rule == 35 for w in result.warnings
    ), f"expected rule 35 warning; got warnings={[w.rule for w in result.warnings]}"


async def test_rule35_default_in_transitions_block_does_not_warn(conf):
    """`[transitions] default = '...'` is the legit global-default syntax.
    Rule 35 must NOT fire here."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [transitions]
        default = "wipe_left"

        [[playlist.section]]
        mode = "swap"
        hold_time = 3

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """
    result = await validate_config(conf(cfg))
    assert all(w.rule != 35 for w in result.warnings), (
        f"rule 35 must not fire for [transitions] default; "
        f"got warnings={[(w.rule, w.location) for w in result.warnings]}"
    )


class TestRule27WrapsForeverModeOnly:
    """bottom_text_wrap=True is only valid in mode=swap. Refused
    in forever_scroll and infini_scroll because the widget would
    block the chain (wraps_forever never terminates on cursor_pos)."""

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_in_forever_scroll_rejected(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_wrap = true
""")
        from led_ticker.validate import validate_config

        result = await validate_config(cfg)
        assert any(
            issue.rule == 27 and "bottom_text_wrap" in issue.message
            for issue in result.errors
        ), f"Expected rule 27 error; got errors={result.errors}"

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_in_infini_scroll_rejected(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "infini_scroll"

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_wrap = true
""")
        from led_ticker.validate import validate_config

        result = await validate_config(cfg)
        assert any(
            issue.rule == 27 and "bottom_text_wrap" in issue.message
            for issue in result.errors
        ), f"Expected rule 27 error; got errors={result.errors}"

    @pytest.mark.asyncio
    async def test_bottom_text_wrap_in_swap_accepted(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 5

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_wrap = true
""")
        from led_ticker.validate import validate_config

        result = await validate_config(cfg)
        # Confirm no rule-27 error (other errors irrelevant for this test).
        rule_27_errors = [e for e in result.errors if e.rule == 27]
        assert (
            not rule_27_errors
        ), f"Expected no rule-27 error in swap mode; got {rule_27_errors}"


class TestRule32ScrollThroughSwapOnly:
    """bottom_text_scroll='scroll_through' is only valid in mode=swap.
    Refused in forever_scroll and infini_scroll for the same reason
    as bottom_text_wrap (rule 27): those modes drive widgets via
    _scroll_one_by_one / _scroll_side_by_side, which interpret the
    widget's reported cursor_pos as physical scroll travel. The
    scroll_through widget inflates cursor_pos to 2*canvas.width +
    bottom_width + padding to anchor the engine's stop math in swap
    mode — that same value, fed to forever_scroll, would produce 2×
    the expected scroll travel and dead canvas between widgets."""

    @pytest.mark.asyncio
    async def test_scroll_through_in_forever_scroll_rejected(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_scroll = "scroll_through"
""")
        from led_ticker.validate import validate_config

        result = await validate_config(cfg)
        assert any(
            issue.rule == 32 and "bottom_text_scroll" in issue.message
            for issue in result.errors
        ), f"Expected rule 32 error; got errors={result.errors}"

    @pytest.mark.asyncio
    async def test_scroll_through_in_infini_scroll_rejected(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "infini_scroll"

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_scroll = "scroll_through"
""")
        from led_ticker.validate import validate_config

        result = await validate_config(cfg)
        assert any(
            issue.rule == 32 and "bottom_text_scroll" in issue.message
            for issue in result.errors
        ), f"Expected rule 32 error; got errors={result.errors}"

    @pytest.mark.asyncio
    async def test_scroll_through_in_swap_accepted(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
hold_time = 5

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_scroll = "scroll_through"
""")
        from led_ticker.validate import validate_config

        result = await validate_config(cfg)
        rule_32_errors = [e for e in result.errors if e.rule == 32]
        assert (
            not rule_32_errors
        ), f"Expected no rule-32 error in swap mode; got {rule_32_errors}"

    @pytest.mark.asyncio
    async def test_scroll_through_marquee_default_not_flagged(self, tmp_path):
        """The default value 'marquee' must NOT trigger rule 32 even in
        forever_scroll mode — only the explicit scroll_through value
        carries the mode constraint."""
        cfg = tmp_path / "config.toml"
        cfg.write_text("""\
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "two_row"
top_text = "TOP"
bottom_text = "bottom"
bottom_text_scroll = "marquee"
""")
        from led_ticker.validate import validate_config

        result = await validate_config(cfg)
        rule_32_errors = [e for e in result.errors if e.rule == 32]
        assert (
            not rule_32_errors
        ), f"marquee mode should not trigger rule 32; got {rule_32_errors}"


@pytest.mark.asyncio
async def test_validate_surfaces_coerced_font_size_as_warning(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 64
cols = 256
default_scale = 4

[[playlist.section]]
mode = "swap"
content_height = 16
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "hi"
font = "Inter-Bold"
font_size = "25"
""")
    from led_ticker.validate import validate_config

    result = await validate_config(cfg)
    assert result.valid  # warnings don't fail validation
    assert len(result.errors) == 0
    assert any(w.rule == 37 and "font_size" in w.message for w in result.warnings)


@pytest.mark.asyncio
async def test_validate_surfaces_image_align_case_as_warning(tmp_path):
    from PIL import Image

    img_path = tmp_path / "tiny.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(img_path)

    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 64
cols = 256
default_scale = 4

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "image"
path = "tiny.png"
image_align = "Left"
""")
    from led_ticker.validate import validate_config

    result = await validate_config(cfg)
    assert result.valid
    assert any(w.rule == 37 and "image_align" in w.message for w in result.warnings)


@pytest.mark.asyncio
async def test_validate_font_size_true_still_errors(tmp_path):
    """Bool is still a hard error — the rule-28 / rule-10 pattern."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 64
cols = 256
default_scale = 4

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
font = "Inter-Bold"
font_size = true
""")
    from led_ticker.validate import validate_config

    result = await validate_config(cfg)
    assert not result.valid
    assert any("must be an int" in e.message for e in result.errors)


@pytest.mark.asyncio
async def test_original_bug_font_size_string_no_typeerror(tmp_path):
    """Regression: font_size = "25" on a hires font used to crash with
    `TypeError: '<' not supported between instances of 'str' and 'int'`
    deep in resolve_font. After coerce-and-warn, it's a warning."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 64
cols = 256
default_scale = 4

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 30.0

[[playlist.section.widget]]
type = "gif"
path = "missing.gif"
fit = "letterbox"
image_align = "center"
text = "Moon         Bunny"
font = "Inter-Bold"
font_size = "25"
""")
    from led_ticker.validate import validate_config

    result = await validate_config(cfg)
    type_errors = [e for e in result.errors if "'<' not supported" in e.message]
    assert type_errors == []
    matches = [
        w
        for w in result.warnings
        if w.rule == 37 and "font_size" in w.location and '"25"' in w.message and w.fix
    ]
    assert len(matches) == 1, (
        f"expected exactly one rule-37 warning for font_size; "
        f"got warnings: {result.warnings!r}"
    )


class TestMigrationError:
    """MigrationError carries its fix string; _run_build_checks routes it directly."""

    def test_migration_error_importable_from_validate(self):
        from led_ticker.validate import MigrationError

        err = MigrationError(
            "text_scale removed ...",
            "Replace with font_size = N × cell_h",
        )
        assert err.message == "text_scale removed ..."
        assert err.suggested_fix == "Replace with font_size = N × cell_h"

    def test_migration_error_is_exception(self):
        from led_ticker.validate import MigrationError

        with pytest.raises(MigrationError):
            raise MigrationError("msg", "fix")

    @pytest.mark.asyncio
    async def test_run_build_checks_returns_migration_errors_separately(self, tmp_path):
        """MigrationError from _build_widget comes back as a third list."""
        from led_ticker.config import SectionConfig
        from led_ticker.validate import _run_build_checks

        section = SectionConfig(
            mode="swap",
            widgets=[{"type": "message", "text": "hi", "text_scale": 2}],
        )
        errors, warnings, migrations = await _run_build_checks([section], tmp_path)
        assert len(errors) == 0
        assert len(migrations) == 1
        loc, msg, fix, fix_key, fix_replacement_key = migrations[0]
        assert "text_scale" in msg
        assert "font_size" in fix

    def test_migration_error_carries_fix_keys(self):
        """MigrationError stores fix_key and fix_replacement_key."""
        from led_ticker.validate import MigrationError

        e = MigrationError(
            "gif_loops renamed to play_count",
            suggested_fix='Rename "gif_loops" to "play_count"',
            fix_key="gif_loops",
            fix_replacement_key="play_count",
        )
        assert e.fix_key == "gif_loops"
        assert e.fix_replacement_key == "play_count"

    def test_migration_error_default_fix_keys_none(self):
        """MigrationError fix_key defaults to None (not auto-fixable)."""
        from led_ticker.validate import MigrationError

        e = MigrationError("text_scale removed", suggested_fix="Use font_size")
        assert e.fix_key is None
        assert e.fix_replacement_key is None


class TestRule39TransitionNames:
    """Unknown transition names surface as rule-39 errors."""

    async def test_unknown_transition_in_section_is_error(self, conf):
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "wipe_leftt"

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        )
        assert not result.valid
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "wipe_leftt" in rule_39[0].message
        assert "wipe_left" in rule_39[0].message

    async def test_cut_sentinel_is_always_valid(self, conf):
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "cut"

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        )
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert rule_39 == []

    async def test_known_transition_name_passes(self, conf):
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
transition = "wipe_left"

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        )
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert rule_39 == []

    async def test_unknown_between_sections_is_error(self, conf):
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[transitions]
between_sections = "pokball_alternating"

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        )
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "pokball_alternating" in rule_39[0].message

    async def test_unknown_entry_transition_is_error(self, conf):
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
entry_transition = "dissolvre"

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        )
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "dissolvre" in rule_39[0].message

    async def test_unknown_default_transition_is_error(self, conf):
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[transitions]
default = "unkown_name"

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        )
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "unkown_name" in rule_39[0].message

    async def test_unknown_widget_transition_is_error(self, conf):
        result = await validate_config(
            conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
widget_transition = "wipe_leffttt"

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        )
        rule_39 = [e for e in result.errors if e.rule == 39]
        assert len(rule_39) == 1
        assert "wipe_leffttt" in rule_39[0].message


class TestUnknownKwargValidationRule:
    """Unknown widget kwargs surface as rule-38 errors in ValidationResult."""

    @pytest.mark.asyncio
    async def test_unknown_kwarg_surfaces_as_validation_error(self, tmp_path):
        """text_color (typo for font_color) → rule=38 error in ValidationResult."""
        from led_ticker.validate import validate_config

        toml_text = """
[display]
rows = 16
cols = 160
hardware_mapping = "adafruit-hat"
gpio_slowdown = 2

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
text_color = [255, 0, 0]
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path)

        assert not result.valid
        rule_38_errors = [e for e in result.errors if e.rule == 38]
        assert len(rule_38_errors) == 1
        assert "text_color" in rule_38_errors[0].message


async def test_validation_result_carries_fix_keys_for_gif_loops(tmp_path):
    """ValidationResult.errors carries fix_key/fix_replacement_key for gif_loops."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "test.gif"
gif_loops = 2
"""
    )
    result = await validate_config(config_file)
    migration_errors = [e for e in result.errors if e.fix_key == "gif_loops"]
    assert migration_errors, "expected error with fix_key='gif_loops'"
    assert migration_errors[0].fix_replacement_key == "play_count"


class TestRule40AssetPaths:
    """Asset path existence is checked in --strict mode only."""

    async def test_missing_gif_path_in_strict_mode_is_error(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "assets/missing.gif"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path, strict=True)
        rule_40 = [e for e in result.errors if e.rule == 40]
        assert len(rule_40) == 1
        assert "missing.gif" in rule_40[0].message

    async def test_missing_gif_path_in_normal_mode_is_not_error(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "assets/missing.gif"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path)
        rule_40 = [e for e in result.errors if e.rule == 40]
        assert rule_40 == []

    async def test_existing_gif_path_in_strict_mode_passes(self, tmp_path):
        gif_path = tmp_path / "assets" / "test.gif"
        gif_path.parent.mkdir()
        gif_path.write_bytes(b"GIF89a")
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "assets/test.gif"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path, strict=True)
        rule_40 = [e for e in result.errors if e.rule == 40]
        assert rule_40 == []

    async def test_message_widget_path_not_checked(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        result = await validate_config(config_path, strict=True)
        rule_40 = [e for e in result.errors if e.rule == 40]
        assert rule_40 == []


class TestStrictModeWarningPromotion:
    """In strict mode, warnings become errors."""

    async def test_strict_promotes_unknown_font_warning_to_error(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
font = "NonExistentFont"
font_size = 24
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)

        # Normal mode: rule 24 is a warning
        normal = await validate_config(config_path)
        rule_24_warnings = [w for w in normal.warnings if w.rule == 24]
        assert len(rule_24_warnings) == 1
        assert normal.valid  # warnings don't fail normal mode

        # Strict mode: rule 24 becomes an error
        strict = await validate_config(config_path, strict=True)
        rule_24_errors = [e for e in strict.errors if e.rule == 24]
        assert len(rule_24_errors) == 1
        assert not strict.valid

    async def test_strict_mode_no_warnings_remain(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
font = "NonExistentFont"
font_size = 24
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        strict = await validate_config(config_path, strict=True)
        assert strict.warnings == []

    async def test_clean_config_valid_in_both_modes(self, tmp_path):
        toml_text = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "hello"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_text)
        normal = await validate_config(config_path)
        strict = await validate_config(config_path, strict=True)
        assert normal.valid
        assert strict.valid


class TestStrictModeCLI:
    """--strict flag behaviour via in-process validate_config calls."""

    async def test_strict_exit_1_on_warning(self, conf):
        """A config with only warnings is valid normally, invalid with strict=True."""
        toml = """
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
font = "GhostFont"
font_size = 24
"""
        path = conf(toml)
        # Normal mode: valid (warning, not error)
        normal = await validate_config(path)
        assert normal.valid, normal.warnings

        # Strict mode: invalid (warning promoted to error)
        strict = await validate_config(path, strict=True)
        assert not strict.valid

    async def test_strict_exit_0_when_clean(self, conf):
        """A warning-free config is valid even with strict=True."""
        path = conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "hello"
""")
        result = await validate_config(path, strict=True)
        assert result.valid

    async def test_nonstrict_exit_0_with_warnings(self, conf):
        """Without strict=True, a config with warnings is still valid."""
        path = conf("""
[display]
rows = 32
cols = 64
chain = 8
default_scale = 1

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hello"
font = "GhostFont"
font_size = 24
""")
        result = await validate_config(path)
        assert result.valid


@pytest.mark.asyncio
async def test_coerce_warning_summary_appears(tmp_path):
    """When validate emits coercion warnings, a summary count line appears."""
    from led_ticker.validate import _format_human

    config_content = """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
hold_seconds = 3.0

[[playlist.section.widget]]
type = "message"
text = "hello"
padding = "6"
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    result = await validate_config(config_file)
    output = _format_human(result)
    coerce_warnings = [w for w in result.warnings if w.rule == 37]
    assert (
        coerce_warnings
    ), "expected at least one rule-37 coercion warning from padding='6'"
    assert "coercion warning" in output.lower()


async def test_apply_migrations_renames_gif_loops(tmp_path):
    """apply_migrations renames gif_loops → play_count in the TOML file."""
    from led_ticker.validate import apply_migrations

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "test.gif"
gif_loops = 2
"""
    )
    result = await validate_config(config_file)
    n = apply_migrations(config_file, result)
    assert n == 1

    # File on disk should now use play_count
    patched = config_file.read_text()
    assert "play_count" in patched
    assert "gif_loops" not in patched


async def test_apply_migrations_returns_zero_when_nothing_to_fix(tmp_path):
    """apply_migrations returns 0 when no auto-fixable errors exist."""
    from led_ticker.validate import apply_migrations

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "Hello"
"""
    )
    result = await validate_config(config_file)
    n = apply_migrations(config_file, result)
    assert n == 0


async def test_apply_migrations_leaves_non_fixable_errors(tmp_path):
    """apply_migrations does not remove non-auto-fixable errors (e.g. text_scale)."""
    from led_ticker.validate import apply_migrations

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "Hello"
text_scale = 2
"""
    )
    result = await validate_config(config_file)
    n = apply_migrations(config_file, result)
    assert n == 0
    text_scale_errors = [e for e in result.errors if "text_scale" in e.message]
    assert text_scale_errors, "text_scale error should still be present"


@pytest.mark.asyncio
async def test_rule_41_title_color_key(tmp_path):
    """Rule 41: title color = ... triggers a validate error."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "forever_scroll"

[playlist.section.title]
type = "message"
text = "News"
color = "random"

[[playlist.section.widget]]
type = "message"
text = "Hello"
"""
    )
    result = await validate_config(config_file)
    rule_41 = [e for e in result.errors if e.rule == 41]
    assert rule_41, "expected rule 41 error for title color ="
    assert rule_41[0].location == "section[0].title"
    assert "font_color" in rule_41[0].fix


@pytest.mark.asyncio
async def test_apply_migrations_renames_title_color(tmp_path):
    """apply_migrations renames title color → font_color in the TOML file."""
    from led_ticker.validate import apply_migrations

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "forever_scroll"

[playlist.section.title]
type = "message"
text = "News"
color = "random"

[[playlist.section.widget]]
type = "message"
text = "Hello"
"""
    )
    result = await validate_config(config_file)
    n = apply_migrations(config_file, result)
    assert n == 1

    patched = config_file.read_text()
    assert "font_color" in patched
    assert "\ncolor " not in patched  # no bare "color" key (font_color is fine)


def test_cli_fix_flag_renames_gif_loops(tmp_path):
    """led-ticker validate --fix renames gif_loops → play_count in the file."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "gif"
path = "test.gif"
gif_loops = 2
"""
    )
    repo_root = str(Path(__file__).parent.parent)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "led_ticker.app.cli",
            "validate",
            "--fix",
            str(config_file),
        ],
        env={
            **os.environ,
            "PYTHONPATH": f"{repo_root}/src:{repo_root}/tests/stubs",
        },
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert "Applied 1 migration" in result.stderr
    patched = config_file.read_text()
    assert "play_count" in patched
    assert "gif_loops" not in patched


# ---------------------------------------------------------------------------
# Rules 42-49: lightbulbs border style value-range checks
# ---------------------------------------------------------------------------


class TestRule42BulbSizeNonPositive:
    async def test_zero_raises(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", bulb_size = 0}
""")
        result = await validate_config(cfg)
        errs = [(e.rule, e.message) for e in result.errors]
        assert any(
            i.rule == 42 for i in result.errors
        ), f"expected rule 42; got errors={errs}"

    async def test_negative_raises(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", bulb_size = -3}
""")
        result = await validate_config(cfg)
        errs = [(e.rule, e.message) for e in result.errors]
        assert any(
            i.rule == 42 for i in result.errors
        ), f"expected rule 42; got errors={errs}"


class TestRule43BulbSizeTooLarge:
    async def test_too_large_for_panel(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", bulb_size = 9}
""")
        result = await validate_config(cfg)
        # max allowed = 16 // 2 = 8; 9 > 8 → rule 43
        errs = [(e.rule, e.message) for e in result.errors]
        assert any(
            i.rule == 43 and "9" in i.message for i in result.errors
        ), f"expected rule 43 with '9'; got errors={errs}"


class TestRule44UnknownMode:
    async def test_unknown_mode(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "sparkle"}
""")
        result = await validate_config(cfg)
        errs = [(e.rule, e.message) for e in result.errors]
        assert any(
            i.rule == 44 for i in result.errors
        ), f"expected rule 44; got errors={errs}"


class TestRule45BadDirection:
    async def test_bad_direction(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "chase", direction = "diag"}
""")
        result = await validate_config(cfg)
        errs = [(e.rule, e.message) for e in result.errors]
        assert any(
            i.rule == 45 for i in result.errors
        ), f"expected rule 45; got errors={errs}"


class TestRule46BadChaseDensity:
    async def test_chase_density_zero(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "chase", chase_density = 0}
""")
        result = await validate_config(cfg)
        errs = [(e.rule, e.message) for e in result.errors]
        assert any(
            i.rule == 46 for i in result.errors
        ), f"expected rule 46; got errors={errs}"


class TestRule47NegativeGap:
    async def test_negative_gap(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", gap = -1}
""")
        result = await validate_config(cfg)
        errs = [(e.rule, e.message) for e in result.errors]
        assert any(
            i.rule == 47 for i in result.errors
        ), f"expected rule 47; got errors={errs}"


class TestRule48ChaseDensityOnNonChase:
    async def test_warning_on_non_chase(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "unison", chase_density = 5}
""")
        result = await validate_config(cfg)
        warns = [(w.rule, w.message) for w in result.warnings]
        assert any(
            i.rule == 48 for i in result.warnings
        ), f"expected rule 48 warning; got warnings={warns}"


class TestRule49DirectionOnNonChase:
    async def test_warning_on_non_chase(self, tmp_path):
        cfg = tmp_path / "c.toml"
        cfg.write_text("""
[display]
rows = 64
cols = 128

[[playlist.section]]
mode = "swap"

[[playlist.section.widget]]
type = "message"
text = "hi"
border = {style = "lightbulbs", mode = "alternate", direction = "ccw"}
""")
        result = await validate_config(cfg)
        warns = [(w.rule, w.message) for w in result.warnings]
        assert any(
            i.rule == 49 for i in result.warnings
        ), f"expected rule 49 warning; got warnings={warns}"

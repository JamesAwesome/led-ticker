import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from led_ticker.app import _build_widget
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


async def test_build_widget_validate_only_returns_none_for_valid_widget():
    cfg = {"type": "message", "text": "hello"}
    result = await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]
    assert result is None


async def test_build_widget_validate_only_raises_on_text_scale():
    cfg = {"type": "message", "text": "hi", "text_scale": 2}
    with pytest.raises(ValueError, match="text_scale"):
        await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]


async def test_build_widget_validate_only_raises_on_animation_wrong_type():
    cfg = {"type": "weather", "location": "NYC", "animation": "typewriter"}
    with pytest.raises(ValueError, match="animation is only valid"):
        await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]


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
    cfg = """\
        [display]
        rows = 32
        cols = 64
        chain = 8
        default_scale = 4

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


def test_cli_exit_code_0_on_valid(conf):
    path = conf(GOOD_CONFIG)
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0


def test_cli_exit_code_1_on_error(conf):
    path = conf(GOOD_CONFIG + '\n[[playlist.section.widget]]\ntype = "banana"\n')
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


def test_cli_exit_code_2_on_missing_file(tmp_path):
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(tmp_path / "missing.toml")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_cli_json_flag_produces_parseable_output(conf):
    path = conf(GOOD_CONFIG)
    proc = subprocess.run(
        ["uv", "run", "led-ticker", "validate", str(path), "--json"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
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
    `text_loops` field is honored INSIDE the widget's own `play()`
    loop — `_play_widget` doesn't pass `hold_time` through, so the
    two values can't interact. A warning here would be misleading."""
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
        f"rule 30 must not fire on gif (hold_time doesn't reach play loop); "
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

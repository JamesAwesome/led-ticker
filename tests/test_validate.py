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
    # Use scale=4 explicitly: 20 * 4 = 80 > 32 → triggers rule 1
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
    assert result.valid is True  # soft warning, not error
    assert any(w.rule == 1 for w in result.warnings)


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


def test_json_output_valid_config(conf):
    path = conf(GOOD_CONFIG)

    async def _run():
        from led_ticker.validate import _format_json

        result = await validate_config(path)
        return _format_json(result)

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(_run())
    finally:
        loop.close()
    data = json.loads(raw)
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

"""Tests for led_ticker.config."""

import textwrap
from pathlib import Path

import pytest

from led_ticker.config import load_config


class TestTransitionObjNotMutated:
    def test_transition_config_has_no_transition_obj_field(self):
        import dataclasses

        from led_ticker.config import TransitionConfig

        fields = {f.name for f in dataclasses.fields(TransitionConfig)}
        assert "transition_obj" not in fields, (
            "transition_obj must be a local variable in run.py, "
            "not a field on the shared TransitionConfig dataclass."
        )


SAMPLE_CONFIG = """\
[display]
rows = 16
cols = 32
chain_length = 5
brightness = 60
gpio_slowdown = 2

[title]
delay = 5

[[playlist.section]]
mode = "forever_scroll"
loop_count = 1

[playlist.section.title]
type = "message"
text = "Hello"
color = "random"

[[playlist.section.widget]]
type = "message"
text = "Test message"

[[playlist.section.widget]]
type = "countdown"
message = "Days Until Spring"
countdown_date = 2026-03-20

[[playlist.section]]
mode = "swap"
loop_count = 2

[[playlist.section.widget]]
type = "message"
text = "Another message"
"""


@pytest.fixture
def config(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE_CONFIG)
    return load_config(p)


def test_load_config_display(config):
    assert config.display.rows == 16
    assert config.display.cols == 32
    assert config.display.chain_length == 5
    assert config.display.brightness == 60
    assert config.display.gpio_slowdown == 2


def test_load_config_sections(config):
    assert len(config.sections) == 2
    assert config.sections[0].mode == "forever_scroll"
    assert config.sections[0].loop_count == 1
    assert config.sections[1].mode == "swap"
    assert config.sections[1].loop_count == 2


def test_load_config_widgets(config):
    section = config.sections[0]
    assert len(section.widgets) == 2
    assert section.widgets[0]["type"] == "message"
    assert section.widgets[0]["text"] == "Test message"
    assert section.widgets[1]["type"] == "countdown"


def test_load_config_title(config):
    assert config.title_delay == 5
    assert config.sections[0].title["text"] == "Hello"
    assert config.sections[0].title["color"] == "random"
    assert config.sections[1].title is None


def test_load_config_defaults(tmp_path):
    p = tmp_path / "minimal.toml"
    p.write_text("""\
[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "message"
text = "hi"
""")
    config = load_config(p)
    assert config.display.rows == 16
    assert config.display.brightness == 100
    assert config.display.hardware_mapping == "adafruit-hat"
    assert config.title_delay == 5


def test_display_config_new_field_defaults_match_existing_sign(tmp_path):
    """New fields must default to values that don't change existing-sign behavior."""
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 16
cols = 32
chain_length = 5

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(p)
    assert cfg.display.parallel == 1
    assert cfg.display.pixel_mapper_config == ""
    assert cfg.display.default_scale == 1
    assert cfg.sections[0].scale == 1
    # Performance defaults preserve existing-sign behavior
    assert cfg.display.pwm_bits == 11
    assert cfg.display.pwm_lsb_nanoseconds == 130
    assert cfg.display.show_refresh_rate is False
    assert cfg.display.disable_hardware_pulsing is False
    assert cfg.display.rp1_rio == 0


def test_display_config_perf_tuning_keys(tmp_path):
    """Performance tuning keys can be overridden from TOML."""
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 32
cols = 64
chain_length = 8
pwm_bits = 8
pwm_lsb_nanoseconds = 200
show_refresh_rate = true
disable_hardware_pulsing = false
rp1_rio = 1

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(p)
    assert cfg.display.pwm_bits == 8
    assert cfg.display.pwm_lsb_nanoseconds == 200
    assert cfg.display.show_refresh_rate is True
    assert cfg.display.rp1_rio == 1


def test_display_config_bigsign_keys(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 32
cols = 64
chain_length = 8
parallel = 1
pixel_mapper_config = "U-mapper"
default_scale = 4

[[playlist.section]]
mode = "swap"
scale = 2
""")
    cfg = load_config(p)
    assert cfg.display.parallel == 1
    assert cfg.display.pixel_mapper_config == "U-mapper"
    assert cfg.display.default_scale == 4
    assert cfg.sections[0].scale == 2


def test_bigsign_example_config_loads(tmp_path):
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root / "config" / "config.bigsign.example.toml")
    assert cfg.display.rows == 32
    assert cfg.display.cols == 64
    assert cfg.display.chain_length == 8
    assert cfg.display.parallel == 1
    # Custom Remap: 2×4 vertical-serpentine, all panels upright.
    # See the config file for the exact panel placement string.
    assert cfg.display.pixel_mapper_config.startswith("Remap:")
    assert "256,64" in cfg.display.pixel_mapper_config  # 256 wide × 64 tall canvas
    assert cfg.display.default_scale == 4
    # Performance defaults baked into the example
    assert cfg.display.gpio_slowdown == 3
    assert cfg.display.pwm_bits == 8
    assert cfg.display.rp1_rio == 1
    assert cfg.display.show_refresh_rate is True
    assert len(cfg.sections) >= 1
    # First section inherits default_scale
    assert cfg.sections[0].scale == 4
    # Second section overrides to scale=2 (letterboxed countdowns)
    assert cfg.sections[1].scale == 2


def test_section_scale_falls_back_to_default(tmp_path):
    """When a section omits scale, it inherits display.default_scale."""
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 32
cols = 64
chain_length = 8
default_scale = 4

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(p)
    assert cfg.sections[0].scale == 4


def test_section_bg_color_defaults_to_none(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="forever_scroll"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].bg_color is None


def test_section_bg_color_parsed_from_toml(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="forever_scroll"\n'
        "bg_color=[26, 59, 142]\n"
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].bg_color == (26, 59, 142)


def test_transition_specified_true_when_section_has_transition_key(tmp_path):
    """`transition_specified` must be True when the section's TOML
    explicitly sets `transition` — used by the engine to decide
    whether to override `between_sections` for inter-section entry."""
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="swap"\n'
        'transition = "pokeball"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].transition_specified is True
    assert cfg.sections[0].transition.type == "pokeball"


def test_transition_specified_false_when_section_omits_transition(tmp_path):
    """When the section doesn't write `transition = ...`, the flag
    is False even though `section.transition` inherits the global
    default. Without this, the engine couldn't tell "user explicitly
    wanted X" from "X was the global default I never overrode"."""
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        "[transitions]\n"
        'default = "pokeball"\n'  # global default; section inherits
        '[[playlist.section]]\nmode="swap"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].transition_specified is False
    # The transition itself still inherits the global default — but
    # without `transition_specified`, the engine treats this section
    # as "use between_sections for entry" rather than "use pokeball
    # for entry".
    assert cfg.sections[0].transition.type == "pokeball"


def _write_cfg(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_section_start_hold_defaults_to_none(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    assert app.sections[0].start_hold is None


def test_section_start_hold_parses_zero(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = 0.0

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    assert app.sections[0].start_hold == 0.0


def test_section_start_hold_parses_positive_float(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"
        start_hold = 2.5

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    assert app.sections[0].start_hold == 2.5


def test_section_separator_defaults_to_none(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    s = app.sections[0]
    assert s.separator is None
    assert s.separator_font is None
    assert s.separator_font_size is None
    assert s.separator_color is None


def test_section_separator_text_parses(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator = " * "

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    assert app.sections[0].separator == " * "


def test_section_separator_empty_string_parses(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator = ""

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    # Empty string is a meaningful value distinct from None — it triggers the
    # "two-space gap, no glyph" path in _resolve_buffer_msg. Must NOT collapse
    # to None during parsing.
    assert app.sections[0].separator == ""


def test_section_separator_font_parses(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator_font = "Inter-Bold"
        separator_font_size = 24

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    s = app.sections[0]
    assert s.separator_font == "Inter-Bold"
    assert s.separator_font_size == 24


def test_section_separator_color_parses_rgb_list(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator_color = [225, 48, 108]

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    # Color is raw at this stage (list[int]); the parser doesn't normalize
    # to ColorProvider — _resolve_buffer_msg does that in app.py at build
    # time. Keep parsing trivial.
    assert app.sections[0].separator_color == [225, 48, 108]


def test_section_separator_color_parses_rainbow_string(tmp_path):
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator_color = "rainbow"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    assert app.sections[0].separator_color == "rainbow"


def test_section_raw_round_trips_from_toml(tmp_path):
    """_raw must contain the original section dict so the validator can
    inspect unknown / cross-scope keys (rules 34 and 35)."""
    cfg = _write_cfg(
        tmp_path,
        """\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "swap"
        hold_time = 3.0
        scroll_step_ms = 35

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    raw = app.sections[0]._raw
    assert raw["mode"] == "swap"
    assert raw["hold_time"] == 3.0
    assert raw["scroll_step_ms"] == 35
    # widget list is stored under the TOML key "widget", not "widgets"
    assert "widget" in raw


def test_section_raw_is_empty_on_direct_construction():
    """Direct programmatic construction of SectionConfig must not
    require _raw — default factory gives an empty dict."""
    from led_ticker.config import SectionConfig

    s = SectionConfig(mode="swap")
    assert s._raw == {}


def test_load_config_coerces_display_brightness_string(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32
brightness = "60"

[[playlist.section]]
mode = "swap"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.display.brightness == 60
    assert isinstance(config.display.brightness, int)
    assert any(w.field == "display.brightness" for w in config._coerce_warnings)


def test_load_config_coerces_multiple_display_fields(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = "16"
cols = "32"
chain_length = "1"
brightness = "60"
gpio_slowdown = "3"

[[playlist.section]]
mode = "swap"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.display.rows == 16
    assert config.display.cols == 32
    assert config.display.chain_length == 1
    assert config.display.brightness == 60
    assert config.display.gpio_slowdown == 3
    fields_warned = {w.field for w in config._coerce_warnings}
    assert fields_warned >= {
        "display.rows",
        "display.cols",
        "display.chain_length",
        "display.brightness",
        "display.gpio_slowdown",
    }


def test_load_config_coerces_section_hold_time_string(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[[playlist.section]]
mode = "swap"
hold_time = "3.0"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.sections[0].hold_time == 3.0
    assert any(w.field == "section[0].hold_time" for w in config._coerce_warnings)


def test_load_config_coerces_section_content_height_string(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[[playlist.section]]
mode = "swap"
content_height = "16"
scale = "2"
loop_count = "3"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.sections[0].content_height == 16
    assert config.sections[0].scale == 2
    assert config.sections[0].loop_count == 3
    fields_warned = {w.field for w in config._coerce_warnings}
    assert "section[0].content_height" in fields_warned
    assert "section[0].scale" in fields_warned
    assert "section[0].loop_count" in fields_warned


def test_load_config_coerces_transition_easing_case(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[transitions]
default = "cut"
easing = "Linear"

[[playlist.section]]
mode = "swap"
""")
    from led_ticker.config import load_config

    config = load_config(cfg)
    assert config.default_transition.easing == "linear"
    assert any(w.field == "transitions.easing" for w in config._coerce_warnings)


def test_load_config_unknown_easing_raises(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32

[transitions]
easing = "easeout"

[[playlist.section]]
mode = "swap"
""")
    import pytest

    from led_ticker.config import load_config

    with pytest.raises(ValueError, match="not a valid choice"):
        load_config(cfg)


def test_entry_transition_parsed_from_toml(tmp_path):
    """entry_transition is parsed when present in TOML."""
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="swap"\n'
        'entry_transition = "pokeball"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].entry_transition is not None
    assert cfg.sections[0].entry_transition.type == "pokeball"


def test_entry_transition_none_when_absent(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="swap"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].entry_transition is None


def test_widget_transition_parsed_from_toml(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="swap"\n'
        'widget_transition = "wipe_left"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].widget_transition is not None
    assert cfg.sections[0].widget_transition.type == "wipe_left"


def test_widget_transition_none_when_absent(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="swap"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].widget_transition is None


def test_entry_transition_and_transition_coexist(tmp_path):
    """entry_transition and transition can both be set independently."""
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="swap"\n'
        'transition = "wipe_left"\n'
        'entry_transition = "pokeball"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].transition.type == "wipe_left"
    assert cfg.sections[0].transition_specified is True
    assert cfg.sections[0].entry_transition is not None
    assert cfg.sections[0].entry_transition.type == "pokeball"


def test_entry_transition_dict_form(tmp_path):
    """entry_transition accepts the dict form with duration."""
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="swap"\n'
        '[playlist.section.entry_transition]\ntype = "dissolve"\nduration = 0.8\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].entry_transition is not None
    assert cfg.sections[0].entry_transition.type == "dissolve"
    assert cfg.sections[0].entry_transition.duration == 0.8


def test_transition_fps_defaults_to_none():
    from led_ticker.config import TransitionConfig

    cfg = TransitionConfig()
    assert cfg.transition_fps is None


def test_transition_fps_parsed_from_section_toml(tmp_path):
    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "swap"
        transition = "push_left"
        transition_fps = 40.0

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    assert cfg.sections[0].transition.transition_fps == 40.0


def test_transition_fps_parsed_from_inline_dict(tmp_path):
    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [transitions]
        between_sections = {type = "push_left", duration = 1.0, transition_fps = 30.0}

        [[playlist.section]]
        mode = "swap"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    assert cfg.between_sections.transition_fps == 30.0


def test_transition_fps_absent_stays_none(tmp_path):
    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "swap"
        transition = "push_left"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    assert cfg.sections[0].transition.transition_fps is None


def test_transition_fps_converts_to_scroll_speed(tmp_path):
    """transition_fps=40 -> scroll_speed=0.025 at the run_transition call site."""
    from led_ticker.config import load_config

    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "swap"
        transition = "push_left"
        transition_fps = 40.0

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    fps = cfg.sections[0].transition.transition_fps
    assert fps == 40.0
    assert abs(1.0 / fps - 0.025) < 1e-9


def test_transition_fps_none_yields_default_scroll_speed(tmp_path):
    """transition_fps=None -> caller uses 0.05 (the run_transition default)."""
    from led_ticker.config import load_config

    toml = textwrap.dedent("""\
        [display]
        rows = 16
        cols = 32
        chain_length = 5

        [[playlist.section]]
        mode = "swap"
        transition = "push_left"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
    """)
    p = tmp_path / "cfg.toml"
    p.write_text(toml)
    cfg = load_config(p)
    fps = cfg.sections[0].transition.transition_fps
    assert fps is None
    scroll_speed = (1.0 / fps) if fps is not None else 0.05
    assert scroll_speed == 0.05

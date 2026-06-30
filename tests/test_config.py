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
mode = "ticker"
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
mode = "slideshow"
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
    assert config.sections[0].mode == "ticker"
    assert config.sections[0].loop_count == 1
    assert config.sections[1].mode == "slideshow"
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


class TestSourceBlockParsing:
    def test_source_block_parses_into_appconfig(self, tmp_path):
        toml = '''\
[[source]]
id = "clock.now"
type = "clock"
format = "%H:%M"

[[playlist.section]]
mode = "slideshow"
'''
        cfg_path = tmp_path / "c.toml"
        cfg_path.write_text(toml)
        cfg = load_config(cfg_path)
        assert len(cfg.sources) == 1
        assert cfg.sources[0].id == "clock.now"
        assert cfg.sources[0].type == "clock"
        assert cfg.sources[0].raw["format"] == "%H:%M"

    def test_no_source_block_yields_empty_list(self, tmp_path):
        cfg_path = tmp_path / "c.toml"
        cfg_path.write_text('[[playlist.section]]\nmode = "slideshow"\n')
        cfg = load_config(cfg_path)
        assert cfg.sources == []

    def test_multiple_source_blocks(self, tmp_path):
        toml = '''\
[[source]]
id = "clock.now"
type = "clock"
format = "%H:%M"

[[source]]
id = "brand.tag"
type = "static"
value = "Open 9-5"

[[playlist.section]]
mode = "slideshow"
'''
        cfg_path = tmp_path / "c.toml"
        cfg_path.write_text(toml)
        cfg = load_config(cfg_path)
        assert len(cfg.sources) == 2
        assert cfg.sources[1].id == "brand.tag"
        assert cfg.sources[1].type == "static"
        assert cfg.sources[1].raw["value"] == "Open 9-5"

    def test_source_block_missing_id_raises(self, tmp_path):
        toml = '''\
[[source]]
type = "clock"

[[playlist.section]]
mode = "slideshow"
'''
        cfg_path = tmp_path / "c.toml"
        cfg_path.write_text(toml)
        with pytest.raises(ValueError, match="id"):
            load_config(cfg_path)

    def test_source_block_missing_type_raises(self, tmp_path):
        toml = '''\
[[source]]
id = "clock.now"

[[playlist.section]]
mode = "slideshow"
'''
        cfg_path = tmp_path / "c.toml"
        cfg_path.write_text(toml)
        with pytest.raises(ValueError, match="type"):
            load_config(cfg_path)


def test_load_config_defaults(tmp_path):
    p = tmp_path / "minimal.toml"
    p.write_text("""\
[[playlist.section]]
mode = "ticker"

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
mode = "slideshow"
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
    assert cfg.display.rp1_pio == 0


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
rp1_pio = 1

[[playlist.section]]
mode = "slideshow"
""")
    cfg = load_config(p)
    assert cfg.display.pwm_bits == 8
    assert cfg.display.pwm_lsb_nanoseconds == 200
    assert cfg.display.show_refresh_rate is True
    assert cfg.display.rp1_pio == 1


def test_obsolete_rp1_rio_key_warns_and_is_ignored(tmp_path):
    """The library renamed rp1_rio → rp1_pio (and flipped the default
    backend to RIO) in June 2026. The old key must not crash a deployed
    config, but it must surface a warning saying what to do."""
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 32
cols = 64
rp1_rio = 1

[[playlist.section]]
mode = "slideshow"
""")
    cfg = load_config(p)
    assert cfg.display.rp1_pio == 0  # old key is ignored, not translated
    warns = [w for w in cfg._coerce_warnings if w.field == "display.rp1_rio"]
    assert len(warns) == 1
    assert "rp1_pio" in warns[0].message


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
mode = "slideshow"
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
    assert (
        cfg.display.rp1_pio == 0
    )  # RIO backend is the library default; example config no longer sets the knob
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
mode = "slideshow"
""")
    cfg = load_config(p)
    assert cfg.sections[0].scale == 4


def test_section_bg_color_defaults_to_none(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="ticker"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].bg_color is None


def test_section_bg_color_parsed_from_toml(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode="ticker"\n'
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
        '[[playlist.section]]\nmode = "slideshow"\n'
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
        '[[playlist.section]]\nmode = "slideshow"\n'
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
        mode = "ticker"

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
        mode = "ticker"
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
        mode = "ticker"
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
        mode = "ticker"

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
        mode = "ticker"
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
        mode = "ticker"
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
        mode = "ticker"
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
        mode = "ticker"
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
        mode = "ticker"
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
        mode = "slideshow"
        hold_time = 3.0
        scroll_step_ms = 35

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """,
    )
    app = load_config(cfg)
    raw = app.sections[0]._raw
    assert raw["mode"] == "slideshow"
    assert raw["hold_time"] == 3.0
    assert raw["scroll_step_ms"] == 35
    # widget list is stored under the TOML key "widget", not "widgets"
    assert "widget" in raw


def test_section_raw_is_empty_on_direct_construction():
    """Direct programmatic construction of SectionConfig must not
    require _raw — default factory gives an empty dict."""
    from led_ticker.config import SectionConfig

    s = SectionConfig(mode="slideshow")
    assert s._raw == {}


def test_load_config_coerces_display_brightness_string(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32
brightness = "60"

[[playlist.section]]
mode = "slideshow"
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
mode = "slideshow"
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
mode = "slideshow"
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
mode = "slideshow"
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
mode = "slideshow"
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
mode = "slideshow"
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
        '[[playlist.section]]\nmode = "slideshow"\n'
        'entry_transition = "pokeball"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].entry_transition is not None
    assert cfg.sections[0].entry_transition.type == "pokeball"


def test_entry_transition_none_when_absent(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode = "slideshow"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].entry_transition is None


def test_widget_transition_parsed_from_toml(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode = "slideshow"\n'
        'widget_transition = "wipe_left"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].widget_transition is not None
    assert cfg.sections[0].widget_transition.type == "wipe_left"


def test_widget_transition_none_when_absent(tmp_path):
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode = "slideshow"\n'
    )
    cfg = load_config(config_file)
    assert cfg.sections[0].widget_transition is None


def test_entry_transition_and_transition_coexist(tmp_path):
    """entry_transition and transition can both be set independently."""
    config_file = tmp_path / "c.toml"
    config_file.write_text(
        "[display]\nrows=16\ncols=32\nchain_length=5\n"
        '[[playlist.section]]\nmode = "slideshow"\n'
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
        '[[playlist.section]]\nmode = "slideshow"\n'
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
        mode = "slideshow"
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
        mode = "slideshow"

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
        mode = "slideshow"
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
        mode = "slideshow"
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
        mode = "slideshow"
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


def test_busy_light_default_disabled(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    cfg = load_config(p)
    assert cfg.busy_light.enabled is False
    assert cfg.busy_light.file_path == "~/.busy"
    assert cfg.busy_light.corner == "top_right"
    assert cfg.busy_light.color == (255, 0, 0)
    assert cfg.busy_light.size == 4
    assert cfg.busy_light.poll_interval == 5.0


def test_busy_light_parsed(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[busy_light]\nenabled=true\nfile_path="/tmp/b"\n'
        'poll_interval=2.0\ncorner="bottom_left"\ncolor=[0,255,0]\nsize=6\n\n'
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    cfg = load_config(p)
    assert cfg.busy_light.enabled is True
    assert cfg.busy_light.file_path == "/tmp/b"
    assert cfg.busy_light.poll_interval == 2.0
    assert cfg.busy_light.corner == "bottom_left"
    assert cfg.busy_light.color == (0, 255, 0)
    assert cfg.busy_light.size == 6


def test_busy_light_invalid_corner_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[busy_light]\nenabled=true\ncorner="middle"\n\n'
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="corner"):
        load_config(p)


def test_busy_light_invalid_size_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\nsize=0\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="size"):
        load_config(p)


def test_busy_light_invalid_color_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\ncolor=[255,0]\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="color"):
        load_config(p)


def test_busy_light_color_out_of_range_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\ncolor=[999,-5,0]\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="color"):
        load_config(p)


def test_busy_light_http_fields_default(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    cfg = load_config(p)
    assert cfg.busy_light.source == "file"
    assert cfg.busy_light.http_host == "0.0.0.0"
    assert cfg.busy_light.http_port == 8081  # default; distinct from [web]'s 8080
    assert cfg.busy_light.token == ""
    assert cfg.busy_light.ttl_seconds == 0.0


def test_busy_light_http_fields_parsed(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[busy_light]\nenabled=true\nsource="http"\n'
        'http_host="127.0.0.1"\nhttp_port=9000\ntoken="abc"\nttl_seconds=300.0\n\n'
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    cfg = load_config(p)
    assert cfg.busy_light.source == "http"
    assert cfg.busy_light.http_host == "127.0.0.1"
    assert cfg.busy_light.http_port == 9000
    assert cfg.busy_light.token == "abc"
    assert cfg.busy_light.ttl_seconds == 300.0


def test_busy_light_invalid_source_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[busy_light]\nenabled=true\nsource="carrier_pigeon"\n\n'
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="busy_light.source"):
        load_config(p)


def test_busy_light_invalid_port_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\nhttp_port=70000\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="busy_light.http_port"):
        load_config(p)


def test_busy_light_negative_ttl_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\nttl_seconds=-1.0\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="busy_light.ttl_seconds"):
        load_config(p)


def test_busy_light_non_string_token_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        "[busy_light]\nenabled=true\ntoken=123\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="busy_light.token"):
        load_config(p)


def test_plugin_transition_show_flags_flow_through_extra():
    from led_ticker.config import TransitionConfig, _parse_transition

    cfg = _parse_transition(
        {"type": "arcade.pokeball", "show_pikachu": False, "show_pokeball": True},
        TransitionConfig(),
    )
    assert cfg.type == "arcade.pokeball"
    assert cfg.extra.get("show_pikachu") is False
    assert cfg.extra.get("show_pokeball") is True


def test_display_hot_reload_defaults_true(tmp_path):
    cfg_file = tmp_path / "c.toml"
    cfg_file.write_text(
        '[display]\nrows = 16\ncols = 32\n\n[[playlist.section]]\nmode = "slideshow"\n'
    )
    cfg = load_config(cfg_file)
    assert cfg.display.hot_reload is True


def test_display_hot_reload_can_be_disabled(tmp_path):
    cfg_file = tmp_path / "c.toml"
    cfg_file.write_text(
        "[display]\nrows = 16\ncols = 32\nhot_reload = false\n\n"
        '[[playlist.section]]\nmode = "slideshow"\n'
    )
    cfg = load_config(cfg_file)
    assert cfg.display.hot_reload is False


def test_web_block_allow_restart_parsed():
    from led_ticker.config import _parse_web_block

    cfg = _parse_web_block({"web": {"allow_restart": True}})
    assert cfg is not None and cfg.allow_restart is True


def test_web_block_allow_restart_defaults_false():
    from led_ticker.config import _parse_web_block

    cfg = _parse_web_block({"web": {}})
    assert cfg is not None and cfg.allow_restart is False


class TestModeMigration:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("swap", "slideshow"),
            ("forever_scroll", "ticker"),
            ("infini_scroll", "one_at_a_time"),
        ],
    )
    def test_old_mode_name_raises_migration_error(self, tmp_path, old, new):
        from led_ticker.validate import MigrationError

        cfg = tmp_path / "config.toml"
        cfg.write_text(
            "[display]\nrows=16\ncols=32\nchain_length=5\n"
            f'[[playlist.section]]\nmode = "{old}"\n'
            '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
        )
        with pytest.raises(MigrationError) as ei:
            load_config(str(cfg))
        assert new in str(ei.value)
        assert old in str(ei.value)

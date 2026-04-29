"""Tests for led_ticker.config."""

import pytest

from led_ticker.config import load_config

SAMPLE_CONFIG = """\
[display]
rows = 16
cols = 32
chain = 5
brightness = 60
slowdown_gpio = 2

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
    assert config.display.chain == 5
    assert config.display.brightness == 60
    assert config.display.slowdown_gpio == 2


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
    assert config.display.gpio_mapping == "adafruit-hat"
    assert config.title_delay == 5


def test_display_config_new_field_defaults_match_existing_sign(tmp_path):
    """New fields must default to values that don't change existing-sign behavior."""
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 16
cols = 32
chain = 5

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(p)
    assert cfg.display.parallel == 1
    assert cfg.display.pixel_mapper == ""
    assert cfg.display.default_scale == 1
    assert cfg.sections[0].scale == 1
    # Performance defaults preserve existing-sign behavior
    assert cfg.display.pwm_bits == 11
    assert cfg.display.pwm_lsb_nanoseconds == 130
    assert cfg.display.show_refresh is False
    assert cfg.display.no_hardware_pulse is False
    assert cfg.display.rp1_rio == 0


def test_display_config_perf_tuning_keys(tmp_path):
    """Performance tuning keys can be overridden from TOML."""
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 32
cols = 64
chain = 8
pwm_bits = 8
pwm_lsb_nanoseconds = 200
show_refresh = true
no_hardware_pulse = false
rp1_rio = 1

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(p)
    assert cfg.display.pwm_bits == 8
    assert cfg.display.pwm_lsb_nanoseconds == 200
    assert cfg.display.show_refresh is True
    assert cfg.display.rp1_rio == 1


def test_display_config_bigsign_keys(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 32
cols = 64
chain = 8
parallel = 1
pixel_mapper = "U-mapper"
default_scale = 4

[[playlist.section]]
mode = "swap"
scale = 2
""")
    cfg = load_config(p)
    assert cfg.display.parallel == 1
    assert cfg.display.pixel_mapper == "U-mapper"
    assert cfg.display.default_scale == 4
    assert cfg.sections[0].scale == 2


def test_bigsign_example_config_loads(tmp_path):
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root / "config" / "config.bigsign.example.toml")
    assert cfg.display.rows == 32
    assert cfg.display.cols == 64
    assert cfg.display.chain == 8
    assert cfg.display.parallel == 1
    # Custom Remap: 2×4 vertical-serpentine, all panels upright.
    # See the config file for the exact panel placement string.
    assert cfg.display.pixel_mapper.startswith("Remap:")
    assert "256,64" in cfg.display.pixel_mapper  # 256 wide × 64 tall canvas
    assert cfg.display.default_scale == 4
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
chain = 8
default_scale = 4

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(p)
    assert cfg.sections[0].scale == 4

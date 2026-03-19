"""Tests for led_ticker.config."""

import tempfile
from pathlib import Path

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


def test_load_config_display():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(SAMPLE_CONFIG)
        f.flush()
        config = load_config(Path(f.name))

    assert config.display.rows == 16
    assert config.display.cols == 32
    assert config.display.chain == 5
    assert config.display.brightness == 60
    assert config.display.slowdown_gpio == 2


def test_load_config_sections():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(SAMPLE_CONFIG)
        f.flush()
        config = load_config(Path(f.name))

    assert len(config.sections) == 2
    assert config.sections[0].mode == "forever_scroll"
    assert config.sections[0].loop_count == 1
    assert config.sections[1].mode == "swap"
    assert config.sections[1].loop_count == 2


def test_load_config_widgets():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(SAMPLE_CONFIG)
        f.flush()
        config = load_config(Path(f.name))

    section = config.sections[0]
    assert len(section.widgets) == 2
    assert section.widgets[0]["type"] == "message"
    assert section.widgets[0]["text"] == "Test message"
    assert section.widgets[1]["type"] == "countdown"


def test_load_config_title():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(SAMPLE_CONFIG)
        f.flush()
        config = load_config(Path(f.name))

    assert config.title_delay == 5
    assert config.sections[0].title["text"] == "Hello"
    assert config.sections[0].title["color"] == "random"
    assert config.sections[1].title is None


def test_load_config_defaults():
    minimal = """\
[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "message"
text = "hi"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(minimal)
        f.flush()
        config = load_config(Path(f.name))

    assert config.display.rows == 16
    assert config.display.brightness == 100
    assert config.display.gpio_mapping == "adafruit-hat"
    assert config.title_delay == 5

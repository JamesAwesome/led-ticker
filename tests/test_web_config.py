"""Tests for the [web] config block."""

import pytest

from led_ticker.config import WebConfig, load_config, read_web_config

MINIMAL = """\
[display]
rows = 16
cols = 32
chain_length = 5

[[playlist.section]]
mode = "forever_scroll"

[[playlist.section.widget]]
type = "message"
text = "hi"
"""


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(body)
    return p


def test_absent_web_block_is_none(tmp_path):
    cfg = load_config(_write(tmp_path, MINIMAL))
    assert cfg.web is None


def test_web_block_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, MINIMAL + "\n[web]\n"))
    assert cfg.web == WebConfig()
    assert cfg.web.host == "0.0.0.0"
    assert cfg.web.port == 8080
    assert cfg.web.token == ""
    assert cfg.web.status_path == "/run/led-ticker/status.json"


def test_web_block_explicit_values(tmp_path):
    overrides = (
        '\n[web]\nhost = "127.0.0.1"\nport = 9090\n'
        'token = "s3cret"\nstatus_path = "/tmp/s.json"\n'
    )
    cfg = load_config(_write(tmp_path, MINIMAL + overrides))
    assert cfg.web == WebConfig(
        host="127.0.0.1", port=9090, token="s3cret", status_path="/tmp/s.json"
    )


@pytest.mark.parametrize(
    "field_line, match",
    [
        ("port = 0", "web.port"),
        ("port = 70000", "web.port"),
        ("token = 5", "web.token"),
        ('status_path = ""', "web.status_path"),
        ("host = 1", "web.host"),
    ],
)
def test_web_block_invalid_values_raise(tmp_path, field_line, match):
    with pytest.raises(ValueError, match=match):
        load_config(_write(tmp_path, MINIMAL + f"\n[web]\n{field_line}\n"))


def test_read_web_config_lightweight(tmp_path):
    # read_web_config must work even when the playlist is invalid —
    # the sidecar serves the validate tab precisely when the config is broken.
    broken = '[web]\nport = 9090\n\n[[playlist.section]]\nmode = "swap"\n'
    assert read_web_config(_write(tmp_path, broken)) == WebConfig(port=9090)


def test_read_web_config_absent_block(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[display]\nrows = 16\n")
    assert read_web_config(p) is None

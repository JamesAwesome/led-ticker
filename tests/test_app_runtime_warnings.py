"""Verify runtime startup logs coerce warnings (without needing real hardware)."""

import logging


def test_load_config_warnings_logged_at_startup(tmp_path, caplog):
    """The list of CoercionWarning collected by load_config should be
    logged via logging.warning() so users see the same message in their
    journal that they'd see from `led-ticker validate`."""
    from led_ticker.app import _log_coerce_warnings
    from led_ticker.config import load_config

    cfg = tmp_path / "config.toml"
    cfg.write_text("""
[display]
rows = 16
cols = 32
brightness = "60"

[[playlist.section]]
mode = "swap"
hold_time = "3.0"
""")

    config = load_config(cfg)
    with caplog.at_level(logging.WARNING):
        _log_coerce_warnings(config)
    messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("brightness" in m for m in messages)
    assert any("hold_time" in m for m in messages)

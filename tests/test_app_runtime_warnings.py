"""Verify runtime startup logs coerce warnings (without real hardware).

Exercises `app.run()` end-to-end with a config that has coerced fields
and asserts the warning messages reach `logging.WARNING`. Targets two
warning sites: load-time (DisplayConfig / SectionConfig fields, drained
right after `load_config`) and per-section widget-build (drained at the
end of each section's widget loop).
"""

from __future__ import annotations

import logging
from unittest import mock

import pytest


class _StopApp(Exception):
    """Break out of run()'s `while True` once we've captured what we need."""


async def test_run_logs_load_time_coerce_warnings(caplog, tmp_path):
    """A config with string-of-digits on a [display] / section field
    must produce a logging.WARNING during run() startup, before the
    section loop begins."""
    from led_ticker import app as app_module
    from led_ticker.app import run as app_run
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

[[playlist.section.widget]]
type = "message"
text = "hi"
""")
    parsed = load_config(cfg)

    class _StoppingTicker:
        def __init__(self, *args, **kwargs):
            self.last_scroll_pos = 0
            raise _StopApp("stop after first Ticker")

        async def run_swap(self, **kw):
            pass

    with (
        mock.patch.object(app_module, "load_config", return_value=parsed),
        mock.patch.object(
            app_module,
            "build_frame_from_config",
            return_value=mock.Mock(
                **{"get_clean_canvas.return_value": mock.Mock(height=16, width=160)}
            ),
        ),
        mock.patch.object(app_module, "_configure_user_font_dir"),
        mock.patch.object(app_module, "Ticker", _StoppingTicker),
        caplog.at_level(logging.WARNING),
        pytest.raises(_StopApp),
    ):
        await app_run(cfg)

    messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    # Two load-time coercions (display.brightness, section[0].hold_time)
    # must both appear in the log.
    assert any("brightness" in m for m in messages), messages
    assert any("hold_time" in m for m in messages), messages

import logging

from led_ticker.app.factories import build_frame_from_config
from led_ticker.config import DisplayConfig


def test_headless_selection_logs_loudly(caplog):
    with caplog.at_level(logging.WARNING):
        build_frame_from_config(DisplayConfig(backend="headless"))
    assert any("headless" in r.message.lower() for r in caplog.records)
    assert any("no hardware" in r.message.lower() for r in caplog.records)

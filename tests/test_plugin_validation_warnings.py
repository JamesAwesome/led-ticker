"""Plugin validation warnings channel (calendar extraction Phase 1)."""

from pathlib import Path

import led_ticker.plugin as plugin
from led_ticker.plugin import ValidationContext


def test_validation_context_is_public_and_frozen():
    assert "ValidationContext" in plugin.__all__
    ctx = ValidationContext(
        scale=4,
        content_height=16,
        panel_width=256,
        panel_height=64,
        config_dir=Path("/tmp/cfg"),
    )
    assert ctx.scale == 4
    assert ctx.content_height == 16
    assert ctx.panel_width == 256
    assert ctx.panel_height == 64
    assert ctx.config_dir == Path("/tmp/cfg")
    # frozen
    import dataclasses

    try:
        ctx.scale = 1  # type: ignore[misc]
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised


def test_api_version_bumped_to_1_1():
    assert plugin.API_VERSION == (1, 1)

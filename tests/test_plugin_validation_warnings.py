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


# ---------------------------------------------------------------------------
# Task 2: _run_validate_config_warnings + collect_validation_warnings
# ---------------------------------------------------------------------------
from pathlib import Path as _P  # noqa: E402

from led_ticker.app.factories import (  # noqa: E402
    _run_validate_config_warnings,
    collect_validation_warnings,
)
from led_ticker.plugin import ValidationContext as _VC  # noqa: E402

_CTX = _VC(
    scale=1, content_height=16, panel_width=160, panel_height=16, config_dir=_P(".")
)


class _WidgetWithWarnings:
    @classmethod
    def validate_config_warnings(cls, cfg, ctx):
        out = []
        if ctx.scale > 2:
            out.append("scale is large")
        if cfg.get("noisy"):
            out.append("noisy is set")
        return out


class _WidgetNoHook:
    pass


class _WidgetBadHook:
    @classmethod
    def validate_config_warnings(cls, cfg, ctx):
        raise RuntimeError("boom")


def test_runner_returns_hook_warnings():
    result = _run_validate_config_warnings(_WidgetWithWarnings, {"noisy": True}, _CTX)
    assert result == ["noisy is set"]


def test_runner_absent_hook_returns_empty():
    assert _run_validate_config_warnings(_WidgetNoHook, {}, _CTX) == []


def test_runner_isolates_raising_hook(caplog):
    # A warnings hook that raises must NOT crash validation.
    assert _run_validate_config_warnings(_WidgetBadHook, {}, _CTX) == []


def test_collect_unknown_type_returns_empty():
    # No 'type' / unknown type => no warnings, no crash.
    assert collect_validation_warnings({}, _CTX) == []
    assert collect_validation_warnings({"type": "does-not-exist"}, _CTX) == []

"""Plugin validation warnings channel (calendar extraction Phase 1)."""

import logging
from pathlib import Path

import pytest

import led_ticker.plugin as plugin
import led_ticker.widgets as _widgets_mod
from led_ticker.plugin import ValidationContext


@pytest.fixture(autouse=True)
def _cleanup_probe_registration():
    yield
    reg = getattr(_widgets_mod, "_WIDGET_REGISTRY", None)
    if isinstance(reg, dict):
        for name in list(reg):
            if name.startswith("phase1_"):
                reg.pop(name, None)


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
    with caplog.at_level(logging.WARNING):
        result = _run_validate_config_warnings(_WidgetBadHook, {}, _CTX)
    assert result == []
    assert "validate_config_warnings raised" in caplog.text


def test_runner_passes_ctx_to_hook():
    ctx_big = _VC(
        scale=4, content_height=16, panel_width=256, panel_height=64, config_dir=_P(".")
    )
    assert _run_validate_config_warnings(_WidgetWithWarnings, {}, ctx_big) == [
        "scale is large"
    ]


def test_collect_unknown_type_returns_empty():
    # No 'type' / unknown type => no warnings, no crash.
    assert collect_validation_warnings({}, _CTX) == []
    assert collect_validation_warnings({"type": "does-not-exist"}, _CTX) == []


# ---------------------------------------------------------------------------
# Task 3: _check_plugin_validation_warnings (validate.py Phase-2 check)
# ---------------------------------------------------------------------------
from types import SimpleNamespace  # noqa: E402

from led_ticker.validate import _check_plugin_validation_warnings  # noqa: E402
from led_ticker.widgets import register  # noqa: E402


def test_check_emits_warning_issue(monkeypatch):
    # Register a throwaway widget type that emits a warning, then build a
    # minimal AppConfig-like object exposing .display and .sections.
    @register("phase1_warn_probe")
    class _Probe:
        @classmethod
        def validate_config_warnings(cls, cfg, ctx):
            return [f"probe warned at scale {ctx.scale}"]

    # _panel_h_real reads: pixel_mapper_config, rows, parallel
    # _panel_w_real reads: pixel_mapper_config, cols, chain_length
    display = SimpleNamespace(
        cols=160,
        rows=16,
        chain_length=1,
        parallel=1,
        default_scale=1,
        pixel_mapper_config="",
    )
    section = SimpleNamespace(
        scale=1, content_height=16, widgets=[{"type": "phase1_warn_probe"}]
    )
    config = SimpleNamespace(display=display, sections=[section])

    issues = _check_plugin_validation_warnings(config, Path("."))
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].rule == 55
    assert issues[0].location == "section[0].widget[0]"
    assert "probe warned at scale 1" in issues[0].message

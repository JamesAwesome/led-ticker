from pathlib import Path

import pytest

from led_ticker.app import _build_widget
from led_ticker.validate import ValidationIssue, ValidationResult


def test_valid_when_no_errors():
    r = ValidationResult(path=Path("x.toml"), errors=[], warnings=[])
    assert r.valid is True


def test_invalid_when_errors_present():
    issue = ValidationIssue(
        rule=1, location="section[0]", message="bad", fix="fix it", severity="error"
    )
    r = ValidationResult(path=Path("x.toml"), errors=[issue], warnings=[])
    assert r.valid is False


def test_valid_with_only_warnings():
    w = ValidationIssue(
        rule=21,
        location="section[0]",
        message="slow",
        fix="speed up",
        severity="warning",
    )
    r = ValidationResult(path=Path("x.toml"), errors=[], warnings=[w])
    assert r.valid is True


async def test_build_widget_validate_only_returns_none_for_valid_widget():
    cfg = {"type": "message", "text": "hello"}
    result = await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]
    assert result is None


async def test_build_widget_validate_only_raises_on_text_scale():
    cfg = {"type": "message", "text": "hi", "text_scale": 2}
    with pytest.raises(ValueError, match="text_scale"):
        await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]


async def test_build_widget_validate_only_raises_on_animation_wrong_type():
    cfg = {"type": "weather", "location": "NYC", "animation": "typewriter"}
    with pytest.raises(ValueError, match="animation is only valid"):
        await _build_widget(cfg, session=None, validate_only=True)  # type: ignore[arg-type]

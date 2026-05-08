# tests/test_validate.py
from pathlib import Path

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

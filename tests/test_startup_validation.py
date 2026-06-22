"""Startup config validation: log report + status-board record (never fatal)."""

import logging
from pathlib import Path

from led_ticker.app.run import (
    _log_validation_report,
    _run_startup_validation,
    _serialize_issues,
)
from led_ticker.validate import ValidationIssue, ValidationResult


def _issue(message="bad", location="section[0].widgets[0]"):
    return ValidationIssue(
        rule=1, location=location, message=message, fix="use rss.feed", severity="error"
    )


def test_serialize_issues_flattens_to_dicts():
    out = _serialize_issues([_issue(message="m", location="loc")])
    assert out == [
        {"rule": 1, "location": "loc", "message": "m", "fix": "use rss.feed"}
    ]


def test_log_report_clean_is_info_no_issues(caplog):
    result = ValidationResult(path=Path("x.toml"))
    with caplog.at_level(logging.INFO):
        _log_validation_report(result)
    assert any("no issues" in r.message for r in caplog.records)


def test_log_report_with_issues_warns_and_includes_report(caplog):
    result = ValidationResult(
        path=Path("x.toml"),
        errors=[_issue(message="Unknown widget type: 'feeds.rss'")],
    )
    with caplog.at_level(logging.WARNING):
        _log_validation_report(result)
    blob = "\n".join(r.message for r in caplog.records)
    assert "1 error(s), 0 warning(s)" in blob
    assert "feeds.rss" in blob  # the per-issue human report is included


async def test_run_startup_validation_logs_and_records(monkeypatch, caplog):
    from led_ticker import status_board
    from led_ticker import validate as validate_mod

    result = ValidationResult(path=Path("x.toml"), errors=[_issue(message="bad")])

    async def fake_validate(path, **kwargs):
        return result

    recorded = {}

    def fake_record(*, errors, warnings, ts):
        recorded.update(errors=errors, warnings=warnings, ts=ts)

    monkeypatch.setattr(validate_mod, "validate_config", fake_validate)
    monkeypatch.setattr(status_board, "record_config_validation", fake_record)

    with caplog.at_level(logging.WARNING):
        await _run_startup_validation(Path("x.toml"))

    assert recorded["errors"][0]["message"] == "bad"
    assert recorded["warnings"] == []
    assert isinstance(recorded["ts"], str) and recorded["ts"]
    assert any("1 error(s)" in r.message for r in caplog.records)


async def test_run_startup_validation_never_raises_on_validator_error(
    monkeypatch, caplog
):
    from led_ticker import validate as validate_mod

    async def boom(path, **kwargs):
        raise RuntimeError("validator exploded")

    monkeypatch.setattr(validate_mod, "validate_config", boom)
    # Must swallow the error (the sign must still boot).
    with caplog.at_level(logging.WARNING):
        await _run_startup_validation(Path("x.toml"))
    assert any("validator error" in r.message for r in caplog.records)

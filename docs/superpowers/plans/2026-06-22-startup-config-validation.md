# Startup Config Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run `validate_config` once at sign startup, log the full report, and publish it to the status board / web UI — so an operator sees every config problem up front instead of discovering them one crash/skip at a time.

**Architecture:** Add a `config_validation` field + `record_config_validation` to the status board (schema 5→6). Add startup helpers to `run.py` that validate after plugins+config load (board already active), log via the existing `validate._format_human` formatter, and record to the board. Add a read-only "Config validation" card to the web status UI. Purely additive diagnostics — never fatal; the existing build-time guards still degrade invalid widgets/transitions, so the sign always boots.

**Tech Stack:** Python 3.14, asyncio, attrs (status board), pytest (asyncio mode AUTO — async tests need no marker), vanilla JS (web UI static page).

## Global Constraints

- Log-and-continue, NEVER fatal: startup validation must not raise into the run loop or stop the sign booting.
- `config_validation` is set ONCE at boot; reloads keep using the existing `last_reload` field and must not touch `config_validation`.
- `SCHEMA_VERSION` bumps 5 → 6; the snapshot top-level-keys tripwire must be updated in the same change. The webui imports `SCHEMA_VERSION` from `status_board`, so no separate webui constant exists to bump.
- `record_config_validation` is instrumentation-only: a no-op when no board is active, and it must never raise into the engine (mirror `record_reload`).
- Reuse `validate._format_human` for the log report — do NOT duplicate validation-result formatting.
- `status_board` must stay dependency-light: `record_config_validation` takes plain `list[dict]` + `str`, NOT `validate.py` types (the run-loop caller serializes the issues). Mirrors `record_reload`'s primitive signature.
- No `from __future__ import annotations`.
- Run `uv run --extra dev ruff check src/ tests/` before every commit (CI lint; the local git hook is broken — commit/push with `--no-verify` and run checks manually).

---

### Task 1: Status board — `config_validation` field, `record_config_validation`, schema bump

**Files:**
- Modify: `src/led_ticker/status_board.py` (add attrs field, snapshot key, `record_config_validation`, bump `SCHEMA_VERSION`)
- Test: `tests/test_status_board.py`

**Interfaces:**
- Consumes: existing `StatusBoard` (attrs class), `_ACTIVE`, `set_active_board`, `clear_active_board`, `record_reload` (the pattern to mirror), `SCHEMA_VERSION`.
- Produces:
  - `StatusBoard.config_validation: dict[str, Any]` (attrs field, factory=dict) + `"config_validation"` key in `snapshot()`.
  - `record_config_validation(*, errors: list[dict[str, Any]], warnings: list[dict[str, Any]], ts: str) -> None` — sets `_ACTIVE.config_validation = {"at": ts, "errors": errors, "warnings": warnings}` and `publish(force=True)`; no-op when `_ACTIVE is None`; never raises.
  - `SCHEMA_VERSION == 6`.

- [ ] **Step 1: Update the schema tripwire test (RED)**

In `tests/test_status_board.py`, add `"config_validation"` to `EXPECTED_TOP_LEVEL_KEYS` (alongside `"last_reload"`) and change the schema assertion in `test_schema_tripwire` from `== 5` to `== 6`:

```python
# in EXPECTED_TOP_LEVEL_KEYS, add after "last_reload":
    "config_validation",
```
```python
# in test_schema_tripwire, change:
    assert snap["schema"] == SCHEMA_VERSION == 6
```

- [ ] **Step 2: Add the `record_config_validation` tests (RED)**

Append to `tests/test_status_board.py`:

```python
def test_record_config_validation_populates_field(tmp_path):
    from led_ticker.status_board import (
        clear_active_board,
        record_config_validation,
        set_active_board,
    )

    board = _board(tmp_path)
    set_active_board(board)
    try:
        record_config_validation(
            errors=[{"rule": 1, "location": "section[0]", "message": "bad", "fix": "fix it"}],
            warnings=[],
            ts="2026-06-22T13:00:00",
        )
        cv = board.snapshot()["config_validation"]
        assert cv["at"] == "2026-06-22T13:00:00"
        assert cv["errors"][0]["message"] == "bad"
        assert cv["warnings"] == []
    finally:
        clear_active_board()


def test_record_config_validation_no_active_board_is_noop(tmp_path):
    from led_ticker.status_board import clear_active_board, record_config_validation

    clear_active_board()
    # Must not raise with no active board.
    record_config_validation(errors=[], warnings=[], ts="2026-06-22T13:00:00")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: FAIL — `test_schema_tripwire` (snapshot has no `config_validation` key / schema is 5), and the two new tests error on `ImportError: cannot import name 'record_config_validation'`.

- [ ] **Step 4: Bump the schema version**

In `src/led_ticker/status_board.py`, change:
```python
SCHEMA_VERSION = 6
```

- [ ] **Step 5: Add the attrs field**

In `src/led_ticker/status_board.py`, in the `StatusBoard` attrs class, add the field immediately after the existing `last_reload` field:
```python
    config_validation: dict[str, Any] = attrs.field(factory=dict)
```

- [ ] **Step 6: Add the key to `snapshot()`**

In `StatusBoard.snapshot()`, add the key immediately after the `"last_reload": self.last_reload,` line:
```python
            "config_validation": self.config_validation,
```

- [ ] **Step 7: Add `record_config_validation`**

In `src/led_ticker/status_board.py`, immediately after the `record_reload` function, add:
```python
def record_config_validation(
    *,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    ts: str,
) -> None:
    """Record the startup config-validation outcome (this boot's config health).
    Instrumentation only — a no-op with no active board, and never raises into the
    engine. Set once at boot; reloads use `last_reload`, not this field."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.config_validation = {"at": ts, "errors": errors, "warnings": warnings}
        _ACTIVE.publish(force=True)
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: PASS (all, including the updated tripwire and the two new tests).

- [ ] **Step 9: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/status_board.py tests/test_status_board.py
git add src/led_ticker/status_board.py tests/test_status_board.py
git commit --no-verify -m "feat(status): config_validation field + record_config_validation (schema 5->6)"
```

---

### Task 2: Startup validation helpers + wiring into `run()`

**Files:**
- Modify: `src/led_ticker/app/run.py` (add `_serialize_issues`, `_log_validation_report`, `_run_startup_validation`; call it in `run()` after the status board is active)
- Test: `tests/test_startup_validation.py` (new)

**Interfaces:**
- Consumes:
  - `validate_config(path: Path, *, strict: bool = False) -> ValidationResult` from `led_ticker.validate` (async).
  - `ValidationResult` (`.errors`, `.warnings` lists of `ValidationIssue`) and `ValidationIssue` (`.rule`, `.location`, `.message`, `.fix`, `.severity`) from `led_ticker.validate`.
  - `_format_human(result) -> str` from `led_ticker.validate`.
  - `status_board.record_config_validation(*, errors, warnings, ts)` from Task 1.
  - Existing `run.py` imports: `logging`, `from datetime import datetime`, `from led_ticker import status_board`, `Path`.
- Produces:
  - `_serialize_issues(issues: list[Any]) -> list[dict[str, Any]]`
  - `_log_validation_report(result: Any) -> None`
  - `async def _run_startup_validation(config_path: Path) -> None`
  - A single `await _run_startup_validation(config_path)` call in `run()` after `_status_handle = _setup_status_board(...)` (line ~463), so the board is already active.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_startup_validation.py`:
```python
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
    assert out == [{"rule": 1, "location": "loc", "message": "m", "fix": "use rss.feed"}]


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


async def test_run_startup_validation_never_raises_on_validator_error(monkeypatch, caplog):
    from led_ticker import validate as validate_mod

    async def boom(path, **kwargs):
        raise RuntimeError("validator exploded")

    monkeypatch.setattr(validate_mod, "validate_config", boom)
    # Must swallow the error (the sign must still boot).
    with caplog.at_level(logging.WARNING):
        await _run_startup_validation(Path("x.toml"))
    assert any("validator error" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_startup_validation.py -q`
Expected: FAIL — `ImportError: cannot import name '_log_validation_report' from 'led_ticker.app.run'`.

- [ ] **Step 3: Add the three helpers to `run.py`**

In `src/led_ticker/app/run.py`, add these functions near the other module-level helpers (e.g. directly after `_build_trans_obj_guarded`):
```python
def _serialize_issues(issues: list[Any]) -> list[dict[str, Any]]:
    """Flatten ValidationIssue objects to plain dicts for the status board (keeps
    status_board free of validate.py types)."""
    return [
        {"rule": i.rule, "location": i.location, "message": i.message, "fix": i.fix}
        for i in issues
    ]


def _log_validation_report(result: Any) -> None:
    """Log the startup config-validation result: one INFO line when clean, else a
    WARNING summary plus the full human report (reusing validate._format_human)."""
    from led_ticker.validate import _format_human  # noqa: PLC0415

    n_err = len(result.errors)
    n_warn = len(result.warnings)
    if n_err == 0 and n_warn == 0:
        logging.info("config validated — no issues")
        return
    logging.warning(
        "config validation: %d error(s), %d warning(s) — the sign will run, "
        "degrading invalid widgets/transitions; fix and restart (or run "
        "`led-ticker validate`):\n%s",
        n_err,
        n_warn,
        _format_human(result),
    )


async def _run_startup_validation(config_path: Path) -> None:
    """Validate the config once at boot: log the full report and publish it to the
    status board. Never fatal — the sign boots regardless and the build-time guards
    degrade invalid widgets/transitions."""
    from led_ticker.validate import validate_config  # noqa: PLC0415

    try:
        result = await validate_config(config_path)
    except Exception as exc:  # noqa: BLE001 - a validator bug must not stop the sign booting
        logging.warning("startup config validation skipped (validator error): %s", exc)
        return
    _log_validation_report(result)
    status_board.record_config_validation(
        errors=_serialize_issues(result.errors),
        warnings=_serialize_issues(result.warnings),
        ts=datetime.now().isoformat(),
    )
```

Note: `_run_startup_validation` imports `validate_config` locally (PLC0415) and calls `status_board.record_config_validation` via the module reference — this is what makes the test's `monkeypatch.setattr(validate_mod, ...)` / `monkeypatch.setattr(status_board, ...)` work.

- [ ] **Step 4: Wire it into `run()`**

In `src/led_ticker/app/run.py`, find:
```python
    _status_handle = _setup_status_board(config, config_path, plugins)
```
Immediately AFTER that line (the status board is now active, so `record_config_validation` will publish), add:
```python
    # Validate the loaded config once and surface the full report (logs + status
    # board). Never fatal: the build-time guards degrade invalid widgets/transitions,
    # so the sign boots regardless. Runs after plugins load, so installed-plugin
    # types resolve and only genuinely-unknown names flag.
    await _run_startup_validation(config_path)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_startup_validation.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Run the existing app/run tests to confirm no regression**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py -q`
Expected: PASS (no regressions from the `run()` insert).

- [ ] **Step 7: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/app/run.py tests/test_startup_validation.py
git add src/led_ticker/app/run.py tests/test_startup_validation.py
git commit --no-verify -m "feat(run): validate config at startup — log report + status record"
```

---

### Task 3: Web status UI — "Config validation" card

**Files:**
- Modify: `src/led_ticker/webui/static/index.html` (card markup + render JS)
- Test: `tests/test_webui_app.py` (content-presence assertion on the static page)

**Interfaces:**
- Consumes: `status.config_validation` from `/api/status` (the field added in Task 1), the page's existing `$()` and `esc()` helpers, and the `st` status object in the render function.
- Produces: a `#config-validation-card` (hidden by default) populated from `status.config_validation`, mirroring the existing `#last-reload-card`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_webui_app.py`:
```python
def test_index_html_has_config_validation_card():
    from pathlib import Path

    import led_ticker.webui as webui_pkg

    html = (Path(webui_pkg.__file__).parent / "static" / "index.html").read_text()
    # The card exists and the render reads the new status field.
    assert 'id="config-validation-card"' in html
    assert 'id="config-validation-body"' in html
    assert "config_validation" in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py::test_index_html_has_config_validation_card -q`
Expected: FAIL — the card markup / `config_validation` reference is absent.

- [ ] **Step 3: Add the card markup**

In `src/led_ticker/webui/static/index.html`, find the existing reload card:
```html
    <div class="card" id="last-reload-card" style="display:none">
      <strong>Last config reload</strong>
      <div id="last-reload-body"></div>
    </div>
```
Add immediately after it:
```html
    <div class="card" id="config-validation-card" style="display:none">
      <strong>Config validation</strong>
      <div id="config-validation-body"></div>
    </div>
```

- [ ] **Step 4: Add the render JS**

In `src/led_ticker/webui/static/index.html`, find the end of the last-reload render block (the `} else { lrCard.style.display = "none"; }` that closes the `last_reload` rendering). Immediately after that closing brace, add:
```javascript
    const cv = st.config_validation || {};
    const cvCard = $("config-validation-card");
    const cvErrs = cv.errors || [];
    const cvWarns = cv.warnings || [];
    if (cv.at && (cvErrs.length || cvWarns.length)) {
      cvCard.style.display = "";
      let cvHtml = `<p>${cvErrs.length} error(s), ${cvWarns.length} warning(s) · ${esc(cv.at)}</p>`;
      const rows = cvErrs.concat(cvWarns);
      cvHtml += "<table>" + rows
        .map((i) => `<tr><td>${esc(i.location || "")}</td><td class="error">${esc(i.message || "")}</td><td class="muted">${esc(i.fix || "")}</td></tr>`)
        .join("") + "</table>";
      $("config-validation-body").innerHTML = cvHtml;
    } else {
      cvCard.style.display = "none";
    }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py::test_index_html_has_config_validation_card -q`
Expected: PASS.

- [ ] **Step 6: Run the webui test suite to confirm no regression**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py tests/test_webui_purity.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/webui/static/index.html tests/test_webui_app.py
git commit --no-verify -m "feat(webui): Config validation status card"
```

---

## Final verification (before opening the PR)

- [ ] **Full suite + lint**

Run:
```bash
uv run --extra dev ruff check src/ tests/
uv run pytest -q
```
Expected: ruff clean; full suite passes (the existing schema tripwire now asserts 6; no other test asserted schema 5).

- [ ] **Open the PR** (branch off main; do NOT merge without explicit user go-ahead). Summarize: startup validation logs the full report + publishes `config_validation` to the status board; web card surfaces it; log-and-continue (never fatal); schema 5→6.

## Self-Review notes (spec coverage)

- Spec §1 (startup validation step, after plugins+config load, async, never raises) → Task 2 (`_run_startup_validation`, wired after `_setup_status_board`, try/except around `validate_config`).
- Spec §2 (log report: INFO when clean, WARNING summary + `_format_human` when issues) → Task 2 (`_log_validation_report`).
- Spec §3 (`config_validation` field, `record_config_validation`, schema bump, startup-only) → Task 1.
- Spec §4 (web "Config validation" card from `status.config_validation`, hidden when clean) → Task 3.
- Spec testing bullets → Tasks 1–3 test steps. Schema-bump risk (webui tolerates schema 6) is covered because the webui imports `SCHEMA_VERSION` from `status_board` — bumping the constant updates the sidecar's expectation automatically (verified: `webui/__init__.py:74` compares against the imported `SCHEMA_VERSION`).

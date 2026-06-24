# WebUI Reload Confirmation + Config-Dir-Aware Text Validation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two webui bugs — false "unknown font"/asset warnings in the live editor-validate path, and the "reload status unknown — check the sign" message that appears on almost every save.

**Architecture:** (1) Thread the real config dir through `validate_config_text` → `validate_config` so relative-path resolution (fonts + assets + plugin checks) anchors to the real config dir instead of the throwaway temp dir. (2) Extract the display's reload detect-and-apply block into a module-level helper and call it per-section (not just once per playlist cycle), and make the webui's confirmation poll patient (2s interval, ~180s cap).

**Tech Stack:** Python 3.14, asyncio, attrs, aiohttp (webui), pytest (`PYTHONPATH=tests/stubs`), vanilla JS in a single static `index.html`.

## Global Constraints

- Python 3.14 / PEP 649: NO `from __future__ import annotations`.
- Tests run with `make test` (sets `PYTHONPATH=tests/stubs`); no Docker, no hardware.
- Status publishing / `record_reload` shape MUST NOT change (webui reads it).
- Backward compatibility: `validate_config(path)` and `validate_config_text(text)` with NO `config_dir` argument MUST behave exactly as today (anchor to the temp/`path.parent` dir). The CLI (`led-ticker validate`) and `validate_file_handler` rely on this.
- Branch: `fix/webui-reload-and-font-validation` (already created off `main`; spec already committed). Commit per task. Do NOT merge or open a PR without explicit per-PR consent.
- Co-author trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

- `src/led_ticker/validate.py` — add `config_dir` param to `validate_config` + `validate_config_text`; use it for all relative-path resolution. (Task 1)
- `src/led_ticker/app/factories.py` — `_configure_user_font_dir` accepts a directory instead of a config path. (Task 1)
- `src/led_ticker/app/run.py` — `_configure_user_font_dir(config_path.parent)` call updated; reload block extracted to module-level `_detect_and_apply_reload`; called per-section. (Task 1 caller fix + Task 2)
- `src/led_ticker/webui/__init__.py` — `validate_handler` passes `config_dir=config_path.parent`. (Task 1)
- `src/led_ticker/webui/static/index.html` — patient `pollReloadOutcome`. (Task 3)
- `tests/test_validate_text.py` — `config_dir` anchoring tests. (Task 1)
- `tests/test_webui_app.py` — webui `/api/validate` font-resolution test (Task 1) + patient-poll static tripwire (Task 3).
- `tests/test_app.py` — update 3 `_configure_user_font_dir(config_path)` call sites to pass the dir. (Task 1)
- `tests/test_run_reload_helpers.py` — `_detect_and_apply_reload` decision tests + per-section wiring tripwire. (Task 2)

---

## Task 1: Config-dir-aware validation (fixes false font/asset warnings)

**Files:**
- Modify: `src/led_ticker/app/factories.py` (`_configure_user_font_dir`)
- Modify: `src/led_ticker/validate.py` (`validate_config`, `validate_config_text`)
- Modify: `src/led_ticker/webui/__init__.py` (`validate_handler`)
- Modify: `src/led_ticker/app/run.py` (one call site)
- Modify: `tests/test_app.py` (3 call sites)
- Test: `tests/test_validate_text.py`, `tests/test_webui_app.py`

**Interfaces:**
- Produces:
  - `validate_config(path, *, strict=False, config_dir: Path | None = None) -> ValidationResult`
  - `validate_config_text(text, *, strict=False, config_dir: Path | None = None) -> ValidationResult`
  - `_configure_user_font_dir(config_dir: Path) -> None` (now takes the directory, appends `fonts/`)

- [ ] **Step 1: Write the failing test (text path honors config_dir)**

In `tests/test_validate_text.py`, append:

```python
async def test_config_dir_anchors_user_font(tmp_path):
    # A hires font that exists ONLY in the real config dir's fonts/ folder.
    # Without config_dir the text path anchors to a throwaway temp dir and the
    # font reads as "unknown" (rule 24). With config_dir it must resolve clean.
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    # Reuse a bundled hires TTF as a stand-in "user font" named beloved-sans.
    import shutil
    from importlib import resources
    bundled = resources.files("led_ticker.fonts") / "hires" / "Inter-Regular.ttf"
    with resources.as_file(bundled) as src:
        shutil.copy(src, fonts / "beloved-sans.ttf")
    toml = GOOD.replace(
        'text = "hello"',
        'text = "hello"\nfont = "beloved-sans"\nfont_size = 16',
    )
    result = await validate_config_text(toml, config_dir=tmp_path)
    assert not any(w.rule == 24 for w in result.warnings), [
        (w.rule, w.message) for w in result.warnings
    ]


async def test_no_config_dir_keeps_temp_anchoring(tmp_path):
    # Back-compat: with NO config_dir, the same font is unknown (rule 24),
    # because the text path still anchors to the throwaway temp dir.
    toml = GOOD.replace(
        'text = "hello"',
        'text = "hello"\nfont = "beloved-sans"\nfont_size = 16',
    )
    result = await validate_config_text(toml)
    assert any(w.rule == 24 for w in result.warnings)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `make test PYTEST_ARGS="tests/test_validate_text.py::test_config_dir_anchors_user_font -v"`
(or `PYTHONPATH=tests/stubs uv run pytest tests/test_validate_text.py::test_config_dir_anchors_user_font -v`)
Expected: FAIL — `validate_config_text() got an unexpected keyword argument 'config_dir'`.

- [ ] **Step 3: Make `_configure_user_font_dir` take a directory**

In `src/led_ticker/app/factories.py`, change the signature and body. Current:

```python
def _configure_user_font_dir(config_path: Path) -> None:
```
…
```python
    hires_loader.USER_FONT_DIR = (config_path.parent / "fonts").resolve()
    hires_loader.load_hires_font.cache_clear()
```

Replace with:

```python
def _configure_user_font_dir(config_dir: Path) -> None:
```
…
```python
    hires_loader.USER_FONT_DIR = (config_dir / "fonts").resolve()
    hires_loader.load_hires_font.cache_clear()
```

Update the docstring's "based on where `config.toml` actually lives" wording to "based on the config directory" (the argument is now the directory, not the file path). Leave the rest of the docstring intact.

- [ ] **Step 4: Update the two production callers to pass the directory**

In `src/led_ticker/app/run.py`, find:

```python
    _configure_user_font_dir(config_path)
```
Replace with:
```python
    _configure_user_font_dir(config_path.parent)
```

In `src/led_ticker/validate.py`, find:

```python
    _configure_user_font_dir(path)
    build_errors, build_warnings, migration_errors = await _run_build_checks(
        config.sections, path.parent
    )
```
Replace with:
```python
    effective_config_dir = config_dir if config_dir is not None else path.parent
    _configure_user_font_dir(effective_config_dir)
    build_errors, build_warnings, migration_errors = await _run_build_checks(
        config.sections, effective_config_dir
    )
```

- [ ] **Step 5: Add `config_dir` to `validate_config` signature and use it for the remaining checks**

In `src/led_ticker/validate.py`, change:

```python
async def validate_config(path: Path, *, strict: bool = False) -> ValidationResult:
```
to:
```python
async def validate_config(
    path: Path, *, strict: bool = False, config_dir: Path | None = None
) -> ValidationResult:
```

Add to the docstring (after the existing `strict=True` block):

```
    ``config_dir`` overrides the directory used to resolve relative paths
    (fonts, assets, plugin checks). Defaults to ``path.parent`` — pass it when
    the TOML was materialized to a throwaway temp file (the web UI's text
    validate) so resolution anchors to the real config directory.
```

Then find:
```python
        warnings.extend(_check_plugin_validation_warnings(config, path.parent))
```
Replace with:
```python
        warnings.extend(_check_plugin_validation_warnings(config, effective_config_dir))
```

And find:
```python
        errors.extend(_check_asset_paths(config, path.parent))
```
Replace with:
```python
        errors.extend(_check_asset_paths(config, effective_config_dir))
```

(`effective_config_dir` is in scope — it was assigned in Step 4, earlier in the same function.)

- [ ] **Step 6: Thread `config_dir` through `validate_config_text`**

In `src/led_ticker/validate.py`, change:

```python
async def validate_config_text(text: str, *, strict: bool = False) -> ValidationResult:
```
to:
```python
async def validate_config_text(
    text: str, *, strict: bool = False, config_dir: Path | None = None
) -> ValidationResult:
```

And in its body change:
```python
        return await validate_config(p, strict=strict)
```
to:
```python
        return await validate_config(p, strict=strict, config_dir=config_dir)
```

Add one line to the docstring: "Pass ``config_dir`` to anchor relative-path resolution (fonts/assets) at the real config directory rather than the temp dir."

- [ ] **Step 7: Run the Task-1 validate tests**

Run: `make test PYTEST_ARGS="tests/test_validate_text.py -v"`
Expected: PASS (both new tests + the 4 existing parity tests).

- [ ] **Step 8: Wire the webui handler + write its test**

In `src/led_ticker/webui/__init__.py`, find:

```python
        result = await validate_config_text(body)
```
Replace with:
```python
        result = await validate_config_text(body, config_dir=config_path.parent)
```

In `tests/test_webui_app.py`, add a test mirroring the existing `test_validate_good_toml` setup (use that test as the structural reference for building the client + tmp_path config). It must place a font in `<config_dir>/fonts/` and POST a config referencing it, asserting no rule-24 warning in the JSON response:

```python
async def test_validate_resolves_user_font_in_config_dir(tmp_path, aiohttp_client):
    import shutil
    from importlib import resources

    fonts = tmp_path / "fonts"
    fonts.mkdir()
    bundled = resources.files("led_ticker.fonts") / "hires" / "Inter-Regular.ttf"
    with resources.as_file(bundled) as srcf:
        shutil.copy(srcf, fonts / "beloved-sans.ttf")

    # Build the client exactly like test_validate_good_toml does, with the
    # config.toml living in tmp_path so config_path.parent == tmp_path.
    client = await _client_for(tmp_path, aiohttp_client)  # see note below

    toml = (
        "[display]\nrows = 32\ncols = 64\nchain_length = 8\ndefault_scale = 1\n\n"
        '[[playlist.section]]\nmode = "swap"\nhold_time = 3\n\n'
        '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
        'font = "beloved-sans"\nfont_size = 16\n'
    )
    resp = await client.post("/api/validate", data=toml)
    body = await resp.json()
    assert resp.status == 200
    rule_24 = [w for w in body.get("warnings", []) if w.get("rule") == 24]
    assert rule_24 == [], rule_24
```

NOTE for implementer: `test_webui_app.py` already has a helper/fixture pattern that builds the aiohttp client around a tmp config dir (see `test_validate_good_toml` near line 163 and the surrounding client setup). REUSE that exact construction rather than inventing `_client_for` — match the file's established style (it may pass `config_path=tmp_path/"config.toml"` into `build_app`/`serve_webui`). Confirm the config file exists on disk if the app requires it at startup.

- [ ] **Step 9: Update the 3 `_configure_user_font_dir` call sites in `tests/test_app.py`**

In `tests/test_app.py`, there are 3 direct calls `_configure_user_font_dir(config_path)` (around lines 739, 766, 788 — locate each by the exact call text). Change each:

```python
        _configure_user_font_dir(config_path)
```
to:
```python
        _configure_user_font_dir(config_path.parent)
```

(The `mock.patch.object(run_module, "_configure_user_font_dir")` sites do NOT change — they patch, not call.)

- [ ] **Step 10: Run the full affected suites**

Run: `make test PYTEST_ARGS="tests/test_validate_text.py tests/test_webui_app.py tests/test_app.py -v"`
Expected: PASS. If any other test calls `_configure_user_font_dir` positionally with a file path and asserts behavior, fix it the same way (pass `.parent`).

- [ ] **Step 11: Commit**

```bash
git add src/led_ticker/validate.py src/led_ticker/app/factories.py \
        src/led_ticker/app/run.py src/led_ticker/webui/__init__.py \
        tests/test_validate_text.py tests/test_webui_app.py tests/test_app.py
git commit -m "fix(webui): anchor text-validate font/asset resolution to the real config dir

validate_config_text materialized the TOML into a temp dir, so fonts and
assets in the real config/fonts/ resolved as 'unknown' in the editor even
though the inventory listed them. Thread config_dir through
validate_config_text -> validate_config (default path.parent; CLI and
validate-file unchanged). _configure_user_font_dir now takes the directory.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Per-section reload detection (display side of "status unknown")

**Files:**
- Modify: `src/led_ticker/app/run.py` (extract helper + call per-section)
- Test: `tests/test_run_reload_helpers.py`

**Interfaces:**
- Produces (module-level in `run.py`):
  - `class _ReloadResult(typing.NamedTuple): config: Any; default_section_trans: Any; schedule_task: Any`
  - `async def _detect_and_apply_reload(*, watcher, config_path, config, widget_cache, widget_tasks, render_breaker, schedule_task, led_frame) -> _ReloadResult | None` — returns the swap result when a reload was applied, else `None` (no change / transient mid-write / rejected). Records reload status as a side effect, exactly as the old inline block did.

- [ ] **Step 1: Write the failing tests for the helper**

In `tests/test_run_reload_helpers.py`, append. These monkeypatch the reload primitives so the test focuses on the helper's decision + status recording, not `_apply_reload` internals:

```python
import importlib
from types import SimpleNamespace
import pytest

run_mod = importlib.import_module("led_ticker.app.run")


def _new_config():
    # Minimal stand-in: the helper only reads .between_sections, .sections,
    # and optionally ._coerce_warnings.
    return SimpleNamespace(between_sections=None, sections=[], _coerce_warnings=[])


class _Watcher:
    def __init__(self, changed):
        self._changed = changed
    def changed(self):
        return self._changed


@pytest.fixture
def _patched_reload(monkeypatch):
    calls = {"record": []}
    monkeypatch.setattr(
        run_mod, "_build_trans_obj_guarded", lambda cfg: "TRANS", raising=True
    )
    async def _fake_apply(*a, **k):
        return ("SCHED", [])  # (schedule_task, restart_required)
    monkeypatch.setattr(run_mod._reload, "_apply_reload", _fake_apply, raising=True)
    def _rec(*, ok, ts, error="", restart_required=None):
        calls["record"].append({"ok": ok, "error": error,
                                "restart_required": restart_required})
    monkeypatch.setattr(run_mod.status_board, "record_reload", _rec, raising=True)
    return calls


async def test_detect_no_change_returns_none(_patched_reload):
    async def _lv(p):  # not reached when watcher reports no change
        raise AssertionError("load_and_validate should not run")
    res = await run_mod._detect_and_apply_reload(
        watcher=_Watcher(False), config_path=None, config=_new_config(),
        widget_cache={}, widget_tasks={}, render_breaker=None,
        schedule_task=None, led_frame=None,
    )
    assert res is None
    assert _patched_reload["record"] == []


async def test_detect_applies_valid_reload(monkeypatch, _patched_reload):
    new_cfg = _new_config()
    async def _lv(p):
        return (new_cfg, [], False)  # (config, errors, transient)
    monkeypatch.setattr(run_mod._reload, "load_and_validate", _lv, raising=True)
    res = await run_mod._detect_and_apply_reload(
        watcher=_Watcher(True), config_path=None, config=_new_config(),
        widget_cache={}, widget_tasks={}, render_breaker=None,
        schedule_task=None, led_frame=None,
    )
    assert res is not None
    assert res.config is new_cfg
    assert res.default_section_trans == "TRANS"
    assert res.schedule_task == "SCHED"
    assert _patched_reload["record"][-1]["ok"] is True


async def test_detect_rejected_reload_returns_none_records_failure(
    monkeypatch, _patched_reload
):
    async def _lv(p):
        return (None, ["boom"], False)
    monkeypatch.setattr(run_mod._reload, "load_and_validate", _lv, raising=True)
    res = await run_mod._detect_and_apply_reload(
        watcher=_Watcher(True), config_path=None, config=_new_config(),
        widget_cache={}, widget_tasks={}, render_breaker=None,
        schedule_task=None, led_frame=None,
    )
    assert res is None
    assert _patched_reload["record"][-1]["ok"] is False
    assert _patched_reload["record"][-1]["error"] == "boom"


async def test_detect_transient_returns_none_no_record(monkeypatch, _patched_reload):
    async def _lv(p):
        return (None, [], True)  # mid-write
    monkeypatch.setattr(run_mod._reload, "load_and_validate", _lv, raising=True)
    res = await run_mod._detect_and_apply_reload(
        watcher=_Watcher(True), config_path=None, config=_new_config(),
        widget_cache={}, widget_tasks={}, render_breaker=None,
        schedule_task=None, led_frame=None,
    )
    assert res is None
    assert _patched_reload["record"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make test PYTEST_ARGS="tests/test_run_reload_helpers.py -k detect -v"`
Expected: FAIL — `module 'led_ticker.app.run' has no attribute '_detect_and_apply_reload'`.

- [ ] **Step 3: Add the `_ReloadResult` NamedTuple and `_detect_and_apply_reload` helper**

In `src/led_ticker/app/run.py`, add near the other module-level reload helpers (after `_build_trans_obj_guarded`, before `run()`). Use `typing.NamedTuple` (add `import typing` if absent; check the existing imports first and reuse the established style). `datetime` and `logging` are already imported (the old inline block used them).

```python
class _ReloadResult(typing.NamedTuple):
    config: Any
    default_section_trans: Any
    schedule_task: Any


async def _detect_and_apply_reload(
    *,
    watcher: Any,
    config_path: Any,
    config: Any,
    widget_cache: dict,
    widget_tasks: dict,
    render_breaker: Any,
    schedule_task: Any,
    led_frame: Any,
) -> "_ReloadResult | None":
    """Check the watcher; if the config changed and validates, apply it.

    Returns a _ReloadResult (new config + rebuilt section-default transition +
    new schedule task) when a reload was applied, else None for: no change,
    transient mid-write, or a rejected (invalid) config. Records reload status
    as a side effect — moved verbatim from the old inline run-loop block so the
    detection cadence (now per-section) is the only behavior change."""
    if not watcher.changed():
        return None
    new_config, errors, transient = await _reload.load_and_validate(config_path)
    if transient:
        return None  # file mid-write; retry next cycle, no record
    ts = datetime.now().isoformat()
    if new_config is None:
        logging.error("config reload rejected: %s", "; ".join(errors))
        status_board.record_reload(ok=False, ts=ts, error="; ".join(errors))
        return None
    schedule_task, restart_required = await _reload._apply_reload(
        new_config,
        old_config=config,
        widget_cache=widget_cache,
        widget_tasks=widget_tasks,
        render_breaker=render_breaker,
        schedule_task=schedule_task,
        respawn_schedule=lambda ot, cfg: _respawn_schedule(ot, cfg, led_frame),
    )
    default_section_trans = _build_trans_obj_guarded(new_config.between_sections)
    for w in getattr(new_config, "_coerce_warnings", []):
        logging.warning("config coerce: %s", w.message)
    if restart_required:
        logging.warning(
            "config reloaded (partial); restart required for: %s",
            ", ".join(restart_required),
        )
    else:
        logging.info("config reloaded")
    status_board.record_reload(ok=True, ts=ts, restart_required=restart_required)
    return _ReloadResult(
        config=new_config,
        default_section_trans=default_section_trans,
        schedule_task=schedule_task,
    )
```

If `typing` is not already imported in `run.py`, prefer matching the file's convention (it already uses `Any`, so `from typing import Any` exists — extend that import or `import typing`). Verify `Any` is imported; reuse it for the field annotations.

- [ ] **Step 4: Replace the inline outer-loop reload block with a call to the helper**

In `src/led_ticker/app/run.py`, find the existing block at the top of the outer `while True` loop:

```python
                    if watcher.changed():
                        new_config, errors, transient = await _reload.load_and_validate(
                            config_path
                        )
                        if transient:
                            pass  # file mid-write; retry next cycle, no record
                        elif new_config is None:
                            ts = datetime.now().isoformat()
                            logging.error(
                                "config reload rejected: %s", "; ".join(errors)
                            )
                            status_board.record_reload(
                                ok=False, ts=ts, error="; ".join(errors)
                            )
                        else:
                            ts = datetime.now().isoformat()
                            (
                                schedule_task,
                                restart_required,
                            ) = await _reload._apply_reload(
                                new_config,
                                old_config=config,
                                widget_cache=widget_cache,
                                widget_tasks=widget_tasks,
                                render_breaker=render_breaker,
                                schedule_task=schedule_task,
                                respawn_schedule=lambda ot, cfg: _respawn_schedule(
                                    ot, cfg, led_frame
                                ),
                            )
                            default_section_trans = _build_trans_obj_guarded(
                                new_config.between_sections
                            )
                            for w in getattr(new_config, "_coerce_warnings", []):
                                logging.warning("config coerce: %s", w.message)
                            config = new_config  # the swap
                            if restart_required:
                                logging.warning(
                                    "config reloaded (partial); restart required "
                                    "for: %s",
                                    ", ".join(restart_required),
                                )
                            else:
                                logging.info("config reloaded")
                            status_board.record_reload(
                                ok=True, ts=ts, restart_required=restart_required
                            )
```

Replace it with:

```python
                    _reload_res = await _detect_and_apply_reload(
                        watcher=watcher,
                        config_path=config_path,
                        config=config,
                        widget_cache=widget_cache,
                        widget_tasks=widget_tasks,
                        render_breaker=render_breaker,
                        schedule_task=schedule_task,
                        led_frame=led_frame,
                    )
                    if _reload_res is not None:
                        config = _reload_res.config
                        default_section_trans = _reload_res.default_section_trans
                        schedule_task = _reload_res.schedule_task
```

- [ ] **Step 5: Add the per-section reload check**

In `src/led_ticker/app/run.py`, find the section loop head and its restart check:

```python
                    for section_index, section in enumerate(config.sections):
                        # Per-section restart check: caps latency at one
```

Insert the reload check as the FIRST statement inside the `for` loop, before the restart check comment/block:

```python
                    for section_index, section in enumerate(config.sections):
                        # Per-section reload check: caps reload latency at one
                        # section instead of one full playlist cycle, so a save
                        # lands inside the web UI's confirmation window. Applied
                        # at the section seam (never mid-scroll). On a reload we
                        # break to restart the cycle against the new sections.
                        _reload_res = await _detect_and_apply_reload(
                            watcher=watcher,
                            config_path=config_path,
                            config=config,
                            widget_cache=widget_cache,
                            widget_tasks=widget_tasks,
                            render_breaker=render_breaker,
                            schedule_task=schedule_task,
                            led_frame=led_frame,
                        )
                        if _reload_res is not None:
                            config = _reload_res.config
                            default_section_trans = _reload_res.default_section_trans
                            schedule_task = _reload_res.schedule_task
                            break
                        # Per-section restart check: caps latency at one
```

(Keep the existing restart-check block exactly as it was, now following the new reload check.)

- [ ] **Step 6: Add the per-section wiring tripwire**

In `tests/test_run_reload_helpers.py`, append a source-scan guard (house style — mirrors `tests/test_engine_redraw_contract.py`). It prevents a regression to "once per full cycle":

```python
from pathlib import Path


def test_reload_detected_per_section_not_only_per_cycle():
    src = Path(run_mod.__file__).read_text()
    # Helper must be called at the cycle top AND inside the per-section loop.
    assert src.count("_detect_and_apply_reload(") >= 2, (
        "reload helper must be invoked both per-cycle and per-section"
    )
    marker = "for section_index, section in enumerate(config.sections):"
    assert marker in src
    section_region = src[src.index(marker):]
    assert "_detect_and_apply_reload(" in section_region, (
        "per-section reload check is missing — the bug was: reload only "
        "detected once per full playlist cycle"
    )
    # The per-section reload must break to restart the cycle on the new config.
    assert "break" in section_region[: section_region.index("record_section")]
```

- [ ] **Step 7: Run the Task-2 tests**

Run: `make test PYTEST_ARGS="tests/test_run_reload_helpers.py -v"`
Expected: PASS (4 helper decision tests + wiring tripwire + the pre-existing `_respawn_schedule` tests).

- [ ] **Step 8: Run the broader reload/app suites for regressions**

Run: `make test PYTEST_ARGS="tests/test_reload.py tests/test_app.py tests/test_app_runtime_warnings.py -v"`
Expected: PASS. The outer-loop behavior is unchanged (same helper, same record calls); only an additional per-section call was added.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/app/run.py tests/test_run_reload_helpers.py
git commit -m "fix(reload): detect config changes per-section, not once per playlist cycle

watcher.changed() ran only at the top of the outer playlist loop, so a save
landed after the web UI's confirmation window (it usually showed 'reload
status unknown'). Extract the reload detect-and-apply block into
_detect_and_apply_reload and also call it at each section boundary, breaking
to restart the cycle against the new config. Restart already had this
finer-grained treatment; reload now matches.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Patient webui reload confirmation (frontend side of "status unknown")

**Files:**
- Modify: `src/led_ticker/webui/static/index.html`
- Test: `tests/test_webui_app.py`

**Interfaces:**
- Consumes: nothing from other tasks (the display now records reloads faster via Task 2; this widens the window so the confirmation actually lands).
- Produces: `pollReloadOutcome` polling at `RELOAD_POLL_INTERVAL_MS = 2000` for up to `RELOAD_POLL_ATTEMPTS = 90` attempts (~180s), wait message "saved — applying at next section…".

- [ ] **Step 1: Write the failing static tripwire**

In `tests/test_webui_app.py`, append:

```python
def test_reload_poll_is_patient():
    from pathlib import Path
    from led_ticker import webui

    html = (Path(webui.__file__).parent / "static" / "index.html").read_text()
    # Patient poll: ~180s cap at a 2s interval.
    assert "RELOAD_POLL_ATTEMPTS = 90" in html
    assert "RELOAD_POLL_INTERVAL_MS = 2000" in html
    # Honest wait message while the next section seam is reached.
    assert "saved — applying at next section…" in html
    # The old impatient 6s budget (3 attempts) and stale message are gone.
    assert "pollReloadOutcome(priorReloadAt, 3)" not in html
    assert "saved — waiting for reload…" not in html
```

- [ ] **Step 2: Run it to verify it fails**

Run: `make test PYTEST_ARGS="tests/test_webui_app.py::test_reload_poll_is_patient -v"`
Expected: FAIL — the constants/message aren't present yet.

- [ ] **Step 3: Add the poll constants**

In `src/led_ticker/webui/static/index.html`, immediately before the line `$("config-save").onclick = async () => {`, insert:

```javascript
// Reload confirmation polling. The display detects config changes at section
// boundaries (one section's duration), so the confirmation must outlast a slow
// playlist — poll patiently rather than timing out to a scary "unknown".
const RELOAD_POLL_INTERVAL_MS = 2000;
const RELOAD_POLL_ATTEMPTS = 90; // ~180s cap
```

- [ ] **Step 4: Use the constants in the save handler**

In `src/led_ticker/webui/static/index.html`, find:

```javascript
      status.textContent = "saved — applying…";
      setTimeout(() => pollReloadOutcome(priorReloadAt, 3), 1500);
```
Replace with:
```javascript
      status.textContent = "saved — applying…";
      setTimeout(() => pollReloadOutcome(priorReloadAt, RELOAD_POLL_ATTEMPTS), RELOAD_POLL_INTERVAL_MS);
```

- [ ] **Step 5: Make `pollReloadOutcome` patient + honest message**

In `src/led_ticker/webui/static/index.html`, find:

```javascript
    if (!lr.at || lr.at === priorAt) {
      if (attemptsLeft > 0) {
        status.textContent = "saved — waiting for reload…";
        setTimeout(() => pollReloadOutcome(priorAt, attemptsLeft - 1), 1500);
      } else {
        status.textContent = "saved (reload status unknown — check the sign)";
      }
      return;
    }
```
Replace with:
```javascript
    if (!lr.at || lr.at === priorAt) {
      if (attemptsLeft > 0) {
        status.textContent = "saved — applying at next section…";
        setTimeout(() => pollReloadOutcome(priorAt, attemptsLeft - 1), RELOAD_POLL_INTERVAL_MS);
      } else {
        status.textContent = "saved (reload status unknown — check the sign)";
      }
      return;
    }
```

- [ ] **Step 6: Run the tripwire**

Run: `make test PYTEST_ARGS="tests/test_webui_app.py::test_reload_poll_is_patient -v"`
Expected: PASS.

- [ ] **Step 7: Lint/format + full webui suite**

Run: `make format && make lint && make test PYTEST_ARGS="tests/test_webui_app.py -v"`
Expected: PASS, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add src/led_ticker/webui/static/index.html tests/test_webui_app.py
git commit -m "fix(webui): patient reload confirmation poll (2s x ~180s, honest message)

The save handler polled only ~6s (3x1.5s) before giving up to 'reload status
unknown — check the sign', but reloads land at a section boundary. Poll at 2s
up to ~180s and show 'applying at next section…' while waiting; keep the
'unknown' message only as a true-timeout fallback.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all three tasks)

- [ ] Run the full suite: `make test`
  Expected: all pass (~1438+ tests).
- [ ] `make lint` clean.
- [ ] Manual spot-check (optional, documented for the reviewer): with a config dir holding `fonts/beloved-sans.otf`, the editor "Validate" shows no font warning; saving a change shows "applying at next section…" then "applied live ✓" within a section.

---

## Self-Review (completed by plan author)

- **Spec coverage:** Problem 1 → Task 1 (config_dir threading: fonts + assets + plugin checks, back-compat default). Problem 2 display → Task 2 (per-section helper + wiring). Problem 2 webui → Task 3 (2s/180s poll + message). Testing section of spec → tests in each task. Out-of-scope items (status schema, restart, mid-section reload, validate_file_handler) are untouched. ✔
- **Placeholder scan:** No TBD/TODO. The one judgment call (reuse `test_webui_app.py`'s existing client construction in Task 1 Step 8) is flagged explicitly with the reference test name rather than left vague. ✔
- **Type consistency:** `_detect_and_apply_reload` returns `_ReloadResult | None`; callers unpack `.config` / `.default_section_trans` / `.schedule_task`; tests assert the same. `_configure_user_font_dir(config_dir: Path)` is consistent across factories.py, run.py, validate.py, and the test updates. `validate_config(..., config_dir=None)` / `validate_config_text(..., config_dir=None)` consistent across signature, body, and webui caller. ✔

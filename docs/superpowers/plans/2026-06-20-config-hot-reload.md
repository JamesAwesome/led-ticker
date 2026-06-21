# Config Hot-Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Editing `config.toml` while the display runs takes effect without restarting — sections/widgets/transitions/schedule/brightness rebuild at the top of the render cycle; a bad edit is validated, rejected, logged, and surfaced while the old config keeps running.

**Architecture:** A `ConfigWatcher` (mtime + content-hash) polled once per cycle; on a real change, an async `load_and_validate` gates an in-place hot-swap. A testable `_apply_reload` evicts only changed/removed widgets (key-diff, cancelling their captured background tasks), resets the render breaker (+ clears its status mirror), and respawns the schedule ticker. The frame/RGBMatrix, status board, preview tee, and busy-light persist (the frame dropped root and can't rebuild).

**Tech Stack:** Python 3.14, asyncio, attrs, dataclasses, pytest. No new dependencies.

## Global Constraints

- Worktree `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/config-hot-reload`, branch `feat/config-hot-reload` (base `origin/main` @ 3f392ca). **Run `git branch --show-current` before editing; abort if it prints `main`.**
- Run `make dev` (or `uv sync --extra dev`) once before the first commit. Tests: `PYTHONPATH=tests/stubs uv run pytest`.
- Lint/format: `uv run --extra dev ruff check src/ tests/` + `ruff format src/ tests/` (line length 88). Types: `uv run --extra dev pyright src/`.
- **No `from __future__ import annotations` in `src/`** (PEP 649). `asyncio_mode = "auto"` — async tests are bare `async def test_…` (no decorator).
- **Status instrumentation must NEVER raise into the engine** — every `status_board.record_*`/`clear_*` wraps its body in try/except and returns on error.
- **Render constraints (CLAUDE.md):** #1 capture the swap; #12 advance_frame per tick; #13 the frame is built once and drops root (so hardware `[display]` settings cannot hot-reload). The reload swap happens ONLY between cycles, on one consistent `config` object.
- **Validation never raises into the loop:** `load_and_validate` wraps its entire body; a missing file mid-rename is a soft skip, not a crash.
- `git add` new files (check `git status` for `??`). Commit trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh`

## Verified API facts (from the spec + code)

- `validate.validate_config(path, *, strict=False)` is **`async`**, raises `FileNotFoundError` if the path is gone, returns `ValidationResult`.
- `ValidationResult.valid` is a property (`len(errors) == 0`); `.errors` is `list[ValidationIssue]`; `ValidationIssue` has `.rule/.location/.message/.fix/.severity`.
- `config.DisplayConfig` is a dataclass (fields: `rows, cols, …, brightness, …, schedule`). `config.load_config(path)` is sync; the loaded `AppConfig` exposes `_coerce_warnings` (each has `.message`), `display`, `sections`, `busy_light`, `plugins`, and `web` (may be absent — use `getattr`).
- `factories._cache_key(widget_cfg: dict) -> str`; `factories._build_widget(...)` is awaited in run.py.
- `factories.build_frame_from_config(display)` consumes ~19 `display.*` fields (rows, cols, chain_length, parallel, pixel_mapper_config, gpio_slowdown, brightness, hardware_mapping, pwm_bits, pwm_lsb_nanoseconds, pwm_dither_bits, show_refresh_rate, disable_hardware_pulsing, rp1_pio, limit_refresh_rate_hz, multiplexing, row_address_type, panel_type, led_rgb_sequence).
- `widget.spawn_tracked(coro)` adds to the module-global `_BACKGROUND_TASKS`.
- `status_board.SCHEMA_VERSION == 4`; `record_section` uses `_ACTIVE.publish(force=True)`; `_ACTIVE` is the active board or `None`.
- run.py: schedule spawned at `:386–396` (`Scheduler.from_config(config.display.schedule)` → `spawn_tracked(_supervised_schedule(led_frame, sched, config.display.schedule.timezone, config.display.brightness))`); `default_section_trans = _build_trans_obj(config.between_sections)` at `:402`; cache-miss build at `:444–457`; `while True` at `:430`, `for … in enumerate(config.sections)` at `:431`.

---

### Task 1: Status board — `last_reload` + `record_reload` + `clear_disabled_widgets` + schema 5

**Files:**
- Modify: `src/led_ticker/status_board.py`
- Test: `tests/test_status_board.py`

**Interfaces:**
- Produces: `StatusBoard.last_reload: dict[str, Any]`; `snapshot()["last_reload"]`; `SCHEMA_VERSION == 5`; `record_reload(*, ok: bool, ts: str, error: str = "", restart_required: list[str] | None = None) -> None`; `clear_disabled_widgets() -> None`.

- [ ] **Step 1: Update the schema tripwire + add recorder tests (failing)**

In `tests/test_status_board.py`: change the assertion at ~line 43 to `assert snap["schema"] == SCHEMA_VERSION == 5`, and add `"last_reload"` to `EXPECTED_TOP_LEVEL_KEYS` (~line 12). Add:

```python
def test_record_reload_success_appears_in_snapshot():
    from led_ticker import status_board

    board = StatusBoard(path=tmp_path_for("reload1"))  # see note below
    status_board.set_active_board(board)
    try:
        status_board.record_reload(ok=True, ts="2026-06-20T10:00:00",
                                   restart_required=["display.rows"])
    finally:
        status_board.clear_active_board()
    lr = board.snapshot()["last_reload"]
    assert lr["ok"] is True
    assert lr["at"] == "2026-06-20T10:00:00"
    assert lr["restart_required"] == ["display.rows"]


def test_record_reload_failure_carries_error():
    from led_ticker import status_board

    board = StatusBoard(path=tmp_path_for("reload2"))
    status_board.set_active_board(board)
    try:
        status_board.record_reload(ok=False, ts="t", error="section 2: bad widget")
    finally:
        status_board.clear_active_board()
    lr = board.snapshot()["last_reload"]
    assert lr["ok"] is False
    assert lr["error"] == "section 2: bad widget"


def test_clear_disabled_widgets_empties_the_list():
    from types import SimpleNamespace

    from led_ticker import status_board

    board = StatusBoard(path=tmp_path_for("reload3"))
    status_board.set_active_board(board)
    try:
        status_board.record_disabled_widget(SimpleNamespace(text="x"), "boom")
        assert board.snapshot()["disabled_widgets"]  # populated
        status_board.clear_disabled_widgets()
    finally:
        status_board.clear_active_board()
    assert board.snapshot()["disabled_widgets"] == []


def test_record_reload_never_raises_without_active_board():
    from led_ticker import status_board

    status_board.clear_active_board()
    status_board.record_reload(ok=True, ts="t")  # must not raise
    status_board.clear_disabled_widgets()        # must not raise
```

Use the file's existing `tmp_path` convention (the other new tests in this file take a `tmp_path` fixture and build `StatusBoard(path=tmp_path / "status.json")`). Replace the `tmp_path_for(...)` shorthand above with `tmp_path` fixture params per test, matching the existing tests.

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: FAIL (schema is 4; `record_reload`/`clear_disabled_widgets` missing).

- [ ] **Step 3: Implement**

In `src/led_ticker/status_board.py`:

```python
SCHEMA_VERSION = 5
```

Add the field (next to `disabled_widgets`):

```python
    last_reload: dict[str, Any] = attrs.field(factory=dict)
```

Add to `snapshot()` (next to `"disabled_widgets"`):

```python
            "last_reload": self.last_reload,
```

Add the two module functions near `record_disabled_widget`:

```python
def record_reload(
    *,
    ok: bool,
    ts: str,
    error: str = "",
    restart_required: list[str] | None = None,
) -> None:
    """Record the outcome of a config-reload attempt. Instrumentation only —
    never raises into the engine."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.last_reload = {
            "ok": ok,
            "at": ts,
            "error": error,
            "restart_required": list(restart_required or []),
        }
        _ACTIVE.publish(force=True)
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        return


def clear_disabled_widgets() -> None:
    """Empty the disabled-widgets list (called on a successful reload, alongside
    RenderBreaker.reset). Instrumentation only — never raises into the engine."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.disabled_widgets.clear()
        _ACTIVE.publish(force=True)
    except Exception:  # noqa: BLE001
        return
```

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q` → PASS.

- [ ] **Step 5: Check no other test pins schema 4, then lint/typecheck/commit**

Run: `grep -rn "SCHEMA_VERSION == 4\|schema.*== 4" tests/` (update any *status-board* schema pin to 5; the `plugins_catalog` schema is separate — leave it). Then:

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py tests/test_webui_app.py tests/test_status_instrumentation.py -q
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/status_board.py tests/test_status_board.py
git commit -m "feat(status): last_reload snapshot + record_reload + clear_disabled_widgets (schema 5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 2: `RenderBreaker.reset()`

**Files:**
- Modify: `src/led_ticker/render_breaker.py`
- Test: `tests/test_render_breaker.py`

**Interfaces:**
- Produces: `RenderBreaker.reset() -> None` (clears `disabled`).

- [ ] **Step 1: Failing test**

Append to `tests/test_render_breaker.py`:

```python
def test_reset_clears_disabled():
    from types import SimpleNamespace

    b = RenderBreaker()
    w = SimpleNamespace(text="hi")
    b.trip(w, ValueError("boom"))
    assert b.is_disabled(w) is True
    b.reset()
    assert b.is_disabled(w) is False
    assert b.disabled == {}
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker.py -q -k reset` → FAIL (`reset` missing).

- [ ] **Step 3: Implement**

In `src/led_ticker/render_breaker.py`, add to `RenderBreaker`:

```python
    def reset(self) -> None:
        """Clear all disabled state — called on a successful config reload so a
        widget the user just fixed gets another chance (mirrors restart-to-retry)."""
        self.disabled.clear()
```

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_render_breaker.py -q` → PASS.

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/render_breaker.py tests/test_render_breaker.py
git commit -m "feat(engine): RenderBreaker.reset() for config hot-reload

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 3: `hot_reload` field on `DisplayConfig` + config-options docs

**Files:**
- Modify: `src/led_ticker/config.py`
- Modify: `docs/site/src/content/docs/reference/config-options.mdx` (the `[display]` field table — required by the drift test)
- Test: `tests/test_config.py` (+ the existing `tests/test_docs_config_options_drift.py` must pass)

**Interfaces:**
- Produces: `DisplayConfig.hot_reload: bool = True`.

- [ ] **Step 1: Failing test**

Add to `tests/test_config.py`:

```python
def test_display_hot_reload_defaults_true(tmp_path):
    cfg_file = tmp_path / "c.toml"
    cfg_file.write_text('[display]\nrows = 16\ncols = 32\n\n[[section]]\nmode = "swap"\n')
    cfg = load_config(cfg_file)
    assert cfg.display.hot_reload is True


def test_display_hot_reload_can_be_disabled(tmp_path):
    cfg_file = tmp_path / "c.toml"
    cfg_file.write_text(
        '[display]\nrows = 16\ncols = 32\nhot_reload = false\n\n'
        '[[section]]\nmode = "swap"\n'
    )
    cfg = load_config(cfg_file)
    assert cfg.display.hot_reload is False
```

(Match `load_config`'s import + the minimal-config shape other `test_config.py` tests use; adjust the TOML if those tests require more keys.)

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_config.py -q -k hot_reload` → FAIL (`hot_reload` unknown / attribute missing).

- [ ] **Step 3: Implement**

In `src/led_ticker/config.py` `DisplayConfig`, add (near `brightness`):

```python
    hot_reload: bool = True  # watch config.toml + reload sections/widgets/schedule live
```

`hot_reload` is a bool, not an int — confirm the loader passes bool fields through (the `_coerce` loop at `config.py` excludes non-int fields via `_DISPLAY_INT_FIELDS`; `hot_reload` must NOT be in that int set, so it passes through as the parsed TOML bool). If the loader drops unknown keys, ensure `hot_reload` is included the same way other bool `[display]` fields are.

- [ ] **Step 4: Run config test — expect pass; then run the drift test (expect fail until docs updated)**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_config.py -q -k hot_reload` → PASS.
Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_config_options_drift.py -q` → likely FAIL ("`hot_reload` missing from config-options.mdx").

- [ ] **Step 5: Document the field**

In `docs/site/src/content/docs/reference/config-options.mdx`, add `hot_reload` to the `[display]` field table with default `true` and a one-line description: "Watch `config.toml` and live-reload sections/widgets/transitions/schedule/brightness without restarting (hardware `[display]`, `[busy_light]`, `[plugins]`, `[web]` changes still need a restart). Set `false` to disable." Match the table's existing column format.

- [ ] **Step 6: Run drift test — expect pass; commit**

```bash
PYTHONPATH=tests/stubs uv run pytest tests/test_config.py tests/test_docs_config_options_drift.py -q
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
cd docs/site && pnpm run format && pnpm run lint && cd "$(git rev-parse --show-toplevel)"
git add src/led_ticker/config.py tests/test_config.py docs/site/src/content/docs/reference/config-options.mdx
git commit -m "feat(config): [display] hot_reload flag (default on)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 4: Race-free per-widget task capture — `_build_sink` contextvar

**Files:**
- Modify: `src/led_ticker/widget.py`
- Test: `tests/test_widget_spawn_sink.py` (new)

**Interfaces:**
- Produces: `widget._build_sink: contextvars.ContextVar[set | None]`; `spawn_tracked` adds the task to the active sink (if any) AND to `_BACKGROUND_TASKS`.

- [ ] **Step 1: Failing test**

Create `tests/test_widget_spawn_sink.py`:

```python
import asyncio

from led_ticker import widget


async def test_spawn_tracked_lands_in_active_sink():
    sink: set = set()
    token = widget._build_sink.set(sink)
    try:
        t = widget.spawn_tracked(asyncio.sleep(0.01))
    finally:
        widget._build_sink.reset(token)
    assert t in sink
    assert t in widget._BACKGROUND_TASKS
    t.cancel()


async def test_spawn_tracked_no_sink_only_global():
    # no active sink -> only the global registry
    t = widget.spawn_tracked(asyncio.sleep(0.01))
    assert t in widget._BACKGROUND_TASKS
    t.cancel()
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widget_spawn_sink.py -q` → FAIL (`_build_sink` missing).

- [ ] **Step 3: Implement**

In `src/led_ticker/widget.py`, add at module scope (near `_BACKGROUND_TASKS`):

```python
import contextvars

# When set (around a single widget build), spawn_tracked also records the task here
# so the caller can cancel exactly that widget's background tasks on a config reload.
# A ContextVar (not a plain global) so concurrent builds can't cross-contaminate.
_build_sink: contextvars.ContextVar["set[asyncio.Task[Any]] | None"] = (
    contextvars.ContextVar("led_ticker_build_sink", default=None)
)
```

Update `spawn_tracked`:

```python
def spawn_tracked(coro: Any) -> asyncio.Task[Any]:
    """asyncio.create_task + keep a strong reference until the task completes.
    If a build sink is active (config-reload widget build), the task is recorded
    there too so it can be cancelled when that widget is evicted."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    sink = _build_sink.get()
    if sink is not None:
        sink.add(task)
        task.add_done_callback(sink.discard)
    return task
```

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_widget_spawn_sink.py -q` → PASS.

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/widget.py tests/test_widget_spawn_sink.py
git commit -m "feat(engine): per-build task sink in spawn_tracked (reload teardown support)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 5: `reload.py` — `ConfigWatcher`, `load_and_validate`, `nonreloadable_changed` + drift guard

**Files:**
- Create: `src/led_ticker/reload.py`
- Test: `tests/test_reload.py` (new)

**Interfaces:**
- Consumes: `validate.validate_config` (async), `config.load_config`, `config.DisplayConfig`.
- Produces: `ConfigWatcher(path, enabled=True)` with `.changed() -> bool`; `async load_and_validate(path) -> tuple[Any, list[str], bool]`; `RELOADABLE_DISPLAY_FIELDS: frozenset[str]`; `nonreloadable_changed(old, new) -> list[str]`.

- [ ] **Step 1: Failing tests**

Create `tests/test_reload.py`:

```python
import asyncio

import pytest

from led_ticker import reload as rl
from led_ticker.config import load_config


def _write(path, body):
    path.write_text(body)
    return path


_MIN = '[display]\nrows = 16\ncols = 32\n\n[[section]]\nmode = "swap"\n'


def test_watcher_no_change_when_unchanged(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    assert w.changed() is False


def test_watcher_detects_content_change(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    import os, time
    p.write_text(_MIN + "\n# edited\n")
    os.utime(p, (time.time() + 5, time.time() + 5))  # ensure mtime advances
    assert w.changed() is True


def test_watcher_ignores_noop_touch(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    import os, time
    os.utime(p, (time.time() + 5, time.time() + 5))  # mtime bump, identical bytes
    assert w.changed() is False


def test_watcher_disabled_never_changes(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p, enabled=False)
    import os, time
    p.write_text(_MIN + "\n# edited\n")
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert w.changed() is False


def test_watcher_missing_file_no_change(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    p.unlink()
    assert w.changed() is False  # no raise


async def test_load_and_validate_valid(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    cfg, errors, transient = await rl.load_and_validate(p)
    assert cfg is not None and errors == [] and transient is False


async def test_load_and_validate_invalid_returns_string_errors(tmp_path):
    # a config that fails validation (unknown widget type)
    p = _write(tmp_path / "c.toml",
               _MIN + '[[section.widgets]]\ntype = "no_such_widget"\n')
    cfg, errors, transient = await rl.load_and_validate(p)
    assert cfg is None and transient is False
    assert errors and all(isinstance(e, str) for e in errors)


async def test_load_and_validate_missing_file_is_transient(tmp_path):
    cfg, errors, transient = await rl.load_and_validate(tmp_path / "gone.toml")
    assert cfg is None and errors == [] and transient is True


def test_nonreloadable_changed_hardware_field(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    b = load_config(_write(tmp_path / "b.toml",
                           '[display]\nrows = 32\ncols = 32\n\n[[section]]\nmode = "swap"\n'))
    assert "display.rows" in rl.nonreloadable_changed(a, b)


def test_nonreloadable_changed_section_only_is_empty(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    b = load_config(_write(tmp_path / "b.toml",
                           _MIN + '[[section.widgets]]\ntype = "message"\ntext = "hi"\n'))
    assert rl.nonreloadable_changed(a, b) == []


def test_nonreloadable_changed_brightness_is_reloadable(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    b = load_config(_write(tmp_path / "b.toml",
                           '[display]\nrows = 16\ncols = 32\nbrightness = 50\n\n'
                           '[[section]]\nmode = "swap"\n'))
    assert "display.brightness" not in rl.nonreloadable_changed(a, b)


def test_every_frame_field_is_restart_required():
    """Drift guard: every display.* field build_frame_from_config consumes must be
    restart-required (NOT in RELOADABLE_DISPLAY_FIELDS), so a future frame field can
    never be silently treated as hot-reloadable."""
    from dataclasses import fields
    from led_ticker.config import DisplayConfig

    frame_fields = {
        "rows", "cols", "chain_length", "parallel", "pixel_mapper_config",
        "gpio_slowdown", "hardware_mapping", "pwm_bits", "pwm_lsb_nanoseconds",
        "pwm_dither_bits", "show_refresh_rate", "disable_hardware_pulsing",
        "rp1_pio", "limit_refresh_rate_hz", "multiplexing", "row_address_type",
        "panel_type", "led_rgb_sequence",
    }
    declared = {f.name for f in fields(DisplayConfig)}
    # every frame field must actually exist on DisplayConfig (catches renames)
    assert frame_fields <= declared, frame_fields - declared
    # and none of them may be reloadable
    assert frame_fields.isdisjoint(rl.RELOADABLE_DISPLAY_FIELDS)
```

> If the `frame_fields` set drifts from `build_frame_from_config`, this test is the place that fails — update both the set and `build_frame_from_config` together. (The implementer should diff `frame_fields` against the real `display.*` accesses in `factories.build_frame_from_config` and reconcile.)

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_reload.py -q` → FAIL (`No module named 'led_ticker.reload'`).

- [ ] **Step 3: Implement `src/led_ticker/reload.py`**

```python
"""Config hot-reload: change detection, validation, and the field-scope diff.

Editing config.toml while the display runs takes effect at the top of the next
render cycle. Validation gates the swap; a bad/missing config never reaches the
loop (the panel keeps running the old config)."""

import hashlib
import logging
import os
from dataclasses import fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Detect config-file changes by mtime, confirmed by content hash. Disabled ->
    always reports no change. An mtime bump with identical bytes (no-op save) is NOT
    a change, so it won't churn a reload/breaker-reset."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._last_mtime = self._stat_mtime()
        self._last_hash = self._hash()

    def _stat_mtime(self) -> "float | None":
        try:
            return os.stat(self.path).st_mtime
        except OSError:
            return None

    def _hash(self) -> "str | None":
        try:
            return hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return None

    def changed(self) -> bool:
        if not self.enabled:
            return False
        m = self._stat_mtime()
        if m is None or m == self._last_mtime:
            return False
        self._last_mtime = m
        h = self._hash()
        if h is None or h == self._last_hash:
            return False
        self._last_hash = h
        return True


async def load_and_validate(path: Path) -> "tuple[Any, list[str], bool]":
    """Validate then load. Returns (config, errors, transient):
      (config, [], False)  -> success
      (None, [msgs], False) -> rejected; record + keep old config
      (None, [], True)     -> transient (file mid-rename); soft skip, retry next cycle
    NEVER raises — a bad/missing config must not reach the render loop."""
    from led_ticker.validate import validate_config  # noqa: PLC0415
    from led_ticker.config import load_config  # noqa: PLC0415

    try:
        result = await validate_config(path)
    except FileNotFoundError:
        return None, [], True
    except Exception as exc:  # noqa: BLE001 - validation must never crash the loop
        return None, [f"{type(exc).__name__}: {exc}"], False
    if not result.valid:
        return None, [f"{i.location}: {i.message}" for i in result.errors], False
    try:
        return load_config(path), [], False
    except FileNotFoundError:
        return None, [], True
    except Exception as exc:  # noqa: BLE001
        return None, [f"{type(exc).__name__}: {exc}"], False


# The ONLY hot-reloadable [display] fields. Everything else feeds the frame at build
# time (built once, root dropped) and is restart-required. brightness is a live
# matrix setter; schedule is driven by the schedule ticker; hot_reload is meta.
RELOADABLE_DISPLAY_FIELDS = frozenset({"schedule", "hot_reload", "brightness"})


def nonreloadable_changed(old: Any, new: Any) -> "list[str]":
    """Names of restart-required fields that differ between old and new config.
    Derived from the dataclass fields (NOT hand-listed) so a new DisplayConfig field
    is restart-required by default. Empty -> a fully-reloadable change."""
    changed: list[str] = []
    for f in fields(type(new.display)):
        if f.name in RELOADABLE_DISPLAY_FIELDS:
            continue
        if getattr(old.display, f.name, None) != getattr(new.display, f.name, None):
            changed.append(f"display.{f.name}")
    if old.busy_light != new.busy_light:
        changed.append("busy_light")
    if old.plugins != new.plugins:
        changed.append("plugins")
    if getattr(old, "web", None) != getattr(new, "web", None):
        changed.append("web")
    return changed
```

> Use string annotations only where a `|` union of a runtime value is needed inline; the file otherwise has no `from __future__ import annotations`. (The shown quoted annotations satisfy pyright without that import.)
> Verify `busy_light`/`plugins`/`web` config objects compare by value (dataclasses with default `eq`). If any is not value-comparable, the implementer gives it `eq=True` or compares a normalized form — note in the report.

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_reload.py -q` → PASS (all). If `test_load_and_validate_invalid_returns_string_errors` doesn't trigger an error with `no_such_widget`, swap in any reliably-invalid config (e.g. a removed knob that raises a MigrationError) — the assertion is on shape (`None` + string errors), not the specific message.

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/reload.py tests/test_reload.py
git commit -m "feat(reload): ConfigWatcher + load_and_validate + restart-field diff

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 6: `reload._apply_reload` — eviction + breaker reset + schedule respawn

**Files:**
- Modify: `src/led_ticker/reload.py`
- Test: `tests/test_reload.py`

**Interfaces:**
- Consumes: `factories._cache_key`, `render_breaker.RenderBreaker.reset`, `status_board.clear_disabled_widgets`, `nonreloadable_changed`.
- Produces: `async _apply_reload(new_config, *, old_config, widget_cache, widget_tasks, render_breaker, schedule_task, respawn_schedule) -> tuple[Any, list[str]]` returning `(schedule_task, restart_required)`. `respawn_schedule` is an async callable `(old_task, new_config) -> task | None` (injected so the helper is testable without run.py).

- [ ] **Step 1: Failing test**

Append to `tests/test_reload.py`:

```python
from led_ticker import reload as rl
from led_ticker import status_board
from led_ticker.render_breaker import RenderBreaker
from led_ticker.config import load_config


async def test_apply_reload_evicts_changed_keeps_unchanged(tmp_path):
    # config A: one message widget "keep" + one "drop"
    a = load_config(_write(tmp_path / "a.toml",
        '[display]\nrows=16\ncols=32\n\n[[section]]\nmode="swap"\n'
        '[[section.widgets]]\ntype="message"\ntext="keep"\n'
        '[[section.widgets]]\ntype="message"\ntext="drop"\n'))
    # config B: "keep" stays, "drop" removed
    b = load_config(_write(tmp_path / "b.toml",
        '[display]\nrows=16\ncols=32\n\n[[section]]\nmode="swap"\n'
        '[[section.widgets]]\ntype="message"\ntext="keep"\n'))

    from led_ticker.app.factories import _cache_key
    keep_key = _cache_key(dict(a.sections[0].widgets[0]))
    drop_key = _cache_key(dict(a.sections[0].widgets[1]))

    keep_task = asyncio.ensure_future(asyncio.sleep(3600))
    drop_task = asyncio.ensure_future(asyncio.sleep(3600))
    widget_cache = {keep_key: object(), drop_key: object()}
    widget_tasks = {keep_key: {keep_task}, drop_key: {drop_task}}
    keep_widget = widget_cache[keep_key]

    breaker = RenderBreaker()
    from types import SimpleNamespace
    breaker.trip(SimpleNamespace(text="x"), ValueError("boom"))

    respawned = []
    async def fake_respawn(old_task, cfg):
        respawned.append(cfg)
        return "NEW_SCHEDULE_TASK"

    new_sched, restart = await rl._apply_reload(
        b, old_config=a, widget_cache=widget_cache, widget_tasks=widget_tasks,
        render_breaker=breaker, schedule_task="OLD", respawn_schedule=fake_respawn)

    # unchanged widget + its task survive; removed widget + task evicted/cancelled
    assert keep_key in widget_cache and widget_cache[keep_key] is keep_widget
    assert drop_key not in widget_cache and drop_key not in widget_tasks
    assert drop_task.cancelled() or drop_task.cancelling()  # cancel requested
    assert not keep_task.cancelled()
    keep_task.cancel()
    # breaker reset + schedule respawned + no restart_required (section-only change)
    assert breaker.disabled == {}
    assert new_sched == "NEW_SCHEDULE_TASK" and respawned == [b]
    assert restart == []


async def test_apply_reload_reports_restart_required(tmp_path):
    a = load_config(_write(tmp_path / "a.toml",
        '[display]\nrows=16\ncols=32\n\n[[section]]\nmode="swap"\n'))
    b = load_config(_write(tmp_path / "b.toml",
        '[display]\nrows=32\ncols=32\n\n[[section]]\nmode="swap"\n'))

    async def fake_respawn(old_task, cfg):
        return None

    _, restart = await rl._apply_reload(
        b, old_config=a, widget_cache={}, widget_tasks={},
        render_breaker=RenderBreaker(), schedule_task=None, respawn_schedule=fake_respawn)
    assert "display.rows" in restart
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_reload.py -q -k apply_reload` → FAIL (`_apply_reload` missing).

- [ ] **Step 3: Implement**

Append to `src/led_ticker/reload.py`:

```python
async def _apply_reload(
    new_config: Any,
    *,
    old_config: Any,
    widget_cache: dict,
    widget_tasks: dict,
    render_breaker: Any,
    schedule_task: Any,
    respawn_schedule: Any,
) -> "tuple[Any, list[str]]":
    """Apply a validated new config in place. Evicts changed/removed widgets
    (cancelling their captured background tasks), resets the render breaker and its
    status mirror, and respawns the schedule ticker. Returns (schedule_task,
    restart_required). The CALLER swaps `config`, rebuilds the section-default
    transition, drains coerce warnings, logs, and records status."""
    from led_ticker import status_board  # noqa: PLC0415
    from led_ticker.app.factories import _cache_key  # noqa: PLC0415

    restart_required = nonreloadable_changed(old_config, new_config)

    valid_keys = {
        _cache_key(dict(w)) for s in new_config.sections for w in s.widgets
    }
    for key in list(widget_cache):
        if key not in valid_keys:
            for t in widget_tasks.pop(key, ()):
                t.cancel()  # cancel-and-move-on; not awaited at the boundary
            widget_cache.pop(key, None)

    render_breaker.reset()
    status_board.clear_disabled_widgets()
    schedule_task = await respawn_schedule(schedule_task, new_config)
    return schedule_task, restart_required
```

> `_cache_key` takes a `dict`; section widget entries may be mapping-like — wrap with `dict(w)` exactly as run.py's cache-miss path does (`cfg = dict(widget_cfg)`). The implementer matches run.py's key computation so keys align with the live cache.

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_reload.py -q` → PASS.
(If `drop_task.cancelling()` isn't available on the runtime, assert `drop_task.cancel()` was effective by `await asyncio.sleep(0)` then `drop_task.cancelled()`.)

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/reload.py tests/test_reload.py
git commit -m "feat(reload): _apply_reload — key-diff eviction + breaker reset + schedule respawn

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 7: run.py helpers — `_respawn_schedule` + `_build_widget_guarded`

**Files:**
- Modify: `src/led_ticker/app/run.py`
- Test: `tests/test_run_reload_helpers.py` (new)

**Interfaces:**
- Consumes: `_supervised_schedule`, `Scheduler.from_config`, `spawn_tracked`, `_build_widget`, `_cache_key`, `widget._build_sink`.
- Produces: `async _respawn_schedule(old_task, config, led_frame) -> task | None`; `async _build_widget_guarded(widget_cfg, *, session, config_dir, default_bg_color, panel_h_for_warning, coercion_collector, widget_cache, widget_tasks) -> Any | None` (None = build failed/skipped).

- [ ] **Step 1: Failing tests**

Create `tests/test_run_reload_helpers.py`:

```python
import asyncio
from types import SimpleNamespace

from led_ticker.app import run as run_mod


class _FakeMatrix:
    def __init__(self):
        self.brightness = 100


def _frame():
    return SimpleNamespace(matrix=_FakeMatrix())


def _cfg(*, enabled, brightness=100, tz="UTC"):
    sched = SimpleNamespace(enabled=enabled, timezone=tz)
    return SimpleNamespace(display=SimpleNamespace(schedule=sched, brightness=brightness))


async def test_respawn_schedule_disabled_sets_base_and_returns_none():
    frame = _frame()
    old = asyncio.ensure_future(asyncio.sleep(3600))
    task = await run_mod._respawn_schedule(old, _cfg(enabled=False, brightness=40), frame)
    assert task is None
    assert frame.matrix.brightness == 40
    assert old.cancelled() or old.cancelling()


async def test_respawn_schedule_enabled_spawns_and_cancels_old():
    frame = _frame()
    old = asyncio.ensure_future(asyncio.sleep(3600))
    task = await run_mod._respawn_schedule(old, _cfg(enabled=True), frame)
    assert task is not None and not task.done()
    assert old.cancelled() or old.cancelling()
    task.cancel()


async def test_build_widget_guarded_skips_on_build_error(monkeypatch):
    async def boom(*a, **k):
        raise ValueError("bad widget cfg")

    monkeypatch.setattr(run_mod, "_build_widget", boom)
    cache, tasks = {}, {}
    out = await run_mod._build_widget_guarded(
        {"type": "message", "text": "x"}, session=None, config_dir=None,
        default_bg_color=None, panel_h_for_warning=None, coercion_collector=[],
        widget_cache=cache, widget_tasks=tasks)
    assert out is None          # skipped, not raised
    assert cache == {} and tasks == {}  # not cached


async def test_build_widget_guarded_caches_on_success(monkeypatch):
    sentinel = object()

    async def ok(*a, **k):
        return sentinel

    monkeypatch.setattr(run_mod, "_build_widget", ok)
    cache, tasks = {}, {}
    cfg = {"type": "message", "text": "x"}
    out = await run_mod._build_widget_guarded(
        cfg, session=None, config_dir=None, default_bg_color=None,
        panel_h_for_warning=None, coercion_collector=[],
        widget_cache=cache, widget_tasks=tasks)
    assert out is sentinel
    assert len(cache) == 1 and len(tasks) == 1  # cached + sink recorded
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_run_reload_helpers.py -q` → FAIL (helpers missing).

- [ ] **Step 3: Implement the helpers in `src/led_ticker/app/run.py`**

Add near the other module-level helpers (after `_supervised_schedule`). Import `_build_sink` from `led_ticker.widget` (extend the existing `from led_ticker.widget import …` line to include `_build_sink`).

```python
async def _respawn_schedule(old_task: Any, config: Any, led_frame: Any) -> Any:
    """Cancel the running schedule ticker (if any) and start a fresh one from the
    new config. Disabled -> set brightness to the new base and return None."""
    if old_task is not None:
        old_task.cancel()
        await asyncio.sleep(0)  # let the old ticker observe the cancel before respawn
    if config.display.schedule.enabled:
        from led_ticker.schedule import Scheduler  # noqa: PLC0415

        sched = Scheduler.from_config(config.display.schedule)
        return spawn_tracked(
            _supervised_schedule(
                led_frame,
                sched,
                config.display.schedule.timezone,
                config.display.brightness,
            )
        )
    led_frame.matrix.brightness = config.display.brightness
    return None


async def _build_widget_guarded(
    widget_cfg: Any,
    *,
    session: Any,
    config_dir: Any,
    default_bg_color: Any,
    panel_h_for_warning: Any,
    coercion_collector: Any,
    widget_cache: dict,
    widget_tasks: dict,
) -> Any:
    """Build one widget (cache-aware), capturing its background tasks in a per-build
    sink so a config reload can cancel exactly those. On a build error, log + skip
    (return None) without caching, so a later good edit retries. Returns the widget
    or None."""
    key = _cache_key(widget_cfg)
    if key in widget_cache:
        return widget_cache[key]
    sink: set = set()
    token = _build_sink.set(sink)
    try:
        widget = await _build_widget(
            dict(widget_cfg),
            session,
            config_dir=config_dir,
            default_bg_color=default_bg_color,
            panel_h_for_warning=panel_h_for_warning,
            coercion_collector=coercion_collector,
        )
    except Exception as exc:  # noqa: BLE001 - a bad reloaded widget must not freeze the panel
        logging.exception("widget build failed; skipping for this pass: %s", exc)
        for t in sink:
            t.cancel()
        return None
    finally:
        _build_sink.reset(token)
    widget_cache[key] = widget
    widget_tasks[key] = sink
    return widget
```

> Match `_build_widget`'s real keyword arguments to the existing cache-miss call (run.py ~`:447–456`): `dict(widget_cfg)` positional, then `session`, `config_dir=`, `default_bg_color=`, `panel_h_for_warning=`, `coercion_collector=`. Keep them identical so behavior is unchanged for the success path.

- [ ] **Step 4: Run — expect pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_run_reload_helpers.py -q` → PASS.

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/app/run.py tests/test_run_reload_helpers.py
git commit -m "feat(run): _respawn_schedule + _build_widget_guarded helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 8: run.py wiring — schedule handle, watcher, the reload sequence

**Files:**
- Modify: `src/led_ticker/app/run.py`
- Test: `tests/test_run_reload_helpers.py` (wiring tripwire)

**Interfaces:**
- Consumes: `reload.ConfigWatcher`, `reload.load_and_validate`, `reload._apply_reload`, `_respawn_schedule`, `_build_widget_guarded`.

- [ ] **Step 1: Wiring tripwire test (failing)**

Append to `tests/test_run_reload_helpers.py`:

```python
def test_run_wires_the_reload_sequence():
    import inspect
    from led_ticker.app import run as run_mod

    src = inspect.getsource(run_mod.run)
    assert "ConfigWatcher(" in src           # watcher created
    assert "load_and_validate(" in src       # validate gate
    assert "_apply_reload(" in src           # the swap
    assert "record_reload(" in src           # status surfacing
    assert "_build_widget_guarded(" in src   # cache-miss build goes through the guard
```

- [ ] **Step 2: Run — expect failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_run_reload_helpers.py -q -k wires` → FAIL.

- [ ] **Step 3: Wire `run()`**

In `src/led_ticker/app/run.py`:

(a) Imports: add `from led_ticker import reload as _reload` and `from led_ticker import status_board` (if not already imported), and `from datetime import datetime` (verify it's imported).

(b) **Capture the schedule task handle.** Replace the schedule spawn (`:386–396`) so the task is stored:

```python
        schedule_task: Any = None
        if config.display.schedule.enabled:
            from led_ticker.schedule import Scheduler  # noqa: PLC0415

            sched = Scheduler.from_config(config.display.schedule)
            schedule_task = spawn_tracked(
                _supervised_schedule(
                    led_frame,
                    sched,
                    config.display.schedule.timezone,
                    config.display.brightness,
                )
            )
```

(c) **Create the watcher** after `default_section_trans`/`panel_h_for_warning` are set, before `async with aiohttp.ClientSession()`:

```python
        watcher = _reload.ConfigWatcher(config_path, enabled=config.display.hot_reload)
```

And create `widget_tasks` immediately next to the existing `widget_cache` declaration (run.py `:421`, inside the `async with`), so they share scope:

```python
            widget_cache: dict[str, Any] = {}
            widget_tasks: dict[str, set] = {}
```

(d) **Replace the cache-miss build** inside the section loop (`:444–457`) with the guarded helper, threading `widget_tasks`; skip a `None` (failed) widget:

```python
                        for widget_cfg in section.widgets:
                            widget = await _build_widget_guarded(
                                widget_cfg,
                                session=session,
                                config_dir=config_path.parent,
                                default_bg_color=section.bg_color,
                                panel_h_for_warning=panel_h_for_warning,
                                coercion_collector=runtime_coerce,
                                widget_cache=widget_cache,
                                widget_tasks=widget_tasks,
                            )
                            if widget is None:
                                continue  # build failed; skip this widget this pass
                            widgets.append(widget)
```

(e) **Insert the reload sequence** at the very top of `while True:`, before `for section_index, …`:

```python
                while True:
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
                            schedule_task, restart_required = await _reload._apply_reload(
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
                            default_section_trans = _build_trans_obj(
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
                    for section_index, section in enumerate(config.sections):
                        ...  # unchanged existing loop body
```

> `render_breaker` is the run-scoped breaker already created earlier in `run()` (from #6). `config` and `default_section_trans` are reassigned here — confirm they're plain locals (they are). Use `datetime.now()` (the schedule's tz handling stays inside `_supervised_schedule`; the reload timestamp is wall-clock-local, which is fine for a status string).

- [ ] **Step 4: Run wiring test + full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_run_reload_helpers.py -q` → PASS.
Run: `PYTHONPATH=tests/stubs uv run pytest -q` → full suite green (the loop change must not regress existing engine/app tests — especially `tests/test_container_refresh.py`, which asserts the section loop re-reads `feed_stories`; the guarded build preserves the same cache + container behavior).

- [ ] **Step 5: Lint/typecheck/commit**

```bash
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/
git add src/led_ticker/app/run.py tests/test_run_reload_helpers.py
git commit -m "feat(run): wire config hot-reload into the render loop

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 9: Docs — web-status `last_reload` + hot-reload concept page

**Files:**
- Modify: `docs/site/src/content/docs/concepts/web-status-ui.mdx`
- Modify: `src/led_ticker/webui/static/index.html`
- Create/Modify: a hot-reload usage note (a short section on an existing concepts page, e.g. the config/usage page, or a new `concepts/hot-reload.mdx` if the sidebar has a natural slot)

**Interfaces:** none (docs + static UI).

- [ ] **Step 1: Render `last_reload` in the web UI**

In `src/led_ticker/webui/static/index.html`, add a render block for `st.last_reload` mirroring the existing `disabled_widgets`/`failed_plugins` blocks: when present, show a card/line with the timestamp (`at`), OK/failed state, the `error` (if any), and `restart_required` fields (if any). Match the file's existing JS/markup style. Hidden when `last_reload` is empty.

- [ ] **Step 2: Document `last_reload` + the feature**

In `docs/site/src/content/docs/concepts/web-status-ui.mdx`, next to `disabled_widgets`, add `last_reload`: "the outcome of the most recent config hot-reload — `{ ok, at, error, restart_required }`. A failed reload shows the validation error verbatim; `restart_required` lists fields (hardware `[display]`, `[busy_light]`, `[plugins]`, `[web]`) that need a restart to take effect."

Add a concise hot-reload usage note (on the config/usage concepts page or a new short page): editing `config.toml` while running reloads sections/widgets/transitions/schedule/brightness at the next cycle (on by default; `[display] hot_reload = false` to disable); a bad edit is rejected and logged while the old config keeps running; hardware/busy/plugins/web changes need a restart; in Docker the read-only bind-mount still reflects host edits; feedback appears in the logs (`journalctl`) and the web status `last_reload`.

- [ ] **Step 3: Docs/UI lint + commit**

```bash
cd docs/site && pnpm install >/dev/null 2>&1; pnpm run format && pnpm run lint && cd "$(git rev-parse --show-toplevel)"
git add docs/site/src/content/docs/concepts/web-status-ui.mdx src/led_ticker/webui/static/index.html docs/site/src/content/docs/
git commit -m "docs(reload): document config hot-reload + last_reload status

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

## Final verification (after all tasks)

- [ ] `PYTHONPATH=tests/stubs uv run pytest -q` — full suite green.
- [ ] `uv run --extra dev ruff check src/ tests/` + `ruff format --check src/ tests/` — clean.
- [ ] `uv run --extra dev pyright src/` — 0 errors.
- [ ] `cd docs/site && pnpm run lint` — clean.
- [ ] `git status` — no untracked (`??`) files.
- [ ] Push, open a PR against `main`, wait for CI green before requesting merge.

## Notes / gotchas

- The reload swap happens ONLY at the top of `while True`, between full cycles — never mid-render (constraints #1/#12). The running cycle always finishes on one consistent `config`.
- `validate_config` is async + raises `FileNotFoundError`; `load_and_validate` awaits it and wraps every exception so nothing propagates into the loop.
- `ValidationResult.errors` are `ValidationIssue` dataclasses — format to strings (`f"{i.location}: {i.message}"`) before logging/joining.
- The restart-required set is DERIVED (`fields(DisplayConfig) - RELOADABLE_DISPLAY_FIELDS`); the drift-guard test (Task 5) fails if a frame field becomes silently reloadable.
- Evicted widget tasks are `.cancel()`-ed but NOT awaited at the boundary (cancel-and-move-on) so teardown can't stall the loop.
- `_build_widget_guarded` build failures log + skip + don't cache (a later good edit retries); they never freeze the panel (the #6 breaker only guards render, not build).
- Status instrumentation (`record_reload`, `clear_disabled_widgets`) never raises into the loop.
- `_cache_key` takes a `dict`; compute it the same way the live cache-miss path does (`dict(widget_cfg)`), so keys align.
- Watch the existing `tests/test_container_refresh.py` AST/behavioral tripwire — the guarded build must keep the cache + container-expansion behavior identical.

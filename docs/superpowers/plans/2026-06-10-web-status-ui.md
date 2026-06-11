# Web Status UI Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only web status UI delivered as an unprivileged sidecar (`led-ticker webui`): the display process publishes a versioned `status.json`; the sidecar serves a tabbed Status/Config/Validate page plus a JSON API.

**Architecture:** Two processes, one image. The display process gains a `StatusBoard` that atomically publishes throttled JSON snapshots at engine boundaries (never per-tick) and disables itself on any failure. The sidecar (aiohttp, same shape as `busy_http`) reads that file, serves the live config redacted, and runs the validate engine on posted TOML. No write path to the display.

**Tech Stack:** Python 3.14, aiohttp (already a dep), attrs, stdlib tomllib/json. Frontend is one static HTML file with vanilla JS — no build step.

**Spec:** `docs/superpowers/specs/2026-06-10-web-status-ui-design.md`

**Worktree notes (read first):**
- Work in `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/web-status-ui`, branch `feat/web-status-ui-spec`. Run `git branch --show-current` and ABORT if it prints `main`.
- The venv must exist: `make dev` may fail at the `pre-commit install` step with a `core.hooksPath` error — that's fine, `uv sync --extra dev` (the first half) is what matters and has already run.
- The pre-commit hook needs `pre-commit` on PATH. Commit with: `PATH="$PWD/.venv/bin:$PATH" git commit -m "..."`.
- Run tests with: `PYTHONPATH=tests/stubs uv run pytest <file> -v` (the stubs provide `rgbmatrix`).
- Lint before any push: `uv run --extra dev ruff check src/ tests/`.

**File structure (locked in here):**

| File | Responsibility |
|---|---|
| `src/led_ticker/config.py` (modify) | `WebConfig` dataclass, `read_web_config()` lightweight reader, wired into `load_config` |
| `src/led_ticker/status_board.py` (create) | `StatusBoard` (snapshot/publish/throttle), `StatusLogHandler`, module-level active-board API |
| `src/led_ticker/webui/__init__.py` (create) | `build_webui_app()` (pure), `serve_webui()`, `run_webui()` |
| `src/led_ticker/webui/redact.py` (create) | `redact_toml()` pure function |
| `src/led_ticker/webui/static/index.html` (create) | The tabbed page |
| `src/led_ticker/widget.py` (modify) | `run_monitor_loop` records monitor updates |
| `src/led_ticker/ticker.py` (modify) | `_show_one` records widget visits |
| `src/led_ticker/app/run.py` (modify) | Build board, startup/section records, log handler |
| `src/led_ticker/validate.py` (modify) | `validate_config_text()` from-string entry point |
| `src/led_ticker/app/cli.py` (modify) | `webui` subcommand |
| `compose.yaml`, `deploy/led-ticker-webui.service`, `config/config.example.toml` (modify/create) | Deployment |
| `docs/site/.../reference/config-options.mdx`, `tests/test_docs_config_options_drift.py`, new docs page (modify/create) | Docs + drift guard |

---

### Task 1: `WebConfig` + `read_web_config`

**Files:**
- Modify: `src/led_ticker/config.py` (dataclass near `BusyLightConfig` ~line 154; parse inside `load_config` ~line 382; `web` field on `AppConfig` ~line 216)
- Test: `tests/test_web_config.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the [web] config block."""

import pytest

from led_ticker.config import WebConfig, load_config, read_web_config

MINIMAL = """
[display]
rows = 16
cols = 32

[[playlist.section]]
mode = "forever_scroll"
[[playlist.section.widgets]]
type = "message"
text = "hi"
"""


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(body)
    return p


def test_absent_web_block_is_none(tmp_path):
    cfg = load_config(_write(tmp_path, MINIMAL))
    assert cfg.web is None


def test_web_block_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, MINIMAL + "\n[web]\n"))
    assert cfg.web == WebConfig()
    assert cfg.web.host == "0.0.0.0"
    assert cfg.web.port == 8080
    assert cfg.web.token == ""
    assert cfg.web.status_path == "/run/led-ticker/status.json"


def test_web_block_explicit_values(tmp_path):
    body = MINIMAL + '\n[web]\nhost = "127.0.0.1"\nport = 9090\ntoken = "s3cret"\nstatus_path = "/tmp/s.json"\n'
    cfg = load_config(_write(tmp_path, body))
    assert cfg.web == WebConfig(
        host="127.0.0.1", port=9090, token="s3cret", status_path="/tmp/s.json"
    )


@pytest.mark.parametrize(
    "field_line, match",
    [
        ("port = 0", "web.port"),
        ("port = 70000", "web.port"),
        ("token = 5", "web.token"),
        ('status_path = ""', "web.status_path"),
        ("host = 1", "web.host"),
    ],
)
def test_web_block_invalid_values_raise(tmp_path, field_line, match):
    with pytest.raises(ValueError, match=match):
        load_config(_write(tmp_path, MINIMAL + f"\n[web]\n{field_line}\n"))


def test_read_web_config_lightweight(tmp_path):
    # read_web_config must work even when the playlist is invalid —
    # the sidecar serves the validate tab precisely when the config is broken.
    broken = '[web]\nport = 9090\n\n[[playlist.section]]\nmode = "swap"\n'
    assert read_web_config(_write(tmp_path, broken)) == WebConfig(port=9090)


def test_read_web_config_absent_block(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[display]\nrows = 16\n')
    assert read_web_config(p) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_web_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'WebConfig'`

- [ ] **Step 3: Implement**

In `src/led_ticker/config.py`, after `BusyLightConfig`:

```python
@dataclass
class WebConfig:
    """The [web] block: status publishing + the `led-ticker webui` sidecar.

    Presence of the block (even empty) enables status publishing in the
    display process. Absence disables it entirely — zero new behavior for
    existing configs.
    """

    host: str = "0.0.0.0"
    port: int = 8080
    token: str = ""  # empty = open; non-empty enables auth on every route
    status_path: str = "/run/led-ticker/status.json"


def _parse_web_block(raw: dict) -> WebConfig | None:
    """Parse + validate the [web] table. Returns None when the block is
    absent. Shared by load_config and read_web_config (the sidecar's
    lightweight reader, which must work on configs whose playlist is
    broken — that's exactly when the validate tab is needed)."""
    if "web" not in raw:
        return None
    w_raw = raw["web"]
    cfg = WebConfig(
        host=w_raw.get("host", "0.0.0.0"),
        port=w_raw.get("port", 8080),
        token=w_raw.get("token", ""),
        status_path=w_raw.get("status_path", "/run/led-ticker/status.json"),
    )
    if not isinstance(cfg.host, str):
        raise ValueError(f"web.host must be a string; got {type(cfg.host).__name__}.")
    if not isinstance(cfg.port, int) or not 1 <= cfg.port <= 65535:
        raise ValueError(f"web.port must be 1-65535; got {cfg.port!r}.")
    if not isinstance(cfg.token, str):
        raise ValueError(f"web.token must be a string; got {type(cfg.token).__name__}.")
    if not isinstance(cfg.status_path, str) or not cfg.status_path.strip():
        raise ValueError(f"web.status_path must be a non-empty string; got {cfg.status_path!r}.")
    return cfg


def read_web_config(path: Path) -> WebConfig | None:
    """Lightweight [web] reader for the sidecar — parses only the web block,
    so a config with playlist errors still serves the status/validate UI."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return _parse_web_block(raw)
```

On `AppConfig`, after the `plugins` field:

```python
    web: WebConfig | None = None
```

In `load_config`, after `plugins = _parse_plugins_block(raw)`:

```python
    web = _parse_web_block(raw)
```

And add `web=web,` to the `AppConfig(...)` construction at the end of `load_config`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_web_config.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full config test file for regressions, then commit**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_config.py tests/test_web_config.py -q`

```bash
git add src/led_ticker/config.py tests/test_web_config.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): add [web] config block with lightweight reader"
```

---

### Task 2: `StatusBoard` — snapshot, atomic publish, throttle, self-disable

**Files:**
- Create: `src/led_ticker/status_board.py`
- Test: `tests/test_status_board.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for StatusBoard publishing: schema, atomicity, throttle, self-disable."""

import asyncio
import json

import pytest

from led_ticker import status_board
from led_ticker.status_board import SCHEMA_VERSION, StatusBoard

# The status.json contract. If this set changes, SCHEMA_VERSION must bump —
# the sidecar names a mismatch instead of misrendering.
EXPECTED_TOP_LEVEL_KEYS = {
    "schema",
    "published_at",
    "min_interval",
    "started_at",
    "hostname",
    "config_path",
    "geometry",
    "plugins",
    "failed_plugins",
    "section",
    "widget",
    "monitor_updates",
    "log_tail",
}


def _board(tmp_path, **kw):
    return StatusBoard(path=tmp_path / "status.json", **kw)


def test_schema_tripwire(tmp_path):
    snap = _board(tmp_path).snapshot()
    assert set(snap.keys()) == EXPECTED_TOP_LEVEL_KEYS, (
        "status.json field set changed. Update EXPECTED_TOP_LEVEL_KEYS AND bump "
        "SCHEMA_VERSION in src/led_ticker/status_board.py (the sidecar refuses "
        "schemas it doesn't know)."
    )
    assert snap["schema"] == SCHEMA_VERSION == 1


def test_publish_roundtrip(tmp_path):
    board = _board(tmp_path)
    board.config_path = "/code/config/config.toml"
    board.publish(force=True)
    on_disk = json.loads((tmp_path / "status.json").read_text())
    assert on_disk["schema"] == SCHEMA_VERSION
    assert on_disk["config_path"] == "/code/config/config.toml"
    assert on_disk["published_at"] > 0


def test_publish_is_atomic_no_tmp_left_behind(tmp_path):
    board = _board(tmp_path)
    board.publish(force=True)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "status.json"]
    assert leftovers == []


def test_publish_creates_parent_dir(tmp_path):
    board = StatusBoard(path=tmp_path / "deep" / "nested" / "status.json")
    board.publish(force=True)
    assert (tmp_path / "deep" / "nested" / "status.json").exists()


def test_throttle_drops_writes_inside_interval(tmp_path):
    board = _board(tmp_path, min_interval=3600.0)  # nothing un-forced can land twice
    board.publish(force=True)
    first = (tmp_path / "status.json").read_text()
    board.config_path = "/changed"
    board.publish(force=False)  # inside interval, no loop running -> dropped (dirty)
    assert (tmp_path / "status.json").read_text() == first
    board.publish(force=True)  # force always writes
    assert json.loads((tmp_path / "status.json").read_text())["config_path"] == "/changed"


async def test_throttle_flushes_dirty_state_via_loop(tmp_path):
    board = _board(tmp_path, min_interval=0.05)
    board.publish(force=True)
    board.config_path = "/late"
    board.publish(force=False)  # gated -> schedules a delayed flush
    await asyncio.sleep(0.15)
    assert json.loads((tmp_path / "status.json").read_text())["config_path"] == "/late"


def test_publish_failure_disables_silently(tmp_path, caplog):
    board = _board(tmp_path)
    board.path = tmp_path  # a directory: os.replace onto it fails
    board.publish(force=True)  # must NOT raise
    assert board.disabled is True
    board.publish(force=True)  # subsequent calls are no-ops, still no raise
    assert "disabling" in caplog.text


def test_module_record_functions_noop_without_active_board():
    status_board.clear_active_board()
    # Must not raise when no board is active.
    status_board.record_monitor_update("RSSFeedMonitor")
    status_board.record_widget_visit(object())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'led_ticker.status_board'`

- [ ] **Step 3: Implement `src/led_ticker/status_board.py`**

```python
"""Status publishing for the web UI sidecar.

The display process is the sole writer of status.json; the `led-ticker webui`
sidecar is a pure reader. Snapshots are versioned (SCHEMA_VERSION), written
atomically (temp + os.replace), throttled to boundaries (never per-tick), and
the publisher disables itself on any failure — a status write must never
affect the panel (same rule as overlay hooks).
"""

import asyncio
import json
import logging
import os
import socket
import time
from collections import deque
from pathlib import Path
from typing import Any

import attrs

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MIN_PUBLISH_INTERVAL = 2.0
LOG_TAIL_MAX = 50


@attrs.define
class StatusBoard:
    """Mutable status state + throttled atomic publisher."""

    path: Path = attrs.field(converter=lambda p: Path(p).expanduser())
    min_interval: float = MIN_PUBLISH_INTERVAL
    started_at: float = attrs.field(factory=time.time)
    hostname: str = attrs.field(factory=socket.gethostname)
    config_path: str = ""
    geometry: dict[str, Any] = attrs.field(factory=dict)
    plugins: list[dict[str, Any]] = attrs.field(factory=list)
    failed_plugins: list[dict[str, str]] = attrs.field(factory=list)
    section: dict[str, Any] = attrs.field(factory=dict)
    widget: dict[str, Any] = attrs.field(factory=dict)
    monitor_updates: dict[str, float] = attrs.field(factory=dict)
    log_tail: deque[dict[str, Any]] = attrs.field(
        factory=lambda: deque(maxlen=LOG_TAIL_MAX)
    )
    disabled: bool = attrs.field(default=False, init=False)
    _last_publish: float = attrs.field(default=0.0, init=False)
    _flush_scheduled: bool = attrs.field(default=False, init=False)
    _dirty: bool = attrs.field(default=False, init=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "published_at": time.time(),
            "min_interval": self.min_interval,
            "started_at": self.started_at,
            "hostname": self.hostname,
            "config_path": self.config_path,
            "geometry": self.geometry,
            "plugins": self.plugins,
            "failed_plugins": self.failed_plugins,
            "section": self.section,
            "widget": self.widget,
            "monitor_updates": self.monitor_updates,
            "log_tail": list(self.log_tail),
        }

    def publish(self, *, force: bool = False) -> None:
        """Write the snapshot if forced or outside the throttle interval.
        Gated calls mark dirty and schedule a delayed flush (when an event
        loop is running) so the last event in a burst still lands."""
        if self.disabled:
            return
        self._dirty = True
        now = time.monotonic()
        if force or (now - self._last_publish) >= self.min_interval:
            self._flush()
            return
        if self._flush_scheduled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # sync context (tests): stay dirty until next eligible call
        self._flush_scheduled = True
        delay = self.min_interval - (now - self._last_publish)
        loop.call_later(delay, self._scheduled_flush)

    def _scheduled_flush(self) -> None:
        self._flush_scheduled = False
        if self._dirty and not self.disabled:
            self._flush()

    def _flush(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self.snapshot()))
            os.replace(tmp, self.path)
            self._last_publish = time.monotonic()
            self._dirty = False
        except Exception:
            # Disable BEFORE logging: StatusLogHandler feeds records back into
            # this board, so logging while enabled would recurse.
            self.disabled = True
            logger.warning(
                "status publish to %s failed; disabling status publishing "
                "for this session (panel unaffected)",
                self.path,
                exc_info=True,
            )


# --- module-level active board -------------------------------------------
# Engine call sites (run_monitor_loop, Ticker._show_one) go through these
# no-op-when-absent functions so instrumentation is one line and dead-cheap
# when [web] is not configured.

_ACTIVE: StatusBoard | None = None


def set_active_board(board: StatusBoard) -> None:
    global _ACTIVE
    _ACTIVE = board


def clear_active_board() -> None:
    global _ACTIVE
    _ACTIVE = None


def get_active_board() -> StatusBoard | None:
    return _ACTIVE


def record_monitor_update(name: str) -> None:
    if _ACTIVE is not None:
        _ACTIVE.monitor_updates[name] = time.time()
        _ACTIVE.publish()


def record_widget_visit(widget: Any) -> None:
    if _ACTIVE is not None:
        _ACTIVE.widget = _widget_summary(widget)
        _ACTIVE.publish()


def record_section(
    *, index: int, total: int, mode: str, title: str, widget_count: int
) -> None:
    if _ACTIVE is not None:
        _ACTIVE.section = {
            "index": index,
            "total": total,
            "mode": mode,
            "title": title,
            "widget_count": widget_count,
        }
        _ACTIVE.publish(force=True)  # section change publishes immediately


def _widget_summary(widget: Any) -> dict[str, str]:
    text = getattr(widget, "text", None) or getattr(widget, "top_text", None)
    path = getattr(widget, "path", None)
    if text:
        summary = str(text)[:80]
    elif path is not None:
        summary = str(path)
    else:
        summary = ""
    return {"type": type(widget).__name__, "summary": summary}


class StatusLogHandler(logging.Handler):
    """Feeds WARNING+ records into the board's bounded log tail."""

    def __init__(self, board: StatusBoard) -> None:
        super().__init__(level=logging.WARNING)
        self.board = board

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.board.log_tail.append(
                {
                    "ts": record.created,
                    "level": record.levelname,
                    "name": record.name,
                    "message": record.getMessage(),
                }
            )
            self.board.publish()
        except Exception:  # noqa: BLE001 - a log handler must never raise
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/status_board.py tests/test_status_board.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): StatusBoard with atomic throttled publishing"
```

---

### Task 3: `StatusLogHandler` + record-function tests

**Files:**
- Test: `tests/test_status_board.py` (extend)

- [ ] **Step 1: Write the failing tests (append to `tests/test_status_board.py`)**

```python
import logging as _logging


def test_log_handler_captures_warning_and_bounds(tmp_path):
    from led_ticker.status_board import LOG_TAIL_MAX, StatusLogHandler

    board = _board(tmp_path)
    handler = StatusLogHandler(board)
    log = _logging.getLogger("test.status.tail")
    log.addHandler(handler)
    try:
        log.info("invisible")  # below handler level
        for i in range(LOG_TAIL_MAX + 10):
            log.warning("warn %d", i)
    finally:
        log.removeHandler(handler)
    assert len(board.log_tail) == LOG_TAIL_MAX
    assert board.log_tail[-1]["message"] == f"warn {LOG_TAIL_MAX + 9}"
    assert board.log_tail[-1]["level"] == "WARNING"
    assert all("invisible" != e["message"] for e in board.log_tail)


def test_log_handler_survives_disabled_board(tmp_path):
    from led_ticker.status_board import StatusLogHandler

    board = _board(tmp_path)
    board.disabled = True
    handler = StatusLogHandler(board)
    log = _logging.getLogger("test.status.disabled")
    log.addHandler(handler)
    try:
        log.warning("must not raise")  # publish is a no-op; emit must not raise
    finally:
        log.removeHandler(handler)


def test_record_monitor_update_with_active_board(tmp_path):
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_monitor_update("RSS BBC")
        assert "RSS BBC" in board.monitor_updates
        assert board.monitor_updates["RSS BBC"] > 0
    finally:
        status_board.clear_active_board()


def test_record_section_publishes_immediately(tmp_path):
    board = _board(tmp_path, min_interval=3600.0)
    status_board.set_active_board(board)
    try:
        status_board.record_section(
            index=1, total=3, mode="swap", title="news", widget_count=4
        )
        on_disk = json.loads((tmp_path / "status.json").read_text())
        assert on_disk["section"]["mode"] == "swap"
        assert on_disk["section"]["index"] == 1
    finally:
        status_board.clear_active_board()


def test_widget_summary_shapes(tmp_path):
    class FakeText:
        text = "Hello world " * 20  # > 80 chars

    class FakePath:
        path = "/code/assets/cat.gif"

    class Bare:
        pass

    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_widget_visit(FakeText())
        assert board.widget["type"] == "FakeText"
        assert len(board.widget["summary"]) == 80

        status_board.record_widget_visit(FakePath())
        assert board.widget["summary"] == "/code/assets/cat.gif"

        status_board.record_widget_visit(Bare())
        assert board.widget == {"type": "Bare", "summary": ""}
    finally:
        status_board.clear_active_board()
```

- [ ] **Step 2: Run tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -v`
Expected: all PASS (Task 2 already implemented these surfaces; this task locks them with tests). If any fail, fix `status_board.py` — the tests are the contract.

- [ ] **Step 3: Commit**

```bash
git add tests/test_status_board.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "test(web): log handler + record function contracts"
```

---

### Task 4: Engine instrumentation (widget.py, ticker.py, app/run.py)

**Files:**
- Modify: `src/led_ticker/widget.py` (`run_monitor_loop`, ~line 148)
- Modify: `src/led_ticker/ticker.py` (`_show_one`, ~line 617)
- Modify: `src/led_ticker/app/run.py` (board construction in `run()`; section record in the section loop ~line 161)
- Test: `tests/test_status_instrumentation.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Engine instrumentation: monitor updates and widget visits reach the board."""

import asyncio

import pytest

from led_ticker import status_board
from led_ticker.status_board import StatusBoard
from led_ticker.widget import run_monitor_loop


class _OneShotMonitor:
    """Updatable that succeeds once then cancels its own loop."""

    name = "RSS BBC"

    def __init__(self):
        self.updated = asyncio.Event()

    async def update(self):
        self.updated.set()


async def test_run_monitor_loop_records_update(tmp_path):
    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)
    monitor = _OneShotMonitor()
    task = asyncio.create_task(run_monitor_loop(monitor, 0.01, splay=False))
    try:
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)  # let the post-update record run
        assert "RSS BBC" in board.monitor_updates
    finally:
        task.cancel()
        status_board.clear_active_board()


async def test_run_monitor_loop_falls_back_to_class_name(tmp_path):
    board = StatusBoard(path=tmp_path / "status.json")
    status_board.set_active_board(board)

    class Nameless:
        def __init__(self):
            self.updated = asyncio.Event()

        async def update(self):
            self.updated.set()

    monitor = Nameless()
    task = asyncio.create_task(run_monitor_loop(monitor, 0.01, splay=False))
    try:
        await asyncio.wait_for(monitor.updated.wait(), timeout=2)
        await asyncio.sleep(0.05)
        assert "Nameless" in board.monitor_updates
    finally:
        task.cancel()
        status_board.clear_active_board()


def test_show_one_calls_record_widget_visit(monkeypatch):
    """AST-free behavioral check: _show_one's body invokes the module hook."""
    import inspect

    from led_ticker import ticker as ticker_mod

    src = inspect.getsource(ticker_mod.Ticker._show_one)
    assert "record_widget_visit" in src, (
        "Ticker._show_one must call status_board.record_widget_visit(widget) "
        "so the web UI's now-playing pane tracks swap-mode visits."
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_instrumentation.py -v`
Expected: FAIL — monitor tests find no recorded names; `_show_one` source lacks the call.

- [ ] **Step 3: Implement the hooks**

`src/led_ticker/widget.py` — add to the imports block:

```python
from led_ticker import status_board
```

In `run_monitor_loop`, right after `consecutive_errors = 0` inside the `try` (the success path):

```python
        try:
            await widget.update()
            consecutive_errors = 0
            status_board.record_monitor_update(
                getattr(widget, "name", None) or type(widget).__name__
            )
```

`src/led_ticker/ticker.py` — add to the imports block:

```python
from led_ticker import status_board
```

At the top of `Ticker._show_one`'s body (it may receive `None` for the no-widget call — guard it):

```python
        if widget is not None:
            status_board.record_widget_visit(widget)
```

`src/led_ticker/app/run.py` — in `run()`, after `led_frame = build_frame_from_config(config.display)`:

```python
    if config.web is not None:
        from led_ticker.status_board import (  # noqa: PLC0415
            StatusBoard,
            StatusLogHandler,
            set_active_board,
        )

        board = StatusBoard(path=Path(config.web.status_path))
        board.config_path = str(config_path)
        board.geometry = {
            "rows": config.display.rows,
            "cols": config.display.cols,
            "chain_length": config.display.chain_length,
            "parallel": config.display.parallel,
            "default_scale": config.display.default_scale,
            "panel_width": config.display.cols * config.display.chain_length,
            "panel_height": config.display.rows * config.display.parallel,
        }
        board.plugins = [
            {
                "namespace": info.namespace,
                "source": info.source,
                "counts": dict(info.counts or {}),
            }
            for info in plugins.loaded
        ]
        board.failed_plugins = [
            {"namespace": ns, "error": str(err)} for ns, err in plugins.failed
        ]
        set_active_board(board)
        logging.getLogger().addHandler(StatusLogHandler(board))
        board.publish(force=True)
```

(If `DisplayConfig` lacks `parallel`, drop that key and compute `panel_height = rows` — check `src/led_ticker/config.py:12` while implementing and keep geometry keys honest.)

In the section loop, change `for section in config.sections:` to:

```python
                for section_index, section in enumerate(config.sections):
```

and immediately inside the loop body add:

```python
                    from led_ticker import status_board as _status  # noqa: PLC0415

                    _status.record_section(
                        index=section_index,
                        total=len(config.sections),
                        mode=section.mode,
                        title=str((section.title or {}).get("text", "")),
                        widget_count=len(section.widgets),
                    )
```

(Prefer a top-of-file `from led_ticker import status_board` import in `run.py` if ruff flags the inline one; either is fine — the call is a no-op without an active board.)

- [ ] **Step 4: Run the new tests plus the engine suites**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_instrumentation.py tests/test_ticker_display.py tests/test_app.py -q`
Expected: PASS. `_show_one` runs in many existing tests — the hook must not break them (it no-ops without an active board).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widget.py src/led_ticker/ticker.py src/led_ticker/app/run.py tests/test_status_instrumentation.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): engine instrumentation publishes to StatusBoard"
```

---

### Task 5: `validate_config_text` from-string entry point

**Files:**
- Modify: `src/led_ticker/validate.py` (next to `validate_config`, ~line 1654)
- Test: `tests/test_validate_text.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""validate_config_text parity with the file-path entry point."""

import pytest

from led_ticker.validate import validate_config, validate_config_text

GOOD = """
[display]
rows = 16
cols = 32

[[playlist.section]]
mode = "forever_scroll"
[[playlist.section.widgets]]
type = "message"
text = "hi"
"""

BAD = GOOD + '\n[[playlist.section]]\nmode = "no_such_mode"\n'


async def test_text_and_path_agree_on_valid(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(GOOD)
    from_path = await validate_config(p)
    from_text = await validate_config_text(GOOD)
    assert from_text.valid == from_path.valid is True


async def test_text_and_path_agree_on_invalid(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(BAD)
    from_path = await validate_config(p)
    from_text = await validate_config_text(BAD)
    assert from_text.valid == from_path.valid is False
    assert [e.message for e in from_text.errors] == [
        e.message for e in from_path.errors
    ]


async def test_text_broken_toml_is_a_result_not_a_raise():
    result = await validate_config_text("this is [not toml")
    assert result.valid is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_validate_text.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate_config_text'`

(If the broken-TOML test fails because `validate_config` RAISES on broken TOML rather than returning an invalid result, match the file-path behavior exactly — adjust the test to `pytest.raises` of the same exception and keep parity. Parity with the path entry point is the contract; check what `validate_config` actually does with broken TOML and mirror it.)

- [ ] **Step 3: Implement (in `src/led_ticker/validate.py`, after `validate_config`)**

```python
async def validate_config_text(text: str, *, strict: bool = False) -> ValidationResult:
    """Validate TOML config content from a string.

    Same engine as validate_config — the text is materialized to a temp file
    so every path-relative check behaves identically. Used by the web UI's
    POST /api/validate; also handy for tests."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="led-ticker-validate-") as td:
        p = Path(td) / "config.toml"
        p.write_text(text)
        return await validate_config(p, strict=strict)
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_validate_text.py tests/test_validate.py -q`
Expected: PASS (run the existing validate suite too — its filename may differ; `ls tests/ | grep validate` and include whatever exists).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate_text.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(validate): from-string entry point validate_config_text"
```

---

### Task 6: `redact_toml`

**Files:**
- Create: `src/led_ticker/webui/__init__.py` (empty for now — package marker)
- Create: `src/led_ticker/webui/redact.py`
- Test: `tests/test_webui_redact.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Redaction of sensitive values from TOML text. Over-redaction is safe;
under-redaction is the worst failure in a read-only design."""

from led_ticker.webui.redact import redact_toml


def test_redacts_token():
    assert 'token = "•••"' in redact_toml('token = "abc123"')


def test_redacts_key_suffixed_names():
    out = redact_toml('weatherapi_key = "k-123"\napi_key = "k-456"')
    assert "k-123" not in out and "k-456" not in out
    assert out.count('"•••"') == 2


def test_redacts_inside_inline_tables():
    out = redact_toml('busy = { source = "http", token = "hunter2", port = 8080 }')
    assert "hunter2" not in out
    assert 'source = "http"' in out
    assert "port = 8080" in out


def test_preserves_comments_and_structure():
    src = "# my comment\n[display]\nrows = 16  # trailing\n"
    assert redact_toml(src) == src


def test_redacts_secret_password_webhook():
    out = redact_toml('secret = "a"\npassword = "b"\nslack_webhook = "c"')
    for leaked in ("\"a\"", "\"b\"", "\"c\""):
        assert leaked not in out


def test_non_sensitive_values_untouched():
    src = 'text = "my token of appreciation"\ncolor = [255, 0, 0]'
    # Values are never scanned — only key NAMES trigger redaction.
    assert redact_toml(src) == src


def test_over_redaction_of_keylike_names_is_accepted():
    # "monkey" contains "key": redacted. Documented behavior — safe direction.
    assert "•••" in redact_toml('monkey = "bananas"')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_redact.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'led_ticker.webui'`

- [ ] **Step 3: Implement**

`src/led_ticker/webui/__init__.py` — create empty (docstring only):

```python
"""Web status UI sidecar (led-ticker webui)."""
```

`src/led_ticker/webui/redact.py`:

```python
"""Sensitive-value redaction for the config view.

Key-NAME based, value-blind: any key whose name contains a sensitive word has
its value replaced. Works on raw TOML text (preserves comments/formatting) and
inside inline tables. Over-redaction (e.g. `monkey`) is accepted — the safe
direction for a read-only UI.
"""

import re

REDACTED = '"•••"'

_KV = re.compile(
    r"""(?P<key>[A-Za-z0-9_.-]*(?:token|key|secret|password|webhook)[A-Za-z0-9_.-]*)
        (?P<eq>\s*=\s*)
        (?P<val>"[^"]*"|'[^']*'|\[[^\]]*\]|[^,}\s#]+)""",
    re.IGNORECASE | re.VERBOSE,
)


def redact_toml(text: str) -> str:
    """Replace values of sensitive-named keys with a redaction marker."""
    return _KV.sub(lambda m: m.group("key") + m.group("eq") + REDACTED, text)
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_redact.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/webui/ tests/test_webui_redact.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): key-name based TOML redaction"
```

---

### Task 7: `build_webui_app` — `/api/status` with auth + degraded states

**Files:**
- Modify: `src/led_ticker/webui/__init__.py`
- Test: `tests/test_webui_app.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Route tests for the webui sidecar app."""

import json
import time

from aiohttp.test_utils import TestClient, TestServer

from led_ticker.status_board import SCHEMA_VERSION, StatusBoard
from led_ticker.webui import build_webui_app


async def _client(tmp_path, *, token="", config_text=None, status=None):
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_text or "[display]\nrows = 16\ncols = 32\n")
    status_path = tmp_path / "status.json"
    if status is not None:
        status_path.write_text(json.dumps(status) if isinstance(status, dict) else status)
    app = build_webui_app(config_path=config_path, status_path=status_path, token=token)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def _fresh_status(**over):
    board = StatusBoard(path="/unused")
    snap = board.snapshot()
    snap.update(over)
    return snap


async def test_status_ok(tmp_path):
    client = await _client(tmp_path, status=_fresh_status())
    try:
        resp = await client.get("/api/status")
        body = await resp.json()
        assert resp.status == 200
        assert body["state"] == "ok"
        assert body["status"]["schema"] == SCHEMA_VERSION
    finally:
        await client.close()


async def test_status_missing_file(tmp_path):
    client = await _client(tmp_path)  # no status.json written
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "missing"
        assert "running" in body["hint"]  # friendly first-run hint
    finally:
        await client.close()


async def test_status_malformed_file(tmp_path):
    client = await _client(tmp_path, status="{not json")
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "unreadable"
    finally:
        await client.close()


async def test_status_schema_mismatch(tmp_path):
    client = await _client(tmp_path, status=_fresh_status(schema=SCHEMA_VERSION + 1))
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "schema_mismatch"
        assert body["found"] == SCHEMA_VERSION + 1
        assert body["supported"] == SCHEMA_VERSION
    finally:
        await client.close()


async def test_status_stale(tmp_path):
    old = _fresh_status(published_at=time.time() - 3600, min_interval=2.0)
    client = await _client(tmp_path, status=old)
    try:
        body = await (await client.get("/api/status")).json()
        assert body["state"] == "stale"
        assert body["status"]["hostname"]  # data still served
    finally:
        await client.close()


async def test_auth_token_enforced_on_all_routes(tmp_path):
    client = await _client(tmp_path, token="s3cret", status=_fresh_status())
    try:
        for path in ("/", "/api/status", "/api/config"):
            assert (await client.get(path)).status == 401
        ok = await client.get("/api/status", headers={"X-Web-Token": "s3cret"})
        assert ok.status == 200
        ok2 = await client.get("/api/status", params={"token": "s3cret"})
        assert ok2.status == 200
    finally:
        await client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_webui_app'`

- [ ] **Step 3: Implement (replace `src/led_ticker/webui/__init__.py` body)**

```python
"""Web status UI sidecar (led-ticker webui).

Pure builder (build_webui_app) + production runner (serve_webui/run_webui),
mirroring busy_http. The sidecar is a pure READER: it never writes status.json
and never touches the config file. It must keep working when the display
process is absent — every degraded state is a friendly JSON answer, not a 500.
This module must never import rgbmatrix (tripwire: tests/test_webui_purity.py).
"""

import asyncio
import json
import logging
import time
from importlib import resources
from pathlib import Path

from aiohttp import web

from led_ticker.status_board import SCHEMA_VERSION
from led_ticker.webui.redact import redact_toml

logger = logging.getLogger(__name__)

STALE_FACTOR = 3.0  # stale when published_at is older than factor × min_interval
MAX_VALIDATE_BODY = 1024 * 1024  # 1 MB


def _read_status(status_path: Path) -> dict:
    """Classify the status file into the API envelope. Never raises."""
    try:
        raw = status_path.read_text()
    except FileNotFoundError:
        return {
            "state": "missing",
            "hint": (
                "The display process hasn't published yet — is led-ticker "
                "running, and does its config have a [web] block?"
            ),
        }
    except OSError as e:
        return {"state": "unreadable", "detail": str(e)}
    try:
        status = json.loads(raw)
    except ValueError as e:
        return {"state": "unreadable", "detail": f"bad JSON: {e}"}
    found = status.get("schema")
    if found != SCHEMA_VERSION:
        return {
            "state": "schema_mismatch",
            "found": found,
            "supported": SCHEMA_VERSION,
            "hint": "led-ticker and the webui are running different versions.",
        }
    age = time.time() - float(status.get("published_at", 0))
    threshold = STALE_FACTOR * float(status.get("min_interval", 2.0))
    state = "stale" if age > threshold else "ok"
    return {"state": state, "age_seconds": round(age, 1), "status": status}


def build_webui_app(
    *, config_path: Path, status_path: Path, token: str = ""
) -> web.Application:
    """Build the aiohttp app. Pure: no I/O at build time."""

    @web.middleware
    async def auth(request: web.Request, handler):
        if token:
            provided = request.headers.get("X-Web-Token") or request.query.get(
                "token"
            )
            if provided != token:
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    async def status_handler(request: web.Request) -> web.Response:
        return web.json_response(_read_status(status_path))

    app = web.Application(middlewares=[auth])
    app.router.add_get("/api/status", status_handler)
    _add_config_routes(app, config_path)  # Task 8
    _add_page_route(app)  # Task 9
    return app
```

For this task, stub the two forward references at module level so the file imports (they become real in Tasks 8–9):

```python
def _add_config_routes(app: web.Application, config_path: Path) -> None:
    """Filled in by the /api/config + /api/validate task."""


def _add_page_route(app: web.Application) -> None:
    """Filled in by the static-page task."""
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -v`
Expected: status tests PASS; `test_auth_token_enforced_on_all_routes` FAILS on `/` and `/api/config` (404, not 401 — those routes land in Tasks 8–9). If 404s break the assertion, temporarily limit that test's loop to `("/api/status",)` and restore the full tuple in Task 9's steps.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/webui/__init__.py tests/test_webui_app.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): sidecar app skeleton with /api/status + auth"
```

---

### Task 8: `/api/config` + `/api/validate`

**Files:**
- Modify: `src/led_ticker/webui/__init__.py` (replace the `_add_config_routes` stub)
- Test: `tests/test_webui_app.py` (extend)

- [ ] **Step 1: Write the failing tests (append to `tests/test_webui_app.py`)**

```python
async def test_config_view_is_redacted(tmp_path):
    cfg = '[web]\ntoken = "supersecret"\n\n[display]\nrows = 16\ncols = 32\nchain_length = 5\n'
    client = await _client(tmp_path, config_text=cfg)
    try:
        body = await (await client.get("/api/config")).json()
        assert "supersecret" not in body["toml"]
        assert "•••" in body["toml"]
        assert body["geometry"]["panel_width"] == 32 * 5
    finally:
        await client.close()


async def test_config_view_missing_file_degrades(tmp_path):
    client = await _client(tmp_path)
    (tmp_path / "config.toml").unlink()
    try:
        resp = await client.get("/api/config")
        body = await resp.json()
        assert resp.status == 200
        assert body["state"] == "unreadable"
    finally:
        await client.close()


async def test_validate_good_toml(tmp_path):
    good = (
        "[display]\nrows = 16\ncols = 32\n\n"
        '[[playlist.section]]\nmode = "forever_scroll"\n'
        '[[playlist.section.widgets]]\ntype = "message"\ntext = "hi"\n'
    )
    client = await _client(tmp_path)
    try:
        resp = await client.post("/api/validate", data=good)
        body = await resp.json()
        assert resp.status == 200
        assert body["valid"] is True
    finally:
        await client.close()


async def test_validate_bad_toml_is_200_with_issues(tmp_path):
    client = await _client(tmp_path)
    try:
        resp = await client.post("/api/validate", data="this is [not toml")
        assert resp.status == 200  # results, not errors
        body = await resp.json()
        assert body["valid"] is False
    finally:
        await client.close()


async def test_validate_oversize_body_is_413(tmp_path):
    client = await _client(tmp_path)
    try:
        resp = await client.post("/api/validate", data="x" * (1024 * 1024 + 1))
        assert resp.status == 413
    finally:
        await client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -v -k "config or validate"`
Expected: FAIL with 404s (routes don't exist).

- [ ] **Step 3: Implement — replace the `_add_config_routes` stub**

```python
def _add_config_routes(app: web.Application, config_path: Path) -> None:
    async def config_handler(request: web.Request) -> web.Response:
        try:
            text = config_path.read_text()
        except OSError as e:
            return web.json_response({"state": "unreadable", "detail": str(e)})
        import tomllib  # noqa: PLC0415

        geometry: dict = {}
        try:
            display = tomllib.loads(text).get("display", {})
            rows = int(display.get("rows", 16))
            cols = int(display.get("cols", 32))
            chain = int(display.get("chain_length", 1))
            parallel = int(display.get("parallel", 1))
            geometry = {
                "rows": rows,
                "cols": cols,
                "chain_length": chain,
                "parallel": parallel,
                "default_scale": int(display.get("default_scale", 1)),
                "panel_width": cols * chain,
                "panel_height": rows * parallel,
            }
        except (ValueError, TypeError):
            pass  # geometry is best-effort; the redacted text is the point
        return web.json_response(
            {"state": "ok", "toml": redact_toml(text), "geometry": geometry}
        )

    async def validate_handler(request: web.Request) -> web.Response:
        if (request.content_length or 0) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        body = await request.text()
        if len(body.encode()) > MAX_VALIDATE_BODY:
            return web.json_response({"error": "body too large"}, status=413)
        from led_ticker.validate import _format_json, validate_config_text  # noqa: PLC0415

        try:
            result = await validate_config_text(body)
        except Exception as e:  # parse explosions are RESULTS, not errors
            return web.json_response(
                {"valid": False, "errors": [{"message": str(e)}], "warnings": []}
            )
        return web.Response(text=_format_json(result), content_type="application/json")

    app.router.add_get("/api/config", config_handler)
    app.router.add_post("/api/validate", validate_handler)
```

NOTE while implementing: open `src/led_ticker/validate.py` and check `_format_json`'s output shape — the tests assert a top-level `"valid"` key. If `_format_json` uses a different key (e.g. `"ok"`), build the response dict by hand from `ValidationResult` instead: `{"valid": result.valid, "errors": [...], "warnings": [...]}` with each issue as `{"rule": i.rule, "message": i.message}` (check `ValidationIssue`'s actual field names at `validate.py:19`). The tests are the contract; the JSON must have `"valid"`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/webui/__init__.py tests/test_webui_app.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): /api/config (redacted) and /api/validate routes"
```

---

### Task 9: Static page + `GET /`

**Files:**
- Create: `src/led_ticker/webui/static/index.html`
- Modify: `src/led_ticker/webui/__init__.py` (replace `_add_page_route` stub)
- Test: `tests/test_webui_app.py` (extend)

- [ ] **Step 1: Write the failing tests (append to `tests/test_webui_app.py`)**

```python
async def test_root_serves_page(tmp_path):
    client = await _client(tmp_path)
    try:
        resp = await client.get("/")
        assert resp.status == 200
        assert resp.content_type == "text/html"
        text = await resp.text()
        for marker in ("Status", "Config", "Validate", "/api/status"):
            assert marker in text
    finally:
        await client.close()
```

Also restore the full route tuple `("/", "/api/status", "/api/config")` in `test_auth_token_enforced_on_all_routes` if it was narrowed in Task 7.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py::test_root_serves_page -v`
Expected: FAIL with 404

- [ ] **Step 3: Create `src/led_ticker/webui/static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>led-ticker</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #111; color: #ddd; }
  header { display: flex; align-items: center; gap: 1rem; padding: .8rem 1.2rem; background: #1a1a1a; border-bottom: 1px solid #333; }
  header h1 { font-size: 1.1rem; margin: 0; }
  #live { font-size: .85rem; }
  #live.ok::before { content: "● "; color: #4c4; }
  #live.stale::before, #live.missing::before { content: "● "; color: #c44; }
  nav { display: flex; gap: .4rem; margin-left: auto; }
  nav button { background: #222; color: #ddd; border: 1px solid #444; border-radius: 6px; padding: .4rem .9rem; cursor: pointer; }
  nav button.active { background: #36c; border-color: #36c; color: #fff; }
  main { padding: 1.2rem; max-width: 70rem; margin: 0 auto; }
  section.tab { display: none; }
  section.tab.active { display: block; }
  .card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
  .hero { text-align: center; }
  .hero .marquee { font-family: ui-monospace, monospace; color: #f80; background: #000; border-radius: 6px; padding: .5rem; margin-top: .5rem; overflow-wrap: anywhere; }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; }
  td, th { text-align: left; padding: .25rem .5rem; border-bottom: 1px solid #2a2a2a; }
  pre, textarea { font-family: ui-monospace, monospace; font-size: .85rem; background: #000; color: #cdc; border: 1px solid #333; border-radius: 6px; padding: .8rem; width: 100%; box-sizing: border-box; white-space: pre-wrap; }
  textarea { min-height: 20rem; resize: vertical; }
  .issues .error { color: #f66; }
  .issues .warning { color: #fc6; }
  .muted { color: #888; }
  #validate-run { background: #36c; color: #fff; border: 0; border-radius: 6px; padding: .5rem 1.2rem; cursor: pointer; margin: .6rem 0; }
</style>
</head>
<body>
<header>
  <h1 id="hostname">led-ticker</h1>
  <span id="uptime" class="muted"></span>
  <span id="live" class="missing">connecting…</span>
  <nav>
    <button data-tab="status" class="active">Status</button>
    <button data-tab="config">Config</button>
    <button data-tab="validate">Validate</button>
  </nav>
</header>
<main>
  <section id="tab-status" class="tab active">
    <div class="card hero">
      <strong>▶ NOW PLAYING</strong>
      <div id="now-section" class="muted">—</div>
      <div id="now-widget" class="marquee">—</div>
    </div>
    <div class="card">
      <strong>Health</strong>
      <table id="monitors"><tbody></tbody></table>
      <pre id="logtail" class="muted">no recent warnings</pre>
    </div>
    <div class="card">
      <strong>Plugins</strong>
      <table id="plugins"><tbody></tbody></table>
    </div>
  </section>
  <section id="tab-config" class="tab">
    <div class="card">
      <strong>Live config</strong> <span id="geometry" class="muted"></span>
      <pre id="config-toml">loading…</pre>
    </div>
  </section>
  <section id="tab-validate" class="tab">
    <div class="card">
      <strong>Validate a candidate config</strong>
      <textarea id="validate-input" placeholder="Paste TOML here…"></textarea>
      <button id="validate-run">Validate</button>
      <div id="validate-result" class="issues"></div>
    </div>
  </section>
</main>
<script>
const qs = new URLSearchParams(location.search);
const tok = qs.get("token");
const auth = tok ? {"X-Web-Token": tok} : {};
const $ = (id) => document.getElementById(id);

document.querySelectorAll("nav button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("nav button").forEach((x) => x.classList.remove("active"));
  document.querySelectorAll("section.tab").forEach((x) => x.classList.remove("active"));
  b.classList.add("active");
  $("tab-" + b.dataset.tab).classList.add("active");
  if (b.dataset.tab === "config") loadConfig();
});

function fmtAgo(ts) {
  const s = Math.max(0, (Date.now() / 1000) - ts);
  if (s < 90) return Math.round(s) + "s ago";
  if (s < 5400) return Math.round(s / 60) + "m ago";
  return Math.round(s / 3600) + "h ago";
}

async function poll() {
  try {
    const r = await fetch("/api/status", {headers: auth});
    const body = await r.json();
    const live = $("live");
    live.className = body.state;
    if (!body.status) {
      live.textContent = body.state === "missing" ? "no status yet" : body.state;
      $("now-section").textContent = body.hint || body.detail || "—";
      return;
    }
    const st = body.status;
    live.textContent = body.state === "ok" ? "live" : "stale " + fmtAgo(st.published_at);
    $("hostname").textContent = st.hostname || "led-ticker";
    const up = (Date.now() / 1000) - st.started_at;
    $("uptime").textContent = "up " + (up > 7200 ? Math.round(up / 3600) + "h" : Math.round(up / 60) + "m");
    const sec = st.section || {};
    $("now-section").textContent = sec.mode
      ? `section ${sec.title || sec.index} (${(sec.index ?? 0) + 1}/${sec.total}) · ${sec.mode} · ${sec.widget_count} widgets`
      : "—";
    const w = st.widget || {};
    $("now-widget").textContent = w.type ? `${w.type}: ${w.summary || ""}` : "—";
    $("monitors").tBodies[0].innerHTML = Object.entries(st.monitor_updates || {})
      .map(([n, ts]) => `<tr><td>${n}</td><td>${fmtAgo(ts)}</td></tr>`).join("")
      || '<tr><td class="muted">no async monitors</td></tr>';
    const fails = (st.failed_plugins || []).map((p) => `<tr><td>${p.namespace}</td><td class="error">failed: ${p.error}</td></tr>`);
    $("plugins").tBodies[0].innerHTML = (st.plugins || [])
      .map((p) => `<tr><td>${p.namespace}</td><td class="muted">${JSON.stringify(p.counts)}</td></tr>`)
      .concat(fails).join("") || '<tr><td class="muted">no plugins</td></tr>';
    $("logtail").textContent = (st.log_tail || []).slice(-10)
      .map((e) => `${e.level} ${e.name}: ${e.message}`).join("\n") || "no recent warnings";
  } catch (e) {
    $("live").className = "missing";
    $("live").textContent = "webui unreachable";
  }
}

async function loadConfig() {
  const r = await fetch("/api/config", {headers: auth});
  const body = await r.json();
  if (body.state !== "ok") { $("config-toml").textContent = body.detail || body.state; return; }
  $("config-toml").textContent = body.toml;
  const g = body.geometry || {};
  if (g.panel_width) $("geometry").textContent = `${g.panel_width}×${g.panel_height} @ scale ${g.default_scale}`;
}

$("validate-run").onclick = async () => {
  const r = await fetch("/api/validate", {method: "POST", headers: auth, body: $("validate-input").value});
  if (r.status === 413) { $("validate-result").innerHTML = '<p class="error">Config too large (1 MB cap).</p>'; return; }
  const body = await r.json();
  const issues = [...(body.errors || []).map((i) => ["error", i]), ...(body.warnings || []).map((i) => ["warning", i])];
  $("validate-result").innerHTML = body.valid
    ? "<p>✓ Valid config.</p>"
    : issues.map(([sev, i]) => `<p class="${sev}">${sev}${i.rule ? " (rule " + i.rule + ")" : ""}: ${i.message}</p>`).join("")
      || '<p class="error">Invalid (no detail returned).</p>';
};

poll();
setInterval(poll, 3000);
</script>
</body>
</html>
```

- [ ] **Step 4: Replace the `_add_page_route` stub**

```python
def _add_page_route(app: web.Application) -> None:
    async def index(request: web.Request) -> web.Response:
        html = (
            resources.files("led_ticker.webui").joinpath("static/index.html")
        ).read_text()
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/", index)
```

- [ ] **Step 5: Run all webui tests; verify package data ships**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -v`
Expected: all PASS.
Then check the wheel includes the HTML: `uv build 2>/dev/null && unzip -l dist/*.whl | grep index.html` — if missing, add the include to `pyproject.toml` per the build backend's data-file syntax (hatchling includes package files by default; verify, don't assume).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/webui/ tests/test_webui_app.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): tabbed status page served from package data"
```

---

### Task 10: CLI subcommand + runner + import-purity tripwire

**Files:**
- Modify: `src/led_ticker/webui/__init__.py` (add `serve_webui` / `run_webui`)
- Modify: `src/led_ticker/app/cli.py` (add `webui` subcommand after the `plugins` subparser, ~line 132)
- Test: `tests/test_webui_purity.py` (create); `tests/test_webui_app.py` (extend)

- [ ] **Step 1: Write the failing tests**

`tests/test_webui_purity.py`:

```python
"""The sidecar must be importable without rgbmatrix — it runs unprivileged
on machines (or containers) with no matrix hardware libs at all."""

import subprocess
import sys


def test_webui_import_does_not_touch_rgbmatrix():
    # Run WITHOUT tests/stubs on the path: if the import chain reaches
    # rgbmatrix at all, sys.modules will show it (stub or real).
    code = (
        "import sys\n"
        "import led_ticker.webui, led_ticker.status_board\n"
        "hit = [m for m in sys.modules if m.startswith('rgbmatrix')]\n"
        "assert not hit, f'webui import pulled in {hit}'\n"
        "print('PURE')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "PURE" in proc.stdout
```

Append to `tests/test_webui_app.py`:

```python
async def test_serve_webui_starts_and_cleans_up(tmp_path):
    from led_ticker.webui import serve_webui

    config_path = tmp_path / "config.toml"
    config_path.write_text("[display]\nrows = 16\n")
    runner = await serve_webui(
        config_path=config_path,
        status_path=tmp_path / "status.json",
        host="127.0.0.1",
        port=0,  # OS-assigned free port
        token="",
    )
    try:
        assert runner.addresses
    finally:
        await runner.cleanup()
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_purity.py tests/test_webui_app.py::test_serve_webui_starts_and_cleans_up -v`
Expected: serve test FAILS on import; purity test may already PASS (good — it's the tripwire keeping it that way).

- [ ] **Step 3: Implement the runner (append to `src/led_ticker/webui/__init__.py`)**

```python
async def serve_webui(
    *, config_path: Path, status_path: Path, host: str, port: int, token: str = ""
) -> web.AppRunner:
    """Start the listener; caller keeps the runner and calls .cleanup().
    Same contract as busy_http.serve_busy."""
    runner = web.AppRunner(
        build_webui_app(config_path=config_path, status_path=status_path, token=token)
    )
    await runner.setup()
    try:
        site = web.TCPSite(runner, host, port)
        await site.start()
    except Exception:
        await runner.cleanup()
        raise
    logger.info("webui listening on %s:%d", host, port)
    return runner


async def run_webui(config_path: Path, web_cfg) -> None:
    """Process entry point for `led-ticker webui`. Runs until cancelled."""
    runner = await serve_webui(
        config_path=config_path,
        status_path=Path(web_cfg.status_path).expanduser(),
        host=web_cfg.host,
        port=web_cfg.port,
        token=web_cfg.token,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
```

- [ ] **Step 4: Wire the CLI (in `src/led_ticker/app/cli.py`)**

After the `plugins` subparser block (~line 132):

```python
    # `webui` subcommand — the unprivileged status sidecar
    webui_parser = subparsers.add_parser(
        "webui",
        help="Run the web status UI sidecar (requires a [web] block in the config)",
    )
    webui_parser.add_argument(
        "--config", "-c", type=Path, default=argparse.SUPPRESS,
        help="Path to TOML config file (defaults to the top-level --config)",
    )
```

After the `plugins` command handler (~line 145):

```python
    if args.command == "webui":
        from led_ticker.config import read_web_config  # noqa: PLC0415
        from led_ticker.webui import run_webui  # noqa: PLC0415

        try:
            web_cfg = read_web_config(args.config)
        except (OSError, ValueError) as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)
        if web_cfg is None:
            print(
                f"No [web] block in {args.config} — add one to enable the "
                "status sidecar (see config.example.toml).",
                file=sys.stderr,
            )
            sys.exit(2)
        asyncio.run(run_webui(args.config, web_cfg))
        sys.exit(0)
```

IMPORTANT: `cli.py` currently imports `run` (and through it the whole app) at module top. Check whether `from led_ticker.app.run import run` pulls in rgbmatrix-touching modules — if the purity test fails after wiring, move that import inside the run branch (`if args.command is None/run` path) the same lazy way `plugins` does it. The purity tripwire is the arbiter.

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_purity.py tests/test_webui_app.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/webui/__init__.py src/led_ticker/app/cli.py tests/test_webui_purity.py tests/test_webui_app.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): led-ticker webui subcommand + import-purity tripwire"
```

---

### Task 11: Deployment artifacts

**Files:**
- Modify: `compose.yaml`
- Create: `deploy/led-ticker-webui.service`
- Modify: `config/config.example.toml`

- [ ] **Step 1: Add the webui service to `compose.yaml`**

Append under `services:` (keep the existing `led-ticker` service untouched except the added shared volume):

```yaml
  # Web status UI — unprivileged sidecar, same image. Reads status.json that
  # the display process publishes; serves http://<pi>:8080.
  webui:
    image: led-ticker
    build: .
    container_name: led-ticker-webui
    restart: unless-stopped
    command: ["led-ticker", "webui", "--config", "/code/config/config.toml"]
    network_mode: host
    volumes:
      - ./config:/code/config:ro
      - ticker-status:/run/led-ticker
```

And add to the display service's `volumes:` list:

```yaml
      - ticker-status:/run/led-ticker
```

And at file bottom:

```yaml
volumes:
  ticker-status:
```

- [ ] **Step 2: Create `deploy/led-ticker-webui.service`**

Look at `deploy/led-ticker.service` first and mirror its conventions (paths, restart policy). Baseline:

```ini
[Unit]
Description=led-ticker web status UI (sidecar)
After=network.target

[Service]
Type=simple
User=ledticker
RuntimeDirectory=led-ticker
RuntimeDirectoryPreserve=yes
ExecStart=/usr/local/bin/led-ticker webui --config /etc/led-ticker/config.toml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Adjust `ExecStart`/config path to match whatever `deploy/led-ticker.service` actually uses — consistency with the existing unit beats this baseline.

- [ ] **Step 3: Add the commented `[web]` block to `config/config.example.toml`**

Place it near the `[busy_light]` example block:

```toml
# Web status UI (read-only). Presence of this block enables status publishing;
# run the sidecar with: led-ticker webui --config config.toml
# Docs: https://docs.ledticker.dev/concepts/web-status-ui/
# [web]
# host = "0.0.0.0"
# port = 8080
# token = ""                                    # non-empty enables auth
# status_path = "/run/led-ticker/status.json"   # compose overrides via shared volume
```

- [ ] **Step 4: Validate compose syntax and commit**

Run: `docker compose config -q` (syntax check; OK to skip if docker absent locally — say so in the commit PR notes)

```bash
git add compose.yaml deploy/led-ticker-webui.service config/config.example.toml
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): compose service, systemd unit, example config block"
```

---

### Task 12: Docs + drift guard

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx` (find exact path with `ls docs/site/src/content/docs/reference/`)
- Modify: `tests/test_docs_config_options_drift.py`
- Create: `docs/site/src/content/docs/concepts/web-status-ui.mdx`

- [ ] **Step 1: Extend the drift test**

In `tests/test_docs_config_options_drift.py`, import `WebConfig` alongside `BusyLightConfig` (line 31) and add to the section-mapping dict (~line 95):

```python
    # [web] surfaces every WebConfig field — 1:1 TOML keys.
    "web": {f.name for f in fields(WebConfig)},
```

Then mirror the existing `BusyLightConfig`-specific test (~line 189) for `WebConfig` if the file's structure expects a per-block test — read the file and follow its pattern exactly.

- [ ] **Step 2: Run the drift test to see exactly what the docs page must contain**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_config_options_drift.py -v`
Expected: FAIL, naming the missing `[web]` table — the failure message tells you the required field set.

- [ ] **Step 3: Add the `[web]` table to the config-options reference page**

Follow the page's existing per-block table format (match `[busy_light]`'s table style exactly — column names, default formatting). Content:

| Field | Default | Description |
|---|---|---|
| `host` | `"0.0.0.0"` | Interface the sidecar binds |
| `port` | `8080` | Sidecar HTTP port |
| `token` | `""` | Optional shared token; non-empty enables auth on every route |
| `status_path` | `"/run/led-ticker/status.json"` | Where the display process publishes status (shared with the sidecar) |

Re-run the drift test until green.

- [ ] **Step 4: Write the docs page `docs/site/src/content/docs/concepts/web-status-ui.mdx`**

Follow `docs/DOCS-STYLE.md` (read it first — it is the rubric). Cover: what the sidecar shows (three tabs), enabling it (`[web]` block + compose service / systemd unit), the read-only design stance (validate in browser, apply by hand), auth + the always-on redaction, and the degraded states (no status yet / stale). Add the page to the docs sidebar following however neighboring concepts pages register (check `docs/site/astro.config.mjs` or the content collection config — copy a sibling's registration).

- [ ] **Step 5: Run docs lint + the full test suite**

Run: `make test` (full suite — instrumentation touched the engine; everything must pass)
Run: `uv run --extra dev ruff check src/ tests/`
If the docs site has a lint target (the pre-commit hook runs `docs-lint`), let the commit hook check it.

- [ ] **Step 6: Commit**

```bash
git add tests/test_docs_config_options_drift.py docs/site/
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs(web): config-options [web] table + web-status-ui concepts page"
```

---

### Task 13: Final check + PR

- [ ] **Step 1: Full suite + lint**

Run: `make test` — expected: all pass, coverage in line with the repo's ~95%.
Run: `uv run --extra dev ruff check src/ tests/` — expected: clean.

- [ ] **Step 2: Manual smoke test (no hardware needed)**

```bash
# Terminal A — fake a display process publishing:
PYTHONPATH=tests/stubs:src uv run python - <<'EOF'
import asyncio, time
from led_ticker.status_board import StatusBoard, set_active_board, record_section
async def main():
    b = StatusBoard(path="/tmp/lt-status/status.json")
    b.config_path = "demo"; set_active_board(b)
    record_section(index=0, total=2, mode="swap", title="demo", widget_count=3)
    while True:
        await asyncio.sleep(2); b.publish(force=True)
asyncio.run(main())
EOF
```

```bash
# Terminal B — the sidecar against a demo config:
printf '[web]\nstatus_path = "/tmp/lt-status/status.json"\nport = 8090\n' > /tmp/lt-demo.toml
PYTHONPATH=tests/stubs:src uv run led-ticker webui --config /tmp/lt-demo.toml
# Browse http://localhost:8090 — expect live dot, section "demo", validate tab works.
# Kill terminal A, wait ~6s, refresh — expect the stale indicator.
```

- [ ] **Step 3: Push and open the PR (do NOT merge — user confirms merges)**

```bash
git push -u origin feat/web-status-ui-spec
gh pr create --title "feat: web status UI sidecar (led-ticker webui)" --body "$(cat <<'EOF'
Read-only web status UI as an unprivileged sidecar, per the approved spec
(docs/superpowers/specs/2026-06-10-web-status-ui-design.md).

- Display process publishes versioned, throttled, atomic status.json (StatusBoard);
  publish failures self-disable and never touch the render path
- `led-ticker webui`: aiohttp sidecar with tabbed Status/Config/Validate page,
  /api/status (+staleness), /api/config (redacted), /api/validate (1MB cap)
- validate_config_text from-string entry point (parity-tested with the CLI path)
- Engine hooks: run_monitor_loop, Ticker._show_one, section loop — all no-op without [web]
- Import-purity tripwire (webui never imports rgbmatrix), schema tripwire,
  redaction test suite
- compose webui service (same image), systemd unit, example config, docs page + drift guard

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (done at plan-writing time)

- **Spec coverage:** every spec section maps to a task — config block (T1), publisher contract/throttle/failure (T2–3), engine instrumentation incl. monitor liveness + log tail (T3–4), validate-from-string (T5), redaction (T6), routes + degraded states + auth + 413/401 semantics (T7–8), tabbed page (T9), CLI + unprivileged/import purity (T10), compose/systemd/example config (T11), docs + drift (T12). Out-of-scope items (busy toggle, preview, apply) appear in no task — correct.
- **Known uncertainty, flagged inline where it bites:** `_format_json`'s exact shape (T8 step 3 note), `DisplayConfig.parallel` existence (T4 step 3 note), `deploy/led-ticker.service` conventions (T11 step 2), docs sidebar registration (T12 step 4), existing validate-suite filename (T5 step 4). Each step says how to resolve against the real file rather than guessing silently.
- **Type consistency check:** `StatusBoard.publish(force=)`, `record_section(index, total, mode, title, widget_count)`, `build_webui_app(config_path=, status_path=, token=)`, `serve_webui(... host, port ...)`, `WebConfig(host, port, token, status_path)` — used identically across tasks.

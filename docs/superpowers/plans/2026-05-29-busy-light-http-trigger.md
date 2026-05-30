# Busy-Light HTTP Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an HTTP push source to the shipped busy-light so a work Mac can flip it on/off via a hotkey macro or a macOS Focus automation over the LAN.

**Architecture:** Keep `BusyLight` as the state+painter. Add a `set_busy()`/`tick_ttl()` API and an optional TTL. Add `busy_http.py` — a one-route `aiohttp.web` app that authenticates and calls `set_busy()`. A `source = "file" | "http"` config knob (file = unchanged default) selects which background source `app/run.py` starts. Panel-agnostic; works on smallsign and bigsign.

**Tech Stack:** Python 3.13, asyncio, `aiohttp` (already a dep — `aiohttp.web` server + `aiohttp.test_utils` for tests), `attrs`, `tomllib`, pytest + pytest-asyncio (`asyncio_mode = "auto"`).

**Spec:** `docs/superpowers/specs/2026-05-29-busy-light-http-trigger-design.md`

**Conventions for every task:**
- Run individual tests with `PYTHONPATH=tests/stubs uv run pytest <path> -v` (the stubs path is what `make test` sets automatically).
- Commit with hooks disabled (worktree hooks are broken): `git -c core.hooksPath=/dev/null commit`.
- Line length limit is 88 (ruff). Run `make lint` before each commit.
- End commit messages with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

- `src/led_ticker/busy_light.py` (modify) — add `ttl_seconds` field, `_busy_until` deadline, `set_busy()`, `tick_ttl()`. Painter/file `update()` unchanged.
- `src/led_ticker/busy_http.py` (**new**) — `build_busy_app(busy, token)` (pure, testable) + `serve_busy(busy, *, host, port, token)` (production runner).
- `src/led_ticker/config.py` (modify) — `BusyLightConfig` gains `source`, `http_host`, `http_port`, `token`, `ttl_seconds`; parse + validation.
- `src/led_ticker/app/run.py` (modify) — replace the inline busy block with `_start_busy_light()`; branch on `source`; optional TTL ticker.
- `tests/test_busy_light.py` (modify) — `set_busy`/`tick_ttl` tests.
- `tests/test_busy_http.py` (**new**) — handler + serve_busy tests.
- `tests/test_config.py` (modify) — new-field parse + validation tests.
- `tests/test_app.py` (modify) — `_start_busy_light` wiring test.
- `docs/site/src/content/docs/concepts/busy-light.mdx` (modify) — remote-trigger section.
- `docs/site/src/content/docs/reference/config-options.mdx` (modify) — 5 new rows (drift-test enforced).
- `config/config.busy_longboi.toml`, `config/config.busy_smallsign.toml` (modify) — commented HTTP source block.
- `CLAUDE.md` (modify) — extend the overlay-hooks/busy-light invariant.

---

## Task 1: BusyLight gains `set_busy` + `tick_ttl` + optional TTL

**Files:**
- Modify: `src/led_ticker/busy_light.py`
- Test: `tests/test_busy_light.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_busy_light.py`:

```python
def test_set_busy_true_then_false():
    busy = BusyLight(file_path="/x")
    busy.set_busy(True)
    assert busy.is_busy is True
    busy.set_busy(False)
    assert busy.is_busy is False


def test_set_busy_no_ttl_leaves_no_deadline():
    busy = BusyLight(file_path="/x")  # ttl_seconds defaults to 0.0
    busy.set_busy(True, now=100.0)
    assert busy._busy_until is None


def test_ttl_arms_deadline_and_expires():
    busy = BusyLight(file_path="/x", ttl_seconds=30.0)
    busy.set_busy(True, now=100.0)
    assert busy._busy_until == 130.0
    busy.tick_ttl(now=129.0)  # before deadline
    assert busy.is_busy is True
    busy.tick_ttl(now=130.0)  # at deadline
    assert busy.is_busy is False
    assert busy._busy_until is None


def test_ttl_refresh_extends_deadline():
    busy = BusyLight(file_path="/x", ttl_seconds=30.0)
    busy.set_busy(True, now=100.0)
    busy.set_busy(True, now=120.0)  # refresh
    assert busy._busy_until == 150.0
    busy.tick_ttl(now=149.0)
    assert busy.is_busy is True


def test_set_busy_false_clears_deadline():
    busy = BusyLight(file_path="/x", ttl_seconds=30.0)
    busy.set_busy(True, now=100.0)
    busy.set_busy(False, now=110.0)
    assert busy.is_busy is False
    assert busy._busy_until is None


def test_tick_ttl_noop_when_no_deadline():
    busy = BusyLight(file_path="/x")
    busy.is_busy = True
    busy.tick_ttl(now=999.0)  # no deadline armed → must not clear
    assert busy.is_busy is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_busy_light.py -v -k "set_busy or ttl"`
Expected: FAIL — `BusyLight` has no `ttl_seconds`/`set_busy`/`tick_ttl`/`_busy_until`.

- [ ] **Step 3: Implement**

In `src/led_ticker/busy_light.py`, add `import time` under `from pathlib import Path`:

```python
import time
from pathlib import Path
```

Add the `ttl_seconds` field and `_busy_until` to the `BusyLight` class, right after the `size` field and before `is_busy`:

```python
    size: int = 4
    ttl_seconds: float = 0.0
    is_busy: bool = attrs.field(default=False, init=False)
    _busy_until: float | None = attrs.field(default=None, init=False)
```

Add these two methods after `update()`:

```python
    def set_busy(self, state: bool, now: float | None = None) -> None:
        """Set busy state from a push source. Arms the TTL deadline when
        ttl_seconds > 0 and state is True; clears it on False."""
        if state:
            self.is_busy = True
            if self.ttl_seconds > 0:
                t = time.monotonic() if now is None else now
                self._busy_until = t + self.ttl_seconds
        else:
            self.is_busy = False
            self._busy_until = None

    def tick_ttl(self, now: float | None = None) -> None:
        """Clear busy state once the TTL deadline passes. No-op when no
        deadline is armed. Kept off the paint path so paint() stays
        paint-only."""
        if self._busy_until is None:
            return
        t = time.monotonic() if now is None else now
        if t >= self._busy_until:
            self.is_busy = False
            self._busy_until = None
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_busy_light.py -v`
Expected: PASS (all existing + 6 new).

- [ ] **Step 5: Lint + commit**

```bash
make lint
git add src/led_ticker/busy_light.py tests/test_busy_light.py
git -c core.hooksPath=/dev/null commit -m "feat: BusyLight.set_busy/tick_ttl with optional TTL

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `busy_http.py` — the HTTP listener

**Files:**
- Create: `src/led_ticker/busy_http.py`
- Test: `tests/test_busy_http.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_busy_http.py`:

```python
"""Tests for the busy-light HTTP listener."""

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

from led_ticker.busy_http import build_busy_app, serve_busy
from led_ticker.busy_light import BusyLight


async def _client(busy, token=""):
    app = build_busy_app(busy, token=token)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def test_get_query_sets_busy_on_and_off():
    busy = BusyLight(file_path="/x")
    client = await _client(busy)
    try:
        resp = await client.get("/busy", params={"state": "on"})
        assert resp.status == 200
        assert (await resp.json())["busy"] is True
        assert busy.is_busy is True

        resp = await client.get("/busy", params={"state": "off"})
        assert (await resp.json())["busy"] is False
        assert busy.is_busy is False
    finally:
        await client.close()


async def test_post_body_sets_busy():
    busy = BusyLight(file_path="/x")
    client = await _client(busy)
    try:
        resp = await client.post("/busy", data="on")
        assert resp.status == 200
        assert busy.is_busy is True
    finally:
        await client.close()


async def test_get_no_state_reports_current():
    busy = BusyLight(file_path="/x")
    busy.is_busy = True
    client = await _client(busy)
    try:
        resp = await client.get("/busy")
        assert resp.status == 200
        assert (await resp.json())["busy"] is True
    finally:
        await client.close()


async def test_bad_state_returns_400():
    busy = BusyLight(file_path="/x")
    client = await _client(busy)
    try:
        resp = await client.get("/busy", params={"state": "maybe"})
        assert resp.status == 400
        assert busy.is_busy is False
    finally:
        await client.close()


async def test_token_required_when_configured():
    busy = BusyLight(file_path="/x")
    client = await _client(busy, token="s3cret")
    try:
        # missing token
        resp = await client.get("/busy", params={"state": "on"})
        assert resp.status == 401
        assert busy.is_busy is False
        # query token
        resp = await client.get("/busy", params={"state": "on", "token": "s3cret"})
        assert resp.status == 200
        assert busy.is_busy is True
        # header token
        busy.is_busy = False
        resp = await client.get(
            "/busy", params={"state": "on"}, headers={"X-Busy-Token": "s3cret"}
        )
        assert resp.status == 200
        assert busy.is_busy is True
    finally:
        await client.close()


async def test_wrong_token_returns_401():
    busy = BusyLight(file_path="/x")
    client = await _client(busy, token="s3cret")
    try:
        resp = await client.get("/busy", params={"state": "on", "token": "nope"})
        assert resp.status == 401
        assert busy.is_busy is False
    finally:
        await client.close()


async def test_serve_busy_binds_and_responds():
    busy = BusyLight(file_path="/x")
    runner = await serve_busy(busy, host="127.0.0.1", port=0)
    try:
        port = runner.addresses[0][1]
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"http://127.0.0.1:{port}/busy", params={"state": "on"}
            ) as r:
                assert r.status == 200
        assert busy.is_busy is True
    finally:
        await runner.cleanup()
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_busy_http.py -v`
Expected: FAIL — `led_ticker.busy_http` does not exist.

- [ ] **Step 3: Implement**

Create `src/led_ticker/busy_http.py`:

```python
"""HTTP push source for the busy light.

A one-route aiohttp app that flips BusyLight.is_busy from a remote trigger
(a work Mac's hotkey macro or macOS Focus automation). aiohttp is already a
runtime dependency (used as a client by the data widgets); this is the first
server. build_busy_app() is pure for testing; serve_busy() is the production
runner.
"""

from __future__ import annotations

import logging

from aiohttp import web

from led_ticker.busy_light import BusyLight

logger = logging.getLogger(__name__)

_TRUTHY = frozenset({"on", "1", "true"})
_FALSY = frozenset({"off", "0", "false"})


def _token_ok(request: web.Request, token: str) -> bool:
    if not token:
        return True
    provided = request.headers.get("X-Busy-Token") or request.query.get("token")
    return provided == token


def build_busy_app(busy: BusyLight, token: str = "") -> web.Application:
    """Build the aiohttp app. GET /busy?state=on|off or POST /busy (body=on|off)
    flips the flag; GET /busy with no state reports current state."""

    async def handle(request: web.Request) -> web.Response:
        if not _token_ok(request, token):
            return web.json_response({"error": "unauthorized"}, status=401)
        state = request.query.get("state")
        if state is None and request.body_exists:
            state = (await request.text()).strip()
        if state is None:
            return web.json_response({"busy": busy.is_busy})
        s = state.strip().lower()
        if s in _TRUTHY:
            busy.set_busy(True)
        elif s in _FALSY:
            busy.set_busy(False)
        else:
            return web.json_response({"error": "bad state"}, status=400)
        return web.json_response({"busy": busy.is_busy})

    app = web.Application()
    app.router.add_get("/busy", handle)
    app.router.add_post("/busy", handle)
    return app


async def serve_busy(
    busy: BusyLight, *, host: str, port: int, token: str = ""
) -> web.AppRunner:
    """Start the listener and return the running AppRunner (caller keeps it
    alive and calls .cleanup() on shutdown)."""
    runner = web.AppRunner(build_busy_app(busy, token=token))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("busy-light HTTP listener on %s:%d", host, port)
    return runner
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_busy_http.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Lint + commit**

```bash
make lint
git add src/led_ticker/busy_http.py tests/test_busy_http.py
git -c core.hooksPath=/dev/null commit -m "feat: busy_http HTTP listener (build_busy_app + serve_busy)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Config fields + validation

**Files:**
- Modify: `src/led_ticker/config.py` (`BusyLightConfig` ~line 153; parse ~line 329; validation ~line 337)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_busy_light_http_fields_default(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    cfg = load_config(p)
    assert cfg.busy_light.source == "file"
    assert cfg.busy_light.http_host == "0.0.0.0"
    assert cfg.busy_light.http_port == 8080
    assert cfg.busy_light.token == ""
    assert cfg.busy_light.ttl_seconds == 0.0


def test_busy_light_http_fields_parsed(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[busy_light]\nenabled=true\nsource="http"\n'
        'http_host="127.0.0.1"\nhttp_port=9000\ntoken="abc"\nttl_seconds=300.0\n\n'
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    cfg = load_config(p)
    assert cfg.busy_light.source == "http"
    assert cfg.busy_light.http_host == "127.0.0.1"
    assert cfg.busy_light.http_port == 9000
    assert cfg.busy_light.token == "abc"
    assert cfg.busy_light.ttl_seconds == 300.0


def test_busy_light_invalid_source_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[busy_light]\nenabled=true\nsource="carrier_pigeon"\n\n'
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="busy_light.source"):
        load_config(p)


def test_busy_light_invalid_port_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[busy_light]\nenabled=true\nhttp_port=70000\n\n'
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="busy_light.http_port"):
        load_config(p)


def test_busy_light_negative_ttl_raises(tmp_path):
    import pytest

    p = tmp_path / "c.toml"
    p.write_text(
        "[display]\nrows=16\ncols=32\n\n"
        '[busy_light]\nenabled=true\nttl_seconds=-1.0\n\n'
        '[[playlist.section]]\nmode="swap"\n\n'
        '[[playlist.section.widget]]\ntype="message"\ntext="hi"\n'
    )
    with pytest.raises(ValueError, match="busy_light.ttl_seconds"):
        load_config(p)
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_config.py -v -k "busy_light_http or busy_light_invalid_source or busy_light_invalid_port or busy_light_negative_ttl"`
Expected: FAIL — `BusyLightConfig` has no `source`/`http_host`/`http_port`/`token`/`ttl_seconds`.

- [ ] **Step 3: Implement**

In `src/led_ticker/config.py`, extend the `BusyLightConfig` dataclass (the block ending at `size: int = 4`):

```python
@dataclass
class BusyLightConfig:
    enabled: bool = False
    file_path: str = "~/.busy"
    poll_interval: float = 5.0
    corner: str = "top_right"
    color: tuple[int, int, int] = (255, 0, 0)
    size: int = 4
    source: str = "file"
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    token: str = ""
    ttl_seconds: float = 0.0
```

Extend the `BusyLightConfig(...)` construction (~line 329) with the new kwargs:

```python
    busy_light = BusyLightConfig(
        enabled=bl_raw.get("enabled", False),
        file_path=bl_raw.get("file_path", "~/.busy"),
        poll_interval=bl_raw.get("poll_interval", 5.0),
        corner=bl_raw.get("corner", "top_right"),
        color=tuple(bl_raw.get("color", [255, 0, 0])),
        size=bl_raw.get("size", 4),
        source=bl_raw.get("source", "file"),
        http_host=bl_raw.get("http_host", "0.0.0.0"),
        http_port=bl_raw.get("http_port", 8080),
        token=bl_raw.get("token", ""),
        ttl_seconds=bl_raw.get("ttl_seconds", 0.0),
    )
```

Add validation immediately after the existing `busy_light.color` check (after line ~353, before the function continues):

```python
    _BUSY_SOURCES = ("file", "http")
    if busy_light.source not in _BUSY_SOURCES:
        raise ValueError(
            f"busy_light.source={busy_light.source!r} is not valid; "
            f"choose one of: {', '.join(_BUSY_SOURCES)}."
        )
    if not 1 <= busy_light.http_port <= 65535:
        raise ValueError(
            f"busy_light.http_port must be 1-65535; got {busy_light.http_port}."
        )
    if busy_light.ttl_seconds < 0:
        raise ValueError(
            f"busy_light.ttl_seconds must be >= 0; got {busy_light.ttl_seconds}."
        )
    if not isinstance(busy_light.token, str):
        raise ValueError(
            f"busy_light.token must be a string; got {type(busy_light.token).__name__}."
        )
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_config.py -v -k busy_light`
Expected: PASS (existing busy_light tests + 5 new).

- [ ] **Step 5: Lint + commit**

```bash
make lint
git add src/led_ticker/config.py tests/test_config.py
git -c core.hooksPath=/dev/null commit -m "feat: busy_light HTTP source config fields + validation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Wire the source into `app/run.py`

**Files:**
- Modify: `src/led_ticker/app/run.py` (imports ~line 32; busy block lines 48-61)
- Test: `tests/test_app.py`

**Context:** The current inline block (lines 48-61 of `run.py`) builds `BusyLight`, registers `busy.paint`, and starts a file poller. Replace it with a module-level `_start_busy_light()` helper that also handles the HTTP source and the optional TTL ticker. This keeps `run()` lean and makes the wiring unit-testable.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py` (top-level, alongside the other tests):

```python
class TestStartBusyLight:
    async def test_file_source_registers_hook_and_reads_file(self, tmp_path):
        from led_ticker.app.run import _start_busy_light
        from led_ticker.config import BusyLightConfig
        from led_ticker.frame import LedFrame

        f = tmp_path / ".busy"
        f.write_text("")
        cfg = BusyLightConfig(
            enabled=True, source="file", file_path=str(f), poll_interval=999
        )
        frame = LedFrame(led_cols=64, led_rows=32)
        busy = await _start_busy_light(cfg, frame)
        assert busy.paint in frame.overlay_hooks
        assert busy.is_busy is True  # initial update() read the existing file

    async def test_http_source_registers_hook_and_threads_ttl(self):
        from led_ticker.app.run import _start_busy_light
        from led_ticker.config import BusyLightConfig
        from led_ticker.frame import LedFrame

        cfg = BusyLightConfig(
            enabled=True,
            source="http",
            http_host="127.0.0.1",
            http_port=0,
            ttl_seconds=120.0,
        )
        frame = LedFrame(led_cols=64, led_rows=32)
        busy = await _start_busy_light(cfg, frame)
        assert busy.paint in frame.overlay_hooks
        assert busy.ttl_seconds == 120.0
        assert busy.is_busy is False  # http source starts not-busy
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py -v -k TestStartBusyLight`
Expected: FAIL — `_start_busy_light` does not exist.

- [ ] **Step 3: Implement**

In `src/led_ticker/app/run.py`, add the import near the other `led_ticker` imports (after the `from led_ticker.widget import run_monitor_loop` line):

```python
from led_ticker.busy_http import serve_busy
```

Add these module-level helpers below the imports, above `async def run(...)`:

```python
async def _ttl_ticker(busy: Any, interval: float = 1.0) -> None:
    """Clear pushed busy state once its TTL expires. 1 Hz; no-op when no
    deadline is armed."""
    while True:
        await asyncio.sleep(interval)
        busy.tick_ttl()


async def _serve_busy_supervised(busy: Any, cfg: Any) -> None:
    """Run the HTTP listener for the process lifetime. A bind failure logs
    and returns — the display loop must never die because the busy port is
    taken."""
    try:
        runner = await serve_busy(
            busy, host=cfg.http_host, port=cfg.http_port, token=cfg.token
        )
    except OSError as e:
        logging.error(
            "busy-light HTTP listener failed to bind %s:%d (%s); "
            "continuing without remote trigger",
            cfg.http_host,
            cfg.http_port,
            e,
        )
        return
    try:
        await asyncio.Event().wait()  # keep the runner alive
    finally:
        await runner.cleanup()


async def _start_busy_light(cfg: Any, led_frame: Any) -> Any:
    """Build the BusyLight, register its paint hook, and start the source
    (file poller or HTTP listener) plus an optional TTL ticker. Returns the
    BusyLight."""
    from led_ticker.busy_light import BusyLight

    busy = BusyLight(
        file_path=cfg.file_path,
        corner=cfg.corner,
        color=cfg.color,
        size=cfg.size,
        ttl_seconds=cfg.ttl_seconds,
    )
    led_frame.overlay_hooks.append(busy.paint)
    if cfg.source == "http":
        asyncio.create_task(_serve_busy_supervised(busy, cfg))
    else:
        await busy.update()  # fast initial read so the dot is correct on frame 1
        asyncio.create_task(run_monitor_loop(busy, cfg.poll_interval, splay=False))
    if cfg.ttl_seconds > 0:
        asyncio.create_task(_ttl_ticker(busy))
    return busy
```

Replace the inline busy block (current lines 48-61) with:

```python
    if config.busy_light.enabled:
        await _start_busy_light(config.busy_light, led_frame)
```

- [ ] **Step 4: Run to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py -v -k TestStartBusyLight`
Expected: PASS (2 tests).

Then confirm nothing else broke in the app suite:
Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py -q`
Expected: PASS.

- [ ] **Step 5: Lint + typecheck + commit**

```bash
make lint
make typecheck
git add src/led_ticker/app/run.py tests/test_app.py
git -c core.hooksPath=/dev/null commit -m "feat: wire busy_light file/http source in app.run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Docs, example configs, and CLAUDE.md invariant

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx` (`## \`[busy_light]\`` table)
- Modify: `docs/site/src/content/docs/concepts/busy-light.mdx`
- Modify: `config/config.busy_longboi.toml`, `config/config.busy_smallsign.toml`
- Modify: `CLAUDE.md` (the "Overlay hooks" invariant bullet)
- Test: `tests/test_docs_config_options_drift.py` (already imports the field set — no edit needed; it just must pass)

**Context:** `test_busy_light_section_field_set_matches_docs` derives the documented field set from `fields(BusyLightConfig)`, so it will FAIL until the 5 new fields appear as rows in the `[busy_light]` table. That failing test is the gate for this task.

- [ ] **Step 1: Confirm the drift test now fails**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_config_options_drift.py -v -k busy_light`
Expected: FAIL — `source`, `http_host`, `http_port`, `token`, `ttl_seconds` missing from the docs table.

- [ ] **Step 2: Add the 5 rows to `config-options.mdx`**

In `docs/site/src/content/docs/reference/config-options.mdx`, under the `## \`[busy_light]\`` table, append these rows (match the existing column layout — Field / Type / Default / Notes):

```markdown
| `source`       | string      | `"file"`      | `"file"` (poll a local file) or `"http"` (remote push from a LAN HTTP call). |
| `http_host`    | string      | `"0.0.0.0"`   | Listen address when `source = "http"`. `0.0.0.0` = all interfaces.           |
| `http_port`    | int         | `8080`        | Listen port when `source = "http"`. Range 1–65535.                           |
| `token`        | string      | `""`          | Shared secret for the HTTP source. Empty = open (trusted LAN only).          |
| `ttl_seconds`  | float       | `0.0`         | HTTP source: busy auto-clears after this many seconds unless refreshed. `0` = explicit on/off only. |
```

- [ ] **Step 3: Run the drift test to verify it passes**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_config_options_drift.py -v -k busy_light`
Expected: PASS.

- [ ] **Step 4: Add the remote-trigger section to `busy-light.mdx`**

In `docs/site/src/content/docs/concepts/busy-light.mdx`, after the `## Toggling it` / Docker section and before `## Sizing per panel`, insert a new section:

````markdown
## Remote trigger (HTTP)

Instead of (or as well as) a local file, the light can be flipped by an HTTP call over your LAN — ideal for triggering it from another machine such as a work laptop. Set `source = "http"`:

<TomlExample
  title="HTTP source"
  code={`[busy_light]
enabled = true
source = "http"
http_host = "0.0.0.0"
http_port = 8080
token = "change-me"      # shared secret; omit/empty = open on the LAN
ttl_seconds = 0          # 0 = explicit on/off; >0 = auto-clear after N seconds`}
/>

The listener exposes one route:

```bash
# turn the light on / off (GET with a query param — easiest for macros)
curl "http://PI-HOST:8080/busy?state=on&token=change-me"
curl "http://PI-HOST:8080/busy?state=off&token=change-me"

# POST with a body works too
curl -X POST "http://PI-HOST:8080/busy" -H "X-Busy-Token: change-me" -d on

# read current state
curl "http://PI-HOST:8080/busy?token=change-me"
```

`PI-HOST` is your Pi's `.local` hostname (e.g. `longboi.local`) or a DHCP-reserved IP. The token may be passed as the `token=` query param or an `X-Busy-Token:` header; a wrong/missing token returns `401`. A token in the query string can appear in logs — fine on a trusted LAN; use the header form if you'd rather not.

### Exposing the port

- **Docker deploy:** add a port mapping to that Pi's compose service:

  ```yaml
  services:
    led-ticker:
      ports:
        - "8080:8080"
  ```

- **Bare-metal / systemd deploy:** the process binds the host port directly — no mapping needed; just make sure no host firewall blocks it.

### TTL (auto-clear)

With `ttl_seconds = 0` the light stays on until an explicit `state=off` arrives. Set it to a positive value (e.g. `1800`) and the light auto-clears after that many seconds unless a fresh `state=on` refreshes it — a safety net if the sender sleeps mid-meeting and never sends `off`.

### Triggering from a Mac

Both reduce to one HTTP call, so neither needs anything installed on a managed work laptop:

- **Manual hotkey** — Keyboard Maestro, Raycast, or a Shortcut with a global key running `curl "http://PI-HOST:8080/busy?state=on&token=…"` (and an `off` twin).
- **Focus automation (hands-off)** — macOS **Shortcuts → Automation → "When [Work] focus turns On"** → action **Get Contents of URL** (GET) `http://PI-HOST:8080/busy?state=on&token=…`; add a matching *turns Off* automation with `state=off`. macOS itself is the detector — no background app of your own.
````

- [ ] **Step 5: Add a commented HTTP block to both example configs**

Append to `config/config.busy_longboi.toml` (after the existing `[busy_light]` block) — keep it commented so the file source stays the active one:

```toml
# --- Remote HTTP trigger (alternative to the file source above) ---
# Flip the light from another machine on the LAN (e.g. a work Mac hotkey or
# macOS Focus automation). Docker: also add `ports: ["8080:8080"]` to the
# compose service. See https://docs.ledticker.dev/concepts/busy-light/
# [busy_light]
# enabled = true
# source = "http"
# http_host = "0.0.0.0"
# http_port = 8080
# token = "change-me"
# size = 8            # ~8-10 px on the 64-tall longboi
# ttl_seconds = 0
```

Append the same block to `config/config.busy_smallsign.toml`, but with `size = 4` (the 16-tall smallsign) instead of `size = 8`.

- [ ] **Step 6: Extend the CLAUDE.md invariant**

In `CLAUDE.md`, find the **Overlay hooks** bullet (`**Overlay hooks** (`frame.py`) — …`). Append to the end of that bullet:

```markdown
The busy source is selectable via `[busy_light]` `source = "file"` (poll, default) or `"http"` (push). The HTTP listener (`busy_http.serve_busy`, an `aiohttp.web` app — aiohttp is already a client-side dep) runs as a **supervised** task: a bind failure or crash logs and the display loop keeps running (a busy port must never freeze the panel). Optional `ttl_seconds` auto-clears pushed busy state via a 1 Hz ticker calling `BusyLight.tick_ttl()` — expiry lives in the ticker, never in `paint()`, so `paint()` stays paint-only.
```

- [ ] **Step 7: Run the full docs + drift + format checks**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_docs_config_options_drift.py -v`
Expected: PASS.

Run: `make docs-lint`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add docs/ config/config.busy_longboi.toml config/config.busy_smallsign.toml CLAUDE.md
git -c core.hooksPath=/dev/null commit -m "docs: document busy_light HTTP source + example configs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] **Full suite + lint + typecheck**

```bash
make lint
make typecheck
make test
```
Expected: all green; coverage ≥ 90%.

- [ ] **Config preflight on the smoke configs**

```bash
make validate CONFIG=config/config.busy_smallsign.toml
make validate CONFIG=config/config.busy_longboi.toml
```
Expected: no errors.

- [ ] Hand off to `superpowers:finishing-a-development-branch`.
```

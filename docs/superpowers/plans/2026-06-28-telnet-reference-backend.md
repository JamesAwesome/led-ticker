# Telnet Reference Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the `Backend` API is usable by an external plugin author by shipping the `api.backend()` plugin surface (core) + a self-contained `telnet` backend (plugins monorepo) that renders the sign as ANSI color in a terminal.

**Architecture:** Two phases, two repos, sequential. **Phase A (core, led-ticker):** add `api.backend()` (buffered + namespaced like every plugin registration, committed via the existing `_REGISTRY_MAP` machinery), export `HeadlessCanvas`, lock the registration-before-selection order, audit `isinstance` leaks, document the lifecycle. **Phase B (plugins monorepo):** a `led-ticker-telnet` package whose `TelnetBackend` reuses `HeadlessCanvas`, serializes each frame to a 24-bit-color half-block (`▀`) ANSI frame, and broadcasts it over a stdlib-`asyncio` TCP server. The backend is the vehicle; **the gaps found = fixed-or-documented are the deliverable.**

**Tech Stack:** Python 3.14 (PEP 649; no `from __future__ import annotations`), attrs, asyncio, the led-ticker plugin entry-point system, uv workspaces.

## Global Constraints
- **TDD**; frequent commits; commit trailer on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh
  ```
- **Plugin backends are namespaced** (`backend = "telnet.telnet"`); built-in backends stay bare (`headless`/`rgbmatrix`).
- **Plugins import ONLY `led_ticker.plugin`** (the public surface). No `from __future__ import annotations` (PEP 649) anywhere.
- **Config via env**: `LED_TICKER_TELNET_PORT` (default `2300`), `LED_TICKER_TELNET_HOST` (default `0.0.0.0`). No TOML config-passing — documented as the headline finding.
- **Production `rgbmatrix` path unchanged / byte-identical.** Webui stays rgbmatrix-pure.
- **Core gates:** `PYTHONPATH=tests/stubs uv run --extra dev pytest` (full suite); `uv run --extra dev ruff check src/ tests/` + `ruff format`; `pyright src/`.
- **Plugin gates** (per-package, run inside `plugins/telnet/`): `uv run pytest --cov=src`; `uv run ruff check src tests` + `ruff format`; `uv run pyright src`.
- **Constraints honored:** #1 (never freeze the panel — bind failure degrades), #3 (no Canvas `GetPixel`; the backend reads *its own* canvas via the public `get_pixel`), #8 (`swap` returns a *different* buffer).
- **NON-GOALS:** browser/web backend or reusing the webui preview pipe; full telnet IAC negotiation (raw TCP + ANSI); a TOML config-passing mechanism (documented finding only); any rgbmatrix change.

---

# PHASE A — Core (`led-ticker`)

Worktree `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/telnet`, branch `feat/telnet-reference-backend` (already created off `origin/main`). Run `make dev` once before starting. This phase is its own PR; merge (or local editable install) before Phase B's tests can pass.

## Task A1: Plugin backend surface — `api.backend()` + `HeadlessCanvas` export + serialization read

**Files:**
- Modify `src/led_ticker/plugin.py` (add `"backends"` buffer key, `backend()` method, export `HeadlessCanvas`)
- Modify `src/led_ticker/_plugin_loader.py` (add `"backends"` → backend registry in `_REGISTRY_MAP`)
- Modify `src/led_ticker/backends/headless.py` (relabel `get_pixel` as a supported backend-serialization read)
- Test: `tests/test_plugins/test_plugin_api.py`

**Interfaces — Produces:** `PluginAPI.backend(name) -> decorator` (buffers `namespace.name` into `_buffers["backends"]`); `led_ticker.plugin.HeadlessCanvas`; the `"backends"` surface commits to the backend `_REGISTRY`.

- [ ] **Step 1: failing tests** (add to `tests/test_plugins/test_plugin_api.py`):
```python
def test_api_backend_buffers_namespaced():
    from led_ticker.plugin import PluginAPI
    api = PluginAPI(namespace="acme")
    class B:
        def setup(self): ...
        def create_canvas(self): ...
        def swap(self, c): ...
    api.backend("web")(B)
    assert api._buffers["backends"] == {"acme.web": B}


def test_backends_surface_commits_to_backend_registry():
    from led_ticker._plugin_loader import _REGISTRY_MAP
    from led_ticker.backends import _REGISTRY
    assert _REGISTRY_MAP["backends"] is _REGISTRY


def test_headless_canvas_on_public_surface():
    import led_ticker.plugin as p
    from led_ticker.backends.headless import HeadlessCanvas
    assert p.HeadlessCanvas is HeadlessCanvas
    assert "HeadlessCanvas" in p.__all__
```

- [ ] **Step 2: run, expect fail** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_plugins/test_plugin_api.py -k "backend or headless_canvas" -v`.

- [ ] **Step 3: implement.**
  In `src/led_ticker/plugin.py`: add `"backends": {},` to the `self._buffers` dict (after `"fonts": {}`). Add the method next to `transition()`:
```python
    def backend(self, name: str) -> Callable[[_T], _T]:
        """Register a rendering Backend under ``namespace.name``.

        Buffered + namespaced like every plugin registration; the loader commits
        it to the backend registry. Plugin backends are therefore selected as
        ``[display] backend = "<namespace>.<name>"`` (built-in headless/rgbmatrix
        stay bare). A backend implements setup()/create_canvas()/swap() — see the
        Backend protocol in led_ticker.plugin."""

        def deco(cls: _T) -> _T:
            self._buffers["backends"][self._qualify(name)] = cls
            return cls

        return deco
```
  Change the headless import to also bring the canvas, and add it to `__all__`:
```python
from led_ticker.backends.headless import HeadlessBackend, HeadlessCanvas
```
  Add `"HeadlessCanvas",` to `__all__` (next to `"HeadlessBackend"`).
  In `src/led_ticker/_plugin_loader.py`: add the import + map entry:
```python
from led_ticker.backends import _REGISTRY as _BACKEND_REGISTRY
```
  and add to `_REGISTRY_MAP`:
```python
    "backends": _BACKEND_REGISTRY,
```
  In `src/led_ticker/backends/headless.py`: relabel the `get_pixel`/`count_nonzero` comment (line ~59) from `# Test-only helpers (not part of the Canvas contract).` to:
```python
    # Read accessors (not part of the Canvas contract). get_pixel is the
    # supported way a backend serializes its OWN canvas's accumulated pixels
    # (constraint #3 bans Canvas GetPixel for the engine, not a backend reading
    # the canvas it created); count_nonzero is test-only.
```

- [ ] **Step 4: run, expect pass.** Then full suite + ruff + pyright (Global Constraints). Confirm `tests/test_webui_purity.py` still green.
- [ ] **Step 5: commit** (`feat(plugin): api.backend() + HeadlessCanvas export for external backend plugins`).

## Task A2: Registration-before-selection load-order tripwire

**Files:** Test `tests/test_app/test_run_order.py` (or alongside the existing reconcile-order tripwire — search `git grep -l "build_frame_from_config" tests/`)

**Interfaces — Consumes:** the run-order in `src/led_ticker/app/run.py` (`reconcile` → `_load_plugins_for_config` → `build_frame_from_config`).

- [ ] **Step 1: failing test** (create the file or add to the located one):
```python
def test_load_plugins_precedes_backend_build():
    """A plugin backend must be registered (load_plugins) before the engine
    selects/builds it (build_frame_from_config). Lock the source order so a
    refactor can't reverse it."""
    import inspect
    import led_ticker.app.run as run
    src = inspect.getsource(run.run)
    i_load = src.index("_load_plugins_for_config(")
    i_build = src.index("build_frame_from_config(")
    assert i_load < i_build, (
        "load_plugins must precede build_frame_from_config so a plugin-registered "
        "backend is available when the engine selects it"
    )
```
- [ ] **Step 2: run, expect PASS immediately** (the order already holds). This is a *lock*, not a fix — confirm it passes, and confirm it would fail if reversed (temporarily swap the two call sites locally, see red, revert). Note that confirmation in the report.
- [ ] **Step 3:** (no production change.) **Step 4:** full suite green. **Step 5: commit** (`test: lock load_plugins-before-build_frame ordering for plugin backends`).

## Task A3: `isinstance`-leak audit tripwire

**Files:** Test `tests/test_backends/test_no_concrete_backend_gates.py`; possibly Modify engine files if a leak is found.

**Interfaces — Produces:** a tripwire asserting the engine never gates behavior on a *concrete backend class*, so a non-rgbmatrix backend can't be silently mishandled.

- [ ] **Step 1: run the audit** (record output in the report):
```bash
grep -rnE "isinstance\([^)]*,\s*(RgbMatrixBackend|RGBMatrix|HeadlessBackend|HeadlessCanvas)\b" \
  src/led_ticker/frame.py src/led_ticker/ticker.py src/led_ticker/app/run.py src/led_ticker/scaled_canvas.py
```
  Note: `isinstance(canvas, ScaledCanvas)` is EXPECTED and correct (the public wrapper, not a backend type) — it is NOT a leak. The audit targets concrete *backend* classes and the raw *headless canvas* class.
- [ ] **Step 2: failing/locking test:**
```python
def test_engine_does_not_gate_on_concrete_backend_types():
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "led_ticker"
    files = ["frame.py", "ticker.py", "app/run.py", "scaled_canvas.py"]
    pat = re.compile(r"isinstance\([^)]*,\s*(RgbMatrixBackend|HeadlessBackend|HeadlessCanvas)\b")
    offenders = {}
    for f in files:
        text = (root / f).read_text()
        hits = [ln for ln in text.splitlines() if pat.search(ln)]
        if hits:
            offenders[f] = hits
    assert not offenders, (
        f"engine gates on a concrete backend/canvas type — a non-rgbmatrix backend "
        f"would silently miss this branch: {offenders}"
    )
```
- [ ] **Step 3:** If the test fails (a real leak exists): fix the engine to dispatch on the protocol / duck-typing / `is_scaled()` instead of the concrete class, with a focused regression test for the corrected behavior. If it passes (no leak): the tripwire stands as the permanent guard. Document the audit outcome in the report either way.
- [ ] **Step 4:** full suite green. **Step 5: commit** (`test: tripwire — engine must not gate on concrete backend/canvas types`).

## Task A4: Backend-author lifecycle — loud failure + async-spawn doc

**Files:**
- Test `tests/test_backends/test_backend_selection.py`
- Modify `src/led_ticker/backends/__init__.py` (doc the async-spawn lifecycle on the `Backend` protocol docstring)
- Modify `docs/plugin-system.md` (a short "authoring a backend plugin" note)

- [ ] **Step 1: failing test** (loud failure on a missing/typo'd backend):
```python
def test_unknown_backend_errors_loudly_listing_known():
    from led_ticker.backends import get_backend_class
    import pytest
    with pytest.raises(ValueError) as ei:
        get_backend_class("telnet")  # bare — plugin backends are namespaced
    msg = str(ei.value)
    assert "unknown backend 'telnet'" in msg
    assert "known backends" in msg  # lists what IS available so the user self-corrects
```
- [ ] **Step 2: run** — expect PASS (registry already raises this). If it passes, the behavior is locked; if the message differs, adjust the assertion to the real message (don't change production unless the message is unhelpful).
- [ ] **Step 3: document the lifecycle.** In `src/led_ticker/backends/__init__.py`, extend the `Backend` protocol docstring with:
```python
    # Lifecycle: setup() is called from INSIDE the running asyncio loop (via
    # LedFrame.setup() in app.run.run()), so a backend that needs background I/O
    # may `asyncio.get_running_loop().create_task(...)` from setup(). setup() is
    # still a sync def — guard get_running_loop() with try/except RuntimeError so
    # the backend also works when constructed outside a loop (e.g. conformance).
```
  In `docs/plugin-system.md`, add a short "Authoring a backend plugin" subsection: register via `api.backend("name")` (namespaced → `[display] backend = "<ns>.name"`); implement `setup`/`create_canvas`/`swap` (swap returns a *different* buffer — constraint #8); reuse `HeadlessCanvas` + its `get_pixel` to serialize; the async-spawn pattern above; and the **known limitation: plugin backends cannot yet take TOML `[display]` config — use env vars** (a possible future `[display.<backend>]` → `from_config` mechanism).
- [ ] **Step 4:** full suite + `make docs-build` + `make docs-lint` green. **Step 5: commit** (`docs: backend-author lifecycle + loud-failure guarantee`).

**End of Phase A → open the core PR, pause for merge go-ahead.**

---

# PHASE B — `led-ticker-telnet` plugin (plugins monorepo)

Repo `/Users/james/projects/github/jamesawesome/led-ticker-plugins` (uv workspace). **Create a separate worktree** (e.g. `git worktree add -b feat/telnet-backend ../led-ticker-plugins-worktrees/telnet origin/main`) and work there. **Cross-repo setup:** this phase imports the Phase-A surface (`api.backend`, `HeadlessCanvas`), which is unreleased — install the local core worktree editable into the plugin's venv so it's importable:
```bash
cd <plugin-worktree>/plugins/telnet
uv sync --extra dev
uv pip install -e /Users/james/projects/github/jamesawesome/led-ticker-worktrees/telnet
```
Pin `led-ticker-core` in `pyproject.toml` to the version that ships `api.backend()` (bump core's version in the Phase-A PR; pin `>=` that here). Phase-A PR must merge (or the editable install above) before Phase-B tests pass against released core.

## Task B1: Scaffold `led-ticker-telnet` + conformant `TelnetBackend` skeleton (no network)

**Files (create, copying `plugins/calendar/` as the template):**
- `plugins/telnet/pyproject.toml`, `README.md`, `CLAUDE.md`, `LICENSE`, `Makefile`, `.pre-commit-config.yaml`, `.gitignore`
- `plugins/telnet/src/led_ticker_telnet/__init__.py`, `plugins/telnet/src/led_ticker_telnet/backend.py`
- `plugins/telnet/tests/conftest.py`, `tests/test_import_purity.py`, `tests/test_telnet_backend.py`

**Interfaces — Produces:** `led_ticker_telnet.backend.TelnetBackend(width, height)` satisfying the `Backend` protocol + Canvas conformance; `led_ticker_telnet.register(api)`.

- [ ] **Step 1: scaffold.** Copy `plugins/calendar/{pyproject.toml,Makefile,.pre-commit-config.yaml,LICENSE,.gitignore}` into `plugins/telnet/`. In `pyproject.toml`: set `name = "led-ticker-telnet"`, `version = "0.1.0"`, description "Telnet (ANSI terminal) rendering backend for led-ticker — watch your sign in a terminal."; `dependencies = ["led-ticker-core>=<phase-A version>"]` (NO aiohttp — stdlib asyncio only); entry point:
```toml
[project.entry-points."led_ticker.plugins"]
telnet = "led_ticker_telnet:register"
```
  Keep the `[project.optional-dependencies] dev` block (pytest/pytest-asyncio/pytest-cov/pre-commit/ruff/pyright) from calendar.
  Copy `plugins/calendar/tests/test_import_purity.py` → `plugins/telnet/tests/test_import_purity.py` and change `SRC = ... / "led_ticker_calendar"` to `"led_ticker_telnet"`.

- [ ] **Step 2: failing test** (`tests/test_telnet_backend.py`):
```python
from led_ticker.backends.conformance import run_backend_conformance
from led_ticker_telnet.backend import TelnetBackend


def test_telnet_backend_passes_conformance():
    run_backend_conformance(lambda: TelnetBackend(width=64, height=32))


def test_swap_returns_a_different_buffer():
    b = TelnetBackend(width=8, height=8)
    b.setup()
    c0 = b.create_canvas()
    c1 = b.swap(c0)
    assert c1 is not c0
```
- [ ] **Step 3: run, expect fail** — `cd plugins/telnet && uv run pytest -q` (import error / no module).
- [ ] **Step 4: implement the skeleton.** `src/led_ticker_telnet/backend.py` (mirror `HeadlessBackend`'s two-buffer swap; NO network yet):
```python
import logging

from led_ticker.plugin import HeadlessCanvas

logger = logging.getLogger(__name__)


class TelnetBackend:
    """Renders frames as ANSI color over a telnet/TCP socket. Output device is a
    terminal; the backend owns its transport (like rgbmatrix owns GPIO)."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self.brightness = 100
        self._buffers = [
            HeadlessCanvas(width, height),
            HeadlessCanvas(width, height),
        ]
        self._back = 0

    def setup(self) -> None:
        # Network added in Task B3.
        pass

    def create_canvas(self) -> HeadlessCanvas:
        return self._buffers[self._back]

    def swap(self, canvas: HeadlessCanvas) -> HeadlessCanvas:
        # `canvas` is the just-drawn back buffer (the "presented" frame).
        # Frame broadcast is added in B3. Flip + return the OTHER buffer so the
        # caller draws into a different object next tick (constraint #8).
        self._back ^= 1
        return self._buffers[self._back]
```
  `src/led_ticker_telnet/__init__.py`:
```python
"""led-ticker-telnet: a telnet/ANSI terminal rendering backend, contributed via
the ``led_ticker.plugins`` entry point. Registers as ``telnet.telnet``; select
with ``[display] backend = "telnet.telnet"``."""

from led_ticker_telnet.backend import TelnetBackend


def register(api):
    api.backend("telnet")(TelnetBackend)
```
- [ ] **Step 5: run, expect pass** — `uv run pytest -q`; `uv run ruff check src tests` + `ruff format`; `uv run pyright src`. **Commit** (`feat: led-ticker-telnet scaffold + conformant TelnetBackend skeleton`).

## Task B2: ANSI half-block frame rendering (pure function)

**Files:** Modify `src/led_ticker_telnet/backend.py` (add `render_ansi`); Test `tests/test_telnet_backend.py`

**Interfaces — Produces:** `render_ansi(canvas) -> str` — a full-frame ANSI string (cursor-home + 24-bit fg/bg half-blocks).

- [ ] **Step 1: failing test:**
```python
def test_render_ansi_encodes_top_and_bottom_pixel_colors():
    from led_ticker_telnet.backend import render_ansi
    c = TelnetBackend(width=1, height=2).create_canvas()
    c.SetPixel(0, 0, 255, 0, 0)   # top → foreground
    c.SetPixel(0, 1, 0, 0, 255)   # bottom → background
    frame = render_ansi(c)
    assert frame.startswith("\x1b[H")            # cursor home
    assert "38;2;255;0;0" in frame               # fg = top pixel
    assert "48;2;0;0;255" in frame               # bg = bottom pixel
    assert "▀" in frame                     # ▀ upper half block
```
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement** (add to `backend.py`):
```python
_ESC = "\x1b"


def render_ansi(canvas) -> str:
    """One pixel row pair per text row: ▀ with fg=top pixel, bg=bottom pixel.
    Reads the backend's own canvas via the public get_pixel (constraint #3 bans
    Canvas GetPixel for the ENGINE, not a backend reading the canvas it made)."""
    out = [f"{_ESC}[H"]  # cursor home — terminal repaints in place each frame
    for y in range(0, canvas.height, 2):
        for x in range(canvas.width):
            tr, tg, tb = canvas.get_pixel(x, y)
            if y + 1 < canvas.height:
                br, bg, bb = canvas.get_pixel(x, y + 1)
            else:
                br, bg, bb = 0, 0, 0
            out.append(
                f"{_ESC}[38;2;{tr};{tg};{tb}m{_ESC}[48;2;{br};{bg};{bb}m▀"
            )
        out.append(f"{_ESC}[0m\r\n")  # reset attrs + CRLF (telnet line ending)
    return "".join(out)
```
- [ ] **Step 4: run, expect pass**; ruff + pyright. **Step 5: commit** (`feat: ANSI half-block frame rendering`).

## Task B3: asyncio TCP server — broadcast, prune, degrade

**Files:** Modify `src/led_ticker_telnet/backend.py`; Test `tests/test_telnet_backend.py`

**Interfaces — Consumes:** `render_ansi`. **Produces:** `TelnetBackend.setup()` starts a TCP server (env-configured); `swap()` broadcasts the rendered frame to connected clients.

- [ ] **Step 1: failing test** (broadcast to a fake writer; no real socket):
```python
import asyncio


def test_swap_broadcasts_frame_to_connected_clients():
    b = TelnetBackend(width=2, height=2)

    class FakeWriter:
        def __init__(self): self.buf = b""
        def write(self, data): self.buf += data
        def is_closing(self): return False

    fw = FakeWriter()
    b._clients = {fw}                  # simulate a connected client
    c = b.create_canvas()
    c.SetPixel(0, 0, 1, 2, 3)
    b.swap(c)
    assert b"\x1b[H" in fw.buf and b"38;2;1;2;3" in fw.buf


def test_setup_without_running_loop_degrades(caplog):
    b = TelnetBackend()
    b.setup()                          # no running loop (sync test) → no crash
    assert b._server is None
```
- [ ] **Step 2: run, expect fail.**
- [ ] **Step 3: implement.** Replace `__init__` server fields + `setup`/`swap` and add the server coroutines:
```python
import asyncio
import os

# in __init__, after self._back = 0:
        self._clients: set = set()
        self._server = None
        self._host = os.environ.get("LED_TICKER_TELNET_HOST", "0.0.0.0")
        self._port = int(os.environ.get("LED_TICKER_TELNET_PORT", "2300"))

    def setup(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "telnet backend: no running event loop at setup(); server not "
                "started (rendering still works, no clients)"
            )
            return
        loop.create_task(self._serve())

    async def _serve(self) -> None:
        try:
            self._server = await asyncio.start_server(
                self._on_client, self._host, self._port
            )
        except OSError as e:  # bind failure must NOT freeze the panel (constraint #1)
            logger.warning("telnet backend: could not bind %s:%s — %s",
                           self._host, self._port, e)
            return
        logger.info("telnet backend ready — connect: telnet <host> %s", self._port)

    async def _on_client(self, reader, writer) -> None:
        self._clients.add(writer)
        writer.write(b"\x1b[2J")  # clear the client's screen on connect
        try:
            await reader.read()   # block until the client disconnects
        finally:
            self._clients.discard(writer)
            try:
                writer.close()
            except Exception:
                pass

    def swap(self, canvas: HeadlessCanvas) -> HeadlessCanvas:
        if self._clients:
            frame = render_ansi(canvas).encode("utf-8", "replace")
            for w in list(self._clients):
                try:
                    if getattr(w, "is_closing", lambda: False)():
                        self._clients.discard(w)
                        continue
                    w.write(frame)   # do NOT await drain — never block swap on a
                                     # slow client; its buffer grows, frames drop
                except Exception:
                    self._clients.discard(w)
        self._back ^= 1
        return self._buffers[self._back]
```
- [ ] **Step 4: run, expect pass**; ruff + pyright. **Step 5: commit** (`feat: asyncio TCP broadcast + bind/loop-failure degradation`).

## Task B4: Wire-up, smoke config, docs (incl. the config finding)

**Files:** `plugins/telnet/README.md`, `plugins/telnet/CLAUDE.md`, `plugins/telnet/config/config.telnet_smoketest.toml`

- [ ] **Step 1:** Create `config/config.telnet_smoketest.toml` — a minimal config with `[display] backend = "telnet.telnet"` (+ a single `message` section) so a maintainer can smoke it.
- [ ] **Step 2:** Write `README.md`: what it is (watch the sign in a terminal), install, `[display] backend = "telnet.telnet"`, `telnet <host> 2300` / `nc <host> 2300`, the `LED_TICKER_TELNET_PORT`/`_HOST` env vars, and a **"Known limitation"** section: *plugin backends cannot take TOML `[display]` config yet — port/host are env-only; a future led-ticker-core `[display.<backend>]` → `from_config` mechanism would close this* (the headline validation finding). Write `CLAUDE.md` (contributor invariants: imports only `led_ticker.plugin`; namespaced as `telnet.telnet`; swap never blocks on a slow client; bind failure degrades).
- [ ] **Step 3:** Run the full plugin gate: `uv run pytest -q` (incl. conformance + import-purity), `uv run ruff check src tests` + `ruff format`, `uv run pyright src`.
- [ ] **Step 4: commit** (`docs: led-ticker-telnet README/CLAUDE + smoke config + config-gap finding`).

**Maintainer deploy-smoke (NOT unit-testable — flag, do not fake):** `[display] backend = "telnet.telnet"` on a machine with `led-ticker-telnet` installed → `telnet localhost 2300`, confirm the sign renders + animates; connect a second client; disconnect one and confirm no crash; confirm bind failure (port in use) logs and the panel still boots.

**End of Phase B → open the plugin PR, pause for merge go-ahead.**

---

## Self-Review

**Spec coverage:** `api.backend()` → A1; `HeadlessCanvas` export → A1; serialization read (`get_pixel`) → A1; load-order tripwire → A2; `isinstance`-leak audit → A3; async-lifecycle + loud-failure + authoring docs → A4; telnet plugin (scaffold/protocol/ANSI/server) → B1–B3; env config + config-gap finding + README/CLAUDE → B4; namespaced `telnet.telnet` → A1+B1; conformance as first external consumer → B1; deploy-smoke → flagged. ✅

**Placeholder scan:** all code steps carry real code; the one investigative task (A3) gives the exact grep + the tripwire + the decision rule (fix vs. lock). The cross-repo editable-core install is an explicit command. No TBDs.

**Type consistency:** `TelnetBackend(width, height)` ctor used identically in B1/B2/B3 tests; `render_ansi(canvas) -> str` defined B2, consumed B3; `_clients` set introduced B3 used by the B3 broadcast test; `api.backend(name)` (A1) consumed by `register` (B1); `_REGISTRY` import aliased `_BACKEND_REGISTRY` (A1) matches the map test.

**Notes for the executor:** (1) Phase A is one PR; Phase B a second, in the plugins monorepo, after A merges/installs. (2) The deploy-smoke is the only non-unit-testable gate — flag it. (3) If A3 finds a real leak, the engine fix must keep the rgbmatrix path byte-identical. (4) Bump core's version in the Phase-A PR so Phase-B can pin it.

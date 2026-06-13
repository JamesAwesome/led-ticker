# Overlay / Busy-Light State in the Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the display's overlay/busy-light state on the web status page, read-only, by publishing an `overlays` key into `status.json` and rendering an Overlays card on the Status tab.

**Architecture:** The display process publishes a static overlay `roster` (captured at registration in `run()`) plus dynamic `busy` state (pulled by the existing heartbeat each beat) into the status snapshot under a new `overlays` key (schema 2→3). The sidecar serves it via the existing `/api/status`; a new card renders it from the poll already running. Zero render-path cost; `busy_http.py`/`frame.py` untouched; `busy_light.py` gains only a read-only `ttl_remaining()` accessor.

**Tech Stack:** stdlib + attrs (display side), aiohttp (existing, sidecar), vanilla JS (page). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-overlay-state-webui-design.md`

**Worktree notes (read first):**
- Work in `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/overlay-state`, branch `feat/overlay-state`. Run `git branch --show-current` and ABORT if it prints `main`.
- Tests: `PYTHONPATH=tests/stubs uv run pytest <files> -q` · Lint: `uv run --extra dev ruff check src/ tests/` · Format: `uv run --extra dev ruff format <files>`.
- Commit with hooks ON: `PATH="$PWD/.venv/bin:$PATH" git commit -m "..."` (the pre-commit ruff pin works on main now; do NOT use `--no-verify`). If the format hook reformats a file, `git add -u` and commit again.
- House style: no gun metaphors; say pitfall/gotcha/sharp edge.
- CAUTION: `app/run.py` carries source-tripwire tests; the heartbeat-spawn move in Task 4 must keep them green (they're listed in that task).

**Pre-verified code facts (do not re-derive):**
- `status_board.py`: `SCHEMA_VERSION = 2` (line 29); `StatusBoard` is `@attrs.define` with fields incl. `swap_count: int = attrs.field(default=0, init=False)` (line 51); `snapshot()` returns a dict literal (lines 60-74); `record_swap()` (line 187) is the pure-setter shape (`if _ACTIVE is not None: _ACTIVE.swap_count += 1`, NO publish); `record_section()` (line 196) is the publish shape (`_ACTIVE.publish(force=True)`) — Task 1's setters mirror `record_swap`, NOT `record_section`. `set_active_board`/`clear_active_board`/`get_active_board` exist (lines 157-168).
- `busy_light.py`: `BusyLight` is `@attrs.define`; `is_busy: bool` is public (line 26); `_busy_until: float | None` is private (line 27); `tick_ttl(self, now=None)` (line 53) already reads `_busy_until` with `time.monotonic() if now is None else now` — the new accessor mirrors this exactly. `import time` already present.
- `config.py`: `BusyLightConfig.source: str = "file"` (line 164).
- `run.py`: `_status_heartbeat(board, tee=None, marker_ttl=None)` (line 105); `_start_busy_light(cfg, led_frame)` returns the `BusyLight` (its return is currently DISCARDED at line 256); plugin overlays registered at `for ns, paint in plugins.overlays:` (line 261); `LoadedPlugins.overlays` is `list[tuple[str, Callable]]`. Current run() order (lines 247-262): `_setup_status_board` → try → `build_frame_from_config` → `_setup_preview` → **heartbeat spawn (253)** → busy start (255-256) → plugin overlays (261-262). The heartbeat spawn must MOVE below busy + plugin registration.
- run.py source tripwires (`tests/test_status_instrumentation.py`): `test_run_spawns_heartbeat` (asserts substring `spawn_tracked(_status_heartbeat` in run() source), `test_setup_runs_before_frame_build` (asserts `_setup_status_board(` precedes `build_frame_from_config(` in source), `test_run_teardown_is_adjacent_to_setup` (asserts the line after the `_setup_status_board(...)` assignment is `try:`). The Task-4 reorder keeps all three.
- Page (`webui/static/index.html`): Status-tab cards are static `<div class="card">` markup (Health 63-67, Plugins 68-71) populated in `poll()` from `st.*`; `lastStatus = st` at line 167; `esc()` helper used throughout; the plugins render at 198-205 is the pattern to mirror.
- Page marker test (`tests/test_webui_app.py:224-237`): a tuple of substrings the served page must contain — extend it.

**File structure:**

| File | Change |
|---|---|
| `src/led_ticker/busy_light.py` | + `ttl_remaining(now=None)` read-only accessor |
| `src/led_ticker/status_board.py` | `overlay_roster`/`busy` fields, snapshot `overlays` key, SCHEMA 3, `set_overlay_roster`/`record_busy` setters |
| `src/led_ticker/app/run.py` | roster capture, bind busy, move heartbeat spawn, heartbeat busy pull params |
| `src/led_ticker/webui/static/index.html` | Overlays card markup + render in `poll()` |
| tests: `test_busy_light.py`, `test_status_board.py`, `test_status_instrumentation.py`, `test_webui_app.py` | extend |

---

### Task 1: `BusyLight.ttl_remaining()` accessor

**Files:**
- Modify: `src/led_ticker/busy_light.py`
- Test: `tests/test_busy_light.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_busy_light.py`):

```python
def test_ttl_remaining_none_when_no_deadline():
    bl = BusyLight(file_path="/x")
    assert bl.ttl_remaining() is None
    bl.set_busy(True)  # no ttl -> stays on, no deadline armed
    assert bl.ttl_remaining() is None


def test_ttl_remaining_positive_while_armed():
    bl = BusyLight(file_path="/x")
    bl.set_busy(True, now=1000.0, ttl=30.0)  # deadline at 1030
    assert bl.ttl_remaining(now=1000.0) == 30.0
    assert bl.ttl_remaining(now=1025.0) == 5.0


def test_ttl_remaining_clamps_to_zero_past_deadline():
    bl = BusyLight(file_path="/x")
    bl.set_busy(True, now=1000.0, ttl=10.0)  # deadline at 1010
    assert bl.ttl_remaining(now=1015.0) == 0.0  # never negative
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_busy_light.py -q`
Expected: FAIL — `AttributeError: 'BusyLight' object has no attribute 'ttl_remaining'`

- [ ] **Step 3: Implement** — add this method to `BusyLight` in `src/led_ticker/busy_light.py`, directly after `tick_ttl` (mirrors its `now` handling):

```python
    def ttl_remaining(self, now: float | None = None) -> float | None:
        """Seconds-from-now until the armed deadline clears the busy state,
        clamped at 0.0; None when no deadline is armed. Read-only — does NOT
        mutate state (unlike tick_ttl). Lets a reader (the web status
        heartbeat) report the remaining time without reaching into the
        private _busy_until, keeping busy_light import-free of the web stack."""
        if self._busy_until is None:
            return None
        t = time.monotonic() if now is None else now
        return max(0.0, self._busy_until - t)
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_busy_light.py -q`
Expected: PASS

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/busy_light.py tests/test_busy_light.py
git add src/led_ticker/busy_light.py tests/test_busy_light.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(busy): read-only ttl_remaining() accessor"
```

---

### Task 2: `status_board` — overlays fields, snapshot, schema bump, setters

**Files:**
- Modify: `src/led_ticker/status_board.py`
- Test: `tests/test_status_board.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_status_board.py`; the file already imports `status_board`, `StatusBoard`, `SCHEMA_VERSION`, `json`, and has the `_board(tmp_path)` helper and the `EXPECTED_TOP_LEVEL_KEYS` set used by `test_schema_tripwire`):

```python
def test_snapshot_has_overlays_with_roster_and_busy(tmp_path):
    board = _board(tmp_path)
    snap = board.snapshot()
    assert "overlays" in snap
    assert snap["overlays"] == {"roster": [], "busy": {"enabled": False}}


def test_set_overlay_roster_stores(tmp_path):
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.set_overlay_roster(
            [{"name": "busy_light", "kind": "core"}, {"name": "acme.clock", "kind": "plugin"}]
        )
        assert board.snapshot()["overlays"]["roster"][1]["name"] == "acme.clock"
    finally:
        status_board.clear_active_board()


def test_record_busy_stores(tmp_path):
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_busy({"enabled": True, "active": True, "source": "http", "ttl_remaining": 12.0})
        assert board.snapshot()["overlays"]["busy"]["active"] is True
    finally:
        status_board.clear_active_board()


def test_overlay_setters_noop_without_active_board(tmp_path):
    status_board.clear_active_board()
    status_board.set_overlay_roster([{"name": "x", "kind": "core"}])  # must not raise
    status_board.record_busy({"enabled": True})  # must not raise


def test_record_busy_does_not_write_file(tmp_path):
    # COST GUARD: record_busy is a pure setter — it must NOT publish/flush.
    # The heartbeat calls board.publish() right after; double-writing would
    # halve the zero-extra-I/O property.
    board = _board(tmp_path)
    status_board.set_active_board(board)
    try:
        status_board.record_busy({"enabled": True, "active": False})
        assert not (tmp_path / "status.json").exists()  # nothing written yet
        board.publish(force=True)
        assert (tmp_path / "status.json").exists()  # the explicit publish writes
    finally:
        status_board.clear_active_board()
```

Then update the existing `test_schema_tripwire` (it asserts `set(snap.keys()) == EXPECTED_TOP_LEVEL_KEYS` and `snap["schema"] == SCHEMA_VERSION == 2`): add `"overlays"` to `EXPECTED_TOP_LEVEL_KEYS` and change the literal `== 2` to `== 3`.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: FAIL — `overlays` missing from snapshot; `set_overlay_roster`/`record_busy` undefined; schema tripwire mismatch.

- [ ] **Step 3a: Bump schema + add fields** in `src/led_ticker/status_board.py`. Change line 29:

```python
SCHEMA_VERSION = 3
```

Add two fields to `StatusBoard` (after the `swap_count` field, before `log_tail`):

```python
    # Overlay roster (static, set once at startup via set_overlay_roster) and
    # busy-light state (dynamic, refreshed each heartbeat beat via record_busy).
    # Both are pure-setter targets — no publish here; the heartbeat's existing
    # per-beat publish serializes them for free.
    overlay_roster: list[dict[str, Any]] = attrs.field(factory=list)
    busy: dict[str, Any] = attrs.field(factory=lambda: {"enabled": False})
```

- [ ] **Step 3b: Add the `overlays` key to `snapshot()`** — insert into the returned dict (e.g. after `"swap_count": self.swap_count,`):

```python
            "overlays": {"roster": self.overlay_roster, "busy": self.busy},
```

- [ ] **Step 3c: Add the two module-level setters** near `record_swap` (mirror its pure-setter shape — NO `publish`):

```python
def set_overlay_roster(roster: list[dict[str, Any]]) -> None:
    """Set the static overlay roster once at startup. Pure setter (no
    publish) — the heartbeat's per-beat publish serializes it."""
    if _ACTIVE is not None:
        _ACTIVE.overlay_roster = roster


def record_busy(state: dict[str, Any]) -> None:
    """Store the current busy-light state. Pure setter (no publish) — like
    record_swap, NOT record_section; the heartbeat publishes right after."""
    if _ACTIVE is not None:
        _ACTIVE.busy = state
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_board.py -q`
Expected: PASS (including the updated `test_schema_tripwire`).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/status_board.py tests/test_status_board.py
git add src/led_ticker/status_board.py tests/test_status_board.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): overlays field in status snapshot (schema 3)"
```

---

### Task 3: heartbeat busy pull (signature + body)

**Files:**
- Modify: `src/led_ticker/app/run.py` (`_status_heartbeat` only — the run() wiring is Task 4)
- Test: `tests/test_status_instrumentation.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_status_instrumentation.py`; it has `StatusBoard`, `status_board`, `LedFrame`, `types`, and async tests already):

```python
async def test_heartbeat_pulls_busy_state(tmp_path):
    import asyncio as _asyncio

    from led_ticker.app.run import _status_heartbeat
    from led_ticker.busy_light import BusyLight

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    busy = BusyLight(file_path="/x")
    busy.set_busy(True, now=__import__("time").monotonic(), ttl=600.0)
    status_board.set_active_board(board)
    task = _asyncio.create_task(
        _status_heartbeat(board, busy=busy, busy_source="http")
    )
    try:
        await _asyncio.sleep(0.15)
        snap = board.snapshot()["overlays"]["busy"]
        assert snap["enabled"] is True
        assert snap["active"] is True
        assert snap["source"] == "http"
        assert snap["ttl_remaining"] is not None and snap["ttl_remaining"] > 0
    finally:
        status_board.clear_active_board()
        await _asyncio.wait_for(task, timeout=2)


async def test_heartbeat_busy_none_leaves_default(tmp_path):
    import asyncio as _asyncio

    from led_ticker.app.run import _status_heartbeat

    board = StatusBoard(path=tmp_path / "status.json", min_interval=0.05)
    status_board.set_active_board(board)
    task = _asyncio.create_task(_status_heartbeat(board, busy=None))
    try:
        await _asyncio.sleep(0.15)
        # busy=None: heartbeat records nothing; the board's default stands.
        assert board.snapshot()["overlays"]["busy"] == {"enabled": False}
    finally:
        status_board.clear_active_board()
        await _asyncio.wait_for(task, timeout=2)
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_instrumentation.py -q -k busy`
Expected: FAIL — `_status_heartbeat()` got an unexpected keyword argument `busy`.

- [ ] **Step 3: Implement** — change `_status_heartbeat`'s signature (line 105-107) and add the busy pull. New signature:

```python
async def _status_heartbeat(
    board: Any,
    tee: Any = None,
    marker_ttl: float | None = None,
    busy: Any = None,
    busy_source: str = "file",
) -> None:
```

Add the busy import alongside the existing module imports inside the function:

```python
    from led_ticker import status_board as _sb  # noqa: PLC0415
    from led_ticker.preview import MARKER_TTL  # noqa: PLC0415
```

(no new import needed for busy — it's passed in). Inside the `while` loop, BEFORE the existing `board.publish()` call, add the busy pull:

```python
        while not board.disabled and _sb.get_active_board() is board:
            if busy is not None:
                try:
                    state = {
                        "enabled": True,
                        "active": busy.is_busy,
                        "source": busy_source,
                        "ttl_remaining": busy.ttl_remaining(),
                    }
                except Exception:
                    state = {"enabled": True, "active": getattr(busy, "is_busy", False), "source": busy_source}
                    logging.warning("busy state read failed; publishing without ttl")
                _sb.record_busy(state)
            board.publish()
            ...  # existing marker/tee block unchanged
```

(Keep the rest of the loop body — the marker/`tee.set_watched` block and `await asyncio.sleep` — exactly as-is. `logging` is already imported in run.py.)

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_instrumentation.py -q`
Expected: PASS (the new busy tests + all existing heartbeat/lifecycle tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/app/run.py tests/test_status_instrumentation.py
git add src/led_ticker/app/run.py tests/test_status_instrumentation.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): heartbeat pulls busy state into the snapshot"
```

---

### Task 4: run() wiring — bind busy, capture roster, move heartbeat spawn

**Files:**
- Modify: `src/led_ticker/app/run.py` (the `run()` setup block, lines ~247-262)
- Test: `tests/test_status_instrumentation.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_status_instrumentation.py`):

```python
def test_run_spawns_heartbeat_after_busy_setup():
    # The heartbeat needs the busy object, which is created by
    # _start_busy_light. Source-order tripwire: the heartbeat spawn must come
    # AFTER the busy-light setup call, or busy doesn't exist yet at the spawn.
    import inspect

    from led_ticker.app.run import run

    src = inspect.getsource(run)
    busy_at = src.index("_start_busy_light(")
    spawn_at = src.index("spawn_tracked(_status_heartbeat")
    assert busy_at < spawn_at, (
        "heartbeat spawn must follow _start_busy_light so the busy object "
        "exists and can be threaded into the heartbeat."
    )


def test_run_builds_overlay_roster_in_source():
    # The roster must be assembled in run() and handed to set_overlay_roster.
    import inspect

    from led_ticker.app.run import run

    src = inspect.getsource(run)
    assert "set_overlay_roster(" in src
    assert '"kind": "core"' in src  # busy_light entry synthesized in run()
    assert '"kind": "plugin"' in src  # plugin overlay entries
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_instrumentation.py -q -k "roster or after_busy"`
Expected: FAIL — current source spawns the heartbeat before busy setup; no `set_overlay_roster` in run().

- [ ] **Step 3: Rewrite the run() setup block.** Replace the current block (lines ~250-262, from `preview_tee = _setup_preview(...)` through the plugin-overlay `for` loop) with this order — `_setup_preview` stays put, then busy + plugin overlays register, then the roster is built and the heartbeat spawned:

```python
        preview_tee = _setup_preview(config, led_frame)

        # Busy light first so the heartbeat (spawned below) can read its state.
        busy = None
        if config.busy_light.enabled:
            busy = await _start_busy_light(config.busy_light, led_frame)

        # Plugin overlays composite over every render path via LedFrame.swap(),
        # same as the busy-light. Each is exception-wrapped so a raising plugin
        # overlay disables itself (logged once) rather than freezing the panel.
        for ns, paint in plugins.overlays:
            led_frame.overlay_hooks.append(_guarded_overlay(ns, paint))

        # Publish the static overlay roster once: names come from the
        # registration sites here (a raw overlay_hooks callable has no clean
        # name). busy.enabled and the busy_light roster entry both derive from
        # the one config gate, so they can't disagree.
        if _status_handle is not None:
            from led_ticker.status_board import set_overlay_roster  # noqa: PLC0415

            roster: list[dict[str, str]] = []
            if busy is not None:
                roster.append({"name": "busy_light", "kind": "core"})
            roster.extend({"name": ns, "kind": "plugin"} for ns, _ in plugins.overlays)
            set_overlay_roster(roster)

            spawn_tracked(
                _status_heartbeat(
                    _status_handle[0],
                    tee=preview_tee,
                    busy=busy,
                    busy_source=config.busy_light.source,
                )
            )
```

Delete the OLD heartbeat spawn (the `if _status_handle is not None: spawn_tracked(_status_heartbeat(_status_handle[0], tee=preview_tee))` at lines ~252-253) — it's replaced by the spawn above. Confirm there is now exactly ONE `spawn_tracked(_status_heartbeat` in run().

- [ ] **Step 4: Run to verify pass + the existing tripwires**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_status_instrumentation.py tests/test_app.py -q`
Expected: PASS, including `test_run_spawns_heartbeat`, `test_setup_runs_before_frame_build`, `test_run_teardown_is_adjacent_to_setup` (the reorder keeps setup→try adjacency and the setup-before-frame order; it only moves the heartbeat spawn and adds the roster build).

- [ ] **Step 5: Lint + commit**

```bash
uv run --extra dev ruff check src/led_ticker/app/run.py tests/test_status_instrumentation.py
git add src/led_ticker/app/run.py tests/test_status_instrumentation.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): capture overlay roster + thread busy into the heartbeat"
```

---

### Task 5: the Overlays card (page)

**Files:**
- Modify: `src/led_ticker/webui/static/index.html`
- Test: `tests/test_webui_app.py`

- [ ] **Step 1: Extend the page-marker test** in `tests/test_webui_app.py`. In the `for marker in (...)` tuple (around line 224-237), add two entries:

```python
            "overlays-card",
            "no overlays installed",
```

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -q -k root_serves`
Expected: FAIL — markers absent from the served page.

- [ ] **Step 2: Add the card markup** — in the Status tab section, immediately after the Plugins card (`</div>` closing the `<div class="card"><strong>Plugins</strong>...` block at line ~71), insert:

```html
    <div class="card" id="overlays-card">
      <strong>Overlays</strong>
      <div id="busy-state" class="muted">—</div>
      <table id="overlay-roster"><tbody></tbody></table>
    </div>
```

- [ ] **Step 3: Add the render logic** in `poll()`, right after the plugins render block (after the `$("logtail").textContent = ...` line ~207, still inside the `if (body.status)` body where `st` is in scope). Mirror the existing card render style (esc on dynamic strings, number-coerce ttl):

```javascript
    const ov = st.overlays || {roster: [], busy: {enabled: false}};
    const b = ov.busy || {enabled: false};
    if (!b.enabled) {
      $("busy-state").textContent = "busy light not configured";
    } else {
      const dot = b.active ? "● busy" : "○ free";
      let line = `${dot} · ${esc(b.source || "")}`;
      if (b.ttl_remaining != null) line += ` · clears in ${Math.round(+b.ttl_remaining)}s`;
      $("busy-state").textContent = line;
    }
    $("overlay-roster").tBodies[0].innerHTML = (ov.roster || [])
      .map((o) => `<tr><td>${esc(o.name)}</td><td class="muted">${esc(o.kind)}</td></tr>`)
      .join("") || '<tr><td class="muted">no overlays installed</td></tr>';
```

Note: `$("busy-state").textContent = line` uses textContent, but `line` is built with `esc(b.source)` — that's harmless (textContent doesn't interpret HTML; the esc is belt-and-suspenders and keeps the pattern uniform). The roster uses `innerHTML`, so `esc()` on `name`/`kind` is load-bearing there.

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_webui_app.py -q`
Expected: PASS (the marker test + all existing webui tests — the new card rides the already-tested `/api/status`).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/webui/static/index.html tests/test_webui_app.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(web): Overlays card on the status tab"
```

---

### Task 6: docs, full gates, smoke, PR

**Files:**
- Modify: `docs/site/src/content/docs/concepts/web-status-ui.mdx`

- [ ] **Step 1: Docs.** Read `docs/DOCS-STYLE.md` first. Add a short "Overlays" subsection under the Status-tab area of `web-status-ui.mdx`: what the card shows (busy light on/off + source + ttl, and the roster of overlays compositing onto the panel incl. plugin overlays), that it's read-only (the busy light's own `[busy_light] source="http"` `/busy` route stays the control surface), and that overlay state needs `[web]` configured. Note the `[busy_light]`/`[web]` default port collision in passing if the page has a relevant troubleshooting spot (both default to 8080 — give one a non-default port). Run `make docs-lint`; if prettier complains, `cd docs/site && pnpm prettier --write <file>`.

- [ ] **Step 2: Full gates** — run and report exact numbers:

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/
uv run --extra dev ruff format --check src/ tests/ 2>&1 | tail -1
PYTHONPATH=tests/stubs uv run pyright src/ 2>&1 | grep -E "^[0-9]+ error"
make docs-lint 2>&1 | tail -3
```
All must pass.

- [ ] **Step 3: Smoke test** (throwaway script under /tmp, deleted after): build a `StatusBoard` into a temp dir + `set_active_board`; build a real `BusyLight`, `set_busy(True, ttl=...)`; run `_status_heartbeat(board, busy=busy, busy_source="http")` for ~0.2s (or call `record_busy` + `publish` directly); `set_overlay_roster([...])`; then `serve_webui` against the dir, fetch `/api/status`, assert the JSON carries `overlays.busy.active == true`, `overlays.busy.ttl_remaining` a positive number, and the roster entries. Then fetch `/` and confirm the page HTML contains `overlays-card`. Paste output in the report.

- [ ] **Step 4: Push + PR (do NOT merge — the user confirms merges).** PR body covers: the read-only design (no control path; `/busy` stays the control surface), the zero-render-cost + heartbeat-piggyback posture (record_busy is a pure no-publish setter), the schema 2→3 bump (with the version-skew envelope note), the `ttl_remaining()` accessor keeping busy decoupled from the web stack, and a hardware validation step for longboi (flip the busy file/HTTP and watch the Overlays card update within ~2-3s; confirm the busy dot also shows in the live preview).

```bash
git push -u origin feat/overlay-state
gh pr create --title "feat: surface overlay/busy-light state in the web UI (read-only)" --body "..."
```

---

## Self-review notes (done at plan-writing time)

- **Spec coverage:** data model `overlays` shape (T2), roster static capture (T4), busy dynamic pull (T3), `ttl_remaining` relative-remainder accessor (T1), schema 2→3 + tripwire both-changes (T2), the cost-critical no-publish setter + its test (T2), heartbeat spawn reorder + bind-busy (T4), `busy_source` threading (T3), `busy=None` leaves default (T3), Overlays card incl. esc/ttl-round (T5), version-skew framing + no unreachable test (honored — no v2-card test written), docs + port-collision note (T6). Every spec section maps to a task.
- **Type/name consistency:** `set_overlay_roster(list[dict])`, `record_busy(dict)`, `ttl_remaining(now=None)`, heartbeat `(board, tee, marker_ttl, busy, busy_source)`, snapshot `overlays.{roster,busy}`, roster entries `{"name","kind"}` with kinds `core`/`plugin`, page ids `overlays-card`/`busy-state`/`overlay-roster` — used identically across tasks.
- **No placeholders:** every step has concrete code/commands. The two source-order tripwires (T4) pin the reorder the spec flagged as the main pitfall.
- **Ordering:** T1→T2 (accessor + board) are independent of each other but both precede T3 (heartbeat uses the accessor + record_busy) and T4 (run wiring uses set_overlay_roster + busy). T5 (page) reads the shape T2/T3/T4 publish. T6 last.

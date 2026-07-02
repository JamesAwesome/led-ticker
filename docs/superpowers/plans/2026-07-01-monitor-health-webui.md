# Monitor-health web UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show, at a glance in the web UI, whether each live-data monitor (polled `[[source]]` value-tokens + data widgets) is running / erroring / stale.

**Architecture:** Publish per-monitor health from the ONE shared poll loop (`run_monitor_loop`) into `status.json` via the status board — a `monitors` dict (`name → {kind, interval, last_ok, error}`) with a roster registered on loop entry, updated on success, error-recorded on failure. The web UI reads it and computes each state client-side. **The load-bearing work is the publisher; the panel is the last ~30%.**

**Tech Stack:** Python 3.14 (PEP 649), attrs, asyncio, the status board (best-effort JSON publisher), a static hand-rendered `index.html`, Astro/Starlight docs.

**Source of truth:** `docs/superpowers/specs/2026-07-01-monitor-health-webui-design.md`.

## Global Constraints

- **Never block or raise into the render loop.** Every board recorder is `if _ACTIVE is None: return` + internally `try/except` guarded (the pattern already used by `record_widget_visit` etc.); `record_monitor_error` runs *inside* `run_monitor_loop`'s `except`, so it must never escape. Nothing here touches the swap/draw path.
- **No per-plugin changes** — all wiring is in core (`run_monitor_loop` + `status_board` + `reload`).
- **No circular import** — `widget.py` must NOT import `sources` (sources imports widget). Source-vs-widget is duck-typed.
- **busy_light is EXCLUDED** — it rides `run_monitor_loop` but has no `.draw`/`.polled`; register only a source (`getattr(obj,"polled",False)`) or a drawable widget (`hasattr(obj,"draw")`).
- **`snapshot()` is synchronous** (no `await`); schema **8→9** + the webui `st.monitor_updates`→`st.monitors` migration + the 4 test assertions + the tripwire ALL land together (Tasks 2 + 5 must not leave `main` with a blank table — they're in one branch/PR).
- **Web UI is read-only** (no new endpoint); **docs ship with the feature**.
- Core gates (NO `PYTHONPATH=tests/stubs` prefix): `uv run --extra dev pytest`, `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev pyright src/`. Docs gates: `make docs-build` + `make docs-lint`. Worktree + PR; never `main`. Use `git -c core.hooksPath=/dev/null` if the pre-commit hook misbehaves.

## Non-Goals

Manual retry/restart buttons; per-monitor history/graphs; alerting/notifications; a dedicated Monitors tab; an error taxonomy beyond faithfully showing the message.

## File Structure

- **Modify** `src/led_ticker/status_board.py` — `monitors` dict + `_monitor_name` + `register_monitor`/`record_monitor_error`/`clear_monitors` + extend `record_monitor_update`; `snapshot()` serializes `monitors`, drop top-level `monitor_updates`; bump `SCHEMA_VERSION`.
- **Modify** `src/led_ticker/widget.py` — `run_monitor_loop` registers on entry, records error+retry on failure, uses `_monitor_name`.
- **Modify** `src/led_ticker/reload.py` — `clear_monitors()` in `_apply_reload`.
- **Modify** `src/led_ticker/webui/static/index.html` — upgrade the existing `#monitors` table + add the roll-up badge + state-compute + liveness gate.
- **Modify tests** `tests/test_status_board.py`, `tests/test_status_instrumentation.py`.
- **Modify docs** `docs/site/src/content/docs/concepts/web-status-ui.mdx` + a cross-link in `concepts/value-tokens.mdx`.

---

## Task 1: status_board — the `monitors` dict + setters

**Files:** Modify `src/led_ticker/status_board.py`; Test `tests/test_status_board.py`.

**Interfaces — Produces:**
- `StatusBoard.monitors: dict[str, dict]` (attrs field, factory=dict). Entry: `{"kind", "interval", "last_ok", "error"}`.
- `_monitor_name(obj) -> str` (module-level): `getattr(obj,"id",None) or getattr(obj,"name",None) or type(obj).__name__`.
- `register_monitor(name, kind, interval) -> str` (module-level, returns the final possibly-suffixed name).
- `record_monitor_error(name, message, consecutive, retry_in) -> None`.
- `clear_monitors() -> None`.
- `record_monitor_update(name)` extended to set `monitors[name]["last_ok"]` + clear `["error"]` (keeps the existing internal `monitor_updates` dict too).

- [ ] **Step 1: Write the failing tests** in `tests/test_status_board.py`:

```python
def test_monitor_name_prefers_id_then_name_then_class():
    from led_ticker.status_board import _monitor_name
    class _Src:  # a source: has .id
        id = "weather.nyc"
    class _Wid:  # a widget with a .name
        name = "RSS BBC"
    class _Bare:
        pass
    assert _monitor_name(_Src()) == "weather.nyc"
    assert _monitor_name(_Wid()) == "RSS BBC"
    assert _monitor_name(_Bare()) == "_Bare"


def test_register_record_update_and_error(tmp_path):
    import led_ticker.status_board as sb
    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)  # if no setter exists, assign sb._ACTIVE = board (see impl note)
    try:
        sb.register_monitor("weather.nyc", "source", 1800)
        assert board.monitors["weather.nyc"] == {
            "kind": "source", "interval": 1800, "last_ok": None, "error": None,
        }
        sb.record_monitor_error("weather.nyc", "401 Unauthorized", 3, 240.0)
        assert board.monitors["weather.nyc"]["error"] == {
            "message": "401 Unauthorized", "consecutive": 3,
            "at": board.monitors["weather.nyc"]["error"]["at"], "retry_in": 240.0,
        }
        sb.record_monitor_update("weather.nyc")
        assert board.monitors["weather.nyc"]["last_ok"] is not None
        assert board.monitors["weather.nyc"]["error"] is None  # cleared on success
    finally:
        sb.set_active_board(None)


def test_register_monitor_name_collision_suffixes(tmp_path):
    import led_ticker.status_board as sb
    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)
    try:
        n1 = sb.register_monitor("WeatherCurrentMonitor", "widget", 10800)
        n2 = sb.register_monitor("WeatherCurrentMonitor", "widget", 10800)
        assert n1 == "WeatherCurrentMonitor"
        assert n2 == "WeatherCurrentMonitor#2"
        assert set(board.monitors) == {"WeatherCurrentMonitor", "WeatherCurrentMonitor#2"}
    finally:
        sb.set_active_board(None)


def test_clear_monitors(tmp_path):
    import led_ticker.status_board as sb
    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)
    try:
        sb.register_monitor("a", "source", 60)
        sb.register_monitor("b", "widget", 60)
        sb.clear_monitors()
        assert board.monitors == {}
    finally:
        sb.set_active_board(None)
```

**Impl note on the active-board setter:** check how tests set `_ACTIVE` today (search `_ACTIVE`/`set_active`/`get_active_board`). If there's a `set_active_board`, use it; if tests assign `sb._ACTIVE = board` directly, mirror that in these tests instead of `set_active_board`. Do not invent a setter that doesn't exist — match the existing test convention.

- [ ] **Step 2: Run → FAIL** — `uv run --extra dev pytest tests/test_status_board.py -k "monitor_name or register_record or collision or clear_monitors" -v`.

- [ ] **Step 3: Implement** in `status_board.py`:

Add the field to `StatusBoard` (next to `monitor_updates`):
```python
    # name -> {kind, interval, last_ok, error}. Registered on poll-loop entry,
    # updated on success, error-recorded on failure; cleared on reload.
    monitors: dict[str, dict] = attrs.field(factory=dict)
```

Add module-level helpers (near `record_monitor_update`), following the existing guarded pattern:
```python
def _monitor_name(obj: Any) -> str:
    """Stable monitor key: a source's .id, else a widget's .name, else classname.
    (Fixes the collision where two polled sources both keyed as their classname.)"""
    return getattr(obj, "id", None) or getattr(obj, "name", None) or type(obj).__name__


def register_monitor(name: str, kind: str, interval: float) -> str:
    """Add/refresh a monitor roster entry (preserving last_ok/error on re-register).
    On a name collision (two same-type widgets with no id/name) append #N so each
    gets a distinct row. Returns the final (possibly suffixed) name. Never raises."""
    if _ACTIVE is None:
        return name
    try:
        m = _ACTIVE.monitors
        if name in m and (m[name].get("kind"), m[name].get("interval")) != (kind, interval):
            # same key already taken by a DIFFERENT monitor -> suffix
            n, final = 2, f"{name}#2"
            while final in m:
                n += 1
                final = f"{name}#{n}"
            name = final
        entry = m.get(name) or {"kind": kind, "interval": interval, "last_ok": None, "error": None}
        entry["kind"], entry["interval"] = kind, interval
        m[name] = entry
        _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        pass
    return name


def record_monitor_error(name: str, message: str, consecutive: int, retry_in: float) -> None:
    if _ACTIVE is None:
        return
    try:
        entry = _ACTIVE.monitors.setdefault(
            name, {"kind": "widget", "interval": 0.0, "last_ok": None, "error": None}
        )
        entry["error"] = {
            "message": message, "consecutive": consecutive,
            "at": time.time(), "retry_in": retry_in,
        }
        _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        pass


def clear_monitors() -> None:
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.monitors.clear()
        _ACTIVE.publish()
    except Exception:  # noqa: BLE001 - instrumentation must never reach the engine
        pass
```

Extend `record_monitor_update` to also touch `monitors` (keep the existing `monitor_updates[name] = time.time()`):
```python
def record_monitor_update(name: str) -> None:
    if _ACTIVE is not None:
        now = time.time()
        _ACTIVE.monitor_updates[name] = now
        entry = _ACTIVE.monitors.get(name)
        if entry is not None:
            entry["last_ok"] = now
            entry["error"] = None
        _ACTIVE.publish()
```

**Collision-suffix subtlety:** the suffix fires only when the *same key* is re-registered with a DIFFERENT `(kind, interval)` — i.e. a genuinely different monitor. A plain re-register of the same monitor (reload/respawn) refreshes in place. (Two identical same-type widgets with identical interval will share a row — acceptable and documented; the common case, distinct sources by `.id`, never collides.)

- [ ] **Step 4: Run → PASS.** Gates. Commit: `git commit -am "feat(status): monitors roster + register/error/clear + _monitor_name"`.

---

## Task 2: snapshot schema 8→9 + drop top-level `monitor_updates`

**Files:** Modify `src/led_ticker/status_board.py`; Test `tests/test_status_board.py` + `tests/test_status_instrumentation.py`.

**Interfaces — Consumes:** Task 1's `monitors` dict. **Produces:** `snapshot()["monitors"]` (list of entries incl. `name`); no top-level `monitor_updates`; `SCHEMA_VERSION = 9`.

- [ ] **Step 1: Update the tripwire + assertions (these are the failing tests).**
  - In `tests/test_status_board.py`: in `EXPECTED_TOP_LEVEL_KEYS` replace `"monitor_updates"` with `"monitors"`; change `assert snap["schema"] == SCHEMA_VERSION == 8` → `== 9`; migrate line ~151 `assert "RSS BBC" in board.monitor_updates` → assert against `board.monitors` (e.g. `assert "RSS BBC" in board.monitors`).
  - In `tests/test_status_instrumentation.py`: migrate `assert "RSS BBC" in board.monitor_updates` (~36) and `assert "Nameless" in board.monitor_updates` (~59) → `board.monitors`. (Task 3 makes those fakes register; if run before Task 3 these two will fail — that's expected ordering, they pass after Task 3. To keep Task 2 self-contained, ALSO assert the snapshot shape here.)
  - Add a snapshot-shape test in `tests/test_status_board.py`:
```python
def test_snapshot_serializes_monitors_not_monitor_updates(tmp_path):
    import led_ticker.status_board as sb
    board = sb.StatusBoard(path=tmp_path / "s.json")
    sb.set_active_board(board)
    try:
        sb.register_monitor("weather.nyc", "source", 1800)
        sb.record_monitor_update("weather.nyc")
        snap = board.snapshot()
        assert "monitor_updates" not in snap
        entries = {m["name"]: m for m in snap["monitors"]}
        assert entries["weather.nyc"]["kind"] == "source"
        assert entries["weather.nyc"]["interval"] == 1800
        assert entries["weather.nyc"]["last_ok"] is not None
        assert entries["weather.nyc"]["error"] is None
    finally:
        sb.set_active_board(None)
```

- [ ] **Step 2: Run → FAIL** — `uv run --extra dev pytest tests/test_status_board.py -k "schema or serializes_monitors" -v`.

- [ ] **Step 3: Implement** in `status_board.py`:
  - `SCHEMA_VERSION = 9`.
  - In `snapshot()`: remove the `"monitor_updates": self.monitor_updates,` line; add (synchronous list comprehension — no await):
```python
            "monitors": [
                {"name": name, **entry} for name, entry in self.monitors.items()
            ],
```

- [ ] **Step 4: Run → PASS** for `tests/test_status_board.py` (the instrumentation ones flip green after Task 3). Gates. Commit: `git commit -am "feat(status): serialize monitors[] (schema 8->9); drop top-level monitor_updates"`.

---

## Task 3: `run_monitor_loop` wiring (register / update / error)

**Files:** Modify `src/led_ticker/widget.py`; Test `tests/test_status_instrumentation.py`.

**Interfaces — Consumes:** `register_monitor`, `record_monitor_update`, `record_monitor_error`, `_monitor_name` (Task 1). **Produces:** every source/widget appears in `board.monitors`; errors carry `retry_in`; busy_light is excluded.

- [ ] **Step 1: Write the failing tests** in `tests/test_status_instrumentation.py`. First, **the existing fakes need `.draw`** so they duck-type as widgets (the new allow-list skips bare `.update()`-only objects). Update the fake monitor(s) used by `test_run_monitor_loop_records_update` / `_falls_back_to_class_name` to include a `draw` attribute (e.g. `def draw(self, *a, **k): ...` or `draw = None` is NOT enough — use a real method or `draw = lambda *a, **k: None`). Then add:

```python
async def test_register_on_entry_and_error_with_retry(tmp_path):
    import led_ticker.status_board as sb
    board = sb.StatusBoard(path=tmp_path / "s.json"); sb.set_active_board(board)

    class _FailingWidget:
        name = "flaky"
        def draw(self, *a, **k): ...
        async def update(self): raise ValueError("boom")

    try:
        task = asyncio.create_task(
            run_monitor_loop(_FailingWidget(), 0.01, splay=False, immediate=True)
        )
        for _ in range(30):
            await asyncio.sleep(0)
            if board.monitors.get("flaky", {}).get("error"):
                break
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        m = board.monitors["flaky"]
        assert m["kind"] == "widget"
        err = m["error"]
        assert err and "boom" in err["message"] and err["consecutive"] >= 1
        assert err["retry_in"] > 0            # the backoff hint
    finally:
        sb.set_active_board(None)


async def test_busy_light_like_not_registered(tmp_path):
    import led_ticker.status_board as sb
    board = sb.StatusBoard(path=tmp_path / "s.json"); sb.set_active_board(board)

    class _BusyLike:  # no .draw, no .polled -> not a monitor
        name = "busy"
        async def update(self): ...

    try:
        task = asyncio.create_task(run_monitor_loop(_BusyLike(), 0.01, splay=False, immediate=True))
        for _ in range(10):
            await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert "busy" not in board.monitors
    finally:
        sb.set_active_board(None)


async def test_status_error_never_escapes_loop(tmp_path, monkeypatch):
    import led_ticker.status_board as sb
    board = sb.StatusBoard(path=tmp_path / "s.json"); sb.set_active_board(board)

    def _boom(*a, **k): raise RuntimeError("board down")
    monkeypatch.setattr(sb, "record_monitor_error", _boom)  # if this reached the loop unwrapped it would kill it

    class _Flaky:
        name = "x"
        def draw(self, *a, **k): ...
        async def update(self): raise ValueError("nope")
    try:
        task = asyncio.create_task(run_monitor_loop(_Flaky(), 0.01, splay=False, immediate=True))
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()  # loop survived a raising recorder
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        sb.set_active_board(None)
```

(Note: `record_monitor_error` is internally guarded, so monkeypatching it to raise tests the CALL SITE's own guard. If the call site relies solely on the recorder's internal guard, wrap the call site too — see Step 3. Match the project's async-test convention; `asyncio_mode = auto` so plain `async def` works.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** in `widget.py` `run_monitor_loop` (it already does `from led_ticker import status_board` — no new import; do NOT import `sources`):

Register as the FIRST statements (before the `splay` mutation / first `await`):
```python
    # Register in the monitor roster (best-effort). Sources duck-type via .polled;
    # data widgets via .draw. Anything that is NEITHER (e.g. the busy-light overlay)
    # is not a data monitor and is skipped. No import of `sources` (circular).
    _mon_name = status_board._monitor_name(widget)
    if getattr(widget, "polled", False):
        _mon_name = status_board.register_monitor(_mon_name, "source", interval)
    elif hasattr(widget, "draw"):
        _mon_name = status_board.register_monitor(_mon_name, "widget", interval)
    else:
        _mon_name = None  # not a monitor (busy_light etc.) — don't record
```

Success branch — use `_mon_name` (replaces the inline `getattr(...)`):
```python
            await widget.update()
            consecutive_errors = 0
            if _mon_name is not None:
                status_board.record_monitor_update(_mon_name)
```

Error branch — record with the retry hint (compute the next backoff, same formula as the top):
```python
        except Exception as exc:
            consecutive_errors += 1
            if _mon_name is not None:
                retry_in = min(_MAX_BACKOFF, _MIN_BACKOFF * (2 ** (consecutive_errors - 1)))
                try:
                    status_board.record_monitor_error(
                        _mon_name, str(exc)[:200], consecutive_errors, retry_in
                    )
                except Exception:  # noqa: BLE001 - instrumentation must never reach the loop
                    pass
            logger.exception(
                "Error updating %s (attempt %d), will back off",
                type(widget).__name__,
                consecutive_errors,
            )
```

- [ ] **Step 4: Run → PASS** — the new tests + the migrated `test_run_monitor_loop_records_update`/`_falls_back_to_class_name` (now that the fakes have `.draw`). Full `tests/test_status_instrumentation.py` + `tests/test_status_board.py`. Gates. Commit.

---

## Task 4: reload prune

**Files:** Modify `src/led_ticker/reload.py`; Test the reload test file.

**Interfaces — Consumes:** `clear_monitors` (Task 1).

- [ ] **Step 1: Write the failing test** (in the reload test file — mirror how it drives `_apply_reload`, or a focused test): register two monitors on the active board, run the reload path (or call the same seam), assert `board.monitors` was cleared (so respawned loops rebuild it). If a full `_apply_reload` harness is heavy, assert at minimum that `_apply_reload` calls `status_board.clear_monitors()` — e.g. spy/patch `clear_monitors` and assert it was called alongside `clear_disabled_widgets`.

```python
def test_apply_reload_clears_monitors(monkeypatch):
    import led_ticker.status_board as sb
    called = {"monitors": False}
    monkeypatch.setattr(sb, "clear_monitors", lambda: called.__setitem__("monitors", True))
    # ... drive _apply_reload with the existing reload-test harness (reuse its fixtures) ...
    assert called["monitors"]
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in `reload.py` `_apply_reload`, next to the existing `status_board.clear_disabled_widgets()` (line ~158):
```python
    status_board.clear_disabled_widgets()
    status_board.clear_monitors()  # respawned source/widget loops re-register
```

- [ ] **Step 4: Run → PASS.** Full suite (reload is load-bearing). Gates. Commit.

---

## Task 5: web UI — Monitors panel + badge + state compute + liveness gate

**Files:** Modify `src/led_ticker/webui/static/index.html`.

**Context:** the page ALREADY has `<table id="monitors">` on the Status tab (line ~126) rendered from `st.monitor_updates` (line ~493, "no async monitors" empty state), and an existing sign-liveness signal (`body.state`, `stallPolls`, `st.published_at`, `st.swap_count` at lines ~471–482). This task UPGRADES that table + adds the badge, reusing the liveness signal.

- [ ] **Step 1: Add a state-compute pure function** near the other helpers:
```javascript
// Monitor state from a status.json monitors[] entry. Client-side so relative
// times stay live between publishes. Rules (spec): error wins over stale;
// backoff (has error) is "error", never "stale"; stale = no error AND
// now - last_ok > interval + splay grace; waiting = never succeeded, neutral.
const SPLAY_GRACE = 60; // seconds — covers run_monitor_loop's up-to-60s splay
function monitorState(m, nowSec) {
  if (m.error) return "error";
  if (m.last_ok == null) return "waiting";
  if (nowSec - m.last_ok > (m.interval || 0) + (m.interval || 0) + SPLAY_GRACE) return "stale";
  return "ok";
}
```
(Threshold = `interval + interval + SPLAY_GRACE` = ~2× interval + splay, per the spec's "interval + grace, grace ≈ interval + 60s".)

- [ ] **Step 2: Migrate the render** at line ~493. Replace the `st.monitor_updates` render with a `st.monitors` render:
  - Compute `now = Date.now()/1000`. For each `m` of `st.monitors || []`, `s = monitorState(m, now)`.
  - **Sign-liveness gate:** if the snapshot itself is stale (reuse the existing `body.state !== "ok"` / stall signal that already drives the "live/stale" indicator), render the rows greyed and show a "sign not reporting" note instead of asserting per-monitor health — a frozen file must not read all-green.
  - Row: a colored dot (green ok / amber stale / red error / grey waiting), `m.name`, a `src`/`widget` tag from `m.kind`, the state word, `updated ${fmtAgo(m.last_ok)}` (or "—" when waiting), `m.interval`, and when `m.error`: `${esc(m.error.message)} ×${m.error.consecutive}${m.error.retry_in ? " · retrying in " + fmtDur(m.error.retry_in) : ""}`.
  - **Sort worst-first:** error > stale > waiting > ok, then by name.
  - **Empty/absent:** `(st.monitors && st.monitors.length) ? rows : '<tr><td class="muted">No live-data monitors configured</td></tr>'`. If `st.monitors` is `undefined` (older schema) → same muted empty row (graceful).
  - **Badge:** compute counts by state; render near the top of the Status tab (e.g. beside the existing live/stale indicator) as `N ok · N stale · N error` with the badge color = worst present (error→red, else stale→amber, else green; waiting doesn't drive color). Reuse existing CSS dot/pill classes if present; else add minimal styles consistent with the page.
  - Reuse the existing `esc`, `fmtAgo` helpers; add a small `fmtDur(sec)` ("~4m") if not present.

- [ ] **Step 3: Verify** — the webui has no JS unit harness, so validate against a crafted status.json:
  - `uv run --extra dev pytest tests/test_status_board.py tests/test_status_instrumentation.py -q` (the data contract the JS consumes is Python-tested in Tasks 1–3).
  - Load the page against a hand-written `status.json` containing an ok source, an erroring source (with `error.retry_in`), a stale widget, and a waiting one; confirm dots/badge/sort/empty-state render and relative times tick. (Describe the fixture in the commit; if a webui test file like `tests/test_webui_*.py` exists that serves the static page, add a smoke assertion that `index.html` references `st.monitors` and not `st.monitor_updates`.)

- [ ] **Step 4: Commit** — `git commit -am "feat(webui): monitors health panel + roll-up badge (state/retry/liveness gate)"`.

---

## Task 6: docs

**Files:** Modify `docs/site/src/content/docs/concepts/web-status-ui.mdx`; `docs/site/src/content/docs/concepts/value-tokens.mdx`.

- [ ] **Step 1:** Add a **"Monitors"** section to `web-status-ui.mdx` (DOCS-STYLE, no "footgun", no release-history framing): what the panel shows and where (the Status tab + the roll-up badge); the states — **ok** (updated within its interval), **error** (shows the message + count + "retrying in …"), **stale** (no update well past the interval — a wedged fetch), **waiting** (before the first fetch); that it covers **both** `[[source]]` value-token sources and data widgets automatically (nothing to enable); and the **"sign not reporting"** behavior when the sign itself stops publishing. Add it to the page's `RelatedPages`/cross-links.

- [ ] **Step 2:** In `concepts/value-tokens.mdx`, in the "Live (polled) sources" section, add a one-line cross-link: if a `:weather.nyc:` token isn't updating, the web UI's **Monitors** panel (link) shows whether the source is erroring or stale.

- [ ] **Step 3:** `make docs-build` && `make docs-lint` clean. The docs-config-options drift gate stays green (no new config fields — the panel is automatic).

- [ ] **Step 4: Commit.**

---

## Self-Review notes (for the executor)

- **Spec coverage:** monitors dict + setters→T1; snapshot/schema/migration→T2; run_monitor_loop wiring + busy_light exclusion + retry_in→T3; reload prune→T4; webui panel/badge/state/liveness→T5; docs→T6. State model lives client-side (T5); the Python side tests the DATA contract (T1–T3).
- **Type/name consistency:** `_monitor_name`, `register_monitor(name,kind,interval)->str`, `record_monitor_error(name,message,consecutive,retry_in)`, `clear_monitors()`, `monitors[name] = {kind,interval,last_ok,error{message,consecutive,at,retry_in}}`, snapshot key `monitors` (list with `name`) — identical across tasks and the webui.
- **Ordering gotcha:** T2 migrates the instrumentation assertions to `board.monitors`, but those monitors only populate once T3 makes the fakes register (they need `.draw`). Keep T2+T3 in the same branch; if an instrumentation assertion is red between T2 and T3, that's expected — it greens at T3. (T2's own `test_snapshot_serializes_monitors...` is self-contained and passes at T2.)
- **The load-bearing correctness properties:** never-raise-into-the-loop (T3 + the guarded recorders), busy_light-excluded (T3), schema-migration-lands-together (T2+T5 don't blank the table). These are mandatory; their tests must not be weakened.
- Verify the active-board test setter convention (`set_active_board` vs direct `_ACTIVE =`) before writing T1's tests.

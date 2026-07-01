# Inline Value Tokens v2 — Core (Polled Sources) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the core polled/async source mechanism that v1 deferred — a `PolledDataSource` base, supervised background polling, shared-session injection, and a plugin-source validate hook — so a plugin can ship an async source (weather lands next, in its own plugin PR).

**Architecture:** A `PolledDataSource(DataSource)` declares `polled=True`, holds an injected `session`+`interval`, and implements `async def update()` which fetches then calls `_set_value()` (write `current` before `version`, no `await` between). Core spawns a supervised `run_monitor_loop(source, interval)` per polled source at startup and respawns on hot-reload; the existing 1 Hz sync ticker already skips polled sources. `draw()` only reads `source.current`.

**Tech Stack:** Python 3.14 (PEP 649), attrs, asyncio, aiohttp (already a dep).

**Source of truth:** `docs/superpowers/specs/2026-06-30-inline-value-tokens-v2-polled-design.md` (§1, §3, §5). The weather plugin (§2) is a SEPARATE plan after the v4.1.0 core release.

## Global Constraints

- **Write-order (CRITICAL):** a source writes `current` **before** `version`, with **no `await` between** — so a reader sampling version-then-current never pairs a new version with a stale value. The `_set_value` helper is the single enforcement point.
- **Supervised, never crashes:** a poll crash/fetch-failure logs and the panel keeps running — use the existing `run_monitor_loop` (exponential backoff, survives exceptions).
- **`draw()` never awaits** — it reads `source.current` (a cached string) only.
- **The 1 Hz sync ticker keeps skipping polled sources** (`if not source.polled`) — never regress that.
- **`PolledDataSource` is public surface** — exported from `led_ticker.plugin.__all__`; plugins import only `led_ticker.plugin`.
- PEP 649 (no `from __future__ import annotations`); DOCS-STYLE (no "footgun"); core gates **without** a `PYTHONPATH=tests/stubs` prefix (it's redundant): `uv run --extra dev pytest`, `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev pyright src/`. Worktree + PR; never `main`. Use `git -c core.hooksPath=/dev/null` if the pre-commit hook misbehaves.

## Non-Goals (core)

The weather source itself (separate plugin plan); sub-field tokens (`:weather.nyc.temp:`); sharing a poll between a widget and a source; crypto/other polled sources; any format-expression-language beyond `str.format`.

## File Structure

- **Modify** `src/led_ticker/sources.py` — extract `DataSource._set_value`; add `PolledDataSource`; spawn polled loops in `spawn_source_refresh` (return all task handles).
- **Modify** `src/led_ticker/plugin.py` — export `PolledDataSource` (`__all__`).
- **Modify** `src/led_ticker/app/factories.py` — `build_source` injects `session`/`interval` into `PolledDataSource` subclasses; add the source `validate_config` hook helper.
- **Modify** `src/led_ticker/app/run.py` — pass the shared session into source-build; store the list of source task handles.
- **Modify** `src/led_ticker/app/reload.py` — cancel+respawn the polled source tasks on reload (extend the existing source-ticker respawn).
- **Modify** `src/led_ticker/validate.py` — run a source class's `validate_config` during preflight.
- **Modify** `tests/test_sources.py`, `tests/test_validate.py`, the reload + plugin-API-drift tests; **docs** `concepts/value-tokens.mdx` + the plugin API reference.

---

## Task 1: `PolledDataSource` + `_set_value` (sources.py)

**Files:** Modify `src/led_ticker/sources.py`; Test `tests/test_sources.py`.

**Interfaces — Produces:**
- `DataSource._set_value(self, new: str) -> bool` (write-order + bump-only-on-change; `refresh()` now delegates to it).
- `class PolledDataSource(DataSource)`: `polled=True`, `session: Any = None`, `interval: int = 1800` (all kw_only), `async def update(self) -> None` (subclass implements), and `compute()` raising (polled never uses the sync path).

- [ ] **Step 1: Write the failing tests** in `tests/test_sources.py`:

```python
import asyncio
import attrs
import pytest
from led_ticker.sources import DataSource, PolledDataSource, StaticSource


def test_set_value_write_order_and_bump_only_on_change():
    s = StaticSource(id="x", value="a")
    assert s._set_value("a") is True          # first set bumps from version 0
    assert (s.current, s.version) == ("a", 1)
    assert s._set_value("a") is False         # unchanged → no bump
    assert s.version == 1
    assert s._set_value("b") is True          # changed → bump
    assert (s.current, s.version) == ("b", 2)


def test_polled_source_is_polled_and_holds_session_interval():
    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None:
            self._set_value("hello")

    s = _Fake(id="acme.live", session="SESS", interval=42)
    assert s.polled is True
    assert s.session == "SESS"
    assert s.interval == 42
    assert s.current == "" and s.version == 0  # nothing until update()


@pytest.mark.asyncio
async def test_polled_update_sets_value_write_order():
    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None:
            await asyncio.sleep(0)            # the fetch await happens BEFORE...
            self._set_value("123")            # ...the synchronous current+version set

    s = _Fake(id="acme.live")
    await s.update()
    assert (s.current, s.version) == ("123", 1)


def test_polled_compute_raises():
    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None: ...

    with pytest.raises(NotImplementedError):
        _Fake(id="x").compute()


def test_sync_refresh_still_works():
    s = StaticSource(id="x", value="z")
    assert s.refresh() is True and s.current == "z" and s.version == 1
    assert s.refresh() is False and s.version == 1
```

- [ ] **Step 2: Run → FAIL** — `uv run --extra dev pytest tests/test_sources.py -k "set_value or polled or sync_refresh" -v`.

- [ ] **Step 3: Implement** in `sources.py`. Add `_set_value` to `DataSource` and delegate `refresh`:

```python
    def _set_value(self, new: str) -> bool:
        """Apply a new value with the write-order contract: write `current`
        BEFORE `version`, with no await between, and bump `version` only when
        the value actually changed. Returns whether it changed. This is the
        SINGLE enforcement point for the contract (sync refresh + polled
        update both go through it)."""
        if new == self.current and self.version != 0:
            return False
        self.current = new  # current BEFORE version (contract)
        self.version += 1
        return True

    def refresh(self) -> bool:
        """Recompute (sync) and apply via _set_value."""
        return self._set_value(self.compute())
```

Add `PolledDataSource` after `DateSource` (and `from typing import Any` is already imported; `attrs` is imported):

```python
@attrs.define(eq=False)
class PolledDataSource(DataSource):
    """Base for asynchronous (network-backed) sources — weather, prices, etc.

    The subclass implements `async def update()`, which performs its awaited
    fetch and then calls `self._set_value(<formatted string>)` (synchronous —
    honoring the write-order contract). Core spawns a supervised
    `run_monitor_loop(self, self.interval)` per polled source (backoff +
    survives exceptions); the 1 Hz sync ticker skips it (`polled` is True).
    `draw()` only ever reads `current` — it never awaits.
    """

    # `session` is an injected shared aiohttp.ClientSession (typed Any here to
    # keep core import-light; the plugin source types it). `interval` is the
    # poll period in seconds (from the [[source]] block; default 30 min).
    polled: bool = attrs.field(default=True, kw_only=True)
    session: Any = attrs.field(default=None, kw_only=True)
    interval: int = attrs.field(default=1800, kw_only=True)

    async def update(self) -> None:
        """Fetch + `self._set_value(...)`. Subclass responsibility."""
        raise NotImplementedError

    def compute(self) -> str:
        raise NotImplementedError("polled sources update via async update()")
```

- [ ] **Step 4: Run → PASS** (match the project's async-test convention — it uses `pytest.mark.asyncio` elsewhere). Run the whole `tests/test_sources.py`.

- [ ] **Step 5: Commit** — `git add src/led_ticker/sources.py tests/test_sources.py && git commit -m "feat(sources): PolledDataSource + _set_value (write-order single enforcement)"`.

---

## Task 2: Export `PolledDataSource` from `led_ticker.plugin`

**Files:** Modify `src/led_ticker/plugin.py`; the plugin-API drift test (find it — `tests/test_docs_plugin_api_drift.py` or similar); `docs/site/.../plugins/api-reference.mdx` if drift-guarded.

**Interfaces — Consumes:** `PolledDataSource` (Task 1). **Produces:** `from led_ticker.plugin import PolledDataSource` works; it's in `__all__`.

- [ ] **Step 1: Write the failing test** (add to the plugin-surface test file):

```python
def test_polled_data_source_is_public():
    import led_ticker.plugin as plugin
    from led_ticker.plugin import PolledDataSource  # noqa: F401
    assert "PolledDataSource" in plugin.__all__
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in `plugin.py`, import `PolledDataSource` alongside the existing `DataSource` import, and add `"PolledDataSource"` to `__all__` (next to `"DataSource"`).

- [ ] **Step 4:** If `tests/test_docs_plugin_api_drift.py` audits `led_ticker.plugin.__all__` against `docs/site/.../plugins/api-reference.mdx`, add `PolledDataSource` to the exports table there. Run the drift test.

- [ ] **Step 5: Run → PASS.** Gates. Commit: `git commit -am "feat(plugin): export PolledDataSource (public surface for async sources)"`.

---

## Task 3: `build_source` injects session/interval into polled sources

**Files:** Modify `src/led_ticker/app/factories.py`; Test `tests/test_sources.py` (factory tests live there).

**Interfaces — Consumes:** `PolledDataSource`, `get_source_class`/`build_source`, `SourceConfig`. **Produces:** `build_source(cfg, session=None)` — for a `PolledDataSource` subclass, constructs it with `id`, `session`, `interval` (from `cfg.raw.get("interval", 1800)`), and the remaining config kwargs; sync core sources unchanged (built without session/interval).

- [ ] **Step 1: Write the failing tests** in `tests/test_sources.py`:

```python
def test_build_source_injects_session_and_interval_for_polled(monkeypatch):
    import attrs
    from led_ticker.sources import PolledDataSource
    from led_ticker.app.factories import build_source, _SOURCE_TYPES  # or _PLUGIN_SOURCE_TYPES
    from led_ticker.config import SourceConfig

    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        location: str = ""
        async def update(self) -> None: ...

    # register the fake type into the plugin source registry
    from led_ticker.sources import _PLUGIN_SOURCE_TYPES
    _PLUGIN_SOURCE_TYPES["acme.live"] = _Fake
    try:
        cfg = SourceConfig(
            id="x", type="acme.live",
            raw={"id": "x", "type": "acme.live", "location": "NYC", "interval": 60},
        )
        src = build_source(cfg, session="SESS")
        assert isinstance(src, _Fake)
        assert src.session == "SESS" and src.interval == 60 and src.location == "NYC"
    finally:
        _PLUGIN_SOURCE_TYPES.pop("acme.live", None)


def test_build_source_sync_unchanged():
    from led_ticker.app.factories import build_source
    from led_ticker.config import SourceConfig
    from led_ticker.sources import ClockSource
    cfg = SourceConfig(id="c", type="clock", raw={"id": "c", "type": "clock", "format": "%H"})
    src = build_source(cfg)  # no session
    assert isinstance(src, ClockSource) and src.fmt == "%H"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — read the current `build_source` in `factories.py`. Add a `session: Any = None` param, and a `PolledDataSource` branch BEFORE the core-type branches:

```python
from led_ticker.sources import PolledDataSource  # add to imports

def build_source(cfg: SourceConfig, session: Any = None) -> DataSource:
    cls = get_source_class(cfg.type)
    if issubclass(cls, PolledDataSource):
        # Generic kwarg passthrough for plugin polled sources: id + injected
        # session/interval + the remaining [[source]] kwargs (location, format,
        # placeholder, …). Drop reserved keys so they don't collide.
        kwargs = {
            k: v for k, v in cfg.raw.items()
            if k not in ("id", "type", "interval")
        }
        return cls(
            id=cfg.id,
            session=session,
            interval=cfg.raw.get("interval", 1800),
            **kwargs,
        )
    # ... existing clock/date/static branches unchanged ...
```

(Verify the exact existing branches/structure and keep them; only add the polled branch + the `session` param.)

- [ ] **Step 4: Run → PASS.** Confirm the existing source-build tests still pass. Gates. Commit.

---

## Task 4: Spawn the polled loops (sources.py `spawn_source_refresh` + run.py)

**Files:** Modify `src/led_ticker/sources.py` (`spawn_source_refresh`); `src/led_ticker/app/run.py` (pass session to source build; store the handles); Test `tests/test_sources.py`.

**Interfaces — Consumes:** `run_monitor_loop` (widget.py), `spawn_tracked`. **Produces:** `spawn_source_refresh(registry) -> list` — returns ALL source task handles: the single 1 Hz sync-refresh task **plus** one `run_monitor_loop` task per polled source.

- [ ] **Step 1: Write the failing test** in `tests/test_sources.py`:

```python
@pytest.mark.asyncio
async def test_spawn_source_refresh_spawns_polled_loops():
    import attrs
    from led_ticker.sources import DataRegistry, PolledDataSource, spawn_source_refresh

    polled_calls = []

    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None:
            polled_calls.append(1)
            self._set_value("v")

    reg = DataRegistry()
    reg.add(_Fake(id="p", interval=0.01))
    tasks = spawn_source_refresh(reg)
    # one 1 Hz sync task + one polled loop task
    assert isinstance(tasks, list) and len(tasks) == 2
    await asyncio.sleep(0.05)
    assert polled_calls, "polled update() was never called by run_monitor_loop"
    for t in tasks:
        t.cancel()


@pytest.mark.asyncio
async def test_one_hz_ticker_does_not_poll_polled_source():
    import attrs
    from led_ticker.sources import DataRegistry, PolledDataSource, run_source_refresh_loop

    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None: ...
    reg = DataRegistry(); s = _Fake(id="p"); reg.add(s)
    task = asyncio.create_task(run_source_refresh_loop(reg, interval=0.01))
    await asyncio.sleep(0.05)
    assert s.version == 0  # the sync ticker never touched the polled source
    task.cancel()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in `sources.py`, add `from led_ticker.widget import run_monitor_loop` (alongside `spawn_tracked`), and rewrite `spawn_source_refresh`:

```python
def spawn_source_refresh(registry: DataRegistry) -> list:
    """Prime sync sources, spawn the shared 1 Hz sync loop, AND spawn a
    supervised `run_monitor_loop` per POLLED source. Returns every task handle
    (the caller stores them for cancellation on hot-reload)."""
    tasks: list = []
    for source in registry.sources():
        if not source.polled:
            source.refresh()
    tasks.append(spawn_tracked(run_source_refresh_loop(registry)))
    for source in registry.sources():
        if source.polled:
            tasks.append(spawn_tracked(run_monitor_loop(source, source.interval)))
    return tasks
```

- [ ] **Step 4:** In `app/run.py`, where `spawn_source_refresh` is called: (a) ensure the shared aiohttp session exists first and is passed into source build (`build_source(cfg, session=...)` — read how the app creates its data-widget session and reuse it); (b) store the returned **list** of handles (where it previously stored a single task) so reload can cancel them. Read run.py to adapt the call sites + the `_ReloadResult`-style storage.

- [ ] **Step 5: Run → PASS.** Full suite (`uv run --extra dev pytest`) — run.py changes ripple. Gates. Commit.

---

## Task 5: Hot-reload — respawn polled tasks (app/reload.py)

**Files:** Modify `src/led_ticker/app/reload.py` (`_apply_reload`); Test the reload test file.

**Interfaces — Consumes:** `spawn_source_refresh` (now returns a list), `build_source(cfg, session)`, the atomic-or-nothing source-rebuild guard already added in v1.

- [ ] **Step 1: Write the failing test** — extend the reload tests: after `_apply_reload` with a changed `[[source]]` set including a polled source, the OLD source task handles (the list) are cancelled and a NEW list is spawned (the new registry's polled sources get loops); and the v1 bad-source guard still keeps the OLD tasks live if a new source fails to build. (Mirror the existing sync-ticker reload test + the bad-source-keeps-old test.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — read `_apply_reload`. It already: builds the new `DataRegistry` (now via `build_source(cfg, session)` — pass the session), atomic-swaps it, and cancels+respawns the source task(s). Extend the cancel to cancel ALL handles in the stored list, and `spawn_source_refresh(new_reg)` returns the new list (which now includes polled loops). Keep the v1 try/except guard: on a build failure, log + keep the OLD registry AND the OLD task list (don't cancel, don't swap). Thread the session into the rebuild.

- [ ] **Step 4: Run → PASS.** Full suite. Gates. Commit.

---

## Task 6: Source `validate_config` hook (validate.py + factories.py)

**Files:** Modify `src/led_ticker/validate.py` (the source-validation path / Rule 56) and/or `src/led_ticker/app/factories.py`; Test `tests/test_validate.py`.

**Interfaces — Produces:** during preflight, a source class's optional `validate_config(cls, cfg) -> list[str]` is run and its errors surfaced (mirrors the widget `_run_validate_config` at `factories.py:560`).

- [ ] **Step 1: Write the failing test** in `tests/test_validate.py`:

```python
def test_source_validate_config_hook_surfaces_errors():
    import attrs
    from led_ticker.sources import PolledDataSource, _PLUGIN_SOURCE_TYPES

    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None: ...
        @classmethod
        def validate_config(cls, cfg):
            return ["acme.live: location is required"] if "location" not in cfg else []

    _PLUGIN_SOURCE_TYPES["acme.live"] = _Fake
    try:
        bad = _appconfig_with_source({"id": "x", "type": "acme.live"})   # helper builds an AppConfig
        errs = _run_validate(bad)                                        # the validate entry point
        assert any("location is required" in e for e in errs)
        ok = _appconfig_with_source({"id": "x", "type": "acme.live", "location": "NYC"})
        assert not any("location is required" in e for e in _run_validate(ok))
    finally:
        _PLUGIN_SOURCE_TYPES.pop("acme.live", None)
```

(Model the `_appconfig_with_source` / `_run_validate` helpers on how the existing Rule-56 tests build an AppConfig + invoke validate — read `tests/test_validate.py`'s source tests and reuse their harness.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in the source-validation rule (Rule 56 `_check_sources` in `validate.py`), after the core-type checks, for each declared source resolve its class via `get_source_class(type)` (already used for the unknown-type check) and, if the class defines `validate_config`, call `cls.validate_config(cfg.raw)` and append the returned errors (wrap in try/except → a clear "validate_config raised" error, mirroring `_run_validate_config`). Core source types (no `validate_config`) are unaffected.

- [ ] **Step 4: Run → PASS.** Gates. Commit.

---

## Task 7: Docs — polled sources subsection

**Files:** Modify `docs/site/src/content/docs/concepts/value-tokens.mdx`; `docs/site/.../plugins/api-reference.mdx`.

- [ ] **Step 1:** Add a short "Live (polled) sources" subsection to `value-tokens.mdx` (DOCS-STYLE): explain that some source types fetch in the background on an `interval` (vs the built-in clock/date/static which compute locally), that they're contributed by plugins via `api.source` + `PolledDataSource`, and that a token shows a placeholder until the first fetch then updates live. Keep the concrete weather `[[source]]` example for the weather-plugin docs (note "see the weather plugin" — the example lands there). No "footgun"; no release-history framing.

- [ ] **Step 2:** Ensure `PolledDataSource` appears in the plugin API reference exports (done in Task 2 if drift-guarded; confirm).

- [ ] **Step 3:** `make docs-build` && `make docs-lint` clean.

- [ ] **Step 4: Commit.**

---

## Self-Review notes (for the executor)

- **Spec coverage:** §1 PolledDataSource→T1; public surface→T2; build/inject→T3; spawn wiring→T4; hot-reload→T5; validate hook→T6; §3 width-reuse = no new code (v1's re-measure-on-change already covers a polled value changing width — note in T7 docs); §5 core tests spread across T1–T6; docs→T7.
- **Type consistency:** `_set_value`, `PolledDataSource(session, interval, update())`, `build_source(cfg, session)`, `spawn_source_refresh -> list`, the source `validate_config` hook — names used identically across tasks.
- **The write-order contract (T1) + supervised-never-crash (T4/T5) are the load-bearing properties** — their tests are mandatory; do not weaken them.
- Tasks 3–6 require reading the current `build_source`/`run.py`/`reload.py`/`validate.py` bodies — the steps give the new code + the integration recipe; match the surrounding style.
- After this core plan merges + **v4.1.0** is cut, the weather source ships in a SEPARATE led-ticker-plugins plan (spec §2).

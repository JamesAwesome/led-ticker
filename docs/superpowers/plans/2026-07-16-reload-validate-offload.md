# Reload Validate Off the Event Loop (Phase 3: #302) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `validate_config`'s synchronous phases run in a worker thread (`asyncio.to_thread`), and the reload path's duplicate `load_config` is offloaded too — a hot-reload of a big config no longer hitches the render loop.

**Architecture:** `validate_config` is a sync–await–sync sandwich: Phase 1a/1b static checks, then the single `await _run_build_checks(...)`, then Phase 1c-cont/1d/2 + schedule checks + notes + strict promotion. Extract the two sync brackets into pure helpers (behavior-identical refactor first, offload second), keep the genuinely-async build checks on the loop, and `to_thread` the brackets. `reload.load_and_validate`'s second `load_config` gets the same `to_thread` treatment boot already uses (`run.py` initial load).

**Tech Stack:** Python 3.14, asyncio, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-16-engine-liveness-phases-design.md` (Phase 3). Issue: #302 (includes the de-risk note: `load_plugins` is idempotent, so the plugin-load inside validate is a guarded no-op on reload).

## Global Constraints

- Work in `/Users/james/projects/github/jamesawesome/led-ticker-reload-validate` on branch `reload-validate-offload`. Verify `pwd` and `git branch --show-current` before git operations.
- Commands via `uv run ...`; `make test` full suite; pyright 0 new errors on touched files before push; no `from __future__ import annotations`; commit trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Task 1 is a **byte-equivalent refactor**: `ValidationResult` outputs (errors, warnings, notes, ordering) must be identical for every existing test — zero test-expectation edits allowed in Task 1. If a test needs changing, the refactor is wrong: STOP, report NEEDS_CONTEXT.
- The apply path (`reload._apply_reload`, engine mutation) stays on the loop — untouched.
- Callers must not change signatures: `validate_config` / `validate_config_text` keep their async signatures; cli (`asyncio.run(validate_config(...))`), webui (3 call sites), and `reload.load_and_validate` keep working unmodified except where a task names them.
- Validation depth (spec, Phase 3): per-task review + ONE adversarial pass, then draft PR. No merge without James.

---

### Task 1: Extract the sync brackets (pure refactor)

**Files:**
- Modify: `src/led_ticker/validate.py` (`validate_config`, lines ~2972-3250)
- Test: existing suites only (`tests/test_validate*.py`, `tests/test_count_validation.py`, `tests/test_reload.py`) — green unchanged.

**Interfaces:**
- Produces two module-level sync helpers with exact signatures:
  - `_validate_static_prebuild(path: Path, *, strict: bool, config_dir: Path | None) -> "_PrebuildResult"` — everything from the `path.exists()` check through the last sync check before `await _run_build_checks` (plugin load suppress, font-dir configure, Phase 1a load with its early-return error shape, all Phase 1b checks).
  - `_validate_static_postbuild(pre: "_PrebuildResult", build_errors, build_warnings, migration_errors, *, strict: bool) -> ValidationResult` — everything after the await (Phase 1c-cont coercion/fix mapping, 1d band checks, Phase 2 soft rules, strict asset checks, schedule checks + notes, strict promotion, result assembly).
  - `_PrebuildResult` — a small `@dataclass` (match validate.py's existing dataclass style) carrying exactly the locals that cross the await: at minimum `config` (or None), `errors`, `warnings`, `effective_config_dir`, and `early_result: ValidationResult | None` (set when Phase 1a fails and the function returned early — the caller returns it without running build checks). READ the function first and enumerate the real crossing locals; add fields as the code demands, list them in your report.
- `validate_config` becomes: `pre = _validate_static_prebuild(...)`; `if pre.early_result is not None: return pre.early_result`; `build_errors, build_warnings, migration_errors = await _run_build_checks(...)` (unchanged call, args from `pre`); `return _validate_static_postbuild(pre, ...)`. NO `to_thread` yet — that's Task 2, so this task's diff is reviewable as pure motion.

- [ ] **Step 1: Snapshot behavior before touching anything**

Run and SAVE the outputs (they're your equivalence oracle):
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-reload-validate
uv run pytest tests/test_validate_visibility_schedule.py tests/test_count_validation.py -q | tail -1
uv run led-ticker validate config/config.example.toml > /tmp/validate_before.txt 2>&1
uv run led-ticker validate config/config.scheduling_smoketest.longboi.toml >> /tmp/validate_before.txt 2>&1
```

- [ ] **Step 2: Perform the extraction**

Move code verbatim — no rewording, no reordering, no "while I'm here" cleanups. The only new lines are the helper `def`s, the dataclass, and the glue in `validate_config`. Keep every comment attached to its code. The local-import statements (`load_plugins_for_config`, `load_config`, `known_backends`, etc.) move with their phases.

- [ ] **Step 3: Prove equivalence**

```bash
uv run pytest tests/test_validate_visibility_schedule.py tests/test_count_validation.py tests/test_reload.py -q
uv run led-ticker validate config/config.example.toml > /tmp/validate_after.txt 2>&1
uv run led-ticker validate config/config.scheduling_smoketest.longboi.toml >> /tmp/validate_after.txt 2>&1
diff /tmp/validate_before.txt /tmp/validate_after.txt && echo IDENTICAL
```
Expected: tests pass unchanged; `IDENTICAL`. Then the full validate surface: `uv run pytest tests/ -q -k "validate"` — all pass.

- [ ] **Step 4: pyright + ruff on validate.py (0 new / clean), then commit**

```bash
git add src/led_ticker/validate.py
git commit -m "refactor(validate): extract sync brackets around the build checks (pure motion, #302)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Offload — `to_thread` the brackets + reload's duplicate load

**Files:**
- Modify: `src/led_ticker/validate.py` (`validate_config` glue only)
- Modify: `src/led_ticker/reload.py` (`load_and_validate`, ~line 81)
- Test: `tests/test_validate_offload.py` (new)

**Interfaces:**
- Consumes: Task 1's helpers.
- Produces: `validate_config`'s glue becomes:
  ```python
      pre = await asyncio.to_thread(
          _validate_static_prebuild, path, strict=strict, config_dir=config_dir
      )
      if pre.early_result is not None:
          return pre.early_result
      build_errors, build_warnings, migration_errors = await _run_build_checks(...)
      return await asyncio.to_thread(
          _validate_static_postbuild, pre, build_errors, build_warnings,
          migration_errors, strict=strict,
      )
  ```
  (add `import asyncio` to validate.py if absent). And `reload.load_and_validate`'s success-path `return load_config(path), [], False` becomes `return await asyncio.to_thread(load_config, path), [], False` (keep both except clauses — `to_thread` propagates the worker's exceptions to the awaiter, so the existing `FileNotFoundError`/`Exception` handling still catches them; confirm `import asyncio` present in reload.py).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validate_offload.py`:

```python
"""#302: the reload-path validate must not block the event loop.

Strategy: monkeypatch the extracted sync brackets with versions that
time.sleep (a REAL thread block); a concurrent heartbeat task must keep
ticking while validate_config runs. If the brackets ran on the loop, the
heartbeat would freeze for the sleep duration."""

import asyncio
import time
from pathlib import Path

import pytest

from led_ticker import validate as validate_mod

CONFIG = Path(__file__).parent.parent / "config" / "config.example.toml"


@pytest.mark.asyncio
async def test_validate_config_does_not_block_the_loop(monkeypatch):
    real_pre = validate_mod._validate_static_prebuild

    def slow_pre(path, *, strict, config_dir):
        time.sleep(0.5)  # real thread block — NOT asyncio.sleep
        return real_pre(path, strict=strict, config_dir=config_dir)

    monkeypatch.setattr(validate_mod, "_validate_static_prebuild", slow_pre)

    beats = 0

    async def heartbeat():
        nonlocal beats
        while True:
            beats += 1
            await asyncio.sleep(0.05)

    hb = asyncio.create_task(heartbeat())
    try:
        result = await validate_mod.validate_config(CONFIG)
    finally:
        hb.cancel()
        with pytest.raises(asyncio.CancelledError):
            await hb
    # 0.5s of thread-blocked prebuild → the loop should have ticked ~10x.
    # Generous floor (3) keeps slow CI honest without flaking.
    assert beats >= 3, f"event loop starved during validate ({beats} beats)"
    assert result is not None


@pytest.mark.asyncio
async def test_load_and_validate_offloads_the_duplicate_load(monkeypatch):
    """The reload path's second load_config must run via to_thread."""
    from led_ticker import reload as reload_mod

    calls = []
    real_to_thread = asyncio.to_thread

    async def spy_to_thread(fn, *args, **kwargs):
        calls.append(getattr(fn, "__name__", repr(fn)))
        return await real_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", spy_to_thread)
    config, errors, transient = await reload_mod.load_and_validate(CONFIG)
    assert config is not None and errors == [] and transient is False
    assert "load_config" in calls, f"duplicate load not offloaded: {calls}"
    assert "_validate_static_prebuild" in calls
    assert "_validate_static_postbuild" in calls
```

Match the repo's async-test convention (grep `pytest.mark.asyncio|anyio` in tests/test_ticker_queue_bounding.py and copy).

- [ ] **Step 2: RED** — run the new file; expected failures: heartbeat starves (beats < 3) and/or the to_thread spy sees no calls.

- [ ] **Step 3: Implement** the glue per the Produces block.

- [ ] **Step 4: GREEN + blast radius**

```bash
uv run pytest tests/test_validate_offload.py -v
uv run pytest tests/test_reload.py tests/test_run_reload_helpers.py -q
uv run pytest tests/ -q -k "validate"
```
All pass. Then webui + cli surfaces: `uv run pytest tests/test_webui* tests/test_list_fields_golden.py -q` (glob-adjust to real filenames).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py src/led_ticker/reload.py tests/test_validate_offload.py
git commit -m "feat(validate,reload): run validate's sync brackets and reload's duplicate load off the event loop (#302)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Thread-safety audit — verified, written down, and pinned

**Files:**
- Modify: `src/led_ticker/validate.py` (one docstring block on `validate_config`)
- Test: `tests/test_validate_offload.py` (append)

**Interfaces:** consumes Tasks 1-2. Produces the documented audit + two pins.

- [ ] **Step 1: Audit every global mutation reachable from the two sync brackets** (this is a read-and-verify step; record each item + verdict in your report AND condense into the docstring):
  1. `load_plugins_for_config` → `load_plugins` idempotency guard (`_plugin_loader.py` ~344, `if _LOADED is not None: return _LOADED`) — verify the guard is the FIRST statement so a worker-thread call after boot is a pure read. (The issue's de-risk note; confirm, don't assume.)
  2. `_configure_user_font_dir` (`led_ticker.app`) — module-global write; verify it's idempotent (same value each call for a given config path) and racing writes of the same value are benign.
  3. `functools.cache`d font/glyph loaders reachable via font-resolution checks — CPython's cache is locked internally; concurrent first-call at worst double-computes. Confirm nothing cached is loop-bound.
  4. `schedule.set_schedule_timezone` / `bind_schedule` — verify NEITHER is reachable from the sync brackets (grep the call graph; validation parses schedules but must never bind or set the clock).
  5. Anything else the brackets import that writes module state — grep `global ` and module-level mutables in the files the brackets touch; list findings.

- [ ] **Step 2: Pin the two audit items that would silently regress**

```python
def test_validate_never_binds_schedules(tmp_path):
    """Validation must be side-effect-free on the schedule registry —
    a worker-thread validate that bound widgets would race the render
    loop's reads."""
    from led_ticker import schedule

    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[display]\nrows = 16\ncols = 32\nbackend = "headless"\n\n'
        "[[playlist.section]]\nmode = \"slideshow\"\n\n"
        "[[playlist.section.widget]]\ntype = \"message\"\ntext = \"hi\"\n"
        'schedule = { start = "09:00", end = "17:00" }\n'
    )
    before = dict(schedule._BINDINGS)
    asyncio.run(validate_mod.validate_config(cfg))
    assert dict(schedule._BINDINGS) == before


def test_plugin_load_guard_is_first():
    """AST pin: load_plugins' idempotency guard must stay its first
    statement — the thread-safety of worker-thread validation rests on it."""
    import ast, inspect
    from led_ticker import _plugin_loader

    tree = ast.parse(inspect.getsource(_plugin_loader.load_plugins))
    first = tree.body[0].body[0]
    src = ast.unparse(first)
    assert "_LOADED" in src and ("return" in src or isinstance(first, ast.If)), src
```

Adapt the second test's AST specifics to `load_plugins`' real shape (read it first); the assertion's intent — guard before any mutation — is the requirement, the exact AST walk is yours.

- [ ] **Step 3: Docstring** — add a "Thread-safety" paragraph to `validate_config`'s docstring: the sync brackets run via `to_thread`; safe because (plugin load idempotent — pinned; font-dir configure idempotent; caches internal-locked; no schedule binding — pinned); the build checks stay on the loop.

- [ ] **Step 4: Run + commit**

```bash
uv run pytest tests/test_validate_offload.py -v   # all pass
git add src/led_ticker/validate.py tests/test_validate_offload.py
git commit -m "test(validate): thread-safety audit pins — no schedule binding, plugin guard first (#302)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Gate, adversarial pass, close the board (controller-run tail)

- [ ] **Step 1: Full gate** — `make test`, `make lint`, branch-files pyright (0 new), `make docs-build`/`docs-lint` only if docs touched, both smoketest validates.
- [ ] **Step 2 (controller):** ONE adversarial correctness pass (mechanism-first) — seed surfaces: refactor-equivalence blind spots (any local that silently changed scope/lifetime across the split), to_thread exception propagation vs the reload path's never-raise contract, concurrent validates (webui text-validate racing a file-watch reload — two worker threads in the brackets simultaneously: audit items hold?), cli's `asyncio.run` path, event-loop-policy edge (no running loop in helpers).
- [ ] **Step 3 (controller):** Fix wave if needed; then draft PR via open-pr (`Closes #302`; note this closes the engine-liveness spec's final phase and the whole issue board except #400). CI watch. No merge without James.

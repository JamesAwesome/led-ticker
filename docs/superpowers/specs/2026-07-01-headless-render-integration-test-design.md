# Headless render integration test — design

**Date:** 2026-07-01
**Status:** Approved (design walked through with James; config strategy chosen: purpose-built + smallsign example).

## Goal

A CI test that boots REAL configs through the FULL production startup path — `run(config_path)`: config load → widget build → frame build → `backend.setup()` → ticker loop → `SwapOnVSync` — on the headless backend, and asserts the panel **renders content**, not merely that the process survives.

## Origin

A `[[sections]]` vs `[[playlist.section]]` schema typo produced a config that parsed to 0 sections: `validate` passed silently, all unit tests were green, and the panel busy-looped dark. The two core bugs are fixed (#335: empty-playlist idle+warn; validate errors on 0 sections), but NOTHING in CI exercises `run()`'s real startup — unit tests stub around it, `validate` is static, and `tools/render_demo` uses a separate renderer pipeline. This test closes the "boots cleanly but panel dark" gap end-to-end.

## Verified foundations

- `run(config_path)` (`app/run.py:646`) is the full async entry — one path argument.
- `[display] backend = "headless"` selects `HeadlessBackend` (`config.py:71`; `factories.py:1112-1116` via `get_backend_class`). Headless does no privilege drop (hardware constraint #13 is rgbmatrix-only).
- `HeadlessCanvas` exposes `get_pixel(x, y)` and `count_nonzero()`; `HeadlessBackend.swap(canvas)` receives every displayed frame.
- `config/config.example.toml` is ALL-CORE (message ×5, countdown ×2, countup, clock, gif with a repo asset) — bootable in CI. `config.bigsign.example.toml` is NOT (plugin widgets `baseball.scores`, `rss.feed` hard-error at load without plugins) — excluded; the scale=4 path is covered by a purpose-built config instead.

## Design

### Configs (3 boots, one test each)

1. **Purpose-built smallsign** (scale=1, e.g. 160×16): 2 `message` widgets + `clock`, `backend = "headless"`, small `hold_time`/`speed` so frames accumulate in ~1–2 s. Fully offline, deterministic. Lives in `tests/` as a fixture file (or written by the test from an inline string — implementer's choice; keep it out of `config/` so it can't be mistaken for a user example).
2. **Purpose-built bigsign-shaped** (scale=4, headless canvas sized accordingly, e.g. 256×64 with `default_scale = 4`): same widget mix — covers the `ScaledCanvas` wrapper path end-to-end.
3. **`config/config.example.toml`** copied to tmp with `backend = "headless"` injected into `[display]` — example-rot protection: the first config users copy must always boot and render. (Injection = simple TOML text edit on the tmp copy; if the example ever gains a widget that can't run in CI, this test is the tripwire that says so.)

### Frame tap

`monkeypatch`-wrap `HeadlessBackend.swap`: the wrapper calls the real `swap` and appends `(canvas.count_nonzero(), hash(bytes-of-pixel-buffer))` to a test-owned list. No production-code changes; no private-attr assertions.

### Assertions (per boot) — the render-demo multiframe tripwire shape

- **Liveness:** ≥ M frames swapped (M ≈ 5) within the ceiling.
- **Content:** ≥ 1 frame with `count_nonzero() > 0` — a `Clear()`+swap loop fails here (the dark-panel class).
- **Motion:** ≥ 2 distinct content hashes among non-black frames — a frozen panel fails here.
- **Status-board agreement:** `swap_count > 0` on the active board (the engine-liveness surface agrees with the pixels).

### Bounding + determinism (anti-flake rules)

- `run()` starts as an `asyncio` task. The test **condition-polls** the frame list (`await asyncio.sleep(0.05)` loop) until M frames arrive or a generous ceiling (~15 s) passes — no fixed sleeps sized to machine speed.
- **Early-failure propagation:** each poll iteration checks `task.done()`; if `run()` died during startup the test re-raises its exception immediately — a boot failure reports as the real traceback, not a timeout.
- Teardown: cancel the task, `await` it with `CancelledError` suppressed, and cancel/await any tracked stragglers (monitor loops, heartbeat) so no orphan task logs during teardown — the schedule-ticker-flake lesson (explicit cancellation, condition-based waiting).
- The status board, if activated by `run()`, is cleared/deactivated in a `finally` so state can't leak between tests (mirror the `set_active_board`/`clear_active_board` convention).

### Placement

`tests/test_integration_render.py`, ordinary pytest — no special CI job. Measure total runtime during implementation; the target is the normal suite (~a few seconds for all three boots). Only if it exceeds ~15 s total: `@pytest.mark.slow` + CI include (empirical call, documented in the test module docstring either way).

## Constraints

- No Docker, no hardware, no network in CI. The purpose-built configs are fully offline; the example config's widgets are all-core (the `gif` asset is in-repo).
- Deterministic: condition-polling + explicit cancellation; no time-sized sleeps.
- No production-code changes expected. If a small seam is genuinely needed (e.g. a teardown hook), it must be additive and never touch the render path — flag it in review rather than working around it silently.
- PEP 649; gates: `uv run --extra dev pytest`, `ruff check`, `ruff format --check`, `pyright src/`; worktree + PR; STOP at the open green PR (explicit merge approval per PR).

## Out of scope

Booting `config.bigsign.example.toml` (plugin widgets); Docker-based smoke tests; performance assertions; screenshot/golden-image comparison (content-hash variation is deliberately weaker but non-brittle).

## Sizing

One test file + one or two small config fixtures. Single-task execution (one implementer + one reviewer).

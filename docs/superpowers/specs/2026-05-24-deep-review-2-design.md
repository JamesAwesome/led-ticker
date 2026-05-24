# Deep Review 2 — Design Spec

**Date:** 2026-05-24
**Goal:** Start a new improvement cycle — findings → prioritized action list → batched PRs — covering the areas not addressed by the first engine review plus a post-refactor engine re-evaluation.

## Background

The first review (`~/Desktop/engine-review.md`, 2026-05-20) was engine-focused: render path, code organization, type safety, error messaging, performance. It drove batches 1–8 and large refactors 1–5, several of which have now landed (Large #2+4, Large #3). This review covers the remaining surface: test suite quality, Python idioms, install/deploy/CI, tooling scripts — plus a targeted post-refactor engine pass.

## Approach

Five parallel review agents, one per domain. Each agent reads its assigned files and produces structured findings (Critical / Significant / Minor). After all five return, findings are synthesized in-chat into a single output document at `~/Desktop/deep-review-2.md`.

## Agent Briefs

### Agent 1 — Engine re-eval

**Files:** `src/led_ticker/app/`, `src/led_ticker/ticker.py`, `src/led_ticker/scaled_canvas.py`, `src/led_ticker/widget.py`, `src/led_ticker/transitions/`

**Scope:**
- Did the large refactors achieve their stated goals?
  - app.py split (`app/cli.py`, `app/factories.py`, `app/coercion.py`, `app/run.py`): clean separation of concerns? residual cross-module tangles?
  - Ticker methods refactor: are the scrolling functions proper methods now? any lingering free-function patterns?
  - ScaledCanvas encapsulation: are the 24+ `isinstance` sites gone? is `paint_hires` used at all call sites? any new leakage?
- Any regressions or new issues introduced by the large refactors
- First-review action items not addressed in batches 1–8 / larges 1–5
- Engine adherence to Python async best practices in its current form

### Agent 2 — Test suite quality

**Files:** `tests/` (all ~50 top-level files), `tests/test_widgets/` (~20 files), `tests/conftest.py`, `tests/fixtures/`, `tests/stubs/`

**Scope:**
- Test code organization: naming conventions, module-to-test mapping, file length
- Fixture reuse vs copy-paste duplication
- Coverage gaps: which code paths have no test, which branches are exercised only by accident
- Brittle tests: tests that couple to implementation details and will break on valid refactors
- Test speed: slow tests, unnecessary real I/O, missing mocks
- Meta-tripwires (`test_engine_redraw_contract.py`, `test_docs_config_options_drift.py`): are they well-maintained or fragile?
- `conftest.py` structure: fixture scope, `mock_frame` vs `swapping_frame` discipline

### Agent 3 — Python idioms / modern Python

**Files:** `src/led_ticker/` (all modules)

**Scope:**
- Asyncio patterns: sync calls blocking the event loop (beyond the known `feedparser` case), cancellation handling, `asyncio.gather` vs sequential awaits, task lifecycle management
- attrs usage: field ordering, validators, `__init_subclass__` guards, `attrs.define` vs `attr.s` style consistency
- Annotation completeness: `Any`-escape sites beyond the already-fixed `Canvas=Any`; missing return types; bare `dict`/`list` vs parameterized generics
- Python 3.11+ features available but unused (e.g., `tomllib` in stdlib — already used; `ExceptionGroup`, `Self`, `LiteralString`, `TaskGroup`)
- Deprecated or outdated patterns (e.g., `asyncio.get_event_loop()` vs `asyncio.get_running_loop()`, old-style string formatting, `Optional[X]` vs `X | None`)
- General CS/Python best practices: single-responsibility, naming, magic numbers, module cohesion

### Agent 4 — Install, deploy & CI

**Files:** `deploy/install.sh`, `deploy/led-ticker.service`, `Dockerfile`, `compose.yaml`, `docker-compose.yml`, `.github/workflows/ci.yml`, `.github/workflows/docs-deploy.yml`

**Scope:**
- `install.sh`: root execution model (necessary? risks?), idempotency (safe to re-run?), update path (how does a user upgrade?), error handling (`set -euo pipefail` present — what else?), rgbmatrix version pinning
- systemd unit: hardening (`ProtectSystem`, `NoNewPrivileges`, restart policy), env file loading, logging
- Docker: USER directive (running as root?), secret handling (`.env` mount), image layer caching, size
- `compose.yaml` vs `docker-compose.yml`: two files in the repo — are they consistent? which is canonical?
- CI (`ci.yml` + `docs-deploy.yml`): coverage threshold enforcement, self-hosted runner security, branch protection adequacy, missing checks (no Docker build in CI, no integration test), docs deploy pipeline risks
- Dependabot config: what's covered, what's missing

### Agent 5 — Tooling & dependency hygiene

**Files:** `tools/render_demo/`, `tools/gif_plan/`, `scripts/`, `Makefile`, `pyproject.toml`, `uv.lock`

**Scope:**
- `render_demo`: robustness (error handling, edge cases), test coverage (`test_renderer_multiframe.py` — is that the only test?), documentation
- `gif_plan`: correctness, test coverage, edge cases
- `crypto-ticker.py`: maintenance state, documentation, whether it's tested
- `check-no-foreign-lockfiles.sh`: does it work? what does it protect?
- Makefile patterns: correctness of phony targets, shell portability, missing targets
- `pyproject.toml` dep hygiene: version pin strategy (floor-only vs ceiling), unused or redundant deps (`tomli-w` is listed as a dep but `tomllib` is stdlib on 3.11+ — verify if `tomli-w` is actually used anywhere; `imageio` vs `Pillow` overlap), missing extras, `requires-python` coverage
- `uv.lock`: any known-vulnerable packages (spot check)

## Output Document

**Path:** `~/Desktop/deep-review-2.md`

**Structure:**
```
# Deep Review 2 — Findings
Date: 2026-05-24

## Executive Summary

## Critical Findings
### C1. [domain] ...

## Significant Findings
### S1. [domain] ...

## Minor Findings
### M1. [domain] ...

## Cross-Cutting Observations
### CC1. ...

## Prioritized Action List
### Quick Wins (< 1 PR each)
### Medium (1–2 PRs each)
### Large (multi-PR)
```

Domain tags on each finding: `[engine]`, `[tests]`, `[python]`, `[deploy]`, `[tooling]` — makes grouping into batch plans easy without re-reading.

## What This Review Does NOT Cover

- Docs site content quality (covered by the `review-docs` skill)
- Hardware wiring / BOM (not software)
- The render path hardware contract (already tripwire-tested; first review covered it)
- Widget feature completeness (out of scope for a quality review)

# Python 3.13 → 3.14 Upgrade — Design

**Date:** 2026-05-30
**Status:** Approved (brainstorming complete)

## Goal

Move led-ticker to **Python 3.14 as the hard floor**, resolve the imminent
`python:3.13-bullseye` EOL (June 2026), bank the free wins that ride along, and
explicitly park the experimental features. Base image becomes
**`python:3.14-bookworm`**.

## Scoping decisions (captured during brainstorming)

- **Floor → 3.14.** `requires-python = ">=3.14"`, dropping 3.11–3.13. led-ticker
  is a self-deployed app (single Docker image to the owner's own Pis), not a
  public library, so backward-compat with older interpreters has little value —
  and bumping the floor is what makes the feature-adoption (e.g. dropping the 59
  `from __future__ import annotations`) actionable.
- **Scope → core upgrade + safe wins.** Get clean on 3.14 and adopt only
  low-risk/high-value improvements. Park genuinely risky/experimental items.
- **Validation → both Pis + 3.13 rollback.** Green CI → build image →
  smoke-test on Pi 4 *and* Pi 5 → keep the last 3.13 image pinned for instant
  rollback.
- **Sequencing → rgbmatrix spike first, then one combined PR.** Front-load the
  single high-risk item (the Cython rebuild) before any app change.

## Why 3.14 (context)

Two background research passes informed this:

- **Feature applicability:** for this codebase 3.14 is **primarily an
  EOL-driven "stay current" move, not a features play**. The marquee 3.14
  features are the wrong shape here (see Out of Scope). The genuinely valuable
  items are the *free* ones: the ~10–20% single-thread interpreter speedup that
  lands on the hand-tuned pixel loops (`scaled_canvas.py`, `text_render.py`),
  the asyncio `ps`/`pstree` introspection tooling that fits the poller-heavy
  architecture, and the ability to drop the 59 `from __future__` imports.
- **Dependency/deploy compatibility:** everything *except* rgbmatrix is
  low-risk. Pillow 12 (cp314 aarch64 wheels), aiohttp 3.13.5 (cp314 armv7l +
  aarch64), all pure-Python deps, and the full dev/tooling stack (pytest 9,
  pytest-asyncio 1.4, pyright, ruff 0.14, hatchling, uv tier-1) are confirmed on
  3.14 with ARM wheels available. The recommended base is `python:3.14-bookworm`.

## Architecture / phases

### Phase 0 — rgbmatrix compatibility spike (de-risk first)

Prove the `jamesawesome/rpi-rgb-led-matrix` fork compiles on
`python:3.14-bookworm` for **arm64**, with **no app changes**:

- **Audit** the fork's `core.pyx` / `.pxd` for the **removed `ma_version_tag`**
  (gone in 3.14, was on `PyDictObject`) and any `Py_REFCNT(op) == 1` idioms
  (3.14 deferred reference counting changes their meaning). Grep/read task — no
  build required.
- **Throwaway arm64 Docker build** of the fork on `python:3.14-bookworm` with
  **Cython ≥ 3.2.5**. Confirm it compiles against the image Python headers
  (`/usr/local/include/python3.14`, *not* the apt `python3-dev` 3.11 headers),
  and that the three fork patches survive: the GCC-12 `pio_rp1.c` anonymous-param
  fix, the `graphics.py` Pillow shim, and the `SubFill` Cython binding.
- **Exit criterion:** a clean arm64 rgbmatrix `.so`. If it breaks, patch the fork
  (isolated fork PR) until it builds. **Nothing in Phase 1 starts until this
  passes.**

### Phase 1 — Core upgrade (one PR)

- **Dockerfile:** `FROM python:3.13-bullseye` → `python:3.14-bookworm`; bump
  `RGBMATRIX_CACHE_BUST` (forces a fresh clone + fresh Cython resolution); pin
  `Cython>=3.2.5` in the rgbmatrix build layer; refresh the migration header
  notes (the bullseye-EOL / bookworm comments are now done).
- **`pyproject.toml`:** `requires-python = ">=3.14"`;
  `[tool.pyright] pythonVersion = "3.14"`; `[tool.ruff] target-version =
  "py314"`. No forced dependency-floor bumps — Pillow/aiohttp/etc. resolve to
  3.14-ready versions on their own.
- **`.python-version` → `3.14`;** `uv sync`.
- **CI:** matrix Python → `3.14` (replace 3.13); update the dependabot
  base-image note to track `python:3.14-*`.
- Get `make test` / `make lint` / `make typecheck` green on 3.14.

### Phase 2 — Safe-win cleanups (bundled into the Phase 1 PR)

- **Remove `from __future__ import annotations`** from all 59 source files as a
  deliberate pass (not a blind sed). Under PEP 649 (3.14 default) annotations are
  lazily evaluated without the import, so attrs and pyright don't need it.
- **Tripwire test for `factories.py:_render_field`** (the `--list-fields` CLI
  output) — the *only* place that observes annotation form at runtime. Removing
  the future import changes attrs field types from strings to real objects, so
  capture the current `--list-fields` output as a snapshot and assert the
  removal doesn't silently change it (or update the snapshot intentionally if it
  legitimately changes).
- **Docs recipe** for asyncio introspection: `python -m asyncio ps <pid>` /
  `pstree <pid>` on a live Pi, tied to the existing CLAUDE.md diagnostic ("a
  silent log stream after startup means a background `update()` task died").

### Phase 3 — Validation & rollback

- Green CI (full suite on 3.14) → build the **arm64** image → smoke-test on
  **both** Pi 4 (smallsign) and Pi 5 (longboi/bigsign), confirming panels
  actually render (the C-extension/hardware path is not exercised by CI).
- Keep the last working **3.13 image tag pinned** for instant rollback.
- The Dockerfile `FROM` change merges to `main` **only after both Pis pass**.

## Risk register

| Risk | Severity | Mitigation |
| --- | --- | --- |
| rgbmatrix Cython rebuild against 3.14 (removed `ma_version_tag`, refcount idioms, needs Cython ≥ 3.2.5, stale Docker cache) | **High** | Phase 0 spike + audit; bump `RGBMATRIX_CACHE_BUST`; pin Cython floor |
| GCC 10→12 change (bookworm) affecting the `pio_rp1.c` anonymous-param patch | Medium | Caught in the Phase 0 arm64 build (same concern as the already-planned bookworm migration) |
| piwheels cp314 gap for bare-metal `pip install` on the Pi (no aarch64; armv7l unconfirmed) | Low (Docker) / Medium (bare-metal) | Irrelevant to the Docker path (ships pre-built); document the gap for bare-metal users |

## Out of scope (parked as separate future spikes)

- **Free-threading / no-GIL.** Net loss here: single event loop, bottleneck is
  the rgbmatrix C draw behind the GIL, and the C extension doesn't declare
  `Py_mod_gil = Py_MOD_GIL_NOT_USED`, so it would force the GIL back on anyway.
- **Sub-interpreters / `InterpreterPoolExecutor`.** Single display loop owns the
  one hardware handle; widgets are I/O-bound and already use `asyncio.to_thread`.
- **Tail-call interpreter** custom build (`--with-tail-call-interp` + Clang 19) —
  a separate experiment with before/after hardware timing.
- **t-strings, `compression.zstd`, UUIDv7, `Path.copy`** — confirmed zero
  surface area in `src/`.
- **Multi-stage slim final image** (~200 MB saving) — an independent
  optimization; deferred to keep this upgrade focused.

## Success criteria

- `make test` (full suite), `make lint`, `make typecheck` green on Python 3.14.
- Docker image builds for arm64 on `python:3.14-bookworm`.
- Panels render correctly on both Pi 4 (smallsign) and Pi 5 (longboi).
- `requires-python = ">=3.14"`; zero `from __future__ import annotations` remain
  in `src/`; `--list-fields` output unchanged (tripwire passes).
- A pinned 3.13 image remains available for rollback.

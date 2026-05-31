# Python 3.13 → 3.14 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move led-ticker to Python 3.14 as the hard floor on a `python:3.14-bookworm` base, banking the free wins (drop 59 `from __future__` imports, asyncio-introspection docs) and parking the experiments.

**Architecture:** A rgbmatrix Cython-rebuild spike (Phase 0) de-risks the only high-risk item before any app change. Then one combined pass updates the Docker base, the Python floor, tooling pins, and CI, removes the future-imports (guarded by a `--list-fields` tripwire), and adds the asyncio-introspection doc. Hardware validation on both Pis with a pinned 3.13 rollback gates the merge.

**Tech Stack:** Python 3.14, Docker (`python:3.14-bookworm`, arm64), Cython ≥ 3.2.5, uv, ruff, pyright, pytest, the `jamesawesome/rpi-rgb-led-matrix` fork.

**Spec:** `docs/superpowers/specs/2026-05-30-python-314-upgrade-design.md`

**Conventions for every task:**
- Run tests with `PYTHONPATH=tests/stubs uv run --extra dev pytest <path>` (uv reads `.python-version` for the interpreter).
- Commit with hooks disabled (worktree hooks are broken): `git -c core.hooksPath=/dev/null commit`.
- Line length is 88 (ruff). Run `make lint` before each commit.
- End commit messages with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

**Two tasks need the owner's environment** (ARM Docker / Pi hardware) and are marked **[USER-RUN]** — a code agent prepares the exact files/commands; the owner executes them and reports back before the gated step proceeds.

---

## File Structure

- `Dockerfile` (modify) — base image `python:3.14-bookworm`, Cython pin, cache-bust, header notes.
- `pyproject.toml` (modify) — `requires-python`, pyright `pythonVersion`, ruff `target-version`.
- `.python-version` (modify) — `3.14`.
- `.github/dependabot.yml` (modify) — base-image tracking note.
- `.github/workflows/ci.yml` (verify — likely no change; CI tracks `.python-version`).
- `tests/golden/list_fields/*.txt` (**new**) — captured `--list-fields` output per widget type.
- `tests/test_list_fields_golden.py` (**new**) — tripwire asserting `--list-fields` output is stable across the future-import removal.
- All 59 `src/led_ticker/**/*.py` (modify) — remove `from __future__ import annotations`.
- `src/led_ticker/app/factories.py` (modify, only if drift) — make `_render_field` type rendering annotation-form-independent.
- `docs/site/src/content/docs/...` (modify) — asyncio-introspection debugging recipe.

---

## Task 1: rgbmatrix 3.14 C-API compatibility audit (Phase 0 gate)

**Files:** none in this repo — audits the `jamesawesome/rpi-rgb-led-matrix` fork.

**Context:** Python 3.14 removed `PyDictObject.ma_version_tag` and changed the meaning of `Py_REFCNT(op) == 1` (deferred refcounting). If the fork's Cython `core.pyx` / `.pxd` or its C uses either, the 3.14 build fails. This is a read-only grep audit — no build.

- [ ] **Step 1: Clone the fork shallowly to a scratch dir**

```bash
git clone --depth=1 --branch main \
  https://github.com/jamesawesome/rpi-rgb-led-matrix.git /tmp/rgbmatrix-audit
```

- [ ] **Step 2: Grep for the removed / changed C-API**

```bash
cd /tmp/rgbmatrix-audit
echo "=== ma_version_tag (removed in 3.14) ==="
grep -rn "ma_version_tag" . || echo "none"
echo "=== Py_REFCNT == 1 idioms (semantics changed) ==="
grep -rnE "Py_REFCNT\s*\([^)]*\)\s*==\s*1|ob_refcnt\s*==\s*1" . || echo "none"
echo "=== Cython version hints in setup ==="
grep -rniE "cython" setup.py setup.cfg pyproject.toml 2>/dev/null || echo "no explicit Cython pin (pip resolves latest)"
```

Expected: ideally all "none" (the binding is a thin SubFill addition + RP1 patches, unlikely to touch dict internals). Record the output.

- [ ] **Step 3: Report findings**

Write the grep results into the task report. **Go/no-go:** if both removed-API greps are "none", the audit is clear → proceed to Task 2. If either matches, note the file:line — Task 2's build will confirm whether Cython ≥ 3.2.5 papers over it or a fork patch is needed.

- [ ] **Step 4: Commit** (audit note only — no repo code changed)

Nothing to commit in this repo. Record findings in the task report for Task 2.

---

## Task 2: rgbmatrix arm64 build spike on python:3.14-bookworm (Phase 0 gate) [USER-RUN]

**Files:** Create (scratch, not committed): `/tmp/rgbmatrix-spike/Dockerfile`

**Context:** Prove the fork compiles cleanly against Python 3.14 headers for arm64 before touching the app. Needs Docker buildx with arm64 emulation (or an actual Pi). A code agent writes the spike Dockerfile + commands; **the owner runs the build** and reports the result.

- [ ] **Step 1: Write the scratch spike Dockerfile**

Create `/tmp/rgbmatrix-spike/Dockerfile`:

```dockerfile
FROM python:3.14-bookworm
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y build-essential git cmake && \
    rm -rf /var/lib/apt/lists/*
RUN cd /opt && \
    git clone --depth=1 --branch main \
        https://github.com/jamesawesome/rpi-rgb-led-matrix.git rgbmatrix-src && \
    cd rgbmatrix-src && \
    pip install "Cython>=3.2.5" && \
    pip install . -v
# Prove the extension imports against the 3.14 interpreter.
RUN python -c "import rgbmatrix; print('rgbmatrix OK on', __import__('sys').version)"
```

- [ ] **Step 2: Build for arm64 [USER-RUN]**

```bash
docker buildx build --platform linux/arm64 -t rgbmatrix-spike \
  --progress=plain /tmp/rgbmatrix-spike
```

Expected: the build completes and the final `python -c "import rgbmatrix..."` prints `rgbmatrix OK on 3.14.x`. Confirm in the log that the compile used `/usr/local/include/python3.14` (the image Python), not `/usr/include/python3.11`.

- [ ] **Step 3: Resolve any failure**

If the build fails:
- `ma_version_tag` / refcount compile error → patch the fork (separate fork PR), commonly by bumping Cython or adjusting the offending line, then re-run.
- `pio_rp1.c` GCC error → the GCC 10→12 anonymous-param issue; patch in the fork.
Iterate until the import line succeeds.

- [ ] **Step 4: Gate**

**Exit criterion:** a clean arm64 build that imports `rgbmatrix` on 3.14. Do **not** start Task 3 until this passes. Record the result (and any fork patch PR link) in the task report.

---

## Task 3: Move the Dockerfile to python:3.14-bookworm

**Files:** Modify `Dockerfile`

- [ ] **Step 1: Update the base image and header note**

Replace lines 1–10 (the `# Base image migration note (M14):` block through the `FROM` line) with:

```dockerfile
# Base: python:3.14-bookworm (Debian 12, GCC 12). Migrated from
# python:3.13-bullseye (Debian 11, EOL June 2026) together with the 3.13->3.14
# Python bump. The rgbmatrix fork compiles cleanly here against the image's
# Python 3.14 headers with Cython >= 3.2.5 (verified by the Phase 0 arm64 spike).
# The GCC10 anonymous-param patch in pio_rp1.c compiles under GCC 12.
# Future optimization (deferred): multi-stage build copying only the compiled
# rgbmatrix .so into python:3.14-slim-bookworm (~200MB smaller).
FROM python:3.14-bookworm AS rgbmatrix
```

- [ ] **Step 2: Pin Cython and bump the cache-bust**

Change `ARG RGBMATRIX_CACHE_BUST=2` to `ARG RGBMATRIX_CACHE_BUST=3`, and update the rgbmatrix build `RUN` (the `cd /opt && git clone ... && pip install .` block) to:

```dockerfile
ARG RGBMATRIX_CACHE_BUST=3
RUN cd /opt && \
    git clone --depth=1 --branch main \
        https://github.com/jamesawesome/rpi-rgb-led-matrix.git rgbmatrix-src && \
    cd rgbmatrix-src && \
    pip install "Cython>=3.2.5" && \
    pip install .
```

Also drop `python3-dev` from the apt line (the build uses the image's bundled 3.14 headers, not the apt 3.11 ones) — change `apt-get install -y build-essential git python3-dev cmake` to `apt-get install -y build-essential git cmake`.

- [ ] **Step 3: Verify the image builds for arm64 [USER-RUN]**

```bash
docker buildx build --platform linux/arm64 -t led-ticker:py314 --progress=plain .
```

Expected: build succeeds through all three layers. (This re-confirms Task 2 inside the real Dockerfile.)

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git -c core.hooksPath=/dev/null commit -m "build: move base image to python:3.14-bookworm

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Bump the Python floor and tooling to 3.14

**Files:** Modify `pyproject.toml`, `.python-version`

- [ ] **Step 1: Update `.python-version`**

Replace its single line `3.13` with `3.14`.

- [ ] **Step 2: Update pyproject pins**

In `pyproject.toml`:
- `requires-python = ">=3.11"` → `requires-python = ">=3.14"`
- under `[tool.pyright]`: `pythonVersion = "3.13"` → `pythonVersion = "3.14"`
- under `[tool.ruff]`: `target-version = "py311"` → `target-version = "py314"`

Leave all dependency version floors unchanged (Pillow/aiohttp/etc. resolve to 3.14-ready versions on their own — per the spec, no forced bumps).

- [ ] **Step 3: Sync the 3.14 toolchain locally**

```bash
uv python install 3.14
uv sync --extra dev
uv run python --version
```

Expected: `uv run python --version` prints `Python 3.14.x`.

- [ ] **Step 4: Run the full gate on 3.14**

```bash
make lint
make typecheck
PYTHONPATH=tests/stubs uv run --extra dev pytest -q
```

Expected: ruff clean, pyright `0 errors`, full suite green (the suite uses `tests/stubs` for rgbmatrix, so no hardware needed). Fix any 3.14-surfaced failures (e.g. a deprecation now an error) minimally before committing.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .python-version uv.lock
git -c core.hooksPath=/dev/null commit -m "build: bump Python floor to 3.14 (pyproject, pyright, ruff, .python-version)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: CI + dependabot housekeeping for 3.14

**Files:** Modify `.github/dependabot.yml`; verify `.github/workflows/ci.yml`

**Context:** `ci.yml` selects the interpreter via `astral-sh/setup-uv` + `.python-version` (there is no explicit `python-version` matrix), so Task 4's `.python-version = 3.14` already moves CI to 3.14. This task confirms that and fixes the stale dependabot note.

- [ ] **Step 1: Confirm ci.yml needs no version change**

```bash
grep -nE "python-version|3\.13" .github/workflows/ci.yml || echo "no hardcoded python version — tracks .python-version"
```

Expected: no hardcoded `python-version`/`3.13` in ci.yml. If any appears, change it to `3.14`.

- [ ] **Step 2: Update the dependabot base-image note**

In `.github/dependabot.yml`, find the comment block referencing `python:3.13-bullseye` / `EOL June 2026` and replace it to reference `python:3.14-bookworm` (Dependabot will file PRs for new `python:3.14-*` images). Keep the surrounding config keys unchanged.

- [ ] **Step 3: Commit**

```bash
git add .github/dependabot.yml
git -c core.hooksPath=/dev/null commit -m "ci: track python:3.14-bookworm base image in dependabot note

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `--list-fields` golden tripwire (before removing future-imports)

**Files:** Create `tests/golden/list_fields/` + `tests/test_list_fields_golden.py`

**Context:** Removing `from __future__ import annotations` changes attrs field types from *strings* to *real objects*, which `factories.py:_render_field` renders for un-hinted fields via `__name__`/`str()`. This characterization test captures the CURRENT output so Task 7 can prove it doesn't drift. Written and committed while the future-imports are still present (so the golden reflects today's behavior).

- [ ] **Step 1: Write the test**

Create `tests/test_list_fields_golden.py`:

```python
"""Tripwire: `--list-fields` output must not change when the
`from __future__ import annotations` imports are removed (the only place
that observes attrs annotation *form* at runtime is factories._render_field).
The golden files are captured on the current tree; Task 7 re-runs this test
after removing the future-imports and either it still passes (no drift) or
the goldens are updated deliberately.
"""

from pathlib import Path

import pytest

from led_ticker.app.factories import _list_widget_fields

GOLDEN_DIR = Path(__file__).parent / "golden" / "list_fields"

# Cover a spread: simple-typed, two-row split (gif), and data widgets whose
# font_color is an un-hinted ColorProvider union — the actual drift surface.
TYPES = ["message", "two_row", "gif", "weather", "mlb", "countdown"]


@pytest.mark.parametrize("widget_type", TYPES)
def test_list_fields_output_is_stable(widget_type):
    golden = GOLDEN_DIR / f"{widget_type}.txt"
    assert golden.exists(), (
        f"missing golden {golden}; regenerate with the snippet in the task"
    )
    assert _list_widget_fields(widget_type) == golden.read_text()
```

- [ ] **Step 2: Generate the golden files from current behavior**

```bash
mkdir -p tests/golden/list_fields
PYTHONPATH=tests/stubs uv run python - <<'PY'
from pathlib import Path
from led_ticker.app.factories import _list_widget_fields
d = Path("tests/golden/list_fields"); d.mkdir(parents=True, exist_ok=True)
for t in ["message", "two_row", "gif", "weather", "mlb", "countdown"]:
    (d / f"{t}.txt").write_text(_list_widget_fields(t))
    print("wrote", t)
PY
```

- [ ] **Step 3: Run the test (passes on current tree)**

```bash
PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_list_fields_golden.py -v
```

Expected: 6 passed (the goldens match the current output).

- [ ] **Step 4: Commit**

```bash
git add tests/test_list_fields_golden.py tests/golden/list_fields/
git -c core.hooksPath=/dev/null commit -m "test: golden tripwire for --list-fields output stability

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Remove `from __future__ import annotations` from all 59 source files

**Files:** Modify all `src/led_ticker/**/*.py` that contain the import; possibly `src/led_ticker/app/factories.py`

**Context:** With the 3.14 floor and PEP 649 lazy annotations, the import is unnecessary. attrs and pyright handle it. The `--list-fields` tripwire from Task 6 is the safety net for the one runtime observer.

- [ ] **Step 1: Confirm the scope**

```bash
grep -rl "from __future__ import annotations" src/ | wc -l   # expect 59
```

- [ ] **Step 2: Remove the import line from every src file**

```bash
grep -rl "from __future__ import annotations" src/ | while read -r f; do
  # delete the exact import line (and a trailing blank line if it becomes a
  # leading blank) — review the diff after.
  perl -0pi -e 's/from __future__ import annotations\n\n?//' "$f"
done
```

- [ ] **Step 3: Run lint, typecheck, and the FULL suite on 3.14**

```bash
make lint
make typecheck
PYTHONPATH=tests/stubs uv run --extra dev pytest -q
```

Expected: ruff clean (it auto-flags any now-needed import via F-rules), pyright `0 errors`, full suite green **including** `tests/test_list_fields_golden.py`.

- [ ] **Step 4: If the `--list-fields` tripwire fails (type-string drift), normalize `_render_field`**

Only if Step 3 shows `test_list_fields_output_is_stable` failing: make the type rendering annotation-form-independent so the output is identical whether `a.type` is a string or a real object. In `src/led_ticker/app/factories.py`, replace the `type_str = (...)` block inside `_render_field` (the `hint.display_type if hint else (...)` expression) with:

```python
        if hint:
            type_str = hint.display_type
        elif a.type is None:
            type_str = ""
        elif isinstance(a.type, str):
            type_str = a.type
        else:
            # Real annotation object (PEP 649): render to a stable string that
            # matches the pre-removal stringified form — name for plain types,
            # str() for unions/generics, with the module qualifier stripped.
            type_str = getattr(a.type, "__name__", None) or str(a.type)
            type_str = type_str.replace("led_ticker.", "").replace(
                "color_providers.", ""
            )
```

Then re-generate the goldens (Task 6 Step 2 snippet) **only if** you have confirmed by eye that the new output is the intended form, and re-run the suite. Prefer fixing the renderer over blindly re-snapshotting.

- [ ] **Step 5: Review the diff for stragglers**

```bash
git diff --stat            # ~59 files, each -1/-2 lines
grep -rn "from __future__ import annotations" src/ || echo "all removed"
```

Expected: no remaining occurrences in `src/`.

- [ ] **Step 6: Commit**

```bash
git add -A src/ tests/golden/
git -c core.hooksPath=/dev/null commit -m "refactor: drop from __future__ import annotations (3.14 PEP 649)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: asyncio-introspection debugging doc

**Files:** Modify a docs page under `docs/site/src/content/docs/` (a deploy/operations or concepts page)

**Context:** 3.14 ships `python -m asyncio ps <pid>` / `pstree <pid>` — a zero-instrumentation live task tree. It directly answers the existing CLAUDE.md diagnostic ("a silent log stream after startup means a background `update()` task died").

- [ ] **Step 1: Find the right docs home**

```bash
ls docs/site/src/content/docs/
grep -rln "systemd\|deploy\|docker compose\|troubleshoot" docs/site/src/content/docs/ | head
```

Pick the operations/deployment-oriented page (or the busy-light/concepts area if no ops page exists). Note the exact path.

- [ ] **Step 2: Add the recipe**

Add a short section to the chosen page:

````markdown
## Inspecting the running async loop (Python 3.14+)

led-ticker is one long-lived asyncio loop plus a background task per data
widget (`run_monitor_loop`) and the optional busy-light HTTP server. On Python
3.14 you can print the live task tree of a running container with no code
changes or restart:

```bash
# pid of the led-ticker process (inside the container or on bare metal)
python -m asyncio pstree <pid>
# flat list with awaited-by edges
python -m asyncio ps <pid>
```

If a data widget's `update()` task has died (the tell-tale: its periodic
"… updated: N stories" INFO log stopped), it will be absent from the tree —
turning the "is the poller alive?" question into a direct answer.
````

- [ ] **Step 3: Note the bare-metal piwheels caveat**

In the same ops/deployment page (or the existing bare-metal install instructions if one exists), add a one-line caveat: on Python 3.14 the **Docker** path ships everything pre-built, but a **bare-metal `pip install` on the Pi** may have to compile some wheels from source — piwheels does not provide aarch64 wheels and its cp314 armv7l coverage is incomplete as of mid-2026. Recommend the Docker deploy, or expect a longer first install on bare metal.

- [ ] **Step 4: Lint the docs**

```bash
make docs-format
make docs-lint
```

Expected: docs-lint passes.

- [ ] **Step 5: Commit**

```bash
git add docs/
git -c core.hooksPath=/dev/null commit -m "docs: asyncio ps/pstree recipe + bare-metal piwheels caveat for 3.14

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Hardware validation + rollback (Phase 3 gate) [USER-RUN]

**Files:** none committed — deployment validation.

**Context:** CI exercises the stub, never the real C extension or panels. This task is the owner's hardware gate; the Dockerfile `FROM` change merges to `main` only after it passes.

- [ ] **Step 1: Pin the current 3.13 image as rollback [USER-RUN]**

Before deploying, tag/retain the last known-good 3.13 image so a rollback is one command:

```bash
docker image tag led-ticker:latest led-ticker:rollback-py313
# (or note the current deployed digest in deploy notes)
```

- [ ] **Step 2: Build and deploy to the Pi 4 (smallsign) [USER-RUN]**

Build/pull the `python:3.14-bookworm` image on the Pi 4 and start it with the smallsign config. Confirm: container stays up, panels render, no rgbmatrix import/runtime error in logs.

- [ ] **Step 3: Build and deploy to the Pi 5 (longboi/bigsign) [USER-RUN]**

Same on the Pi 5 (different rgbmatrix GPIO backend — RP1). Confirm panels render and the RP1 path works.

- [ ] **Step 4: Gate the merge**

Only after BOTH Pis render correctly: the branch is clear to merge. If either fails, roll back with `docker run … led-ticker:rollback-py313` and report the failure (most likely a rgbmatrix runtime issue → re-open Task 2).

---

## Final verification (after all tasks)

- [ ] `make lint`, `make typecheck`, `PYTHONPATH=tests/stubs uv run --extra dev pytest -q` all green on 3.14.
- [ ] `grep -rn "from __future__ import annotations" src/` → empty.
- [ ] `grep -rn "3\.13\|bullseye" Dockerfile .python-version pyproject.toml` → no stale 3.13/bullseye refs.
- [ ] Both Pis validated (Task 9); 3.13 rollback image retained.
- [ ] Hand off to `superpowers:finishing-a-development-branch`.

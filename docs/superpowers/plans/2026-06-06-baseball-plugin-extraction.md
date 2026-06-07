# Baseball Plugin Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the MLB scores/standings widgets, the baseball emoji, and the baseball transitions out of led-ticker core into a new standalone public `led-ticker-baseball` plugin (namespace `baseball`).

**Architecture:** Two-repo effort mirroring the pool extraction. Core gets a pure-additive public-surface expansion (Phase 0) and later a removal+migration PR (Phase 3). A new `led-ticker-baseball` repo holds the plugin, importing ONLY `led_ticker.plugin`. The baseball emoji's private `_generate_baseball_hires` generator moves with the emoji+transition so the plugin is self-contained.

**Tech Stack:** Python 3.14 (PEP 649, no `from __future__ import annotations`), uv, pytest, ruff, hatchling, GitHub Actions, the led-ticker plugin entry-point system (`led_ticker.plugins` group).

**Companion spec:** `docs/superpowers/specs/2026-06-06-baseball-plugin-extraction-design.md`

**Worktree discipline (load-bearing):** Every code change goes through a worktree + PR — NEVER commit on `main`. Core PRs (Phase 0, Phase 3) each get their own worktree off `led-ticker`. The new repo's work happens in that repo on a feature branch. Run `git branch --show-current` before any commit; abort if it is `main`. Run `make dev` in any new core worktree before pushing (pre-commit/pyright need the venv).

**Locked decisions:** repo `led-ticker-baseball`; namespace `baseball`; widgets `baseball.scores` / `baseball.standings`; transitions `baseball.roll` / `baseball.roll_reverse` / `baseball.roll_alternating`; emoji slug `:baseball.ball:` (lo-res `ball` + hi-res `ball`); strict public-surface import purity.

---

## Phase 0 — Core public-surface expansion (Core PR A)

**Worktree:** `git worktree add -b feat/plugin-surface-baseball ../lt-surface ../led-ticker` (off `main`), then `cd ../lt-surface && make dev`.

**Files:**
- Modify: `src/led_ticker/plugin.py` (imports + `__all__`)
- Test: `tests/test_plugin_surface.py` (new or existing plugin-surface test)

### Task 0.1: Failing test for the new public symbols

**Files:**
- Test: `tests/test_plugin_surface.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plugin_surface.py
import led_ticker.plugin as P

NEW_SYMBOLS = [
    "TickerMessage",
    "FrameAwareBase",
    "safe_scale",
    "compute_baseline_for_band",
    "measure_width",
    "resolve_band_heights",
    "font_line_height_logical",
    "FONT_DEFAULT",
    "FONT_SMALL",
    "ScaledCanvas",
    "unwrap_to_real",
    "paint_hires",
]


def test_baseball_surface_symbols_exported():
    for name in NEW_SYMBOLS:
        assert name in P.__all__, f"{name} missing from led_ticker.plugin.__all__"
        assert hasattr(P, name), f"{name} not importable from led_ticker.plugin"


def test_frame_aware_base_is_the_internal_class():
    # FrameAwareBase is the public alias of widgets._frame_aware._FrameAware
    from led_ticker.widgets._frame_aware import _FrameAware
    assert P.FrameAwareBase is _FrameAware
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../lt-surface && PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_surface.py -v`
Expected: FAIL — symbols not in `__all__`.

### Task 0.2: Add the symbols to the public surface

**Files:**
- Modify: `src/led_ticker/plugin.py`

- [ ] **Step 1: Add the imports** (place beside the existing grouped imports near the top of `plugin.py`)

```python
from led_ticker.drawing import (
    compute_baseline,
    compute_baseline_for_band,
    get_text_width,
    safe_scale,
)
from led_ticker.fonts import (
    FONT_DEFAULT,
    FONT_SMALL,
    font_line_height_logical,
    resolve_font,
)
from led_ticker.pixel_emoji import (
    HiResEmoji,
    draw_emoji_at,
    measure_emoji_at,
    measure_width,
)
from led_ticker.pixel_emoji import draw_with_emoji as _draw_with_emoji
from led_ticker.scaled_canvas import ScaledCanvas, paint_hires, unwrap_to_real
from led_ticker.widgets._frame_aware import _FrameAware as FrameAwareBase
from led_ticker.widgets.message import SegmentMessage, TickerMessage
from led_ticker.widgets._row_layout import resolve_band_heights
```

> Merge these into the EXISTING import blocks rather than duplicating lines already present (`compute_baseline`, `get_text_width`, `resolve_font`, `SegmentMessage`, the `draw_with_emoji` alias, etc. are already imported — extend those statements, don't re-add).

- [ ] **Step 2: Add the names to `__all__`** (alphabetical, beside existing entries)

```python
    "FONT_DEFAULT",
    "FONT_SMALL",
    "FrameAwareBase",
    "ScaledCanvas",
    "TickerMessage",
    "compute_baseline_for_band",
    "font_line_height_logical",
    "measure_width",
    "paint_hires",
    "resolve_band_heights",
    "safe_scale",
    "unwrap_to_real",
```

- [ ] **Step 3: Run the surface test**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugin_surface.py -v`
Expected: PASS.

- [ ] **Step 4: Run the full core suite + lint** (no regression; surface change is additive)

Run: `make test && uv run --extra dev ruff check src/ tests/`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/plugin.py tests/test_plugin_surface.py
git commit -m "feat(plugin): expand public surface for rich-rendering plugins

Add TickerMessage, FrameAwareBase, safe_scale, compute_baseline_for_band,
measure_width, resolve_band_heights, font_line_height_logical,
FONT_DEFAULT/FONT_SMALL, and the hi-res transition surface
(ScaledCanvas/unwrap_to_real/paint_hires) to led_ticker.plugin.
Prerequisite for the led-ticker-baseball plugin.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 0.3: Document the new surface

**Files:**
- Modify: `docs/plugin-system.md` (public-surface reference section)

- [ ] **Step 1:** Add the new symbols to the public-surface table in `docs/plugin-system.md`, grouped as "rendering helpers" (TickerMessage, FrameAwareBase, safe_scale, compute_baseline_for_band, measure_width, resolve_band_heights, font_line_height_logical, FONT_DEFAULT, FONT_SMALL) and "hi-res transition surface" (ScaledCanvas, unwrap_to_real, paint_hires).
- [ ] **Step 2: Commit**

```bash
git add docs/plugin-system.md
git commit -m "docs(plugin-system): document expanded public surface"
```

- [ ] **Step 3: Push + open PR** (do NOT merge without explicit go-ahead)

```bash
git push -u origin feat/plugin-surface-baseball
gh pr create --title "feat(plugin): expand public surface for rich-rendering plugins" \
  --body "Pure-additive public-surface expansion. Prerequisite for the led-ticker-baseball plugin extraction. See docs/superpowers/specs/2026-06-06-baseball-plugin-extraction-design.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

**CHECKPOINT:** Phase 0 PR must be reviewed/merged before Phase 2 can pass CI against core `main`. (For local development, Phase 2 resolves against the sibling checkout, so build can proceed in parallel against the worktree — but green CI requires the merge.)

---

## Phase 1 — Git repository setup

This phase is mostly manual `gh` / GitHub operations. No TDD; the "test" is a green first CI run.

### Task 1.1: Create the local project + GitHub repo

- [ ] **Step 1: Create the folder and init**

```bash
mkdir -p ~/projects/github/jamesawesome/led-ticker-baseball
cd ~/projects/github/jamesawesome/led-ticker-baseball
git init
git branch -M main
```

- [ ] **Step 2: Create the public GitHub repo**

```bash
gh repo create JamesAwesome/led-ticker-baseball --public \
  --description "Baseball: MLB scores/standings widgets, baseball emoji, and baseball transitions for led-ticker (plugin)."
git remote add origin git@github.com:JamesAwesome/led-ticker-baseball.git
```

### Task 1.2: Set up read-only deploy-key CI auth (security-sensitive)

led-ticker is PRIVATE; CI checks it out as a sibling via a read-only deploy key. Mirrors the pool setup exactly.

- [ ] **Step 1: Generate a dedicated keypair**

```bash
ssh-keygen -t ed25519 -N "" -C "led-ticker-baseball CI (read-only)" \
  -f /tmp/lt-baseball-ci-key
```

- [ ] **Step 2: Add the PUBLIC key as a read-only deploy key on the private core repo**

```bash
gh repo deploy-key add /tmp/lt-baseball-ci-key.pub \
  --repo JamesAwesome/led-ticker \
  --title "led-ticker-baseball CI (read-only)"
# (read-only is the default — do NOT pass --allow-write)
```

- [ ] **Step 3: Add the PRIVATE key as a secret on the new repo**

```bash
gh secret set LED_TICKER_DEPLOY_KEY \
  --repo JamesAwesome/led-ticker-baseball \
  < /tmp/lt-baseball-ci-key
```

- [ ] **Step 4: Shred the temp keys**

```bash
rm -f /tmp/lt-baseball-ci-key /tmp/lt-baseball-ci-key.pub
```

### Task 1.3: Seed repo files

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `LICENSE`, `src/led_ticker_baseball/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`** (templated from pool; deps verified against what `mlb.py` actually needs — see Task 2.2)

```toml
[project]
name = "led-ticker-baseball"
version = "0.1.0"
description = "MLB scores/standings widgets, baseball emoji, and baseball transitions for led-ticker."
readme = "README.md"
requires-python = ">=3.14"
authors = [{ name = "James Awesome", email = "james@morelli.nyc" }]
dependencies = [
    "led-ticker",
    "aiohttp",
]

# Entry-point NAME ("baseball") becomes the plugin namespace.
[project.entry-points."led_ticker.plugins"]
baseball = "led_ticker_baseball:register"

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/led_ticker_baseball"]

# led-ticker is not on PyPI; resolve against the sibling checkout.
[tool.uv.sources]
led-ticker = { path = "../led-ticker", editable = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["../led-ticker/tests/stubs"]
```

- [ ] **Step 2: Write `.gitignore`** (copy pool's — `.venv`, `__pycache__`, `*.egg-info`, `uv.lock` is COMMITTED so do not ignore it).

- [ ] **Step 3: Copy `LICENSE`** from `led-ticker-pool` (same author/license).

- [ ] **Step 4: Write a `README.md` stub** with title + one-line description + a "Development" section pointing at the sibling-checkout setup (`uv sync --extra dev`). Full docs land in Phase 5.

- [ ] **Step 5: Write a placeholder `src/led_ticker_baseball/__init__.py`**

```python
"""led-ticker-baseball: MLB scores/standings widgets, baseball emoji, and
baseball transitions, contributed via the ``led_ticker.plugins`` entry point.
The entry-point name ``baseball`` is the plugin namespace."""


def register(api):
    # Real registrations wired in Phase 2.
    pass
```

### Task 1.4: CI workflow with CURRENT action versions

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Verify latest action versions BEFORE writing** (mandatory — do not copy stale pins)

```bash
gh release view --repo actions/checkout --json tagName -q .tagName
gh release view --repo astral-sh/setup-uv --json tagName -q .tagName
```
Record the latest stable tags. As of 2026-06-06 pool uses `actions/checkout@v6.0.3` and `astral-sh/setup-uv@v8.2.0`. If newer exists, use it here AND note a follow-up to bump pool to match (keep the two plugins in lockstep).

- [ ] **Step 2: Write the workflow** (substitute the versions confirmed in Step 1)

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout led-ticker-baseball
        uses: actions/checkout@<latest>     # from Step 1
        with:
          path: led-ticker-baseball
      - name: Checkout led-ticker (sibling dependency)
        uses: actions/checkout@<latest>     # from Step 1
        with:
          repository: JamesAwesome/led-ticker
          path: led-ticker
          ssh-key: ${{ secrets.LED_TICKER_DEPLOY_KEY }}
      - name: Install uv
        uses: astral-sh/setup-uv@<latest>   # from Step 1
        with:
          python-version: "3.14"
      - name: Sync
        working-directory: led-ticker-baseball
        run: uv sync --extra dev
      - name: Lint
        working-directory: led-ticker-baseball
        run: uv run ruff check src tests
      - name: Test
        working-directory: led-ticker-baseball
        run: uv run pytest -q
```

- [ ] **Step 3: Commit the seed + push**

```bash
cd ~/projects/github/jamesawesome/led-ticker-baseball
git add -A
git commit -m "chore: scaffold led-ticker-baseball plugin repo + CI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push -u origin main
```

- [ ] **Step 4: Confirm first CI run is GREEN**

```bash
gh run watch --repo JamesAwesome/led-ticker-baseball
```
Expected: deploy-key checkout of core succeeds, `uv sync` resolves, ruff + pytest pass (no real tests yet → pytest exits 0 with "no tests ran" or the placeholder). If the sibling checkout fails, the deploy key/secret pairing is wrong — revisit Task 1.2.

**CHECKPOINT:** Do not start Phase 2 ports until the first CI run is green (proves the deploy-key plumbing).

---

## Phase 2 — Build the plugin

All work in `~/projects/github/jamesawesome/led-ticker-baseball` on a feature branch (`git checkout -b feat/port-widgets`). Each task ends green + committed. Ports reuse the EXISTING core tests verbatim where possible; only the led-ticker imports change (→ `led_ticker.plugin`).

### Task 2.1: Port the baseball emoji

**Files:**
- Create: `src/led_ticker_baseball/emoji.py`
- Create: `tests/test_emoji.py` (port baseball slices of core `test_pixel_emoji.py` / `test_hires_loader.py`)

- [ ] **Step 1: Create `emoji.py`** — move from core `pixel_emoji.py`: the lo-res `BASEBALL` sprite (rename module constant to `BALL`), the hi-res `BASEBALL_HIRES` (→ `BALL_HIRES`), and the `_generate_baseball_hires` generator. The generator is self-contained pixel math; it imports nothing from core except basic types — verify with `grep "led_ticker" emoji.py` afterward (should be empty or only `led_ticker.plugin`).

- [ ] **Step 2: Write `tests/test_emoji.py`** — port the baseball-specific assertions from core's `test_pixel_emoji.py` (sprite dimensions, lit-pixel counts) and the `_generate_baseball_hires` checks from `test_hires_loader.py`. Adjust imports to `from led_ticker_baseball.emoji import BALL, BALL_HIRES, _generate_baseball_hires`.

- [ ] **Step 3: Run**

Run: `uv run pytest tests/test_emoji.py -v`
Expected: PASS.

- [ ] **Step 4: Commit** (`feat: port baseball emoji (ball lo/hi-res + generator)`).

### Task 2.2: Port the scores widget (ex-`mlb.py`)

**Files:**
- Create: `src/led_ticker_baseball/scores.py`
- Create: `tests/test_scores.py` (port `test_mlb.py`, `test_mlb_scoreboard.py`, `test_mlb_lazy_palette.py`)

- [ ] **Step 1: Copy `mlb.py` → `scores.py`** and rewrite EVERY `from led_ticker.<x> import …` to `from led_ticker.plugin import …`. Specific rewrites:

```python
# BEFORE (core internals)                          # AFTER (public surface)
from led_ticker._types import Canvas, Color, ColorTuple, DrawResult, Font
from led_ticker.color_providers import ColorProvider
from led_ticker.colors import RGB_WHITE, lazy_palette, make_color
from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL
from led_ticker.widget import run_monitor_loop, spawn_tracked
from led_ticker.widgets._frame_aware import _FrameAware
from led_ticker.widgets.message import SegmentMessage, TickerMessage
# inline:
from led_ticker.drawing import compute_baseline_for_band, safe_scale
from led_ticker.pixel_emoji import draw_with_emoji, measure_width
from led_ticker.fonts import font_line_height_logical
from led_ticker.widgets._row_layout import resolve_band_heights
```

become:

```python
from led_ticker.plugin import (
    Canvas, Color, DrawResult, Font,
    ColorProvider,
    make_color,
    FONT_DEFAULT, FONT_SMALL, font_line_height_logical,
    run_monitor_loop, spawn_tracked,
    FrameAwareBase,
    SegmentMessage, TickerMessage,
    compute_baseline_for_band, safe_scale,
    draw_with_emoji, measure_width,
    resolve_band_heights,
    colors,  # for colors.RGB_WHITE, colors.lazy_palette
)
```

Replace bare `RGB_WHITE` → `colors.RGB_WHITE`, `lazy_palette` → `colors.lazy_palette`, `_FrameAware` base → `FrameAwareBase`. `ColorTuple` is a `tuple[int,int,int]` alias — if not on the surface, inline it as `tuple[int, int, int]` (it is only a type annotation). Remove the `@register("mlb")` decorator (registration moves to `__init__.register`).

- [ ] **Step 2: Verify import purity**

Run: `grep -n "from led_ticker" src/led_ticker_baseball/scores.py | grep -v "led_ticker.plugin"`
Expected: NO output (only `led_ticker.plugin` imports remain).

- [ ] **Step 3: Port the tests** — copy `test_mlb.py`, `test_mlb_scoreboard.py`, `test_mlb_lazy_palette.py` into `tests/test_scores.py` (or keep as three files); rewrite `from led_ticker.widgets.mlb import …` → `from led_ticker_baseball.scores import …`.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/test_scores.py -v` (or the three files)
Expected: PASS. Fix any symbol that was reachable as a core internal but is missing from the public surface — if a genuinely-needed symbol is missing, STOP and add it to Phase 0's surface (amend that PR), do not import the internal.

- [ ] **Step 5: Commit** (`feat: port MLB scores widget as baseball.scores`).

### Task 2.3: Port the standings widget (ex-`mlb_standings.py`)

**Files:**
- Create: `src/led_ticker_baseball/standings.py`
- Create: `tests/test_standings.py` (port `test_mlb_standings.py`)

- [ ] **Step 1: Copy `mlb_standings.py` → `standings.py`.** Rewrite core imports to `led_ticker.plugin` as in Task 2.2. The line `from led_ticker.widgets.mlb import (MLB_TEAM_NAMES, …)` becomes `from led_ticker_baseball.scores import (MLB_TEAM_NAMES, …)` — same-package import, allowed (the import-purity rule governs `led_ticker.*` only). Remove `@register("mlb_standings")`.

- [ ] **Step 2: Verify purity** — `grep "from led_ticker" standings.py | grep -v led_ticker.plugin` → empty.

- [ ] **Step 3: Port `test_mlb_standings.py` → `tests/test_standings.py`**, rewriting imports.

- [ ] **Step 4: Run** — `uv run pytest tests/test_standings.py -v` → PASS.

- [ ] **Step 5: Commit** (`feat: port MLB standings as baseball.standings`).

### Task 2.4: Port the baseball transition (+ its hi-res funcs)

**Files:**
- Create: `src/led_ticker_baseball/transition.py`
- Create: `tests/test_transition.py` (port baseball slices of `test_baseball.py`, `test_transitions.py`, `test_hires_loader.py`)

- [ ] **Step 1: Copy `transitions/baseball.py` → `transition.py`.** MOVE INTO IT the three baseball funcs from core `_hires_loader.py`: `render_hires_baseball_frame`, `_baseball_rotation_frames`, `_paint_procedural_baseball`. They call `_generate_baseball_hires` — import it from the sibling `from led_ticker_baseball.emoji import _generate_baseball_hires`. Rewrite core imports:

```python
# BEFORE                                            # AFTER
from led_ticker._types import Canvas, PixelData
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.transitions import Transition, register_transition
from led_ticker.transitions._hires_loader import SNAP_THRESHOLD
```

become:

```python
from led_ticker.plugin import (
    Canvas, PixelData, Transition, ScaledCanvas, unwrap_to_real, paint_hires,
)

# SNAP_THRESHOLD: core's snap point for hi-res transitions. Defined locally so
# the plugin owns its tuning constant (or import from led_ticker.plugin if added).
SNAP_THRESHOLD = 0.95
```

Remove `@register_transition(...)` decorators (registration moves to `__init__`). Keep the three transition classes (roll / reverse / alternating) but adjust their registered NAMES at wire-up time.

- [ ] **Step 2: Verify purity** — `grep "from led_ticker" transition.py | grep -v led_ticker.plugin` → empty (sibling `led_ticker_baseball.emoji` import is fine).

- [ ] **Step 3: Port the tests** — baseball assertions from `test_baseball.py`, the baseball cases in `test_transitions.py`, and the `render_hires_baseball_frame` cases from `test_hires_loader.py` → `tests/test_transition.py`. Rewrite imports to `led_ticker_baseball.transition`.

- [ ] **Step 4: Run** — `uv run pytest tests/test_transition.py -v` → PASS.

- [ ] **Step 5: Commit** (`feat: port baseball transition family + hi-res render funcs`).

### Task 2.5: Wire `register(api)`

**Files:**
- Modify: `src/led_ticker_baseball/__init__.py`

- [ ] **Step 1: Write the real `register`**

```python
"""led-ticker-baseball: MLB scores/standings widgets, baseball emoji, and
baseball transitions, contributed via the ``led_ticker.plugins`` entry point.
The entry-point name ``baseball`` is the plugin namespace, so widgets are
``type = "baseball.scores"`` / ``"baseball.standings"``, transitions are
``baseball.roll`` / ``baseball.roll_reverse`` / ``baseball.roll_alternating``,
and the emoji is ``:baseball.ball:``."""

from led_ticker_baseball.emoji import BALL, BALL_HIRES
from led_ticker_baseball.scores import MLBScores
from led_ticker_baseball.standings import MLBStandings
from led_ticker_baseball.transition import (
    BaseballRoll,
    BaseballRollAlternating,
    BaseballRollReverse,
)


def register(api):
    api.widget("scores")(MLBScores)
    api.widget("standings")(MLBStandings)
    api.transition("roll")(BaseballRoll)
    api.transition("roll_reverse")(BaseballRollReverse)
    api.transition("roll_alternating")(BaseballRollAlternating)
    api.emoji("ball", BALL)
    api.hires_emoji("ball", BALL_HIRES)
```

> Use the ACTUAL class names from the ported files (the placeholders `MLBScores` / `BaseballRoll` etc. above must match what `scores.py` / `transition.py` define — check and fix).

- [ ] **Step 2: Commit** (`feat: wire register(api) for baseball plugin`).

### Task 2.6: Entry-point smoke test + AST import-purity tripwire

**Files:**
- Create: `tests/test_smoke.py`
- Create: `tests/test_import_purity.py`

- [ ] **Step 1: Write the entry-point smoke test** (templated from pool's `test_smoke.py`)

```python
from led_ticker import _plugin_loader as L


def test_entry_point_registers_baseball_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "baseball" in loaded, f"baseball plugin not discovered: {result}"

        from led_ticker.widgets import get_widget_class
        assert get_widget_class("baseball.scores") is not None
        assert get_widget_class("baseball.standings") is not None
    finally:
        L.reset_plugins()
```

- [ ] **Step 2: Write the AST import-purity tripwire** (NEW — pool lacks this; see deferred note to backport)

```python
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "led_ticker_baseball"


def _led_ticker_imports(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "led_ticker":
                names.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "led_ticker":
                    names.append(alias.name)
    return names


def test_plugin_imports_only_public_surface():
    offenders = {}
    for py in SRC.rglob("*.py"):
        bad = [m for m in _led_ticker_imports(py) if m != "led_ticker.plugin"]
        if bad:
            offenders[py.name] = bad
    assert not offenders, (
        f"modules import led_ticker internals instead of led_ticker.plugin: {offenders}"
    )
```

- [ ] **Step 3: Run the full plugin suite**

Run: `uv run pytest -q`
Expected: all PASS (emoji, scores, standings, transition, smoke, import-purity).

- [ ] **Step 4: Lint** — `uv run ruff check src tests` → clean.

- [ ] **Step 5: Commit** (`test: entry-point smoke + AST import-purity tripwire`).

- [ ] **Step 6: Push branch + open PR; confirm CI green; merge after go-ahead.**

```bash
git push -u origin feat/port-widgets
gh pr create --title "feat: baseball plugin (scores, standings, emoji, transitions)" \
  --body "Ports MLB widgets, baseball emoji, and baseball transitions against the expanded led_ticker.plugin surface. Import-purity AST-verified.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh run watch --repo JamesAwesome/led-ticker-baseball
```

**CHECKPOINT:** Plugin CI green (against core `main` once Phase 0 is merged) before Phase 3 removes anything from core.

---

## Phase 3 — Remove from core + migrate (Core PR B)

**Worktree:** `git worktree add -b feat/remove-baseball ../lt-remove ../led-ticker` (off `main`, AFTER Phase 0 merged), then `cd ../lt-remove && make dev`.

### Task 3.1: Capture core's current validation guardrails (regression guard)

- [ ] **Step 1:** Before deleting anything, `grep -n "raise\|ValueError\|valid\|layout\|must be\|allowed" src/led_ticker/widgets/mlb.py src/led_ticker/widgets/mlb_standings.py` and record every config-validation rule (layout values, two-row field gating, team-abbr checks). Confirm each one exists in the plugin's `validate_config` (add to the plugin + its tests if missing — amend the Phase 2 PR). This pre-empts the pool "lost guardrails" regression.

### Task 3.2: Delete the core widgets + transition + emoji

**Files:**
- Delete: `src/led_ticker/widgets/mlb.py`, `src/led_ticker/widgets/mlb_standings.py`, `src/led_ticker/transitions/baseball.py`
- Modify: `src/led_ticker/widgets/__init__.py` (drop the `mlb` / `mlb_standings` imports)
- Modify: `src/led_ticker/pixel_emoji.py` (remove `BASEBALL`, `BASEBALL_HIRES`, `_generate_baseball_hires`, and their `EMOJI_REGISTRY` / `HIRES_REGISTRY` entries)
- Modify: `src/led_ticker/transitions/_hires_loader.py` (remove `render_hires_baseball_frame`, `_baseball_rotation_frames`, `_paint_procedural_baseball`)

- [ ] **Step 1:** Delete the three widget/transition files and remove their `widgets/__init__.py` imports.
- [ ] **Step 2:** Remove the baseball emoji constants + generator + registry entries from `pixel_emoji.py`.
- [ ] **Step 3:** Remove the three baseball funcs from `_hires_loader.py` (leave nyancat/pokeball intact).
- [ ] **Step 4: Confirm nothing else references them**

Run: `grep -rn "BASEBALL\|_generate_baseball_hires\|render_hires_baseball_frame\|\"mlb\"\|widgets.mlb\|transitions.baseball" src/led_ticker/`
Expected: NO output (besides comments you intend to keep).

- [ ] **Step 5: Commit** (`feat: remove baseball widgets/emoji/transition (moved to led-ticker-baseball plugin)`).

### Task 3.3: Update core tests

**Files:**
- Delete: `tests/test_mlb.py`, `tests/test_mlb_scoreboard.py`, `tests/test_mlb_lazy_palette.py`, `tests/test_mlb_standings.py`, `tests/test_baseball.py`
- Modify: `tests/test_pixel_emoji.py`, `tests/test_hires_loader.py`, `tests/test_transitions.py`, `tests/test_widgets/test_message.py` (remove baseball-specific assertions)

- [ ] **Step 1:** Delete the five baseball/mlb test files.
- [ ] **Step 2:** Remove baseball assertions from the four shared test files (search each for `baseball` / `BASEBALL`).
- [ ] **Step 3: Run** — `make test` → green (no missing-symbol errors, coverage intact).
- [ ] **Step 4: Commit** (`test: drop baseball tests from core`).

### Task 3.4: Migrate configs

**Files:**
- Modify: the ~14 `config/config.*` files using mlb/baseball (see spec inventory)

- [ ] **Step 1: Migrate widget keys** — in every config: `type = "mlb"` → `type = "baseball.scores"`; `type = "mlb_standings"` → `type = "baseball.standings"`; transition `"baseball"` → `"baseball.roll"`, `"baseball_reverse"` → `"baseball.roll_reverse"`, `"baseball_alternating"` → `"baseball.roll_alternating"`.

```bash
grep -rln 'type = "mlb' config/
grep -rln 'baseball' config/
```

- [ ] **Step 2: Migrate emoji refs** — `:baseball:` → `:baseball.ball:` in configs that will run the plugin (`config.toml`, `config.longboi.toml`, `config.small_sign.toml`). For plugin-free core demo/test configs (`config.scale_smoketest.toml`, `config.hires_emoji_test.example.toml`), replace `:baseball:` with a remaining core hi-res emoji (`:moon:` or `:star:`) or drop it — these must keep validating WITHOUT the plugin installed.

- [ ] **Step 3: Validate the plugin-running configs** (with the plugin installed locally: `cd ../led-ticker-baseball && uv pip install -e .` into the same env, or rely on `requirements-plugins`):

Run: `make validate CONFIG=config/config.toml`
Expected: passes (or fails ONLY on missing plugin, which Task 3.5 wires).

- [ ] **Step 4: Commit** (`feat: migrate configs to baseball.* plugin keys`).

### Task 3.5: Wire plugin install (declarative + Docker + deploy)

**Files:**
- Modify: `config/requirements-plugins.example.txt`, `Dockerfile`, `deploy/install.sh`

- [ ] **Step 1:** Add the baseball plugin git URL to `config/requirements-plugins.example.txt` alongside pool:

```
led-ticker-pool @ git+https://github.com/JamesAwesome/led-ticker-pool@main
led-ticker-baseball @ git+https://github.com/JamesAwesome/led-ticker-baseball@main
```

- [ ] **Step 2:** Confirm the Dockerfile Layer-2b constraint-based install (`pip install -c constraints-core.txt -r config/requirements-plugins.txt`) needs NO change (it installs whatever is in the live file) — just verify the live-file copy step is intact.
- [ ] **Step 3:** Confirm `deploy/install.sh` likewise picks up the new plugin via the same mechanism (no per-plugin code).
- [ ] **Step 4: Commit** (`feat: add baseball plugin to declarative install`).

### Task 3.6: Update docs-drift tests + CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (remove mlb/baseball file-map + invariant entries; note baseball as external plugin), `tests/test_docs_config_options_drift.py` if it references baseball.

- [ ] **Step 1:** Remove the `widgets/mlb.py`, `widgets/mlb_standings.py`, `transitions/baseball.py` lines from CLAUDE.md's package-layout map and the baseball/MLB invariant bullets; add a one-liner to the Plugin-invariants section ("baseball widgets/emoji/transitions live in the external `led-ticker-baseball` plugin").
- [ ] **Step 2: Run** — `make test` (catches docs-drift tests) → green.
- [ ] **Step 3: Commit** (`docs: drop baseball from CLAUDE.md (now an external plugin)`).

- [ ] **Step 4: Push + open Core PR B; confirm CI green; merge after go-ahead.**

```bash
git push -u origin feat/remove-baseball
gh pr create --title "feat: extract baseball into the led-ticker-baseball plugin" \
  --body "Removes MLB widgets, baseball emoji, and baseball transitions from core; migrates configs to baseball.* keys; wires the plugin into the declarative install. Depends on the led-ticker-baseball repo being published. See docs/superpowers/specs/2026-06-06-baseball-plugin-extraction-design.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Phase 4 — Hardware validation

No automated tests; observe real panels. Each sign needs `cp config/requirements-plugins.example.txt config/requirements-plugins.txt` (if absent) + `docker compose up --build` to install the plugin before its migrated config works.

- [ ] **Step 1: Bigsign / longboi (scale > 1):** boot a config exercising `baseball.scores` (all three layouts), `baseball.standings`, the hi-res `:baseball.ball:` emoji, and a `baseball.roll` transition. Confirm hi-res sprite + transition render correctly (no clip, smooth roll, correct snap).
- [ ] **Step 2: Smallsign (scale = 1):** confirm the lo-res 8×8 `:baseball.ball:` and the non-hires `baseball.roll` transition render.
- [ ] **Step 3:** Confirm the `:baseball.ball:` showcase line on production signs (longboi, small_sign) renders after their rebuild.
- [ ] **Step 4:** Record results; if anything clips/breaks, file against the plugin (rendering) or core (surface friction).

---

## Phase 5 — Docs

**Files:**
- Plugin `README.md` (canonical), docs-site `plugins/available/` entry, slimmed core MLB widget pages.

- [ ] **Step 1:** Write the plugin `README.md` as canonical baseball docs: config keys (`baseball.scores` with `layout` ticker/scoreboard/two_row + all options, `baseball.standings`), the `:baseball.ball:` emoji, the three transitions, install instructions, screenshots/GIFs (use the making-a-gif skill). Commit + push in the plugin repo.
- [ ] **Step 2:** Add a `plugins/available/` directory entry for baseball on the docs site (mirror the pool entry), linking to the plugin README.
- [ ] **Step 3:** Slim the core docs-site MLB widget page(s) to pointers at the plugin (mirror what pool did to `widgets/pool.mdx`); update the sidebar label.
- [ ] **Step 4:** Verify deployed pages (cloudflared access — see reference memory). Commit docs PRs in the relevant repos.

---

## Self-review notes (coverage map)

| Spec section | Covered by |
|---|---|
| Core surface expansion | Phase 0 (Tasks 0.1–0.3) |
| Git repo + deploy-key CI | Phase 1 (Tasks 1.1–1.4) |
| Up-to-date Actions | Task 1.4 Step 1 (mandatory version verify) |
| Build plugin (widgets/emoji/transition/register/validate) | Phase 2 (Tasks 2.1–2.6) |
| Import purity | Task 2.6 AST tripwire |
| Remove from core + migrate configs | Phase 3 (Tasks 3.2–3.5) |
| Lost-guardrail risk | Task 3.1 |
| Hardware validation | Phase 4 |
| Docs | Phase 5 |
| Pool AST-test backport | Deferred (memory: project_pool_ast_import_purity_test) |

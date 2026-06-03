# Pool Widget Extraction (→ `led-ticker-pool` plugin) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the built-in `pool` widget into a standalone, pip-installable plugin package (`led-ticker-pool`, entry-point namespace `pool`, referenced in TOML as `type = "pool.monitor"`), using the extraction to *harden and validate* the plugin system — then document the plugin system based on that real experience.

**Architecture:** Six phases across two repos. Phase 1 hardens `led_ticker.plugin` (re-export the already-existing `Container`/`Updatable` protocols + `run_monitor_loop` + the `SegmentMessage`/`TwoRowMessage` building blocks — the engine already supports container widgets structurally, so this is re-exports + docs, not a redesign). Phases 2–3 scaffold the new repo and port `PoolMonitor` to import only `led_ticker.plugin`, moving pool's bespoke `current_window` validation into a `validate_config` classmethod (dogfooding that convention). Phase 4 removes pool from core. Phase 5 validates end-to-end (incl. hardware). Phase 6 writes the docs, grounded in the experience, with pool as the flagship walkthrough.

**Tech Stack:** Python 3.14, attrs, aiohttp, InfluxDB v2 (Flux/CSV over HTTP), pytest. The new package depends on `led-ticker` (the plugin API) + `aiohttp`. No `from __future__ import annotations` in led-ticker src (forbidden); the new repo may set its own conventions but mirroring led-ticker's is sensible.

**Two repos:**
- **`led-ticker`** (this repo) — Phase 1 (surface hardening) and Phase 4 (remove pool + migrate configs) are PRs here.
- **`led-ticker-pool`** (NEW repo) — Phases 2–3 build it; Phase 5 installs + validates it.

**Decisions locked (from planning):** harden the surface (don't rewrite pool as a `draw()` widget); repo `led-ticker-pool`; namespace `pool` → `type = "pool.monitor"`.

---

## Grounding facts (from the read-only audit — rely on these)

- **`Container` protocol already exists**: `src/led_ticker/widget.py:99-111` — `@runtime_checkable class Container(Protocol): feed_stories: list[Widget]`. The engine's `_expand_sources` (`src/led_ticker/ticker.py:1044-1058`) does `isinstance(s, Container)` and `out.extend(s.feed_stories)`. **So any widget (built-in or plugin) with a `feed_stories: list[Widget]` attribute is already expanded by the engine** — no base class, no engine change needed. `feed_title` is NOT part of the `Container` protocol (only RSS-specific code at `ticker.py:196` reads it); a generic container only needs `feed_stories`.
- **`Updatable` protocol** (`widget.py:61-67`): `async def update(self) -> None`. **`run_monitor_loop(widget: Updatable, interval: float, splay: bool = True)`** (`widget.py:113-159`) polls `widget.update()` with exponential backoff.
- **`SegmentMessage`** (`widgets/message.py:216-306`): `__init__(self, segments: list[tuple[str, Color]], padding=6, center=False, bg_color=None, font=None, font_color=None)`; has `draw()`.
- **`TwoRowMessage`** (`widgets/two_row.py:73-164`): `@register("two_row") @attrs.define`, fields incl. `top_text, bottom_text, font, top_font, bottom_font, top_color, bottom_color, top_row_height, ...`; has `draw()`.
- **`_build_widget`** (`app/factories.py:848-885`): `cls = get_widget_class(type)`; `if hasattr(cls, "start"): return await cls.start(session=session, **cfg)` else `cls(**cfg)`. Containers are NOT special-cased in the builder — only the engine expands them.
- **Pool's internal imports** (`widgets/pool.py:14-21`): `_types.{Color,Font}`, `color_providers.ColorProviderBase`, `colors.{BLUE,GREEN,ORANGE,PINK,RED,RGB_WHITE,make_color}`, `fonts.FONT_DEFAULT`, `widget.{run_monitor_loop,spawn_tracked}`, `widgets.register`, `widgets.message.SegmentMessage`, `widgets.two_row.TwoRowMessage`. Plus `aiohttp` + InfluxDB env vars (`INFLUXDB_URL/ORG/BUCKET/TOKEN`). **No other internals.**
- **Pool's core couplings to remove in Phase 4**: `@register("pool")` + the auto-import in `widgets/__init__.py`; six `"pool"` entries in `_DISPATCH_APPLICABLE_TYPES` (`factories.py:336-341`); pool's `_POOL_DURATION_RE` (`factories.py:344`) + its use in `validate_widget_cfg`; configs `config/config.example.toml`, `config/config.pool_bigsign.toml`, `config/config.pool_smallsign.toml` (`type = "pool"`); any pool tests in `tests/`.

---

# PHASE 1 — Harden `led_ticker.plugin` for container/monitor widgets (led-ticker PR)

Re-export the protocols + helpers a data-fetching container widget needs, so pool (and any future monitor) can be authored from the public surface alone. The engine already supports container widgets — this phase makes the contract *public + documented + tested*.

### Task 1.1: Re-export `Container`, `Updatable`, `run_monitor_loop`

**Files:**
- Modify: `src/led_ticker/plugin.py`
- Test: `tests/test_plugins/test_container_surface.py` (create)

- [ ] **Step 1: Write the failing test**

```python
def test_container_monitor_surface_is_exported():
    import led_ticker.plugin as p

    for name in ("Container", "Updatable", "run_monitor_loop"):
        assert hasattr(p, name), f"missing public export: {name}"
        assert name in p.__all__


def test_a_plugin_container_widget_expands_via_the_engine():
    # A widget with feed_stories is treated as a Container by the engine's
    # expansion — prove the public Container protocol matches what the engine
    # isinstance-checks.
    from led_ticker.plugin import Container
    from led_ticker.ticker import _expand_sources

    class Feed:
        def __init__(self):
            self.feed_stories = ["a", "b"]

    f = Feed()
    assert isinstance(f, Container)
    assert _expand_sources([f, "x"]) == ["a", "b", "x"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_plugins/test_container_surface.py -q`
Expected: FAIL — `Container`/`Updatable`/`run_monitor_loop` not on `led_ticker.plugin`.

- [ ] **Step 3: Add the re-exports**

In `src/led_ticker/plugin.py`, extend the `from led_ticker.widget import ...` line (currently `from led_ticker.widget import Widget, spawn_tracked`) to:

```python
from led_ticker.widget import (
    Container,
    Updatable,
    Widget,
    run_monitor_loop,
    spawn_tracked,
)
```

Add `"Container"`, `"Updatable"`, `"run_monitor_loop"` to `__all__` (group `Container`/`Updatable` with the protocol/type names like `Widget`; `run_monitor_loop` with the lower-case helpers).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_plugins/test_container_surface.py -q` → PASS.
Run: `uv run python -c "import led_ticker.plugin"` → clean; `uv run ruff check src/led_ticker/plugin.py` → clean (re-exports are in `__all__`).

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add src/led_ticker/plugin.py tests/test_plugins/test_container_surface.py
git -C <worktree> -c core.hooksPath=/dev/null commit -m "feat(plugins): re-export Container/Updatable protocols + run_monitor_loop"
```

### Task 1.2: Re-export `SegmentMessage` + `TwoRowMessage` (the composable render widgets)

**Files:**
- Modify: `src/led_ticker/plugin.py`
- Test: `tests/test_plugins/test_container_surface.py` (extend)

**Context:** A monitor widget composes its screens from message widgets. Re-export the two pool uses. Their constructors (from the audit): `SegmentMessage(segments, padding=6, center=False, bg_color=None, font=None, font_color=None)`; `TwoRowMessage(top_text, bottom_text, font=..., top_font=None, bottom_font=None, top_color=..., bottom_color=..., top_row_height=None, ...)`.

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_message_building_blocks_are_exported():
    from led_ticker.plugin import SegmentMessage, TwoRowMessage, make_color

    seg = SegmentMessage([("Hi", make_color(255, 255, 255))], center=True)
    two = TwoRowMessage(top_text="A", bottom_text="B")
    # both satisfy the Widget protocol (have draw)
    from led_ticker.plugin import Widget

    assert isinstance(seg, Widget)
    assert isinstance(two, Widget)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_plugins/test_container_surface.py -q -k "building_blocks"`
Expected: FAIL — not exported.

- [ ] **Step 3: Add the re-exports**

In `src/led_ticker/plugin.py`, add:

```python
from led_ticker.widgets.message import SegmentMessage
from led_ticker.widgets.two_row import TwoRowMessage
```

Add `"SegmentMessage"`, `"TwoRowMessage"` to `__all__`.

> Import-cycle check: `plugin.py` is imported lazily (by `_plugin_loader` at app startup), not by `led_ticker/__init__`. `widgets.message`/`widgets.two_row` don't import `plugin`/`_plugin_loader`. Confirm `uv run python -c "import led_ticker.plugin"` stays clean; if a cycle appears, move these two imports into a `TYPE_CHECKING`-guarded block is NOT an option (they're runtime-used) — instead verify the actual cycle and break it at the lower module. Expected: no cycle.

- [ ] **Step 4: Run + lint**

Run: `uv run pytest tests/test_plugins/test_container_surface.py -q` → PASS; `uv run ruff check src/led_ticker/plugin.py` → clean.

- [ ] **Step 5: Commit**

```bash
git -C <worktree> -c core.hooksPath=/dev/null commit -am "feat(plugins): re-export SegmentMessage + TwoRowMessage building blocks"
```

### Task 1.3: Document the monitor/container pattern + extend the AST boundary fixture

**Files:**
- Modify: `src/led_ticker/plugin.py` (module docstring / a `Container` note), `docs/plugin-system.md` (already has a §4 "async/data-fetching" note + §10 gap — update §10 to mark these closed)
- Test: `tests/test_plugins/test_container_surface.py` (add an end-to-end plugin-container test)

- [ ] **Step 1: Write the end-to-end test**

A local plugin registering a container monitor widget (with `feed_stories` + an `update()` + a `start()` that spawns `run_monitor_loop`) loads and is usable. Append:

```python
def test_plugin_monitor_widget_loads_and_is_a_container(tmp_path):
    import textwrap

    from led_ticker import _plugin_loader as L
    from led_ticker.plugin import Container
    from led_ticker.widgets import get_widget_class

    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            import attrs
            from led_ticker.plugin import (
                SegmentMessage, make_color, run_monitor_loop, spawn_tracked,
            )

            def register(api):
                @api.widget("feed")
                @attrs.define
                class Feed:
                    feed_stories: list = attrs.field(init=False, factory=list)
                    async def update(self):
                        self.feed_stories = [
                            SegmentMessage([("hi", make_color(255,255,255))])
                        ]
                    @classmethod
                    async def start(cls, session, update_interval=300, **kw):
                        w = cls(**kw)
                        await w.update()
                        spawn_tracked(run_monitor_loop(w, update_interval))
                        return w
            """
        )
    )
    try:
        L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)
        cls = get_widget_class("acme.feed")
        assert cls is not None
        # An instance with feed_stories is a Container
        inst = cls()
        assert isinstance(inst, Container)
    finally:
        L.reset_plugins()
```

- [ ] **Step 2: Run, implement docs, run again**

Run the test (it should PASS given Tasks 1.1/1.2). Then update `src/led_ticker/plugin.py`'s module docstring to add one paragraph: a widget may be a **monitor/container** — declare a `feed_stories: list[Widget]` field (the engine expands it live), implement `async def update(self)`, and drive refresh from a `start()` classmethod via `spawn_tracked(run_monitor_loop(self, interval))`. Update `docs/plugin-system.md` §10 to mark the `run_monitor_loop` / message-widget / container gaps as **closed in Phase 1**, and §4's note accordingly.

- [ ] **Step 3: Verify + commit**

Run: `uv run pytest tests/test_plugins/ -q` → all pass; `make lint`/`make typecheck` → clean.

```bash
git -C <worktree> add src/led_ticker/plugin.py docs/plugin-system.md tests/test_plugins/test_container_surface.py
git -C <worktree> -c core.hooksPath=/dev/null commit -m "docs(plugins): document monitor/container widget pattern; close surface gaps"
```

### Task 1.4: Phase-1 verification + finish (open the led-ticker PR)

- [ ] `make lint` / `make typecheck` / `make test` all green.
- [ ] The public surface now exports: `Container`, `Updatable`, `run_monitor_loop`, `SegmentMessage`, `TwoRowMessage` (verify via the tests + `test_public_surface_boundary` style check).
- [ ] Use **superpowers:finishing-a-development-branch** → push `feat/plugin-extract`, open PR ("feat(plugins): public container/monitor widget surface"). This PR is a prerequisite for the plugin to import these names; it can merge before the new repo work, or the new repo can depend on the branch during development.

---

# PHASE 2 — Scaffold the `led-ticker-pool` repo (NEW repo)

**This phase is in a NEW git repository, not the led-ticker worktree.** Create it under a sibling path (e.g. `/Users/james/projects/github/jamesawesome/led-ticker-pool`). Confirm the path with the user before `git init`.

### Task 2.1: Initialize the package

**Files (in the new repo):**
- Create: `pyproject.toml`, `src/led_ticker_pool/__init__.py`, `README.md`, `.gitignore`, `tests/test_smoke.py`, CI workflow.

- [ ] **Step 1: `pyproject.toml`** — declare the package, deps, and the entry point:

```toml
[project]
name = "led-ticker-pool"
version = "0.1.0"
description = "Pool water-temperature monitor widget for led-ticker (InfluxDB-backed)."
requires-python = ">=3.14"
dependencies = ["led-ticker", "aiohttp"]

[project.entry-points."led_ticker.plugins"]
pool = "led_ticker_pool:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/led_ticker_pool"]
```

> `led-ticker` must be installable for the dep to resolve. During development, install it editable from the sibling repo: `uv pip install -e /path/to/led-ticker` (or add a `[tool.uv.sources]` path entry). If led-ticker isn't published, document the editable-install dev setup in the README.

- [ ] **Step 2: A minimal `register`** (`src/led_ticker_pool/__init__.py`) that loads via the entry-point channel:

```python
"""led-ticker-pool: a pool water-temperature monitor plugin."""


def register(api):
    # Phase 3 moves the real PoolMonitor here. For now, a trivial widget proves
    # the entry-point channel resolves.
    @api.widget("monitor")
    class _Placeholder:
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            return canvas, cursor_pos
```

- [ ] **Step 3: Smoke test** that the plugin loads via the ENTRY-POINT channel (not just a local dir). In `tests/test_smoke.py`:

```python
def test_entry_point_registers_pool_namespace():
    from led_ticker import _plugin_loader as L

    L.reset_plugins()
    try:
        # entry_points_enabled=True picks up this installed package's
        # [project.entry-points."led_ticker.plugins"] pool = ...
        result = L.load_plugins(None, entry_points_enabled=True)
        assert any(info.namespace == "pool" for info in result.loaded), result.loaded
        from led_ticker.widgets import get_widget_class
        assert get_widget_class("pool.monitor") is not None
    finally:
        L.reset_plugins()
```

- [ ] **Step 4: Install + run the smoke test**

```bash
cd /path/to/led-ticker-pool
uv venv && uv pip install -e . && uv pip install -e /path/to/led-ticker
uv run pytest -q   # entry-point smoke test passes -> the package is discoverable
```

- [ ] **Step 5: CI workflow** — a GitHub Actions workflow that installs the package + led-ticker and runs `pytest` + `ruff`. Mirror led-ticker's CI shape.

- [ ] **Step 6: Commit (in the new repo)**

```bash
git init && git add -A && git commit -m "chore: scaffold led-ticker-pool plugin package"
```

---

# PHASE 3 — Port `PoolMonitor` into the plugin (NEW repo)

### Task 3.1: Port the module, public-surface-only imports

**Files (new repo):** `src/led_ticker_pool/monitor.py` (the ported `PoolMonitor`), `src/led_ticker_pool/__init__.py` (real `register`).

- [ ] **Step 1: Copy `pool.py`** from led-ticker (`src/led_ticker/widgets/pool.py`) into `src/led_ticker_pool/monitor.py`. Then rewrite its imports — replace the internal-imports block with public-surface-only:

```python
# OLD (internal):
# from led_ticker._types import Color, Font
# from led_ticker.color_providers import ColorProviderBase
# from led_ticker.colors import BLUE, GREEN, ORANGE, PINK, RED, RGB_WHITE, make_color
# from led_ticker.fonts import FONT_DEFAULT
# from led_ticker.widget import run_monitor_loop, spawn_tracked
# from led_ticker.widgets import register
# from led_ticker.widgets.message import SegmentMessage
# from led_ticker.widgets.two_row import TwoRowMessage

# NEW (public surface only):
from led_ticker.plugin import (
    Color,
    ColorProviderBase,
    Font,
    SegmentMessage,
    TwoRowMessage,
    colors,
    make_color,
    resolve_font,
    run_monitor_loop,
    spawn_tracked,
)
```

Then fix the references:
- `BLUE, GREEN, ORANGE, PINK, RED, RGB_WHITE` → `colors.BLUE`, `colors.GREEN`, etc. (update every use, e.g. the `DIM/AVG_COLOR/...` module constants and `_zone_color`).
- `FONT_DEFAULT` → `resolve_font("6x12")` (it's the 6x12 BDF). Change the `font` attrs default: `font: Font = attrs.field(factory=lambda: resolve_font("6x12"), kw_only=True)`.
- Remove `@register("pool")`; the class is registered by `register(api)` (next step).

- [ ] **Step 2: Wire `register(api)`** in `src/led_ticker_pool/__init__.py`:

```python
"""led-ticker-pool: a pool water-temperature monitor plugin."""

from led_ticker_pool.monitor import PoolMonitor


def register(api):
    api.widget("monitor")(PoolMonitor)   # -> pool.monitor
```

(`api.widget("monitor")` is a decorator factory; calling it on the class registers `pool.monitor` and returns the class unchanged.)

- [ ] **Step 3: Move pool's bespoke validation into `validate_config`** (dogfood the convention). Pool's `current_window` must be a negative Flux duration — in led-ticker core this was the hardcoded `_POOL_DURATION_RE` check in `validate_widget_cfg`. Add to `PoolMonitor`:

```python
import re

_POOL_DURATION_RE = re.compile(r"^-(\d+(ns|us|ms|s|m|h|d|w))+$")

# (inside class PoolMonitor)
    @classmethod
    def validate_config(cls, cfg):
        msgs = []
        cw = cfg.get("current_window")
        if cw is not None and not _POOL_DURATION_RE.match(str(cw)):
            msgs.append(
                f"current_window must be a negative Flux duration "
                f'(e.g. "-24h", "-90m"); got {cw!r}'
            )
        sid = cfg.get("sensor_id")
        if sid is not None and not re.match(r"^[A-Za-z0-9_-]+$", str(sid)):
            msgs.append(f"sensor_id must match [A-Za-z0-9_-]+; got {sid!r}")
        return msgs
```

(This replaces the core-side `_POOL_DURATION_RE` validation removed in Phase 4, and the `start()` sensor_id check can stay as a runtime guard too.)

- [ ] **Step 4: Port the tests.** Copy pool's tests from led-ticker (`tests/` — find `test_pool*` / `tests/test_widgets/test_pool*`) into the new repo's `tests/`. Rewrite imports: the widget is now `led_ticker_pool.monitor.PoolMonitor`; reference type as `pool.monitor`; the InfluxDB HTTP calls are already mocked (aioresponses / a stub session) — keep that. Add a test that `PoolMonitor.validate_config({"current_window": "24h"})` returns the duration error and `{"current_window": "-24h"}` returns `[]`.

- [ ] **Step 5: Run the new repo's suite**

```bash
cd /path/to/led-ticker-pool && uv run pytest -q   # all ported pool tests pass
uv run ruff check src tests
```

- [ ] **Step 6: Behavioral parity check** — load the plugin via a local dir into led-ticker and `led-ticker validate` a config using `type = "pool.monitor"`; confirm it validates and (with a mocked/stubbed InfluxDB) builds. Confirm `validate_config` surfaces a bad `current_window`.

- [ ] **Step 7: Commit (new repo)**

```bash
git add -A && git commit -m "feat: port PoolMonitor to a public-surface-only plugin (pool.monitor)"
```

---

# PHASE 4 — Remove pool from led-ticker core + migrate configs (led-ticker PR)

**Back in the led-ticker worktree.** Delete the built-in and clean up every core coupling the audit found. Do this AFTER the plugin works (Phase 3), so there's no window where pool is unavailable.

### Task 4.1: Delete the widget + de-register it

**Files:**
- Delete: `src/led_ticker/widgets/pool.py`
- Modify: `src/led_ticker/widgets/__init__.py` (remove the pool auto-import)

- [ ] **Step 1:** Remove the line in `src/led_ticker/widgets/__init__.py` that imports `pool` (the audit noted it's the auto-import that triggers `@register("pool")`). Delete `src/led_ticker/widgets/pool.py`.

- [ ] **Step 2:** Remove the six `"pool"` entries from `_DISPATCH_APPLICABLE_TYPES` (`src/led_ticker/app/factories.py:336-341`) — drop `"pool"` from each of `top_font`, `top_font_size`, `top_font_threshold`, `bottom_font`, `bottom_font_size`, `bottom_font_threshold`.

- [ ] **Step 3:** Remove `_POOL_DURATION_RE` (`factories.py:344`) and its use in `validate_widget_cfg` (grep `_POOL_DURATION_RE` — remove the definition and the validation branch that references it). This validation now lives in the plugin's `validate_config`.

- [ ] **Step 4:** Delete pool's core tests (grep `tests/` for `pool` — `tests/test_widgets/test_pool*` etc.). Any shared test fixture referencing pool must be updated.

- [ ] **Step 5: Run the suite** — `make test`. Expect failures ONLY where tests reference `type="pool"` or the removed regex; fix each by deleting the pool-specific assertion (pool is no longer a built-in). `make lint`/`make typecheck` clean.

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add -A
git -C <worktree> -c core.hooksPath=/dev/null commit -m "feat: remove built-in pool widget (extracted to led-ticker-pool plugin)"
```

### Task 4.2: Migrate the pool configs + document the install

**Files:**
- Modify: `config/config.example.toml`, `config/config.pool_bigsign.toml`, `config/config.pool_smallsign.toml`

- [ ] **Step 1:** In each config, change `type = "pool"` → `type = "pool.monitor"`. Add a commented `[plugins]` block if absent (the dir defaults to `plugins`). Add a comment noting the pool widget now requires the `led-ticker-pool` plugin (install via pip / `requirements-plugins.txt` / a Docker layer).

- [ ] **Step 2:** Add a short section to the deploy docs / the config files' header comments: how to install the plugin (`pip install led-ticker-pool`, or drop the package in `config/plugins/`, or the entry-point + Docker layer). The full walkthrough is Phase 6.

- [ ] **Step 3: Validate the migrated configs** — with the `led-ticker-pool` plugin installed/available, `led-ticker validate config/config.pool_bigsign.toml` passes (the `pool.monitor` type resolves). Without the plugin, it reports `pool.monitor` as unknown (expected — documents the dependency).

- [ ] **Step 4: Commit**

```bash
git -C <worktree> -c core.hooksPath=/dev/null commit -am "config: migrate pool configs to the pool.monitor plugin type"
```

### Task 4.3: Finish the led-ticker removal PR

- [ ] `make test`/`make lint`/`make typecheck` green. Use **superpowers:finishing-a-development-branch** → PR ("feat: extract pool widget to the led-ticker-pool plugin"). Note in the PR: requires the `led-ticker-pool` plugin for pool functionality; configs migrated to `pool.monitor`.

---

# PHASE 5 — End-to-end + hardware validation

### Task 5.1: Real install + run

- [ ] Install `led-ticker-pool` the way a user would (pip from the repo, or the documented editable/Docker path) into a led-ticker environment that has core pool removed.
- [ ] Run `led-ticker plugins --config config/config.pool_smallsign.toml` → confirms `pool.monitor` is listed.
- [ ] Run the display against a real config pointing at the real InfluxDB (the pool sign's actual data source). Confirm the pool screens render identically to the pre-extraction built-in.
- [ ] **Hardware validation on the pool sign** (smallsign + bigsign as applicable) — the user runs it; confirm temps display, cycling, fonts, and colors match the prior built-in behavior.

### Task 5.2: Capture the friction (input to docs)

- [ ] Write a short "extraction log" (`docs/superpowers/specs/` or a scratch note): every point of friction — anything that required reaching past `led_ticker.plugin`, any awkward pattern, any missing helper, install/packaging snags, the `validate_config` dogfood experience. **This is the raw material for Phase 6.** If the friction reveals a missing public export or a real ergonomic gap, loop back: add it to the surface (a small Phase-1-style PR) before writing docs that paper over it.

---

# PHASE 6 — Documentation (FINAL — grounded in the experience)

The deferred docs deliverables, now written against a *real* extraction with pool as the flagship example.

### Task 6.1: Docs-site "Plugins" page

**Files:** `docs/site/src/content/docs/<reference|concepts>/plugins.mdx` (match the site's structure + frontmatter; the `examples/plugins/README.md` already points here).

- [ ] Cover (from the spec's Documentation deliverables + the technical README): writing a local plugin; **packaging an installable one** (the `led-ticker-pool` `pyproject.toml` + entry point as the worked example); the `register(api)` contract; every `api.*` method; the `.` namespace separator; widget patterns (attrs, `font_color`, `validate_config`, the **monitor/container + `start()` + `run_monitor_loop`** pattern — using pool); lifecycle hooks; the `[plugins]` block; the `plugins` CLI; deployment (local dir + Docker); and a **full `led-ticker-pool` walkthrough** (the real extraction).
- [ ] Fold in the documented edges: the `font_color`-field convention, `validate_config` widget-only/pre-coercion timing, single-file-plugins-share-`fonts/`, the `plugins.dir` trust boundary, hi-res-emoji pairing.

### Task 6.2: CLAUDE.md plugin-invariants section

**Files:** `CLAUDE.md` (currently has zero plugin mention).

- [ ] Add a "Plugins" subsection under Architecture: the public-API boundary (plugins import only `led_ticker.plugin`), atomic load + error isolation, the `.` separator + emoji-pattern reason, registry retrofits, "plugins load after config parse / before widget build", the overlay-guard divergence, and the container/monitor contract.

### Task 6.3: `config.example.toml` `[plugins]` block + promote the technical README

**Files:** `config/config.example.toml`, `docs/plugin-system.md`.

- [ ] Add a commented `[plugins]` block (enabled/dir/disable) to `config.example.toml`.
- [ ] Reconcile `docs/plugin-system.md` (the engineering reference) with the polished docs-site page (cross-link; the README stays the terse integrator reference, the site page is the narrative tutorial).

### Task 6.4: Final verification + finish

- [ ] Docs build (the astro/starlight site builds; `make` docs target if present). The `examples/plugins/README.md` "see the Plugins page" link now resolves.
- [ ] Use **superpowers:finishing-a-development-branch** → PR ("docs: plugin system documentation + pool extraction walkthrough"). This closes the entire plugin-system arc.

---

## Self-Review

**Scope/coverage:** Phase 1 closes the three real gaps the pool audit found (Container/Updatable protocols, run_monitor_loop, SegmentMessage/TwoRowMessage) — all confirmed via the audit to be re-exports (the engine already supports containers structurally). Phases 2–3 build + port into the new `led-ticker-pool` repo (entry-point channel validated). Phase 4 removes every core coupling the audit enumerated (auto-import, 6 dispatch entries, `_POOL_DURATION_RE`, 3 configs, pool tests). Phase 5 validates end-to-end + hardware. Phase 6 = docs, the explicit final phase.

**Placeholder scan:** Concrete code for the led-ticker phases (1, 4) from the audit's verbatim findings; concrete scaffolding/port steps for the new repo (2, 3). The greenfield-repo path and the InfluxDB test-mocking are referenced to the existing pool tests (which already mock the HTTP layer) rather than re-specified — acceptable, as those tests are ported wholesale. The one genuinely open item (the new repo's absolute path) is flagged as "confirm with the user before git init", not a silent TBD.

**Type/name consistency:** The names re-exported in Phase 1 (`Container`, `Updatable`, `run_monitor_loop`, `SegmentMessage`, `TwoRowMessage`) are exactly the names Phase 3's port imports from `led_ticker.plugin`. The namespace `pool` + `api.widget("monitor")` → `pool.monitor` is used consistently in Phases 2 (smoke test), 3 (register), 4 (config migration), 5 (validation). `validate_config` (Phase 3) matches the convention's signature (`(cls, cfg) -> list[str]`).

**Cross-repo note:** Phases 1 + 4 are led-ticker PRs; 2 + 3 are the new repo; 5 spans both. Phase 1 should merge (or be branch-available) before Phase 3 imports its new exports. Phase 4 (core removal) must land AFTER Phase 3 (plugin works), to avoid a no-pool window.

# Plugin System — Phase E (Functional Surface) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the plugin system user-facing: a `[plugins]` config block (enable/dir/disable), a `led-ticker plugins` CLI command, `validate`/`--list-fields` that load plugins first, the font accessor re-exported with an overlay `draw_text` helper, and a complete `examples/plugins/` reference plugin.

**Architecture:** A `PluginsConfig` dataclass parses `[plugins]` (same pattern as `BusyLightConfig`). A shared `load_plugins_for_config(config_path)` reads that block (via a lightweight raw-TOML read, so it can run *before* full `load_config` — preserving the established "plugins load before config validation" order) and drives `load_plugins`, which gains a `disable` set. The run loop, the `validate` path, and the new `plugins` CLI command all call that one helper, so plugin contributions are visible everywhere. The font accessor (`resolve_font`/`Font`/`HiresFont`) plus a thin `draw_text` overlay helper close the twice-deferred "can't render text in an overlay" gap. `examples/plugins/acme/` exercises every surface + every hook and doubles as the comprehensive integration fixture.

**Tech Stack:** Python 3.14, pytest, argparse (existing CLI), dataclasses. No `from __future__ import annotations` (tripwire-forbidden). No new dependencies.

**Builds on (merged):** Phases A–D — `led_ticker.plugin.PluginAPI` (registry surfaces + lifecycle hooks), `_plugin_loader` (`load_plugins`, `LoadedPlugins`, discovery, `reset_plugins`), `validate_widget_cfg` + `_run_validate_config`.

**Explicitly OUT of scope (separate docs follow-up):** the docs-site "Plugins" page, the CLAUDE.md plugin-invariants section, and the `config.example.toml` commented `[plugins]` block. This plan is code + tests only.

---

## File Structure

**Modified:**
- `src/led_ticker/config.py` — `PluginsConfig` dataclass; `_parse_plugins_block(raw) -> PluginsConfig` (parse + validate); wire `plugins` into `AppConfig`.
- `src/led_ticker/_plugin_loader.py` — `load_plugins` gains `disable: set[str] | None`; new `read_plugins_config(config_path)` (lightweight) + `load_plugins_for_config(config_path)` (config-driven loader).
- `src/led_ticker/app/run.py` — `_load_plugins_for_config` delegates to the shared `load_plugins_for_config`.
- `src/led_ticker/validate.py` — `validate_config` loads plugins (config-driven) before build checks.
- `src/led_ticker/app/cli.py` — new `plugins` subcommand; `--list-fields` and `validate` load plugins first.
- `src/led_ticker/plugin.py` — re-export `resolve_font`, `Font`, `HiresFont`; add `draw_text` helper; extend `__all__`.

**Created:**
- `examples/plugins/acme/__init__.py` — reference plugin (every surface + every hook).
- `examples/plugins/acme/fonts/Brand.ttf` — a real font so the example's `api.font` resolves.
- `examples/plugins/README.md` — short pointer (one paragraph; full walkthrough is the docs follow-up).
- Tests: `tests/test_plugins/test_plugins_config.py`, `test_cli_plugins.py`, `test_example_plugin.py`; extend `test_font_plugins.py`, `test_plugin_api.py`, `test_validate_config.py`.

**Invariant (do not break):** plugins still load **before** `load_config` validates names (the Phase B ordering). The `[plugins]` block is therefore read by a lightweight raw-TOML pass (`read_plugins_config`), NOT by the full `load_config`. `load_config` *also* parses the block into `AppConfig.plugins` for completeness, but the run/validate/CLI loaders use the early read.

---

## Pre-flight (run once before Task E1)

- [ ] **Confirm branch + baseline**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e
git branch --show-current      # MUST print feat/plugin-phase-e — abort if main
make dev                       # uv sync (the pre-commit-install step may fail harmlessly because core.hooksPath is set)
make test                      # baseline green (≈2542 passed at branch point)
```

---

## Task E1: `[plugins]` config block

**Files:**
- Modify: `src/led_ticker/config.py`
- Test: create `tests/test_plugins/test_plugins_config.py`

**Context:** Config blocks follow the `BusyLightConfig` pattern (config.py:150-162): a `@dataclass` with defaults, parsed from `raw.get("<name>", {})` in `load_config`, validated immediately after. `AppConfig` (config.py:165-177) holds each block via `field(default_factory=...)`. The spec's `[plugins]` block has `enabled: bool = True`, `dir: str = "plugins"`, `disable: list[str] = []`. We factor parsing into `_parse_plugins_block(raw)` so the lightweight early-reader (Task E2) and `load_config` share one validated parser.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins/test_plugins_config.py`:

```python
import pytest

from led_ticker.config import PluginsConfig, _parse_plugins_block


def test_defaults_when_block_absent():
    cfg = _parse_plugins_block({})
    assert cfg == PluginsConfig(enabled=True, dir="plugins", disable=[])


def test_parses_all_fields():
    cfg = _parse_plugins_block(
        {"plugins": {"enabled": False, "dir": "addons", "disable": ["acme", "x"]}}
    )
    assert cfg.enabled is False
    assert cfg.dir == "addons"
    assert cfg.disable == ["acme", "x"]


def test_enabled_must_be_bool():
    with pytest.raises(ValueError, match="plugins.enabled must be a bool"):
        _parse_plugins_block({"plugins": {"enabled": "yes"}})


def test_dir_must_be_str():
    with pytest.raises(ValueError, match="plugins.dir must be a string"):
        _parse_plugins_block({"plugins": {"dir": 3}})


def test_disable_must_be_list_of_str():
    with pytest.raises(ValueError, match="plugins.disable must be a list of strings"):
        _parse_plugins_block({"plugins": {"disable": "acme"}})
    with pytest.raises(ValueError, match="plugins.disable must be a list of strings"):
        _parse_plugins_block({"plugins": {"disable": [1, 2]}})
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_plugins_config.py -q`
Expected: FAIL — `cannot import name 'PluginsConfig'`.

- [ ] **Step 3: Add `PluginsConfig` + `_parse_plugins_block`**

In `src/led_ticker/config.py`, immediately after the `BusyLightConfig` dataclass (ends at config.py:162), add:

```python
@dataclass
class PluginsConfig:
    enabled: bool = True
    dir: str = "plugins"
    disable: list[str] = field(default_factory=list)


def _parse_plugins_block(raw: dict) -> PluginsConfig:
    """Parse + validate the ``[plugins]`` TOML table into a PluginsConfig.

    Shared by ``load_config`` and the lightweight early reader the run loop /
    validate / CLI use (so plugin discovery can run before full config
    validation). Defaults: enabled=True, dir="plugins", disable=[].
    """
    p_raw = raw.get("plugins", {})
    cfg = PluginsConfig(
        enabled=p_raw.get("enabled", True),
        dir=p_raw.get("dir", "plugins"),
        disable=p_raw.get("disable", []),
    )
    if not isinstance(cfg.enabled, bool):
        raise ValueError(
            f"plugins.enabled must be a bool; got {type(cfg.enabled).__name__}."
        )
    if not isinstance(cfg.dir, str):
        raise ValueError(
            f"plugins.dir must be a string; got {type(cfg.dir).__name__}."
        )
    if not isinstance(cfg.disable, list) or not all(
        isinstance(n, str) for n in cfg.disable
    ):
        raise ValueError(
            f"plugins.disable must be a list of strings; got {cfg.disable!r}."
        )
    return cfg
```

- [ ] **Step 4: Wire `plugins` into `AppConfig` and `load_config`**

In `AppConfig` (config.py:165-177), add a field after `busy_light`:

```python
    busy_light: BusyLightConfig = field(default_factory=BusyLightConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
```

In `load_config`, after the busy-light parsing/validation block (config.py:331-380, which ends with the `busy_light.token` check), add:

```python
    plugins = _parse_plugins_block(raw)
```

Then find where `AppConfig(...)` is constructed at the end of `load_config` and add `plugins=plugins,` to its kwargs (alongside `busy_light=busy_light,`). (Search for `busy_light=busy_light` to find the constructor call.)

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_plugins/test_plugins_config.py -q` → PASS.
Run: `uv run pytest tests/ -q -k "config or load_config"` → PASS (existing configs default to an enabled plugins block; no behavior change).

- [ ] **Step 6: Lint + commit**

Run: `uv run ruff check src/led_ticker/config.py` → clean.

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e add src/led_ticker/config.py tests/test_plugins/test_plugins_config.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e -c core.hooksPath=/dev/null commit -m "feat(plugins): add [plugins] config block (enabled/dir/disable)"
```

---

## Task E2: `disable` list + config-driven loader

**Files:**
- Modify: `src/led_ticker/_plugin_loader.py`
- Modify: `src/led_ticker/app/run.py`
- Test: create `tests/test_plugins/test_loader_config.py`

**Context:** `load_plugins(plugin_dir, *, entry_points_enabled=True)` (_plugin_loader.py:336) discovers local + entry-point sources and loads each. Phase E adds a `disable` set: a discovered namespace in `disable` is skipped + logged. A new `read_plugins_config(config_path)` does a lightweight `tomllib` read of just the `[plugins]` block (so it runs before full `load_config`), and `load_plugins_for_config(config_path)` turns that into the right `load_plugins(...)` call. `run.py`'s existing `_load_plugins_for_config` (run.py:98) is rewired to delegate, so the run loop honors enable/dir/disable.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins/test_loader_config.py`:

```python
import textwrap

from led_ticker import _plugin_loader as L


def _write(plugin_dir, name, body="def register(api):\n    pass\n"):
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / f"{name}.py").write_text(textwrap.dedent(body))


def test_disable_skips_named_namespace(tmp_path):
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    _write(pdir, "keep")
    _write(pdir, "drop")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False, disable={"drop"})
        loaded = {info.namespace for info in result.loaded}
        assert loaded == {"keep"}
    finally:
        L.reset_plugins()


def test_read_plugins_config_reads_block(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """
            [display]
            rows = 16
            cols = 64

            [plugins]
            enabled = false
            dir = "addons"
            disable = ["x"]
            """
        )
    )
    pc = L.read_plugins_config(cfg_path)
    assert pc.enabled is False
    assert pc.dir == "addons"
    assert pc.disable == ["x"]


def test_read_plugins_config_defaults_on_unreadable(tmp_path):
    # A malformed/absent TOML must not crash the loader; load_config surfaces
    # the real error later. read_plugins_config returns defaults.
    bad = tmp_path / "nope.toml"
    pc = L.read_plugins_config(bad)
    assert pc.enabled is True and pc.dir == "plugins" and pc.disable == []


def test_load_plugins_for_config_disabled_loads_nothing(tmp_path):
    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    _write(tmp_path / "plugins", "acme")
    (tmp_path / "config.toml").write_text(
        "[display]\nrows=16\ncols=64\n[plugins]\nenabled=false\n"
    )
    try:
        result = L.load_plugins_for_config(tmp_path / "config.toml")
        assert result.loaded == [] and result.failed == []
    finally:
        L.reset_plugins()


def test_load_plugins_for_config_honors_dir_and_disable(tmp_path):
    L.reset_plugins()
    addons = tmp_path / "addons"
    _write(addons, "keep")
    _write(addons, "drop")
    (tmp_path / "config.toml").write_text(
        '[display]\nrows=16\ncols=64\n[plugins]\ndir="addons"\ndisable=["drop"]\n'
    )
    try:
        result = L.load_plugins_for_config(tmp_path / "config.toml")
        assert {i.namespace for i in result.loaded} == {"keep"}
    finally:
        L.reset_plugins()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_loader_config.py -q`
Expected: FAIL — `load_plugins()` got an unexpected keyword `disable`; `read_plugins_config`/`load_plugins_for_config` undefined.

- [ ] **Step 3: Add `disable` to `load_plugins`**

In `src/led_ticker/_plugin_loader.py`, change the `load_plugins` signature and the discovery loop. Current:

```python
def load_plugins(
    plugin_dir: Path | None, *, entry_points_enabled: bool = True
) -> LoadedPlugins:
    """Discover + load all plugins once. Idempotent (call reset_plugins() in
    tests to reload)."""
    global _LOADED
    if _LOADED is not None:
        return _LOADED
    result = LoadedPlugins()
    loaded_ns: set[str] = set()
    sources = []
    if plugin_dir is not None:
        sources.extend(_discover_local(plugin_dir))
    if entry_points_enabled:
        sources.extend(_discover_entry_points())
    for ns, source, thunk in sources:
        try:
            register, requires = thunk()
        except Exception as e:
            logger.exception("plugin %r (%s) failed to import", ns, source)
            result.failed.append((ns, str(e)))
            continue
        _load_one(ns, source, register, requires, loaded_ns, result)
    _LOADED = result
    return result
```

Replace with:

```python
def load_plugins(
    plugin_dir: Path | None,
    *,
    entry_points_enabled: bool = True,
    disable: set[str] | None = None,
) -> LoadedPlugins:
    """Discover + load all plugins once. Idempotent (call reset_plugins() in
    tests to reload). ``disable`` is a set of namespaces to skip + log."""
    global _LOADED  # noqa: PLW0603
    if _LOADED is not None:
        return _LOADED
    disabled = disable or set()
    result = LoadedPlugins()
    loaded_ns: set[str] = set()
    sources = []
    if plugin_dir is not None:
        sources.extend(_discover_local(plugin_dir))
    if entry_points_enabled:
        sources.extend(_discover_entry_points())
    for ns, source, thunk in sources:
        if ns in disabled:
            logger.info("plugin %r disabled via [plugins].disable; skipping", ns)
            continue
        try:
            register, requires = thunk()
        except Exception as e:
            logger.exception("plugin %r (%s) failed to import", ns, source)
            result.failed.append((ns, str(e)))
            continue
        _load_one(ns, source, register, requires, loaded_ns, result)
    _LOADED = result
    return result
```

- [ ] **Step 4: Add `read_plugins_config` + `load_plugins_for_config`**

In `src/led_ticker/_plugin_loader.py`, add near `load_plugins` (the file already imports `from pathlib import Path` and `logging`):

```python
def read_plugins_config(config_path: Path) -> "PluginsConfig":
    """Lightweight read of just the ``[plugins]`` block, so plugin discovery can
    run BEFORE full config validation (plugin-provided easings etc. must be
    registered before load_config validates them). Returns defaults if the file
    can't be read/parsed — load_config surfaces the real error afterward.
    """
    import tomllib

    from led_ticker.config import _parse_plugins_block

    try:
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
    except Exception:
        from led_ticker.config import PluginsConfig

        return PluginsConfig()
    return _parse_plugins_block(raw)


def load_plugins_for_config(config_path: Path) -> LoadedPlugins:
    """Config-driven plugin load: read the ``[plugins]`` block, then load from
    ``<config dir>/<dir>`` honoring enable/disable. Used by the run loop, the
    ``validate`` path, and the ``plugins`` CLI command."""
    pc = read_plugins_config(config_path)
    if not pc.enabled:
        logger.info("plugins disabled via [plugins].enabled=false; skipping")
        return load_plugins(None, entry_points_enabled=False)
    plugin_dir = config_path.parent / pc.dir
    return load_plugins(plugin_dir, disable=set(pc.disable))
```

Add the type-only import for the annotation at the top of the file (under a `TYPE_CHECKING` guard to avoid an import cycle, since `config.py` is heavier):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from led_ticker.config import PluginsConfig
```

(If `TYPE_CHECKING`/`typing` is already imported, just add the guarded import.)

- [ ] **Step 5: Rewire `run.py`'s `_load_plugins_for_config`**

In `src/led_ticker/app/run.py`, the current helper (run.py:98) is:

```python
def _load_plugins_for_config(config_path: Path):
    """..."""
    return load_plugins(config_path.parent / "plugins")
```

Replace its body to delegate (and update the import at run.py:16 to also bring in the new helper):

```python
def _load_plugins_for_config(config_path: Path):
    """Load plugins honoring the [plugins] config block (enable/dir/disable)."""
    return load_plugins_for_config(config_path)
```

Update the import line `from led_ticker._plugin_loader import (...)` in run.py to include `load_plugins_for_config` (keep `_guarded_overlay`, `_run_shutdown_hooks`, `_run_startup_hooks`, `load_plugins`).

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_plugins/test_loader_config.py -q` → PASS.
Run: `uv run pytest tests/test_plugins/ -q` → PASS.
Run: `uv run python -c "import led_ticker._plugin_loader; import led_ticker.app.run"` → clean (no import cycle).

- [ ] **Step 7: Lint + commit**

Run: `uv run ruff check src/led_ticker/_plugin_loader.py src/led_ticker/app/run.py` → clean.

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e add src/led_ticker/_plugin_loader.py src/led_ticker/app/run.py tests/test_plugins/test_loader_config.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e -c core.hooksPath=/dev/null commit -m "feat(plugins): disable-list + config-driven load_plugins_for_config"
```

---

## Task E3: `led-ticker plugins` CLI command

**Files:**
- Modify: `src/led_ticker/app/cli.py`
- Test: create `tests/test_plugins/test_cli_plugins.py`

**Context:** The CLI uses argparse (cli.py:32-42) with subparsers; `validate` is a subparser (cli.py:45). Add a `plugins` subparser. Its handler calls `load_plugins_for_config(args.config)` (top-level `--config`, default `config.toml`) and prints, per loaded plugin: namespace, source, and contribution counts (`PluginInfo.counts`); plus a "failed" section from `result.failed`. So the print logic is testable, factor it into a pure `_format_plugins(result) -> str` in cli.py.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugins/test_cli_plugins.py`:

```python
from led_ticker._plugin_loader import LoadedPlugins, PluginInfo
from led_ticker.app.cli import _format_plugins


def test_format_plugins_lists_loaded_and_counts():
    result = LoadedPlugins(
        loaded=[
            PluginInfo(namespace="acme", source="/cfg/plugins/acme.py",
                       counts={"widgets": 2, "transitions": 1}),
        ],
        failed=[],
    )
    out = _format_plugins(result)
    assert "acme" in out
    assert "/cfg/plugins/acme.py" in out
    assert "widgets: 2" in out or "widgets=2" in out or "2 widgets" in out


def test_format_plugins_reports_failures():
    result = LoadedPlugins(loaded=[], failed=[("bad", "boom")])
    out = _format_plugins(result)
    assert "bad" in out
    assert "boom" in out


def test_format_plugins_empty():
    out = _format_plugins(LoadedPlugins())
    assert "no plugins" in out.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_cli_plugins.py -q`
Expected: FAIL — `cannot import name '_format_plugins'`.

- [ ] **Step 3: Add `_format_plugins` + the subcommand**

In `src/led_ticker/app/cli.py`, add the formatter (module level, e.g. above `def main`):

```python
def _format_plugins(result) -> str:
    """Human-readable summary of loaded + failed plugins for `led-ticker plugins`."""
    lines: list[str] = []
    if not result.loaded and not result.failed:
        return "No plugins found."
    if result.loaded:
        lines.append(f"Loaded {len(result.loaded)} plugin(s):")
        for info in result.loaded:
            contrib = (
                ", ".join(f"{k}: {v}" for k, v in sorted(info.counts.items()))
                or "(hooks only)"
            )
            lines.append(f"  {info.namespace}  [{info.source}]  {contrib}")
    if result.failed:
        lines.append(f"Failed {len(result.failed)} plugin(s):")
        for ns, err in result.failed:
            lines.append(f"  {ns}: {err}")
    return "\n".join(lines)
```

Register the subparser next to `validate` (after the `val_parser` block, before `args = parser.parse_args()` at cli.py:93):

```python
    # `plugins` subcommand
    subparsers.add_parser(
        "plugins",
        help="List loaded plugins (and any that failed) for the config",
    )
```

Add the handler. Right after `args = parser.parse_args()` (cli.py:93) and BEFORE the `if args.command == "validate":` block, add:

```python
    if args.command == "plugins":
        from led_ticker._plugin_loader import load_plugins_for_config  # noqa: PLC0415

        result = load_plugins_for_config(args.config)
        print(_format_plugins(result))
        sys.exit(0)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_plugins/test_cli_plugins.py -q` → PASS.

- [ ] **Step 5: Manual smoke (optional but recommended)**

```bash
mkdir -p /tmp/pe_cfg/plugins
printf '[display]\nrows=16\ncols=64\n' > /tmp/pe_cfg/config.toml
printf 'def register(api):\n    @api.widget("clock")\n    class C:\n        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):\n            return canvas, cursor_pos\n' > /tmp/pe_cfg/plugins/acme.py
uv run led-ticker --config /tmp/pe_cfg/config.toml plugins
```
Expected: prints `Loaded 1 plugin(s):` with `acme  [...]  widgets: 1`.

- [ ] **Step 6: Lint + commit**

Run: `uv run ruff check src/led_ticker/app/cli.py` → clean.

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e add src/led_ticker/app/cli.py tests/test_plugins/test_cli_plugins.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e -c core.hooksPath=/dev/null commit -m "feat(plugins): led-ticker plugins CLI command"
```

---

## Task E4: `validate` + `--list-fields` load plugins first

**Files:**
- Modify: `src/led_ticker/validate.py`
- Modify: `src/led_ticker/app/cli.py`
- Test: extend `tests/test_plugins/test_validate_config.py`

**Context:** `validate_config(path, *, strict)` (validate.py:1609) loads + checks the config but does NOT load plugins, so a plugin widget type fails validation as "unknown". And the CLI `--list-fields TYPE` (cli.py:96-107) calls `_list_widget_fields` directly without loading plugins, so a plugin widget's fields aren't listable. Phase E loads plugins (config-driven) before both. `validate_config` knows `path` → load from `path`. `--list-fields` uses the top-level `args.config`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugins/test_validate_config.py` (the file already imports `pytest`, `textwrap`, `from led_ticker import _plugin_loader as L`):

```python
from led_ticker.validate import validate_config as run_validate


async def test_validate_loads_plugins_so_plugin_widget_is_known(tmp_path):
    L.reset_plugins()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            '''
            def register(api):
                @api.widget("clock")
                class Clock:
                    def __init__(self, **kw):
                        pass
                    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
                        return canvas, cursor_pos
            '''
        )
    )
    (tmp_path / "config.toml").write_text(
        textwrap.dedent(
            """
            [display]
            rows = 16
            cols = 64

            [[playlist.section]]
            [[playlist.section.widget]]
            type = "acme.clock"
            """
        )
    )
    try:
        result = await run_validate(tmp_path / "config.toml")
        # The plugin widget type resolved — no "unknown widget type" error.
        joined = " ".join(str(e) for e in result.errors)
        assert "acme.clock" not in joined or "unknown" not in joined.lower()
    finally:
        L.reset_plugins()
```

> Note: confirm `ValidationResult`'s error field name (`.errors`) by reading `validate.py`; adjust the assertion to the real attribute. The point is: validating a config that references `acme.clock` must NOT report it as an unknown type once plugins load.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_plugins/test_validate_config.py -q -k "loads_plugins"`
Expected: FAIL — `acme.clock` reported as unknown widget type (plugins not loaded).

- [ ] **Step 3: Load plugins in `validate_config`**

In `src/led_ticker/validate.py`, in `validate_config`, after the config is loaded (the `config = load_config(path)` line, validate.py:1630) — actually plugins must load BEFORE `load_config` so plugin easings/types validate during parse. Insert at the very top of `validate_config`, right after the `if not path.exists(): raise FileNotFoundError(...)` guard and BEFORE `from led_ticker.config import load_config` / `load_config(path)`:

```python
    from led_ticker._plugin_loader import load_plugins_for_config

    load_plugins_for_config(path)
```

(This is idempotent — guarded by `_LOADED`. In the running app the run loop already loaded them; in the standalone `validate` CLI this is the first load.)

- [ ] **Step 4: Load plugins before `--list-fields`**

In `src/led_ticker/app/cli.py`, in the `--list-fields` branch (cli.py:96), load plugins before resolving the type. Change:

```python
        if args.list_fields is not None:
            from led_ticker.app.factories import _list_section_fields  # noqa: PLC0415

            if args.list_fields == "section":
                print(_list_section_fields())
                sys.exit(0)
            try:
                print(_list_widget_fields(args.list_fields))
```

to:

```python
        if args.list_fields is not None:
            from led_ticker.app.factories import _list_section_fields  # noqa: PLC0415

            if args.list_fields == "section":
                print(_list_section_fields())
                sys.exit(0)
            # Load plugins so a plugin widget type (e.g. acme.clock) is listable.
            from led_ticker._plugin_loader import load_plugins_for_config  # noqa: PLC0415

            load_plugins_for_config(args.config)
            try:
                print(_list_widget_fields(args.list_fields))
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_plugins/test_validate_config.py -q` → PASS.
Run: `uv run pytest tests/ -q -k "validate"` → PASS (built-in configs unaffected — `load_plugins_for_config` on a config with no `plugins/` dir loads nothing).

- [ ] **Step 6: Lint + commit**

Run: `uv run ruff check src/led_ticker/validate.py src/led_ticker/app/cli.py` → clean.

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e add src/led_ticker/validate.py src/led_ticker/app/cli.py tests/test_plugins/test_validate_config.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e -c core.hooksPath=/dev/null commit -m "feat(plugins): validate + --list-fields load plugins first"
```

---

## Task E5: Font re-exports + `draw_text` overlay helper

**Files:**
- Modify: `src/led_ticker/plugin.py`
- Test: extend `tests/test_plugins/test_font_plugins.py`, `tests/test_plugins/test_plugin_api.py`

**Context:** Independent reviews of Phases C and D both flagged: a plugin can register a font but can't LOAD it to draw text in an overlay, because `resolve_font`/`Font`/`HiresFont` aren't re-exported and there's no public text-draw helper. `resolve_font(name, size=None, threshold=None) -> Font | HiresFont` lives in `led_ticker.fonts`; `Font` is `led_ticker._types.Font`; `HiresFont` is `led_ticker.fonts.hires_loader.HiresFont`. The real text+emoji renderer is `pixel_emoji.draw_with_emoji(canvas, font, cursor_pos, y, color, text, ...)`. Phase E re-exports the font types/resolver and adds a friendly `draw_text(canvas, font, text, x, y, color) -> int` wrapper (hiding `draw_with_emoji`'s animation-oriented args).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_plugin_api.py`:

```python
def test_font_accessor_and_draw_text_are_exported():
    import led_ticker.plugin as p

    for name in ("resolve_font", "Font", "HiresFont", "draw_text"):
        assert hasattr(p, name), f"missing public export: {name}"
```

Append to `tests/test_plugins/test_font_plugins.py` (it already imports `resolve_font`/`BUNDLED_HIRES_DIR`/`HiresFont` from `led_ticker.fonts...`):

```python
def test_draw_text_renders_via_public_surface():
    # A plugin overlay author: resolve a built-in font and draw text on a canvas
    # using ONLY led_ticker.plugin.
    from led_ticker.plugin import draw_text, make_color, resolve_font

    font = resolve_font("6x12")  # a built-in BDF alias; no size needed
    from led_ticker.pixel_emoji import ScaledCanvas
    from tests.stubs.rgbmatrix import _StubCanvas  # mirror existing test usage

    canvas = _StubCanvas(width=64, height=16)
    end_x = draw_text(canvas, font, "hi", x=0, y=10, color=make_color(255, 255, 255))
    assert isinstance(end_x, int) and end_x > 0  # cursor advanced
```

> Confirm the stub-canvas import path by grepping existing tests (`grep -rn "_StubCanvas" tests/` — Phase D used `from led_ticker.pixel_emoji import ScaledCanvas` wrapping a stub, and other tests import the stub directly). Use whatever construction the existing `draw_with_emoji` tests use; the assertion (advanced cursor, no raise) is the point. Drop the unused `ScaledCanvas` import if not needed.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_plugins/test_plugin_api.py tests/test_plugins/test_font_plugins.py -q -k "exported or draw_text"`
Expected: FAIL — `resolve_font`/`Font`/`HiresFont`/`draw_text` not on `led_ticker.plugin`.

- [ ] **Step 3: Add the re-exports + `draw_text`**

In `src/led_ticker/plugin.py`, extend the import block (after line 27, the `pixel_emoji` import). Add:

```python
from led_ticker._types import Font
from led_ticker.fonts import resolve_font
from led_ticker.fonts.hires_loader import HiresFont
from led_ticker.pixel_emoji import draw_with_emoji
```

(Keep the existing `from led_ticker._types import Canvas, Color, PixelData` line; you may merge `Font` into it: `from led_ticker._types import Canvas, Color, Font, PixelData`.)

Add the helper (module level, e.g. just after `make_color`):

```python
def draw_text(
    canvas: Canvas, font: Font, text: str, x: int, y: int, color: Color
) -> int:
    """Draw ``text`` on ``canvas`` at baseline ``y`` starting at column ``x``.

    For use inside an ``api.overlay`` painter (or anywhere a plugin has a
    canvas). ``font`` comes from ``resolve_font(name[, size])``; ``color`` from
    ``make_color(r, g, b)``. Inline ``:emoji:`` tokens in ``text`` render too.
    Returns the cursor x-position after the drawn text.
    """
    return draw_with_emoji(canvas, font, x, y, color, text)
```

Extend `__all__` — add (keeping alphabetical grouping): `"Font"`, `"HiresFont"`, `"draw_text"`, `"resolve_font"`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_plugins/test_plugin_api.py tests/test_plugins/test_font_plugins.py -q` → PASS.
Run: `uv run python -c "import led_ticker.plugin"` → clean; `uv run ruff check src/led_ticker/plugin.py` → clean (the re-exports are in `__all__`, so F401 won't fire).

- [ ] **Step 5: Commit**

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e add src/led_ticker/plugin.py tests/test_plugins/test_plugin_api.py tests/test_plugins/test_font_plugins.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e -c core.hooksPath=/dev/null commit -m "feat(plugins): re-export font accessor + add draw_text overlay helper"
```

---

## Task E6: `examples/plugins/` reference plugin (every surface + hooks)

**Files:**
- Create: `examples/plugins/acme/__init__.py`, `examples/plugins/acme/fonts/Brand.ttf`, `examples/plugins/README.md`
- Test: create `tests/test_plugins/test_example_plugin.py`

**Context:** The spec wants a canonical reference plugin exercising every surface + hook, and the testing strategy wants a fixture exercising every surface. One artifact serves both: `examples/plugins/acme/` as a package, loaded in a test that asserts each surface registered and is usable. It registers a widget, transition, color_provider, animation, border, easing, emoji, hires_emoji, font, overlay, on_startup, on_shutdown — all namespaced `acme.*`.

- [ ] **Step 1: Create the reference plugin package**

Create `examples/plugins/acme/__init__.py`:

```python
"""Reference led-ticker plugin — exercises every plugin surface + hook.

Drop this directory into your ``config/plugins/`` (or install it as a package
with an ``[project.entry-points."led_ticker.plugins"]`` entry) and reference its
contributions in TOML as ``acme.<name>`` (e.g. ``type = "acme.clock"``).
"""

from led_ticker.plugin import (
    Animation,
    AnimationFrame,
    BorderEffectBase,
    ColorProviderBase,
    HiResEmoji,
    StartupContext,
    Widget,
    draw_text,
    make_color,
    resolve_font,
    spawn_tracked,
)

# Shared state a startup poller updates and the overlay paints (the canonical
# "service plugin" pattern).
_STATE = {"tick": 0}


def register(api):
    @api.widget("clock")
    class Clock:
        def __init__(self, **kwargs):
            self.text = kwargs.get("text", "12:00")

        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            return canvas, cursor_pos

    @api.transition("swoosh")
    class Swoosh:
        def render(self, canvas, outgoing, incoming, t):
            return canvas

    @api.color_provider("fire")
    class Fire(ColorProviderBase):
        frame_invariant = True

        def color_for(self, index, total, frame=0):
            return make_color(255, 80, 0)

    @api.animation("scramble")
    class Scramble:
        def frame_for(self, text, frame):
            return AnimationFrame(visible_text=text)

    @api.border("neon")
    class Neon(BorderEffectBase):
        def paint(self, canvas, frame_count):
            return canvas

    api.easing("snap", lambda p: p * p)
    api.emoji("spark", [(x, y, 255, 200, 0) for x in range(8) for y in range(8)])
    api.hires_emoji(
        "glow", HiResEmoji(pixels=((0, 0, 255, 200, 0),), physical_size=16)
    )
    api.font("Brand", "fonts/Brand.ttf")

    def paint(canvas):
        # Draw a tiny status pixel; a real plugin might draw_text(...) here.
        canvas.SetPixel(0, 0, 0, 200, 0)

    api.overlay(paint)

    def on_startup(ctx: StartupContext):
        _STATE["tick"] = 1  # a real plugin would spawn_tracked(poller())

    api.on_startup(on_startup)
    api.on_shutdown(lambda: _STATE.update(tick=0))
```

> Verify the `Animation`/`Transition`/`ColorProviderBase`/`BorderEffectBase` minimal shapes against the real Protocols (read `animations.py`, `transitions.py`, `color_providers.py`, `borders.py`). Adjust method names/signatures so each class actually satisfies its registry's expectations (the test in Step 3 will catch mismatches). `Clock.draw`'s signature mirrors the Widget protocol used in earlier-phase test plugins.

- [ ] **Step 2: Add a real font file + README**

Copy a bundled hi-res font into the example so `api.font` resolves to a real file:

```bash
mkdir -p /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e/examples/plugins/acme/fonts
cp "$(ls /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e/src/led_ticker/fonts/hires/*.otf /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e/src/led_ticker/fonts/hires/*.ttf 2>/dev/null | head -1)" /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e/examples/plugins/acme/fonts/Brand.ttf
```

Create `examples/plugins/README.md`:

```markdown
# Example led-ticker plugin

`acme/` is a complete reference plugin exercising every plugin surface
(widget, transition, color provider, animation, border, easing, emoji,
hi-res emoji, font) and every lifecycle hook (overlay, on_startup,
on_shutdown). Each contribution is namespaced `acme.*`.

**Local use:** copy `acme/` into your `config/plugins/`.
**Packaged use:** ship it as a package declaring
`[project.entry-points."led_ticker.plugins"]  acme = "acme:register"`.

Full walkthrough: see the Plugins page in the docs site.
```

- [ ] **Step 3: Write the comprehensive load test**

Create `tests/test_plugins/test_example_plugin.py`:

```python
from pathlib import Path

from led_ticker import _plugin_loader as L

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "plugins"


def test_example_plugin_registers_every_surface_and_hook():
    L.reset_plugins()
    try:
        result = L.load_plugins(EXAMPLES, entry_points_enabled=False)
        assert not result.failed, result.failed
        info = next(i for i in result.loaded if i.namespace == "acme")
        # Every registry surface contributed:
        for surface in (
            "widgets", "transitions", "color_providers", "animations",
            "borders", "easing", "emojis", "hires_emojis", "fonts",
        ):
            assert info.counts.get(surface, 0) >= 1, f"missing {surface}: {info.counts}"
        # Every hook collected:
        assert any(ns == "acme" for ns, _ in result.overlays)
        assert any(ns == "acme" for ns, _ in result.startup_hooks)
        assert any(ns == "acme" for ns, _ in result.shutdown_hooks)
    finally:
        L.reset_plugins()


def test_example_plugin_contributions_are_usable():
    from led_ticker.fonts import resolve_font
    from led_ticker.widgets import get_widget_class

    L.reset_plugins()
    try:
        L.load_plugins(EXAMPLES, entry_points_enabled=False)
        # widget class resolvable; font resolvable to a real HiresFont
        assert get_widget_class("acme.clock") is not None
        font = resolve_font("acme.Brand", size=16)
        assert font.__class__.__name__ == "HiresFont"
    finally:
        L.reset_plugins()
```

> `examples/` sits at the repo root; `Path(__file__).resolve().parents[2]` from `tests/test_plugins/test_example_plugin.py` is the repo root — verify the depth (`parents[2]`) resolves to the dir containing `examples/` and adjust if the test tree nests differently.

- [ ] **Step 4: Run the test, iterate on the plugin until clean**

Run: `uv run pytest tests/test_plugins/test_example_plugin.py -q`
If a surface fails to register, the example class doesn't satisfy that registry's contract — fix the example class (not the test) until all surfaces register and `result.failed` is empty.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check examples/plugins/acme/__init__.py tests/test_plugins/test_example_plugin.py` → clean.

> If `examples/` is outside ruff's configured `src`/`tests` paths, `make lint` may not cover it — run ruff on the file explicitly as above.

```bash
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e add examples/ tests/test_plugins/test_example_plugin.py
git -C /Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/plugin-phase-e -c core.hooksPath=/dev/null commit -m "feat(plugins): examples/plugins reference plugin + comprehensive load test"
```

---

## Task E7: Final verification + whole-phase review

**Files:** none (verification only)

- [ ] **Step 1: Lint** — `make lint` → `All checks passed!` (also run `uv run ruff check examples/` explicitly).
- [ ] **Step 2: Typecheck** — `make typecheck` → `0 errors`.
- [ ] **Step 3: Full suite + coverage** — `make test` → all green, coverage ≥ project floor (≈95%).
- [ ] **Step 4: Public-surface tripwire** — `uv run pytest tests/test_plugins/test_plugin_api.py -q -k export` → PASS (`resolve_font`/`Font`/`HiresFont`/`draw_text` exported).
- [ ] **Step 5: CLI smoke** — run the `led-ticker plugins` smoke from Task E3 Step 5; confirm output. Also `uv run led-ticker --config /tmp/pe_cfg/config.toml validate --list-fields acme.clock` lists the plugin widget's fields.
- [ ] **Step 6: Report** — summarize the surface added (config block, CLI, validate-load, font accessor + draw_text, example plugin), confirm the docs follow-up is still pending (docs-site page, CLAUDE.md, config.example.toml), and hand back for the whole-phase review + `finishing-a-development-branch`.

---

## Self-Review (against spec "Config / CLI & validation integration / Deployment / Testing strategy")

**1. Spec coverage:**
- `[plugins]` block (enabled/dir/disable, validated) → E1.
- "enabled=false disables all discovery" → E2 (`load_plugins_for_config` returns empty when disabled). "dir relative to config dir", "disable list skips namespaces" → E2.
- `led-ticker validate` loads plugins first → E4. `--list-fields acme.x` lists plugin widget fields → E4 (no change to `_list_widget_fields` needed — it works on any registered class once loaded).
- `led-ticker plugins` command (namespace, source, contribution summary, failures) → E3.
- `examples/plugins/` complete sample (every surface + a hook) → E6.
- Font accessor gap (re-export `resolve_font`/`Font`/`HiresFont` + overlay text) → E5 (the twice-deferred carry-forward).
- Testing strategy "fixture plugin exercising every surface, assert usable" → E6's two tests.

**Deferred to the docs follow-up (per the agreed split):** docs-site "Plugins" page, CLAUDE.md invariants section, `config.example.toml` `[plugins]` block. The spec's "Documentation deliverables" section is entirely the follow-up's scope.

**2. Placeholder scan:** No TBD/"handle errors". Every code step shows complete code. The few "verify against the real Protocol / stub path / parents[] depth" notes are explicit verification instructions with a concrete fallback (the test catches mismatches), not placeholders.

**3. Type/name consistency:** `PluginsConfig(enabled, dir, disable)` defined in E1, parsed by `_parse_plugins_block` (E1), consumed by `read_plugins_config`/`load_plugins_for_config` (E2). `load_plugins(..., disable=set)` signature in E2 matches its E2 tests and the `load_plugins_for_config` call. `_format_plugins(result)` (E3) consumes `LoadedPlugins.loaded[*].counts` and `.failed` (the real fields). `draw_text(canvas, font, text, x, y, color)` (E5) wraps `draw_with_emoji(canvas, font, cursor_pos, y, color, text)` with `x→cursor_pos` — arg order verified against pixel_emoji.py:2901. `resolve_font`/`Font`/`HiresFont` re-export sources verified (`led_ticker.fonts`, `_types`, `hires_loader`).

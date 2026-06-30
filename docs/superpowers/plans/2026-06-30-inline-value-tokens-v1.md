# Inline Value Tokens v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed live `:source.id:` value tokens in widget text (e.g. `"It's :clock.now:"`), driven by config-declared `[[source]]` blocks, across all text-bearing widgets.

**Architecture:** A new `sources.py` holds a unified `DataSource` (synchronous `compute()` for v1), a `DataRegistry` reached via a module accessor, a shared 1 Hz refresh ticker that bumps an integer `version` only when a value changes, and a stateful `TokenizedField` substitution helper. Widgets resolve tokens *before* layout (so the existing `draw_with_emoji` pipeline is unchanged) and re-measure only when a referenced source's version moves — but resolution is **frozen** during scroll / transition / typewriter so a mid-flight width change can't corrupt rendering.

**Tech Stack:** Python 3.14 (PEP 649), attrs widgets, asyncio, stdlib `tomllib`, BDF text rendering.

**Source of truth:** `docs/superpowers/specs/2026-06-30-inline-value-tokens-v1-design.md`. Read it before starting any task.

## Global Constraints

- **Token resolution order:** emoji wins, then source, then literal. The substitution pre-pass substitutes only names that resolve to a declared source AND are NOT in the emoji registry; everything else (emoji slugs, unknown tokens, literal colons) passes through untouched.
- **`[[source]]` is top-level** (`raw["source"]`), a sibling of `[playlist]` — NOT nested under it.
- **Resolution-freeze is REQUIRED** for scroll, transition compositing, and typewriter reveal (hardware constraints #6/#7/#12 + the transition frame-freeze invariant). Re-resolve/re-measure is allowed ONLY on a held tick.
- **Polled background-loop wiring is DEFERRED to v2.** Ship the `polled` field + the write-order contract only; no `run_monitor_loop` branch, no polled core source.
- **Plugins import only `led_ticker.plugin`**; `__all__` is the contract.
- **PEP 649:** no `from __future__ import annotations` in any new/edited file.
- **DOCS-STYLE.md** for docs; no "footgun"/"gun" metaphor anywhere.
- **Core gates (run for every task that touches code):** `PYTHONPATH=tests/stubs uv run --extra dev pytest`, `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev pyright src/`.
- **Worktree + PR; never commit on `main`.** Commits in the worktree may need `git -c core.hooksPath=/dev/null` if the pre-commit hook misbehaves.

## Non-Goals (v1)

Weather / any polled or async source; the polled background-loop wiring; a formatting DSL beyond a single `format` string; sub-field token addressing (one source = one value string); fixed-pixel-width slots / segment-aware drawing; the "undeclared token" validate warning; sub-second refresh granularity.

## File Structure

- **Create** `src/led_ticker/sources.py` — `DataSource` base + `ClockSource`/`DateSource`/`StaticSource`, `DataRegistry`, `get_data_registry`/`set_data_registry`, the 1 Hz `run_source_refresh_loop`, and `TokenizedField`. One focused file (~`borders.py` size).
- **Create** `tests/test_sources.py` — unit tests for sources, registry, refresh, `TokenizedField`.
- **Modify** `src/led_ticker/config.py` — `SourceConfig` dataclass, parse `raw["source"]`, add `sources` to `AppConfig`.
- **Modify** `src/led_ticker/app/factories.py` — `get_source_class(type)` factory (mirrors `get_widget_class`); the source-type registry.
- **Modify** `src/led_ticker/app/run.py` — build the registry from `AppConfig.sources` at startup, `set_data_registry(...)`, spawn the refresh loop.
- **Modify** `src/led_ticker/plugin.py` — the `api.source` surface + `__all__` + `"sources"` buffer; register core clock/date/static.
- **Modify** `src/led_ticker/pixel_emoji.py` — add `is_emoji_slug(slug) -> bool` (public helper used by `TokenizedField`).
- **Modify** `src/led_ticker/widgets/_frame_aware.py` (FrameAwareBase) — `_resolution_locked` flag; `pause_frame`/`resume_frame` set/clear it.
- **Modify** `src/led_ticker/widgets/message.py`, `widgets/two_row.py`, `widgets/_image_base.py` — token wiring per widget.
- **Modify** `src/led_ticker/ticker.py` — scroll-branch resolution freeze (resolve once, lock for the loop).
- **Modify** `src/led_ticker/app/reload.py` — atomic registry swap + refresh-ticker respawn.
- **Modify** `src/led_ticker/validate.py` — `[[source]]` rules.
- **Create** `docs/site/src/content/docs/concepts/value-tokens.mdx` + an example `[[source]]` block in a config example.

---

## Task 1: `sources.py` — DataSource, core sources, registry, refresh loop

**Files:**
- Create: `src/led_ticker/sources.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces: `class DataSource` (`id: str`, `current: str`, `version: int`, `polled: bool`, `compute() -> str`, `refresh() -> bool`); `ClockSource`/`DateSource`/`StaticSource`; `class DataRegistry` (`get(id) -> DataSource | None`, `ids() -> set[str]`, `add(src)`); `get_data_registry() -> DataRegistry`, `set_data_registry(reg)`; `async def run_source_refresh_loop(reg)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_sources.py`:

```python
import datetime
import led_ticker.sources as sources
from led_ticker.sources import (
    ClockSource, DateSource, StaticSource, DataRegistry,
    get_data_registry, set_data_registry,
)


def test_static_compute_returns_value():
    s = StaticSource(id="brand.tag", value="Open 9-5")
    assert s.compute() == "Open 9-5"
    assert s.polled is False


def test_clock_compute_formats_now():
    s = ClockSource(id="clock.now", fmt="%H:%M", tz=None)
    # compute() formats the current time; assert it matches strftime now
    out = s.compute()
    assert out == datetime.datetime.now().strftime("%H:%M")


def test_date_compute_with_timezone():
    s = DateSource(id="date.ny", fmt="%Y", tz="America/New_York")
    assert s.compute() == datetime.datetime.now(
        datetime.timezone.utc
    ).astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).strftime("%Y")


def test_refresh_bumps_version_only_on_change():
    s = StaticSource(id="x", value="a")
    s.refresh()                      # first refresh sets current, version -> 1
    assert s.current == "a"
    v1 = s.version
    changed = s.refresh()            # unchanged value
    assert changed is False
    assert s.version == v1           # NO bump when value is identical


def test_refresh_writes_current_before_version(monkeypatch):
    # Write-order contract: a stub that flips value, assert current is set
    # before version is read by a notional reader (here: current updated when
    # changed=True, and version strictly increments).
    s = StaticSource(id="x", value="a")
    s.refresh()
    s.value = "b"                    # change the underlying value
    assert s.refresh() is True
    assert s.current == "b"
    assert s.version >= 2


def test_registry_get_set_and_lookup():
    reg = DataRegistry()
    s = StaticSource(id="brand.tag", value="hi")
    reg.add(s)
    set_data_registry(reg)
    assert get_data_registry().get("brand.tag") is s
    assert get_data_registry().get("missing") is None
    assert "brand.tag" in get_data_registry().ids()
```

- [ ] **Step 2: Run to verify they fail** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_sources.py -v` → FAIL (module/classes missing).

- [ ] **Step 3: Implement `src/led_ticker/sources.py`** (sources + registry portion; `TokenizedField` lands in Task 2):

```python
"""Live value sources for inline `:source.id:` tokens.

A DataSource produces a string value (`current`) and an integer `version`
that bumps ONLY when the value changes. v1 ships synchronous sources
(clock/date/static); the `polled` field is part of the contract but the
background-loop wiring is deferred to v2.

Write-order contract (binds future polled sources): write `current` BEFORE
`version`, with no `await` between, so a reader sampling version-then-current
can never pair a new version with a stale value.
"""

import asyncio
import datetime
from typing import Any
from zoneinfo import ZoneInfo

import attrs

from led_ticker.widget import spawn_tracked


@attrs.define(eq=False)
class DataSource:
    """Base class. Subclasses implement compute(); refresh() applies it."""

    id: str
    polled: bool = attrs.field(default=False, kw_only=True)
    current: str = attrs.field(default="", init=False)
    version: int = attrs.field(default=0, init=False)

    def compute(self) -> str:
        raise NotImplementedError

    def refresh(self) -> bool:
        """Recompute; bump version iff the value changed. Returns changed."""
        value = self.compute()
        if value == self.current and self.version != 0:
            return False
        self.current = value          # current BEFORE version (contract)
        self.version += 1
        return True


@attrs.define(eq=False)
class StaticSource(DataSource):
    value: str = ""

    def compute(self) -> str:
        return self.value


@attrs.define(eq=False)
class ClockSource(DataSource):
    fmt: str = "%H:%M"
    tz: str | None = None

    def compute(self) -> str:
        now = (
            datetime.datetime.now(ZoneInfo(self.tz))
            if self.tz
            else datetime.datetime.now()
        )
        return now.strftime(self.fmt)


@attrs.define(eq=False)
class DateSource(ClockSource):
    """Same machinery as ClockSource; separate type for config clarity."""


class DataRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, DataSource] = {}

    def add(self, source: DataSource) -> None:
        self._by_id[source.id] = source

    def get(self, source_id: str) -> DataSource | None:
        return self._by_id.get(source_id)

    def ids(self) -> set[str]:
        return set(self._by_id)

    def sources(self) -> list[DataSource]:
        return list(self._by_id.values())


_REGISTRY: DataRegistry = DataRegistry()


def get_data_registry() -> DataRegistry:
    return _REGISTRY


def set_data_registry(registry: DataRegistry) -> None:
    """Atomically swap the process registry (used at startup + hot-reload)."""
    global _REGISTRY
    _REGISTRY = registry


async def run_source_refresh_loop(
    registry: DataRegistry, interval: float = 1.0
) -> None:
    """1 Hz: refresh every synchronous source; version bumps drive widgets."""
    while True:
        for source in registry.sources():
            if not source.polled:
                source.refresh()
        await asyncio.sleep(interval)


def spawn_source_refresh(registry: DataRegistry) -> Any:
    """Prime each source once, then spawn the 1 Hz loop (tracked task)."""
    for source in registry.sources():
        if not source.polled:
            source.refresh()
    return spawn_tracked(run_source_refresh_loop(registry))
```

- [ ] **Step 4: Run tests to verify they pass** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_sources.py -v` → PASS.

- [ ] **Step 5: Add a refresh-loop test** (the loop bumps versions over time) and run it:

```python
import asyncio
import pytest
from led_ticker.sources import StaticSource, DataRegistry, run_source_refresh_loop


@pytest.mark.asyncio
async def test_refresh_loop_picks_up_value_change():
    reg = DataRegistry()
    s = StaticSource(id="x", value="a")
    reg.add(s)
    task = asyncio.create_task(run_source_refresh_loop(reg, interval=0.01))
    await asyncio.sleep(0.05)
    assert s.current == "a" and s.version >= 1
    s.value = "b"
    await asyncio.sleep(0.05)
    assert s.current == "b"
    task.cancel()
```

(Check `tests/` for the existing asyncio-test convention — the project uses `pytest.mark.asyncio` elsewhere; match it.)

- [ ] **Step 6: Gates + commit** — run the three core gates; then:

```bash
git add src/led_ticker/sources.py tests/test_sources.py
git commit -m "feat(sources): DataSource + clock/date/static + registry + 1Hz refresh"
```

---

## Task 2: `TokenizedField` substitution helper + `is_emoji_slug`

**Files:**
- Modify: `src/led_ticker/sources.py` (add `TokenizedField`)
- Modify: `src/led_ticker/pixel_emoji.py` (add public `is_emoji_slug`)
- Test: `tests/test_sources.py` (add), `tests/test_pixel_emoji.py` (add the helper test)

**Interfaces:**
- Consumes: `DataRegistry` (Task 1); `EMOJI_PATTERN`, `_get_registry` (pixel_emoji).
- Produces: `is_emoji_slug(slug: str) -> bool`; `class TokenizedField` with `has_tokens: bool`, `resolve(registry: DataRegistry) -> tuple[str, bool]` (returns `(text, changed)`).

- [ ] **Step 1: Write failing tests** in `tests/test_sources.py`:

```python
from led_ticker.sources import TokenizedField, StaticSource, DataRegistry


def _reg(*srcs):
    r = DataRegistry()
    for s in srcs:
        s.refresh()
        r.add(s)
    return r


def test_field_with_no_tokens_is_inert():
    f = TokenizedField("plain text, no tokens")
    assert f.has_tokens is False
    assert f.resolve(DataRegistry()) == ("plain text, no tokens", False)


def test_declared_source_is_substituted():
    f = TokenizedField("now: :clock.now:!")
    reg = _reg(StaticSource(id="clock.now", value="9:01"))
    assert f.resolve(reg) == ("now: 9:01!", True)


def test_emoji_slug_is_preserved_not_substituted():
    # :heart: is an emoji slug, not a source — left intact for draw_with_emoji
    f = TokenizedField("love :heart: it")
    assert f.has_tokens is False           # emoji slugs are not source candidates
    assert f.resolve(_reg()) == ("love :heart: it", False)


def test_unknown_token_falls_through_to_literal():
    f = TokenizedField("hi :nope.x: bye")
    assert f.resolve(_reg()) == ("hi :nope.x: bye", False)


def test_changed_flips_only_on_version_move():
    s = StaticSource(id="x", value="a")
    reg = _reg(s)
    f = TokenizedField("v=:x:")
    assert f.resolve(reg) == ("v=a", True)     # first resolve: changed
    assert f.resolve(reg) == ("v=a", False)    # no version move: unchanged
    s.value = "b"; s.refresh()
    assert f.resolve(reg) == ("v=b", True)     # version moved: changed


def test_source_colliding_with_emoji_name_is_left_for_emoji():
    # If a name is an emoji slug, the pre-pass must NOT substitute it even
    # if a same-named source somehow exists (emoji wins).
    f = TokenizedField(":heart:")
    reg = _reg(StaticSource(id="heart", value="X"))
    assert f.resolve(reg) == (":heart:", False)
```

And in `tests/test_pixel_emoji.py`:

```python
from led_ticker.pixel_emoji import is_emoji_slug


def test_is_emoji_slug_true_for_builtin():
    assert is_emoji_slug("heart") is True


def test_is_emoji_slug_false_for_unknown():
    assert is_emoji_slug("clock.now") is False
```

- [ ] **Step 2: Run to verify fail** — `PYTHONPATH=tests/stubs uv run --extra dev pytest tests/test_sources.py tests/test_pixel_emoji.py -v` → FAIL.

- [ ] **Step 3: Add `is_emoji_slug` to `pixel_emoji.py`** (near `_get_registry`, ~line 2503):

```python
def is_emoji_slug(slug: str) -> bool:
    """True if `slug` (no surrounding colons) is a registered emoji."""
    return slug in _get_registry()
```

- [ ] **Step 4: Add `TokenizedField` to `sources.py`:**

```python
import re

from led_ticker.pixel_emoji import EMOJI_PATTERN, is_emoji_slug


class TokenizedField:
    """Compile-once template for one text field; substitutes declared-source
    tokens, leaves emoji/unknown/literal intact, and re-substitutes only when
    a referenced source's version moves.
    """

    def __init__(self, text: str) -> None:
        self._raw = text
        # Candidate source ids = :slug: tokens that are NOT emoji slugs.
        self._candidate_ids: list[str] = []
        for m in EMOJI_PATTERN.finditer(text):
            slug = m.group()[1:-1]
            if not is_emoji_slug(slug) and slug not in self._candidate_ids:
                self._candidate_ids.append(slug)
        self._last_versions: dict[str, int] = {}
        self._cached: str = text
        self._first: bool = True

    @property
    def has_tokens(self) -> bool:
        return bool(self._candidate_ids)

    def resolve(self, registry: "DataRegistry") -> tuple[str, bool]:
        if not self._candidate_ids:
            return self._raw, False
        versions = {
            cid: (s.version if (s := registry.get(cid)) is not None else -1)
            for cid in self._candidate_ids
        }
        if not self._first and versions == self._last_versions:
            return self._cached, False
        self._first = False
        self._last_versions = versions

        def _sub(match: "re.Match[str]") -> str:
            slug = match.group()[1:-1]
            if is_emoji_slug(slug):
                return match.group()           # emoji wins; leave intact
            src = registry.get(slug)
            return src.current if src is not None else match.group()

        self._cached = EMOJI_PATTERN.sub(_sub, self._raw)
        return self._cached, True
```

(Note: `import re`/`EMOJI_PATTERN` at module top of `sources.py`; the `DataRegistry` type hint is a forward ref string to avoid reordering. `import` of `pixel_emoji` from `sources` is core-internal and acceptable.)

- [ ] **Step 5: Run tests → PASS.**

- [ ] **Step 6: Gates + commit:**

```bash
git add src/led_ticker/sources.py src/led_ticker/pixel_emoji.py tests/test_sources.py tests/test_pixel_emoji.py
git commit -m "feat(sources): TokenizedField substitution + is_emoji_slug (emoji wins)"
```

---

## Task 3: `[[source]]` config parsing + the source-class factory + startup wiring

**Files:**
- Modify: `src/led_ticker/config.py` (add `SourceConfig`, add `sources` to `AppConfig`, parse `raw["source"]`)
- Modify: `src/led_ticker/app/factories.py` (`get_source_class`, the type registry mapping `"clock"/"date"/"static"`)
- Modify: `src/led_ticker/app/run.py` (build registry from `cfg.sources`, `set_data_registry`, `spawn_source_refresh`)
- Test: `tests/test_config.py` (add), `tests/test_sources.py` (factory)

**Interfaces:**
- Consumes: `ClockSource`/`DateSource`/`StaticSource` (Task 1), `set_data_registry`/`spawn_source_refresh` (Task 1).
- Produces: `SourceConfig` (`id: str`, `type: str`, `raw: dict`); `AppConfig.sources: list[SourceConfig]`; `get_source_class(type) -> type[DataSource]`; `build_source(SourceConfig) -> DataSource`.

- [ ] **Step 1: Write failing tests** in `tests/test_config.py`:

```python
import tomllib
from led_ticker.config import load_config_from_dict  # see note below


def test_source_block_parses_into_appconfig(tmp_path):
    toml = '''
[[source]]
id = "clock.now"
type = "clock"
format = "%H:%M"

[[playlist.section]]
mode = "slideshow"
'''
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text(toml)
    cfg = __import__("led_ticker.config", fromlist=["load_config"]).load_config(str(cfg_path))
    assert len(cfg.sources) == 1
    assert cfg.sources[0].id == "clock.now"
    assert cfg.sources[0].type == "clock"
    assert cfg.sources[0].raw["format"] == "%H:%M"


def test_no_source_block_yields_empty_list(tmp_path):
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text('[[playlist.section]]\nmode = "slideshow"\n')
    cfg = __import__("led_ticker.config", fromlist=["load_config"]).load_config(str(cfg_path))
    assert cfg.sources == []
```

And in `tests/test_sources.py` (factory builds the right class):

```python
from led_ticker.app.factories import get_source_class, build_source
from led_ticker.config import SourceConfig
from led_ticker.sources import ClockSource, StaticSource


def test_get_source_class_known_types():
    assert get_source_class("clock") is ClockSource
    assert get_source_class("static") is StaticSource


def test_build_source_clock_passes_format_and_tz():
    sc = SourceConfig(id="clock.now", type="clock",
                      raw={"id": "clock.now", "type": "clock", "format": "%H", "timezone": None})
    src = build_source(sc)
    assert isinstance(src, ClockSource)
    assert src.id == "clock.now" and src.fmt == "%H"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add `SourceConfig` + parse + `AppConfig.sources`** in `config.py`. Add the dataclass near the other config dataclasses:

```python
@dataclass
class SourceConfig:
    id: str
    type: str
    raw: dict = field(default_factory=dict)
```

Add `sources: list[SourceConfig] = field(default_factory=list)` to `AppConfig`. In `load_config`, before building `AppConfig`, parse the top-level array:

```python
sources = []
for i, source_raw in enumerate(raw.get("source", [])):
    if "id" not in source_raw or "type" not in source_raw:
        raise ValueError(f"[[source]][{i}] requires both 'id' and 'type'.")
    sources.append(
        SourceConfig(id=source_raw["id"], type=source_raw["type"], raw=source_raw)
    )
```

and pass `sources=sources` into the `AppConfig(...)` constructor.

- [ ] **Step 4: Add the factory** in `app/factories.py` (mirror `get_widget_class`):

```python
from led_ticker.sources import ClockSource, DateSource, StaticSource, DataSource
from led_ticker.config import SourceConfig

_SOURCE_TYPES: dict[str, type[DataSource]] = {
    "clock": ClockSource,
    "date": DateSource,
    "static": StaticSource,
}


def get_source_class(source_type: str) -> type[DataSource]:
    # Plugin source types (namespaced) merge in via the plugin registry — see
    # Task 4; this dict holds the core types.
    cls = _SOURCE_TYPES.get(source_type)
    if cls is None:
        raise ValueError(f"Unknown source type: {source_type!r}")
    return cls


def build_source(cfg: SourceConfig) -> DataSource:
    cls = get_source_class(cfg.type)
    if cls in (ClockSource, DateSource):
        return cls(id=cfg.id, fmt=cfg.raw.get("format", "%H:%M"),
                   tz=cfg.raw.get("timezone"))
    if cls is StaticSource:
        return cls(id=cfg.id, value=cfg.raw.get("value", ""))
    return cls(id=cfg.id)
```

- [ ] **Step 5: Wire startup** in `app/run.py`. Where the app builds widgets at startup, build the registry first (sources must exist before widgets resolve):

```python
from led_ticker.sources import DataRegistry, set_data_registry, spawn_source_refresh
from led_ticker.app.factories import build_source

registry = DataRegistry()
for source_cfg in cfg.sources:
    registry.add(build_source(source_cfg))
set_data_registry(registry)
spawn_source_refresh(registry)
```

(Read `app/run.py` to place this BEFORE widget construction + alongside the other `spawn_tracked` startup tasks. Constraint #13: this is pre-frame-build-safe — no privileged FS, just task spawn.)

- [ ] **Step 6: Run tests → PASS.** Gates. Commit:

```bash
git add src/led_ticker/config.py src/led_ticker/app/factories.py src/led_ticker/app/run.py tests/test_config.py tests/test_sources.py
git commit -m "feat(sources): [[source]] config parsing + factory + startup registry"
```

---

## Task 4: `api.source` plugin surface

**Files:**
- Modify: `src/led_ticker/plugin.py` (`"sources"` buffer, `source` decorator, `__all__`)
- Modify: `src/led_ticker/app/_plugin_loader.py` (commit the `"sources"` buffer into the source registry — find where `"easing"` etc. are committed)
- Modify: `src/led_ticker/app/factories.py` (merge plugin source types into `get_source_class` lookup)
- Test: `tests/test_plugin_api.py` (or the existing plugin-surface test file), and the plugin-API drift test + `docs/.../plugins/api-reference.mdx` if drift-guarded.

**Interfaces:**
- Consumes: the source registry (Task 3).
- Produces: `api.source(type)` decorator registering a `DataSource` subclass under `namespace.type`.

- [ ] **Step 1: Write failing test** in the plugin-surface test file:

```python
def test_api_source_registers_and_resolves():
    from led_ticker.plugin import PluginAPI
    from led_ticker.sources import DataSource
    api = PluginAPI(namespace="acme")

    @api.source("ticker")
    class _S(DataSource):
        def compute(self): return "x"

    assert "acme.ticker" in api._buffers["sources"]


def test_api_source_dup_rejected():
    from led_ticker.plugin import PluginAPI
    from led_ticker.sources import DataSource
    api = PluginAPI(namespace="acme")

    @api.source("dup")
    class _A(DataSource):
        def compute(self): return "a"

    import pytest
    with pytest.raises(Exception):
        @api.source("dup")
        class _B(DataSource):
            def compute(self): return "b"
```

(Match the EXACT `PluginAPI` constructor + dup-rejection mechanism used by the existing `api.widget`/`api.transition` tests — read them first; the dup behavior should mirror those surfaces.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add the surface** in `plugin.py`: add `"sources": {}` to the `_buffers` dict (~line 235); add a `source` decorator mirroring `widget`/`transition` (the class-registering shape, NOT the `easing` direct-call shape) ~after the `transition` method (~line 285):

```python
def source(self, name: str) -> Callable[[_T], _T]:
    """Register a DataSource subclass under ``namespace.name``."""
    def deco(cls: _T) -> _T:
        self._buffers["sources"][self._qualify(name)] = cls
        return cls
    return deco
```

Add `"source"` to `__all__`/the documented surface list as appropriate.

- [ ] **Step 4: Commit plugin sources into the registry.** In `app/_plugin_loader.py`, find the loop that commits `_buffers` surfaces into core registries (where `widgets`/`transitions`/`easing` land) and add `"sources"` → merge into the `_SOURCE_TYPES` map (or a parallel plugin-source dict consulted by `get_source_class`). Update `get_source_class` to consult the merged plugin types.

- [ ] **Step 5: Register core sources through the surface (optional consistency) OR keep the core `_SOURCE_TYPES` dict** — core clock/date/static may stay in the `_SOURCE_TYPES` literal (they're not plugins). Confirm `get_source_class` resolves both core literal types and plugin-registered namespaced types.

- [ ] **Step 6: Update the plugin-API drift test + docs** — if `tests/test_docs_plugin_api_drift.py` enumerates the `api.*` surfaces, add `source`; add `api.source` to `docs/site/.../plugins/api-reference.mdx`. Run that test.

- [ ] **Step 7: Run tests → PASS.** Gates. Commit:

```bash
git add -A
git commit -m "feat(plugin): api.source surface for live-value sources"
```

---

## Task 5: `message` (TickerMessage) integration + the resolution-freeze model

This task establishes the freeze mechanism (`_resolution_locked` + the `pause_frame`/`resume_frame` extension + the engine scroll-lock) that Tasks 6/7 reuse.

**Files:**
- Modify: `src/led_ticker/widgets/_frame_aware.py` (FrameAwareBase: `_resolution_locked`; `pause_frame`/`resume_frame` set/clear it)
- Modify: `src/led_ticker/widgets/message.py` (TickerMessage token wiring)
- Modify: `src/led_ticker/ticker.py` (scroll-branch: resolve once, lock for the loop)
- Test: `tests/test_widgets/test_message.py` (or where TickerMessage is tested), `tests/test_ticker_display.py` (the scroll + transition tripwires)

**Interfaces:**
- Consumes: `TokenizedField` (Task 2), `get_data_registry` (Task 1).
- Produces: the `_resolution_locked` contract: `pause_frame()`→locked, `resume_frame()`→unlocked; widgets re-resolve only when `not _resolution_locked`. A duck-typed engine helper `_lock_resolution_if_supported(widget, bool)` and `_resolve_now_if_supported(widget)`.

- [ ] **Step 1: Write failing tests.** Token render + held re-resolve:

```python
# tests/test_widgets/test_message.py
from led_ticker.widgets.message import TickerMessage
from led_ticker.sources import StaticSource, DataRegistry, set_data_registry
from led_ticker.fonts import ... # match existing test imports / a stub canvas fixture

def _registry(*srcs):
    r = DataRegistry()
    for s in srcs: s.refresh(); r.add(s)
    set_data_registry(r)
    return r

def test_message_substitutes_token_on_draw(stub_canvas):
    s = StaticSource(id="brand.tag", value="HELLO")
    _registry(s)
    w = TickerMessage(text="x :brand.tag: y")
    w.draw(stub_canvas)
    # assert the rendered pixels correspond to "x HELLO y" — use the existing
    # text-pixel assertion helper in this test file (stub DrawText writes pixels)

def test_message_rewidths_when_value_width_changes_while_held(stub_canvas):
    s = StaticSource(id="t", value="9:59")
    _registry(s)
    w = TickerMessage(text=":t:")
    w.draw(stub_canvas)
    first = w._content_width
    s.value = "10:000"; s.refresh()
    w.draw(stub_canvas)              # held redraw, not locked
    assert w._content_width != first  # re-measured
```

Scroll-freeze tripwire (C2) + transition-freeze tripwire (C1) in `tests/test_ticker_display.py` — model them on the existing scroll/transition tests in that file. The C2 assertion: a token value width change *during* a scroll does not alter the in-flight `stop_pos` (the scroll completes against the entry width; the new value applies next pass). The C1 assertion: with a widget as a transition participant, calling `pause_frame()` sets `_resolution_locked` so a `resolve()` during the transition returns the cached string even if the source version moved.

```python
def test_pause_frame_locks_resolution():
    from led_ticker.widgets.message import TickerMessage
    from led_ticker.sources import StaticSource, DataRegistry, set_data_registry
    r = DataRegistry(); s = StaticSource(id="t", value="a"); s.refresh(); r.add(s)
    set_data_registry(r)
    w = TickerMessage(text=":t:")
    w.draw(_stub())                      # cache "a"
    w.pause_frame()
    s.value = "bb"; s.refresh()          # version moves while locked
    w.draw(_stub())
    assert w._content_width == w._content_width  # width unchanged while locked
    # (assert the rendered text is still "a", not "bb")
    w.resume_frame()
    w.draw(_stub())
    # now "bb" applies
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Extend FrameAwareBase** (`widgets/_frame_aware.py`): add `_resolution_locked: bool = attrs.field(init=False, default=False)`. In `pause_frame()` set `self._resolution_locked = True`; in `resume_frame()` set it `False`. (Read the current methods first; keep the existing frame-counter behavior intact.)

- [ ] **Step 4: Wire TickerMessage** (`message.py`):
  - Add init field `_token: TokenizedField | None` built in `__attrs_post_init__`: `self._token = TokenizedField(self.text)`. Keep `_has_emoji` as-is (computed on the RAW text — emoji slugs survive substitution).
  - At the top of `draw`, before `full_text = self.text`, resolve when not locked:

```python
full_text = self.text
if self._token is not None and self._token.has_tokens:
    if not self._resolution_locked:
        resolved, changed = self._token.resolve(get_data_registry())
        if changed:
            self._content_width = -1   # re-measure (held re-center)
        self._resolved_text = resolved
    full_text = self._resolved_text
```

  - Store `_resolved_text: str` (init=False, default=""). Use `full_text` everywhere `self.text` currently feeds rendering/measurement — including `count_text_chars(...)` at line 166: change `total_chars=count_text_chars(self.text)` → `total_chars=count_text_chars(full_text)` (the I3 hue-anchor fix; the substituted string is the one rendered). Also the measurement branches that read `self.text` (lines 112/117) must use `full_text`.
  - **Typewriter freeze (message animation):** when `self.animation is not None` and the field has tokens, lock resolution for the reveal so the slice length is stable — set `self._resolution_locked = True` on the first animated draw of a visit and clear it when the animation completes / on visit reset. (Simplest: while an animation is active, do not re-resolve — gate the resolve on `self.animation is None or not _animation_active`.) Keep it minimal; the tripwire is `test_message_typewriter_token_stable`.

- [ ] **Step 5: Engine scroll-freeze** (`ticker.py`, `_swap_and_scroll` scroll branch). Read the scroll branch (around the `stop_pos` computation). Add duck-typed helpers near `_advance_frame_if_supported`:

```python
def _resolve_now_if_supported(widget):
    fn = getattr(widget, "resolve_tokens_now", None)
    if callable(fn):
        fn()

def _lock_resolution_if_supported(widget, locked):
    if hasattr(widget, "_resolution_locked"):
        widget._resolution_locked = locked
```

Add a `resolve_tokens_now()` method to token-bearing widgets that forces a resolve + width invalidate (so the scroll measures the fresh value). In the scroll branch: `_resolve_now_if_supported(widget)` BEFORE the width/`stop_pos` computation, then `_lock_resolution_if_supported(widget, True)` for the loop, and `_lock_resolution_if_supported(widget, False)` in a `finally`.

- [ ] **Step 6: Run tests → PASS.** Gates. Commit:

```bash
git add -A
git commit -m "feat(tokens): message integration + resolution-freeze (scroll/transition/typewriter)"
```

---

## Task 6: two_row integration

**Files:**
- Modify: `src/led_ticker/widgets/two_row.py`
- Test: `tests/test_widgets/test_two_row.py`

**Interfaces:**
- Consumes: `TokenizedField`, `get_data_registry`, the `_resolution_locked` contract (Task 5).
- Produces: per-row token resolution; invalidates BOTH `_content_width` and `_bottom_width`.

- [ ] **Step 1: Write failing tests** — a `top_text` token and a `bottom_text` token each resolve + render; and the bottom-row width tripwire: a bottom-row token whose value width changes (while held) invalidates `_bottom_width` and re-decides overflow on the next visit (read `two_row.py:163/488` for the `_bottom_width` cache + the `wraps_forever`/`forces_offscreen_scroll` reads).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — build a `TokenizedField` for each of `top_text` and `bottom_text` in `__attrs_post_init__`. In `draw`, when not `_resolution_locked`, resolve each; on `changed` invalidate the matching cache(s): a top change → `_content_width = -1`; a bottom change → `_bottom_width = -1` (AND `_content_width` if the top/bottom share a measure path — verify). Use the resolved strings everywhere the raw `top_text`/`bottom_text` feed measurement/rendering, including any `count_text_chars`/per-char anchor (mirror Task 5's fix). Overflow-mode (`wraps_forever`/`forces_offscreen_scroll`) reads happen at visit entry — document that a value crossing the threshold flips mode next visit (no code needed; it falls out of the engine reading these once per visit).

- [ ] **Step 4: Run → PASS.** Gates. Commit:

```bash
git add -A
git commit -m "feat(tokens): two_row integration (per-row + _bottom_width invalidation)"
```

---

## Task 7: image/gif overlay integration + typewriter freeze

**Files:**
- Modify: `src/led_ticker/widgets/_image_base.py`
- Test: `tests/test_widgets/test_image_base.py`

**Interfaces:**
- Consumes: `TokenizedField`, `get_data_registry`, the `_resolution_locked` contract.
- Produces: token resolution in the overlay text + bottom_text; typewriter reveal freeze; hue `total_chars` from the substituted string.

- [ ] **Step 1: Write failing tests** — a token in the image text overlay resolves + renders (use the existing `_play_with_text` / draw-text test harness in this file). The typewriter-freeze tripwire (I3): with `animation = "typewriter"` + a token, a value change mid-reveal does not corrupt the slice, and the per-char hue total is counted from the substituted string (find the `count_text_chars`/total_chars call in `_image_base.py`'s text-draw path and assert it uses the substituted text).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — `TokenizedField` for the overlay `text` and `bottom_text`; resolve when not locked; feed resolved strings to the draw/measure path; for `animation = "typewriter"` lock resolution for the reveal duration (mirror Task 5); count hue `total_chars` from the substituted string. (Constraint #10 still applies — the rebind logic is unchanged; you only change what STRING is drawn, not the canvas wiring.)

- [ ] **Step 4: Run → PASS.** Gates. Commit:

```bash
git add -A
git commit -m "feat(tokens): image/gif overlay integration + typewriter freeze"
```

---

## Task 8: hot-reload — atomic registry swap + refresh-ticker respawn

**Files:**
- Modify: `src/led_ticker/app/reload.py` (`_apply_reload`)
- Test: `tests/test_*reload*.py` (find the reload test file)

**Interfaces:**
- Consumes: `DataRegistry`, `set_data_registry`, `spawn_source_refresh` (Task 1), `build_source` (Task 3).
- Produces: reload rebuilds the registry atomically + respawns the 1 Hz ticker.

- [ ] **Step 1: Write failing tests** — `_apply_reload` with a changed `[[source]]` set: the new registry is fully built and swapped via `set_data_registry` (not mutated in place — assert the OLD registry object is not the one a post-reload `get_data_registry()` returns), and the old refresh ticker task is cancelled + a new one spawned. A removed referenced id → a surviving widget's token resolves to literal (covered by Task 2's behavior; assert at the reload level the registry lookup returns None).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — read `_apply_reload`. Where it rebuilds sections/widgets/schedule, add: build a NEW `DataRegistry` from the reloaded `cfg.sources`, `set_data_registry(new_reg)` (atomic global swap), cancel the stored source-refresh task, and `spawn_source_refresh(new_reg)` (store the new task handle the same way the schedule task is stored). Mirror the existing schedule-respawn pattern exactly.

- [ ] **Step 4: Run → PASS.** Gates. Commit:

```bash
git add -A
git commit -m "feat(tokens): hot-reload rebuilds source registry + respawns refresh ticker"
```

---

## Task 9: validate rules for `[[source]]`

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `AppConfig.sources` (Task 3), `is_emoji_slug` (Task 2), `get_source_class` (Tasks 3/4).

- [ ] **Step 1: Write failing tests** — one per rule: duplicate `id` → error; `id` equal to an emoji slug → error; unknown `type` → error; clock/date `format` that `strftime` rejects → error; `static` missing `value` → error; invalid `timezone` → error. NO warning for an undeclared token. Model on the existing validate-rule tests (`TestRule…` classes); add a new rule number following the current max.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** a `_check_sources` rule in `validate.py` consulting `cfg.sources`: collect ids (dup → error); for each, `is_emoji_slug(id)` → error; `type not in known source types` → error (use `get_source_class`, catch the ValueError); clock/date → try `datetime.now().strftime(format)` and catch/validate, and `ZoneInfo(tz)` for timezone; static → require `value`. Append issues via the existing rule-emitting pattern.

- [ ] **Step 4: Run → PASS.** Gates. Commit:

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "feat(validate): [[source]] rules (dup/collision/type/format/value/tz)"
```

---

## Task 10: docs + example config

**Files:**
- Create: `docs/site/src/content/docs/concepts/value-tokens.mdx`
- Modify: a config example (e.g. `config/config.example.toml`) — add a commented `[[source]]` block + a token in a message
- Modify: `docs/site/src/content/docs/reference/config-options.mdx` (the `[[source]]` block) + cross-links from `concepts/sections-and-modes.mdx` / the widget pages
- Test: `make docs-build` + `make docs-lint`; the config-options drift audit if it covers `[[source]]`

- [ ] **Step 1: Write the concept page** `value-tokens.mdx` (DOCS-STYLE): the `:source.id:` syntax, the three core source types with example `[[source]]` blocks, the emoji-wins / literal-fallback rule, that values update live (1 Hz; reflow only on change), and the v1 scope note (no weather yet). No "footgun" metaphor; no release-history framing.

- [ ] **Step 2: Add the example** `[[source]]` block + a token usage to a config example; add the reference-page entry.

- [ ] **Step 3: Build + lint** — `make docs-build` && `make docs-lint` → clean. If `tests/test_docs_config_options_drift.py` audits top-level config blocks, ensure `[[source]]` is reflected.

- [ ] **Step 4: Commit:**

```bash
git add -A
git commit -m "docs(tokens): value-tokens concept page + example + reference"
```

---

## Self-Review notes (for the executor)

- **Spec coverage:** §1 syntax→T2; §2 config→T3; §3 sources/registry/refresh/api.source→T1,T4; §4+§4a rendering+freeze→T5 (mechanism), T6/T7 (reuse); §5 validate→T9; §6 tests→spread across tasks; §7 docs→T10; hot-reload→T8.
- **Type consistency:** `DataSource`/`DataRegistry`/`TokenizedField`/`get_data_registry`/`build_source`/`get_source_class`/`is_emoji_slug` names are used identically across tasks.
- **The freeze tripwires (C1 transition, C2 scroll, I3 typewriter) are mandatory** — a widget task is not done until its tripwire passes. Do not weaken them.
- Several integration tasks (5–8) require reading the current function bodies (`_swap_and_scroll`, `_apply_reload`, the two_row/image draw paths) — the steps give the exact anchors + the new code; match the surrounding style.

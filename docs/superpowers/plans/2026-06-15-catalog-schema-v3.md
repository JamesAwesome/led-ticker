# Catalog Schema v3 — Typed Plugin Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Represent the whole plugin surface (widgets, transitions, emoji, +
recognized fonts/borders/color_providers/animations/easing) in the bundled plugin
catalog via a typed `provides` object, replacing the untyped flat list.

**Architecture:** Add a frozen attrs `PluginProvides` value object (Task 1), then
atomically flip the catalog to schema v3 — loader, JSON data, `Catalog.search`,
the two `plugin_cmd.py` consumers, and all test fixtures move together so the
suite stays green (Task 2). Finally document the schema (Task 3).

**Tech Stack:** Python 3.14, attrs, stdlib json + importlib.resources, pytest.

## Global Constraints

- Worktree: `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/catalog-schema-v3`, branch `feat/catalog-schema-v3` (based on `origin/main` @ 588db61). **Verify with `git branch --show-current` before any edit; abort if it prints `main`.**
- Run `make dev` in the worktree once before the first commit (installs pre-commit/pre-push hooks against the venv).
- Tests run with `PYTHONPATH=tests/stubs uv run pytest -q`.
- Lint/format: `uv run --extra dev ruff check src/ tests/` and `uv run --extra dev ruff format src/ tests/`. Ruff line length is 88.
- Types: `uv run --extra dev pyright src/`.
- `git add` every new file (check `git status` for `??` before committing).
- Commit trailer (every commit): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` plus the session trailer.
- No `from __future__ import annotations`.
- Fully-qualified surface names everywhere (e.g. `nyancat.forward`, not `forward`).
- `emoji` lists each slug once (covers the lo-res + hi-res pair); there is NO `hires_emoji` kind.

---

### Task 1: `PluginProvides` value object + helpers

**Files:**
- Modify: `src/led_ticker/plugins_catalog.py` (add `_SURFACE_KINDS`, `_PRIMARY_ORDER`, `PluginProvides` near the top, after the imports / before `CatalogSource`)
- Test: `tests/test_plugins/test_catalog.py`

**Interfaces:**
- Consumes: nothing (pure value object).
- Produces:
  - `_SURFACE_KINDS: tuple[str, ...]` = `("widgets","transitions","emoji","fonts","borders","color_providers","animations","easing")` (canonical/display order).
  - `_PRIMARY_ORDER: tuple[str, ...]` = `("widgets","transitions","color_providers","animations","borders","emoji","fonts","easing")` (install-hint priority).
  - `class PluginProvides` (frozen attrs) with tuple fields named exactly as `_SURFACE_KINDS`, each defaulting to `()`, and methods:
    - `all_names() -> tuple[str, ...]` — every name across kinds, in `_SURFACE_KINDS` order.
    - `is_empty() -> bool` — True when no names in any kind.
    - `groups() -> list[tuple[str, tuple[str, ...]]]` — `(kind_key, names)` for each non-empty kind, in `_SURFACE_KINDS` order.
    - `primary() -> tuple[str, str] | None` — `(kind_key, first_name)` of the first non-empty kind by `_PRIMARY_ORDER`, else `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins/test_catalog.py`:

```python
# --- PluginProvides value object ---

from led_ticker.plugins_catalog import PluginProvides


def test_provides_all_names_in_canonical_order():
    p = PluginProvides(
        widgets=("ns.w1", "ns.w2"),
        transitions=("ns.t1",),
        emoji=("ns.e1",),
    )
    assert p.all_names() == ("ns.w1", "ns.w2", "ns.t1", "ns.e1")


def test_provides_is_empty():
    assert PluginProvides().is_empty() is True
    assert PluginProvides(transitions=("ns.t",)).is_empty() is False


def test_provides_groups_skips_empty_kinds_in_order():
    p = PluginProvides(emoji=("ns.e",), widgets=("ns.w",))
    # widgets before emoji (canonical order), transitions omitted (empty)
    assert p.groups() == [("widgets", ("ns.w",)), ("emoji", ("ns.e",))]


def test_provides_primary_prefers_widgets_then_transitions():
    both = PluginProvides(widgets=("ns.w",), transitions=("ns.t",))
    assert both.primary() == ("widgets", "ns.w")
    trans_only = PluginProvides(transitions=("ns.t1", "ns.t2"))
    assert trans_only.primary() == ("transitions", "ns.t1")
    emoji_only = PluginProvides(emoji=("ns.ball",))
    assert emoji_only.primary() == ("emoji", "ns.ball")
    assert PluginProvides().primary() is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugins/test_catalog.py -q -k provides`
Expected: FAIL — `ImportError: cannot import name 'PluginProvides'`.

- [ ] **Step 3: Implement `PluginProvides`**

In `src/led_ticker/plugins_catalog.py`, after the existing imports and the
`_VALID_SOURCE_TYPES` line, add:

```python
# Every surface a plugin can register (see led_ticker.plugin PluginAPI).
# Canonical order = list/display order. `emoji` covers the lo-res + hi-res pair.
_SURFACE_KINDS = (
    "widgets",
    "transitions",
    "emoji",
    "fonts",
    "borders",
    "color_providers",
    "animations",
    "easing",
)

# Order the install hint picks a "primary" surface in (first non-empty wins).
_PRIMARY_ORDER = (
    "widgets",
    "transitions",
    "color_providers",
    "animations",
    "borders",
    "emoji",
    "fonts",
    "easing",
)


@attrs.define(frozen=True)
class PluginProvides:
    """The typed surface a catalog plugin contributes, grouped by kind.

    Each field is a tuple of fully-qualified ``namespace.name`` strings. Fields
    are named exactly as ``_SURFACE_KINDS`` so the loader can splat a dict in.
    """

    widgets: tuple[str, ...] = ()
    transitions: tuple[str, ...] = ()
    emoji: tuple[str, ...] = ()
    fonts: tuple[str, ...] = ()
    borders: tuple[str, ...] = ()
    color_providers: tuple[str, ...] = ()
    animations: tuple[str, ...] = ()
    easing: tuple[str, ...] = ()

    def all_names(self) -> tuple[str, ...]:
        """Every provided name across all kinds, in canonical order."""
        return tuple(
            name for kind in _SURFACE_KINDS for name in getattr(self, kind)
        )

    def is_empty(self) -> bool:
        return not self.all_names()

    def groups(self) -> list[tuple[str, tuple[str, ...]]]:
        """Non-empty ``(kind, names)`` pairs in canonical order (for display)."""
        return [
            (kind, getattr(self, kind))
            for kind in _SURFACE_KINDS
            if getattr(self, kind)
        ]

    def primary(self) -> tuple[str, str] | None:
        """The ``(kind, first_name)`` for the install hint, by priority order."""
        for kind in _PRIMARY_ORDER:
            names = getattr(self, kind)
            if names:
                return (kind, names[0])
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugins/test_catalog.py -q -k provides`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + typecheck**

Run: `uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/ && uv run --extra dev pyright src/`
Expected: all clean, 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/plugins_catalog.py tests/test_plugins/test_catalog.py
git commit -m "feat(catalog): PluginProvides typed-surface value object

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Schema-v3 flip — loader, JSON migration, search, CLI consumers, fixtures

This is the atomic flip: `CatalogEntry.provides` changes type, so the loader,
the bundled JSON, `Catalog.search`, both `plugin_cmd.py` consumers, and all test
fixtures must change together to keep the suite green.

**Files:**
- Modify: `src/led_ticker/plugins_catalog.py` (`SCHEMA_VERSION`, `CatalogEntry.provides` type, `Catalog.search`, new `_parse_provides`, `_parse_entry`)
- Modify: `src/led_ticker/plugins_catalog.json` (all 10 entries → typed `provides`, `schema_version: 3`)
- Modify: `src/led_ticker/app/plugin_cmd.py` (`cmd_list` grouped render; `cmd_install` kind-aware hint; add `_KIND_LABELS`, `_install_hint`)
- Test: `tests/test_plugins/test_catalog.py`, `tests/test_plugins/test_plugin_cli.py`

**Interfaces:**
- Consumes: `PluginProvides`, `_SURFACE_KINDS` (Task 1).
- Produces:
  - `SCHEMA_VERSION = 3`.
  - `CatalogEntry.provides: PluginProvides`.
  - `_parse_provides(raw: object) -> PluginProvides`.
  - `plugin_cmd._install_hint(kind: str, name: str) -> str` and `plugin_cmd._KIND_LABELS: dict[str, str]`.

- [ ] **Step 1: Write the failing loader/integrity tests**

In `tests/test_plugins/test_catalog.py`, **replace** the bodies of the existing
`test_split_families_provide_their_types`, `test_pool_provides_monitor`, and
`test_baseball_provides_all_current_widgets` with the typed-shape versions below,
and add the new tests:

```python
def test_split_families_provide_their_types():
    cat = load_catalog()
    assert cat.get("rss").provides.widgets == ("rss.feed",)
    assert cat.get("weather").provides.widgets == ("weather.current",)
    for fam in ("nyancat", "pokeball", "pacman", "sailor_moon"):
        prov = cat.get(fam).provides
        assert prov.widgets == ()  # transition-only plugins
        assert set(prov.transitions) == {
            f"{fam}.forward", f"{fam}.reverse", f"{fam}.alternating"
        }


def test_pool_provides_monitor():
    cat = load_catalog()
    assert cat.get("pool").provides.widgets == ("pool.monitor",)


def test_baseball_provides_full_typed_surface():
    cat = load_catalog()
    prov = cat.get("baseball").provides
    assert set(prov.widgets) == {
        "baseball.scores",
        "baseball.standings",
        "baseball.promotions",
        "baseball.statcast",
        "baseball.attendance",
    }
    assert set(prov.transitions) == {
        "baseball.roll",
        "baseball.roll_reverse",
        "baseball.roll_alternating",
    }
    assert prov.emoji == ("baseball.ball",)


def test_pokeball_provides_transitions_and_emoji():
    prov = load_catalog().get("pokeball").provides
    assert set(prov.transitions) == {
        "pokeball.forward",
        "pokeball.reverse",
        "pokeball.alternating",
    }
    assert prov.emoji == ("pokeball.ball",)


def test_schema_version_is_3():
    from led_ticker.plugins_catalog import SCHEMA_VERSION

    assert SCHEMA_VERSION == 3


def test_parse_provides_valid_multi_kind():
    from led_ticker.plugins_catalog import _parse_provides

    p = _parse_provides(
        {"widgets": ["a.w"], "transitions": ["a.t"], "emoji": ["a.e"]}
    )
    assert p.widgets == ("a.w",)
    assert p.transitions == ("a.t",)
    assert p.emoji == ("a.e",)


def test_parse_provides_absent_is_empty():
    from led_ticker.plugins_catalog import _parse_provides

    assert _parse_provides(None).is_empty() is True


def test_parse_provides_rejects_non_dict():
    from led_ticker.plugins_catalog import _parse_provides

    with pytest.raises(ValueError, match="must be an object"):
        _parse_provides(["a.w"])


def test_parse_provides_rejects_unknown_kind():
    from led_ticker.plugins_catalog import _parse_provides

    with pytest.raises(ValueError, match="unknown surface kind"):
        _parse_provides({"widgetz": ["a.w"]})


def test_parse_provides_rejects_non_string_list():
    from led_ticker.plugins_catalog import _parse_provides

    with pytest.raises(ValueError, match="list of strings"):
        _parse_provides({"widgets": [123]})


def test_search_finds_each_kind():
    cat = load_catalog()
    assert "baseball" in {e.name for e in cat.search("attendance")}  # widget
    assert "baseball" in {e.name for e in cat.search("roll")}  # transition
    assert "baseball" in {e.name for e in cat.search("baseball.ball")}  # emoji
    assert "nyancat" in {e.name for e in cat.search("nyancat.forward")}  # trans-only
```

Also update the older provides-shaped assertions already in the file:
- In `test_get_and_search_case_insensitive`, leave the `search("MLB")` /
  `search("POOL")` lines as-is (they match name/summary).
- `test_search_matches_provides` currently asserts `search("coingecko")` finds
  crypto — keep it; `coingecko` is in `crypto.coingecko` (a widget name) so it
  stays in the haystack via `all_names()`.
- Delete the now-superseded `test_search_finds_new_baseball_widgets_and_surfaces`
  (replaced by `test_search_finds_each_kind`).

- [ ] **Step 2: Update the `CatalogEntry`/fixture constructors in both test files**

Every `CatalogEntry(..., provides=(...))` literal must become
`provides=PluginProvides(...)`. Make these exact edits:

In `tests/test_plugins/test_catalog.py`:
- `_git_entry()` → `provides=PluginProvides(widgets=("pool.monitor",)),`
- `test_requirement_git_with_subdirectory`'s entry → `provides=PluginProvides(widgets=("rss.feed",)),`
- Ensure `from led_ticker.plugins_catalog import PluginProvides` is present (added in Task 1 Step 1).

In `tests/test_plugins/test_plugin_cli.py`:
- Add to the imports at top: `from led_ticker.plugins_catalog import PluginProvides` (alongside the existing `Catalog, CatalogEntry, CatalogSource` import).
- `_catalog()` pool entry → `provides=PluginProvides(widgets=("pool.monitor",)),`
- `_entry(name)` helper → `provides=PluginProvides(widgets=(f"{name}.thing",)),`

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_plugins/test_catalog.py -q -k "schema_version or parse_provides or full_typed or pokeball or split_families or search_finds_each or pool_provides"`
Expected: FAIL — `SCHEMA_VERSION` still 2 / `_parse_provides` missing / `.provides.widgets` AttributeError (provides is still a tuple).

- [ ] **Step 4: Flip the loader to v3**

In `src/led_ticker/plugins_catalog.py`:

(a) Bump the version:

```python
SCHEMA_VERSION = 3
```

(b) Change the `CatalogEntry.provides` field type from
`provides: tuple[str, ...]` to:

```python
    provides: PluginProvides
```

(c) Replace `Catalog.search`'s haystack line. Change:

```python
            haystack = " ".join([entry.name, entry.summary, *entry.provides]).lower()
```

to:

```python
            haystack = " ".join(
                [entry.name, entry.summary, *entry.provides.all_names()]
            ).lower()
```

(d) Add `_parse_provides` just above `_parse_entry`:

```python
def _parse_provides(raw: object) -> PluginProvides:
    """Parse the typed `provides` object. Rejects a non-object, unknown surface
    kinds (typo guard), and non-string entries. Absent/None -> all-empty."""
    if raw is None:
        return PluginProvides()
    if not isinstance(raw, dict):
        raise ValueError(
            f"catalog entry 'provides' must be an object, got {type(raw).__name__}"
        )
    unknown = [k for k in raw if k not in _SURFACE_KINDS]
    if unknown:
        raise ValueError(
            f"catalog 'provides' has unknown surface kind(s) {sorted(unknown)} "
            f"(valid: {list(_SURFACE_KINDS)})"
        )
    kwargs: dict[str, tuple[str, ...]] = {}
    for kind in _SURFACE_KINDS:
        vals = raw.get(kind, [])
        if not isinstance(vals, list) or not all(isinstance(v, str) for v in vals):
            raise ValueError(f"catalog 'provides.{kind}' must be a list of strings")
        kwargs[kind] = tuple(vals)
    return PluginProvides(**kwargs)
```

(e) In `_parse_entry`, change:

```python
        provides=tuple(raw.get("provides", [])),
```

to:

```python
        provides=_parse_provides(raw.get("provides")),
```

- [ ] **Step 5: Migrate the bundled JSON to v3**

Overwrite `src/led_ticker/plugins_catalog.json` with (whole file):

```json
{
  "schema_version": 3,
  "plugins": [
    {
      "name": "pool",
      "namespace": "pool",
      "summary": "Pool water temperature from InfluxDB v2 (ticker / two_row layouts).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pool",
      "provides": { "widgets": ["pool.monitor"] },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "pool-v0.1.0", "subdirectory": "plugins/pool" }
      ]
    },
    {
      "name": "baseball",
      "namespace": "baseball",
      "summary": "MLB scores, standings, promotions, statcast & attendance widgets, baseball.roll* transitions, and the :baseball.ball: emoji.",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/baseball",
      "provides": {
        "widgets": ["baseball.scores", "baseball.standings", "baseball.promotions", "baseball.statcast", "baseball.attendance"],
        "transitions": ["baseball.roll", "baseball.roll_reverse", "baseball.roll_alternating"],
        "emoji": ["baseball.ball"]
      },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "baseball-v0.1.0", "subdirectory": "plugins/baseball" }
      ]
    },
    {
      "name": "crypto",
      "namespace": "crypto",
      "summary": "CoinGecko cryptocurrency price ticker.",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/crypto",
      "provides": { "widgets": ["crypto.coingecko"] },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "crypto-v0.1.0", "subdirectory": "plugins/crypto" }
      ]
    },
    {
      "name": "calendar",
      "namespace": "calendar",
      "summary": "Calendar (.ics) agenda/next/two_row widget.",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/calendar",
      "provides": { "widgets": ["calendar.events"] },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "calendar-v0.1.0", "subdirectory": "plugins/calendar" }
      ]
    },
    {
      "name": "rss",
      "namespace": "rss",
      "summary": "RSS/Atom feed headlines (rss.feed).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/rss",
      "provides": { "widgets": ["rss.feed"] },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "rss-v0.2.0", "subdirectory": "plugins/rss" }
      ]
    },
    {
      "name": "weather",
      "namespace": "weather",
      "summary": "Current-conditions weather widget using WeatherAPI.com (weather.current).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/weather",
      "provides": { "widgets": ["weather.current"] },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "weather-v0.2.0", "subdirectory": "plugins/weather" }
      ]
    },
    {
      "name": "nyancat",
      "namespace": "nyancat",
      "summary": "Nyan Cat sprite-trail transitions (nyancat.forward/.reverse/.alternating; hi-res).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/nyancat",
      "provides": { "transitions": ["nyancat.forward", "nyancat.reverse", "nyancat.alternating"] },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "nyancat-v0.1.0", "subdirectory": "plugins/nyancat" }
      ]
    },
    {
      "name": "pokeball",
      "namespace": "pokeball",
      "summary": "Pokeball/Pikachu sprite-trail transitions (pokeball.forward/.reverse/.alternating; hi-res) and the :pokeball.ball: emoji.",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pokeball",
      "provides": {
        "transitions": ["pokeball.forward", "pokeball.reverse", "pokeball.alternating"],
        "emoji": ["pokeball.ball"]
      },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "pokeball-v0.1.0", "subdirectory": "plugins/pokeball" }
      ]
    },
    {
      "name": "pacman",
      "namespace": "pacman",
      "summary": "Pac-Man sprite-trail transitions (pacman.forward/.reverse/.alternating).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pacman",
      "provides": { "transitions": ["pacman.forward", "pacman.reverse", "pacman.alternating"] },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "pacman-v0.1.0", "subdirectory": "plugins/pacman" }
      ]
    },
    {
      "name": "sailor_moon",
      "namespace": "sailor_moon",
      "summary": "Sailor Moon sprite-trail transitions (sailor_moon.forward/.reverse/.alternating).",
      "homepage": "https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/sailor_moon",
      "provides": { "transitions": ["sailor_moon.forward", "sailor_moon.reverse", "sailor_moon.alternating"] },
      "sources": [
        { "type": "git", "url": "https://github.com/JamesAwesome/led-ticker-plugins", "ref": "sailor_moon-v0.1.0", "subdirectory": "plugins/sailor_moon" }
      ]
    }
  ]
}
```

- [ ] **Step 6: Update the `plugin_cmd.py` consumers**

In `src/led_ticker/app/plugin_cmd.py`:

(a) Add module-level helpers (near the top, after the imports):

```python
_KIND_LABELS = {
    "widgets": "widgets",
    "transitions": "transitions",
    "emoji": "emoji",
    "fonts": "fonts",
    "borders": "borders",
    "color_providers": "color providers",
    "animations": "animations",
    "easing": "easing",
}


def _install_hint(kind: str, name: str) -> str:
    """The 'how to use it' clause for an install success message, by surface kind."""
    if kind == "widgets":
        return f'Add  type = "{name}"  to a widget section,'
    if kind == "transitions":
        return f'Use  transition = "{name}"  in a section,'
    if kind == "color_providers":
        return f'Use  font_color = {{ style = "{name}" }}  on a widget,'
    if kind == "animations":
        return f'Use  animation = "{name}"  on a widget,'
    if kind == "borders":
        return f'Use  border = "{name}"  on a widget,'
    if kind == "emoji":
        return f"Use  :{name}:  inline in widget text,"
    if kind == "fonts":
        return f'Use  font = "{name}"  on a widget,'
    return f'Use  easing = "{name}"  on a transition,'  # easing
```

(b) In `cmd_list`, replace:

```python
        print(f"  {entry.name}{suffix} — {entry.summary}")
        if entry.provides:
            print(f"      provides: {', '.join(entry.provides)}")
```

with:

```python
        print(f"  {entry.name}{suffix} — {entry.summary}")
        for kind, names in entry.provides.groups():
            shown = [f":{n}:" for n in names] if kind == "emoji" else list(names)
            print(f"      {_KIND_LABELS[kind]}: {', '.join(shown)}")
```

(c) In `cmd_install`, replace the success block:

```python
    if entry is not None and entry.provides:
        print(
            f'Installed. Add e.g.  type = "{entry.provides[0]}"  to a widget '
            "section, then restart led-ticker."
        )
    else:
        print("Installed. Restart led-ticker to load the plugin.")
    return 0
```

with:

```python
    primary = entry.provides.primary() if entry is not None else None
    if primary is not None:
        kind, name = primary
        print(f"Installed. {_install_hint(kind, name)} then restart led-ticker.")
    else:
        print("Installed. Restart led-ticker to load the plugin.")
    return 0
```

- [ ] **Step 7: Write the CLI consumer tests**

Append to `tests/test_plugins/test_plugin_cli.py`:

```python
def test_cmd_list_groups_by_kind(capsys):
    cat = Catalog(
        entries=(
            CatalogEntry(
                name="baseball",
                namespace="baseball",
                summary="MLB stuff",
                homepage="",
                provides=PluginProvides(
                    widgets=("baseball.scores",),
                    transitions=("baseball.roll",),
                    emoji=("baseball.ball",),
                ),
                sources=(
                    CatalogSource(type="git", url="https://h/o/r", ref="main"),
                ),
            ),
        )
    )
    plugin_cmd.cmd_list(catalog=cat)
    out = capsys.readouterr().out
    assert "widgets: baseball.scores" in out
    assert "transitions: baseball.roll" in out
    assert "emoji: :baseball.ball:" in out  # emoji shown in :slug: form


def _install_only_catalog(provides):
    return Catalog(
        entries=(
            CatalogEntry(
                name="x",
                namespace="x",
                summary="x",
                homepage="",
                provides=provides,
                sources=(CatalogSource(type="git", url="https://h/o/x", ref="main"),),
            ),
        )
    )


def test_install_hint_widget(tmp_path, fakepip, capsys):
    cat = _install_only_catalog(PluginProvides(widgets=("x.thing",)))
    plugin_cmd.cmd_install("x", config_path=tmp_path / "config.toml", catalog=cat)
    assert 'type = "x.thing"' in capsys.readouterr().out


def test_install_hint_transition_only(tmp_path, fakepip, capsys):
    cat = _install_only_catalog(PluginProvides(transitions=("x.forward",)))
    plugin_cmd.cmd_install("x", config_path=tmp_path / "config.toml", catalog=cat)
    out = capsys.readouterr().out
    assert 'transition = "x.forward"' in out
    assert "type =" not in out  # the old bug: must NOT call a transition a widget type


def test_install_hint_emoji_only(tmp_path, fakepip, capsys):
    cat = _install_only_catalog(PluginProvides(emoji=("x.ball",)))
    plugin_cmd.cmd_install("x", config_path=tmp_path / "config.toml", catalog=cat)
    assert ":x.ball:" in capsys.readouterr().out
```

- [ ] **Step 8: Run the full suite**

Run: `PYTHONPATH=tests/stubs uv run pytest -q`
Expected: PASS (all tests; the catalog + CLI tests now reflect v3).

- [ ] **Step 9: Lint + typecheck + validate JSON**

Run:
```bash
python3 -m json.tool src/led_ticker/plugins_catalog.json > /dev/null && echo "JSON OK"
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format src/ tests/
uv run --extra dev pyright src/
```
Expected: `JSON OK`, ruff clean, pyright 0 errors.

- [ ] **Step 10: Eyeball the CLI output**

Run: `PYTHONPATH=tests/stubs uv run led-ticker plugin list 2>/dev/null | sed -n '1,40p'`
Expected: baseball shows `widgets:` / `transitions:` / `emoji: :baseball.ball:` lines; nyancat shows only a `transitions:` line.

Run: `PYTHONPATH=tests/stubs uv run led-ticker plugin install nyancat --dry-run 2>/dev/null`
Expected: dry-run (no install). (The kind-aware hint only prints on a real install; the dry-run path is unchanged — this just confirms no crash.)

- [ ] **Step 11: Commit**

```bash
git add src/led_ticker/plugins_catalog.py src/led_ticker/plugins_catalog.json src/led_ticker/app/plugin_cmd.py tests/test_plugins/test_catalog.py tests/test_plugins/test_plugin_cli.py
git commit -m "feat(catalog): schema v3 — typed provides surface + grouped list/kind-aware install hint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Document the catalog schema in `docs/plugin-system.md`

**Files:**
- Modify: `docs/plugin-system.md` (add a subsection under §8 "Discovery, CLI, deployment")

**Interfaces:**
- Consumes: nothing (documentation).
- Produces: nothing code-facing.

- [ ] **Step 1: Read the current §8 to find the insertion point**

Run: `sed -n '/^## 8\./,/^## 9\./p' docs/plugin-system.md`
Expected: prints §8 "Discovery, CLI, deployment" through the start of §9. Note the
last line of §8 before `## 9.` — the new subsection goes immediately before `## 9.`.

- [ ] **Step 2: Add the catalog-schema subsection**

Insert this block at the end of §8 (immediately before the `## 9.` heading):

```markdown
### The plugin catalog (`plugins_catalog.json`)

`src/led_ticker/plugins_catalog.json` is the bundled, offline source of truth for
`led-ticker plugin list / search / install`. It is loaded and validated by
`load_catalog()` in `src/led_ticker/plugins_catalog.py`. Current
`schema_version` is **3**.

Each entry:

| field        | meaning                                                                 |
| ------------ | ----------------------------------------------------------------------- |
| `name`       | friendly plugin name (the CLI argument, e.g. `baseball`)                |
| `namespace`  | the plugin's registration namespace (`<namespace>.<surface>`)           |
| `summary`    | one-line human description (also part of the `search` haystack)         |
| `homepage`   | URL shown for reference                                                  |
| `provides`   | the typed surface object (below)                                         |
| `sources`    | install sources — `git` (`url` + `ref` + optional `subdirectory`) and/or `pypi` (`package` + optional `version`) |

`provides` is an **object keyed by surface kind** — the full set the plugin API
can register: `widgets`, `transitions`, `emoji`, `fonts`, `borders`,
`color_providers`, `animations`, `easing`. Every key is optional; values are
arrays of fully-qualified `namespace.name` strings. A hi-res emoji is listed once
under `emoji` by its slug (the lo-res + hi-res pair share it) — there is no
`hires_emoji` key. An unknown key fails the load (typo guard).

```json
"provides": {
  "widgets": ["baseball.scores", "baseball.standings"],
  "transitions": ["baseball.roll", "baseball.roll_reverse"],
  "emoji": ["baseball.ball"]
}
```

The typed surface drives three things: `plugin list` prints one grouped line per
non-empty kind (emoji shown as `:slug:`); `search` matches over name, summary, and
every provided name across kinds; and `plugin install` prints a **kind-aware**
"how to use it" hint (a widget → `type = "…"`, a transition → `transition = "…"`,
an emoji → `:…:`, etc.) chosen from the first non-empty kind by priority.

**Refreshing an entry:** read the plugin's `register(api)` (its
`src/<pkg>/__init__.py` in the `led-ticker-plugins` monorepo) and list each
registered surface under its kind — `api.widget("x")` → `widgets: ["<ns>.x"]`,
`api.transition("x")` → `transitions: ["<ns>.x"]`, `api.emoji("x", …)` →
`emoji: ["<ns>.x"]`, and so on. The bundled JSON is guarded by
`tests/test_plugins/test_catalog.py`.
```

- [ ] **Step 3: Verify it reads correctly**

Run: `sed -n '/### The plugin catalog/,/^## 9\./p' docs/plugin-system.md`
Expected: the new subsection prints in full, ending right before `## 9.`.

- [ ] **Step 4: Commit**

```bash
git add docs/plugin-system.md
git commit -m "docs(plugins): document the catalog schema (v3 typed provides)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] `PYTHONPATH=tests/stubs uv run pytest -q` — full suite green.
- [ ] `uv run --extra dev ruff check src/ tests/` — clean.
- [ ] `uv run --extra dev ruff format --check src/ tests/` — clean.
- [ ] `uv run --extra dev pyright src/` — 0 errors.
- [ ] `python3 -m json.tool src/led_ticker/plugins_catalog.json > /dev/null` — valid JSON.
- [ ] `git status` shows no untracked (`??`) files.
- [ ] Push and open a PR against `main`; wait for CI green before requesting merge.

## Notes / gotchas

- The schema flip in Task 2 is atomic: do not commit between changing
  `SCHEMA_VERSION` and migrating the JSON + fixtures, or the suite goes red.
- `docs/plugin-system.md` lives at the repo root `docs/`, NOT `docs/site/`, so the
  `docs-lint` (prettier + astro) hook does not apply to it.
- `cmd_install`'s kind-aware hint only prints on a *real* install (the `--dry-run`
  and pip-failure paths are unchanged).
- Do not touch `sources`, `requirement()`, `_requirement_key`, or `_dist_key` —
  only the `provides` representation and its three consumers change.
```

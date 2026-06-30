# Flag plugin dependencies in example configs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every example config's plugin dependency machine-checkable and enforced, and warn at startup when a deployed config references plugins that aren't installed.

**Architecture:** A new pure module `src/led_ticker/_config_scan.py` holds the existing `config_references` walk (moved verbatim) plus `required_plugins()` (catalog-derived namespace→package map + the deploy-relevant surfaces the Store walk doesn't need) and `plugin_dependency_warning()`. `app/run.py` logs the warning at startup; a tripwire test pins each example's `# requires-plugins:` header to its derived dependencies.

**Tech Stack:** Python 3.14, `tomllib`, pytest, the existing `plugins_catalog` + `webui/store` + `_plugin_loader` modules.

**Spec:** `docs/superpowers/specs/2026-06-29-example-config-plugin-flags-design.md` (twice robustness-reviewed).

## Global Constraints

- Python 3.14. **No `from __future__ import annotations`** in any source (PEP 649 rule, core + plugins).
- `src/led_ticker/_config_scan.py` **must not** import `webui` or anything pulling in `aiohttp`/`rgbmatrix` — the display process imports it. Allowed imports: stdlib (`re`, `tomllib`, `pathlib`, `logging`, `collections.abc`), `led_ticker.plugins_catalog`, `led_ticker.app.plugin_cmd`.
- `config_references` behaviour stays **identical** (verbatim move): existing `tests/test_webui_store.py`, `tests/test_webui_purity.py`, `tests/test_webui_app.py` must pass unchanged.
- The catalog filter lives **only** in `required_plugins`. The shared `config_references` walk stays unfiltered (the Store needs non-catalog namespaces for `in_use_by`).
- Namespace→package is derived from `load_catalog()` via `_requirement_key(e.requirement())` — **no hand-maintained map**.
- Header canonical form: pip package names, lowercase, sorted, `", "`-separated; literal `none` for no deps. Line: `# requires-plugins: <packages|none>`.
- Before finishing: `uv run --extra dev ruff check src/ tests/` is clean, and `make test` passes.
- Work on branch `feat/example-config-plugin-flags` (already created). Never commit to `main`.

---

### Task 1: Extract `config_references` into a pure shared module

A behaviour-preserving move so the display process can scan configs without importing `webui`/aiohttp. Guarded by the existing Store tests.

**Files:**
- Create: `src/led_ticker/_config_scan.py`
- Modify: `src/led_ticker/webui/store.py:1-66` (remove the moved code; re-export `config_references`)
- Test: existing `tests/test_webui_store.py`, `tests/test_webui_purity.py`

**Interfaces:**
- Produces: `config_references(config_path: Path) -> dict[str, list[dict[str, str]]]` (unchanged signature) and an internal `_references_from_data(data: dict) -> dict[str, list[dict[str, str]]]` for reuse by Task 2.

- [ ] **Step 1: Baseline — confirm the existing tests pass before moving anything**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker-pluginflags && uv run pytest tests/test_webui_store.py tests/test_webui_purity.py -q`
Expected: PASS (this is the safety net for the move).

- [ ] **Step 2: Create `src/led_ticker/_config_scan.py` with the moved walk**

```python
"""Static analysis of a config's plugin dependencies — no widget build, no
rgbmatrix, no HTTP. Holds the Store's config_references walk plus
required_plugins() and the startup dependency warning. Pure; safe to import
from the display process (must not import webui/aiohttp)."""

import re
import tomllib
from collections.abc import Iterable
from pathlib import Path

from led_ticker.app.plugin_cmd import _requirement_key
from led_ticker.plugins_catalog import load_catalog

_TRANSITION_KEYS = ("transition", "entry_transition", "widget_transition")

# Inline emoji token in widget text, e.g. ":pokeball.ball:". A namespaced slug
# carries a dot; the namespace is the leading segment.
_EMOJI_TOKEN = re.compile(r":([a-z0-9_]+)\.[a-z0-9_.]+:")


def _references_from_data(data: dict) -> dict[str, list[dict[str, str]]]:
    """The recursive reference walk over already-parsed TOML. Returns
    {namespace: [{"section", "type"}, ...]} for every dotted type/transition
    value and inline :ns.slug: emoji. UNFILTERED — includes non-catalog
    namespaces (the Store needs them for in_use_by)."""
    out: dict[str, list[dict[str, str]]] = {}

    def add(ns_source: str, section: str) -> None:
        if "." in ns_source:
            ns = ns_source.split(".")[0]
            out.setdefault(ns, []).append({"section": section, "type": ns_source})

    def add_emoji_refs(text: str, section: str) -> None:
        for m in _EMOJI_TOKEN.finditer(text):
            out.setdefault(m.group(1), []).append(
                {"section": section, "type": m.group(0)}
            )

    def walk(obj: object, section: str) -> None:
        if isinstance(obj, dict):
            title = obj.get("title")
            sec = title.get("text") if isinstance(title, dict) else section
            sec = sec if isinstance(sec, str) and sec else section
            t = obj.get("type")
            if isinstance(t, str):
                add(t, sec)
            for key in _TRANSITION_KEYS:
                v = obj.get(key)
                if isinstance(v, str):
                    add(v, sec)
            for v in obj.values():
                if isinstance(v, str):
                    add_emoji_refs(v, sec)
                walk(v, sec)
        elif isinstance(obj, list):
            for v in obj:
                if isinstance(v, str):
                    add_emoji_refs(v, section)
                walk(v, section)

    walk(data, "config")
    return out


def config_references(config_path: Path) -> dict[str, list[dict[str, str]]]:
    """Plugin references in a config file, keyed by namespace. Used by the web
    Store. Missing/unparseable file -> {}."""
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    return _references_from_data(data)
```

- [ ] **Step 3: Update `src/led_ticker/webui/store.py` to import from the new module**

Remove the moved lines (the `import re`, `_TRANSITION_KEYS`, `_EMOJI_TOKEN`, and the whole `config_references` function — `store.py:7,15-66` in the current file). Keep `import tomllib` only if still used elsewhere in `store.py` (it is — leave other imports alone). Add at the top of the import block:

```python
from led_ticker._config_scan import config_references
```

Leave `_active_namespaces` and `build_store` (and their `config_references(config_path)` call at the old line ~110) untouched — the name now resolves to the imported one.

- [ ] **Step 4: Verify the move changed no behaviour**

Run: `uv run pytest tests/test_webui_store.py tests/test_webui_purity.py tests/test_webui_app.py -q`
Expected: PASS (same as the Step 1 baseline). `test_webui_purity.py` confirms `_config_scan` pulled in no `rgbmatrix`.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/_config_scan.py src/led_ticker/webui/store.py
git commit --no-verify -m "refactor: extract config_references into pure _config_scan module"
```

---

### Task 2: `required_plugins()` — catalog-derived map + deploy surfaces

Adds the dependency derivation: the namespaces `config_references` finds, **plus** the two deploy-relevant surfaces the Store walk omits (top-level `[transitions]`, `[display] backend`), filtered to catalog plugins and mapped to pip packages.

**Files:**
- Modify: `src/led_ticker/_config_scan.py` (append helpers)
- Test: Create `tests/test_example_config_plugin_flags.py`

**Interfaces:**
- Consumes: `_references_from_data` (Task 1), `load_catalog`, `_requirement_key`.
- Produces: `required_plugins(source: dict | str | Path) -> set[str]`; `_namespace_to_package() -> dict[str, str]`; `_referenced_namespaces(data: dict) -> set[str]`; `_load(source: str | Path) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_example_config_plugin_flags.py`:

```python
import tomllib

from led_ticker._config_scan import required_plugins


def _cfg(toml: str) -> dict:
    return tomllib.loads(toml)


def test_plugin_free_is_empty():
    assert required_plugins(_cfg('[display]\nrows = 16\n')) == set()


def test_string_form_widget_and_transition():
    toml = """
[[playlist.section]]
transition = "nyancat.forward"
[[playlist.section.widget]]
type = "rss.feed"
"""
    assert required_plugins(_cfg(toml)) == {"led-ticker-rss", "led-ticker-flair"}


def test_table_form_transition():
    toml = """
[[playlist.section]]
[playlist.section.transition]
type = "pacman.forward"
[[playlist.section.widget]]
type = "message"
"""
    assert required_plugins(_cfg(toml)) == {"led-ticker-flair"}


def test_top_level_transitions_surface():
    toml = '[transitions]\nbetween_sections = "nyancat.alternating"\n'
    assert required_plugins(_cfg(toml)) == {"led-ticker-flair"}


def test_inline_emoji_dependency():
    toml = """
[[playlist.section]]
[[playlist.section.widget]]
type = "message"
text = "go :pokeball.ball: go"
"""
    assert required_plugins(_cfg(toml)) == {"led-ticker-flair"}


def test_plugin_backend_counts_builtin_does_not():
    assert required_plugins(_cfg('[display]\nbackend = "telnet"\n')) == {"led-ticker-telnet"}
    assert required_plugins(_cfg('[display]\nbackend = "headless"\n')) == set()


def test_commented_usage_and_non_plugin_dotted_are_empty():
    # weather is only in a comment; "1.5" and a core a.b are non-plugin dotted.
    toml = """
[display]
gpio_slowdown = 1
# [[playlist.section.widget]]
# type = "weather.current"
[[playlist.section]]
[[playlist.section.widget]]
type = "message"
text = "version 1.5"
"""
    assert required_plugins(_cfg(toml)) == set()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_example_config_plugin_flags.py -q`
Expected: FAIL with `ImportError: cannot import name 'required_plugins'`.

- [ ] **Step 3: Append the implementation to `src/led_ticker/_config_scan.py`**

```python
def _load(source: str | Path) -> dict:
    try:
        return tomllib.loads(Path(source).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}


def _namespace_to_package() -> dict[str, str]:
    """Catalog-derived namespace -> pip package. The same expression the Store
    uses; flair's four namespaces collapse to led-ticker-flair. Derived from
    load_catalog() (the drift-guarded SoT) — no hand map.

    NOTE: the "pip package name" guarantee holds because every catalog source is
    a pypi package today. A future git/#subdirectory source would yield a dedup
    key, not a pip-installable name."""
    return {
        e.namespace: _requirement_key(e.requirement()) for e in load_catalog().entries
    }


def _referenced_namespaces(data: dict) -> set[str]:
    """All plugin namespaces a config references — the recursive walk PLUS the
    two deploy surfaces the Store walk omits: top-level [transitions]
    default/between_sections, and [display] backend (a bare namespace).
    UNFILTERED (includes non-catalog namespaces and built-in backends)."""
    namespaces = set(_references_from_data(data))
    trans = data.get("transitions")
    if isinstance(trans, dict):
        for key in ("default", "between_sections"):
            v = trans.get(key)
            if isinstance(v, str) and "." in v:
                namespaces.add(v.split(".")[0])
    # [display] backend is a BARE namespace (no dot), so the dotted walk misses
    # it. Scoped to exactly this key so a stray free-text value can't over-count.
    # Sharp edge: if a future catalog namespace ever equals a built-in backend
    # name (rgbmatrix/headless), this would false-flag. None collide today.
    display = data.get("display")
    if isinstance(display, dict):
        backend = display.get("backend")
        if isinstance(backend, str):
            namespaces.add(backend)
    return namespaces


def required_plugins(source: dict | str | Path) -> set[str]:
    """Pip packages a config requires, from its ACTIVE (uncommented) plugin
    references. Parses with tomllib (comments excluded); never builds widgets,
    so it works whether or not the plugins are installed. Non-plugin dotted
    values and non-catalog namespaces fall through."""
    data = source if isinstance(source, dict) else _load(source)
    nsmap = _namespace_to_package()
    return {nsmap[ns] for ns in _referenced_namespaces(data) if ns in nsmap}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_example_config_plugin_flags.py -q`
Expected: PASS (7 passed). If `test_plugin_backend_counts_builtin_does_not` fails because `telnet` isn't in the catalog, confirm `led-ticker-telnet` is a catalog entry (`grep -n '"telnet"' src/led_ticker/plugins_catalog.json`); it is, per the catalog.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/_config_scan.py tests/test_example_config_plugin_flags.py
git commit --no-verify -m "feat: required_plugins() — catalog-derived deps from a config"
```

---

### Task 3: Startup dependency warning

A pure `plugin_dependency_warning()` that distinguishes "absent" from "installed but failed", wired into the display startup.

**Files:**
- Modify: `src/led_ticker/_config_scan.py` (append)
- Modify: `src/led_ticker/app/run.py` (call after config load, ~line 611)
- Test: `tests/test_example_config_plugin_flags.py` (append)

**Interfaces:**
- Consumes: `required_plugins`, `_namespace_to_package`, `_load` (Task 2). `LoadedPlugins.loaded: list[PluginInfo]` (`PluginInfo.namespace: str`), `LoadedPlugins.failed: list[tuple[str, str]]`.
- Produces: `plugin_dependency_warning(config_source, loaded_namespaces: Iterable[str], failed_namespaces: Iterable[str]) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_example_config_plugin_flags.py`:

```python
from led_ticker._config_scan import plugin_dependency_warning

_RSS_CFG = {"playlist": {"section": [{"widget": [{"type": "rss.feed"}]}]}}


def test_warning_absent_plugin_names_package_and_remedy():
    msg = plugin_dependency_warning(_RSS_CFG, loaded_namespaces=[], failed_namespaces=[])
    assert msg is not None
    assert "led-ticker-rss" in msg
    assert "aren't installed" in msg
    assert "docs.ledticker.dev/plugins" in msg


def test_warning_installed_but_failed_says_fix_not_install():
    msg = plugin_dependency_warning(
        _RSS_CFG, loaded_namespaces=[], failed_namespaces=["rss"]
    )
    assert msg is not None
    assert "failed to load" in msg
    assert "led-ticker-rss" in msg


def test_no_warning_when_required_plugin_is_loaded():
    assert (
        plugin_dependency_warning(_RSS_CFG, loaded_namespaces=["rss"], failed_namespaces=[])
        is None
    )


def test_no_warning_for_plugin_free_config():
    assert plugin_dependency_warning({"display": {"rows": 16}}, [], []) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_example_config_plugin_flags.py -q -k warning`
Expected: FAIL with `ImportError: cannot import name 'plugin_dependency_warning'`.

- [ ] **Step 3: Append the implementation to `src/led_ticker/_config_scan.py`**

```python
def plugin_dependency_warning(
    config_source: dict | str | Path,
    loaded_namespaces: Iterable[str],
    failed_namespaces: Iterable[str],
) -> str | None:
    """A one-shot WARNING message when a config needs plugins that aren't
    loaded, else None. Distinguishes absent (install) from installed-but-failed
    (fix). All three inputs use plugin NAMESPACES; packages are derived here."""
    data = config_source if isinstance(config_source, dict) else _load(config_source)
    nsmap = _namespace_to_package()
    required = required_plugins(data)
    installed = {nsmap[ns] for ns in loaded_namespaces if ns in nsmap}
    failed_pkgs = {nsmap[ns] for ns in failed_namespaces if ns in nsmap}
    absent = required - installed - failed_pkgs
    broken = required & failed_pkgs
    if not absent and not broken:
        return None
    lines: list[str] = []
    if absent:
        lines.append(
            "Config references plugins that aren't installed: "
            + ", ".join(sorted(absent))
            + " — their widgets/transitions will be skipped. Install them "
            "(config/requirements-plugins.txt or the web UI Store) and restart."
        )
    if broken:
        lines.append(
            "Installed but failed to load: "
            + ", ".join(sorted(broken))
            + " — fix or remove it (see the plugin-load errors above)."
        )
    lines.append("https://docs.ledticker.dev/plugins/")
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_example_config_plugin_flags.py -q -k warning`
Expected: PASS (4 passed).

- [ ] **Step 5: Wire the warning into `src/led_ticker/app/run.py`**

The block at `run.py:605-611` loads plugins then the config:

```python
    plugins = _load_plugins_for_config(config_path)
    for ns, err in plugins.failed:
        ...  # (existing per-plugin failure logging — leave as-is)
    config = await asyncio.to_thread(load_config, config_path)
```

Immediately **after** the `config = await asyncio.to_thread(load_config, config_path)` line, add:

```python
    _plugin_warning = plugin_dependency_warning(
        config_path,
        [info.namespace for info in plugins.loaded],
        [ns for ns, _err in plugins.failed],
    )
    if _plugin_warning:
        logging.getLogger(__name__).warning(_plugin_warning)
```

Add the import near the other `led_ticker` imports at the top of `run.py`:

```python
from led_ticker._config_scan import plugin_dependency_warning
```

(`import logging` is already present in `run.py` — confirm with `grep -n "^import logging" src/led_ticker/app/run.py`; if absent, add it.)

- [ ] **Step 6: Verify nothing regressed in the app entry path**

Run: `uv run pytest tests/test_app.py -q`
Expected: PASS. Then `uv run --extra dev ruff check src/led_ticker/_config_scan.py src/led_ticker/app/run.py` → clean.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/_config_scan.py src/led_ticker/app/run.py tests/test_example_config_plugin_flags.py
git commit --no-verify -m "feat: warn at startup about uninstalled plugin dependencies"
```

---

### Task 4: Standardize + enforce the `# requires-plugins:` headers, and the setup.sh tip

The tripwire test (written first, red), then the headers it pins (green), the old-block removal, the three dev-fixture headers, and the static `setup.sh` tip.

**Files:**
- Modify: `config/config.example.toml`, `config/config.bigsign.example.toml`, `config/config.firebird.example.toml`, `config/config.try.example.toml`, `config/config.showroom-bigsign.example.toml`, `config/config.bigsign.firebird.example.toml` (starters)
- Modify: `config/config.hires_emoji_test.example.toml`, `config/config.hires_transitions_test.example.toml`, `config/config.presentation_test.example.toml` (fixtures)
- Modify: `scripts/setup.sh` (bigsign tip)
- Test: `tests/test_example_config_plugin_flags.py` (append the tripwire)

**Interfaces:**
- Consumes: `required_plugins` (Task 2). The verified per-file values:

| config | line value |
| --- | --- |
| `config.example.toml` | `none` |
| `config.bigsign.example.toml` | `led-ticker-baseball, led-ticker-rss` |
| `config.firebird.example.toml` | `led-ticker-flair` |
| `config.try.example.toml` | `led-ticker-flair, led-ticker-rss` |
| `config.showroom-bigsign.example.toml` | `led-ticker-flair, led-ticker-weather` |
| `config.bigsign.firebird.example.toml` | `none` |
| `config.hires_emoji_test.example.toml` | `led-ticker-flair, led-ticker-weather` |
| `config.hires_transitions_test.example.toml` | `led-ticker-baseball, led-ticker-flair` |
| `config.presentation_test.example.toml` | `led-ticker-rss, led-ticker-weather` |

- [ ] **Step 1: Write the failing tripwire test**

Append to `tests/test_example_config_plugin_flags.py`:

```python
import re
from pathlib import Path

from led_ticker._config_scan import _namespace_to_package, _referenced_namespaces, _load

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# User-facing starters: the line (incl. `none`) is mandatory. Dev fixtures are
# exempt unless they use plugins. An explicit list — a filename heuristic would
# misclassify config.gif_text.example.toml (contains "text", not a fixture marker).
STARTERS = {
    "config.example.toml",
    "config.bigsign.example.toml",
    "config.firebird.example.toml",
    "config.try.example.toml",
    "config.showroom-bigsign.example.toml",
    "config.bigsign.firebird.example.toml",
}

_LINE = re.compile(r"^#\s*requires-plugins:\s*(.*?)\s*$", re.MULTILINE)


def _declared(path: Path) -> set[str] | None:
    """Parsed `# requires-plugins:` set, or None if the line is absent. `none`
    -> empty set. Lenient: whitespace/trailing-comma/case-insensitive none."""
    matches = _LINE.findall(path.read_text(encoding="utf-8"))
    assert len(matches) <= 1, f"{path.name}: expected at most one requires-plugins line"
    if not matches:
        return None
    body = matches[0].strip()
    if body.lower() == "none" or body == "":
        return set() if body.lower() == "none" else _fail_empty(path)
    return {p.strip() for p in body.split(",") if p.strip()}


def _fail_empty(path: Path):
    raise AssertionError(f"{path.name}: empty `# requires-plugins:` — use `none`")


def _example_configs() -> list[Path]:
    return sorted(_CONFIG_DIR.glob("config.*.example.toml"))


def test_starters_header_matches_derived():
    for path in sorted(_CONFIG_DIR.glob("config.*.example.toml")):
        if path.name not in STARTERS:
            continue
        declared = _declared(path)
        derived = required_plugins(path)
        assert declared is not None, (
            f"{path.name}: missing `# requires-plugins:` line (starters require it, "
            f"`none` included). Set it to: # requires-plugins: "
            f"{', '.join(sorted(derived)) or 'none'}"
        )
        assert declared == derived, (
            f"{path.name}: header {sorted(declared)} != derived {sorted(derived)}. "
            f"missing {sorted(derived - declared)}; stale {sorted(declared - derived)}. "
            f"Set the line to: # requires-plugins: {', '.join(sorted(derived)) or 'none'}"
        )


def test_example_is_plugin_free():
    path = _CONFIG_DIR / "config.example.toml"
    assert required_plugins(path) == set()
    assert _declared(path) == set()  # declares `none`


def test_any_plugin_using_example_declares_it():
    for path in _example_configs():
        derived = required_plugins(path)
        if not derived:
            continue
        declared = _declared(path)
        assert declared is not None, (
            f"{path.name}: uses plugins but has no `# requires-plugins:` line. "
            f"Add: # requires-plugins: {', '.join(sorted(derived))}"
        )
        assert declared == derived, (
            f"{path.name}: header {sorted(declared)} != derived {sorted(derived)}"
        )


def test_catalog_covers_every_referenced_namespace():
    # Runs against the UNFILTERED namespace set (not required_plugins, which
    # already drops unknowns) so a config referencing an uncatalogued plugin
    # namespace fails loudly.
    known = set(_namespace_to_package())
    # Built-in backends are legal bare values that are not plugins.
    builtins = {"rgbmatrix", "headless"}
    for path in _example_configs():
        refs = _referenced_namespaces(_load(path))
        # Only namespaces that look like plugins (the walk also surfaces bare
        # backend names); a dotted ref to an unknown namespace is the real risk.
        unknown = {
            ns for ns in refs
            if ns not in known and ns not in builtins
        }
        # Filter to things that actually appeared as a dotted/plugin ref:
        # bare non-backend strings never enter refs except via backend, handled
        # by the builtins set above.
        assert not unknown, (
            f"{path.name} references namespaces not in the catalog: {sorted(unknown)}. "
            f"Add them to src/led_ticker/plugins_catalog.json or fix the typo."
        )
```

- [ ] **Step 2: Run the tripwire to verify it fails**

Run: `uv run pytest tests/test_example_config_plugin_flags.py -q -k "starters or plugin_using or catalog_covers or plugin_free"`
Expected: FAIL — the starters/fixtures don't yet carry standardized `# requires-plugins:` lines (e.g. `config.bigsign.example.toml` still has the free-text `# ── Plugin dependencies ──` block, not the machine line).

- [ ] **Step 3: Add/replace the header line in each starter**

For each starter, ensure a single line `# requires-plugins: <value>` exists near the top (immediately after the opening title comment block, before `[display]`), using the value from the Interfaces table. For `config.bigsign.example.toml` and `config.firebird.example.toml`, **replace** the existing `# ── Plugin dependencies ──` … `# ──────` block with the single line plus a one-line pointer. Example for `config.bigsign.example.toml` — replace its top block with:

```toml
# requires-plugins: led-ticker-baseball, led-ticker-rss
# Install via config/requirements-plugins.txt (or the web UI Store), then restart.
# See https://docs.ledticker.dev/plugins/
```

For `config.example.toml` (already plugin-free, no old block), insert after its title/intro comment (before `[display]`):

```toml
# requires-plugins: none
```

For `config.bigsign.example.toml`, the commented `weather.current` example stays, but is documented with a prose note where it sits (NOT in the machine line), e.g. above the commented block:

```toml
# (uncomment the weather section below to add current conditions — needs led-ticker-weather)
```

Apply the same single-line pattern to `config.firebird.example.toml` (`led-ticker-flair`), `config.try.example.toml` (`led-ticker-flair, led-ticker-rss`), `config.showroom-bigsign.example.toml` (`led-ticker-flair, led-ticker-weather`), and `config.bigsign.firebird.example.toml` (`none`).

- [ ] **Step 4: Add the header line to the three plugin-using dev fixtures**

Insert the line near the top of each:
- `config/config.hires_emoji_test.example.toml`: `# requires-plugins: led-ticker-flair, led-ticker-weather`
- `config/config.hires_transitions_test.example.toml`: `# requires-plugins: led-ticker-baseball, led-ticker-flair`
- `config/config.presentation_test.example.toml`: `# requires-plugins: led-ticker-rss, led-ticker-weather`

- [ ] **Step 5: Run the tripwire to verify it passes**

Run: `uv run pytest tests/test_example_config_plugin_flags.py -q`
Expected: PASS (all unit + tripwire tests). If a fixture value mismatches, trust the test's printed "Set the line to:" hint over the table.

- [ ] **Step 6: Add the static `setup.sh` tip**

In `scripts/setup.sh`, find the bigsign tip (the `cp config/config.bigsign.example.toml config/config.toml` Tip block in the deploy branch) and append one line:

```
       (that config uses plugins — you'll get an install prompt at startup; see its header)
```

(Static text only — no parsing. Confirm the surrounding `say`/`ok` echo style and match it.)

- [ ] **Step 7: Full suite + lint**

Run: `uv run --extra dev ruff check src/ tests/` → clean.
Run: `make test` → PASS.

- [ ] **Step 8: Commit**

```bash
git add config/*.example.toml scripts/setup.sh tests/test_example_config_plugin_flags.py
git commit --no-verify -m "feat: enforce machine-readable # requires-plugins: headers on example configs"
```

---

## Notes / future (not in this plan)

- Optional belt-and-suspenders guard discussed during design: a meta-test that, *when plugins are installed in the dev/CI venv*, loads each example through the real engine and asserts the engine-resolved plugin set ⊆ the walk's derived set — catching a missed config-schema surface. Deferred; the core suite is hermetic.
- `plugin_hint` could later consume `_namespace_to_package()` instead of suggesting `led-ticker plugin install <namespace>`.

## Self-review

- **Spec coverage:** Component 1 (shared module + `required_plugins`) → Tasks 1-2; Component 2 (banner) → Task 3; Component 3 (headers) + Component 4 (tripwire) + Component 5 (`setup.sh`) → Task 4. The catalog-completeness meta-test and the top-level-`[transitions]`/`[display] backend`/emoji/table-form cases all have explicit unit tests. Covered.
- **Placeholder scan:** none — every code step shows complete code; every config value is the exact verified string.
- **Type consistency:** `required_plugins`, `_referenced_namespaces`, `_references_from_data`, `_namespace_to_package`, `_load`, `plugin_dependency_warning`, and `config_references` keep one signature across all tasks; `PluginInfo.namespace` / `LoadedPlugins.failed` shapes match `_plugin_loader.py`.
</content>

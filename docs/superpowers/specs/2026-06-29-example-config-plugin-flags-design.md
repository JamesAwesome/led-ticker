# Flag plugin dependencies in example configs — design

**Status:** approved (brainstorm 2026-06-29); revised after a robustness review
(2026-06-29) — see "Revision: robustness review" below.
**Scope:** small, self-contained feature. One spec → one plan → one PR.

## Problem

`make setup` seeds `config/config.example.toml` → `config/config.toml`, and its
output actively tips bigsign users to `cp config/config.bigsign.example.toml
config/config.toml`. Several shipped example configs reference **plugin**
widget/transition types (`rss.feed`, `baseball.scores`, `nyancat.alternating`,
…) that are **not installed by default**. A user who deploys such a config
discovers the dependency only when the widgets fail at runtime.

The examples *do* already carry a free-text `# ── Plugin dependencies ──`
header, but it:

1. **drifts** — bigsign's still says "and rebuild before running" (the model is
   now restart/reconcile, no rebuild) and labels `weather.current` a "commented
   example";
2. **is unenforced** — nothing checks the header against what the config
   actually uses, so a new example (or an edit) can ship plugin deps unflagged
   or stale;
3. **is invisible at the deploy moment** — `setup.sh` has no plugin awareness.

The runtime story is already strong: any namespaced type that fails to resolve
raises an actionable hint via `plugin_hint()` (`src/led_ticker/_plugin_hint.py`)
— e.g. *"'rss.feed' looks like a plugin widget, but no 'rss' plugin is loaded.
Install it with `led-ticker plugin install rss`…"* — and `validate` surfaces
it. The gap is **knowing before you deploy**, and **keeping the in-file flag
honest**.

User decision: **it is fine for examples to require plugins — but the
dependency must be flagged**, enforced so it cannot drift, and surfaced at the
deploy moment.

## Goals

- A single, machine-checkable declaration of plugin dependencies in each
  user-facing example, enforced by a test so it cannot drift.
- A deploy-time warning that fires on **every** path (including the manual
  bigsign/firebird `cp`), not just `make setup`.
- One shared derivation of "what plugins does this config require," reused by
  the warning and the test — and itself **built on existing infrastructure**,
  not a parallel reimplementation.
- Fix the current drift in the existing headers.

## Non-goals

- Forcing the bigsign/firebird examples to be plugin-free (explicitly allowed
  to use plugins).
- Auto-installing plugins, or changing `setup.sh` to parse configs (rejected as
  overkill — see Decisions).
- Reworking the existing per-widget `plugin_hint` runtime errors (kept as-is;
  the banner complements them).

## Revision: robustness review (the brittleness fixes)

An adversarial review found that the first draft reinvented two pieces of
existing, drift-guarded infrastructure in a narrower, buggier form, and that its
tripwire would have forced a shipped config to under-declare a real dependency.
The four adopted changes — now baked into the components below:

1. **Map is derived from the catalog, not hand-kept.** `plugins_catalog.json`
   (`src/led_ticker/plugins_catalog.py`, `SCHEMA_VERSION = 4`, drift-guarded by
   `tests/test_docs_available_covers_catalog.py`) already maps each plugin
   `namespace` → its pip `package`, already represents the flair four-namespaces
   → one-package case, and is the file you *cannot* forget when adding a
   first-party plugin (CLI + Store read it). Derive namespace→package from
   `load_catalog()` instead of maintaining a second copy.
2. **The walk reuses `config_references`, not a new field-list scan.**
   `webui/store.py:config_references()` is a pure, tested recursive walker that
   already handles **table-form transitions** (`[playlist.section.transition]`
   with `type = "pacman.forward"`) and **inline `:ns.slug:` emoji** — both of
   which the draft's hand-enumerated field walk missed (the table case would
   have silently under-counted). Extract it to a shared module and extend it to
   also cover the two surfaces it currently misses: top-level `[transitions]`
   `default`/`between_sections`, and `[display] backend`.
3. **Header reflects ACTIVE deps only; commented examples get a prose note.**
   The enforced `# requires-plugins:` line equals the derived active set. A
   plugin used only in a *commented* example (e.g. bigsign's commented
   `weather.current`) is documented with a plain inline human note, not the
   machine line — the startup banner catches it the moment it's uncommented.
4. **Banner distinguishes "absent" from "installed but broken."** Map loaded
   *and* failed plugin namespaces through the same catalog-derived map to package
   names — `LoadedPlugins.failed` is a list of `(namespace, error)` tuples — so a
   pip-installed-but-`register()`-crashed plugin is told to *fix*, not *install*.
   (No `_plugin_loader` change: since the map is catalog-derived it is not a
   drift vector, so reusing it on the installed side is uniform and simpler than
   the review's suggested `PluginInfo.dist_name` addition — one mapping
   mechanism, not two.)

A **second** adversarial review verified all of the above against the code
(reproduced the derivation table with `tomllib`; confirmed `requirement()` is
bare-pypi so `_requirement_key` normalizes versions away; confirmed
`config_references` extracts with no import cycle / no aiohttp; confirmed the
banner data shapes). It was **go, change-first (precision only)** — those edits
are folded into the components below: the catalog filter lives in
`required_plugins` while the shared walk stays unfiltered (the Store needs
non-catalog namespaces for `in_use_by`); `[display] backend` is a bare-string
top-level special case, not part of the dotted recursion; the fixtures rule
forces correct headers onto **three** dev fixtures (not one); the
catalog-completeness meta-test runs on the unfiltered namespace set; a unit test
covers the top-level `[transitions]` surface; and the pip-name guarantee carries
a "assumes pypi-package sources" caveat.

## Components

### 1. Shared config-scan module + `required_plugins()`

**Extract** `config_references()` (today in `src/led_ticker/webui/store.py`,
pure, covered by `tests/test_webui_purity.py`) into a dependency-light shared
module — `src/led_ticker/_config_scan.py` (transitively needs only `tomllib` +
`plugins_catalog` + `plugin_cmd`; **must not** import `webui`/aiohttp, so the
display process can use it — verified no import cycle). Update `webui/store.py`
to import from there.

The shared walk stays **unfiltered** — it returns *all* referenced namespaces
(catalog **and** non-catalog). This is load-bearing for the Store:
`build_store` (`store.py:202-204`) iterates `active − catalog_namespaces` and
looks up `refs.get(ns)` to compute `in_use_by` for **externally-installed**
plugins. Pushing the catalog filter into the walk would silently break that. The
**catalog filter lives only in `required_plugins()`** (below).

Generalize the shared walk to also collect, beyond what it does today (`type`
values on any nested mapping; the `transition`/`entry_transition`/
`widget_transition` keys in string and `{type=…}` table form; inline `:ns.slug:`
emoji):

- the top-level `[transitions]` `default` / `between_sections` string values
  (the dotted surface `config_references` currently excludes); and
- **`[display] backend`** — a dedicated **top-level special case**, NOT part of
  the dotted recursion. A backend value is a *bare* namespace
  (`backend = "telnet"`, or the built-ins `backend = "rgbmatrix"` /
  `"headless"`), so the walk's `"." in value` dotted logic never reaches it. The
  scan matches **exactly** `data["display"]["backend"]` as a bare string and
  emits that namespace (the catalog filter in `required_plugins` then keeps only
  catalog backends like `telnet`; built-ins fall through). Scope it to that one
  key so a free-text value elsewhere that happens to equal `rss`/`pool` can't
  over-count. (Sharp edge to note in code: if a *future* catalog namespace ever
  equals a built-in backend name, this bare match would false-flag — none
  collide today; only `telnet` is a catalog backend.)

```python
# _config_scan.py
def required_plugins(source: dict | str | Path) -> set[str]:
    """Packages a config requires, from its ACTIVE (uncommented) plugin refs.
    Parses with tomllib (comments excluded for free); never builds widgets, so
    it works whether or not the plugins are installed. Returns canonical pip
    package names (flair's four namespaces collapse to led-ticker-flair).

    Calls the unfiltered shared walk, then keeps only namespaces present in the
    catalog map and maps them to packages. Non-plugin dotted values ("1.5", a
    core a.b) and non-catalog namespaces fall through."""
```

- **Namespace→package** comes from `load_catalog()` —
  `{e.namespace: _requirement_key(e.requirement()) for e in load_catalog().entries}`
  (the same expression `webui/store.py` already uses to collapse flair). No hand
  map. A meta-test (below) keeps the catalog itself complete.
- **Output:** set of pip package names (deduped). **Caveat to note in code:** the
  "pip package name" guarantee holds because every catalog source is currently a
  `pypi` package with `version=None`; if a first-party plugin ever switches to a
  git/`#subdirectory` source, `_requirement_key` returns a dedup *key*, not a
  pip-installable name, and headers/banner would render that. Assert/comment that
  the derivation assumes pypi-package sources.
- **Known remaining gap (now narrow):** plugin-registered *borders / color
  providers / animations / fonts* referenced by namespaced value in inline
  tables. No first-party plugin ships those as a primary surface today; the
  runtime `plugin_hint` still catches them at load. (Emoji and the `telnet`
  backend, called out by the first review, are now *covered*, not gaps.)

### 2. Startup banner (the "warn")

In `src/led_ticker/app/run.py`, after the config is loaded and the plugin set is
known:

- `cat_map = {e.namespace: _requirement_key(e.requirement()) for e in load_catalog().entries}`
  (the catalog-derived namespace→package map, shared with `required_plugins`).
- `required = required_plugins(config_source)` (pip package names).
- `installed = {cat_map[i.namespace] for i in loaded if i.namespace in cat_map}` —
  loaded plugins' namespaces mapped to packages (flair's namespaces collapse).
- `failed_pkgs = {cat_map[ns] for (ns, _err) in LoadedPlugins.failed if ns in cat_map}`
  — pip-installed but `register()` raised.
- `absent = required - installed - failed_pkgs`; `broken = required & failed_pkgs`.
- Emit at most **one** `logging.WARNING` roll-up, wording each case correctly:

  > `Config references plugins that aren't installed: led-ticker-baseball,
  > led-ticker-rss — their widgets/transitions will be skipped. Install them
  > (config/requirements-plugins.txt or the web UI Store) and restart.`
  > …and, if `broken` is non-empty:
  > `Installed but failed to load: led-ticker-pool — fix or remove it (see the
  > plugin-load errors above).`
  > `https://docs.ledticker.dev/plugins/`

- Packages sorted, comma-joined. Logged once at startup, not per frame. Additive
  to the existing per-widget `plugin_hint` errors.

### 3. Standardized `# requires-plugins:` header

Each **user-facing starter** carries a machine-readable line near the top:

```
# requires-plugins: led-ticker-baseball, led-ticker-rss
```

or, for a plugin-free config:

```
# requires-plugins: none
```

- Canonical form: pip package names, comma-separated, sorted, lowercase. `none`
  (literal) for no dependencies.
- A one-line human pointer may follow (install via
  `config/requirements-plugins.txt` or the web UI Store, then restart; link to
  docs).
- **Commented optional examples** get a separate plain prose note, NOT the
  machine line — e.g. `# (uncomment the weather section below to add current
  conditions — needs led-ticker-weather)`. The machine line stays equal to the
  active set.
- Replaces the existing free-text `# ── Plugin dependencies ──` block; the stale
  "rebuild before running" wording is removed.

Per-file active values are **computed by the implementer with
`required_plugins(file)`**, not hand-listed. Expected results (pinned by the
tripwire) given today's uncommented usage:

| config                                 | requires-plugins (active)                |
| -------------------------------------- | ---------------------------------------- |
| `config.example.toml`                  | `none`                                   |
| `config.bigsign.example.toml`          | `led-ticker-baseball, led-ticker-rss` (weather is commented → prose note, not the line) |
| `config.firebird.example.toml`         | `led-ticker-flair`                       |
| `config.try.example.toml`              | `led-ticker-flair, led-ticker-rss`       |
| `config.showroom-bigsign.example.toml` | `led-ticker-flair, led-ticker-weather`   |
| `config.bigsign.firebird.example.toml` | `none`                                   |

(All six verified by reproducing `required_plugins` with `tomllib`; the
implementer should still re-run rather than trust the table.)

### 4. Tripwire test (`tests/test_example_config_plugin_flags.py`)

- **STARTERS** = the six user-facing configs above (explicit list constant).
- For each starter: parse its `# requires-plugins:` line into a package set
  (`none` → empty); assert it **equals** `required_plugins(path)`.
- Assert `config.example.toml` derives to empty **and** declares `none` (the
  plugin-free-starter guard the earlier review asked for).
- **Fixtures rule:** iterate all `config/*.example.toml`; the header is not
  required on non-starters, but any file with non-empty `required_plugins(file)`
  MUST carry a correct line. **This forces a header onto three dev fixtures**
  (verified by reproducing the derivation), not just one — the implementer must
  add all three or the tripwire fails on first run:
  - `config.hires_emoji_test.example.toml` → `led-ticker-flair, led-ticker-weather`
    (`weather.current` type + `:pokeball.ball:` emoji — the case that broke the draft);
  - `config.hires_transitions_test.example.toml` → `led-ticker-baseball, led-ticker-flair`
    (table-form `type = "pacman.forward"`, `baseball.roll…`);
  - `config.presentation_test.example.toml` → `led-ticker-rss, led-ticker-weather`
    (active `rss.feed` + `weather.current`).
- A starter missing the line entirely fails.
- **Failure message:** on mismatch, print the symmetric difference and the exact
  canonical line to paste — e.g. `header is missing {led-ticker-flair}; has
  stale {}; set the line to: "# requires-plugins: led-ticker-flair,
  led-ticker-weather"`. Parsing is lenient (strip whitespace, tolerate a
  trailing comma, case-insensitive `none`); canonical form is only enforced in
  the *fix hint*, not required on input. Defined behavior: empty-after-colon →
  treated as malformed (fail with hint); multiple `# requires-plugins:` lines →
  fail ("exactly one expected").

- **Catalog-completeness meta-test:** must run against the **unfiltered** walk
  output (raw referenced namespaces), NOT `required_plugins()` — the latter
  already drops non-catalog namespaces, so asserting *its* output resolves
  through `load_catalog()` is vacuously green-by-construction. Asserting the
  unfiltered set against the catalog is what actually catches "someone added
  `type = "foo.bar"` to an example but forgot `foo` in the catalog." (Zero
  unknown namespaces today, so it passes now.)

### 5. `setup.sh` static tip

One static line appended to the existing bigsign `cp` tip:

```
  Tip: for the bigsign layout, replace it with config/config.bigsign.example.toml
       cp config/config.bigsign.example.toml config/config.toml
       (that config uses plugins — you'll get an install prompt at startup; see its header)
```

No TOML parsing, no duplicated map.

## Data flow

```
config TOML ──tomllib──► _config_scan.required_plugins() ──► {pip packages}
   (catalog: namespace→package)        │                          │
                 (startup) ────────────►│                  (test) ►│ == parsed header line
   loaded/failed namespaces ─cat_map──►│
                       absent / broken ─► WARNING banner (once)
```

## Testing

- `test_example_config_plugin_flags.py`:
  - `required_plugins()` units: plugin-free → empty; string-form `rss.feed` +
    `nyancat.forward` → `{led-ticker-rss, led-ticker-flair}`; **table-form**
    transition (`[…transition] type="pacman.forward"`) → `{led-ticker-flair}`;
    **top-level `[transitions]`** (a config whose *only* plugin ref is
    `between_sections = "nyancat.alternating"`) → `{led-ticker-flair}` (the
    added surface — no shipped fixture exercises it non-redundantly, so it needs
    a dedicated unit); inline `:pokeball.ball:` emoji → `{led-ticker-flair}`;
    `[display] backend="telnet"` → `{led-ticker-telnet}` and `backend="headless"`
    (built-in) → empty; commented-only plugin usage → empty; non-plugin dotted
    value (`"1.5"`, core `a.b`) → empty.
  - Header == derived across the six STARTERS; `config.example.toml` ⇒ empty +
    `none`.
  - Fixtures rule across all `config/*.example.toml` (incl. the
    `hires_emoji`/`hires_transitions` counter-examples).
  - Catalog-completeness meta-test.
- Banner units (`caplog`): required-but-absent → warning naming the package,
  once; required-but-`failed` → "installed but failed" wording; all required
  installed → silent.
- Reuse guard: a quick assertion that `webui/store.py` still resolves the same
  references after the extraction (or rely on the existing
  `test_webui_purity.py` / Store tests).

## Decisions (resolved during brainstorm + review)

- **Warn surface = startup banner**, not `setup.sh` parsing (setup only ever
  seeds the plugin-free smallsign → would fire ~never and duplicate logic in
  bash). `setup.sh` gets a static one-line tip.
- **Header form = machine-readable comment line**, not free prose (brittle to
  scrape, already drifts) and not a real TOML key (non-functional schema field).
- **Namespace→package is derived from `load_catalog()`**, not a hand map — the
  catalog is the existing drift-guarded SoT.
- **The walk reuses an extracted `config_references`**, not a new field-list
  scan — a recursive "scan everything, intersect with catalog namespaces" walk
  is robust to new surfaces; a hardcoded field list is not.
- **Commented-example deps → prose note**, not the enforced line (keeps the
  machine line honest about active deps without forbidding optional templates).
- **File scope = six user-facing starters require the line; dev fixtures exempt
  unless they use plugins.**

## Out of scope / future

- Teaching `plugin_hint` to consume the catalog map (it currently suggests
  `led-ticker plugin install <namespace>`); a later unification.
- A `led-ticker plugins-for <config>` CLI subcommand (the banner covers the
  need).
- Scanning plugin-namespaced borders/color-providers/animations (no first-party
  plugin ships one as a primary surface yet; runtime hint still catches them).
</content>

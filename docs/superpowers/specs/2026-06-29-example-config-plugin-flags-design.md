# Flag plugin dependencies in example configs — design

**Status:** approved (brainstorm 2026-06-29)
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
  the warning and the test.
- Fix the current drift in the existing headers.

## Non-goals

- Forcing the bigsign/firebird examples to be plugin-free (explicitly allowed
  to use plugins).
- Auto-installing plugins, or changing `setup.sh` to parse configs (rejected as
  overkill — see Decisions).
- Reworking the existing per-widget `plugin_hint` runtime errors (kept as-is;
  the banner complements them).

## Canonical map (single source of truth)

A new module-level constant — `PLUGIN_NAMESPACE_TO_PACKAGE` — maps a plugin
**namespace** (the segment before the first `.` in a type/transition name) to
its installable **package**:

| namespace                                   | package               |
| ------------------------------------------- | --------------------- |
| `pool`                                      | `led-ticker-pool`     |
| `baseball`                                  | `led-ticker-baseball` |
| `crypto`                                    | `led-ticker-crypto`   |
| `calendar`                                  | `led-ticker-calendar` |
| `rss`                                       | `led-ticker-rss`      |
| `weather`                                   | `led-ticker-weather`  |
| `nyancat`, `pokeball`, `pacman`, `sailor_moon` | `led-ticker-flair` |

`led-ticker-flair` is the one many-to-one case (four transition namespaces, one
package). This map is the single SoT; if a first-party plugin namespace is added
later, it is added here.

**Location:** `src/led_ticker/_plugin_hint.py` (it already owns the
"namespaced name → plugin" knowledge and is import-light), exported alongside a
new `required_plugins(...)` helper.

## Components

### 1. `required_plugins(source) -> set[str]` (derivation helper)

- **Input:** a parsed-TOML mapping (`dict`) or a path to a `.toml` file.
- **Behavior:** parse with `tomllib` (comments are ignored natively), walk every
  `[[playlist.section]]`'s `title`/`widget` `type` values and section-level
  `transition` / `entry_transition` / `widget_transition` values, plus the
  top-level `[transitions]` table values. For each value containing a `.`, take
  the namespace and, if it is in `PLUGIN_NAMESPACE_TO_PACKAGE`, add the package.
- **Output:** the set of required **package** names (deduped; flair collapses).
- Operates on the **parsed structure, never built widgets**, so it works
  whether or not the plugin is installed (no "unknown type" load error), and
  commented lines are excluded for free.
- Pure and import-light (only `tomllib`); reused by both the banner and the
  test.

**Surface scanned:** widget/title `type` and the transition fields
(`transition` / `entry_transition` / `widget_transition` per section, plus
`[transitions]` `default` / `between_sections`). This covers the primary surface
of all seven first-party plugins. **Known, accepted gap:** plugins can also
register borders, color providers, animations, fonts, and emoji (e.g. flair's
`:pokeball.ball:` embedded in arbitrary text, or a hypothetical
`border = "x.y"`). The derivation does **not** scan those — emoji live inside
free text and color/border values are inline tables, so scanning them reliably
is disproportionate. In practice a config using flair's emoji almost always also
uses a flair transition (already counted), and the runtime `plugin_hint` still
catches any uncounted reference at load. If a first-party plugin ever ships a
namespaced *border/color/animation* as its primary surface, revisit this.

Edge cases:
- A dotted value whose namespace is **not** a known plugin (e.g. a future core
  namespaced type, or `"1.5"`) contributes nothing.
- A namespaced value that *is* a known plugin is counted even if the plugin
  happens to be installed — the function answers "what does this config
  require," not "what is missing." (Missing-set subtraction is the caller's job;
  see the banner.)

### 2. Startup banner (the "warn")

In `src/led_ticker/app/run.py`, after the config is loaded and the plugin set is
known:

- `required = required_plugins(config_source)`
- `installed = {package names of loaded plugins}` — derived from the
  `LoadedPlugins` handle / entry-point distributions already available at
  startup (map each loaded plugin's namespace through the same canonical map, or
  read the distribution name directly if exposed).
- `missing = required - installed`
- If `missing` is non-empty, emit **one** `logging.WARNING` roll-up:

  > `Config references plugins that aren't installed: led-ticker-baseball,
  > led-ticker-rss. Their widgets/transitions will be skipped. Install them
  > (config/requirements-plugins.txt or the web UI Store) and restart —
  > https://docs.ledticker.dev/plugins/`

- Packages listed sorted, comma-joined. Logged once at startup, not per frame.
- This is additive: the existing per-widget `plugin_hint` errors still fire; the
  banner is the up-front roll-up.

### 3. Standardized `# requires-plugins:` header

Each **user-facing starter** carries a machine-readable line near the top:

```
# requires-plugins: led-ticker-rss, led-ticker-baseball
```

or, for a plugin-free config:

```
# requires-plugins: none
```

- Packages comma-separated, sorted, lowercase, the canonical `led-ticker-*`
  names. `none` (literal) for no dependencies.
- A one-line human pointer may follow (e.g. `# Install via
  config/requirements-plugins.txt or the web UI Store, then restart. See
  https://docs.ledticker.dev/plugins/`).
- Replaces the existing free-text `# ── Plugin dependencies ──` block. The stale
  "rebuild before running" wording is removed (restart/reconcile model).

Per-file declared values (derived from current uncommented usage):

| config                                | requires-plugins                              |
| ------------------------------------- | --------------------------------------------- |
| `config.example.toml`                 | `none`                                        |
| `config.bigsign.example.toml`         | derived (currently `led-ticker-baseball, led-ticker-rss`; include `led-ticker-weather` only if its `weather.current` widget is uncommented) |
| `config.firebird.example.toml`        | `led-ticker-flair`                            |
| `config.try.example.toml`             | `led-ticker-flair, led-ticker-rss`            |
| `config.showroom-bigsign.example.toml`| derived                                       |
| `config.bigsign.firebird.example.toml`| derived                                       |

The implementer computes each value with `required_plugins(file)` rather than
hand-listing — the table above is the expected result, and the tripwire pins it.

### 4. Tripwire test (`tests/test_example_config_plugin_flags.py`)

- **STARTERS** = the six user-facing configs above (an explicit list constant).
- For each starter: parse its `# requires-plugins:` line into a set of packages
  (`none` → empty set); assert it **equals** `required_plugins(path)`. Set
  equality catches missing, extra, and stale entries.
- Assert `config.example.toml` derives to the empty set **and** declares
  `none` — this is also the "starter is plugin-free" guard the earlier review
  asked for.
- **Fixtures rule:** for the `*_test.example.toml` / other non-starter example
  configs, the header is **not required**, but **if** `required_plugins(file)`
  is non-empty the file MUST still carry a correct `# requires-plugins:` line.
  (Iterate all `config/*.example.toml`; a plugin-using file without a correct
  line fails.)
- A starter missing the line entirely fails (the line is mandatory on starters,
  `none` included).

### 5. `setup.sh` static tip

One static line appended to the existing bigsign `cp` tip, e.g.:

```
  Tip: for the bigsign layout, replace it with config/config.bigsign.example.toml
       cp config/config.bigsign.example.toml config/config.toml
       (that config uses plugins — you'll get an install prompt at startup; see its header)
```

No TOML parsing, no duplicated map.

## Data flow

```
config TOML ──tomllib──► required_plugins() ──► {packages}
                               │                     │
        (startup) ────────────►│              (test) ►│ == parsed header line
        installed set ─────────┘
              │
          missing set ──► WARNING banner (once)
```

## Testing

- `test_example_config_plugin_flags.py`:
  - `required_plugins()` unit cases: plugin-free dict → empty; a dict using
    `rss.feed` + `nyancat.forward` → `{led-ticker-rss, led-ticker-flair}`;
    commented-only usage (parse a file whose only plugin type is in a comment)
    → empty; a non-plugin dotted value (`"1.5"`, a core `a.b`) → empty.
  - Header-vs-derived equality across the six STARTERS.
  - `config.example.toml` ⇒ empty + `none`.
  - Fixture rule: any `config/*.example.toml` with non-empty derivation has a
    matching line.
- Banner: a unit test asserting that, given a config requiring an uninstalled
  package and an `installed` set lacking it, the missing set is computed and the
  warning is logged once (capture with `caplog`); and that when all required
  packages are installed, nothing is logged.

## Decisions (resolved during brainstorm)

- **Warn surface = startup banner**, not `setup.sh` parsing. `setup.sh` only
  ever seeds the plugin-free smallsign, so a parse-and-warn there would fire
  ~never and would duplicate the namespace→package map in bash. The banner is in
  Python, has the loaded config + installed-plugin set, and catches the manual
  `cp` path. `setup.sh` gets only a static one-line tip.
- **Header form = machine-readable comment line**, not free prose (brittle to
  scrape, already drifts) and not a real TOML key (would add a non-functional
  schema field the loader must special-case).
- **File scope = six user-facing starters require the line; dev fixtures exempt
  unless they use plugins.** Avoids `# requires-plugins: none` noise on 11
  dev-only fixtures while still catching any unflagged plugin use anywhere.

## Out of scope / future

- Teaching the existing `plugin_hint` to consume `PLUGIN_NAMESPACE_TO_PACKAGE`
  (it currently suggests `led-ticker plugin install <namespace>`); a later
  unification, not needed here.
- A `led-ticker plugins-for <config>` CLI subcommand (the banner covers the
  need).

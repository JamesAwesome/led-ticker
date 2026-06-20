# Plugin catalog schema v3 — typed plugin surface (adoption item 4E)

**Date:** 2026-06-15
**Status:** approved (design), pre-implementation
**Goal:** Make the bundled plugin catalog represent the **whole** plugin surface —
widgets, transitions, emoji, and (as recognized-but-currently-unused kinds) fonts,
borders, color providers, animations, easing — not just widgets. Today `provides`
is an untyped flat list, so a plugin that ships only transitions/emoji (nyancat,
pacman, sailor_moon, pokeball) can't say what kind of thing it offers, emoji are
buried in prose `summary`, and the `install` hint mis-tells users to put a
transition in a widget `type =`.

## Background / why

`src/led_ticker/plugins_catalog.json` is the bundled, offline source of truth for
`led-ticker plugin list / search / install`. It's currently `schema_version: 2`
(v2 added `subdirectory` for the monorepo consolidation, #241).

Each entry has `provides: [str, ...]` — a flat, **untyped** list:

- For widget plugins it lists widget `type =` names (`pool.monitor`).
- For the sprite-trail plugins it lists **transition** names (`nyancat.forward`)
  — same field, different meaning, nothing records which.
- Emoji aren't represented at all except as prose in `summary` (baseball/pokeball
  `:…ball:`). PR #221 stuffed baseball's transitions+emoji into `summary` as a
  stopgap and flagged this schema work as the real fix.

Consequences:

1. `cmd_list` prints a flat `provides:` line that can't say widget vs transition
   vs emoji.
2. `Catalog.search` only matches `name + summary + provides`, so an emoji slug or
   font name that lives only in prose may be missed.
3. **Bug:** `cmd_install` (`plugin_cmd.py:496-498`) assumes `provides[0]` is a
   widget and prints `Add type = "<x>"`. For nyancat/pacman/sailor_moon that
   tells the user to put a *transition* into a widget `type =`.

The plugin API (`PluginAPI` in `led_ticker/plugin.py`) can register these
surfaces: `widget`, `transition`, `color_provider`, `animation`, `border`,
`easing`, `emoji`, `hires_emoji`, `font`. A hi-res emoji always pairs with a
low-res emoji of the same slug, so the catalog represents the **slug once** under
`emoji`.

## Decisions (from brainstorming)

1. **Structured `provides` object** keyed by surface kind (not a flat list, not a
   list of `{kind,name}` objects, not sibling top-level fields). Bump
   `schema_version` 2 → 3.
2. **Recognize the full plugin-API surface** as known kinds; unknown keys are a
   load error (typo guard). Data only populates kinds a plugin actually ships
   (today: widgets, transitions, emoji).
3. `cmd_list` renders **grouped, non-empty** lines per kind; emoji shown as
   `:slug:`.
4. `cmd_install` hint is **kind-aware**, driven by a priority order.
5. Summaries stay **hand-written prose** (kept accurate), not auto-derived.
6. Technical documentation is a deliverable: a catalog-schema reference section in
   `docs/plugin-system.md`.

## Schema (v3)

```jsonc
{
  "schema_version": 3,
  "plugins": [
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
    }
  ]
}
```

- `provides` is an **object**. Keys are surface kinds; values are arrays of
  fully-qualified `namespace.name` strings.
- **Known kinds:** `widgets`, `transitions`, `emoji`, `fonts`, `borders`,
  `color_providers`, `animations`, `easing`. All optional. A missing/empty
  `provides` (`{}`) is valid.
- **`emoji`** lists the slug once (covers the lo-res + hi-res pair); there is no
  `hires_emoji` key.
- Unknown keys → `ValueError` at load.
- `name`, `namespace`, `summary`, `homepage`, `sources` are unchanged from v2.

## Data model (`src/led_ticker/plugins_catalog.py`)

New frozen attrs class (style matches `CatalogSource` / `CatalogEntry`):

```python
_SURFACE_KINDS = (
    "widgets", "transitions", "emoji", "fonts",
    "borders", "color_providers", "animations", "easing",
)

@attrs.define(frozen=True)
class PluginProvides:
    widgets: tuple[str, ...] = ()
    transitions: tuple[str, ...] = ()
    emoji: tuple[str, ...] = ()
    fonts: tuple[str, ...] = ()
    borders: tuple[str, ...] = ()
    color_providers: tuple[str, ...] = ()
    animations: tuple[str, ...] = ()
    easing: tuple[str, ...] = ()

    def all_names(self) -> tuple[str, ...]:
        """Every provided name across all kinds (for the search haystack)."""
        ...

    def is_empty(self) -> bool: ...

    # (kind_label, name) of the best install-hint surface, or None when empty.
    def primary(self) -> tuple[str, str] | None:
        """First non-empty kind by priority:
        widgets > transitions > color_providers > animations > borders
        > emoji > fonts > easing."""
        ...

    def groups(self) -> list[tuple[str, tuple[str, ...]]]:
        """Non-empty (kind_label, names) pairs in display order, for cmd_list."""
        ...
```

`CatalogEntry.provides` changes type `tuple[str, ...]` → `PluginProvides`.

## Loader / validation

- `SCHEMA_VERSION = 3`. Clean break: the gate `version != SCHEMA_VERSION` already
  rejects a mismatched file; the bundled JSON is migrated in the same change. No
  dual-shape support.
- New `_parse_provides(raw: object) -> PluginProvides`:
  - `None`/absent → `PluginProvides()` (all empty).
  - non-`dict` → `ValueError("'provides' must be an object")`.
  - any key not in `_SURFACE_KINDS` → `ValueError` naming the bad key + the valid
    set (typo guard).
  - any value not a list of `str` → `ValueError`.
- `_parse_entry` calls `_parse_provides(raw.get("provides"))`.

## Consumers

### `Catalog.search` (`plugins_catalog.py`)
Haystack becomes `name + summary + provides.all_names()` (was `+ provides`).
Transition / emoji / font names become first-class searchable.

### `cmd_list` (`plugin_cmd.py`)
Replace the single flat `provides:` line with one line per non-empty kind, in
display order, emoji rendered as `:slug:`:

```
  baseball [declared] [installed] — MLB scores, standings, …
      widgets:     baseball.scores, baseball.standings, baseball.promotions, baseball.statcast, baseball.attendance
      transitions: baseball.roll, baseball.roll_reverse, baseball.roll_alternating
      emoji:       :baseball.ball:
```

A plugin with empty `provides` prints no surface lines (just name + summary).

### `cmd_install` hint (`plugin_cmd.py:496-498`)
Replace the hardcoded `type = "<provides[0]>"` with a kind-aware hint from
`provides.primary()`. The table is ordered by `primary()` priority (first
non-empty kind wins):

| primary kind     | hint shown                                   |
| ---------------- | -------------------------------------------- |
| widgets          | `type = "ns.x"` (in a widget section)        |
| transitions      | `transition = "ns.x"`                        |
| color_providers  | `font_color = { style = "ns.x" }`            |
| animations       | `animation = "ns.x"`                         |
| borders          | `border = "ns.x"`                            |
| emoji            | `:ns.x:` inline in widget text               |
| fonts            | `font = "ns.x"`                              |
| easing           | used via a transition's `easing = "ns.x"`    |
| (empty provides) | "Restart led-ticker to load the plugin."     |

This fixes the transition-only-plugin mis-hint. The "then restart led-ticker"
tail is preserved.

## Data migration — all 10 entries

Enumerated from each plugin's `register()` on `led-ticker-plugins@main`:

| plugin       | widgets                                                            | transitions                              | emoji            |
| ------------ | ----------------------------------------------------------------- | ---------------------------------------- | ---------------- |
| pool         | pool.monitor                                                       | —                                        | —                |
| baseball     | scores, standings, promotions, statcast, attendance (all `baseball.*`) | roll, roll_reverse, roll_alternating | baseball.ball    |
| crypto       | crypto.coingecko                                                   | —                                        | —                |
| calendar     | calendar.events                                                    | —                                        | —                |
| rss          | rss.feed                                                           | —                                        | —                |
| weather      | weather.current                                                    | —                                        | —                |
| nyancat      | —                                                                  | forward, reverse, alternating            | —                |
| pokeball     | —                                                                  | forward, reverse, alternating            | pokeball.ball    |
| pacman       | —                                                                  | forward, reverse, alternating            | —                |
| sailor_moon  | —                                                                  | forward, reverse, alternating            | —                |

(All transition/widget names are written fully-qualified, e.g.
`nyancat.forward`.) No current plugin registers fonts/borders/color
providers/animations/easing, so those keys stay absent. Summaries are left as-is
(already accurate after #221-style wording) — re-checked for accuracy during the
edit.

## Documentation (`docs/plugin-system.md`)

Add a **"Plugin catalog (`plugins_catalog.json`)"** reference subsection under
§8 "Discovery, CLI, deployment" covering:

- The JSON shape: `schema_version: 3`, entry fields, `sources` (git/pypi +
  `ref`/`subdirectory`), and the typed `provides` object.
- The known surface kinds; that `emoji` covers the lo+hi-res pair; that unknown
  keys are rejected at load.
- How `provides` feeds `plugin list` (grouped display), `search` (haystack), and
  the kind-aware `install` hint.
- How to add/refresh an entry: read the plugin's `register(api)` in the monorepo
  and list each registered surface under its kind.

## Tests (`tests/test_plugins/test_catalog.py`, `test_plugin_cli.py`)

- **Parse/validation:** `_parse_provides` for a valid multi-kind dict; unknown-key
  rejection; non-list value rejection; non-string element rejection; absent/empty
  → all-empty `PluginProvides`.
- **Model:** `all_names()` flattens across kinds; `primary()` priority (widgets
  beats transitions; transition-only → transitions; emoji-only → emoji; empty →
  None); `groups()` returns non-empty kinds in order.
- **Bundled integrity (guards the hand-edited JSON):** `schema_version == 3`
  enforced (a v2 doc rejected); baseball has the 5 widgets + 3 transitions + ball
  emoji; nyancat/pacman/sailor_moon are **transition-only** (`widgets == ()`);
  pokeball has 3 transitions + ball emoji; pool/crypto/calendar/rss/weather are
  widget-only.
- **Search:** finds a widget (`attendance`), a transition (`roll`,
  `nyancat.forward`), and an emoji (`baseball.ball`).
- **`cmd_list`:** grouped lines render with `widgets:` / `transitions:` / `emoji:`
  labels and `:slug:` for emoji; an empty-provides entry prints no surface lines.
- **`cmd_install` hint:** kind-correct per primary surface — widget → `type =`,
  transition-only (nyancat) → `transition =`, emoji-only → `:slug:`.
- Update existing fixtures in `test_plugin_cli.py` (the inline `CatalogEntry(...,
  provides=(...))` fixtures at lines ~23 and ~172) and `test_catalog.py`
  (lines ~47-78, ~107, ~136) to the new `PluginProvides` shape.

Full suite + ruff + pyright + docs-lint green.

## Non-goals

- Docs-site **auto-rendered** catalog table (adoption slice D) — separate.
- PyPI `sources` population (slice C) — unchanged here.
- A runtime/test drift guard that imports external plugins to verify the catalog
  matches their `register()` — not hermetic; enumeration is done by hand now. A
  future guard is its own idea.
- No change to `sources`, `requirement()`, dedup (`_requirement_key` / `_dist_key`)
  — only the `provides` representation and its three consumers change.

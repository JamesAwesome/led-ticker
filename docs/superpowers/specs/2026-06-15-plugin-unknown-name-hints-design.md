# Plugin-aware "unknown name" errors (P1) — Design

**Date:** 2026-06-15
**Status:** Approved (brainstorm with James)

## Context

led-ticker's plugin extraction roadmap (see
`docs/superpowers/reviews/2026-06-15-plugin-extraction-recommendation.html`)
flagged **P1** as the prerequisite gate for moving any component out of core: the
config-author's "this name doesn't resolve" experience is only half-built.

- **Widgets** have an actionable migration path (`_CRYPTO_MIGRATION` in
  `app/factories.py` → `MigrationError`): "type X moved to the led-ticker-Y
  plugin; install it and use `y.x`."
- **Transitions have no equivalent.** Rule 39 (`validate.py`) only runs
  `difflib` against the *installed* registry, so a user who pastes
  `transition = "nyancat"` after that family is extracted gets
  `unknown transition 'nyancat'`, an **empty** did-you-mean hint, and a docs link
  to a catalogue that no longer lists it — a dead end.
- **No registry** detects the "namespaced name, but that plugin isn't installed"
  case (`transition = "arcade.nyancat"` with the arcade plugin absent).

This work builds the failure-UX scaffolding so extraction is non-breaking. It does
NOT extract anything — it makes future extraction safe. It is intentionally
sequenced **before** the plugin-registry / `led-ticker plugin install` project
(adoption item #4); the fix strings here are written so #4's install CLI slots in
with a one-line change.

## The three scenarios

When a name fails to resolve, exactly one of these applies:

| | Scenario | Example | Today | After P1 |
|---|---|---|---|---|
| **A** | Extracted legacy bare name | `transition = "nyancat"` after nyancat→arcade | dead-end "unknown transition" | migration message + fix |
| **B** | Namespaced name, plugin not loaded | `transition = "arcade.nyancat"`, arcade absent | terse "unknown transition" | plugin-aware hint |
| **C** | Genuine typo | `transition = "wipe_leftt"` | difflib did-you-mean ✓ | unchanged |

## Core design — one precedence chain, surfaced identically everywhere

For any unresolved name, the error `(message, fix)` is built by layering:

1. **Migration entry?** (a bare name we extracted) → the migration message + fix.
2. **Namespaced (`x.y`)?** → plugin-aware hint (scenario B).
3. **Else** → typo; existing difflib did-you-mean (scenario C, unchanged).

The `"cut"` sentinel and names that *do* resolve (installed plugin) are untouched.

## Components

### A. Generic hint helper — new module `src/led_ticker/_plugin_hint.py`

```python
def plugin_hint(name: str, kind: str) -> str | None:
    """If `name` is a namespaced reference to a plugin component that
    isn't loaded, return an actionable hint; else None.

    `kind` is the human word for the registry — "transition", "widget",
    "border", "color provider", "animation". Detection is purely the
    dot-namespacing convention (`<plugin>.<name>`): if `name` has no dot
    it isn't a plugin reference (returns None). Registry-agnostic and
    context-free — it does not consult the loaded-plugin set, so it works
    from the bare runtime lookups that have no LoadedPlugins handle.
    """
```

Message shape (final wording tuned in implementation, must contain the namespace
and point at `requirements-plugins.txt`):

> `'arcade.nyancat' looks like a plugin transition, but no 'arcade' plugin is loaded. Add it to config/requirements-plugins.txt and reinstall, or check the namespace. See https://docs.ledticker.dev/plugins/.`

### B. Transition migration map — in `src/led_ticker/transitions/__init__.py`

Mirrors `_CRYPTO_MIGRATION` (`app/factories.py:327`):

```python
# name → (message, suggested_fix). SHIPS EMPTY. The arcade-extraction
# PR adds nyancat/pokeball/pacman/sailor_moon entries in the same commit
# that removes them from core (the crypto precedent). A live entry for a
# transition still present in core would be unreachable/contradictory.
_TRANSITION_MIGRATION: dict[str, tuple[str, str]] = {}

def explain_unknown_transition(name: str) -> tuple[str, str]:
    """Build (message, fix) for a transition name that isn't registered,
    layering migration → plugin_hint → difflib typo suggestion."""
```

`explain_unknown_transition` is the single source of the "why didn't this resolve"
answer, used by both the runtime lookup and the validator.

### C. Runtime lookups upgraded (scenario B across all registries)

- `transitions/__init__.py:get_transition_class` — raises a `ValueError` built from
  `explain_unknown_transition(name)` (message + fix joined) instead of the terse
  registry dump.
- `widgets/__init__.py:get_widget_class` — appends `plugin_hint(name, "widget")` to
  its error when the name is namespaced. The existing `_CRYPTO_MIGRATION` /
  `MigrationError` path in `validate_widget_cfg` is **unchanged** (it already owns
  scenario A for widgets, and runs before the registry lookup).
- Border / color-provider / animation unknown-name sites
  (`app/coercion.py` border + animation paths, `color_providers.py`
  `_provider_from_style`) — append `plugin_hint(name, <kind>)`. One line each;
  no migration maps for these (no extraction planned).

### D. Validate-time

- Rule 39 (`_check_transition_names` in `validate.py`) calls
  `explain_unknown_transition` and emits its `(message, fix)` as the rule-39
  `ValidationIssue` (rule number stays **39**). So `led-ticker validate` shows the
  migration/plugin message for scenarios A and B; scenario C is byte-for-byte the
  current behavior.
- The widget validate path inherits the improved `get_widget_class` error for
  namespaced-unknown widget types automatically (it calls `get_widget_class` after
  the crypto check).

### E. Forward-compatibility with item #4

Fix strings point at `config/requirements-plugins.txt` + the docs today. When the
`led-ticker plugin install` CLI ships (item #4 Phase 3), updating them to mention
the command is a one-line change. Item #4's curated catalog (`plugins.json`) can
later own the `name → plugin` mapping that `_TRANSITION_MIGRATION` hardcodes; the
spec deliberately does NOT build that catalog now (YAGNI). `_plugin_hint.py` may
later be enriched with loaded/failed-plugin awareness (e.g. "the arcade plugin
failed to load: <error>") — out of scope for P1.

## Files touched

- **New:** `src/led_ticker/_plugin_hint.py` (the helper), `tests/test_plugin_hint.py`.
- **Modified:** `src/led_ticker/transitions/__init__.py` (map + `explain_*` +
  `get_transition_class`), `src/led_ticker/widgets/__init__.py`
  (`get_widget_class` hint), `src/led_ticker/validate.py` (rule 39),
  `src/led_ticker/app/coercion.py` + `src/led_ticker/color_providers.py`
  (border/animation/provider unknown-name sites).
- **Tests:** `tests/test_plugin_hint.py` (new) plus additions to
  `tests/test_validate.py` (rule 39) and the transition/widget lookup tests.

## Testing

- **`plugin_hint`**: dotted name → hint containing the namespace and the kind word;
  bare name → `None`; verify the kind word varies per registry.
- **`explain_unknown_transition` precedence**: monkeypatch a `_TRANSITION_MIGRATION`
  entry → migration message wins over the dot-hint; namespaced unknown (no
  migration entry) → plugin hint; plain typo → difflib suggestion (existing
  behavior preserved). The shipped map stays empty — the entry is injected by the
  test, proving the mechanism without a dormant live entry.
- **Rule 39**: a namespaced-unknown transition now yields the plugin hint (was an
  empty did-you-mean); the existing `wipe_leftt`→`wipe_left` typo test
  (`tests/test_validate.py`) still passes unchanged; a monkeypatched migration
  entry surfaces through rule 39.
- **Runtime lookups**: `get_transition_class` and `get_widget_class` raise the rich
  message for namespaced-unknown names.
- **One generic-hint test** through a border (or provider) coercion site.
- **Regression**: the crypto widget migration tests
  (`tests/test_widgets/test_crypto_migration.py`) stay green and untouched.

## Out of scope

- Extracting any transition/widget (the arcade/feeds/calendar repos).
- The `led-ticker plugin install` CLI and `plugins.json` catalog (item #4).
- Loaded/failed-plugin awareness in the hint.
- Auto-fix (`fix_key`/`fix_replacement_key`) for transition migrations — the
  rename isn't a simple key swap, so no auto-fix.

## Delivery

Feature branch + PR (worktree `feat/plugin-unknown-name-hints`). Staged commits per
the project's review pattern: helper + tests → transition map/explain + lookup →
validate rule 39 → generic hint wiring on the other registries → docs touch-up if
any.

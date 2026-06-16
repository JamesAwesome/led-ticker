# Calendar Extraction — Design

**Date:** 2026-06-16
**Status:** Approved (brainstorming)
**Author:** James + Claude

## Summary

Extract the `calendar` widget from led-ticker core into a standalone
`led-ticker-calendar` plugin repo, modeled on `led-ticker-baseball` /
`led-ticker-pool` / `led-ticker-crypto`. The widget code is already
extraction-clean: the P3 plugin-surface readiness audit (PR #219) made every
`led_ticker.*` name the widget imports reachable on the public
`led_ticker.plugin` surface, except the `register` decorator (replaced by
`api.widget(...)` on registration). The `icalendar` + `recurring-ical-events`
dependencies are calendar-only in core and move with the widget.

The one genuinely new wrinkle versus the prior extractions: core's
`validate.py` carries three calendar-specific **static-validator warning**
rules that baseball/pool never had. The errors-only plugin `validate_config`
hook cannot carry warnings, so this extraction also adds a **plugin validation
warnings channel** to core — a purely additive, independently-mergeable API
feature that the planned weather/rss extractions will reuse.

The widget module (`calendar.py`, 1162 lines) moves **verbatim** (imports
rewritten to `led_ticker.plugin`); splitting it is an optional follow-up, kept
out of the move so the extraction stays behavior-identical and verifiable.

## Decisions (locked during brainstorming)

1. **Validation strategy:** Re-home calendar's validation into the plugin
   (not drop, not generalize-in-core).
2. **TOML type:** `calendar.events` (namespace `calendar`, widget name
   `events`). Layout (`agenda` / `next` / `two_row`) stays a separate field.
3. **Advisory warnings:** Extend the plugin API with a warnings channel and
   re-home all three rules faithfully (not drop, not keep-generic-in-core).
4. **Module:** Move `calendar.py` verbatim; split later if desired.
5. **Scope:** The core warnings-channel API ships as part of this effort but
   is called out as an independently-mergeable PR (it also serves weather/rss).

## Architecture

### New core API — plugin validation warnings channel

`validate_config(cls, cfg) -> list[str]` stays **errors-only and untouched**;
pool/baseball/crypto keep working with no change. Add an **optional sibling
classmethod**:

```python
@classmethod
def validate_config_warnings(cls, cfg: dict[str, Any], ctx) -> list[str]:
    """Return advisory warning strings (empty list / absent hook = none)."""
```

`ctx` is a new **public** lightweight dataclass, exported from
`led_ticker.plugin`, carrying the geometry the re-homed rules need (the
per-widget `cfg` alone is insufficient — the font/scroll-cutoff rules read
section/display geometry):

- `scale: int` — section scale (`section.scale`)
- `content_height: int` — section content height
- `panel_width: int` — real panel width
- `panel_height: int` — real panel height
- `config_dir: Path` — directory of the config.toml (for resolving relative
  `ics_url` `file://`/path values in the ics-existence check)

**Wiring:**

- `validate.py`'s widget loop builds a `ctx` per section and calls
  `validate_config_warnings(cls, cfg, ctx)` for each widget whose class
  defines it. Each returned string becomes a `ValidationIssue(severity=
  "warning", rule=<new generic rule id>, location=…)`. Warnings only run in
  the no-errors phase (mirrors today's Phase-2 gating).
- The runtime build path (`factories.py`) logs any returned warnings at
  `logging.WARNING` so a non-`validate` startup still surfaces them.
- `API_VERSION` bumps. The drift-guarded Plugin API reference
  (`docs/site/.../plugins/api-reference`) gains the hook + `ctx` fields;
  `tests/test_docs_plugin_api_drift.py` updated. An authoring note documents
  errors-vs-warnings.

This is additive: no existing plugin or behavior changes.

### Plugin repo `led-ticker-calendar`

Mirror `led-ticker-baseball` structure exactly.

```
led-ticker-calendar/
  pyproject.toml
  README.md                         # user-facing; demo gif(s)
  CLAUDE.md                         # contributor invariants
  Makefile                          # dev/test/lint/format/typecheck
  .github/workflows/ci.yml          # sibling-checkout w/ LED_TICKER_DEPLOY_KEY
  .github/dependabot.yml
  .pre-commit-config.yaml
  .gitignore
  config/                           # example config snippet / smoketest
    config.calendar_smoketest.toml  # moved from core
  src/led_ticker_calendar/
    __init__.py                     # register(api): api.widget("events")(Calendar)
    calendar.py                     # verbatim widget; imports -> led_ticker.plugin
  tests/
    conftest.py
    test_smoke.py
    test_import_purity.py           # AST tripwire: only led_ticker.plugin
    test_calendar.py                # + the rest, moved from core
    test_calendar_*.py
    fixtures/
      calendar_sample.ics
      calendar_corpus/*.ics
```

**`pyproject.toml`** (baseball template): `name = "led-ticker-calendar"`,
entry point `calendar = "led_ticker_calendar:register"`; dependencies
`led-ticker`, `aiohttp`, `icalendar>=6.1`, `recurring-ical-events>=3.0`; dev
extras (pytest/pytest-asyncio/pytest-cov/pre-commit/ruff/pyright);
`[tool.uv.sources] led-ticker = { path = "../led-ticker", editable = true }`;
`[tool.pytest.ini_options] asyncio_mode = "auto"`, `pythonpath =
["../led-ticker/tests/stubs"]`; ruff (`select = ["E","F","I","UP","B","SIM"]`);
pyright `extraPaths = ["../led-ticker/tests/stubs"]`; coverage `fail_under =
90`. Hatchling wheel packaging `packages = ["src/led_ticker_calendar"]`.

**`__init__.py`** — `register(api)` calls `api.widget("events")(Calendar)`.
(Calendar registers a single widget; no transitions/emoji/fonts.)

**`calendar.py`** — moved verbatim. Edits limited to:
- imports rewritten from `led_ticker.<internal>` to `led_ticker.plugin`
  (everything the readiness audit confirmed is on the public surface:
  `format_clock`, `TickerMessage`, `TwoRowMessage`, `FrameAwareBase`,
  `as_color_provider`, `ColorProvider`, `compute_baseline`, `compute_cursor`,
  `count_text_chars`, `draw_with_emoji`, `measure_width`, `run_monitor_loop`,
  `spawn_tracked`, `make_color`, `FONT_DEFAULT`, `FONT_SMALL`, `Canvas`,
  `DrawResult`, `Font`; `colors.DEFAULT_COLOR` via the `colors` module export).
- the `@register("calendar")` decorator removed (registration now via
  `api.widget("events")`).
- `validate_config` keeps the existing error-typed checks (required/placeholder
  `ics_url`, layout/timezone/field-type/`time_format`/two_row-knob checks).
- a new `validate_config_warnings(cls, cfg, ctx)` holds the three re-homed
  advisory rules (see below).

**`test_import_purity.py`** — the baseball AST tripwire verbatim (asserts every
`led_ticker.*` import in `src/led_ticker_calendar` is exactly
`led_ticker.plugin`).

**Re-homed validation rules** (in `validate_config_warnings`):
1. **ics local-file existence** (was core rule 54) — `ics_url` that is a
   local path / `file://` (not `http(s)`/`webcal(s)`) resolved against
   `ctx.config_dir` and warned if missing. Stays a *warning* (the file may be
   written at runtime by a cron).
2. **two_row font-cutoff** — for `layout = "two_row"`, mirror the runtime
   `FONT_DEFAULT → FONT_SMALL` substitution and predict per-band cutoff using
   `ctx.scale` / `ctx.content_height` / `ctx.panel_*`, via the public
   `get_text_width` / `resolve_font` / `font_line_height_logical` /
   `resolve_band_heights`.
3. **scroll-cutoff** — calendar's held top row (day + time) is data-driven;
   warn when predicted content exceeds the held region.

(Rules 2 and 3 are ported from `validate.py`'s existing calendar branches,
re-expressed against `ctx` instead of the in-core `AppConfig` walk.)

### Core removal

- Delete `src/led_ticker/widgets/calendar.py`.
- Remove `calendar` from `src/led_ticker/widgets/__init__.py` auto-imports.
- Remove `icalendar` + `recurring-ical-events` from core `pyproject.toml`
  (+ refresh `uv.lock`). Confirmed calendar-only (no other core importer).
- Delete the three calendar branches in `validate.py`:
  `_check_calendar_ics_paths` (rule 54) and the `wtype == "calendar"` /
  `is_calendar_two_row` branches in the two_row-font and scroll-cutoff rules.
  (Now re-homed into the plugin's `validate_config_warnings`.)
- Remove the `# --- Calendar ---` `FieldHint` block from `factories.py`.
- Rename `_CRYPTO_MIGRATION` → `_EXTRACTED_TYPES` (it is no longer crypto-only)
  and add a `calendar → calendar.events` entry: a `MigrationError` message
  pointing at the led-ticker-calendar plugin, with `suggested_fix` to install
  it and use `type = "calendar.events"`.
- Update core tests:
  - drop the `widgets/calendar.py` entry from
    `tests/test_plugin_extraction_readiness.py`'s allowlist.
  - relocate/remove calendar exercises in `tests/test_border_surface_drift.py`.
  - remove validate-rule tests for the deleted rules
    (`tests/test_widgets/test_calendar_validate_contract.py` and the rule-54 /
    two_row / scroll-cutoff calendar assertions in the validate tests).
  - fix docs-config drift tests
    (`tests/test_docs_config_options_drift.py`) for the removed fields.
  - delete moved fixtures (`tests/fixtures/calendar_corpus/`,
    `calendar_sample.ics`) and the moved `test_calendar*.py`.
- Add a `calendar` entry to `src/led_ticker/plugins_catalog.json`
  (`namespace: "calendar"`, `provides: ["calendar.events"]`, homepage, git
  source `JamesAwesome/led-ticker-calendar` ref `main`).
- Update core `CLAUDE.md`: add the `led-ticker-calendar` bullet to the Plugin
  ecosystem list; adjust the "extracted widgets" prose if needed.
- Example configs: convert/remove the calendar block in
  `config/config.example.toml`; move `config/config.calendar_smoketest.toml`
  into the plugin repo.

### Docs-site

Mirror baseball's docs-site treatment of an extracted plugin:
- Reframe `docs/site/src/content/docs/widgets/calendar.mdx` as a plugin page
  (points at the led-ticker-calendar repo; canonical reference content lives in
  the plugin README).
- Update `widgets/index.mdx` (move calendar under plugins / mark extracted) and
  the `concepts/busy-light.mdx` mention.
- Update `docs/content-source/widgets/calendar.md` and the docs-site demo files
  (`demos/widget-calendar*.toml`, `calendar_*sample.ics`) consistent with the
  plugin form, or relocate to the plugin repo.
- Verify deployed pages via `cloudflared access` (the docs site sits behind
  Cloudflare Access; plain curl 302s).

### Deploy note

Each sign's gitignored `config/requirements-plugins.txt` must add
`led-ticker-calendar` (recommend a tag/SHA pin for prod, not `@main`), and each
`config.toml` must migrate `type = "calendar"` → `type = "calendar.events"`.
Same operational shape as the baseball extraction deploy note.

## Sequencing

Four PRs, each on its own branch/worktree (never `main`), each green before the
next. `make dev` in every new worktree before pushing; `ruff check` before push.

1. **Core API — plugin validation warnings channel** (additive). Hook + public
   `ctx` dataclass + validate.py/factories.py wiring + `API_VERSION` bump +
   api-reference doc + drift test. Mergeable on its own; serves weather/rss too.
2. **Plugin repo** — scaffold + verbatim widget + re-homed `validate_config` /
   `validate_config_warnings` + moved tests/fixtures + CI green (≥90% cov).
   Coexists with core's `calendar` (namespaced `calendar.events` does not
   collide), so it is verifiable independently before core removal.
3. **Core removal** — delete widget/deps/rules + `_EXTRACTED_TYPES` breadcrumb
   + catalog entry + core test updates + example-config edits + CLAUDE.md.
4. **Docs-site** — reframe pages, deploy-verify.

## Verification

- Plugin CI green: `ruff check`, `ruff format --check`, `pyright src`,
  `pytest --cov` ≥ 90%; `test_import_purity` passing.
- Core after removal: `make test` + `make lint` green; readiness/drift tripwires
  green.
- `led-ticker validate` on a migrated config surfaces the three re-homed
  warnings through the plugin hook (proves the warnings channel end-to-end).
- A config with bare `type = "calendar"` raises the migration breadcrumb with
  the install/rename guidance.
- Cross-repo dev install (`led-ticker` editable sibling) resolves; the widget
  renders via `make render-demo` / smoketest config.

## Out of scope (optional follow-ups)

- Splitting `calendar.py` into `ics.py` / `format.py` / `render.py` /
  `calendar.py` modules.
- Demo-gif polish beyond a single README gif.
- Migrating the config-skill fact-pack / creating-a-config references for the
  new namespaced type (tracked separately).
- A future busy-light calendar source consuming this plugin (currently only a
  code comment in `busy_light.py`; not built).

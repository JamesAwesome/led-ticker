# Inline value tokens v2 — polled sources (weather)

**Date:** 2026-06-30
**Status:** Approved (brainstorm complete) — ready for an implementation plan.
**Predecessor:** v1 (`docs/superpowers/specs/2026-06-30-inline-value-tokens-v1-design.md`, shipped v3.1.0). v1 shipped synchronous sources (clock/date/static), the `[[source]]` config, `DataSource`/`DataRegistry`/`TokenizedField`, the 1 Hz sync refresh ticker, and the `api.source` plugin surface — and **deferred the polled/async background-loop wiring + any field-format DSL** to v2. This spec is v2.

## Goal

Make a live weather token work: `text = "NYC: :weather.nyc:"` → `"NYC: 72°F Sunny"`, updating in the background. Generalize the deferred **polled-source** path so any plugin can ship an async source via `api.source`; weather is the first consumer.

## Spans two repos, sequenced

- **Core (led-ticker):** the polled-source *mechanism* — `PolledDataSource` base, the deferred spawn wiring, shared-session injection, a plugin-source `validate_config` hook, and a tiny fake polled source for tests. **No weather code.** Ships first as a new minor (~**v3.2.0**).
- **Plugin (led-ticker-plugins/weather):** `WeatherSource` via `api.source`, pinning `led-ticker-core>=3.2.0`. Lands after the core release.

This spec covers both; the implementation plan is **core-first**, then a separate plugin plan.

## Global constraints

- **Core ↔ plugin boundary:** plugins import only `led_ticker.plugin`; `PolledDataSource` is added to `led_ticker.plugin.__all__`. The polled-loop *spawn* machinery is core; the weather *poller* is plugin.
- **Write-order contract (CRITICAL for polled):** a source writes `current` **before** `version`, with **no `await` between**, so a reader sampling version-then-current can never pair a new version with a stale value. v1 sync sources satisfy this trivially; a polled `update()` does its `await`ed fetch first, then assigns `current` then `version` synchronously at the end.
- **Render loop never awaits / never crashes:** `draw()` reads `source.current` (a cached string) — never awaits. A poll crash/fetch-failure logs and the panel keeps running (mirror `run_monitor_loop` + the busy_http supervised pattern).
- **Secrets in `.env`, not config:** `WEATHERAPI_KEY` from env (same as the weather widget).
- PEP 649; DOCS-STYLE (no "footgun"); core gates (`uv run --extra dev pytest`, `ruff check src/ tests/`, `pyright src/`); plugin gates per the monorepo CI. Worktree + PR; never `main`.

## 1. The polled-source mechanism (core)

### `PolledDataSource(DataSource)` (in `sources.py`, exported via `led_ticker.plugin`)
- `polled = True` (overrides the base default).
- Constructed by core's source factory with the per-source config kwargs **plus** an injected shared `session` (an `aiohttp.ClientSession`) and `interval: int` (seconds). A polled source declares its identity by subclassing `PolledDataSource`, so `build_source` can detect it (`issubclass(cls, PolledDataSource)`) and inject `session`/`interval`.
- Subclass implements **`async def update(self) -> None`**: fetch, build the value, then (write-order, no `await` between) set `self.current = <new>` and `self.version += 1` **only if the value changed** (reuse the base's "bump only on change" rule — a small helper `self._set_value(new_str)` that does the change-check + write-order assignment).
- `compute()` is N/A for polled (the base `compute()`/sync `refresh()` are never called on a polled source — the 1 Hz ticker already skips `if not source.polled`).

### Spawn wiring (the v1-deferred part)
- At **startup** (`app/run.py`, where `spawn_source_refresh` is called for sync sources): for each `polled` source in the `DataRegistry`, `spawn_tracked(run_monitor_loop(source, source.interval))`. `run_monitor_loop` already gives exponential backoff + per-call logging + survives exceptions — exactly the supervised behavior required. Store the task handles like the sync ticker's so they can be cancelled on reload.
- At **hot-reload** (`reload.py` `_apply_reload`): the existing atomic registry rebuild + sync-ticker respawn is extended to also **cancel the old polled tasks and spawn new ones** for the new registry's polled sources (mirror the sync-ticker respawn already there).
- **Session:** core creates/owns one shared `aiohttp.ClientSession` (the app already creates one for data widgets) and injects it into polled sources at build. Source build happens after the session exists.

### Source `validate_config` hook (core)
- v1's validate (Rule 56) checks the **core** source types (dup id, emoji collision, unknown type, clock/date format, static value). v2 adds: for a source whose class defines `validate_config(cls, cfg) -> list[str]`, run it during preflight and surface its errors (mirror the widget `_run_validate_config` at `factories.py:560`). This lets a **plugin** source validate its own kwargs (weather: location present, format fields known) at `make validate`.

## 2. The weather source (plugin: led-ticker-plugins/weather)

### `WeatherSource(PolledDataSource)` → `api.source("current")` → type `weather.current`
- The WeatherAPI fetch currently inside `WeatherWidget.update()` is **refactored into one shared module-level helper** (`async def fetch_current(session, location) -> dict`) used by BOTH the widget and the source (DRY; no duplicated client).
- `update()` calls the shared fetch, builds the **fields dict**, then `self._set_value(self._format.format(**self._fields))`.
- **Fields exposed:** `temp_f`, `temp_c`, `condition`, `feelslike_f`, `feelslike_c`, `humidity`, `wind_mph`, `high_f`, `low_f`, and **`emoji`** = `f":{_match_condition(condition)}:"` (the matched condition slug **with colons**).
- **The emoji compose:** because token substitution runs *before* layout, a `format` of `"{temp_f}° {emoji}"` resolves to `"72° :partly_cloudy:"`, and the widget's existing `draw_with_emoji` then renders that slug as a **sprite** — weather tokens get condition icons for free, no special code.
- `register(api)` adds `api.source("current")(WeatherSource)` alongside the existing `api.widget("current")`.

### Field-format
- `format` is a Python `str.format` over the fields; format-specs allowed (`{temp_f:.0f}`). **Default** (omitted): `"{temp_f}°F {condition}"`. One source = one rendered string; **no** sub-field tokens (`:weather.nyc.temp:`) — v1 non-goal.
- `WeatherSource.validate_config(cls, cfg)`: `location` required (str or `{lat, lon}` dict, same as the widget); every `{field}` referenced in `format` must be a known field (parse with `string.Formatter().parse`); unknown field → a clear error.

## 3. Staleness / errors / first value

- Before the first successful fetch, `current` = a `placeholder` (config field, default `"…"`) so the token isn't blank/awkward (`"NYC: …"`).
- On a later fetch failure, **keep the last good value** (the poller's backoff retries; `update()` only `_set_value`s on success).
- Variable width (e.g. `"72°F Sunny"` → `"8°F Thunderstorm"`, or the emoji) is handled exactly as v1 handles clock tokens: the widget re-measures on `version` change (emoji-aware `measure_width`), reflowing at the next safe tick. No new width work.

## 4. Config + dedup

```toml
[[source]]
id = "weather.nyc"
type = "weather.current"
location = "New York, US"        # name / zip / "lat,lon" / {lat=…, lon=…}
interval = 1800                  # seconds; default 30 min
format = "{temp_f}°F {condition}"   # optional; default "{temp_f}°F {condition}"
# placeholder = "…"               # optional; shown until the first fetch
```
`WEATHERAPI_KEY` from `.env`. **Dedup:** one poller per declared source `id`; a `weather.current` *widget* for the same location polls independently (documented — WeatherAPI quota at a 30-min interval is ~1.4k calls/month, negligible; sharing a poll between a widget and a source is a non-goal).

## 5. Testing

**Core:**
- A **fake polled source** (`class _FakePolled(PolledDataSource)` whose `update()` sets a canned value) drives the mechanism without network: startup spawns its loop; `current`/`version` update; the 1 Hz sync ticker does NOT poll it; write-order holds (a reader sampling version-then-current never sees a torn pair — assert via an `update()` that sets current-before-version).
- Spawn wiring: each polled source gets a tracked `run_monitor_loop` task at startup; hot-reload cancels old + spawns new (mirror the sync-ticker reload test).
- A poll that raises is logged and the loop survives (the panel keeps running).
- The source `validate_config` hook runs during preflight + surfaces errors (a fake source with a failing `validate_config` → a validate error).
- `PolledDataSource` is in `led_ticker.plugin.__all__` (drift test).

**Plugin (weather):**
- `WeatherSource.update()` with a mocked `fetch_current` → `current` renders the format; fields populate; the default format applies when omitted.
- The `{emoji}` field yields a colon-wrapped slug; an end-to-end resolve of `"{temp_f}° {emoji}"` → `"72° :partly_cloudy:"`.
- `validate_config`: missing `location` → error; an unknown `{field}` in `format` → error; a valid block → no error.
- The shared `fetch_current` helper is used by both the widget and the source (no duplicated client).

## Non-goals (v2)

- Sub-field tokens (`:weather.nyc.temp:`) — one source = one string.
- Sharing a single poll between a widget and a same-location source.
- Other polled sources (crypto, etc.) — they follow trivially via `api.source` + `PolledDataSource` after v2; not built here.
- A general expression language in `format` beyond `str.format` field interpolation.
- Per-field localization / unit auto-detection beyond exposing both `_f` and `_c` fields.

## Sequencing & releases

1. **Core PR** (this spec's §1 + §3-width-reuse + §5-core tests) on `feat/value-tokens-v2-polled` → review → merge → cut **v3.2.0** (minor; adds the polled-source mechanism + the `PolledDataSource` public surface).
2. **Plugin PR** (led-ticker-plugins/weather: §2) pinning `led-ticker-core>=3.2.0` → review → merge → release the weather plugin.
3. Docs: a "polled sources / weather" section on the value-tokens concept page (core docs) + the weather plugin README.

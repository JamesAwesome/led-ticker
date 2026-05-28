# Pool Monitor Widget — Design Spec

**Date:** 2026-05-27
**Status:** Approved (design); pending implementation plan

## Goal

Add a `pool` widget that displays live pool water temperature on the LED sign by
reading directly from the InfluxDB v2 server that the `pool_monitor` project
writes to. The sign has direct network access to that InfluxDB instance.

The widget cycles through a small set of glanceable screens (title → today →
7-day → season), matching the established "feed monitor" pattern used by the MLB
standings widget.

## Data source

The `pool_monitor` project ingests Inkbird IBS-P02R wireless thermometer
readings via `rtl_433 → MQTT → Telegraf → InfluxDB v2`.

- **InfluxDB:** v2.x, Flux query language, token auth.
- **Measurement:** `mqtt_consumer`
- **Field:** `temperature_C` (float, Celsius)
- **Tags:** `id`, `model`, `channel` (identify the physical sensor)
- **Cadence:** a reading roughly every 10 seconds per sensor.

Battery (`battery_ok`) and the separate `weather` measurement are intentionally
**out of scope** — the sign already has a weather widget, and battery is
maintenance noise on a public sign.

### Connection / credentials

Read from the environment (the sign's `.env`), mirroring how the weather widget
reads `WEATHERAPI_KEY`:

| Variable          | Purpose                  | Source                         |
|-------------------|--------------------------|--------------------------------|
| `INFLUXDB_URL`    | base URL, e.g. `http://influxdb:8086` | env, config may override |
| `INFLUXDB_TOKEN`  | **secret** auth token    | env only                       |
| `INFLUXDB_ORG`    | org, e.g. `pool`         | env, config may override       |
| `INFLUXDB_BUCKET` | bucket, e.g. `pool_temps`| env, config may override       |

The token is **only** read from env (never from `config.toml`). If
`INFLUXDB_TOKEN` is missing, `start()` raises `ValueError` with a clear message,
matching the weather widget's behavior.

## Architecture

### Pattern: feed monitor

`PoolMonitor` follows `MLBStandingsMonitor` exactly:

- `@register("pool")`, `@attrs.define`
- `session: aiohttp.ClientSession` injected
- `@classmethod async def start(...)` → builds the widget, runs an initial
  `await update()`, then `asyncio.create_task(run_monitor_loop(self, update_interval))`
- `async def update(self)` → runs the Flux queries and rebuilds the display
  messages
- Exposes `feed_title` and `feed_stories` (the cycle screens)

`run_monitor_loop` (in `widget.py`) already provides exponential backoff on
fetch errors, so transient InfluxDB/network failures are handled for free — the
last good `feed_stories` keep displaying.

### Integration into the run loop

`PoolMonitor` is a container widget. As of the 2026-05-28 `Container` Protocol
refactor (PR #122), `app/run.py` no longer lists container types explicitly —
any widget that exposes `feed_stories: list[Widget]` satisfies the
`Container` Protocol structurally and is re-expanded by `_expand_sources`
on every pass through the section. `PoolMonitor` declares `feed_stories`
on the class, so no wiring in `app/run.py` is needed; the engine picks it
up automatically. The Container conformance is asserted by
`tests/test_widget_protocol.py::test_container_protocol_recognizes_pool_monitor`.

### Reading InfluxDB (chosen: raw Flux over injected session)

Query via `POST {INFLUXDB_URL}/api/v2/query?org={ORG}` with header
`Authorization: Token {TOKEN}`, `Content-Type: application/vnd.flux`, and
`Accept: application/csv`. Parse the annotated CSV response. This reuses the
same injected `aiohttp.ClientSession` every other widget gets and adds **no new
dependency** (rejected alternative: the `influxdb-client` library, which brings
its own connection handling that doesn't fit the injected-session model).

`update()` issues these reads (measurement `mqtt_consumer`, field
`temperature_C`, optional `id` tag filter):

1. **Current** — `last()` reading (most recent value + its timestamp, for
   staleness).
2. **Trend** — value ~30 min ago (a `last()` over a window ending 30 min back),
   compared to current.
3. **Today** — `min()` / `max()` since local midnight.
4. **7-day** — `mean()`, `min()`, `max()` over the trailing 7 days.
5. **Season** — `min()` / `max()` over the current calendar year.

These can be one multi-yield Flux script or a few small queries; the plan will
decide. All values come back in Celsius.

### Rendering: generic `SegmentMessage` (chosen)

The cycle screens are color-coded segmented lines — exactly what MLB's
`MLBGameMessage` already does (`list[tuple[str, Color]]`, centerable,
font-aware, inline-emoji-capable). That class is generically useful but
mislocated in `mlb.py`.

**Decision:** promote it to a generic `SegmentMessage` in
`widgets/message.py`; have both the MLB widgets and `PoolMonitor` use it. This
is a small, contained move that removes a pool→mlb coupling. (Rejected:
reusing `MLBGameMessage` as-is = coupling; a pool-local copy = ~30 lines of
duplicated draw logic.)

The MLB import sites (`mlb.py`, `mlb_standings.py`) update to the new name. No
behavior change for MLB.

## Display

### The cycle

Each screen is a centered `SegmentMessage`. `feed_title` is the title screen;
`feed_stories` holds the three stat screens.

| # | Screen  | Example (hires)        | Notes |
|---|---------|------------------------|-------|
| 1 | Title   | `POOL TEMPS`           | `feed_title`; text from config `title`, default `"POOL TEMPS"` |
| 2 | Today   | `82°F ▲ 84/78`         | current (zone-colored) + trend arrow + today hi/lo |
| 3 | 7-day   | `7D AVG 80 84/76`      | 7-day mean + 7-day high/low |
| 4 | Season  | `Season HI 88 LO 71`   | current calendar year high/low |

Scope labels are spelled per the table: `7D` for the 7-day screen, and the word
**`Season`** (not `SEA`) for the season screen. In **lores** (160 px logical),
a fully-spelled line that overflows simply scrolls (standard ticker behavior);
hires has the same logical width so it behaves identically.

### Colors

- **Temp number — recolored by zone** (matches the pool_monitor dashboard):
  - `< 70°F` → blue (cool)
  - `70–80°F` → green (normal)
  - `80–90°F` → amber (warm)
  - `≥ 90°F` → red (hot)
  - Zone thresholds are evaluated in the display unit (°F or °C-equivalent
    boundaries).
- **Trend arrow:** green up, red down, gray steady. A deadband of ~0.5°F
  (≈0.3°C) around "no change" prevents flicker between up/steady on tiny
  fluctuations. The plan must confirm which glyphs the BDF (lores) font
  actually contains: prefer `▲`/`▼`/`–` if present, otherwise fall back to
  ASCII `^`/`v`/`-`. Glyph choice can differ between lores and hires.
- **Hi** values use a warm color, **Lo** values a cool color; scope/`AVG`/`HI`/`LO`
  labels are dimmed gray.

### Units

`units` config field (`"imperial"` | `"metric"`), default **`imperial`**.
Stored values are Celsius; convert to °F when imperial. Display rounds to the
nearest whole degree and appends `°F` / `°C` on the headline temp (the compact
hi/lo tags omit the unit suffix).

### Failure / staleness

- **Stale data:** if the newest reading is older than `stale_after` (default
  **900 s / 15 min**), keep showing the last value but render the temp **dimmed**
  (muted gray) as a stale marker.
- **InfluxDB unreachable:** `run_monitor_loop` backoff retries; the previously
  built `feed_stories` continue displaying. On the very first failed `start()`
  (no data ever fetched), build a minimal placeholder so the widget still
  conforms (e.g. title + a dimmed `POOL --`).

### Refresh

`update_interval` config field, default **300 s** (pool water temperature
changes slowly; configurable).

## Configuration

Example `config.toml` block:

```toml
[[playlist.section.widget]]
type = "pool"
title = "POOL TEMPS"        # optional, this is the default
sensor_id = "12345"          # optional; omit to use the only/first sensor
units = "imperial"           # optional, default imperial
update_interval = 300        # optional, seconds
stale_after = 900            # optional, seconds
# influxdb_url / influxdb_org / influxdb_bucket optional config overrides;
# token always comes from INFLUXDB_TOKEN env var
```

Config keys map directly to `@attrs.define` fields (the project's standard
schema mechanism). `sensor_id` omitted → query without an `id` filter (assumes a
single sensor / first match).

## Documentation

The widget ships with docs, matching every other widget:

- **New page** `docs/site/src/content/docs/widgets/pool.mdx` — same structure as
  `weather.mdx`: frontmatter (`title`, `description`), intro paragraph, a
  `<DemoGif>`, a `<TomlExample>` minimal config, an `<OptionsTable>` for all
  config fields, and `<RelatedPages>`. Must document the `.env` requirement
  (`INFLUXDB_URL/TOKEN/ORG/BUCKET`), since the widget is non-functional without
  it.
- **Index table** `docs/site/src/content/docs/widgets/index.mdx` — add a `pool`
  row to the widget table and include `pool` in the "Live data (background
  fetch)" list.
- **Sidebar nav** `docs/site/astro.config.mjs` — add
  `{ label: "pool", link: "/widgets/pool/" }` to the widgets sidebar group.
- **Config example** `config/config.example.toml` — add a commented `pool`
  widget block.
- **Demo gif** `docs/site/demos-long/widget-pool.gif` — a committed deliverable,
  produced via the `making-a-gif` skill and wired into the `<DemoGif>` on
  `pool.mdx` (same as every other widget). It should capture the full cycle
  (title → today → 7-day → season) so the colors and screens are visible.

  Rendering the real widget needs a reachable InfluxDB with data at render
  time. The plan must pick one of: (a) render on a machine that can reach the
  live InfluxDB (using the same `.env`); or (b) provide a small seeding/fixture
  path so the render harness can produce representative values offline. The
  plan should confirm which the `render-demo` tooling can support before
  committing to an approach.

## Testing

Mirror `tests/test_widgets/test_weather.py` and the MLB standings tests:

- **Protocol conformance** — the built `feed_stories`/`feed_title` are valid
  drawable messages; `PoolMonitor` builds without network (mock session).
- **Flux parsing** — feed canned annotated-CSV responses; assert parsed
  current/today/7-day/season values.
- **Zone color selection** — temp value → expected zone color (boundaries:
  69/70, 79/80, 89/90).
- **Trend deadband** — up / down / steady selection including the ±0.5°F
  deadband edges.
- **Unit conversion** — Celsius → Fahrenheit rounding; metric passthrough.
- **Staleness** — reading older than `stale_after` → dimmed temp; fresh →
  normal.
- **Cycle composition** — correct number and order of `feed_stories` (title via
  `feed_title`; today/7-day/season stories).
- **Missing token** — `start()` raises `ValueError` when `INFLUXDB_TOKEN` unset.

## Out of scope

- Battery level display.
- The `weather` measurement (separate weather widget already exists).
- Multi-sensor aggregation / averaging (single configurable `sensor_id`).
- Avg-of-daily-highs style aggregates (7-day = window mean + window min/max).
- Historical graphs / sparklines.

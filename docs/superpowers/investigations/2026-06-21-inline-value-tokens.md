# Investigation: inline value tokens (`:clock.current_time:`, `:weather.nyc:`)

**Date:** 2026-06-21
**Status:** Investigation only — NOT started, NOT yet brainstormed/approved. This records the feasibility findings + a recommended architecture so the work can be picked up later.
**Next step if pursued:** brainstorm → spec for the synchronous-source **v1** (see Scope).

## The idea / use case

Let any widget's text embed inline tokens that resolve to a live string, reusing the existing `:slug:` syntax. Example (a gif/image overlay):

> `"hello! the time is :clock.current_time: and the weather is :weather.nyc:!"`

→ renders with the current time and NYC weather substituted in.

## Difficulty (raw feasibility pass)

The two examples are very different:
- **`:clock.current_time:`** — synchronous, no params, no network. **Medium.** Only hard part: resolved text changes width and breaks a cached-once layout.
- **`:weather.nyc:`** as literally stated (arbitrary parameter, live async data, no shared source) — **Large.** Drags in a whole live-data subsystem.

**But** the config-declared-sources approach (below) collapses the weather case to **Medium-plus / mostly reuse**.

## Key engine constraints (with landmarks)

- **Token syntax already parses this.** `_parse_segments` (`pixel_emoji.py:2506`), regex `:[a-z_][a-z0-9_.]*:` (`pixel_emoji.py:40`) already accepts dotted names; unknown slugs fall through to literal text (no crash). The leading `[a-z_]` keeps `12:30:45` from parsing as a token.
- **Emoji resolve to PIXELS; a value token resolves to a STRING** that must re-flow through glyph layout. So it's NOT a small add to the emoji path — it's a substitution pre-pass feeding the normal text pipeline.
- **Width is computed once and cached** (`message.py:57` `_content_width` sentinel; `drawing.py:66` `_TEXT_WIDTH_CACHE`). Scroll/center/overflow decisions depend on it. Variable-width resolved text ("9:01"→"12:34") makes it stale → layout glitches. **This is the real blocker, not the registry plumbing.**
- **Render loop is synchronous, ~50ms tick** (`ticker.py:1022` ENGINE_TICK_MS=50; `_hold_ticks` ~`:427`). `draw()` must not do I/O/await. A token can only READ a pre-fetched cache.
- **Live data lives per-widget-INSTANCE** (`led-ticker-plugins/plugins/weather/.../weather.py` `self.weather`, polled by `run_monitor_loop` `widget.py:129`). No shared/global cache, no registry of pollers, no param-keyed source.
- **Plugin registries are generic.** Adding a new `api.<thing>(name, fn)` resolver surface is ~4 mechanical touch-points (`plugin.py:305` `easing` is the callable analog; `_plugin_loader.py:28` `_REGISTRY_MAP`; commit loop needs no change). `<namespace>.<name>` + dup-rejection come for free.
- `clock` is currently a **core** widget (`widgets/clock.py`), not a plugin.

## Recommended architecture (from optimization + performance engineer review)

Both specialists converged. The headline: **declare the possible data sources in config** — this is the load-bearing simplification, plus two techniques that make it cheap to render.

### 1. Config-declared sources (the key move)
A top-level `[[source]]` array-of-tables on `AppConfig` (`config.py:321`), **sibling to `sections`** (sources are global, cross-section — do NOT nest in sections). Reuse the existing raw-dict-passthrough pattern (`SectionConfig.widgets` is already `list[dict]` handed to a factory; do the same with a `source(type)` factory mirroring `get_widget_class`).

```toml
[[source]]
id = "weather.nyc"          # the token name (namespaced like everything else)
type = "weather"            # selects the poller class from a registry
location = "New York, US"   # poller-specific kwargs, passed through verbatim
interval = 600
format = "{temp_f}°F {condition}"   # value -> string, poller-defined fields
```

This collapses the hard parts:
- **Parameter → key.** `:weather.nyc:` becomes `registry["weather.nyc"].value` — same fixed-string lookup shape as emoji. No parameterized resolver.
- **One poller per source, dedup by construction.** N references → 1 background poller. (Avoids the longboi "copied snapshot froze" lifecycle trap.)
- **Bounded + pre-validated token set at config-load.** `validate.py` enumerates declared source ids and rejects unknown tokens at preflight (`make validate`) — kills the arbitrary-fetch / rate-limit / abuse surface entirely.
- **Enables a precomputed max-width per source** (from the declared `format`) — the key to the width problem.

### 2. Fixed-width reserved slots (solves the width blocker)
Reserve `max_width_px` per slot, derived from the source's declared `format` at config-load; justify + pad the resolved value inside it. Then the widget's total `_content_width` stays **constant for its whole life** → the existing once-computed width cache stays valid, no relayout, no scroll/center oscillation. A value change just repaints one box. Steady-state per-tick cost ≈ a static string. Add a placeholder value (e.g. `--:--`) sized to the slot so the first real value doesn't trigger a relayout.

### 3. Compile-once template + version-bump change detection
Compile the token'd string ONCE at construction (mirror the existing `_has_emoji`-at-construction pattern, `message.py:62`) into literals + dynamic slots. The **background poller** does change-detection: bump an integer `version` on a source ONLY when its value actually changes. `draw()` does O(segments) int-compares and re-renders a slot only on version mismatch. **Regex/measurement never run on the 50ms tick.** Substitution happens before layout, so `draw_with_emoji` (`pixel_emoji.py:2590`) and the per-char color path need ZERO changes (they see plain text).
- Subtlety: per-char color (rainbow) + padded fixed-width slots — decide padding does NOT advance hue; document as a tripwire.

### 4. One unified `DataSource` abstraction (don't build two systems)
Clock and weather are the SAME abstraction with a `polled: bool` flag:
- **Synchronous** (clock/date/static): `polled=False`, a pure `compute()` — no network/auth/rate-limit.
- **Polled** (weather/crypto): `polled=True`, a background `run_monitor_loop` owns the value.
Same `[[source]]` block, same read site (`registry[id].current`), same validation, same width mechanism. Only branch is at construction (polled spawns a loop; synchronous doesn't).

### 5. Reuse vs genuinely new
**Reuse:** `run_monitor_loop` (backoff/splay/status, `widget.py:129`); `spawn_tracked` (hot-reload teardown, `widget.py:32`); `_parse_segments` (dotted-name parse + registry-or-literal fallback); the generic plugin registry (`api.source(type)` = easing analog, `_plugin_loader.py:30`); `validate.py` preflight; the status board (pollers show up for free).
**Genuinely new (small):** a `DataSource` + `DataRegistry` (one file ≈ `borders.py` size); `[[source]]` parsing → `SourceConfig` (copy the `widgets` raw-dict pattern); the substitution + width-cache-invalidation step (`message.py:83`); the `api.source` plugin surface. Core ships the registry + clock/date sources; plugins contribute the async pollers.
- **Wrong reuse target:** do NOT force this through the ColorProvider interface — ColorProvider is per-frame pure compute; a data source is a cached external value. Superficial resemblance.

## Recommended scope split

- **v1 — synchronous sources only** (`type = "clock" | "date" | "static"`). Proves the whole pipeline (tokenize → registry → substitute → fixed-width slot → render → width-invalidation) end-to-end with zero async/abuse risk. Self-contained **Medium**. Includes the `api.source` surface with the registry complete (so the polled path exists, unused).
- **v2 — first polled source** (weather as a plugin via `api.source`). Now just "add a poller class + prove the background-loop + version-bump path on hardware," not a new subsystem.
- **Defer:** a formatting DSL beyond a single `format` string; any push/observer machinery beyond the integer version counter (YAGNI).

## The one trap to plan for

Width-cache invalidation (`message.py:57`/`:83`) is the only hardware-correctness-adjacent spot — cursor/scroll math depends on `_content_width` being right (CRITICAL constraints #6/#7). Fixed-width slots largely sidestep it by keeping width constant, but it wants a regression tripwire: a `message` with a live token whose value width changes must re-measure and re-decide hold-vs-scroll.

## Open design forks (decide at brainstorm time)

- Reuse `:slug:` syntax (ergonomic, already parses) vs a distinct value-token syntax (conceptually cleaner — values aren't sprites).
- Exact `[[source]]` schema + the `format` field's capability.
- Whether `clock`/`date` ship as core sources or a bundled first-party source plugin.

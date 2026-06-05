# led-ticker Plugin System — Technical Reference

> Engineering reference for the plugin system (Phases A–E + polish, merged in PRs #144–#149). This is the loadable internal/integrator doc — the polished docs-site "Plugins" page is a separate deliverable. Source of truth for the public surface: `src/led_ticker/plugin.py`.

## 1. What it is

Third parties (and the user) can add **widgets, transitions, color providers, animations, borders, easing functions, emojis (lo-res + hi-res), and fonts**, plus **lifecycle hooks** (overlay paint, startup, shutdown), **without editing `src/led_ticker`**. Two delivery channels:

- **Local plugins** — `.py` files or package dirs dropped in `<config dir>/plugins/`.
- **Installed packages** — pip-installed, discovered via a `[project.entry-points."led_ticker.plugins"]` entry point.

Core invariant: **a plugin imports ONLY `led_ticker.plugin`.** Everything else under `led_ticker.*` is internal and may change without notice.

## 2. The `register(api)` contract

> The canonical, reader-facing version of this contract and the full public surface now lives on the docs site: **[Plugin API reference](https://docs.ledticker.dev/plugins/api-reference/)**. This file keeps the loader-internal and deployment detail below.

A plugin is a module (or package `__init__.py`) exposing one top-level function:

```python
# config/plugins/acme.py   (or an installed package's module)
from led_ticker.plugin import Widget

def register(api):
    @api.widget("clock")          # registered as  acme.clock
    class Clock:
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            ...
            return canvas, cursor_pos
```

- The loader builds `api = PluginAPI(namespace, root)` and calls `register(api)`.
- **Namespace** = the file stem / package dir name (local) or the entry-point name (installed).
- Every registered name is **auto-prefixed** with the namespace using a **`.` separator** (`acme.clock`). A plugin literally cannot register a bare/built-in name — the API prefixes for it, so it can never shadow a built-in.
- A module may optionally expose `requires_api = 1` (the major API version it needs).

### Atomic load + error isolation
`api.*` calls **buffer** registrations keyed by the namespaced name; the loader **commits** them into the real registries only if `register(api)` returns cleanly (a two-pass validate-then-write commit). On any exception the buffer is discarded — **no half-registered plugin**. A broken plugin is logged, recorded in `LoadedPlugins.failed`, and skipped; other plugins and the app continue.

## 3. The public surface (`led_ticker.plugin`)

The complete catalog — every registration method, the `__all__` exports, and
the authoring conventions — is the canonical
[Plugin API reference](https://docs.ledticker.dev/plugins/api-reference/) on
the docs site (guarded against drift by
`tests/test_docs_plugin_api_drift.py`). Sections 4–11 below cover what that
page intentionally omits: deeper authoring patterns, loader internals,
deployment, and known edges.

## 4. Widget authoring patterns

### The `Widget.draw` contract
`draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None) -> DrawResult` where `DrawResult = tuple[Canvas, int]` (the canvas + the post-draw cursor x).

### Config fields → use `@attrs.define`
A widget that takes config fields **must** be an `@attrs.define` class (or expose a `start()` classmethod). Config validation derives the allowed fields from `cls.__attrs_attrs__`; a plain class rejects every field as unknown. `attrs` is a standard dependency — importing it directly is fine (only `led_ticker.*` internals are off-limits).

```python
import attrs
from led_ticker.plugin import draw_text, make_color, resolve_font

@api.widget("clock")
@attrs.define          # innermost — must run before @api.widget
class Clock:
    text: str = "12:00"
    font_color: object = None   # declare to accept the font_color knob (see below)

    @classmethod
    def validate_config(cls, cfg):                 # optional pre-flight check
        return ["text must not be empty"] if cfg.get("text") == "" else []

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        font = resolve_font("6x12")
        color = make_color(255, 255, 255)
        if self.font_color is not None and hasattr(self.font_color, "color_for"):
            color = self.font_color.color_for(0, 0, len(self.text))
        return canvas, draw_text(canvas, font, self.text, cursor_pos, 10, color)
```

### The `font_color` convention
To accept the standard `font_color = {style="acme.fire"}` config knob, the widget **declares a `font_color` field** (e.g. `font_color: object = None`). The loader coerces the TOML value to a ColorProvider and injects it into that field. Without the field, `font_color` is rejected as an unknown field. (`font_color` accepts `"rainbow"`/`"color_cycle"`/`"shimmer"`/an RGB list/`{style=...}`.)

### The `animation` / `border` knobs
A plugin widget can host `animation = {style="ns.x"}` / `border = {style="ns.x"}` **only if it declares an `animation` / `border` attrs field** (built-in widgets use a hardcoded allowlist; plugin widgets opt in by declaring the field).

### `validate_config` convention (widgets)
A widget class may define `@classmethod validate_config(cls, cfg) -> list[str]`. It runs during config validation **before coercion** (sees raw TOML values, gets a copy of cfg), and any returned messages become pre-flight errors. Wired for **widgets only** (providers/transitions don't get it). It travels with the type — no `api.*` registration.

### Async / data-fetching widgets — the `start()` classmethod
If a widget class has a `start()` classmethod, the builder calls `await cls.start(session=session, **cfg)` instead of `cls(**cfg)`. This is the pattern for widgets that need the shared `aiohttp.ClientSession` and/or a background poll loop:

```python
@classmethod
async def start(cls, session, update_interval=300, **kwargs):
    widget = cls(session=session, **kwargs)
    await widget.update()                       # initial fetch
    spawn_tracked(_poll_loop(widget, update_interval))   # background refresh
    return widget
```

> NOTE (gap closed, see §10): `run_monitor_loop`, the `SegmentMessage`/`TwoRowMessage` render widgets, and the `Container`/`Updatable` "container" protocols are now **on the public surface** via `led_ticker.plugin`. A data-fetching widget declares `feed_stories`, implements `async update()`, and drives refresh from `start()` via `spawn_tracked(run_monitor_loop(self, interval))`.

## 5. Non-widget surface contracts (minimal shapes)

The minimal class shapes for transitions, color providers, animations,
borders, easings, emojis, and fonts are listed on the
[Plugin API reference](https://docs.ledticker.dev/plugins/api-reference/)
(each with the method it must implement). Worked, build-it-up examples of a
custom transition and color provider are the subject of the forthcoming
extension authoring walkthroughs.

## 6. Lifecycle hooks (the "service plugin" pillar)

```python
_STATE = {"n": 0}

def register(api):
    async def _poll():
        _STATE["n"] += 1                        # a real poller loops with await asyncio.sleep(...)

    def on_startup(ctx):                         # ctx: StartupContext(frame, session, config)
        spawn_tracked(_poll())                  # must be a coroutine

    def paint(canvas):                           # overlay — runs every frame, exception-guarded
        draw_text(canvas, resolve_font("5x8"), str(_STATE["n"]), 0, 7, make_color(0, 200, 0))

    api.on_startup(on_startup)
    api.overlay(paint)
    api.on_shutdown(lambda: _STATE.update(n=0))
```

- `StartupContext(frame, session, config)` — `frame` is the `LedFrame` (`.overlay_hooks`, `.matrix`, `.get_clean_canvas()`, `.swap()`); `session` is the shared `aiohttp.ClientSession`; `config` is the parsed app config.
- Register overlays via `api.overlay` (guarded), **not** by appending to `ctx.frame.overlay_hooks` (unguarded → a raise freezes the panel).
- Run order: `parse config → load plugins → build frame → append plugin overlays → enter session → run on_startup → main loop → (finally) run on_shutdown`.

## 7. `[plugins]` config block

```toml
[plugins]
enabled = true          # default true; false disables ALL discovery (local + entry points)
dir = "plugins"         # default; relative to the config.toml dir (absolute/empty rejected)
disable = ["acme"]      # namespaces to skip (whitespace-stripped)
```

Read by a lightweight `read_plugins_config()` **before** full `load_config` (plugins must register before config validation resolves names). A malformed `[plugins]` block / broken TOML surfaces as a clean error: a `ValidationResult` error (`led-ticker validate`, exit 1) or a clean CLI message (`led-ticker plugins`, exit 2) — never a traceback.

## 8. Discovery, CLI, deployment

- **Local discovery**: each non-`_` `.py` file (namespace = stem) and each package dir with `__init__.py` (namespace = dir name) under the plugin dir.
- **Entry-point discovery**: `importlib.metadata.entry_points(group="led_ticker.plugins")`. A package declares:
  ```toml
  [project.entry-points."led_ticker.plugins"]
  acme = "acme_pkg:register"     # entry-point name = namespace; value = module:register (or module)
  ```
- **`led-ticker plugins`** — lists loaded plugins (namespace, source, contribution **names** like `acme.clock`) + any failures. `led-ticker validate` and `--list-fields ns.x` load plugins first. `--config` works before or after the subcommand.
- **Deployment**: local plugins ride the existing `./config:/code/config:ro` mount → `config/plugins/`. Installed packages are pip-installed into the image (recommended: a `config/requirements-plugins.txt` consumed by a documented Dockerfile layer, or a `FROM led-ticker` user image).

## 9. Loader internals (`led_ticker._plugin_loader`, internal — not for plugins)

- `load_plugins(plugin_dir, *, entry_points_enabled=True, disable=None) -> LoadedPlugins` — idempotent (process-global `_LOADED`; tests call `reset_plugins()`).
- `load_plugins_for_config(config_path)` — config-driven entry used by run / validate / CLI.
- `LoadedPlugins(loaded: list[PluginInfo], failed: list[(ns, err)], overlays, startup_hooks, shutdown_hooks)`. `PluginInfo(namespace, source, counts, names)`.
- `ENTRY_POINT_GROUP = "led_ticker.plugins"`.

## 10. Known surface gaps & edges (as of the polish round)

These are the documented sharp edges + the gaps a real "monitor/feed" widget (e.g. the pool widget) hits — relevant to any data-fetching widget extraction:

- **Monitor/container widgets are supported.** `Container`/`Updatable` protocols, `run_monitor_loop`, and the `SegmentMessage`/`TwoRowMessage` building blocks are re-exported from `led_ticker.plugin`. A data-fetching widget declares `feed_stories`, implements `async update()`, and drives refresh from `start()` via `spawn_tracked(run_monitor_loop(self, interval))`.
- **Font knobs not auto-injected into plugin widgets.** Only `font_color` is injected (and only when declared). `font`/`font_size`/`font_threshold` are built-in-widget conveniences; a plugin widget reads fonts itself via `resolve_font`. (`--list-fields` correctly hides these for plugin widgets.)
- **`validate_config`** is widget-only and pre-coercion (raw config values).
- **hi-res-only emoji** without a lo-res pairing won't render inline / on unscaled canvases (logs a load-time warning).
- **Single-file local plugins share the plugins dir** for `api.font` relative paths — prefer a package dir when bundling fonts.
- **`plugins.dir` allows `..`** (trusted-config model — the operator controls the config and the dir contents).
- **Transition default-slot kwargs**: a plugin transition's config kwargs work per-section and as `between_sections`, but the global `[transitions].default` slot bypasses kwarg parsing (bare-string default works).

## 11. Reference example

`examples/plugins/acme/` is a complete reference plugin exercising every surface + every hook (namespaced `acme.*`), importing only `led_ticker.plugin` (+ `attrs`). An AST test (`tests/test_plugins/test_public_surface_boundary.py`) enforces the import boundary. The full plugin test suite lives under `tests/test_plugins/`.

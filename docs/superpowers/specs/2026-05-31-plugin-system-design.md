# Plugin System — Design

**Date:** 2026-05-31
**Status:** Approved (brainstorming complete)
**Scale:** Largest change to date — touches every extension registry, the config
loader, the validator, the CLI, the run loop, and the deploy story.

## Goal

Let widgets, transitions, emojis, color providers, animations, borders, easing
functions, and **fonts** live **outside** `src/led_ticker` — as local files
(`config/plugins/`) or installed Python packages (entry points) — and register
into the existing registries with **no core fork**. Plus a second pillar of
**lifecycle hooks** (per-type validation, overlay paint, startup/shutdown). All
trusted (no sandboxing), namespaced (no shadowing built-ins), and error-isolated
(a broken plugin never takes down the sign).

## Decisions captured during brainstorming

- **Audience / distribution:** BOTH local-dir plugins and installable
  entry-point packages, through one discovery layer. **Trusted** model — no
  sandboxing (a public/untrusted marketplace was explicitly rejected as out of
  scope).
- **v1 registry surfaces:** widgets, transitions, emojis (lo + hi-res), color
  providers, animations, borders, easing — *plus* **fonts** (added so a plugin
  can ship a widget and the font it needs together).
- **Naming:** **namespaced**. Each plugin declares a namespace (defaults to its
  package/dir name); its contributions are referenced as `namespace.name`.
  Built-ins stay bare. A plugin can never shadow a built-in; two plugins
  claiming one namespace errors at load.
- **Registration style:** **Style A** — each plugin exposes a top-level
  `register(api)` hook; the loader passes a namespace-bound `PluginAPI`.
- **v1 lifecycle hooks:** per-type config validation, overlay paint hooks,
  startup/shutdown hooks. *(Cross-cutting validation rules deferred.)*

## Current extension surfaces (inventory)

Everything below already exists but is locked inside `src/led_ticker`. The
plugin system makes each accept external, namespaced registrations.

| Surface | Today's registry / wiring | Add mechanism today |
| --- | --- | --- |
| Widgets | `_WIDGET_REGISTRY` + `@register` (`widgets/__init__.py`); discovery = **explicit import list** | edit the import list |
| Transitions | `_TRANSITION_REGISTRY` + `@register_transition`; discovery = **pkgutil** auto-scan of `transitions/` | drop a file in the package |
| Color providers | hardcoded `(class, allowed_kwargs)` map in `coercion._provider_from_style` | edit the map |
| Animations | hardcoded map in `coercion._coerce_animation` (`coercion.py:508`) | edit the map |
| Borders | hardcoded `match style` in `coercion._coerce_border` (`coercion.py:305`) | edit the match |
| Easing | `EASING` dict (`transitions/__init__.py`) | edit the dict |
| Emojis | `EMOJI_REGISTRY` / `HIRES_REGISTRY` dicts (`pixel_emoji.py`) | edit `pixel_emoji.py` |
| Fonts | `config/fonts/` dir scan + bundled `fonts/hires/` + BDF aliases | drop a file in `config/fonts/` |

The provider / animation / border maps are the **same shape** — a style name →
`(class, allowed-kwargs)` — so retrofitting them to a registry is one repeated
pattern.

## Architecture: two pillars, one loader

```
 Discovery (one loader)                         Existing registries (made
 ┌─────────────────────────┐                    plugin-aware, namespaced)
 │ config/plugins/*.py|pkg  │   register(api)    ┌──────────────────────────┐
 │   ns = filename          │ ───────────────►   │ _WIDGET_REGISTRY          │
 │ entry_points(            │   PluginAPI bound  │ _TRANSITION_REGISTRY      │
 │   "led_ticker.plugins")  │   to the plugin's  │ _PROVIDER_REGISTRY (new)  │
 │   ns = entry-point name  │   namespace        │ _ANIMATION_REGISTRY (new) │
 └─────────────────────────┘                    │ _BORDER_REGISTRY (new)    │
            │                                    │ EASING / EMOJI_* / fonts  │
            ▼                                    └──────────────────────────┘
   atomic buffer → commit on                     Pillar 2: lifecycle hooks
   success / discard+log on error          ┌───────────────────────────────┐
            │                               │ overlay paint (LedFrame hooks)│
            └─────────────────────────────► │ on_startup / on_shutdown      │
                                            │ per-type validate_config()    │
                                            └───────────────────────────────┘
```

**The public-API boundary is the whole point.** Plugins import *only*
`led_ticker.plugin`. Everything else (`widgets._WIDGET_REGISTRY`,
`coercion._provider_from_style`, etc.) stays internal and refactorable.

## The public API — `led_ticker/plugin.py`

The single author-facing module. Internals live in `led_ticker/_plugin_loader.py`
(discovery/load) — never imported by plugins.

```python
API_VERSION = (1, 0)   # (major, minor); additive within a major

class PluginAPI:
    """Passed to a plugin's register(api). Every name is auto-prefixed with the
    plugin's namespace; registrations buffer and commit atomically."""
    namespace: str

    # --- registry contributions (decorators register the decorated object) ---
    def widget(self, name: str) -> Callable[[type], type]: ...
    def transition(self, name: str) -> Callable[[type], type]: ...
    def color_provider(self, style: str) -> Callable[[type], type]: ...
    def animation(self, style: str) -> Callable[[type], type]: ...
    def border(self, name: str) -> Callable[[type], type]: ...
    def easing(self, name: str, fn: Callable[[float], float]) -> None: ...
    def emoji(self, slug: str, data: PixelData) -> None: ...
    def hires_emoji(self, slug: str, data: HiResEmoji) -> None: ...
    def font(self, name: str, path: str) -> None: ...   # path rel. to plugin root

    # --- lifecycle hooks ---
    def overlay(self, paint: Callable[[Canvas], None]) -> None: ...
    def on_startup(self, fn: StartupHook) -> None: ...
    def on_shutdown(self, fn: ShutdownHook) -> None: ...
```

Re-exported from `led_ticker.plugin` for authors to subclass / annotate:
`Widget`, `AsyncWidget`, `Transition`, `ColorProvider`, `ColorProviderBase`,
`Animation`, `BorderEffect`, `BorderEffectBase`, `Canvas`, `Color`, `PixelData`,
`HiResEmoji`, `StartupContext`, `spawn_tracked`, and the drawing helpers
(`draw_emoji_at`, `measure_emoji_at`, `get_text_width`, `compute_baseline`) plus
`colors`. These are thin re-exports so core module paths can move.

**The `register(api)` contract.** A plugin module/package exposes one
top-level `def register(api): ...`. Example local plugin (namespace `myclock`
from the filename):

```python
# config/plugins/myclock.py
from led_ticker.plugin import Widget

def register(api):
    @api.widget("clock")                     # -> registered as  myclock.clock
    class Clock:                             # satisfies the Widget protocol
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            ...
            return canvas, cursor_pos

    api.font("Brand", "fonts/Brand.ttf")      # -> font  myclock.Brand
    api.easing("snap", lambda p: p * p)       # -> easing myclock.snap
```

**Namespacing & atomic commit.** The loader constructs
`api = PluginAPI(namespace, root)`. Each `api.*` call **buffers** a registration
keyed by the *namespaced* name (`f"{namespace}.{name}"`). The loader calls
`register(api)`; only if it returns without raising are the buffered entries
**committed** into the real registries (and the hook lists). On any exception the
buffer is discarded — no half-registered plugin. A plugin literally cannot
register a bare/un-namespaced name (the API prefixes for it), so it cannot shadow
a built-in.

## Namespace separator: `.` (not `:`) — and why

Plugin-contributed names are referenced as **`namespace.name`** (dot). This
refines the colon shown during brainstorming, for one concrete reason: inline
emoji use a colon delimiter — `EMOJI_PATTERN = re.compile(r":[a-z_]+:")`
(`pixel_emoji.py:37`). A namespaced emoji written `:acme:heart:` would mis-parse
(the regex grabs `:acme:` as the slug `acme`). `:acme.heart:` parses cleanly
once the pattern is widened. So the dot is the only separator that works
uniformly across **all** surfaces, including inline emoji.

Concrete config references:

```toml
type = "acme.clock"                       # plugin widget
transition = "acme.swoosh"                # plugin transition
easing = "acme.snap"                      # plugin easing
font = "acme.Brand"                       # plugin font
font_color = { style = "acme.fire" }      # plugin color provider
animation = { style = "acme.scramble" }   # plugin animation
border = { style = "acme.neon" }          # plugin border
text = "in a meeting :acme.headset:"      # plugin inline emoji
```

`EMOJI_PATTERN` widens to `re.compile(r":[a-z_][a-z0-9_.]*:")` so it admits
`ns.slug` while still matching every built-in `[a-z_]+` slug. The widening must
be applied everywhere the pattern/`re.split` is used (`_parse_segments`,
`draw_with_emoji` at `pixel_emoji.py:2701`).

## Discovery & loading

A single idempotent `load_plugins(config_dir, plugins_cfg) -> LoadedPlugins`
(in `_plugin_loader.py`), called from `app/run.py:run()`, the `validate` CLI
command, and the `--list-fields` command. Guarded so it runs once per process.

**Sequence:**

1. Resolve the local plugin dir: `config/plugins/` relative to the `config.toml`
   directory (same anchoring as `config/fonts/`). Overridable / disablable via
   the `[plugins]` config block.
2. **Local discovery:** each top-level non-`_` `.py` file (namespace = stem) and
   each package dir with `__init__.py` (namespace = dir name) under the plugin
   dir. Import via `importlib` from the file path under a synthetic module name.
3. **Entry-point discovery:** `importlib.metadata.entry_points(group=
   "led_ticker.plugins")`. Each entry: name = namespace, value = `module:register`
   (or `module`, then `module.register`).
4. For each discovered plugin: resolve `register`, check API-version compat,
   build a namespace-bound `PluginAPI(namespace, root)`, call `register(api)`
   inside `try/except`, commit-on-success / log-and-skip-on-error (see Safety).
5. Return `LoadedPlugins` = the committed registry counts (for the `plugins`
   CLI) plus the collected `overlay_hooks`, `startup_hooks`, `shutdown_hooks` for
   the run loop to wire in.

**Where it slots in `run()`:** after `load_config` *parses* the TOML (which
stores raw widget dicts and does NOT resolve widget-type names) and before any
widget is built (`_build_widget` → `get_widget_class`). The `[plugins]` block is
read from the parsed config. Order:
`parse config → load_plugins → build frame → append plugin overlays → enter
session → run plugin on_startup → main loop → (finally) run plugin on_shutdown`.

## Registry retrofits (per surface)

**Widgets / Transitions.** Already `dict` registries. `api.widget` /
`api.transition` insert the namespaced name. The built-in `@register` /
`@register_transition` decorators and pkgutil/import-list discovery are
unchanged. `get_widget_class` / `get_transition` already raise with the
available list.

**Color providers (the structural one).** Replace `coercion._provider_from_style`'s
hardcoded `STYLE_MAP` with a `_PROVIDER_REGISTRY: dict[str, type[ColorProvider]]`.
Built-ins register themselves (move the map into registrations). Allowed kwargs
are **derived from the provider class** (its `attrs` fields / `__init__`
parameters) rather than a hardcoded set, so plugin providers validate kwargs
without bespoke wiring — while preserving the current nice "unknown/missing
kwarg" error messages. `api.color_provider(style)` inserts `ns.style`. Coercion
looks up `font_color = {style="ns.fire", ...}` in the registry.

**Animations / Borders.** Identical treatment — `coercion._coerce_animation`'s
`(class, allowed_kwargs)` map and `_coerce_border`'s `match style` become
`_ANIMATION_REGISTRY` / `_BORDER_REGISTRY`, kwargs derived from the class.
`api.animation` / `api.border` insert namespaced styles.

**Easing.** `api.easing(name, fn)` inserts `ns.name` into `EASING`. Transitions
resolve `easing = "ns.name"` from the same dict.

**Emojis.** `api.emoji` / `api.hires_emoji` insert `ns.slug` into
`EMOJI_REGISTRY` / `HIRES_REGISTRY`. The lo/hi-res fallback, `draw_emoji_at`,
`measure_emoji_at`, and the widened inline `:ns.slug:` parsing all resolve
namespaced slugs. Hi-res-only plugin slugs follow the existing rule (no low-res
fallback → require `scale > 1`).

**Fonts.** A new `_PLUGIN_FONTS: dict[str, FontSource]` maps `ns.name` →
`(plugin_root, relpath)`. `api.font(name, path)` records it; `path` resolves
relative to the plugin's root — `importlib.resources` for an installed package,
the plugin directory for a local one (the `PluginAPI` is constructed with the
right root for each channel). The font loader (`resolve_font` / hires + BDF
loaders) gains a namespaced lookup that consults `_PLUGIN_FONTS` before the
`config/fonts/` → bundled → BDF-alias chain. The existing `@functools.cache`
keying on `(name, size, threshold)` is unchanged (name becomes `ns.font`). Loose
user fonts keep working via `config/fonts/`. Packaging non-Python font files
inside an installed plugin uses standard package-data inclusion.

## Lifecycle hooks (pillar 2)

**Per-type config validation — by convention, not an API call.** A registered
widget / provider class may define:

```python
@classmethod
def validate_config(cls, cfg: dict) -> list[str]:
    return ["text is required"] if not cfg.get("text") else []
```

The static validator (`led-ticker validate`) and `validate_widget_cfg` call it
when present and surface the returned messages as pre-flight errors. This is
cleaner than an `api.validate_type(...)` registration because the rule **travels
with the type** and needs no separate wiring. Field-level validation
(`--list-fields`, unknown-field detection) and construction-time `raise`s remain
free for any `attrs` widget — `validate_config` is for the cross-field rules that
those don't cover.

**Overlay paint.** `api.overlay(paint)` collects a `Callable[[Canvas], None]`.
After the frame is built, the loader appends each to `LedFrame.overlay_hooks`
(the busy-light mechanism). **Divergence from the core overlay invariant:**
because plugin code is less trusted than core, each plugin overlay is wrapped so
an exception **disables that hook and logs once** rather than propagating out of
`swap()` (a raising core hook freezes the panel; a plugin must not be able to).

**Startup / shutdown.** `api.on_startup(fn)` / `api.on_shutdown(fn)` collect
hooks run once around the main loop. `on_startup(ctx)` receives a
`StartupContext(frame, session, config)` and may be sync or async (awaited if a
coroutine); it spins up background work via the public `spawn_tracked` (now
GC-safe). `on_shutdown()` runs best-effort in the run-loop `finally`. Service
plugins (a poller that drives an overlay, an external integration) use these.

## Config — `[plugins]` block

```toml
[plugins]
enabled = true                # default true; false disables all discovery
dir = "plugins"               # default; relative to the config.toml directory
disable = ["acme", "experimental"]   # namespaces to skip loading
```

Validated at load: `enabled` bool, `dir` string, `disable` list of strings.

## CLI & validation integration

- `led-ticker validate CONFIG` — loads plugins first, so plugin widget/provider/
  font/transition types validate (and `validate_config` classmethods run).
- `led-ticker validate --list-fields acme.clock` — loads plugins, lists the
  plugin widget's `attrs` fields (the existing `_list_widget_fields` works on any
  registered class).
- **New** `led-ticker plugins` — lists every loaded plugin: namespace, source
  (local path / entry-point package + version), API version, and a contribution
  summary (e.g. "2 widgets, 1 transition, 1 font, 1 overlay"). Also reports
  plugins that **failed** to load and why.

## Safety & robustness

- **Atomic load:** buffer in `PluginAPI`, commit only on a clean `register(api)`.
  No partially-registered plugin.
- **Error isolation:** every plugin load is wrapped — failure logs `namespace`
  + traceback and is skipped; other plugins and the app continue. A broken
  plugin is a missing namespace, not a crash.
- **Namespace rules:** built-ins bare; plugins `ns.name`; a plugin cannot
  register a bare name (API-enforced); two plugins claiming one namespace → the
  second is rejected and logged.
- **API version:** `led_ticker.plugin.API_VERSION = (1, 0)`. A plugin may declare
  `requires_api = 1` (major); a major mismatch is rejected with a clear message.
  Within a major, only additive changes.
- **Overlay guard:** plugin overlay hooks are exception-wrapped (disable + log),
  unlike core hooks.

## Deployment

- **Local plugins** ride the existing `./config:/code/config:ro` mount →
  `config/plugins/`. Drop `.py` files or package dirs there; reachable in Docker
  with no image change. (`:ro` is fine — the loader only reads.)
- **Installed packages** are `pip install`ed into the image. Recommended
  pattern: a `config/requirements-plugins.txt` consumed by a documented Dockerfile
  layer (or the user's own image `FROM led-ticker`). The package declares its
  entry point in its `pyproject.toml`:
  ```toml
  [project.entry-points."led_ticker.plugins"]
  acme = "acme_led_ticker:register"
  ```
- A `examples/plugins/` directory in the repo ships a complete, working sample
  plugin (one of each surface + a hook) as the canonical reference.

## Testing strategy

- **Fixture plugin** (a local `.py` under a tmp plugin dir) exercising **every**
  surface and hook; assert each registers under the namespace and is *usable*:
  build the widget, run the transition one frame, resolve `ns.Brand`, coerce
  `{style="ns.x"}` into the provider/animation/border, parse `:ns.slug:`, apply
  the easing, the overlay paints, `on_startup`/`on_shutdown` fire.
- **Entry-point channel:** monkeypatch `importlib.metadata.entry_points` to a
  fake entry → same assertions.
- **Error isolation:** a plugin whose `register` raises → logged + skipped,
  siblings load, app continues; assert atomic (no partial registration).
- **Namespace collision:** two plugins, one namespace → second skipped + logged.
- **Shadowing prevented:** a plugin cannot register a bare/built-in name.
- **API version:** incompatible major → skipped with message.
- **Validator/CLI:** `validate` + `--list-fields ns.x` see plugin types;
  `validate_config` messages surface; `plugins` command output.
- **Overlay guard:** a raising plugin overlay is disabled + logged; the panel
  still swaps (use `swapping_frame`).
- **Inline emoji:** `:ns.slug:` parses to one token; built-in `:slug:` unchanged.
- **Font resolution:** from a local plugin dir and a simulated package resource.
- **Tripwires:** the public `led_ticker.plugin` surface is asserted stable (a
  test enumerating its exports), and an AST/import test that plugins never need
  to import internal modules.

## Documentation deliverables

- New docs-site page **"Plugins"**: writing a local plugin, packaging an
  installable one (entry point), the `register(api)` contract, every `api.*`
  method, namespace rules + the `.` separator, the lifecycle hooks, deployment
  (local + image), the `plugins` CLI, and the full `examples/plugins/` walkthrough.
- **CLAUDE.md** invariant: the public-API boundary, atomic load + error
  isolation, the `.` separator (and the emoji-pattern reason), the registry
  retrofits, "plugins load after config parse / before widget build", and the
  plugin-overlay guard divergence.
- `config.example.toml` gains a commented `[plugins]` block.

## File structure

**New:**
- `src/led_ticker/plugin.py` — public author API (`PluginAPI` type, re-exports,
  `API_VERSION`, `StartupContext`).
- `src/led_ticker/_plugin_loader.py` — discovery (local + entry points), atomic
  load, error isolation, namespace binding, hook collection, `LoadedPlugins`.
- `examples/plugins/` — a reference plugin.
- `tests/test_plugins/` — the test suite above + the fixture plugin.

**Modified:**
- `widgets/__init__.py`, `transitions/__init__.py` — thin internal hooks for
  namespaced external registration (built-in registration unchanged).
- `app/coercion.py` — provider/animation/border maps → registries, kwargs
  derived from the class.
- `pixel_emoji.py` — widened `EMOJI_PATTERN`, namespaced emoji resolution.
- fonts loader (`fonts/__init__.py`, `fonts/hires_loader.py`) — `_PLUGIN_FONTS`
  namespaced lookup.
- `app/run.py` — `load_plugins` call + overlay/startup/shutdown wiring.
- `app/cli.py` — load plugins in `validate`/`--list-fields`; `plugins` command.
- `config.py` — `[plugins]` block.
- `app/factories.py` / `validate.py` — call `validate_config` classmethod.
- `config.example.toml`, `CLAUDE.md`, docs site.

## Phasing (guidance for the implementation plan)

One spec, but the plan should stage it so each phase is independently testable:

- **Phase A — framework:** `plugin.py` + `_plugin_loader.py` (both discovery
  channels, namespacing, atomic load, error isolation, API version) wired to
  **widgets + transitions** only. Proves the loader end-to-end.
- **Phase B — coercion registries:** color providers, animations, borders
  (map → registry, kwargs-from-class) + easing.
- **Phase C — emojis + fonts:** widened inline parsing; `_PLUGIN_FONTS` with
  package-resource resolution.
- **Phase D — hooks:** `validate_config` convention, guarded overlay,
  on_startup/on_shutdown + `StartupContext`.
- **Phase E — surface & polish:** `[plugins]` config, `plugins` CLI,
  validate/`--list-fields` integration, `examples/plugins/`, docs, CLAUDE.md.

## Out of scope (v1)

- Cross-cutting validation rules (global rules spanning the whole config).
- Structural surfaces: run-modes, busy-light sources, layouts.
- Sandboxing / permissions / capability limits (trusted model).
- A marketplace / plugin index / remote fetch.
- Hot-reload (plugins load once at startup).
- Loose-font workflow changes — `config/fonts/` stays as-is.

## Success criteria

- A local `config/plugins/foo.py` and an installed entry-point package can each
  contribute a working widget, transition, emoji, color provider, animation,
  border, easing, and font — referenced as `foo.name` in TOML — with no edit to
  `src/led_ticker`.
- Plugins import only `led_ticker.plugin`.
- A broken plugin logs and is skipped; the sign runs; other plugins load.
- `led-ticker validate` / `--list-fields foo.x` / `led-ticker plugins` all see
  plugin contributions.
- Per-type `validate_config`, overlay paint, and startup/shutdown hooks fire.
- `make test` / `make lint` / `make typecheck` green; the public-API tripwire and
  plugin test suite pass.

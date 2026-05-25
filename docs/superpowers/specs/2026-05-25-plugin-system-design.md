# Plugin System Design

**Date:** 2026-05-25  
**Status:** Approved

## Goal

Allow widgets, transitions, emoji, color providers, and animations to be packaged and installed separately from `led-ticker` via pip. Anyone can publish a `led-ticker-*` package to PyPI. Installing it and rebuilding the Docker image is sufficient to activate it — no config changes required beyond using the new type names in TOML.

## Discovery mechanism

Python entry points via `importlib.metadata`. Plugin packages declare a single entry point in their `pyproject.toml` pointing at their top-level module. Led-ticker imports that module at startup; the decorators in it run as side effects, populating the existing registries.

```toml
# plugin's pyproject.toml
[project.entry-points."led_ticker.plugins"]
led_ticker_nba = "led_ticker_nba"

[project.dependencies]
led-ticker = ">=2.0"
```

One entry point per package, regardless of how many widgets/transitions/emoji it registers.

## Plugin loading — `src/led_ticker/plugins.py`

New module. `load_plugins()` discovers and imports all installed plugins before anything else runs.

```python
import importlib.metadata

def load_plugins() -> None:
    for ep in importlib.metadata.entry_points(group="led_ticker.plugins"):
        try:
            ep.load()
        except Exception as e:
            raise RuntimeError(
                f"Plugin {ep.name!r} failed to load: {e}"
            ) from e

def list_plugins() -> list[tuple[str, str, str]]:
    """Return (name, version, module) for each installed plugin. Does not import."""
    dist_map = importlib.metadata.packages_distributions()
    result = []
    for ep in importlib.metadata.entry_points(group="led_ticker.plugins"):
        dist_name = dist_map.get(ep.value, [ep.name])[0]
        try:
            version = importlib.metadata.version(dist_name)
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
        result.append((dist_name, version, ep.value))
    return result
```

`load_plugins()` is called in two places:
- `app/cli.py` — before the display loop starts
- `validate.py` — before config validation runs

Both paths are now plugin-aware. Calling `load_plugins()` twice is safe: the registries check for name collisions and raise on duplicate registration, so the second call is a no-op if the same modules are already imported.

**Fail-fast:** any plugin that fails to import raises `RuntimeError` with the plugin name and the original exception. The app refuses to start.

## Registration API

Plugin authors use the same patterns as built-in code. New helpers are added for the extension points that don't have them yet.

```python
# Widgets — unchanged
from led_ticker.widgets import register

@register("nba_scores")
class NBAScoresWidget: ...

# Transitions — unchanged
from led_ticker.transitions import register_transition

@register_transition("fireworks")
class Fireworks: ...

# Emoji (lo-res 8×8)
from led_ticker.pixel_emoji import register_emoji

register_emoji("basketball", pixels=[(x, y, r, g, b), ...])

# Emoji (hi-res, bigsign only)
from led_ticker.pixel_emoji import register_hires_emoji, HiResEmoji

register_hires_emoji("basketball", HiResEmoji(pixels=(...), physical_size=32))
# _auto_trim_hires is applied automatically

# Color providers
from led_ticker.color_providers import register_color_provider, ColorProvider

@register_color_provider("pulse")
class PulseProvider(ColorProvider):
    frame_invariant = False
    def color_for(self, frame, char_index, total_chars): ...

# Animations
from led_ticker.animations import register_animation

@register_animation("bounce")
class BounceAnimation: ...
```

## Extension point table

| Extension point | Registration function | Status |
|---|---|---|
| Widget | `@register("name")` from `led_ticker.widgets` | this PR |
| Transition | `@register_transition("name")` from `led_ticker.transitions` | this PR |
| Emoji lo-res | `register_emoji(slug, pixels)` from `led_ticker.pixel_emoji` | this PR |
| Emoji hi-res | `register_hires_emoji(slug, hires)` from `led_ticker.pixel_emoji` | this PR |
| Color provider | `@register_color_provider("name")` from `led_ticker.color_providers` | this PR |
| Animation | `@register_animation("name")` from `led_ticker.animations` | this PR |
| Overlay hook | `register_overlay_hook(callable)` from `led_ticker.frame` | **deferred** — lands with `LedFrame.swap()` migration |

The overlay hook extension point is reserved and documented here so the plugin API surface is stable. It is not implemented in this PR. Implementation arrives alongside the `LedFrame.swap()` centralization (the "full compositing" migration that replaces all `frame.matrix.SwapOnVSync` call sites).

## Emoji registry changes

`EMOJI_REGISTRY` is currently lazily populated (via `_build_emoji_registry()` on first access). `HIRES_REGISTRY` is built eagerly from a hardcoded dict at module load. Both need to become mutable after initial construction so `register_emoji` / `register_hires_emoji` can add entries at plugin load time (before first canvas access).

Changes to `pixel_emoji.py`:
- Both registries become plain mutable dicts
- `register_emoji(slug, pixels)` calls `_get_emoji_registry()` to trigger lazy init if needed, then appends — safe to call at any point relative to canvas access
- `register_hires_emoji(slug, hires)` applies `_auto_trim_hires` then appends to `HIRES_REGISTRY`
- Duplicate slug raises `ValueError` (same collision guard as widget/transition registries)

## Color provider and animation registries

Currently providers and animations are resolved by string matching in `_coerce.py` and `app/factories.py` respectively. Both need explicit registries following the same pattern as the widget registry.

New additions:
- `_COLOR_PROVIDER_REGISTRY: dict[str, type[ColorProvider]]` in `color_providers.py`
- `@register_color_provider("name")` decorator
- `_ANIMATION_REGISTRY: dict[str, type]` in `animations.py`
- `@register_animation("name")` decorator
- Built-in providers and animations self-register at module load

`_coerce.py` and `factories.py` look up by registry instead of hardcoded string matching.

## Docker deployment — `plugins.txt`

A `plugins.txt` file at the repo root, standard pip requirements format. Ships empty (all lines commented) so a fresh clone builds unchanged.

```
# led-ticker plugins — one package per line
# led-ticker-nba-scores>=1.0
# led-ticker-weather-icons>=0.5
```

Dockerfile gets one new layer between the deps layer and the source layer:

```dockerfile
# Layer 1: rgbmatrix (slow, rarely changes)
# Layer 2: uv sync (deps)
# Layer 3: plugins  ← new
COPY plugins.txt .
RUN grep -v '^\s*#' plugins.txt | grep -v '^\s*$' | xargs --no-run-if-empty uv pip install

# Layer 4: source
COPY src/ .
```

The `xargs --no-run-if-empty` handles the empty-file case without `|| true`. Layer ordering means plugin installs are cached when only source changes but not the plugin list. `make build-docker` picks this up automatically.

## Local dev — `make install-plugins`

New Makefile target for developing against plugins without a Docker rebuild:

```makefile
install-plugins:
	uv pip install $(shell grep -v '^\s*#' plugins.txt | grep -v '^\s*$$' | tr '\n' ' ')
```

## CLI — `led-ticker plugins list`

New subcommand. Reads installed entry points via metadata only — does not import plugins — so it's fast and safe even if a plugin is broken.

```
$ led-ticker plugins list
Installed plugins (2):
  led-ticker-nba-scores 1.2.0   → led_ticker_nba
  led-ticker-weather-icons 0.5.0 → led_ticker_weather_icons

$ led-ticker plugins list   # when empty
No plugins installed.
```

Wired into `app/cli.py` as `led-ticker plugins list`. The `plugins` subcommand group leaves room for future subcommands (`plugins validate`, `plugins info`) without breaking the interface.

## What changes

| File | Change |
|---|---|
| `src/led_ticker/plugins.py` | New — `load_plugins()`, `list_plugins()` |
| `src/led_ticker/app/cli.py` | Call `load_plugins()` at startup; add `plugins list` subcommand |
| `src/led_ticker/validate.py` | Call `load_plugins()` before validation |
| `src/led_ticker/pixel_emoji.py` | Add `register_emoji()`, `register_hires_emoji()`; make registries mutable |
| `src/led_ticker/color_providers.py` | Add `_COLOR_PROVIDER_REGISTRY`, `@register_color_provider()`; self-register builtins |
| `src/led_ticker/animations.py` | Add `_ANIMATION_REGISTRY`, `@register_animation()`; self-register builtins |
| `src/led_ticker/app/_coerce.py` | Look up providers via `_COLOR_PROVIDER_REGISTRY` instead of hardcoded strings |
| `src/led_ticker/app/factories.py` | Look up animations via `_ANIMATION_REGISTRY` instead of hardcoded strings |
| `plugins.txt` | New at repo root — empty by default |
| `Dockerfile` | New layer to install `plugins.txt` packages |
| `Makefile` | `make install-plugins` target |

## Out of scope for this PR

- `register_overlay_hook` / `LedFrame.swap()` — deferred to the full compositing migration
- Plugin authoring documentation on docs site — follow-up PR
- `plugins.txt` version pinning tooling or lock file — standard pip patterns suffice

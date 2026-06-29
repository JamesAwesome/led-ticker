# led-ticker

[![CI](https://github.com/JamesAwesome/led-ticker/actions/workflows/ci.yml/badge.svg)](https://github.com/JamesAwesome/led-ticker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

![led-ticker — a live LED ticker scrolling weather, crypto, and transit widgets side by side](https://docs.ledticker.dev/demos-long/sections-forever_scroll.gif)

An asyncio Python toolkit that drives RGB LED matrix panels from a Raspberry Pi via a TOML config. It runs HUB75 panels through an Adafruit RGB Matrix HAT (or Bonnet) on top of [`jamesawesome/rpi-rgb-led-matrix`](https://github.com/JamesAwesome/rpi-rgb-led-matrix) — our modified fork of [`hzeller/rpi-rgb-led-matrix`](https://github.com/hzeller/rpi-rgb-led-matrix) that adds Raspberry Pi 5 (RP1) support and a few patches — so anything that library drives, led-ticker drives. Two reference builds share one codebase and one Docker image:

- **Smallsign** — Pi 4 + 5× chained 16×32 panels = 160×16 logical canvas
- **Bigsign** — Pi 5 + 8× P3 32×64 panels in a 2×4 vertical-serpentine layout = 256×64 canvas

New to LED signs? [Why led-ticker?](https://docs.ledticker.dev/why-led-ticker/) covers when a Raspberry Pi HUB75 sign is the right tool — and when WLED, Tidbyt, or an ESP32 clock fits better.

Full documentation: <https://docs.ledticker.dev>

## Showcase

A few of the things a config can put on the wall — every cell links to the page that explains it:

| | | |
|:---:|:---:|:---:|
| [![Two-row layout](https://docs.ledticker.dev/demos-long/widget-two_row.gif)](https://docs.ledticker.dev/widgets/two_row/) | [![Inline emoji in a message](https://docs.ledticker.dev/demos-pinned/message-inline-emoji.gif)](https://docs.ledticker.dev/assets/emoji/) | [![Hi-res "grand opening" message](https://docs.ledticker.dev/demos-pinned/message-hires-grand-opening.gif)](https://docs.ledticker.dev/concepts/fonts/) |
| Held top + scrolling bottom | Inline `:slug:` emoji | Hi-res fonts |
| [![Nyancat sprite-trail transition](https://docs.ledticker.dev/demos-long/transitions-nyancat.gif)](https://docs.ledticker.dev/transitions/) | [![Animated lightbulb border](https://docs.ledticker.dev/demos-pinned/border-lightbulbs-rainbow.gif)](https://docs.ledticker.dev/concepts/borders/) | [![Typewriter reveal with rainbow color](https://docs.ledticker.dev/demos-pinned/message-typewriter-rainbow.gif)](https://docs.ledticker.dev/concepts/animations/) |
| Sprite-trail transitions | Animated borders | Animations + color providers |

## Quick start

Run it straight from a clone for local development and config work:

```bash
git clone https://github.com/JamesAwesome/led-ticker.git
cd led-ticker
make dev
cp config/config.example.toml config/config.toml  # or config.bigsign.example.toml
led-ticker --config config/config.toml
```

**Installing for real?** The [Getting started guide](https://docs.ledticker.dev/getting-started/) is the complete walkthrough — install via Docker, preview configs on your laptop with no hardware attached, then deploy the same image to a Raspberry Pi in under five minutes. For the physical build — BOM, wiring, and panel-tuning — see [building your own](https://docs.ledticker.dev/hardware/building-your-own/).

## Configuration

Everything is configured via a TOML file. Three reference configs ship in `config/`:

- `config.example.toml` — smallsign starter (160×16)
- `config.bigsign.example.toml` — bigsign with `pixel_mapper_config`, scaling, RP1 tuning (256×64)
- `config.firebird.example.toml` — realistic bigsign storefront layout (Firebird Yoga)

Full config reference: <https://docs.ledticker.dev/reference/config-options/>. Per-widget pages document every knob: <https://docs.ledticker.dev/widgets/>.

### Engine

The display engine is published on PyPI as **`led-ticker-core`**:

```bash
pip install led-ticker-core
```

### Plugins

Extra widgets (and other extension points) are installed as plugins, declared in a pip-requirements file. The first-party plugins live in the **[led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins)** monorepo — one package each, each with its own README. Install them like this:

```bash
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
# edit to add/remove plugins, then restart (no image rebuild needed):
docker compose restart
```

The live `config/requirements-plugins.txt` is gitignored (it's yours to customize); the tracked `.example` lists all the first-party plugins (pool, baseball, crypto, calendar, RSS, weather, and the flair transitions) as a starting point — trim it to what your sign uses. Installed plugins auto-register via their `led_ticker.plugins` entry point — no `[plugins]` config change needed.

First-party data plugins are on PyPI — add them by name:

| Plugin | PyPI package | Widget types |
|--------|-------------|--------------|
| Pool | `led-ticker-pool` | `pool.monitor` |
| Baseball / MLB | `led-ticker-baseball` | `baseball.scores`, `.standings`, `.promotions`, `.statcast`, `.attendance` |
| CoinGecko crypto | `led-ticker-crypto` | `crypto.coingecko` |
| Calendar (.ics) | `led-ticker-calendar` | `calendar.events` |
| RSS/Atom feeds | `led-ticker-rss` | `rss.feed` |
| Weather | `led-ticker-weather` | `weather.current` |

The homage sprite-trail transitions (`nyancat`, `pokeball`, `pacman`, `sailor_moon`) ship together on PyPI as **`led-ticker-flair`** — one install adds all four (`transition = "nyancat.forward"` etc.) plus the `:pokeball.ball:` emoji.

Browse the first-party plugins in the [led-ticker-plugins](https://github.com/JamesAwesome/led-ticker-plugins) monorepo — they double as worked examples. Building your own? The [plugin authoring guide](https://docs.ledticker.dev/plugins/) walks you through shipping it as a standalone package in your own repo — no fork, no monorepo PR needed.

Pre-flight a config before deploying:

```bash
make validate CONFIG=config/config.toml
```

`led-ticker validate` checks the config against a registry of decision rules — bad font sizes, scroll-mode + stretch collisions, content-height overflow. Exits non-zero on errors. Useful in CI. Full output format: <https://docs.ledticker.dev/tools/validate/>.

## Development

```bash
make dev        # Install deps (requires uv)
make test       # Run tests (no Docker needed; uses test stubs for rgbmatrix)
make lint       # Run ruff linter
make format     # Auto-format code
make validate CONFIG=config/config.toml  # Pre-flight a config
```

Tests use a stub `rgbmatrix` package so they run on any machine — no Raspberry Pi or Docker required. ~1450 tests, ~2 min on a laptop.

New contributors: start with [CONTRIBUTING.md](CONTRIBUTING.md) (setup, the change flow, where things live). `CLAUDE.md` holds the load-bearing invariants — the hardware-rendering constraints and per-subsystem rules — and has the step-by-step recipes for adding a widget or transition + the test-stub canvas contract.

## Deployment

### Docker on Raspberry Pi

```bash
docker compose up -d
```

The compose file mounts `./config` read-only into the container; edit TOML on the host and the running display hot-reloads most changes live (widgets, sections, schedule, brightness) — a restart is needed only for hardware-level fields like the panel chain or scaling.

### Web UI (optional)

An optional sidecar serves a read-only status dashboard (live preview, monitors, plugins, inventory) plus a token-gated config editor. Enable it with the `webui` compose profile — `COMPOSE_PROFILES=webui docker compose up -d`. Details: <https://docs.ledticker.dev/concepts/web-status-ui/>.

The header shows the deployed build (`build <branch>@<sha>`). Rebuild the sign so the display **and** the webui sidecar both land on the new code with `make rebuild` (a stamped `docker compose up -d --build --force-recreate` with the `webui` profile) — a bare `docker compose up -d --build` rebuilds the image but leaves the profile-gated webui container on the old one.

The compose file's `restart: unless-stopped` policy handles auto-restart on crash and on Pi reboot. Full deploy walkthrough: <https://docs.ledticker.dev/hardware/building-your-own/>.

## Hardware

The single Docker image detects the SoC at runtime and selects the BCM2711 GPIO backend (Pi 4) or the RP1 PIO/RIO backend (Pi 5). On the Pi 5 the RP1 RIO backend is the default; the runtime CLI accepts `--led-rp1-pio=1` to force the low-CPU PIO backend. For chain ≥ 2 with flicker raise `gpio_slowdown` from 2 to 3+.

Hardware reference (BOM, wiring, panel-tuning knobs): <https://docs.ledticker.dev/hardware/building-your-own/>.

### Hardware compatibility

led-ticker works with the same hardware as the underlying `jamesawesome/rpi-rgb-led-matrix` library (our fork of `hzeller/rpi-rgb-led-matrix`):

- **Controller boards:** Adafruit RGB Matrix HAT and RGB Matrix Bonnet (`hardware_mapping = "adafruit-hat"`). Other HUB75 wiring/GPIO mappings supported by the library also work.
- **Panels:** HUB75 RGB LED matrix panels — any pitch (P3, P4, P5, …). The reference builds use P3 32×64 and 16×32 panels; chains and serpentine layouts are configured in TOML.
- **Raspberry Pi:** Pi 4 (BCM2711 GPIO backend) and Pi 5 (RP1 PIO/RIO backend). The single Docker image detects the SoC at runtime.

See the [hardware reference](https://docs.ledticker.dev/hardware/building-your-own/) for BOMs, wiring diagrams, and panel-tuning knobs.

### Calibration & diagnostics

Two deterministic helpers for bringing up a custom panel chain:

- **`panel-test`** — paints the whole wall solid R → G → B → White → Black so you can isolate hardware/wiring/driver issues from your config before touching any TOML. [Docs](https://docs.ledticker.dev/tools/panel-test/)
- **`panel-map`** — derives your `pixel_mapper_config` "Remap" string from a photo of numbered panels, instead of hand-iterating with random text. [Docs](https://docs.ledticker.dev/tools/panel-map/)

## Community

- **Questions, ideas, show-and-tell:** [GitHub Discussions](https://github.com/JamesAwesome/led-ticker/discussions)
- **Bugs & feature requests:** [Issues](https://github.com/JamesAwesome/led-ticker/issues)
- **Contributing:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **Build a plugin:** the [authoring guide](https://docs.ledticker.dev/plugins/) — ship a standalone plugin in your own repo, no fork needed
- **Be excellent to each other:** [Code of Conduct](CODE_OF_CONDUCT.md)
- **Security:** report privately — see [SECURITY.md](SECURITY.md)
- **General contact:** hello@ledticker.dev

## Origins & transparency

led-ticker began as an original asyncio LED-ticker library written by James Awesome, and was developed further with the use of Claude AI.

## License

[MIT](LICENSE) © James Awesome

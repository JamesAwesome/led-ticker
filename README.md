# led-ticker

[![CI](https://github.com/JamesAwesome/led-ticker/actions/workflows/ci.yml/badge.svg)](https://github.com/JamesAwesome/led-ticker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An asyncio Python toolkit that drives RGB LED matrix panels from a Raspberry Pi via a TOML config. It runs HUB75 panels through an Adafruit RGB Matrix HAT (or Bonnet) on top of the [`hzeller/rpi-rgb-led-matrix`](https://github.com/hzeller/rpi-rgb-led-matrix) library, so anything that library drives, led-ticker drives. Two reference builds share one codebase and one Docker image:

- **Smallsign** — Pi 4 + 5× chained 16×32 panels = 160×16 logical canvas
- **Bigsign** — Pi 5 + 8× P3 32×64 panels in a 2×4 vertical-serpentine layout = 256×64 canvas

Full documentation: <https://docs.ledticker.dev>

## Quick start

```bash
git clone https://github.com/JamesAwesome/led-ticker.git
cd led-ticker
make dev
cp config/config.example.toml config/config.toml  # or config.bigsign.example.toml
led-ticker --config config/config.toml
```

For hardware setup, BOM, and wiring diagrams see [docs.ledticker.dev/hardware/building-your-own](https://docs.ledticker.dev/hardware/building-your-own/).

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

Extra widgets (and other extension points) are installed as plugins, declared in a pip-requirements file:

```bash
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
# edit to add/remove plugins, then restart (no image rebuild needed):
docker compose restart
```

The live `config/requirements-plugins.txt` is gitignored (it's yours to customize); the tracked `.example` ships the pool water-temperature widget (`type = "pool.monitor"`) as a starting point. Installed plugins auto-register via their `led_ticker.plugins` entry point — no `[plugins]` config change needed.

First-party data plugins are on PyPI — add them by name:

| Plugin | PyPI package | Widget types |
|--------|-------------|--------------|
| Pool | `led-ticker-pool` | `pool.monitor` |
| Baseball / MLB | `led-ticker-baseball` | `baseball.scores`, `.standings`, `.promotions`, `.statcast`, `.attendance` |
| CoinGecko crypto | `led-ticker-crypto` | `crypto.coingecko` |
| Calendar (.ics) | `led-ticker-calendar` | `calendar.events` |
| RSS/Atom feeds | `led-ticker-rss` | `rss.feed` |
| Weather | `led-ticker-weather` | `weather.current` |

Homage sprite-trail transitions (`nyancat`, `pokeball`, `pacman`, `sailor_moon`) are NOT on PyPI — install them via the `git+https` subdirectory form shown in `config/requirements-plugins.example.txt`.

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

The compose file mounts `./config` read-only into the container so you edit TOML on the host and the container picks it up on restart.

### Systemd

`deploy/led-ticker.service` and `deploy/install.sh` manage auto-start and auto-restart-on-crash. Full deploy walkthrough: <https://docs.ledticker.dev/hardware/building-your-own/>.

## Hardware

The single Docker image detects the SoC at runtime and selects the BCM2711 GPIO backend (Pi 4) or the RP1 PIO/RIO backend (Pi 5). On the Pi 5 the RP1 RIO backend is the default; the runtime CLI accepts `--led-rp1-pio=1` to force the low-CPU PIO backend. For chain ≥ 2 with flicker raise `gpio_slowdown` from 2 to 3+.

Hardware reference (BOM, wiring, panel-tuning knobs): <https://docs.ledticker.dev/hardware/building-your-own/>.

### Hardware compatibility

led-ticker works with the same hardware as the underlying `hzeller/rpi-rgb-led-matrix` library:

- **Controller boards:** Adafruit RGB Matrix HAT and RGB Matrix Bonnet (`hardware_mapping = "adafruit-hat"`). Other HUB75 wiring/GPIO mappings supported by the library also work.
- **Panels:** HUB75 RGB LED matrix panels — any pitch (P3, P4, P5, …). The reference builds use P3 32×64 and 16×32 panels; chains and serpentine layouts are configured in TOML.
- **Raspberry Pi:** Pi 4 (BCM2711 GPIO backend) and Pi 5 (RP1 PIO/RIO backend). The single Docker image detects the SoC at runtime.

See the [hardware reference](https://docs.ledticker.dev/hardware/building-your-own/) for BOMs, wiring diagrams, and panel-tuning knobs.

## Community

- **Questions, ideas, show-and-tell:** [GitHub Discussions](https://github.com/JamesAwesome/led-ticker/discussions)
- **Bugs & feature requests:** [Issues](https://github.com/JamesAwesome/led-ticker/issues)
- **Contributing:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **Be excellent to each other:** [Code of Conduct](CODE_OF_CONDUCT.md)
- **Security:** report privately — see [SECURITY.md](SECURITY.md)
- **General contact:** hello@ledticker.dev

## License

[MIT](LICENSE) © James Awesome

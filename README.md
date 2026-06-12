# led-ticker

[![CI](https://github.com/JamesAwesome/led-ticker/actions/workflows/ci.yml/badge.svg)](https://github.com/JamesAwesome/led-ticker/actions/workflows/ci.yml)

An asyncio Python toolkit that drives RGB LED matrix panels from a Raspberry Pi via a TOML config. Two reference builds share one codebase and one Docker image:

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
- `config.moonbunny.example.toml` — real-world bigsign storefront layout

Full config reference: <https://docs.ledticker.dev/reference/config-options/>. Per-widget pages document every knob: <https://docs.ledticker.dev/widgets/>.

### Plugins

Extra widgets (and other extension points) are installed as plugins, declared in a pip-requirements file:

```bash
cp config/requirements-plugins.example.txt config/requirements-plugins.txt
# edit to add/remove plugins, then rebuild the image:
docker compose up -d --build
```

The live `config/requirements-plugins.txt` is gitignored (it's yours to customize); the tracked `.example` ships the pool water-temperature widget (`type = "pool.monitor"`) as a starting point. Installed plugins auto-register via their `led_ticker.plugins` entry point — no `[plugins]` config change needed.

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

Contributor guide (adding a widget, adding a transition, the test-stub canvas contract): see `CLAUDE.md` in this repo for the load-bearing invariants.

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

## License

See [LICENSE](LICENSE).

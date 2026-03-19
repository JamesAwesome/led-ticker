# led-ticker

An asyncio Python toolkit for displaying scrolling feeds on LED matrix panels.

Display news, weather, countdowns, crypto prices, and custom messages on Adafruit 16x32 LED matrix panels using a Raspberry Pi.

## Quick Start

```bash
# Clone and install
git clone https://github.com/jamesawesome/crypto-ticker.git
cd crypto-ticker
make dev

# Configure
cp config.example.toml config.toml
cp .env.example .env
# Edit config.toml to set up your widgets
# Edit .env to add API keys (weather, etc.)

# Run
led-ticker --config config.toml
```

## Configuration

Everything is configured via a TOML file. See `config.example.toml` for a full reference.

```toml
[display]
rows = 16
cols = 32
chain = 5
brightness = 60

[[playlist.section]]
mode = "forever_scroll"
loop_count = 1

[playlist.section.title]
type = "message"
text = "Headlines"

[[playlist.section.widget]]
type = "rss_feed"
feed_url = "https://www.nintendolife.com/feeds/news"
```

### Display Modes

- **`forever_scroll`** — All widgets scroll side-by-side in a continuous stream
- **`infini_scroll`** — Each widget fully scrolls off before the next appears
- **`swap`** — Instant switching between widgets (no scrolling)

### Built-in Widgets

| Type | Description | Requires |
|------|-------------|----------|
| `message` | Static text | — |
| `countdown` | Days until a date | — |
| `rss_feed` | Headlines from any RSS feed | — |
| `weather` | Current weather | `OPENWEATHERMAP_API_KEY` |
| `coinbase` | Crypto price (Coinbase) | — |
| `coingecko` | Crypto price (CoinGecko) | — |
| `etherscan` | Ethereum gas prices | `ETHERSCAN_API_KEY` |

## Adding a New Widget

Create one file in `src/led_ticker/widgets/`:

```python
import attrs
from led_ticker._compat import require_graphics
from led_ticker.drawing import get_text_width, compute_cursor
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.colors import DEFAULT_COLOR
from led_ticker.widgets import register

@register("my_widget")
@attrs.define
class MyWidget:
    message: str
    font: object = attrs.Factory(lambda: FONT_DEFAULT)
    font_color: object = attrs.Factory(lambda: DEFAULT_COLOR)
    center: bool = True
    padding: int = 6

    def draw(self, canvas, cursor_pos=0, **kwargs):
        graphics = require_graphics()
        content_width = get_text_width(self.font, self.message, padding=0)
        cursor_pos, end_padding = compute_cursor(
            canvas.width, content_width, cursor_pos, self.padding, self.center
        )
        cursor_pos += graphics.DrawText(
            canvas, self.font, cursor_pos, 12, self.font_color, self.message
        )
        cursor_pos += end_padding
        return canvas, cursor_pos
```

Add the import to `src/led_ticker/widgets/__init__.py`, then use it in your config:

```toml
[[playlist.section.widget]]
type = "my_widget"
message = "Hello World"
```

For async widgets that fetch data, implement `update()` and use `run_monitor_loop()` — see `widgets/weather.py` for an example.

## Development

```bash
make dev        # Create venv + install deps
make test       # Run tests (no Docker needed)
make lint       # Run ruff linter
make format     # Auto-format code
```

Tests use a stub `rgbmatrix` package so they run on any machine — no Raspberry Pi or Docker required.

## Deployment

### Docker (on Raspberry Pi)

```bash
cp config.example.toml config/config.toml
cp .env.example .env
docker compose up -d
```

### Bare Metal (on Raspberry Pi)

```bash
sudo bash deploy/install.sh
sudo systemctl start led-ticker
```

## Hardware

Requires Adafruit 16x32 LED matrix panels connected to a Raspberry Pi via the [Adafruit RGB Matrix HAT](https://www.adafruit.com/product/2345). Uses the [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library.

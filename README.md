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
- **`swap`** — Switching between widgets with configurable transitions

### Transitions

Set transitions per-section or globally in `[transitions]`:

| Transition | Effect | Best for |
|------------|--------|----------|
| `cut` | Instant switch, no animation. The old widget disappears and the new one appears immediately. | Default. Fast data displays. |
| `push_left` | Old and new content move together like a conveyor belt — old slides off the left edge while new enters from the right. Both are visible simultaneously during the animation. | General purpose. The most natural-feeling transition. |
| `push_right` | Same as push_left but reversed — old exits right, new enters from left. | Variety. Going "back" in a sequence. |
| `push_up` | Timed vertical cut (true vertical push requires pixel-level rendering). Old content is replaced by new at the midpoint. | Quick section changes. |
| `wipe_left` | New content sweeps across from right to left, replacing old content as it goes. Similar to push_left but the content doesn't slide — the boundary moves across stationary content. | Clean, professional look. |
| `wipe_right` | Same as wipe_left but the boundary moves left to right. | Variety. |
| `color_flash` | Three phases: old content is shown, then the entire display flashes bright white, then new content appears. Inspired by sports scoreboard score updates. | Alerts, countdowns, score changes. |
| `dissolve` | Clean crossfade — old content is shown for the first half, then new content for the second half. | Ambient content. Between sections. |
| `split` | Old content splits apart from the center — the left half slides left, the right half slides right, revealing new content underneath. Like opening a book. | Dramatic reveals. Titles. |
| `curtain` | Old content slides off to the left like a theater curtain opening, revealing new content behind it. | Headlines. Theatrical effect. |
| `nyancat` | A pixel-art Nyan Cat (pop-tart cat) flies across the screen from left to right, trailing a 6-color rainbow. The rainbow wipes away old content and reveals new content in its wake. Best with duration 1.5-2.0s. | Fun. Easter eggs. Showing off your LED sign. |

```toml
[transitions]
default = "push_left"
duration = 0.5
easing = "ease_out"          # linear, ease_out, ease_in_out
between_sections = "dissolve"

[[playlist.section]]
mode = "swap"
transition = "nyancat"       # override per section
```

### Text Presentation Effects

Wrap any widget with a presentation effect:

| Effect | Description |
|--------|-------------|
| `typewriter` | Characters appear one at a time |
| `color_cycle` | Text hue rotates through rainbow |
| `rainbow` | Per-character rainbow sweep |
| `pulse` | Flash to white then decay |
| `bounce` | Scroll in, pause, scroll out |

```toml
[[playlist.section.widget]]
type = "message"
text = "Breaking News!"
presentation = "typewriter"
```

### Built-in Widgets

| Type | Description | Requires |
|------|-------------|----------|
| `message` | Static text | — |
| `countdown` | Days until a date | — |
| `rss_feed` | Headlines from any RSS feed | — |
| `weather` | Current weather with icons | `WEATHERAPI_KEY` |
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

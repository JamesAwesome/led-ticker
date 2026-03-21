# led-ticker

An asyncio Python toolkit for displaying scrolling feeds on LED matrix panels.

Display news, weather, countdowns, crypto prices, and custom messages on Adafruit 16x32 LED matrix panels using a Raspberry Pi.

## Quick Start

```bash
# Clone and install
git clone https://github.com/JamesAwesome/led-ticker.git
cd led-ticker
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
| `cut` | Instant switch, no animation. | Default. Fast data displays. |
| `push_left` | Old and new content move together — old slides off the left edge while new enters from the right. Both visible simultaneously. | General purpose. Most natural. |
| `push_right` | Same as push_left but reversed — old exits right, new enters from left. | Variety. Going "back" in a sequence. |
| `push_up` | Old content slides up off the top while new enters from the bottom. | Countdowns. Section changes. |
| `push_down` | Old content slides down off the bottom while new enters from the top. | Variety. Vertical transitions. |
| `wipe_left` | Cyan sweep line moves right-to-left across stationary content, erasing it to black. Content stays still while the line moves. | Clean, professional look. |
| `wipe_right` | Magenta sweep line moves left-to-right. | Variety. |
| `wipe_up` | White sweep line moves bottom-to-top. | Vertical wipes. |
| `wipe_down` | Green sweep line moves top-to-bottom. | Vertical wipes. |
| `color_flash` | Three phases: old content → solid color flash → new content. | Alerts, score changes. |
| `dissolve` | Random pixel scatter creates a TV static effect. Old degrades, new emerges. | Between sections. Ambient. |
| `split` | Black band expands from center with magenta edge lines. | Dramatic reveals. Titles. |
| `nyancat` | Pixel-art Nyan Cat flies left-to-right trailing a rainbow. Rainbow fills the screen before new content appears. | Fun. Easter eggs. |
| `nyancat_reverse` | Same as nyancat but right-to-left with flipped sprite. | Variety. |
| `scroll` | Seamless continuous scroll with a bullet separator (` * `). Old text scrolls off left, new enters from right at constant speed. Like a news ticker. | RSS feeds. Continuous content. |
| `push_alternating` | Cycles through push_left → push_right → push_up → push_down each swap. | Dynamic variety. |
| `wipe_alternating` | Cycles through wipe_left → wipe_right → wipe_up → wipe_down each swap, each with its own color. Customizable via `transition_colors`. | Dynamic variety. |
| `nyancat_alternating` | Alternates between nyancat and nyancat_reverse each swap. | Fun. |

```toml
[transitions]
default = "push_left"
duration = 0.5
easing = "ease_out"          # linear, ease_out, ease_in_out
between_sections = "dissolve"

[[playlist.section]]
mode = "swap"
transition = "nyancat"       # override per section
transition_duration = 2.0    # override duration per section
transition_color = [255, 0, 0]  # custom color for flash/wipe transitions
# Per-direction colors for wipe_alternating:
# transition_colors = [[0,255,255], [255,0,255], [255,255,255], [0,255,0]]
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
| `mlb` | MLB scores & series info | — (free API) |

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

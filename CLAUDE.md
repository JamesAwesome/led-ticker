# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an asyncio-based Python library for displaying cryptocurrency prices, RSS feeds, weather, and custom messages on LED matrix panels (16x32 Adafruit panels) using a Raspberry Pi. The system runs multiple concurrent monitors that fetch data from various APIs and display scrolling/swapping content on the LED matrix.

## Commands

### Testing
```bash
# Build the test Docker image
make build-test

# Run all tests
make test

# Run tests directly with pytest (if not using Docker)
pytest

# Open a dev shell in test container
make shell
```

### Running the Application
```bash
# Main entry point
python3 scripts/crypto-ticker.py
```

## Architecture

### Core Components

**AsyncTicker** (`src/async_ticker/async_ticker.py`): The main ticker orchestrator that manages display modes:
- `run_forever_scroll()`: Scrolls all monitors side-by-side in a continuous stream with buffer messages between items
- `run_infini_scroll()`: Scrolls monitors one-by-one, each fully scrolling off before the next appears
- `run_swap()`: Swaps between monitors with no scrolling, displaying each for a fixed duration

All three modes support an optional title that displays first with a configurable delay, and can accept a notification queue for priority messages.

**LedFrame** (`src/async_ticker/frame.py`): Wraps the `rgbmatrix.RGBMatrix` with configuration for the LED panel hardware. Initializes the matrix with specific GPIO mappings, brightness, PWM settings, etc., and provides `get_clean_canvas()` for rendering.

**Monitor Widgets**: Self-updating async objects that fetch data and can draw themselves to a canvas at a given cursor position:
- `CoinbasePriceMonitor`: Cryptocurrency prices via Coinbase API (symbol, price, 24h change)
- `CoinGeckoPriceMonitor`: Alternative crypto prices via CoinGecko API
- `EtherscanGasMonitor`: Ethereum gas prices (Low/Avg/High) via Etherscan API
- `RSSFeedMonitor` (`src/async_ticker/async_news_feed.py`): RSS feed stories
- `WeatherWidget`: Current weather via OpenWeatherMap API
- `TickerMessage`: Static text messages with customizable fonts and colors
- `TickerCountdown`: Countdown to a specific date

Each monitor has a `start()` classmethod that initializes it, fetches initial data, and spawns a background task to periodically update its data. The `draw()` method renders the widget to a canvas at the given cursor position and returns the new cursor position.

### Display Flow

1. Monitors are initialized with `await Monitor.start(...)`, which spawns background async tasks that continuously update their data
2. An `AsyncTicker` is created with a list of monitors, a frame, optional title, and optional notification queue
3. The ticker's run method (scroll/swap) is called, which:
   - Enqueus all monitors (and title if present) into a notification queue
   - Continuously renders from the queue using the specified display mode
   - For scrolling modes, each widget draws at a cursor position that moves left each frame
   - Canvas is swapped via `frame.matrix.SwapOnVSync(canvas)` for smooth animation

### Widget Drawing Protocol

All widgets implement `draw(canvas, cursor_pos=0, **kwargs)` which:
- Takes a canvas and starting cursor position
- Renders their content using `graphics.DrawText()` and custom fonts
- Returns `(canvas, new_cursor_pos)` where new_cursor_pos is where the next widget should start drawing
- Most widgets support `center=True` to center content when narrower than canvas width
- Padding is added between elements for visual separation

### Fonts

BDF bitmap fonts in `src/async_ticker/fonts/` (5x8, 6x10, 6x12, 7x13) are loaded via the `rgbmatrix` library. Different font constants in `src/async_ticker/fonts/__init__.py` are used for different elements (FONT_SYMBOL, FONT_PRICE, FONT_CHANGE, etc.).

### Color System

RGB colors are defined in `src/async_ticker/colors.py` using `graphics.Color()`. Common patterns:
- Trend colors: UP_TREND_COLOR (green) for positive changes, DOWN_TREND_COLOR (red) for negative
- RANDOM_COLOR: A cycling iterator through various colors for visual variety
- Widget-specific colors passed as font_color parameters

## Development Notes

### API Keys and Environment Variables

The application uses environment variables for API keys:
- `OPENWEATHERMAP_API_KEY`: Required for WeatherWidget
- Etherscan API key passed directly to EtherscanGasMonitor

### Test Structure

Tests use pytest with fixtures in `tests/conftest.py`:
- `mock_canvas`: Mocked canvas with width=160
- `mock_draw_text`: Mocked `rgbmatrix.graphics.DrawText` that returns text width

Tests run in Docker with access to `/dev/mem` for hardware simulation.

### Adding New Widgets

1. Create a new widget class with attrs (`@attr.s`)
2. Implement `__attrs_post_init__()` if needed for initialization
3. Add a `start()` classmethod that calls `update()` and spawns a monitor task
4. Implement `async def update()` to fetch fresh data
5. Implement `async def monitor(update_interval)` to loop and update periodically
6. Implement `draw(canvas, cursor_pos, **kwargs)` to render the widget
7. Return `(canvas, new_cursor_pos)` from draw

### Hardware Configuration

The LED matrix is configured in `LedFrame.__attrs_post_init__()`. Key parameters:
- `led_gpio_mapping`: Usually "adafruit-hat"
- `led_slowdown_gpio`: Adjust if flickering occurs (typically 1-4)
- `led_brightness`: 0-100, controls overall brightness
- `led_chain`: Number of chained panels
- `led_rows` / `led_cols`: Dimensions of each panel

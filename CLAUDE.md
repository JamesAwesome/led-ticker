# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**led-ticker** is an asyncio Python toolkit for displaying scrolling feeds on LED matrix panels (16x32 Adafruit panels) using a Raspberry Pi. It supports RSS feeds, weather, countdowns, crypto prices, and custom messages via a TOML configuration file.

## Commands

```bash
make dev        # Create venv + install with dev deps
make test       # Run pytest with coverage (no Docker needed)
make lint       # Run ruff linter
make format     # Auto-format with ruff
make clean      # Remove build artifacts
```

## Architecture

### Package Layout

```
src/led_ticker/
  __init__.py          # Package root
  _compat.py           # Lazy rgbmatrix import shim (real lib or stub)
  app.py               # CLI entry point (led-ticker --config config.toml)
  config.py            # TOML config loader (tomllib)
  ticker.py            # Display orchestrator (scroll/swap modes)
  frame.py             # LedFrame hardware wrapper
  widget.py            # Widget/AsyncWidget protocols + run_monitor_loop()
  drawing.py           # Shared drawing helpers (get_text_width, compute_cursor)
  colors.py            # RGB color constants
  fonts/               # BDF bitmap fonts + loader
  widgets/
    __init__.py         # Registry (@register decorator) + auto-imports
    message.py          # TickerMessage, TickerCountdown
    weather.py          # WeatherWidget (OpenWeatherMap)
    rss_feed.py         # RSSFeedMonitor
    crypto/
      coinbase.py       # CoinbasePriceMonitor
      coingecko.py      # CoinGeckoPriceMonitor
      etherscan.py      # EtherscanGasMonitor
```

### Key Patterns

**Widget Protocol**: All widgets implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`. Async widgets also implement `update()` and use `run_monitor_loop()` for background data fetching.

**Widget Registry**: Widgets are registered via `@register("name")` decorator in `widgets/__init__.py`. The config loader uses `get_widget_class(name)` to instantiate widgets from TOML.

**Hardware Abstraction**: `_compat.py` provides lazy rgbmatrix imports. Tests use a stub package in `tests/stubs/rgbmatrix/` that parses real BDF files for accurate font widths.

### Display Flow

1. `app.py` loads TOML config and builds widgets from the registry
2. `Ticker` is created with a list of widgets and a `LedFrame`
3. Ticker runs one of three modes: `run_forever_scroll()`, `run_infini_scroll()`, or `run_swap()`
4. Each mode enqueues widgets and renders them via `draw()` calls
5. Canvas is pushed to hardware via `frame.matrix.SwapOnVSync(canvas)`

### Adding a New Widget

1. Create `src/led_ticker/widgets/my_widget.py`
2. Add `@register("my_widget")` decorator to the class
3. Implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`
4. For async data fetching: implement `update()` and use `run_monitor_loop()`
5. Add the import to `src/led_ticker/widgets/__init__.py`
6. Add to config.toml: `type = "my_widget"`

### Testing

Tests run locally without Docker. The `rgbmatrix` stub at `tests/stubs/rgbmatrix/` provides `Font`, `Color`, `DrawText`, `RGBMatrix`, and `RGBMatrixOptions`.

- `make test` sets `PYTHONPATH=tests/stubs` automatically
- Widget tests go in `tests/test_widgets/`
- Use `@attrs.define` for widget classes
- Use `compute_cursor()` for centering logic (don't duplicate it)

### Configuration

TOML config at `config.toml` (see `config.example.toml`). Environment variables for API keys in `.env` (see `.env.example`).

### Hardware

- LED matrix configured in `LedFrame.__attrs_post_init__()`
- `led_gpio_mapping`: Usually "adafruit-hat"
- `led_slowdown_gpio`: Adjust if flickering (1-4)
- `led_brightness`: 0-100
- `led_chain`: Number of chained panels

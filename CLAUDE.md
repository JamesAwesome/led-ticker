# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**led-ticker** is an asyncio Python toolkit for displaying scrolling feeds on LED matrix panels (16x32 Adafruit panels) using a Raspberry Pi. It supports RSS feeds, weather with icons, countdowns, crypto prices, custom messages, animated transitions, and text presentation effects — all via a TOML configuration file.

## Commands

```bash
make dev        # Create venv + install with dev deps
make test       # Run pytest with coverage (no Docker needed)
make lint       # Run ruff linter
make format     # Auto-format with ruff
make clean      # Remove build artifacts
make build-docker  # Build production Pi Docker image
```

## Architecture

### Package Layout

```
src/led_ticker/
  __init__.py          # Package root
  _compat.py           # Lazy rgbmatrix import shim (real lib or stub)
  app.py               # CLI entry point (led-ticker --config config.toml)
  config.py            # TOML config loader (tomllib/tomli)
  ticker.py            # Display orchestrator (scroll/swap modes)
  frame.py             # LedFrame hardware wrapper
  widget.py            # Widget/AsyncWidget protocols + run_monitor_loop() with backoff
  drawing.py           # Shared drawing helpers (get_text_width, compute_cursor)
  colors.py            # RGB color constants
  transition.py        # Transition effects + registry + runner
  presentation.py      # Text presentation effects (typewriter, rainbow, etc.)
  shadow_canvas.py     # Offscreen pixel buffer for compositing
  fonts/               # BDF bitmap fonts + loader (generic names: FONT_LABEL, FONT_VALUE, etc.)
  widgets/
    __init__.py         # Registry (@register decorator) + auto-imports
    message.py          # TickerMessage, TickerCountdown
    weather.py          # WeatherWidget (WeatherAPI.com) with 8x8 pixel icons
    weather_icons.py    # 7 weather condition icons (sun, cloud, rain, snow, thunder, fog, partly cloudy)
    rss_feed.py         # RSSFeedMonitor (no draw() — stories expand into TickerMessages)
    nyancat.py          # Nyan Cat sprite + rainbow trail for transitions
    crypto/
      coinbase.py       # CoinbasePriceMonitor
      coingecko.py      # CoinGeckoPriceMonitor
      etherscan.py      # EtherscanGasMonitor
```

### Key Patterns

**Widget Protocol**: All widgets implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`. Async widgets also implement `update()` and use `run_monitor_loop()` for background data fetching with exponential backoff on errors (60s min, 1hr max).

**Widget Registry**: `@register("name")` decorator. Config loader uses `get_widget_class(name)`.

**Transition Registry**: `@register_transition("name")` decorator. 11 transitions available.

**Presentation Registry**: `@register_presentation("name")` decorator. 5 text effects available.

**Hardware Abstraction**: `_compat.py` provides lazy rgbmatrix imports. Tests use stubs in `tests/stubs/rgbmatrix/` with BDF font parsing and pixel storage.

**CRITICAL: ShadowCanvas vs Real Canvas**: The real rgbmatrix `graphics.DrawText` is a C function that type-checks its canvas argument — it rejects `ShadowCanvas`. Any code that calls `widget.draw()` must pass a real canvas or the test stub canvas. The `_render_to_shadow()` helper in `transition.py` tries ShadowCanvas and catches `TypeError` to fall back gracefully on real hardware. Compositing transitions use pixel-accurate rendering in tests but fall back to simpler rendering on real hardware.

### Display Flow

1. `app.py` loads TOML config (`config/config.toml`) and builds widgets from the registry
2. `Ticker` is created with widgets, frame, optional transition config, and hold_time
3. Ticker runs one of three modes: `run_forever_scroll()`, `run_infini_scroll()`, or `run_swap()`
4. In swap mode: each widget is held (and scrolled if overflowing), then a transition runs to the next widget
5. Between playlist sections: a section-to-section transition runs
6. Canvas is pushed to hardware via `frame.matrix.SwapOnVSync(canvas)`

### Transition System

- **Push-based** (cursor_pos manipulation, works everywhere): push_left, push_right, push_up, color_flash, cut
- **Compositing** (ShadowCanvas pixel rendering, falls back on real hardware): wipe_left, wipe_right, dissolve, split, curtain, nyancat
- Transitions are configured globally in `[transitions]` and overridden per-section
- `run_transition()` runs from t=0.0 to t=1.0 inclusive — no separate "final frame"
- After a transition, `_swap_and_scroll(skip_initial_draw=True)` avoids redundant re-draw
- No black flash between sections — last widget stays on screen

### Text Presentation Effects

`WidgetPresenter` wraps any widget and adds frame-aware rendering:
- typewriter, color_cycle, rainbow, pulse, bounce
- Configured per-widget: `presentation = "typewriter"`

### Weather Widget

- Uses WeatherAPI.com (env var `WEATHERAPI_KEY`)
- API key read at runtime via `os.getenv` (not import time)
- `start()` catches initial update failure — app continues, retries in background
- 8x8 pixel weather icons (show_icon config, default true)
- Location is a string: city name, zip code, or "lat,lon"
- Dict locations from TOML auto-converted to "lat,lon" string

### RSSFeedMonitor

- Has NO `draw()` method — does not satisfy Widget protocol directly
- `app.py` expands `widget.feed_stories` into the widget list (list of TickerMessages)
- Never pass an RSSFeedMonitor to a Ticker's monitors list directly

### Error Handling

- `run_monitor_loop()` has exponential backoff: 60s → 120s → 240s → ... → 1hr max
- Resets to normal interval on successful update
- All async widget `update()` errors are caught — display continues with stale data
- Weather widget validates API error responses and raises clear `ValueError`

### Adding a New Widget

1. Create `src/led_ticker/widgets/my_widget.py`
2. Add `@register("my_widget")` decorator to the class
3. Implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`
4. For async data fetching: implement `update()` and use `run_monitor_loop()`
5. Add the import to `src/led_ticker/widgets/__init__.py`
6. Add to config.toml: `type = "my_widget"`

### Adding a New Transition

1. Add to `src/led_ticker/transition.py`
2. Add `@register_transition("my_transition")` decorator
3. Implement `frame_at(t, canvas, outgoing, incoming)` where t is 0.0-1.0
4. At t=0: show only outgoing. At t=1.0: show only incoming.
5. For pixel compositing: use `_render_to_shadow()` with fallback

### Testing

245+ tests, 90%+ coverage, runs in <1s with no Docker.

- `make test` sets `PYTHONPATH=tests/stubs` automatically
- Test stubs provide pixel storage (`_StubCanvas.SetPixel/get_pixel`)
- Stub `DrawText` writes actual pixels for compositing test coverage
- Widget tests in `tests/test_widgets/`
- Transition tests in `tests/test_transitions.py` and `tests/test_nyancat.py`
- Shared fixtures in `tests/conftest.py`: `canvas`, `mock_frame`, `make_widget`
- Async tests use `monkeypatch` to patch `asyncio.sleep` for instant execution
- Weather tests need `monkeypatch.setenv("WEATHERAPI_KEY", "test-key")`

### Configuration

- App config: `config/config.toml` (mounted in Docker)
- Example: `config.example.toml`
- API keys: `.env` (see `.env.example`)
- Per-section: `mode`, `transition`, `transition_duration`, `hold_time`, `loop_count`
- Per-widget: `presentation`, `show_icon` (weather)
- Global: `[transitions] default`, `duration`, `easing`, `between_sections`

### Docker / Deployment

- Production image: `python:3.13-bullseye` base
- rgbmatrix built from fork: `github.com/jamesawesome/rpi-rgb-led-matrix` (vendored Pillow struct, Python 3.9+ support)
- Config mounted read-only via docker-compose: `./config:/code/config:ro`
- Systemd service: `deploy/led-ticker.service`
- Bare-metal install: `deploy/install.sh`

### Hardware

- Target: Raspberry Pi 4 Model B, 5 chained 32x16 panels = 160x16 pixels
- `led_gpio_mapping`: "adafruit-hat"
- `led_slowdown_gpio`: 2 (adjust if flickering)
- `led_brightness`: 60
- Display refreshes at ~20fps (0.05s per frame)

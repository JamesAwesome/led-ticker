# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**led-ticker** is an asyncio Python toolkit for displaying scrolling feeds on LED matrix panels (16x32 Adafruit panels) using a Raspberry Pi. It supports RSS feeds, weather with icons, countdowns, crypto prices, custom messages, animated transitions, and text presentation effects — all via a TOML configuration file.

## Commands

```bash
make dev        # uv sync (install all deps)
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
  fonts/               # BDF bitmap fonts + loader
  widgets/
    __init__.py         # Registry (@register decorator) + auto-imports
    message.py          # TickerMessage, TickerCountdown
    weather.py          # WeatherWidget (WeatherAPI.com) with 8x8 pixel icons
    weather_icons.py    # 7 weather condition icons
    rss_feed.py         # RSSFeedMonitor (no draw() — stories expand into TickerMessages)
    nyancat.py          # Nyan Cat sprite + rainbow trail for transitions
    crypto/
      coinbase.py       # CoinbasePriceMonitor
      coingecko.py      # CoinGeckoPriceMonitor
      etherscan.py      # EtherscanGasMonitor
```

### Key Patterns

**Widget Protocol**: All widgets implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`. All draw() methods support `y_offset` via kwargs (default 0), used for vertical transitions. Async widgets also implement `update()` and use `run_monitor_loop()` with exponential backoff.

**Widget Registry**: `@register("name")` decorator. Config loader uses `get_widget_class(name)`.

**Transition Registry**: `@register_transition("name")` decorator. 18 transitions available.

**Presentation Registry**: `@register_presentation("name")` decorator. 5 text effects available.

### CRITICAL: Hardware Rendering Constraints

These constraints were learned through extensive real-hardware testing:

1. **SwapOnVSync return value MUST be captured**: `canvas = frame.matrix.SwapOnVSync(canvas)`. The return value is the previous front buffer which becomes the new back buffer. If discarded, you draw to the actively-displayed buffer, causing tearing and corruption. EVERY call site must capture this.

2. **DrawText rejects non-Canvas objects**: The real rgbmatrix `graphics.DrawText` is a C function that type-checks for `rgbmatrix.core.Canvas`. Python objects like ShadowCanvas will get `TypeError`. Never call `widget.draw()` on anything other than a real canvas or the test stub canvas.

3. **No GetPixel**: Cannot read pixels back from any canvas. The framebuffer stores pre-computed GPIO bitplane data, not RGB values. Reverse mapping is infeasible.

4. **SetPixel works everywhere**: `canvas.SetPixel(x, y, r, g, b)` works on real canvases, test stubs, and any object. All transition visual effects use SetPixel.

5. **Swap-then-sleep ordering**: Always `SwapOnVSync` first, then `asyncio.sleep`. Never sleep before swap — it adds frame latency.

6. **Font advance width ≠ visible glyph width**: BDF font characters have advance widths that include trailing whitespace within the character cell. When text scrolls to the right edge, the cursor reaches x=159 but the last visible pixel may be 2-3px earlier depending on the character (e.g., "!" is narrow within its cell, "M" fills it). This is standard bitmap font behavior, not a bug.

7. **Widget padding is for layout, not scroll stop**: `draw()` returns `cursor_pos` which includes `end_padding` (default 6px). This padding provides spacing between widgets in `forever_scroll` side-by-side mode — do NOT remove it from the widget. Instead, `_swap_and_scroll` ADDS padding back to stop_pos to compensate: `stop_pos = -(cursor_pos - canvas.width) + padding`. Since cursor_pos overshoots by padding, adding it scrolls less far left, putting the last character flush with x=159.

6. **Test stubs simulate double-buffering**: The stub `SwapOnVSync` returns a DIFFERENT canvas object (not the same one) to catch code that discards the return value.

### Display Flow

1. `app.py` loads TOML config and builds widgets from the registry
2. `Ticker` is created with widgets, frame, transition config, and hold_time
3. Ticker runs one of three modes: `run_forever_scroll()`, `run_infini_scroll()`, or `run_swap()`
4. In swap mode: each widget is held (scrolled if overflowing), then transition runs
5. `run_transition()` returns the current back-buffer canvas — caller must capture it
6. Between sections: a section-to-section transition runs
7. Canvas pushed to hardware via `canvas = frame.matrix.SwapOnVSync(canvas)`

### Transition System

All transitions work on real hardware. They fall into three categories:

**Push-based** (rapid scroll — both contents move together):
- `push_left` — rapid scroll left: outgoing exits left, incoming enters from right
- `push_right` — rightward push: incoming enters from left at pos=0, outgoing exits right at pos=boundary (avoids DrawText rightward-bleed overlap)
- `push_up` — rapid scroll up: outgoing exits top, incoming enters from bottom
- `push_down` — rapid scroll down: outgoing exits bottom, incoming enters from top

Push transitions use draw-blackout-draw: draw outgoing at its scroll position, SetPixel-blackout the zone where incoming will appear, then draw incoming. This prevents overlap since DrawText cannot be clipped. They receive `outgoing_scroll_pos` from `_swap_and_scroll` via `run_transition` kwargs so they can continue from where the text stopped scrolling.

**Instant/flash**:
- `cut` — instant switch
- `color_flash` — white flash between content

**Wipe-based** (stationary outgoing + sweep line erase):
- `wipe_left` — stationary outgoing + sweep line moving right-to-left
- `wipe_right` — stationary outgoing + sweep line moving left-to-right
- `wipe_up` — stationary outgoing + sweep line erasing bottom-to-top
- `dissolve` — random pixel scatter (seeded RNG) creates TV static effect
- `split` — center-outward expanding black band with magenta edge lines
- `wipe_down` — top-down row blackout with sweep line (formerly 'curtain')
- `nyancat` — Nyan Cat flies left-to-right, rainbow fills screen before cut
- `scroll` — seamless continuous scroll with bullet dot separator (2x2 SetPixel, 6px symmetric gaps). Uses `_scroll_between` at 1px/frame for constant speed. Note: `forever_scroll` mode uses a text `•` character via `DEFAULT_BUFFER_MSG` with cursor-based spacing — visually similar but different rendering approach.
- `nyancat_reverse` — Nyan Cat flies right-to-left (flipped sprite), rainbow fills screen
- `pokeball` — Pokeball rolls left-to-right with Pikachu chasing; 4-frame rotation, 4-frame Pikachu run cycle
- `pokeball_reverse` — Pokeball + Pikachu right-to-left (flipped sprites)
- `pokeball_alternating` — cycles through pokeball → pokeball_reverse each swap
- `baseball` — white baseball with red stitching rolls left-to-right; 4-frame stitch rotation
- `baseball_reverse` — baseball right-to-left (flipped)
- `baseball_alternating` — cycles through baseball → baseball_reverse each swap
- `push_alternating` — cycles through push_left → push_right → push_up → push_down each swap
- `nyancat_alternating` — cycles through nyancat → nyancat_reverse each swap
- `wipe_alternating` — cycles through wipe_left → wipe_right → wipe_up → wipe_down each swap

**How wipe transitions work**: Draw outgoing widget at pos=0 (stationary text), then use SetPixel to black out regions and draw colored sweep lines on top. At t=1.0, snap to incoming. This avoids the compositing problem entirely — no need to draw both widgets or read pixels back.

### Text Presentation Effects

`WidgetPresenter` wraps any widget with frame-aware rendering:
- typewriter, color_cycle, rainbow, pulse, bounce
- Configured per-widget: `presentation = "typewriter"`

### Adding a New Widget

1. Create `src/led_ticker/widgets/my_widget.py`
2. Add `@register("my_widget")` decorator
3. Implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`
4. Support `y_offset = kwargs.get("y_offset", 0)` — use `12 + y_offset` in DrawText
5. For async data: implement `update()` and use `run_monitor_loop()`
6. Add import to `src/led_ticker/widgets/__init__.py`

### Adding a New Transition

1. Add to `src/led_ticker/transition.py`
2. Add `@register_transition("name")` decorator
3. Implement `frame_at(t, canvas, outgoing, incoming)` where t is 0.0-1.0
4. At t=0: show only outgoing. At t=1.0: show only incoming.
5. Use SetPixel for visual effects (sweep lines, blackout regions) — NOT ShadowCanvas
6. Never call `widget.draw()` on anything other than the real `canvas` parameter

### Testing

275+ tests, 92% coverage, runs in ~1s with no Docker.

- `make test` sets `PYTHONPATH=tests/stubs` automatically
- Test stubs simulate double-buffering (SwapOnVSync returns different canvas)
- Stub `DrawText` writes actual pixels for pixel-level test assertions
- Weather tests need `monkeypatch.setenv("WEATHERAPI_KEY", "test-key")`

### Configuration

- App config: `config/config.toml` (mounted in Docker at `/code/config/`)
- Example: `config.example.toml`
- API keys: `.env` (see `.env.example`)
- Per-section: `mode`, `transition`, `transition_duration`, `transition_color`, `hold_time`, `loop_count`
- Per-widget: `presentation`, `show_icon` (weather)
- Global: `[transitions] default`, `duration`, `easing`, `between_sections`

### Docker / Deployment

- Production image: `python:3.13-bullseye` base, 3-layer caching (rgbmatrix → deps → source)
- rgbmatrix from fork: `github.com/jamesawesome/rpi-rgb-led-matrix`
- Config mounted read-only: `./config:/code/config:ro`
- Systemd: `deploy/led-ticker.service`

### Hardware

- Raspberry Pi 4 Model B, 5 chained 32x16 panels = 160x16 pixels
- `led_gpio_mapping`: "adafruit-hat"
- `led_slowdown_gpio`: 2
- `led_brightness`: 60
- ~20fps (0.05s per frame)
- DrawText clips safely at canvas edges (y can be negative or > height)

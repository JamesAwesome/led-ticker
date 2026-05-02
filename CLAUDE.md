# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**led-ticker** is an asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels using a Raspberry Pi. It supports RSS feeds, weather with icons, countdowns, crypto prices, custom messages, animated transitions, and text presentation effects — all via a TOML configuration file.

Two hardware targets share one codebase and one Docker image:

- **Small sign** — Pi 4 + 5× chained 16×32 Adafruit panels = 160×16 logical canvas
- **Bigsign** — Pi 5 + 8× P3 32×64 panels in a 2×4 vertical-serpentine layout = 256×64 logical canvas, rendered via `ScaledCanvas` (drawing logic stays at "1× scale" with 16-tall content; the wrapper scales SetPixel calls to scale×scale blocks and vertically centers the content)

## Commands

```bash
make dev        # uv sync (install all deps)
make test       # Run pytest with coverage (no Docker needed)
make lint       # Run ruff linter
make format     # Auto-format with ruff
make clean      # Remove build artifacts
make build-docker  # Build production Docker image (single image, both Pis)
```

## Architecture

### Package Layout

```
src/led_ticker/
  __init__.py          # Package root
  _compat.py           # Lazy rgbmatrix import shim (real lib or stub)
  _types.py            # Canvas type alias used across the package
  app.py               # CLI entry point (led-ticker --config config.toml)
  config.py            # TOML config loader (tomllib/tomli)
  ticker.py            # Display orchestrator (scroll/swap/forever_scroll modes)
  frame.py             # LedFrame hardware wrapper
  scaled_canvas.py     # ScaledCanvas: wraps a real canvas and scales SetPixel
                       #   to scale×scale blocks (used by bigsign, scale=4)
  text_render.py       # Pure-Python BDF rasterizer (needed when scale > 1
                       #   because graphics.DrawText cannot scale)
  widget.py            # Widget/AsyncWidget protocols + run_monitor_loop() with backoff
  drawing.py           # Shared drawing helpers (get_text_width, compute_cursor)
  colors.py            # RGB color constants (DEFAULT_COLOR, RGB_WHITE,
                       #   UP_TREND_COLOR/DOWN_TREND_COLOR/NEUTRAL_TREND_COLOR
                       #   for crypto/finance widgets, etc.)
  presentation.py      # Text presentation effects (typewriter, rainbow, etc.)
  pixel_emoji.py       # Inline pixel-art emoji renderer (:name: in messages)
  fonts/               # BDF bitmap fonts + loader
  transitions/
    __init__.py         # Transition protocol, registry, easing, run_transition()
    push.py             # PushLeft/Right/Up/Down, PushAlternating
    wipe.py             # _BaseWipe, WipeLeft/Right/Up/Down, WipeAlternating
    effects.py          # Cut, ColorFlash, Dissolve, SplitHorizontal, Scroll
    nyancat.py          # NyanCat/Reverse/Alternating + sprite data + draw functions
    pokeball.py         # Pokeball/Reverse/Alternating + Pikachu sprites + draw functions
    baseball.py         # Baseball/Reverse/Alternating + sprite data + draw functions
    pacman.py           # Pacman/Reverse/Alternating + ghost sprites + draw functions
    sailor_moon.py      # SailorMoon/Reverse/Alternating + Moon Stick sprite + sparkle trail
  widgets/
    __init__.py         # Registry (@register decorator) + auto-imports
    message.py          # TickerMessage, TickerCountdown
    weather.py          # WeatherWidget (WeatherAPI.com) with 8x8 pixel icons
    weather_icons.py    # 7 weather condition icons
    rss_feed.py         # RSSFeedMonitor (no draw() — stories expand into TickerMessages)
    two_row.py          # TwoRowMessage: held top + scrolling bottom for tall canvases
    mlb.py              # MLBMonitor: scores, series, postponements, "Final"
    mlb_icons.py        # MLB team logos / pixel sprites
    mlb_standings.py    # MLBStandingsMonitor (top N + tracked teams, offseason detection)
    gif.py              # GifPlayer: animated GIFs at native physical resolution
    still.py            # StillImage: single PNG/JPG (mirrors GifPlayer feature surface)
    _image_base.py      # _BaseImageWidget: shared text-overlay surface + _play_with_text
    _gif_decode.py      # Pillow-based GIF decoder (animated, with frame-duration logging)
    _image_fit.py       # Canonical fit/alpha/validation primitives (pillarbox/letterbox/stretch/crop)
    crypto/
      coinbase.py       # CoinbasePriceMonitor
      coingecko.py      # CoinGeckoPriceMonitor
      etherscan.py      # EtherscanGasMonitor
```

**Inline Emoji**: Use `:name:` in TickerMessage text to render pixel art icons inline. Defined in `pixel_emoji.py`. Available: `baseball`, `taco`, `flower`, `star`, `sun`, `moon`, `cloud`, `rain`, `snow`, `thunder`, `fog`, `instagram`, `email`. Each icon is an 8×8 sprite stored as `(x, y, r, g, b)` tuples; the icon carries its own colors (text uses the surrounding `font_color`). Add a new emoji by appending pixel data + a registry entry.

**Hi-res emoji on the bigsign**: Some slugs additionally have a high-resolution variant in `HIRES_REGISTRY` (currently `:moon:` is 32×32). When rendered on a `ScaledCanvas` the hi-res sprite is painted DIRECTLY to the underlying real canvas via `_draw_hires_emoji`, bypassing the wrapper's `scale × scale` block expansion. A 32×32 sprite at scale=4 occupies the same horizontal footprint as the equivalent 8×8 low-res emoji (8 logical columns) but with 16× more detail per cell. On non-`ScaledCanvas` paths (small sign, scale=1) the renderer falls back to the 8×8 low-res sprite automatically. Hi-res sprites can be generated programmatically (see `_generate_moon_hires` for the circle-subtraction approach).

**Per-widget colors in config**: TOML configs can specify RGB lists like `font_color = [255, 150, 190]`, `color = [225, 48, 108]`, `top_color`, or `bottom_color`. The loader in `app._build_widget`/`_build_title` coerces 3-int lists/tuples in any of these keys to `graphics.Color` automatically. `color = "random"` still works for titles (cycles through `RANDOM_COLOR`).

**Two-row widget (`type = "two_row"`)**: For tall canvases (the bigsign), `TwoRowMessage` renders a held top row + a scrolling bottom row. Top stays at a fixed position (alignable left/center/right via `top_align`); the bottom scrolls when its content overflows canvas width (`bottom_align` only takes effect when it fits). Best in `swap` mode at `scale = 2` so 128 logical px is wide enough to hold typical handles. Uses FONT_SMALL (5×8). Inline emoji slugs work in both rows — `pixel_emoji.draw_with_emoji` accepts an `emoji_y` override that the widget computes per row from the canvas height.

**Per-section `content_height`**: `SectionConfig.content_height` (default 16) controls the wrapper's logical canvas height. Larger values create vertical breathing room — useful for the `two_row` widget where `content_height = 20` gives 2 rows of gap between top and bottom text bands (16 packs them tight, 24 gives 4 rows of air). The wrapper still letterboxes the bigsign symmetrically; you're trading letterbox for content area. Only applies when `scale > 1` (i.e., when the wrapper is created).

**ScaledCanvas (bigsign)**: When `default_scale > 1` in config, the canvas returned to widgets is a `ScaledCanvas` wrapper. Widgets keep drawing at logical 16-tall coordinates; the wrapper expands every `SetPixel` to a scale×scale block on the real canvas and centers the content vertically. `DrawText` cannot be scaled, so `text_render.py` provides a pure-Python BDF rasterizer (`ScaledCanvas.draw_bdf_text`) that uses `SetPixel` and therefore inherits the wrapper's scaling. `_swap` knows how to in-place swap the wrapper's `.real` canvas so the wrapper identity is stable across frames. `_y_offset` is cached at construction since real-canvas height is constant for a wrapper's lifetime.

**Native-resolution painting via `unwrap_to_real`**: Some widgets and transitions need physical pixel granularity, not the wrapper's logical-pixel-then-block-expand path — e.g. the GIF widget (each LED is a real pixel, not a 4×4 block) and the Dissolve transition (logical-grain scatter at scale=4 turns out to be a fade-through-black at t=0.5). `scaled_canvas.unwrap_to_real(canvas)` peels any ScaledCanvas wrappers and returns the underlying real canvas, leaving non-wrapped canvases untouched. Use this whenever you need physical pixels. For widgets that own their own swap loop (like GifPlayer.play()), keep an `innermost` pointer to the deepest wrapper so you can rebind `.real` to the new back-buffer after each `SwapOnVSync`.

**GIF widget (`type = "gif"`) and Still-image widget (`type = "image"`)** share a base class `_BaseImageWidget` (in `widgets/_image_base.py`) that provides the entire text-overlay surface: `text_align` (`auto` | `left` | `right` | `scroll` | `scroll_over`) + `text_valign` (`top` | `center` | `bottom`) + `text_y_offset` / `text_x_offset` for pixel nudging + `scroll_direction` + `scroll_speed_ms` + `text_scale` (block-scale glyphs via a temporary ScaledCanvas at `content_height = panel_h // text_scale` so `text_valign="top"` lands at the panel edge, not a centered band) + `text_loops` floor + inline `:slug:` emoji. Subclasses provide `_paint_full(canvas)`, `_paint_skip_black(canvas)`, `_load`, and an optional `_pick_frame_for_elapsed(elapsed_ms)` hook (gif advances `_current_frame_idx`; still leaves it as the no-op default).

  - `GifPlayer` decodes animated GIFs via Pillow and paints frames at native physical res (bypassing ScaledCanvas — see "Native-resolution painting" above). Per-visit duration is `gif_loops × sum(durations)`. Two run modes: legacy `mode = "gif"` (panel takeover, no titles) and `mode = "swap"` (unified path via `_has_play` dispatch; titles + transitions Just Work).
  - `StillImage` decodes a single PNG / JPG / single-frame GIF. Per-visit duration is `hold_seconds`. With `text_loops > 0` `hold_seconds` becomes a duration FLOOR (`max(hold_seconds, text_loops × traversal)`).

  Four shared `fit` modes (`pillarbox`, `letterbox`, `stretch`, `crop`); `image_align = "left" | "center" | "right"` anchors pillarboxed images horizontally. Transparent PNGs and palette-transparency GIFs both alpha-composite onto black during decode so skip-black scroll-text exposes the transparent regions (text walks "behind" the silhouette). Fit + alpha primitives (`apply_fit`, `flatten_onto_black`, `validate_choice`, `VALID_FITS`, `VALID_GIF_ALIGNS`) live in `widgets/_image_fit.py` — the canonical home; do not duplicate. **Static-text fast path:** when not scrolling and `text_loops == 0`, `_play_with_text` paints once and sleeps cumulative duration instead of redrawing identical frames every tick. **Footgun validation** raises (rather than silently no-op'ing) on `text_align="scroll"` + `fit="stretch"` (no transparent regions to expose text), `text_x_offset != 0` + scroll modes, and `hold_seconds < 0.05`.

**`play()`-style widgets in run_swap**: A widget can opt out of the standard hold-and-scroll path by exposing an async `play(real_canvas, frame, loop_count) -> Canvas` method. `_run_swap`'s `_show_one` helper dispatches to `_play_widget` (which unwraps the ScaledCanvas, calls `play()`, then re-anchors `.real` to the new back-buffer) when `_has_play(widget)` returns true. `_has_play` checks `inspect.iscoroutinefunction(type(widget).play)` — looking at the CLASS, not the instance — so Mock objects (which auto-generate any attribute on access) don't false-positive in tests. Currently only `GifPlayer` uses this; any future video / animation widget can follow the same pattern.

**BDF glyphs carry pre-computed `lit_pixels`**: `BDFGlyph.lit_pixels` is a flat `list[tuple[int, int]]` of `(col, row)` for set bits, computed at parse time. The bigsign rasterizer iterates this directly instead of branching every cell — most cells are unlit. `bitmap` is preserved as the source of truth; tests in `test_bdf_parser.py` assert the two stay in sync.

### Key Patterns

**Widget Protocol**: All widgets implement `draw(canvas, cursor_pos=0, **kwargs) -> (canvas, int)`. All draw() methods support `y_offset` via kwargs (default 0), used for vertical transitions. Async widgets also implement `update()` and use `run_monitor_loop()` with exponential backoff.

**Widget Registry**: `@register("name")` decorator. Config loader uses `get_widget_class(name)`.

**Transition Registry**: `@register_transition("name")` decorator in `transitions/` package. 30 transitions available.

**Presentation Registry**: `@register_presentation("name")` decorator. 5 text effects available.

### CRITICAL: Hardware Rendering Constraints

These constraints were learned through extensive real-hardware testing:

1. **SwapOnVSync return value MUST be captured**: `canvas = frame.matrix.SwapOnVSync(canvas)`. The return value is the previous front buffer which becomes the new back buffer. If discarded, you draw to the actively-displayed buffer, causing tearing and corruption. EVERY call site must capture this.

2. **DrawText rejects non-Canvas objects**: The real rgbmatrix `graphics.DrawText` is a C function that type-checks for `rgbmatrix.core.Canvas`. Python objects like ShadowCanvas will get `TypeError`. Never call `widget.draw()` on anything other than a real canvas or the test stub canvas.

3. **No GetPixel**: Cannot read pixels back from any canvas. The framebuffer stores pre-computed GPIO bitplane data, not RGB values. Reverse mapping is infeasible.

4. **SetPixel works everywhere**: `canvas.SetPixel(x, y, r, g, b)` works on real canvases, test stubs, and any object. All transition visual effects use SetPixel.

5. **Swap-then-sleep ordering**: Always `SwapOnVSync` first, then `asyncio.sleep`. Never sleep before swap — it adds frame latency.

6. **Font advance width ≠ visible glyph width**: BDF font characters have advance widths that include trailing whitespace within the character cell. When text scrolls to the right edge, the cursor reaches x=159 but the last visible pixel may be 2-3px earlier depending on the character (e.g., "!" is narrow within its cell, "M" fills it). This is standard bitmap font behavior, not a bug.

7. **Widget padding is for layout, not scroll stop**: `draw()` returns `cursor_pos` which includes `end_padding` (default 6px). This padding provides spacing between widgets in `forever_scroll` side-by-side mode — do NOT remove it from the widget. Instead, `_swap_and_scroll` ADDS padding back to stop_pos to compensate: `stop_pos = -(cursor_pos - canvas.width) + padding`. Since cursor_pos overshoots by padding, adding it scrolls less far left, putting the last character flush with the right edge.

8. **Test stubs simulate double-buffering**: The stub `SwapOnVSync` returns a DIFFERENT canvas object (not the same one) to catch code that discards the return value.

9. **ScaledCanvas wraps the real canvas**: In bigsign mode (`default_scale > 1`) the canvas widgets receive is a `ScaledCanvas`. `_swap` mutates `.real` in place so wrapper identity is preserved across frames; transitions that re-wrap (`run_transition` at `incoming_scale != current`) must do so explicitly and not rely on the wrapper survival path.

10. **`play()`-style widgets must rebind their text/secondary canvases after every swap**: A widget that owns its swap loop (e.g. `GifPlayer.play()`, `StillImage.play()`) typically holds two canvas references: one for the image (real canvas, native pixels) and one for text (a temporary ScaledCanvas wrapper or the same real canvas at scale=1). After `canvas = frame.matrix.SwapOnVSync(canvas)`, the secondary reference is now stale — pointing at the old front buffer that's currently displaying. ScaledCanvas wrappers re-anchor via `wrapper.real = canvas`; raw-canvas references must be reassigned (`text_canvas = canvas`). Skip this rebind and you paint to the displayed buffer every other tick — visible as a "pulsing" flicker on the panel. Both widgets now share `_BaseImageWidget._play_with_text` so the rebind lives in one place. Tripwires: `test_play_text_scale_1_text_canvas_follows_back_buffer` (gif) and `test_text_canvas_follows_back_buffer` (still).

11. **Per-pixel scatter (Dissolve) must run at physical resolution on ScaledCanvas**: A SetPixel-based scatter operating on the wrapper's logical canvas at scale=4 has only 1024 logical pixels — at peak (`t=0.5`, `count=total`) every logical pixel blacks out, every 4×4 block on the real canvas blacks out, and the panel goes 100% black for one frame. That's a fade-through-black, not a dissolve. Unwrap via `unwrap_to_real(canvas)` and call `real.SetPixel` so the scatter has 16× more grain (16,384 pixels on the bigsign). Tripwire: `test_scatter_uses_physical_resolution_through_scaled_canvas` in `tests/test_transitions.py`.

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
- `pacman` — Pac-Man chases 3 scared ghosts (Blinky/Pinky/Inky) left-to-right with dots; chomping mouth animation + ghost wave animation
- `pacman_reverse` — Pac-Man + ghosts right-to-left (flipped)
- `pacman_alternating` — cycles through pacman → pacman_reverse each swap
- `push_alternating` — cycles through push_left → push_right → push_up → push_down each swap
- `nyancat_alternating` — cycles through nyancat → nyancat_reverse each swap
- `wipe_alternating` — cycles through wipe_left → wipe_right → wipe_up → wipe_down each swap
- `sailor_moon` — Moon Stick wand sweeps left-to-right with sparkle trail erasing outgoing content
- `sailor_moon_reverse` — Moon Stick sweeps right-to-left (flipped sprite)
- `sailor_moon_alternating` — cycles through sailor_moon → sailor_moon_reverse each swap

**How wipe transitions work**: Draw outgoing widget at pos=0 (stationary text), then use SetPixel to black out regions and draw colored sweep lines on top. At t=1.0, snap to incoming. This avoids the compositing problem entirely — no need to draw both widgets or read pixels back. The blackouts are NOT redundant against `Clear()` — they erase parts of `outgoing.draw()`'s text bleed (DrawText cannot be clipped).

**Presenter freeze during transitions**: `run_transition` calls `pause()` on outgoing/incoming before its loop and `resume()` after (try/finally). `WidgetPresenter` exposes these methods to keep `frame_count` from advancing while the widget is being re-rendered for compositing — otherwise a Bounce/Typewriter/Rainbow-wrapped widget mid-cycles during the dissolve and re-enters the next section at a wrong phase. Plain widgets without `pause()` are skipped via duck-typing.

**Cross-scale dissolves**: `run_transition(..., incoming_scale=N)` re-wraps the canvas at the new scale at t ≥ 0.5 so the incoming widget dissolves IN at its native size instead of flashing the wrong scale. The function returns the new wrapper — callers MUST capture the return value (`canvas = await run_transition(...)`) to follow the new wrapper for subsequent renders.

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

1. Create `src/led_ticker/transitions/my_transition.py` (or add to existing file)
2. Import and use `@register_transition("name")` decorator from `led_ticker.transitions`
3. Implement `frame_at(t, canvas, outgoing, incoming)` where t is 0.0-1.0
4. At t=0: show only outgoing. At t=1.0: show only incoming.
5. Use SetPixel for visual effects (sweep lines, blackout regions) — NOT ShadowCanvas
6. Never call `widget.draw()` on anything other than the real `canvas` parameter
7. Add import to `src/led_ticker/transitions/__init__.py` (submodule import + re-export)

### Testing

580+ tests, ~95% coverage, runs in ~15s with no Docker.

- `make test` sets `PYTHONPATH=tests/stubs` automatically
- Test stubs simulate double-buffering: the real-stub `RGBMatrix.SwapOnVSync` returns a DIFFERENT canvas object each call so dropped-capture bugs surface
- Stub `DrawText` writes actual pixels for pixel-level test assertions
- Weather tests need `monkeypatch.setenv("WEATHERAPI_KEY", "test-key")`

**Tripwire fixtures in `tests/conftest.py`:**
- `mock_frame` — convenience fixture; `SwapOnVSync.return_value = canvas` (same object). Fine for tests that don't care about capture-correctness
- `swapping_frame` — rotates between two canvas mocks. Use this in regression tests for CLAUDE.md constraint #1 (capture the swap return). Drop the capture and `widget.draw` will only see one canvas — assert on `len({id(c) for c in draw_args}) >= 2`

**Common failure modes the suite now catches:**
- SwapOnVSync return dropped → `TestSwapOnVSyncCapture` (test_ticker_display.py)
- Cross-scale dissolve missing wrapper switch → `TestRunTransitionCrossScale`
- `_swap_and_scroll(skip_initial_draw=True/continuous=True)` regressions → dedicated tests
- WidgetPresenter mid-cycling during transitions → `test_pause_freezes_frame_count`
- MLB widget state-bucket fall-through → branch-specific assertions on `update()`

### Configuration

- App config: `config/config.toml` (mounted in Docker at `/code/config/`, gitignored)
- Examples: `config/config.example.toml` (small sign), `config/config.bigsign.example.toml` (Pi 5 bigsign with `pixel_mapper`, scaling, RP1 tuning), `config/config.moonbunny.example.toml` (real-world bigsign template — store-window display with brand colors and inline `:instagram:`/`:email:` emoji)
- API keys: `.env` (see `.env.example`)
- Per-section: `mode`, `transition`, `transition_duration`, `transition_color`, `hold_time`, `loop_count`
- Per-widget: `presentation`, `show_icon` (weather), `scale` (override `default_scale` per section, e.g. countdowns at 2× on the bigsign)
- Global: `[transitions] default`, `duration`, `easing`, `between_sections`
- Pi 5 only: `rp1_rio` (0=PIO, 1=RIO), `pwm_bits`, `pwm_lsb_nanoseconds`, `show_refresh`

### Docker / Deployment

- Production image: `python:3.13-bullseye` base, 3-layer caching (rgbmatrix → deps → source)
- Single image runs on both the Pi 4 sign and the Pi 5 bigsign. The rgbmatrix library is hardcoded to `jamesawesome/rpi-rgb-led-matrix` (default branch `main`) — based on kingdo9's pi5_support (upstream PR [hzeller#1886](https://github.com/hzeller/rpi-rgb-led-matrix/pull/1886), maintainer-approved) with one patch on top: 42 anonymous `PIO` parameters in `pio_rp1.c` were given a name so the file builds under bullseye GCC 10. The library detects the SoC at runtime and selects the BCM2711 GPIO backend (Pi 4) or the RP1 PIO/RIO backend (Pi 5). The pre-RP1 codebase is preserved on the `pi4_legacy` branch. Track #1886 and retire our branch once it merges into `hzeller/master`.
  - On the Pi 5, the runtime CLI also accepts `--led-rp1-rio=0|1` (PIO vs Registered IO mode). For chain ≥ 2 with flicker, raise `slowdown_gpio` from 2 to 3+.
- Config mounted read-only: `./config:/code/config:ro`
- Systemd: `deploy/led-ticker.service`

### Hardware

**Small sign (Pi 4):**
- Raspberry Pi 4 Model B, 5× chained 32×16 panels = 160×16 pixels
- `led_gpio_mapping`: "adafruit-hat"
- `led_slowdown_gpio`: 2
- `led_brightness`: 60
- `default_scale`: 1 (no scaling)
- ~20fps (0.05s per frame)

**Bigsign (Pi 5):**
- Raspberry Pi 5, 8× P3 32×64 panels in a 2×4 vertical-serpentine layout = 256×64 pixels
- `led_gpio_mapping`: "adafruit-hat"
- `led_slowdown_gpio`: 3 (paired with `rp1_rio=1`; raise to 4–5 if flicker)
- `pwm_bits`: 8 (down from default 11 for ~8× faster refresh; minor color hit)
- `rp1_rio`: 1 (RIO mode — faster, more CPU; `0` = PIO mode, lower CPU)
- `default_scale`: 4 (drawing logic is 16-tall and `ScaledCanvas` blows it up to 64-tall)
- Custom `pixel_mapper` Remap string for serpentine panel layout (see `config.bigsign.example.toml`)

**Both:**
- DrawText clips safely at canvas edges (y can be negative or > height)
- Same Docker image, same `compose.yaml` — the rgbmatrix library detects the SoC at runtime

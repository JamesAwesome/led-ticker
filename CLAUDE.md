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

**Hi-res transitions on the bigsign**: The `nyancat`, `pokeball`, and `baseball` transition families have hi-res variants that auto-activate when `frame_at` receives a `ScaledCanvas` (i.e. the bigsign at scale=4). Dispatch lives in each transition's `frame_at` (`isinstance(canvas, ScaledCanvas)` + `_registry_name in HIRES_REGISTRY`) and routes to `_frame_at_hires` or `_frame_at_lowres`. Sprites are bundled at `src/led_ticker/transitions/sprites/` (`nyancat.webp`, `pikachu-run-transparent.gif`); baseball renders procedurally from the existing `:baseball:` hi-res emoji geometry, rotated through 8 frames at 45° via PIL. The shared loader (`_hires_loader.py`) decodes via Pillow once, caches via `@functools.cache load_hires`, and paints to `unwrap_to_real(canvas)` so each pixel is a real LED, not a 4×4 logical block. The `HiresSpec.trail` field selects what fills behind the leading entity to erase outgoing text: `"none"`, `"black"` (pokeball), or `"rainbow"` (nyancat). Trail saturates at `TRAIL_SATURATION_T=0.85` (full panel covered), holds, then snaps to incoming at `SNAP_THRESHOLD=0.95` — matches the lowres "fill, hold, cut" feel. `sailor_moon` and `pacman` intentionally have no hi-res variant (8-bit aesthetic IS the design / no asset staged). `run_transition` passes `duration_ms` to `frame_at` so the hi-res path can pick a sprite frame from wall-clock elapsed time. Dispatch boilerplate is intentionally duplicated across `nyancat.py`/`pokeball.py`/`baseball.py`; if you find yourself adding a 4th family, refactor to a mixin first.

**Hi-res fonts on the bigsign**: Widgets can opt into TTF/OTF rendering at native physical resolution by setting `font = "<name>"` and `font_size = <pixels>` in their TOML config. The loader (`fonts/hires_loader.py`) scans `config/fonts/` first (user-supplied, gitignored — for licensed fonts like Adobe's Beloved Sans), then `src/led_ticker/fonts/hires/` (bundled — currently `Inter-Regular`, `Inter-Bold`), then falls back to BDF aliases (`6x12`, `5x8`, etc.). The user-supplied dir is re-anchored at startup to `<config.toml dir>/fonts/` (via `app._configure_user_font_dir`) so the same install works in dev and Docker. Glyphs are rasterized via Pillow once per (font, size, threshold) tuple, thresholded at 50% intensity by default for a clean pixel-art look (no anti-aliasing fuzz on the LED panel), and cached via `@functools.cache load_hires_font`. The render path (`text_render._draw_hires_text`) paints lit pixels directly to `unwrap_to_real(canvas).SetPixel`, bypassing the wrapper's 4×4 block expansion. `(x, y)` widget coords are still LOGICAL — the renderer multiplies by `canvas.scale` internally. Existing `get_text_width` and `pixel_emoji.draw_with_emoji` are polymorphic on font type via `isinstance(font, HiresFont)`. `font_line_height(font)` is the shared helper for vertical alignment math (replaces the hardcoded BDF cell height of 12). Widgets without `font`/`font_size` in TOML keep their class default (BDF). Hi-res rendering on the small sign is allowed but text overflows vertically — user's responsibility to pick `font_size` ≤ panel height.

**Per-widget `font_threshold`**: TOML can include `font_threshold = <0..255>` next to `font` / `font_size` to override the rasterization cutoff for that widget only. Default 128 (50% intensity) gives clean output for medium-stroke fonts like Inter. Thin-stroked fonts (Beloved Sans Regular at 24-32px) need ~80 — at the 128 default the antialiased pixels of thin strokes (left vertical of `n`/`u`) come out around 60-100 grey and get quantized to zero, leaving glyphs visibly broken. The threshold is part of the loader's cache key so different widgets at the same name+size but different thresholds don't collide. BDF aliases ignore threshold (pre-rasterized bitmaps). Type-validated: only `int` 0-255 accepted (rejects str, float, bool — bool is excluded explicitly since it's an int subclass).

**Match thresholds within a font family**: Bold weights render fine at the default 128 in isolation, but mixing thresholds inside one family inverts the weight relationship. Concretely: Beloved Sans Regular at thr=80 has 61 lit pixels per `n`; Bold at thr=128 has 54. Lowering the threshold on Regular fattens it past Bold's natural weight, so on the panel Bold no longer looks bolder. Pair Bold to the same `font_threshold` as Regular (e.g. both at 80) so the weight contrast survives. This is a hardware-validated finding from on-Pi testing — the in-tree `test_bold_renders_stroke_complete_at_default_threshold` only proves Bold is stroke-complete at 128, NOT that mixing thresholds preserves weight ordering.

**Marquee auto-floor on image/gif widgets** (`_image_base._play_with_text`): when `text_align ∈ ("scroll", "scroll_over")`, the per-tick loop runs at LEAST one full traversal (`text_w + text_width` ticks at `scroll_speed_ms` cadence) regardless of the source's natural duration (`gif_loops × loop_ms` for gifs, `hold_seconds` for stills). Without this, hires-wide marquees got cut off mid-pass on the panel — a hardware-observed bug since hires fonts are 2-3× wider per char than BDF. `text_loops > 0` raises the floor further; the implicit minimum is now 1 (was: 0, no floor). The source duration extends transparently to match — your gif keeps looping until the marquee finishes its pass.

**Pillow anchor gotcha** (`hires_loader._rasterize_glyph`): `pil_font.getbbox(ch)` returns coords in anchor `"la"` (left-ascender) space, NOT baseline-relative. Rasterizer renders at `(0, 0)` (which puts the ascender line at y=0 and baseline at y=ascent), then computes `bearing_y = ascent - bbox[1]` to convert to baseline-relative for the renderer. If Pillow ever changes its default anchor, this formula needs revisiting. **Width tracking** (`drawing.get_text_width`): hi-res glyph advances are real pixels; for layout against logical canvas widths the function ceil-divides by the canvas scale. Pass `canvas=` to any draw-time call site to read scale from the canvas (`getattr(canvas, "scale", 1)`); call sites that compute widths before any canvas exists (e.g. `TickerMessage.__init__`) get `SCALE_FALLBACK = 4` — a bigsign-only assumption preserved for back-compat. Audit no-canvas call sites if hi-res use spreads beyond the bigsign at scale=4, since they'll under-report widths on a small sign. **Cache-key gotcha** (`hires_loader.load_hires_font`): `@functools.cache`'d on `(name, size, threshold)`; lookups with `threshold=80.0` (float) hash distinctly from `threshold=80` (int) and would double-rasterize the same glyphs. `resolve_font` validates type explicitly to prevent this — any new caller adding parameters must do the same. **Baseline math is font-aware** (`drawing.compute_baseline`): the centered baseline is computed from `font_line_height(font)` and `font_ascent(font)` — NOT a hardcoded `y=12`. For BDF on a 16-row logical canvas it returns 12 (back-compat), for hires Inter @ 24px on a 64-row real panel it returns 10 (the difference centers the larger font on the taller panel). All draw-time callers (`TickerMessage.draw`, `_BaseImageWidget._baseline_y`) go through this; never hardcode a baseline.

**Per-widget colors in config**: TOML configs can specify RGB lists like `font_color = [255, 150, 190]`, `color = [225, 48, 108]`, `top_color`, or `bottom_color`. The loader in `app._build_widget`/`_build_title` coerces 3-int lists/tuples in any of these keys to `graphics.Color` automatically. `color = "random"` still works for titles (cycles through `RANDOM_COLOR`).

**Two-row widget (`type = "two_row"`)**: For tall canvases (the bigsign), `TwoRowMessage` renders a held top row + a scrolling bottom row. Top stays at a fixed position (alignable left/center/right via `top_align`); the bottom scrolls when its content overflows canvas width (`bottom_align` only takes effect when it fits). Both alignments default to `"center"`. Best in `swap` mode at `scale = 2` so 128 logical px is wide enough to hold typical handles. Default font is FONT_SMALL (5×8); supports any font (BDF or HiresFont) via the `font` kwarg — row baselines are computed by `_row_layout` calling `compute_baseline` against a half-canvas, so the same code path works for both. **Per-row font overrides**: `top_font` / `bottom_font` (with their own `_size` and `_threshold` knobs) override `font` for that row only — useful for "@MoonBunny" in Inter-Bold on top + a thinner Inter-Regular promo line below. **Asymmetric row split**: `top_row_height = N` (logical rows) gives the top band exactly N rows and the bottom `canvas.height - N` rows; default `None` is the legacy 50/50. Use it to fit a larger font in the bottom row when both rows can't share size — e.g. `top_row_height = 4` with FONT_SMALL on top + Beloved Sans Bold @ 22 on the bottom. **Per-row text/emoji nudges**: `top_text_y_offset` / `bottom_text_y_offset` and `top_emoji_y_offset` / `bottom_emoji_y_offset` (logical rows; default 0). Negative shifts up, positive down. Set text + emoji to the same value to shift the entire row together; set them differently to tune emoji-text vertical alignment when the emoji sprite is taller than its row band (e.g. `top_emoji_y_offset = 1` to nudge an 8-tall emoji down 4 real px in a small top band so it visually centers with the text). **Naming convention**: single-region widgets (gif/image's text overlay, TickerMessage) use unprefixed names like `text_y_offset`; multi-region widgets (TwoRowMessage's two bands) prefix with `top_` / `bottom_`. Don't add `top_` to a single-region widget — the prefix lies about what's there. Don't drop the prefix on a multi-region widget — there's no way to address a specific region without it. Defaults to `None`, falls back to `font`. Inline emoji slugs work in both rows — `pixel_emoji.draw_with_emoji` accepts an `emoji_y` override that the widget computes per row from the canvas height; emoji size capped at `_EMOJI_ROW_CAP = 8` so a hi-res sprite that would overflow the row falls back to low-res. Hi-res text fonts that don't fit the per-row band (font line-height > canvas.height // 2) raise at draw time with a clear message identifying which row.

**Per-section `content_height`**: `SectionConfig.content_height` (default 16) controls the wrapper's logical canvas height. **Hard ceiling: `content_height * scale ≤ panel_h_real`** — for bigsign at scale=4, that's `content_height ≤ 16`. Above the ceiling the wrapper's `_y_offset` goes negative (the logical canvas is taller than the panel), top + bottom rows of the logical canvas overflow the visible area, and content placed near those edges silently clips. The "breathing room" framing in older configs (`content_height = 20`) is a footgun on bigsign — BDF text was tolerant because cells stayed near the vertical center, but hi-res emoji and large hi-res fonts surface the clip immediately (e.g. TwoRow's hi-res `:instagram:` cuts off ~4 real px at the bottom). Only applies when `scale > 1` (i.e., when the wrapper is created). For per-row breathing room, use `text_y_offset` on TickerMessage or pick a smaller `font_size` rather than over-spec'ing `content_height`.

**ScaledCanvas (bigsign)**: When `default_scale > 1` in config, the canvas returned to widgets is a `ScaledCanvas` wrapper. Widgets keep drawing at logical 16-tall coordinates; the wrapper expands every `SetPixel` to a scale×scale block on the real canvas and centers the content vertically. `DrawText` cannot be scaled, so `text_render.py` provides a pure-Python BDF rasterizer (`ScaledCanvas.draw_bdf_text`) that uses `SetPixel` and therefore inherits the wrapper's scaling. `_swap` knows how to in-place swap the wrapper's `.real` canvas so the wrapper identity is stable across frames. `_y_offset` is cached at construction since real-canvas height is constant for a wrapper's lifetime.

**Native-resolution painting via `unwrap_to_real`**: Some widgets and transitions need physical pixel granularity, not the wrapper's logical-pixel-then-block-expand path — e.g. the GIF widget (each LED is a real pixel, not a 4×4 block) and the Dissolve transition (logical-grain scatter at scale=4 turns out to be a fade-through-black at t=0.5). `scaled_canvas.unwrap_to_real(canvas)` peels any ScaledCanvas wrappers and returns the underlying real canvas, leaving non-wrapped canvases untouched. Use this whenever you need physical pixels. For widgets that own their own swap loop (like GifPlayer.play()), keep an `innermost` pointer to the deepest wrapper so you can rebind `.real` to the new back-buffer after each `SwapOnVSync`.

**GIF widget (`type = "gif"`) and Still-image widget (`type = "image"`)** share a base class `_BaseImageWidget` (in `widgets/_image_base.py`) that provides the entire text-overlay surface: `text_align` (`auto` | `left` | `right` | `scroll` | `scroll_over`) + `text_valign` (`top` | `center` | `bottom`) + `text_y_offset` / `text_x_offset` for pixel nudging + `scroll_direction` + `scroll_speed_ms` + `text_scale` (block-scale glyphs via a temporary ScaledCanvas at `content_height = panel_h // text_scale` so `text_valign="top"` lands at the panel edge, not a centered band) + `text_loops` floor + inline `:slug:` emoji. Subclasses provide `_paint_full(canvas)`, `_paint_skip_black(canvas)`, `_load`, plus optional hooks `_pick_frame_for_elapsed(elapsed_ms)` (advance per-frame state — default no-op for stills, gif overrides) and `_is_static() -> bool` (drives the static-text fast path — defaults `True` for stills, gif returns `len(self._frames) <= 1`).

**Two-row text overlay on image widgets**: Setting `bottom_text != ""` on a gif/image widget switches it to held-top + scroll-on-overflow-bottom semantics — the image painted underneath, two text rows over it. Mirrors `TwoRowMessage`'s contract; per-row knobs parallel TwoRow's: `top_text` (back-compat alias: `text` works as top text when only `bottom_text` is added), `top_color` / `bottom_color` (default to `font_color`), `top_align` / `bottom_align` (default `"center"`), `top_font` / `bottom_font` (with `_size` and `_threshold`; default to `font`), `top_text_y_offset` / `bottom_text_y_offset`, `top_emoji_y_offset` / `bottom_emoji_y_offset`, `top_row_height` (asymmetric split). Layout helpers in `widgets/_row_layout.py` (`row_layout`, `aligned_x`, `resolve_band_heights`) are shared with `TwoRowMessage` so the two widgets can't drift in row positioning. Single-row `text_align` / `text_valign` / `text_x_offset` / `text_scale` are refused in two-row mode (use the per-row knobs); `bg_color` keeps its whole-canvas / letterbox-fill semantics — no per-row band-bg knobs (image painted underneath replaces that role). **Architecture**: `_play_with_two_row_text` paints the image to the unwrapped real canvas (native pixels) but wraps the same canvas in a `ScaledCanvas` for text+emoji draw. All band-height / baseline / aligned_x math operates in LOGICAL units against the wrapper — same coordinate system as TwoRowMessage, so `top_row_height = 5` reads identically on both widgets. The wrap is also why hires emoji (`:instagram:` 32×32) fires correctly: `pixel_emoji.draw_with_emoji`'s `isinstance(canvas, ScaledCanvas)` gate sees the wrapper. BDF text on bigsign also gets the wrapper's `scale × scale` block-expansion automatically. The wrapper's `.real` is rebound after each `SwapOnVSync` (CLAUDE.md constraint #10) so successive ticks paint to the correct back-buffer. Scale propagation: `ticker._play_widget` stashes `wrapper.scale` on `widget._logical_scale` BEFORE unwrapping (since `play()` receives the raw real canvas) — that's how the widget knows what scale to use for the wrap. Tripwires: `test_play_widget_stashes_logical_scale_on_widget` (ticker side), `TestTwoRowLogicalUnits` (widget side, three tests covering logical-rows interpretation, band-fit rejection, and that the text canvas is a ScaledCanvas wrapper so hires emoji fires). Field-surface tripwire (`tests/test_widgets/test_image_base.py:TestFieldSurfaceMatchesTwoRow`) catches drift between the two widgets' per-row field sets at the test layer.

**Single-row image text on bigsign — wrap fires on `_logical_scale`**: `_play_with_text` computes `effective_scale = max(text_scale, _logical_scale)` and wraps when > 1. Three motivating cases this fixes: (1) HiresFont + `text_scale=1` on bigsign now gets hires emoji because `pixel_emoji.draw_with_emoji`'s `isinstance(c, ScaledCanvas)` gate fires. (2) BDF text + `text_scale=1` on bigsign now block-expands to fill the panel instead of rendering at native 12 px (was effectively unreadable; nobody had a working such config). (3) `text_y_offset` is documented as logical pixels and now actually operates on logical pixels everywhere — previously real px when `text_scale=1`. User intent on `text_scale > 1` is honored as-is (so `text_scale=2` on bigsign still gives 2× block-expansion, not 4×). Tripwires: `TestSingleRowLogicalScaleWrap` (3 tests covering bigsign-wraps, smallsign-no-wrap, user-text-scale-honored).

  - `GifPlayer` decodes animated sources via Pillow and paints frames at native physical res (bypassing ScaledCanvas — see "Native-resolution painting" above). Format-agnostic despite the name: anything Pillow opens with `n_frames` and `seek()` works (gif, animated webp, apng, multi-frame tiff). Per-frame durations come from `img.info["duration"]`. Per-visit duration is `gif_loops × sum(durations)`. Two run modes: legacy `mode = "gif"` (panel takeover, no titles) and `mode = "swap"` (unified path via `_has_play` dispatch; titles + transitions Just Work).
  - `StillImage` decodes a single PNG / JPG / single-frame GIF. Per-visit duration is `hold_seconds`. With `text_loops > 0` `hold_seconds` becomes a duration FLOOR (`max(hold_seconds, text_loops × traversal)`).

  Four shared `fit` modes (`pillarbox`, `letterbox`, `stretch`, `crop`); `image_align = "left" | "center" | "right"` anchors pillarboxed images horizontally. Transparent PNGs and palette-transparency GIFs both alpha-composite onto black during decode so skip-black scroll-text exposes the transparent regions (text walks "behind" the silhouette). Fit + alpha primitives (`apply_fit`, `flatten_onto_black`, `validate_choice`, `VALID_FITS`, `VALID_IMAGE_ALIGNS`) live in `widgets/_image_fit.py` — the canonical home; do not duplicate. **Static-text fast path:** when `_is_static()` AND `text_align ∈ (left, right)` AND `text_loops == 0`, `_play_with_text` paints once and sleeps cumulative duration instead of redrawing identical frames every tick. The `_is_static()` gate is critical: a multi-frame gif must NOT fast-path (frames would freeze on idx 0 — tripwire `test_gif_static_text_does_not_freeze_animation`). **Footgun validation** raises on `text_align="scroll"` + `fit="stretch"` (no transparent regions to expose text), `text_x_offset != 0` + scroll modes, `hold_seconds < 0.05`, and (at first paint) `panel_h // text_scale < 12` (BDF cell wouldn't fit).

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
- `nyancat` — Nyan Cat flies left-to-right, rainbow fills screen before cut (hi-res variant on bigsign — animated webp Nyan Cat)
- `scroll` — seamless continuous scroll with bullet dot separator (2x2 SetPixel, 6px symmetric gaps). Uses `_scroll_between` at 1px/frame for constant speed. Note: `forever_scroll` mode uses a text `•` character via `DEFAULT_BUFFER_MSG` with cursor-based spacing — visually similar but different rendering approach.
- `nyancat_reverse` — Nyan Cat flies right-to-left (flipped sprite), rainbow fills screen (hi-res variant on bigsign — animated webp Nyan Cat)
- `pokeball` — Pokeball rolls left-to-right with Pikachu chasing; 4-frame rotation, 4-frame Pikachu run cycle (hi-res variant — procedural ball + animated Pikachu sprite; show_pikachu / show_pokeball toggles)
- `pokeball_reverse` — Pokeball + Pikachu right-to-left (flipped sprites) (hi-res variant — procedural ball + animated Pikachu sprite; show_pikachu / show_pokeball toggles)
- `pokeball_alternating` — cycles through pokeball → pokeball_reverse each swap
- `baseball` — white baseball with red stitching rolls left-to-right; 4-frame stitch rotation (hi-res variant — procedural ball reusing :baseball: emoji geometry, 8 rotation frames)
- `baseball_reverse` — baseball right-to-left (flipped) (hi-res variant — procedural ball reusing :baseball: emoji geometry, 8 rotation frames)
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

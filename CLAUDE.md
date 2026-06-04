# CLAUDE.md

Guidance for Claude Code when working in this repository.

User-facing prose for every feature mentioned in this file lives on the docs site at <https://docs.ledticker.dev>. This file keeps only the **load-bearing invariants** the assistant must respect when generating or modifying code, plus navigation aids (commands, file map, contributor flows). When this file links to a docs page, the link is the source of truth for "how the feature works"; the surrounding paragraph here is the source of truth for "how to keep it working."

## Project Overview

**led-ticker** is an asyncio Python toolkit that drives RGB LED matrix panels from a Raspberry Pi via a TOML config. Two reference builds share one codebase and one Docker image (the rgbmatrix library detects the SoC at runtime):

- **Smallsign** — Pi 4 + 5× chained 16×32 panels = 160×16 logical canvas, `default_scale = 1`
- **Bigsign** — Pi 5 + 8× P3 32×64 panels in a 2×4 vertical-serpentine layout = 256×64, `default_scale = 4`. Drawing logic stays at 16-tall logical content; `ScaledCanvas` expands every `SetPixel` to a `scale × scale` block on the real canvas and centers vertically.

Hardware reference details: <https://docs.ledticker.dev/hardware/smallsign/> · <https://docs.ledticker.dev/hardware/bigsign/> · <https://docs.ledticker.dev/hardware/building-your-own/>

## Commands

```bash
make dev           # uv sync (install all deps)
make test          # pytest with coverage (no Docker, no hardware)
make lint          # ruff
make format        # ruff format
make validate      # led-ticker validate CONFIG=path.toml (config preflight); supports --list-fields <type> (e.g. --list-fields message) to print a widget's recognized TOML fields
make render-emoji-previews  # re-generate emoji preview PNGs after adding new slugs
make clean         # remove build artifacts
make build-docker  # production image (single image, both Pis)
```

Full CLI + Make-target reference: <https://docs.ledticker.dev/reference/cli/>

## Architecture

### Package Layout

```
src/led_ticker/
  __init__.py          # Package root
  _compat.py           # Lazy rgbmatrix import shim (real lib or stub)
  _types.py            # Canvas type alias used across the package
  app/
    cli.py             # CLI entry point (led-ticker --config config.toml)
    run.py             # Main async display loop
    factories.py       # Widget/transition/frame factories; validate_widget_cfg (public validation API)
    coercion.py        # Raw TOML value coercion helpers
  app.py               # Thin shim — re-exports app/ entry points
  config.py            # TOML config loader (stdlib tomllib)
  ticker.py            # Display orchestrator (scroll/swap/forever_scroll modes)
  frame.py             # LedFrame hardware wrapper
  scaled_canvas.py     # ScaledCanvas wrapper + unwrap_to_real
  text_render.py       # Pure-Python BDF rasterizer (needed when scale > 1
                       #   because graphics.DrawText cannot scale)
  validate.py          # Static config validator (`led-ticker validate`)
  widget.py            # Widget/AsyncWidget protocols + run_monitor_loop()
  drawing.py           # Shared drawing helpers (get_text_width, compute_baseline)
  colors.py            # RGB color constants
  color_providers.py   # ColorProvider base + Rainbow, ColorCycle, Gradient, Shimmer, _ConstantColor
  animations.py        # Animation protocol + Typewriter
  borders.py           # BorderEffect protocol + RainbowChaseBorder, ConstantBorder
  pixel_emoji.py       # Inline pixel-art emoji renderer + EMOJI_REGISTRY / HIRES_REGISTRY
  fonts/               # BDF + hires TTF loader
  transitions/
    __init__.py         # Registry, easing, run_transition()
    push.py             # PushLeft/Right/Up/Down, PushAlternating, PushRandom
    wipe.py             # WipeLeft/Right/Up/Down, WipeAlternating, WipeRandom
    effects.py          # Cut, ColorFlash, Dissolve, SplitHorizontal, Scroll
    nyancat.py / pokeball.py / baseball.py / pacman.py / sailor_moon.py
    _hires_loader.py    # Hires sprite cache + render_hires_frame
  widgets/
    __init__.py         # Registry (@register decorator) + auto-imports
    message.py          # TickerMessage, TickerCountdown
    weather.py / weather_icons.py
    rss_feed.py         # RSSFeedMonitor (no draw() — stories expand into TickerMessages)
    two_row.py          # TwoRowMessage: held top + scrolling bottom
    mlb.py              # Team logos render through pixel_emoji's standard 8x8 path
                        #   (the previous mlb_icons.py was folded in and deleted).
                        #   layout = "ticker" | "scoreboard" | "two_row"; two_row uses
                        #   MLBTwoRowMessage (custom draw, two-band, multi-color segments).
    mlb_standings.py
    gif.py / still.py   # GifPlayer / StillImage; share _BaseImageWidget
    _frame_aware.py     # _FrameAware mixin: frame_count + pause_frame/resume_frame
    _row_layout.py      # row_layout, aligned_x, resolve_band_heights
    _image_base.py      # _BaseImageWidget: text-overlay surface + _play_with_text
    _gif_decode.py      # Pillow-based GIF decoder
    _image_fit.py       # Canonical fit/alpha/validation primitives
    crypto/             # coinbase, coingecko, etherscan
```

### Load-bearing invariants by subsystem

Each bullet is a rule that must hold when modifying the named area. Full prose for the user-facing knobs lives on the linked docs page.

**Inline emoji** (`pixel_emoji.py`) — `EMOJI_REGISTRY` is the source of truth; never inline a static slug list (it rots). Widgets that draw a single icon at a known (x, y) call `pixel_emoji.draw_emoji_at(canvas, slug, x, y)` rather than blitting; for layout math BEFORE the draw call `pixel_emoji.measure_emoji_at(canvas, slug)` so the gate matches `draw_emoji_at` exactly. Hires-only slugs (in `HIRES_REGISTRY` but not `EMOJI_REGISTRY`) have no low-res fallback — confirm `scale > 1` before using. Inline hi-res emoji bottom-anchor to the text baseline in REAL pixels (`baseline*scale + y_offset_real - physical_size`), exact at any scale — not the old `y - 8` 8-logical-row assumption (which only held at scale=4). Low-res 8×8 emoji anchor at logical `baseline - 8`. Both `draw_with_emoji` (default path) and `draw_emoji_at` (via its `bottom_baseline=` kwarg) bottom-anchor; explicit-position callers (single-icon `top_logical`, two-row band layout) keep a top-anchor. Docs: <https://docs.ledticker.dev/assets/emoji/>.

**Hi-res emoji on the bigsign** — Hires sprites paint DIRECTLY to the underlying real canvas (bypass the wrapper's block expansion). Routing happens via `isinstance(canvas, ScaledCanvas)` inside the helpers above; on smallsign / scale=1, the renderer falls back to the 8×8 sprite automatically. Hires sprites can be generated programmatically (`_generate_moon_hires` is the circle-subtraction template).

**Hi-res transitions** — `nyancat`, `pokeball`, `baseball` families have hires variants that auto-activate when `frame_at` receives a `ScaledCanvas`. Sprites bundled at `src/led_ticker/transitions/sprites/`. Shared loader is `_hires_loader.py` (`@functools.cache`'d, paints to `unwrap_to_real(canvas)`). `HiresSpec.trail` selects what fills behind the leading entity (`"none"` / `"black"` / `"rainbow"`); trail saturates at `TRAIL_SATURATION_T=0.85`, snaps to incoming at `SNAP_THRESHOLD=0.95`. `sailor_moon` and `pacman` intentionally have no hires variant. Dispatch boilerplate is duplicated across the three hires families on purpose — refactor to a mixin only if a 4th family appears.

**Hi-res fonts** — Loader scan order: `config/fonts/` (user-supplied; gitignored, re-anchored at startup to `<config.toml dir>/fonts/` via `app._configure_user_font_dir`), then `src/led_ticker/fonts/hires/` (bundled), then BDF aliases. Glyphs cached via `@functools.cache load_hires_font` keyed on `(name, size, threshold)` — `resolve_font` validates threshold type explicitly so `80.0` (float) and `80` (int) cache distinctly. Render path (`text_render._draw_hires_text`) paints to `unwrap_to_real(canvas).SetPixel` and multiplies logical coords by `canvas.scale` internally. `font_line_height(font)` and `compute_baseline(font, ...)` (in `drawing.py`) are font-aware — never hardcode a baseline or cell height. Docs: <https://docs.ledticker.dev/concepts/fonts/>.

**Pillow anchor gotcha** (`hires_loader._rasterize_glyph`) — `pil_font.getbbox(ch)` returns coords in anchor `"la"` (left-ascender) space, NOT baseline-relative. Rasterizer renders at `(0, 0)` and computes `bearing_y = ascent - bbox[1]` to convert. If Pillow ever changes its default anchor, revisit this formula. **Width tracking** (`drawing.get_text_width`): hires advances are real pixels; for layout against logical widths the function ceil-divides by `getattr(canvas, "scale", 1)`. Pre-canvas call sites get `SCALE_FALLBACK = 4` (a bigsign-only assumption preserved for back-compat) — audit those if hires usage spreads beyond bigsign.

**`font_threshold`** — Per-widget int 0-255, default 128 (50% intensity). Thin-stroked fonts need ~80; bool excluded explicitly (it's an int subclass). Mixing thresholds within a family inverts weight ordering — pair Bold to the same threshold as Regular.

**Marquee auto-floor on image/gif widgets** (`_image_base._play_with_text`) — when `text_align ∈ ("scroll", "scroll_over")`, the per-tick loop runs at LEAST one full traversal regardless of the source's natural duration. `text_loops > 0` raises the floor further; the implicit minimum is 1 (was 0). Source duration extends transparently to match.

**Per-widget colors in TOML** — The loader auto-coerces 3-int lists in `font_color`, `color`, `top_color`, `bottom_color` to `graphics.Color`. `color = "random"` works for titles (cycles through `RANDOM_COLOR`).

**Two-row widget** — `TwoRowMessage` renders held top + scrolling-on-overflow bottom. Bottom only scrolls when content exceeds canvas width. Per-row knobs use the `top_` / `bottom_` prefix convention; single-region widgets (TickerMessage, image text overlay) use unprefixed names. Don't mix conventions: the prefix on a single-region widget lies; dropping the prefix on a multi-region widget is unaddressable. Hires text fonts that don't fit a per-row band (font line-height > canvas.height // 2) raise at draw time identifying the row. Layout helpers in `widgets/_row_layout.py` are shared with image widgets — both must keep using them so row positioning can't drift. **Per-row emoji cap** scales with band height: `max(EMOJI_ROW_CAP, band_h)`. Default `content_height = 16` with 50/50 split gives band = 8 = cap (back-compat); bumping `content_height` or `top_row_height` raises the cap so a hi-res sprite that fits the band visually renders at hi-res instead of falling back to the 8×8 lo-res variant. Tripwire: `test_emoji_cap_scales_with_band_height` in `tests/test_widgets/test_image_base.py`. `row_layout` accepts `sprite_logical_height` (defaults to `EMOJI_ROW_CAP = 8`); widget callers pass their per-row cap so the actual sprite is centered within the band rather than always centering an 8-row sub-band. Tripwire: `test_hires_sprite_anchors_within_full_band` in `tests/test_widgets/test_two_row.py` (and the mirrored test in `test_image_base.py`). Docs: <https://docs.ledticker.dev/widgets/two_row/>.

**Container widgets** (`Container` Protocol in `widget.py`) — Widgets whose `feed_stories: list[Widget]` is rebuilt by a background `update()` task are first-class to the engine. `app/run.py` pushes them into `Ticker.monitors` AS THEMSELVES (not pre-expanded); `_build_ticker_iter` re-reads `feed_stories` via `_expand_sources` on every pass through the section, so live updates surface within at most one cycle. NEVER use `itertools.cycle(snapshot)` or `widgets.extend(container.feed_stories)` at section build — that was the longboi stale-display bug (2026-05-28): containers updated correctly in the background but the cycle iterator yielded the original snapshot forever, freezing the panel on whatever state was current when the container booted. Each `update()` emits one INFO log per call ("MLB NYM updated: 5 stories (live: 1)") so a silent log stream after startup is a diagnostic signal that the background task died. The engine emits a DEBUG log per pass ("section cycle N: M sources → K widgets") so users debugging "is the engine re-reading?" can flip to DEBUG. Tripwires: `tests/test_container_refresh.py` (behavioral: mutate `feed_stories`, verify next pull yields new content; AST: assert `app/run.py` never re-introduces `widgets.extend(.feed_stories)`).

**Pool widget** — pool is no longer a core widget; it's the external [`led-ticker-pool`](https://github.com/JamesAwesome/led-ticker-pool) plugin (`pool.monitor`), extracted in PR #151. Its layout (`ticker`/`two_row`) and option docs live in that repo's README; the plugin contract is in the **Plugin invariants** section below and `docs/plugin-system.md`. Core no longer carries pool code, tests, or `_DISPATCH_APPLICABLE_TYPES` entries.

**Overlay hooks** (`frame.py`) — `LedFrame.overlay_hooks: list[Callable[[Canvas], None]]` run inside `swap()` on the real canvas before every `SwapOnVSync`, so an overlay composites over every render path (engine, transitions, play-widgets) with no per-call-site change. `LedFrame` stays mechanism-only. The list is append-only, painted in registration order — intentionally no removal, naming, enable/disable, or z-order beyond list order (YAGNI for the single current consumer; promote to a named-handle registry when a second/removable overlay appears). A hook MUST be paint-only and not raise — an exception propagates out of `swap()` and skips the hardware swap (panel freezes, constraint #1); inputs that reach a hook (e.g. `[busy_light]` color/corner/size) are validated at config-load so a hook isn't handed bad data. First consumer: `busy_light.BusyLight` (file-driven corner dot via `[busy_light]` config); real calendar/Slack sources are a future swap-in behind the same hook. Docs: <https://docs.ledticker.dev/concepts/busy-light/>. The busy source is selectable via `[busy_light]` `source = "file"` (poll, default) or `"http"` (push). The HTTP listener (`busy_http.serve_busy`, an `aiohttp.web` app — aiohttp is already a client-side dep) runs as a **supervised** task: a bind failure or crash logs and the display loop keeps running (a busy port must never freeze the panel). Optional `ttl_seconds` auto-clears pushed busy state via a 1 Hz ticker calling `BusyLight.tick_ttl()` — expiry lives in the ticker, never in `paint()`, so `paint()` stays paint-only.

**Per-section `content_height`** — Hard ceiling: `content_height × scale ≤ panel_h_real`. For bigsign at scale=4, that's `content_height ≤ 16`. Above the ceiling the wrapper's `y_offset_real` goes negative and content silently clips. BDF text is forgiving (cells sit near the vertical center) but hires emoji and large hires fonts surface the clip immediately. For per-row breathing room, use `text_y_offset` on the widget — not a higher `content_height`.

**ScaledCanvas / unwrap_to_real** — When `default_scale > 1` widgets receive a `ScaledCanvas` wrapper. `_swap` mutates `.real` in place so wrapper identity is stable across frames. `y_offset_real` is cached at construction. `DrawText` cannot be scaled, so use `ScaledCanvas.draw_bdf_text` (uses `SetPixel`, inherits scaling). For hi-res paint sites (writing individual physical LEDs), use `scaled_canvas.paint_hires(canvas, callback)` — it unwraps the real canvas and forwards `scale` and `y_offset_real` to the callback so each paint site only contains the draw logic. Use `scaled_canvas.unwrap_to_real(canvas)` directly only when you need the raw canvas without the scale/offset context (e.g. Dissolve scatter). After `widget.play()` returns a new back-buffer, call `canvas.rebind_innermost(new_real)` to rewire the wrapper chain instead of walking it manually.

**GIF / Still image widgets** — Both extend `_BaseImageWidget` (`widgets/_image_base.py`) which provides the entire text-overlay surface: `text_align`, `text_valign`, `text_y_offset`, `text_x_offset`, `scroll_direction`, `scroll_speed_ms`, `font_size`, `text_loops`, inline `:slug:` emoji. Subclasses provide `_paint_full(canvas)`, `_paint_skip_black(canvas)`, `_load`, plus optional hooks `_pick_frame_for_elapsed(elapsed_ms)` and `_is_static() -> bool`. `_is_static()` drives the static-text fast path — multi-frame gifs MUST NOT fast-path (frames freeze on idx 0; tripwire `test_gif_static_text_does_not_freeze_animation`). Fit / alpha primitives live in `widgets/_image_fit.py` — canonical, do not duplicate. Validation rejects `text_align="scroll"` + `fit="stretch"`, `text_x_offset != 0` + scroll modes, `hold_seconds < 0.05`, BDF `font_size < cell_h`. Docs: <https://docs.ledticker.dev/widgets/gif/> · <https://docs.ledticker.dev/widgets/image/>.

**`text_align="scroll"` vs `"scroll_over"` paint order** — `"scroll"`: text first, then `_paint_skip_black` paints non-black image pixels on top → text walks BEHIND the image silhouette (use with RGBA + transparent regions). `"scroll_over"`: image first, text on top → always visible (use with opaque RGB). `"auto"` resolves based on `image_align`: `left`→`right`, `right`→`left`, `center`→`scroll_over`.

**Two-row text overlay on image widgets** — Setting `bottom_text != ""` on a gif/image widget switches it to held-top + scroll-on-overflow-bottom. `_play_with_two_row_text` paints the image to the unwrapped real canvas (native pixels) but wraps the same canvas in a `ScaledCanvas` for text+emoji draw. All band-height / baseline math operates in LOGICAL units against the wrapper — same coordinate system as TwoRowMessage. The wrap is also why hires emoji fires correctly (`isinstance(canvas, ScaledCanvas)` gate sees the wrapper). Wrapper `.real` is rebound after each `SwapOnVSync` (constraint #10). Single-row knobs (`text_align`, `text_valign`, `text_x_offset`, `font_size`) are refused in two-row mode. Tripwires: `TestTwoRowLogicalUnits`, `TestFieldSurfaceMatchesTwoRow`.

**Single-row image text — `font_size` is the unified knob** — `_resolved_font_size` resolves user-facing `font_size` (real pixels), then `block_scale_for_font_size(font, font_size)` converts to integer block scale. BDF: rounds down to nearest integer multiple of cell height (raises if `font_size < cell_h`). HiresFont: always 1. Wrap scale at the call site is `block_scale` for BDF and `_logical_scale` for HiresFont (so the hires-emoji ScaledCanvas gate still fires). HiresFont configs MUST specify `font_size` explicitly; `validate_widget_cfg` raises with a hint. Migration error catches stale `text_scale =` TOMLs at config-load with the formula. Tripwires: `TestSingleRowFontSize`, `TestResolvedFontSize`, `TestBlockScaleForFontSize`, `TestFontSizeMigration`.

**Typewriter on image widgets** (`animation = "typewriter"` on `gif` / `image`) — Single-row only. Raises if `bottom_text != ""`, `text_align ∈ ("scroll", "scroll_over")`, or `text == ""`. Reads its per-effect counter via `frame_for("animation")` so it composes cleanly with continuous-phase `font_color` / `border`. Forces the slow path (`_play_with_text` gate predicate adds `AND animation is None`). Tripwires: `TestImageTypewriter` (5 tests).

**`play()`-style widgets in `run_swap`** — A widget can opt out of the standard hold-and-scroll path by exposing an async `play(real_canvas, frame, loop_count) -> Canvas` method. `_run_swap`'s `_show_one` helper dispatches to `_play_widget` (which unwraps the ScaledCanvas, calls `play()`, then re-anchors `.real` to the new back-buffer) when `_has_play(widget)` returns true. `_has_play` checks `inspect.iscoroutinefunction(type(widget).play)` — looking at the CLASS, not the instance — so Mock objects don't false-positive. Currently used by `GifPlayer` and `StillImage`. If the class has a `play` attribute that is NOT a coroutinefunction (e.g., forgot `async`), `_has_play` raises `RuntimeError` rather than silently routing the widget to the `draw()` path.

**BDF glyphs carry pre-computed `lit_pixels`** — `BDFGlyph.lit_pixels` is a flat `list[tuple[int, int]]` of `(col, row)` for set bits, computed at parse time. Bigsign rasterizer iterates this directly (most cells are unlit). `bitmap` is preserved as the source of truth; `test_bdf_parser.py` asserts the two stay in sync.

### Key Patterns

**Widget Protocol** — All widgets implement `draw(canvas, cursor_pos=0, *, y_offset: int = 0, font_color: Any = None) -> (canvas, int)`. The `y_offset` param shifts the widget vertically; omitting it breaks PushUp/PushDown transitions. Async data widgets implement `update()` and use `run_monitor_loop()` with exponential backoff.

**Widget Registry** — `@register("name")` decorator. Config loader uses `get_widget_class(name)`.

**Transition Registry** — `@register_transition("name")` decorator in the `transitions/` package.

**Color providers + animations** — see "Color providers and animations" below. Replaces the legacy `@register_presentation` registry.

### CRITICAL: Hardware Rendering Constraints

These constraints were learned through extensive real-hardware testing. They are the contract for any code that touches the render path. Do not relax them.

1. **SwapOnVSync return value MUST be captured**: `canvas = frame.matrix.SwapOnVSync(canvas)`. The return value is the previous front buffer which becomes the new back buffer. If discarded, you draw to the actively-displayed buffer, causing tearing and corruption. EVERY call site must capture this.

2. **DrawText rejects non-Canvas objects**: The real rgbmatrix `graphics.DrawText` is a C function that type-checks for `rgbmatrix.core.Canvas`. Python objects like ShadowCanvas will get `TypeError`. Never call `widget.draw()` on anything other than a real canvas or the test stub canvas.

3. **No GetPixel**: Cannot read pixels back from any canvas. The framebuffer stores pre-computed GPIO bitplane data, not RGB values. Reverse mapping is infeasible.

4. **SetPixel works everywhere**: `canvas.SetPixel(x, y, r, g, b)` works on real canvases, test stubs, and any object. All transition visual effects use SetPixel.

5. **Swap-then-sleep ordering**: Always `SwapOnVSync` first, then `asyncio.sleep`. Never sleep before swap — it adds frame latency.

6. **Font advance width ≠ visible glyph width**: BDF font characters have advance widths that include trailing whitespace within the character cell. When text scrolls to the right edge, the cursor reaches x=159 but the last visible pixel may be 2-3px earlier depending on the character (e.g., "!" is narrow within its cell, "M" fills it). This is standard bitmap font behavior, not a bug.

7. **Widget padding is for layout, not scroll stop**: `draw()` returns `cursor_pos` which includes `end_padding` (default 6px). This padding provides spacing between widgets in `forever_scroll` side-by-side mode — do NOT remove it from the widget. Instead, `_swap_and_scroll` ADDS padding back to stop_pos to compensate: `stop_pos = -(cursor_pos - canvas.width) + padding`. Since cursor_pos overshoots by padding, adding it scrolls less far left, putting the last character flush with the right edge.

8. **Test stubs simulate double-buffering**: The stub `SwapOnVSync` returns a DIFFERENT canvas object (not the same one) to catch code that discards the return value.

9. **ScaledCanvas wraps the real canvas**: In bigsign mode (`default_scale > 1`) the canvas widgets receive is a `ScaledCanvas`. `_swap` mutates `.real` in place so wrapper identity is preserved across frames; transitions that re-wrap (`run_transition` at `incoming_scale != current`) must do so explicitly and not rely on the wrapper survival path.

10. **`play()`-style widgets must rebind their text/secondary canvases after every swap**: A widget that owns its swap loop (e.g. `GifPlayer.play()`, `StillImage.play()`) typically holds two canvas references: one for the image (real canvas, native pixels) and one for text (a temporary ScaledCanvas wrapper or the same real canvas at scale=1). After `canvas = frame.matrix.SwapOnVSync(canvas)`, the secondary reference is now stale — pointing at the old front buffer that's currently displaying. ScaledCanvas wrappers re-anchor via `wrapper.real = canvas`; raw-canvas references must be reassigned (`text_canvas = canvas`). Skip this rebind and you paint to the displayed buffer every other tick — visible as a "pulsing" flicker on the panel. Both widgets share `_BaseImageWidget._play_with_text` so the rebind lives in one place. The two-row equivalent in `_play_with_two_row_text` follows the same pattern. Tripwires: `test_play_no_wrap_text_canvas_follows_back_buffer` (single-row gif), `test_play_two_row_no_wrap_text_canvas_follows_back_buffer` (two-row gif), and `test_text_canvas_follows_back_buffer` (still).

11. **Per-pixel scatter (Dissolve) must run at physical resolution on ScaledCanvas**: A SetPixel-based scatter operating on the wrapper's logical canvas at scale=4 has only 1024 logical pixels — at peak (`t=0.5`, `count=total`) every logical pixel blacks out, every 4×4 block on the real canvas blacks out, and the panel goes 100% black for one frame. That's a fade-through-black, not a dissolve. Unwrap via `unwrap_to_real(canvas)` and call `real.SetPixel` so the scatter has 16× more grain (16,384 pixels on the bigsign). Tripwire: `test_scatter_uses_physical_resolution_through_scaled_canvas` in `tests/test_transitions.py`.

12. **Every per-tick redraw loop must call `advance_frame()` per tick**: Frame-aware widgets (the `_FrameAware` mixin) track `_frame_count`, which `ColorProvider.color_for(frame, ...)` reads to animate Rainbow / ColorCycle. Any loop that calls `widget.draw(...)` at frame cadence must call `_advance_frame_if_supported(widget)` before the draw — otherwise the provider sees a stuck `_frame_count` and Rainbow renders as a static gradient that scrolls but doesn't sweep. Applies to: (a) the shared engine in `ticker.py` — `_swap_and_scroll` (held + scroll branches), `_scroll_and_delay` (scroll-in + post-scroll hold), `_scroll_one_by_one`, `_scroll_side_by_side` (advance every UNIQUE buffered widget per outer tick — dedup by `id()`); (b) `play()`-style widgets that own their render loop — `GifPlayer.play()` / `StillImage.play()` via `_BaseImageWidget._play_with_text` / `_play_with_two_row_text`. Static-text fast paths bypass via the provider's `frame_invariant` flag — `_ConstantColor`, `Random`, and `Gradient` are `frame_invariant=True` and skip the per-tick loop; Rainbow / ColorCycle are `False` (forced through the loop). New providers default to `False` (conservative). **Transition compositors are exempt** — `run_transition` calls `pause_frame()` so the widget's counter doesn't drift while being re-rendered for compositing. `_scroll_between` is dispatched directly (not through `run_transition`) and explicitly calls `outgoing.pause_frame()` / `incoming.pause_frame()` at entry, `resume_frame()` in `finally`. Enforcement: `tests/test_engine_redraw_contract.py` AST-scans `ticker.py` and asserts every loop body containing `widget.draw(...)` also calls `_advance_frame_if_supported(...)`, with an `ALLOW_LIST` for transition compositors that pause instead. Single-sleep holds (`await asyncio.sleep(hold_time)` after a final draw) are NOT caught by AST; each such site needs its own per-function tripwire. Tripwires: `TestScrollOneByOne` / `TestScrollSideBySide` / `TestScrollAndDelay` / `TestSwapAndScrollEngineTick` (`tests/test_ticker_display.py`); `TestPlayLoopAdvancesFrame` (`tests/test_widgets/test_image_base.py`).

### Display Flow

1. `app.py` loads TOML config and builds widgets from the registry
2. `Ticker` is created with widgets, frame, transition config, and hold_time
3. Ticker runs one of three modes: `run_forever_scroll()`, `run_infini_scroll()`, or `run_swap()`
4. In swap mode: each widget is held (scrolled if overflowing), then transition runs
5. `run_transition()` returns the current back-buffer canvas — caller MUST capture it
6. Between sections: a section-to-section transition runs
7. Canvas pushed to hardware via `canvas = frame.matrix.SwapOnVSync(canvas)`

### Transition System

30+ transitions registered. Full catalogue + per-family knobs: <https://docs.ledticker.dev/transitions/>. Categories:

- **Push** — outgoing + incoming move together (`push_left/right/up/down`, `push_alternating`, `push_random`). Use draw-blackout-draw to avoid DrawText overlap; receive `outgoing_scroll_pos` from `_swap_and_scroll` so they continue from where text stopped scrolling.
- **Wipe** — stationary outgoing + colored sweep line erases (`wipe_left/right/up/down`, `wipe_alternating`, `wipe_random`). Draw outgoing at pos=0, SetPixel-blackout regions, draw sweep on top, snap to incoming at t=1.0. Blackouts erase `outgoing.draw()`'s text bleed (DrawText cannot be clipped) — they are NOT redundant against `Clear()`.
- **Sprite-trail** — `nyancat`, `pokeball`, `baseball`, `pacman`, `sailor_moon` (each has `_reverse` and `_alternating`; first three have hires variants). See "Hi-res transitions" above.
- **Special** — `cut` (instant), `color_flash` (white flash), `dissolve` (seeded RNG scatter), `split` (center-outward black band), `scroll` (seamless continuous scroll with bullet separator).

**Frame freeze during transitions** — `run_transition` calls `pause_frame()` on outgoing/incoming before its loop and `resume_frame()` after (try/finally). Frame-aware widgets (`_FrameAware`-derived) use this to keep `frame_count` from advancing while being re-rendered for compositing — otherwise a Typewriter / Rainbow widget mid-cycles during the dissolve and re-enters the next section at a wrong phase. Plain widgets are skipped via duck-typing.

**Cross-scale dissolves** — `run_transition(..., incoming_scale=N)` re-wraps the canvas at the new scale at t ≥ 0.5 so the incoming widget dissolves IN at its native size. The function returns the new wrapper — callers MUST capture the return value (`canvas = await run_transition(...)`).

**Symmetric `bg_color` through transitions** — `run_transition(..., outgoing_bg_color=(r,g,b), incoming_bg_color=(r,g,b))` keeps bg color painted throughout. Without these, the per-frame reset is `Clear()` and bg-colored sections show twin flashes (bg disappears at start, "border on black" one-tick flash at end). With both set, t<0.5 paints `Fill(outgoing_bg)` and t>=0.5 paints `Fill(incoming_bg)` — cut-over at 0.5 matches `incoming_scale`'s switch point. Either side can be `None` independently. **Hires snap inside `_hires_loader`** — `render_hires_frame` and `render_hires_baseball_frame` do their own Clear+draw at t≥SNAP_THRESHOLD (0.95) before drawing incoming; `run_transition` forwards `incoming_bg_color` via `frame_at` kwargs and the snap calls `_snap_reset(canvas, incoming_bg_color)` so bordered widgets don't show the one-tick "border on black" flash. Call sites: `app.py` passes `last_bg_color` → outgoing, `section.bg_color` → incoming; `ticker.py:_run_swap` passes `prev_object.bg_color` → outgoing, `ticker_object.bg_color` → incoming. Tripwires: `TestRunTransitionIncomingBgColor`, `TestRunTransitionOutgoingBgColor`, `TestHiresSnapRespectsIncomingBg`.

### Color providers and animations

User-facing surface: <https://docs.ledticker.dev/concepts/color-providers/> · <https://docs.ledticker.dev/concepts/animations/> · <https://docs.ledticker.dev/concepts/borders/> · <https://docs.ledticker.dev/concepts/frame-counters/>.

**Color provider contract** — `font_color` (and `top_color` / `bottom_color` on TwoRow / image widgets) accepts: constant `[r, g, b]`, legacy `"random"` sentinel, string shorthand (`"rainbow"` / `"color_cycle"` / `"shimmer"`), or inline table (`{style = "gradient", from = [...], to = [...]}` or `{style = "shimmer", ...}`). At config-load all normalize to a `ColorProvider` with `color_for(frame, char_index, total_chars) -> Color`. Constants wrap in `_ConstantColor` so widget-side dispatch is uniform. Per-char providers (`rainbow`, `gradient`) cause widgets that opt in to iterate characters and render each with its own color: currently `TickerMessage`, `TwoRowMessage` (per-row), and `_BaseImageWidget` text-overlay surface. Whole-string providers (`color_cycle`, `random`, constant) get a single `color_for` call per draw. New providers default `frame_invariant = False` (conservative). `ColorProvider` subclasses that omit the `frame_invariant` class attribute raise `TypeError` at definition time via `__init_subclass__` — the same enforcement applies to `BorderEffect` subclasses. Data widgets (`coinbase`, `coingecko`, `etherscan`, `mlb`, `mlb_standings`) accept `font_color` as a whole-string provider — they call `color_for(frame, 0, 1)` once per draw tick and apply the result uniformly to the label / text segments (not per-char). Per-char providers like `rainbow` still work but only their first hue position (`char_index=0`) is used, cycling with `frame` across ticks.

**Per-char providers + emoji** — Rainbow / gradient sweep continuously across `:slug:` emoji boundaries: sprites render as sprites, the letters between/around them get per-char colors with `char_index` advancing across the emoji segments without resetting. Implemented via `pixel_emoji.draw_with_emoji(color: Color | ColorProvider, frame=N)` + `text_render.draw_text_per_char`.

**`Shimmer`** — cosine bright-spot sweep. `per_char=True`, `frame_invariant=False`, `restart_on_visit=False`. Fields: `base_color` (Color), `shimmer_color` (Color), `speed` (float, chars/sec, default 14.0), `width` (float, chars, default 8.0), `pause` (float, seconds, default 0.5). Wired in `coercion.py`; TOML keys `base`/`shimmer` accept `[r,g,b]` or string shorthands (`white`, `gold`, `blue`, `cyan`).

**Animation contract** — Custom animations implement the `Animation` Protocol (`src/led_ticker/animations.py`): `def frame_for(self, frame: int, full_text: str, canvas_width: int, text_width: int) -> AnimationFrame`. `AnimationFrame` carries `visible_text: str` (the slice to render this tick). Currently only `Typewriter` is shipped; the Protocol documents the contract for future animations.

**`animation = "typewriter"`** — Field on `TickerMessage`, `gif`, `image` (single-row only on the image side). `validate_widget_cfg` raises if `animation` appears on other widget types. Color and animation compose. `frames_per_char` (default 3) controls speed via the inline-table form: `animation = {style = "typewriter", frames_per_char = 6}`. The previous `WidgetPresenter` wrapper + `presentation = "..."` knob was removed; `Bounce` (animation) and `Pulse` (color provider) were removed in the rework. Migration error in `_build_widget` points users at the remaining knobs.

**Engine tick** (`_swap_and_scroll`) — Held-text branches run a tick loop calling `advance_frame + draw + swap` at `ENGINE_TICK_MS = 50ms` cadence so frame-aware effects animate during holds. Scroll branch also calls `advance_frame` per tick.

**Per-effect frame counters** — `_FrameAware._effect_frames` stores one counter per effect on a widget. Continuous-phase effects (`Rainbow`, `ColorCycle`, `RainbowChaseBorder`) set `restart_on_visit = False` as a class attribute — counter doesn't reset on `_show_one`'s visit-entry call, so phase advances continuously across `loop_count > 1`. Restart-on-visit effects (`Typewriter`, default for unknown classes) reset per visit. Section transitions still reset via `run_transition`'s `_reset_presenter` — entry-to-section is always fresh state. Widget code reads `self.frame_for(attr_name)` instead of `self._frame_count` when calling effect APIs. Widget's `_frame_count` is preserved as the engine tick counter (resets per visit) for back-compat with direct readers.

**Rainbow border** — `border` field accepted on `message`, `countdown`, `two_row`, `gif`, `image` (other types raise at config-load). Paints an animated 1- or 2-pixel ring around the panel perimeter at PHYSICAL resolution (bypasses ScaledCanvas via `unwrap_to_real`). Border paints BEFORE text in `TickerMessage.draw` (text overlaps border on collision). `RainbowChaseBorder` uses the same `((idx * char_offset) + frame * speed) % 360` hue formula as `Rainbow.color_for` for letters, indexed by perimeter position (clockwise from top-left). On TwoRowMessage at scale=2 the border traces the actual real-panel edge, not the wrapper. On image widgets, `border.frame_invariant` flag is part of the fast-path gate predicate (same shape as `font_color.frame_invariant`). `GifPlayer._play_no_text` runs at engine 50ms cadence (via `_pick_frame_for_elapsed`) so animated borders chase uniformly regardless of gif frame durations — side effect: gifs with native frame durations < 50ms cap at 20 Hz on this path. Bigsign-tuned defaults: `speed=4` (~12s per revolution), `char_offset=6` (~60 distinct hue cycles around a 640-px perimeter). Tripwires: `TestRenderTickBorder`, `TestRenderTwoRowTickBorder`, `TestPlayWithTextBorderFastPath`, `TestPlayWithTwoRowBorderFastPath`, `TestImageBorderPhysicalResolution`, `TestGifPlayNoTextRefactor`, `TestStillPlayNoTextBorder`.

**Weather two-color design** — `WeatherWidget` has both `font_color` (label) and `font_color_temp` (temperature value) as separate `ColorProvider` fields. Default `font_color_temp = RGB_WHITE` keeps the value steady-bright while the label can use an effect. Set both to the same provider if you want them to match.

## Plugin invariants

led-ticker is extensible via plugins; the `pool.monitor` widget lives in the external [`led-ticker-pool`](https://github.com/JamesAwesome/led-ticker-pool) repo. When touching plugin-related code:

- **Public surface:** plugins import ONLY from `led_ticker.plugin` (the curated re-export module). Never import `led_ticker.<internal>` from a plugin. `led_ticker.plugin.__all__` is the contract; adding to it is an API change.
- **Registration:** a plugin ships a `register(api)` function under the `led_ticker.plugins` entry-point group; `api.widget("name")(cls)` (and the sibling `transition`/`emoji`/`font`/… surfaces) register into a namespaced registry (`<plugin>.<name>`, e.g. `pool.monitor`). `API_VERSION` gates compatibility.
- **Install:** plugins are installed from `config/requirements-plugins.txt` (copied from `.example`), constraint-based (`-c <frozen core deps>`, NOT `--no-deps`) so they may bring new deps but can't move core's pinned versions — the Docker build writes `/code/constraints-core.txt`; `deploy/install.sh` freezes to a temp file. Entry points auto-register at startup; the `[plugins]` config block only controls loading/disable, not installation.
- **Validation:** a widget plugin may define `validate_config(cls, cfg) -> list[str]` (pre-coercion); it runs inside `validate_widget_cfg`.
- **Python 3.14 / PEP 649:** no `from __future__ import annotations` in plugin source (same rule as core).
- Deep reference: `docs/plugin-system.md`. User-facing overview: the docs-site [Plugins page](https://docs.ledticker.dev/plugins/).

### Adding a New Widget

1. Create `src/led_ticker/widgets/my_widget.py`
2. Add `@register("my_widget")` decorator
3. Implement `draw(canvas, cursor_pos=0, *, y_offset: int = 0, font_color: Any = None) -> (canvas, int)`
4. Use `y_offset` directly in layout (e.g. `baseline_y + y_offset`) — omitting it breaks PushUp/PushDown transitions
5. For animated `font_color` (rainbow, color_cycle) or `border` effects: inherit `_FrameAware` from `widgets/_frame_aware.py` and decorate with `@attrs.define`. Without `_FrameAware`, the engine's `advance_frame()` calls are no-ops and animated effects render as static colors.
6. For async data: implement `update()` and use `run_monitor_loop()`
7. Add import to `src/led_ticker/widgets/__init__.py`

### Adding a New Transition

1. Create `src/led_ticker/transitions/my_transition.py` (or add to existing file)
2. Import and use `@register_transition("name")` decorator from `led_ticker.transitions`
3. Implement `frame_at(t, canvas, outgoing, incoming)` where t is 0.0-1.0
4. At t=0: show only outgoing. At t=1.0: show only incoming.
5. Use SetPixel for visual effects (sweep lines, blackout regions) — NOT ShadowCanvas
6. Never call `widget.draw()` on anything other than the real `canvas` parameter
7. No manual registration needed — `transitions/__init__.py` uses `pkgutil.iter_modules` to auto-discover every non-private `.py` file in `transitions/`. Creating the file and applying `@register_transition` is sufficient.

### Testing

1438+ tests, ~95% coverage, runs in ~2 minutes with no Docker.

- `make test` sets `PYTHONPATH=tests/stubs` automatically
- Test stubs simulate double-buffering: the real-stub `RGBMatrix.SwapOnVSync` returns a DIFFERENT canvas object each call so dropped-capture bugs surface
- Stub `DrawText` writes actual pixels for pixel-level test assertions
- Weather tests need `monkeypatch.setenv("WEATHERAPI_KEY", "test-key")`

**Tripwire fixtures in `tests/conftest.py`:**
- `mock_frame` — convenience; `SwapOnVSync.return_value = canvas` (same object). Fine for tests that don't care about capture-correctness.
- `swapping_frame` — rotates between two canvas mocks. Use this in regression tests for constraint #1 (capture the swap return). Drop the capture and `widget.draw` will only see one canvas — assert on `len({id(c) for c in draw_args}) >= 2`.

**Meta-tripwires worth knowing about:**
- `tests/test_engine_redraw_contract.py` — AST-scans `ticker.py` for constraint #12 (advance_frame in every per-tick loop)
- `tests/test_docs_config_options_drift.py` — audits `docs/site/.../reference/config-options.mdx` against `config.py` dataclasses (per-section field set + `[display]` defaults)
- `widgets/_image_base.py:TestFieldSurfaceMatchesTwoRow` — catches drift between two_row + image two-row text overlay field sets
- `tools/render_demo/test_renderer_multiframe.py` — synthetic rainbow-text fixture; asserts `n_frames > 1` AND first-frame ≠ last-frame on `render()` output. Catches both regression classes for the renderer pipeline: engine not swapping the canvas, AND widget not varying its canvas across captured ticks.

### Configuration

User-facing reference: <https://docs.ledticker.dev/reference/config-options/>.

- App config: `config/config.toml` (mounted in Docker at `/code/config/`, gitignored)
- Examples: `config/config.example.toml` (smallsign), `config/config.bigsign.example.toml` (bigsign with `pixel_mapper_config`, scaling, RP1 tuning), `config/config.moonbunny.example.toml` (real-world bigsign template)
- API keys: `.env` (see `.env.example`)

**Section transition precedence** — When a section explicitly writes `transition = "..."` in its TOML, that transition is used for BOTH the inter-section ENTRY (when this section appears) AND inter-widget transitions (between widgets within the section). Sections that omit `transition` fall back to `[transitions] between_sections` for entry. The `transition_specified: bool` flag on `SectionConfig` records whether the user wrote the field — without it the parser cannot distinguish "user wrote `transition = X`" from "section inherited X from default". `_build_trans_obj` is the shared factory used for both entry and inter-widget transitions. For independent control, sections also accept `entry_transition` (overrides how THIS section appears, ignoring `between_sections` and `transition`) and `widget_transition` (overrides inter-widget transitions within this section). Precedence: `entry_transition` > `transition` > `between_sections` for entry; `widget_transition` > `transition` > cut for within-section.

### Docker / Deployment

- Production image: `python:3.14-bookworm` base, 3-layer caching (rgbmatrix → deps → source).
- Single image runs on both Pi 4 and Pi 5. The rgbmatrix library is hardcoded to `jamesawesome/rpi-rgb-led-matrix` (default branch `main`) — Pi5 RP1 support (hzeller#1886, merged upstream) plus three patches: GCC10 anonymous-param fix (`pio_rp1.c`), Pillow shim (`graphics.py`), SubFill Python binding (`core.pyx`). The library detects the SoC at runtime and selects the BCM2711 GPIO backend (Pi 4) or the RP1 PIO/RIO backend (Pi 5). The pre-RP1 codebase is preserved on the `pi4_legacy` branch.
- On the Pi 5, the runtime CLI also accepts `--led-rp1-rio=0|1` (PIO vs Registered IO mode). For chain length ≥ 2 with flicker, raise `gpio_slowdown` from 2 to 3+.
- Config mounted read-only: `./config:/code/config:ro`.
- Systemd: `deploy/led-ticker.service`. Full deploy walkthrough: <https://docs.ledticker.dev/hardware/building-your-own/>.

### Hardware quick reference

- **Smallsign (Pi 4)** — 5× 32×16 = 160×16 px. `default_scale = 1`, `gpio_slowdown = 2`, `hardware_mapping = "adafruit-hat"`, ~20 fps. Full BOM + wiring: <https://docs.ledticker.dev/hardware/smallsign/>.
- **Bigsign (Pi 5)** — 8× P3 32×64 in a 2×4 vertical-serpentine = 256×64 px. `default_scale = 4`, `gpio_slowdown = 3` paired with `rp1_rio = 1`, `pwm_bits = 8`, custom `pixel_mapper_config` Remap string. DrawText clips safely at canvas edges (y can be negative or > height). Full BOM + chain diagram + Pi-5 tuning: <https://docs.ledticker.dev/hardware/bigsign/>.

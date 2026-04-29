# Design: Port led-ticker to Pi 5 / 2×4 P3 Big Sign

**Date:** 2026-04-29
**Status:** Approved (brainstorm). Ready for implementation planning.

## Summary

Adapt the led-ticker codebase to run on a second physical sign while keeping the existing sign working from the same `main` branch. The new sign uses a Raspberry Pi 5, an Adafruit RGB Matrix HAT, and 8 P3 32×64 panels arranged in a 2×4 serpentine layout (single chain of 8, folded with `U-mapper`), giving a logical canvas of **64 × 256 pixels** — 16× the pixel count of the existing 16 × 160 sign.

All current widgets and transitions are ported with a deliberately blocky, pixel-doubled aesthetic: existing assets (BDF fonts, sprites, weather icons, pixel emoji) are scaled up by an integer factor at draw time. A `Region` parameter is plumbed through the widget protocol but always equals the full canvas — it's a hook for a future zoned-layout mode (multiple widgets sharing the canvas), explicitly deferred.

## Goals

- The new sign boots and runs the existing widget set (RSS, weather, MLB standings, countdowns, crypto, messages) at the new resolution with the existing transitions.
- The existing 16×160 sign continues to work from the same branch with no behavior change.
- Each sign has its own `config.toml` and its own systemd unit; one Docker image source, two build-arg variants (Pi 4 fork vs Pi 5 fork of `rpi-rgb-led-matrix`).
- Pixel-doubled rendering is uniform across text, sprites, and transition effects — no per-asset rework required for the port.
- Per-section `scale` config so individual widgets/sections can override the default scale factor.
- Test coverage stays in the 90s and `make test` continues to pass without Docker.

## Non-goals

- Zoned multi-region layouts (different widgets sharing the canvas in non-overlapping regions). The `Region` type is plumbed but unused beyond full-canvas defaults.
- New widget types (live game scores, calendar, clock, etc.). Out of scope for this port.
- Hand-drawn larger sprites or new BDF fonts. Existing assets are scaled, not redrawn.
- Layout engine, widget composition primitives, dynamic per-zone scale.

## Hardware constants

- **Pi:** Raspberry Pi 5 running Raspbian 64-bit
- **HAT:** Adafruit RGB Matrix HAT (same `gpio_mapping = "adafruit-hat"`)
- **Panels:** 8× 32×64 P3, single serpentine chain
- **Layout (cable enters bottom-right at panel 1):**
  ```
  8  6  4  2     ← top row (panels physically rotated 180°)
  7  5  3  1     ← bottom row
  ```
- **Logical canvas:** 64 tall × 256 wide (rows × parallel × ... × cols × chain ÷ U-mapper fold)
- **Library mapper:** `U-mapper` (built into hzeller library, no custom mapping needed)

## Library / Pi 5 dependency

The current image pins `github.com/jamesawesome/rpi-rgb-led-matrix`, which targets Pi 4. Pi 5 swapped GPIO from the SoC to the RP1 chip, breaking the original library. Pi 5 has been running variants of this lib in the past, but the working fork needs reverification.

**Approach:**
1. Survey current state of Pi 5–capable forks (hzeller branches, community forks).
2. Pick the most stable one and re-fork under `jamesawesome/` so the project controls the pin.
3. Add a Docker build-arg `RGBMATRIX_REF` so the same `Dockerfile` produces a `pi4` and `pi5` image variant.
4. `pyproject.toml` dependency uses the same build-arg via a wheel build step or installs the library at image-build time (current pattern).

**Risk:** the Pi-5 fork may be less mature than the Pi-4 one. We'll verify hardware refresh quality on first boot and tune `slowdown_gpio` / `pwm_lsb_nanoseconds` as needed.

## Configuration

### `[display]` schema additions

```toml
[display]
rows = 32              # was 16
cols = 64              # was 32
chain = 8              # was 5
parallel = 1
pixel_mapper = "U-mapper"   # NEW — defaults to "" for existing sign
brightness = 60
slowdown_gpio = 2      # tune per-Pi
gpio_mapping = "adafruit-hat"
default_scale = 4      # NEW — base scale factor for widgets/transitions
```

`LedFrame` already exposes a `led_pixel_mapper` attribute; the TOML loader needs to wire `pixel_mapper` through to it.

### Per-section override

```toml
[[playlist.section]]
mode = "swap"
scale = 2              # NEW — overrides display.default_scale for this section
# ... rest unchanged
```

### Per-sign config files

- `config/config.toml` — existing sign (unchanged)
- `config/config.bigsign.toml` (or location-named) — new sign
- Each Pi mounts its own config file; the systemd unit's `--config` argument selects which.

## Canvas dimensions: derived, not hardcoded

Logical canvas size is `canvas.width × canvas.height` after pixel mapping. The codebase will use these properties exclusively rather than any hardcoded `160`/`16` constants. The implementation plan will include a sweep for such constants (likely in test stubs and a few drawing helpers).

The test stub `RGBMatrix` will honor configured rows/cols/chain/parallel/mapper so widget tests can run against both a 16×160 stub and a 64×256 stub.

## Pixel-doubling renderer

### `ScaledCanvas` wrapper

A small wrapper class (`drawing.py` or new `scaled_canvas.py`) takes a real canvas plus an integer `scale` and a `content_height` (default 16 — the existing widget content's natural height). The contract: **callers always work in a `content_height`-tall logical canvas**, and the wrapper scales it up and vertically centers it within the real canvas at write time.

- `width` returns `real.width // scale`
- `height` returns `content_height` (always 16 by default — same as the existing sign)
- `SetPixel(x, y, r, g, b)` paints a `scale × scale` block on the underlying canvas at `(x * scale, y * scale + y_center_offset)`, where `y_center_offset = (real.height - content_height * scale) // 2`
- `Clear()` clears the underlying canvas
- `SwapOnVSync` is **not** exposed on the wrapper — the Ticker calls swap on the real canvas after rendering completes

This means widgets see a 16-tall logical canvas regardless of scale. At `scale = 4` on a 64-tall real canvas, content fills exactly. At `scale = 2`, content is 32 real-pixels tall, centered with 16 black pixels top and bottom — letterboxing, no widget changes needed.

Used everywhere existing code calls `SetPixel`:
- Sprite blits (nyancat, pokeball, baseball, pacman, sailor_moon)
- Weather icons, pixel emoji
- Transition sweep lines, dissolve random pixels, split center-band, scroll separator dot

**At `scale = 1`** the wrapper is either bypassed entirely or trivially passes through, so the existing sign sees no behavior change. Implementation may choose either; the test fixture asserts equivalence at `scale = 1`.

### Text rendering: pure-Python BDF rasterization for scaled path

`graphics.DrawText` is a C function that writes directly to a real canvas, and real canvases don't support `GetPixel` — we can't intercept or read back what `DrawText` produced. So we can't pixel-double its output.

**Approach:** parse BDF font files in pure Python at startup and bypass `graphics.DrawText` entirely for `scale > 1`.

BDF is a simple text format that lists each glyph's bitmap as hex rows. A small parser produces a `{char: 2D bool array}` dict per loaded font. To draw text:

1. For each character, look up its glyph bitmap.
2. Iterate the bitmap's lit cells and `SetPixel` each one onto a `ScaledCanvas` — the wrapper paints `scale × scale` blocks automatically.
3. Advance x by the glyph's advance width.

**At `scale = 1`** the existing sign keeps using `graphics.DrawText` unchanged — no behavior or performance change. The pure-Python path is only taken when `scale > 1`.

The bundled fonts (`5x8.bdf`, `6x10.bdf`, `6x12.bdf`, `7x13.bdf`) parse once at module import. Glyph data is small (a few KB total) and stays resident.

### Glyph cache

Parsed glyph bitmaps are themselves the cache — preloaded at module import, indexed by `(font, char)`. No eviction needed. Drawing a string is a sequence of dict lookups + bitmap iterations.

If the per-frame glyph iteration becomes a hot path, a second-level cache keyed on `(text, font, color, scale)` can pre-compute the full string's lit-block list. Not needed for v1; the per-character iteration on a 256-wide canvas at 20 fps is well within the Pi 5's budget.

### Y centering

Centering is computed once inside the `ScaledCanvas` wrapper as `(real.height - content_height * scale) // 2` and added to every `SetPixel` Y coordinate. Widgets remain oblivious. For `scale = 4` on a 64-tall canvas it's `0` (content fills); for `scale = 2` it's `16` (16-pixel letterbox top and bottom).

## Widget protocol

### New signature (kwargs only, backwards-compatible)

```python
def draw(canvas, cursor_pos=0, *, region=None, **kwargs) -> (canvas, int):
    region = region or Region(0, 0, canvas.width, canvas.height)
    y_offset = kwargs.get("y_offset", 0)
    # ... draw in logical coordinates; `canvas` may be a ScaledCanvas
```

The `canvas` argument is either a real `RGBMatrix` canvas (existing sign, `scale = 1`) or a `ScaledCanvas` wrapper (bigsign, `scale > 1`). Either way, widgets work in **logical coordinates** — they treat the canvas as 16 tall regardless of scale. The wrapper's `width`/`height`/`SetPixel` translate transparently. Widgets call a shared `draw_text()` helper (defined alongside the BDF parser) that handles both paths: at scale = 1 it forwards to `graphics.DrawText`; at scale > 1 it iterates parsed BDF glyph data and `SetPixel`s onto the wrapper.

`scale` is **not** part of the widget signature. Widgets that need to know it (rare — primarily for hardcoded constants that should multiply with scale) can pull it via `getattr(canvas, "scale", 1)`. `region` is passed for forward compatibility with zoned layouts.

### `Region` type

```python
@attrs.define
class Region:
    x: int
    y: int
    width: int
    height: int
```

Defined in `drawing.py`. Defaults to full canvas. **Always equals full canvas in this port** — it's a forward-compatibility hook for future zoned layouts.

### Plumbing

- `Ticker` reads `scale` from each section's TOML. For sections with `scale > 1`, it wraps the real canvas in a `ScaledCanvas(real, scale)` once and passes the wrapper into widget `draw()` calls and into `run_transition`.
- `_swap_and_scroll` clamps cursor against `region.width` (= `canvas.width` today, which is logical width when wrapped) instead of `canvas.width` directly. Same behavior now, correct behavior later.
- `transitions/run_transition` receives the wrapper transparently and forwards it to `frame_at()`. Transitions get logical coordinates; existing transition code works unchanged for SetPixel-based effects.
- Shared drawing helpers (`get_text_width`, `compute_cursor`) operate on logical coordinates — the same numbers they produce today.

### Per-widget changes

Because the `ScaledCanvas` always presents a 16-tall logical canvas, **the existing widget Y-baselines and pixel math stay correct unchanged**. The only required change per widget:

1. **Replace direct `graphics.DrawText` calls with a shared `draw_text()` helper** that picks the right path (C function vs. BDF rasterizer) based on whether `canvas` is a real canvas or a `ScaledCanvas`. The helper signature mirrors `graphics.DrawText` so call sites are mechanical replacements.

That's it. `12 + y_offset` keeps producing visually-correct text. SetPixel-based sprite blits and weather icons keep their existing pixel arrays. The wrapper does the work.

Affected widgets: `message`, `weather`, `mlb_standings`, `crypto/coinbase`, `crypto/coingecko`, `crypto/etherscan`, `rss_feed` (no draw, only feeds messages).

## Transitions at scale

All transition code stays in logical coordinates and uses `SetPixel`/`DrawText` exactly as today. Scaling, block painting, and centering are handled by the `ScaledCanvas` wrapper.

### Logical-width changes per scale

The bigsign is wider in real pixels (256) than the existing sign (160), but **narrower in logical pixels** at `scale = 4`: 256 / 4 = **64 logical wide**. At `scale = 2` it's 128 logical wide. This means:

- Sprite traversal covers fewer logical pixels at higher scale, so we tune per-frame step delays (number of frames per logical-pixel step) so the on-wall traversal duration feels right. Numbers will be tuned on hardware.
- Less text fits per screenful at `scale = 4` than on the existing sign at `scale = 1`. This is fine for a scrolling ticker but worth knowing for hold-mode messages.

### Per-transition work

- **Sprite-based** (nyancat, pokeball, baseball, pacman, sailor_moon): no code changes. Sprite arrays unchanged. Tune per-frame step delays for the new logical width.
- **Wipe** (`wipe_*`, `dissolve`, `split`): no code changes. Sweep-line widths and pixel counts already scale automatically via the wrapper.
- **Push** (`push_*`): no code changes. `DrawText` is replaced by the shared `draw_text()` helper as part of the widget refactor; blackout-zone math is in logical coordinates.
- **`scroll`** separator dot: no code changes (still a logical 2×2 SetPixel block; wrapper paints it as `(2 × scale) × (2 × scale)`).
- **`cut`, `color_flash`**: unaffected.
- **`*_alternating` variants**: driven by underlying transitions, no per-variant work.

### Frame budget

Target stays 20 fps (0.05 s/frame). Pi 5 has meaningful headroom over Pi 4. If we hit a wall, levers in priority order:
1. Add the second-level `(text, font, color, scale)` glyph-string cache mentioned in the rendering section
2. Lower `pwm_bits` from 11 → 9 (trades color depth for refresh)
3. Drop frame rate to 15 fps
4. Pre-rasterize sprite frames as bitmaps rather than per-frame loops

## Deployment

### Single source, dual image

- One `Dockerfile`. Build-arg `RGBMATRIX_REF=<ref>` selects which fork/branch of `rpi-rgb-led-matrix` to compile.
- CI builds two image tags: `led-ticker:pi4` and `led-ticker:pi5`.
- Each Pi pulls the appropriate tag.

### Per-sign systemd

`deploy/led-ticker.service` is per-Pi. Each unit hardcodes its own `--config` argument and image tag.

### Existing sign: zero regression

The existing Pi 4 sign keeps building against the current fork (current `RGBMATRIX_REF` becomes the default for the `pi4` image). All existing tests pass. All existing config files keep working — `pixel_mapper` defaults to `""`, `default_scale` defaults to `1`.

## Testing

### Existing tests

275+ tests must continue to pass against the 16×160 stub. No regressions on the existing sign.

### New tests for the bigsign path

A parallel set of tests using a 64×256 stub canvas, covering:

- Text scaling at `scale = 2` and `scale = 4`
- Sprite scaling on one representative transition (e.g. nyancat)
- One wipe transition (e.g. wipe_left)
- One push transition (e.g. push_left)
- Scroll separator dot at scale > 1
- Weather icon at scale > 1
- `message` widget at `scale = 4`
- Centering math when `scale = 2` on a 64-tall canvas

Assertions: `SetPixel` blocks land at correct `(x, y, scale)` positions.

### Hardware verification (manual)

On first boot of the new sign:
1. Port `config/config.toml` to bigsign config (same content, new `[display]` block).
2. Verify each widget renders with each transition.
3. Tune `slowdown_gpio` and `pwm_lsb_nanoseconds` until refresh is clean (no flicker, no tearing).
4. Confirm 20 fps target is hit; if not, apply frame-budget levers.

## Rollout order

Phases are roughly independent and can be reviewed/merged separately:

1. **Pi 5 fork research + dependency pin.** Survey forks, pick one, re-fork under `jamesawesome/`, add `RGBMATRIX_REF` build-arg. Independent unblocker.
2. **Canvas-size config plumbing.** Wire `pixel_mapper` and `default_scale` from TOML through to `LedFrame` and `Ticker`. No widget changes; existing tests pass unchanged.
3. **`Region` type + plumb wrapper through draw signatures.** Mechanical change across widgets and `run_transition`: add the optional `region` kwarg, accept either real-canvas or wrapper. No behavior change at `scale = 1`. Existing tests pass unchanged.
4. **`ScaledCanvas` + BDF parser + `draw_text()` helper.** New helper and rendering path. The pure-Python BDF parser plus the wrapper class. Add unit tests against the parser (correct glyph bitmaps for sample chars) and the wrapper (correct block placement at scale = 2 and scale = 4).
5. **Replace `graphics.DrawText` calls in widgets and transitions with `draw_text()`.** Mechanical, file-by-file. No behavior change at `scale = 1`.
6. **Wire scale through Ticker.** Read `scale` from each section, build the `ScaledCanvas` wrapper when `scale > 1`, pass it into widget `draw()` and `run_transition`. After this lands, bigsign config can render.
7. **Hardware boot + tuning.** Manual verification on the new sign. Tune timing constants (`slowdown_gpio`, `pwm_lsb_nanoseconds`), per-transition step delays for the new logical width. Update bigsign `config.toml`.

## Deferred / future work

- Zoned multi-region layouts (the "C" in the original D = B + hooks-for-C choice). The `Region` type is the seed; an implementation plan for this is a separate spec.
- New widget types (live game scores, calendar, clock).
- Hand-drawn higher-resolution sprite assets or larger BDF fonts.
- Dynamic per-zone scale.

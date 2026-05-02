# GIF widget — design

> **HISTORICAL.** This is the original 2026-05-01 design that drove the
> initial 7-task implementation. The shipped widget grew well beyond
> this scope: text alongside the gif (`text_align` left/right/scroll/
> scroll_over), inline `:slug:` emoji, `text_scale` for chunky bigsign
> glyphs, `text_loops` marquee floor, `gif_align` horizontal anchor,
> alpha-aware decode for transparent gifs, `mode = "swap"` integration
> via `_has_play` dispatch in run_swap, and the Dissolve fix to
> physical-resolution scatter. Notably the "Non-goals" claim that text
> wouldn't blend with gifs is no longer accurate. Current behavior
> lives in `CLAUDE.md` (see "GIF widget", "Native-resolution painting
> via unwrap_to_real", "play()-style widgets in run_swap"); use that
> doc for reference, this one for context on the original direction.

---

Display animated GIFs on the bigsign LED panel as if it were a small monitor: GIF plays at native physical resolution (256×64), advances frames at the GIF's intrinsic per-frame durations, loops a configurable number of times, then transitions out to the next section.

Test target: `~/Desktop/pika_wave.gif` (a Pikachu wave). Once landed, GIFs live alongside the config under an `assets/` dir.

## Goals

- A new `type = "gif"` widget addressable from TOML, with a new section `mode = "gif"` for playback orchestration.
- Loop count from config (predictable duration: GIF plays N full loops then moves on).
- Configurable aspect-ratio fitting: `pillarbox` (default), `letterbox`, `stretch`, `crop`.
- Config-relative GIF paths (`path = "assets/pika_wave.gif"`).
- Section transitions sandwich the GIF: entry transition runs first against the GIF's first frame, then GIF plays through, then the next section's transition runs against the GIF's last frame.
- No new runtime deps — Pillow ≥10 is already in `pyproject.toml`.

## Non-goals

- Not supporting video files (MP4/WebM) — GIF only.
- Not supporting hot-reload of GIFs at runtime; restart picks up new files.
- Not supporting per-row blending of GIFs with text (the GIF takes over the whole panel for the duration of its section).
- Not gamma-correcting the panel output. Raw RGB pixels go through SetPixel; if colors look washed-out we can revisit.

## Architecture

A new run mode (`gif`) drives a new orchestrator (`Ticker.run_gif()`) that pulls one widget at a time from `notif_queue` and calls its `play()` method. The widget owns Pillow decoding and pre-rendered per-frame pixel data; the orchestrator owns the frame-cadence sleep loop and loop counting.

### Why a new mode

The existing `swap` / `forever_scroll` / `infini_scroll` modes drive widgets at a fixed scroll-speed cadence (~50 ms). GIF playback runs at the GIF's intrinsic frame durations, which vary per frame (50 ms to 200 ms+). Trying to shoehorn variable-cadence playback into `run_swap` would require widgets to advertise custom timing back to the run loop. A dedicated `run_gif` is cleaner and isolates the new behavior.

### Why bypass ScaledCanvas

A GIF is conceptually a "monitor frame" — already at full physical resolution. We want to paint at the real 256×64 underlying canvas without each pixel becoming a `scale × scale` block. The GIF widget detects `ScaledCanvas` and unwraps to `canvas.real` for both `draw()` and `play()`.

The section's `scale` setting is effectively ignored for `mode = "gif"` sections. Documented in the example config.

### Transition sandwiching

Section transitions are unchanged. The first/last-frame approach lets the existing `run_transition` infrastructure work without knowing it's a GIF:

1. Entry transition (between previous section and the GIF section) runs `run_transition(outgoing=prev_section_last_widget, incoming=gif_widget)`. The GIF widget's `draw()` paints frame 0 of the GIF — `run_transition` composites against this exactly like a static widget.
2. After the transition completes, `Ticker.run_gif()` takes over. The widget's `play()` method runs the actual playback loop.
3. After playback completes, `widget._current_frame_idx` is set to the last frame. Subsequent `widget.draw()` calls paint the last frame to the canvas.
4. The next section's transition treats the GIF widget as `outgoing` and composites the GIF's last-frame pixels.

## Components

### `src/led_ticker/widgets/gif.py` — new file

```python
@register("gif")
@attrs.define
class GifPlayer:
    path: str
    fit: str = "pillarbox"  # pillarbox | letterbox | stretch | crop
    padding: int = 0  # required by widget protocol; unused for GIFs
    _frames: list[tuple[bytes, int]] = attrs.field(init=False, factory=list)
    _current_frame_idx: int = attrs.field(init=False, default=0)
    _loaded: bool = attrs.field(init=False, default=False)

    def _load(self) -> None: ...
    def draw(self, canvas, cursor_pos=0, **kwargs) -> tuple[Canvas, int]: ...
    async def play(self, real_canvas, frame, loop_count: int = 1) -> Canvas: ...
```

- `_load()`: lazy. First call opens the GIF, iterates `n_frames` via `seek()`, applies `fit` mode at decode time, stores `[(rgb_bytes, duration_ms), ...]` where `rgb_bytes` is a flat `bytes` of length `panel_w * panel_h * 3`.
- `draw(canvas, cursor_pos=0, **kwargs)`: paints `_frames[_current_frame_idx]` directly to `canvas.real` (via SetPixel) at full physical resolution. Returns `(canvas, canvas.width)` so the widget claims the entire row width.
- `play(real_canvas, frame, loop_count)`: the playback loop. For each loop, for each frame: clear, paint pixels, swap, sleep. Sets `_current_frame_idx = len(frames) - 1` on exit.

### `src/led_ticker/widgets/_gif_decode.py` — new file

```python
def decode_gif(path: Path, panel_w: int, panel_h: int, fit: str
              ) -> list[tuple[bytes, int]]: ...
```

Pure function, easy to unit-test. Returns a list of `(rgb_bytes, duration_ms)` tuples.

Fit modes:
- **pillarbox**: scale by height to `panel_h`, clamp width to `panel_w`, center on a 256×64 black canvas. So a 256×256 GIF becomes 64×64 in the middle; a 1024×64 wide GIF becomes 256×16 letterboxed (i.e. pillarbox is really "fit-by-height, don't exceed width").
- **letterbox**: scale by width to `panel_w`, clamp height to `panel_h`, center.
- **stretch**: resize directly to `panel_w × panel_h`, distorting.
- **crop**: scale to cover both axes (the larger ratio), center-crop the excess.

Pillow does the heavy lifting: `Image.open() → seek(i) → convert("RGB") → resize() / paste onto black canvas`.

### `src/led_ticker/ticker.py` — extend

- New `Ticker.run_gif(loop_count: int = 0)` method. Pulls one or more GIF widgets from `notif_queue` and calls each widget's `play()` method on `canvas.real`.
- New `_run_gif()` async helper analogous to `_run_swap`. Always starts playback from frame 0 (frame 0 is what the entry transition compositing already painted, so the visible frame is continuous across the transition→playback boundary).

### `src/led_ticker/app.py` — extend

- Add `"gif": "run_gif"` to `RUN_MODES`.
- For widgets where `cfg["type"] == "gif"`: resolve `path` relative to the config file's directory before constructing the widget. `path = (config_path.parent / cfg["path"]).resolve()`.

### `config/config.bigsign.example.toml` — example

Add a commented-out section showing the `gif` mode + widget config, including all four `fit` values and the `loop_count` knob.

## Data flow

**Config load**:
```
TOML → app.py builds widgets → for type="gif":
  resolve path relative to config dir →
  GifPlayer instance (decoding deferred to first .draw() / .play() call)
```

**Section run with mode="gif"**:
```
1. just_transitioned: run_transition(outgoing=prev_widget, incoming=gif_widget)
     → gif_widget.draw() paints frame 0 to canvas; existing dissolve composites against it
2. Ticker.run_gif(section.loop_count):
     widget = notif_queue.get()
     widget._load()  # first call decodes all frames
     real = canvas.real if isinstance(canvas, ScaledCanvas) else canvas
     await widget.play(real, frame, loop_count)
3. After play(), widget._current_frame_idx = last frame.
4. Next section's transition reads widget.draw() and gets the last frame back.
```

**Per-frame paint** (inside `play()`):
```python
for loop in range(max(1, loop_count)):
    for frame_pixels, duration_ms in self._frames:
        real.Clear()
        for y in range(panel_h):
            row_offset = y * panel_w * 3
            for x in range(panel_w):
                base = row_offset + x * 3
                real.SetPixel(x, y, frame_pixels[base], frame_pixels[base + 1], frame_pixels[base + 2])
        real = frame.matrix.SwapOnVSync(real)  # CLAUDE.md #1: must capture
        await asyncio.sleep(max(50, duration_ms) / 1000)
self._current_frame_idx = len(self._frames) - 1
```

**Performance**: 256 × 64 = 16 384 SetPixels per frame. At ~10 fps, ~164 K SetPixels/sec. The bigsign already sustains ~256K/sec for `forever_scroll` text at scale=4, so this is well within budget. Memory cost per frame: 49 KB; a typical 30-frame GIF stays under 2 MB.

## Error handling

- **Path doesn't exist**: raise a clear `FileNotFoundError("GIF not found at <path>")` at decode time. Caught at config-build time and treated as a config error (section skipped, logged) — same handling as other widget construction errors today.
- **File isn't a valid GIF**: Pillow raises; propagate as a config error.
- **Single-frame GIF / static PNG aliased to .gif**: works fine; `n_frames=1`, plays through `loop_count` times.
- **Per-frame `duration_ms = 0`** (some tools emit this): clamp to ≥50 ms.
- **`loop_count = 0`** in config: interpret as "play once" (consistent with the rest of the codebase).

## Testing

- `decode_gif` unit tests covering each fit mode, building synthetic in-memory GIFs via `Image.new() / save(format='GIF', save_all=True, append_images=...)`. Assert frame count, output dims (always 256×64), and that the relevant black-band region is all-zero RGB.
- `GifPlayer._load()`: idempotency — second call doesn't redecode.
- `GifPlayer.play()` smoke test on the test-stub canvas: assert `SwapOnVSync` is called `n_frames × loop_count` times; assert SetPixel total is `panel_w * panel_h * frames * loops`.
- Regression test for CLAUDE.md constraint #1 (capture the swap return) using the `swapping_frame` fixture pattern.
- Hardware test: copy `~/Desktop/pika_wave.gif` to `<repo>/config/assets/pika_wave.gif` (creating the directory), wire it into the test config with `mode = "gif"`, `loop_count = 2`, `fit = "pillarbox"`, deploy to the bigsign. Watch for frame advancement, transition sandwiching, and any flicker/tearing.

## Open questions / future work

- **Color rendering**: the LED panel does its own gamma; raw sRGB pixels may look washed out (especially whites and dark grays). If pika_wave looks bad, a follow-up could add an optional `gamma` knob (default 1.0, set to ~2.2 for a perceptual fix).
- **Memory for long GIFs**: currently we eagerly decode every frame into memory. A 1000-frame GIF would be ~50 MB. Not a concern for the test target. Future work could lazy-decode if needed.
- **Multiple GIFs per section**: the design supports it (notif_queue iteration), but practically you'd usually have one. The orchestrator handles this for free; no extra work.

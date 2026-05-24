# render-demo

Render a led-ticker config TOML to a gif at panel resolution. Used by the
docs site to generate per-widget demo gifs from minimal config snippets.

## Usage

```bash
uv run python tools/render_demo/render.py path/to/config.toml -o out.gif \
  [--duration 5] [--upscale 4] [--start-section 0]
```

## How it works

The script wraps `LedFrame.matrix.SwapOnVSync` with a `RecordingMatrix` that
snapshots each canvas before forwarding to the underlying stub swap. After
`--duration` seconds, the captured frames are upscaled (default 4x) and
encoded to a gif.

## Missing assets

If the config references images, gifs, or fonts that don't exist on disk,
the renderer generates synthetic placeholder stand-ins (dark-lavender block
with the missing path text) before running. This means customer-IP configs
can be used as structural demos without committing brand assets to the repo.

## Tests

```bash
uv run pytest tools/render_demo/ -v
```

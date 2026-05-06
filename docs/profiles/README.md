# Performance Profiles

py-spy flame graphs of led-ticker running on real hardware. Used as
baselines so future regressions are visible by comparison.

Filename convention: `YYYY-MM-DD-<config>-<target>.svg`

## How to capture

```bash
# Inside the running container
docker compose exec led-ticker pip install py-spy
docker compose exec led-ticker py-spy record \
  -o /tmp/profile.svg \
  --pid 1 \
  --duration 60

# Copy out
docker compose cp led-ticker:/tmp/profile.svg ./profile.svg
```

If `Permission denied: ptrace`, add `cap_add: [SYS_PTRACE]` to the
service in `compose.yaml` and `docker compose up -d --force-recreate`.

## Profiles in this directory

### `2026-05-06-presentation-smoke-bigsign.svg`

- Target: bigsign (Pi 5 + 8× P3 panels @ 256×64 logical, scale=4)
- Config: `config/config.presentation_test.example.toml` (17 sections —
  rainbow + emoji + animation + hires fonts + RSS + gif + still image)
- Captured: 60s, on the `presentation-emoji-per-char` branch right
  before merge to main (commit `e948254`).

**Context**: hardware was running healthy at the time of capture —
rgbmatrix C-side refresh was 86 Hz worst-case (11.6 ms vs 50 ms
engine tick budget = 77% headroom). Python `_run_once` saw ~3% CPU.

**Hot Python paths** (relative to active samples, not wall time):
- 35% `text_render.draw_text`
- 31% `scaled_canvas.draw_bdf_text` (per-glyph lit-pixel iteration)
- 28% `scaled_canvas.SetPixel` (4×4 block expansion on bigsign)
- 32% `gif.play` / `_run_gif`
- 25% `TickerMessage.draw`
- 15% `draw_text_per_char` (per-char rainbow / gradient)

**Conclusion**: no measurable performance problem. The branch's
recent additions (per-tick advance for animated providers, per-char
rainbow on hires fonts) don't impact frame budget. If a future
profile shows the BDF rasterizer chain (`draw_text` →
`draw_bdf_text` → `SetPixel`) consuming substantially more — or the
hardware refresh dipping toward the 50 ms tick budget — start
optimizing there.

Optimization options ranked by effort × payoff (deferred — not
worth doing today):
1. Constant-color BDF string cache → single `SetImage` call (~4 hr,
   skips 16× block expansion for static text).
2. Frame-buffer approach: render to numpy array, push via SetImage
   once per tick (~2 days, eliminates Python per-pixel loop entirely).
3. Cython-compile `SetPixel` + `draw_bdf_text` (~4 hr, modest gain).

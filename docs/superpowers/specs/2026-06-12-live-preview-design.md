# Live display preview — design

**Date:** 2026-06-12
**Status:** approved design, pre-implementation
**Builds on:** the web status UI (specs of 2026-06-10 and 2026-06-11; shipped in
PRs #192/#196/#197). All standing invariants carry forward: read-only sidecar,
never-500 degraded states, rgbmatrix import purity, web path must never affect
the panel.

## Summary

Mirror what's on the LED panel into the web status page: a `TeeCanvas` in the
display process shadows every draw into a byte buffer, `frame.swap()` writes a
raw-RGB frame file to the tmpfs volume at 5 fps, the sidecar serves the bytes
verbatim, and the browser renders them onto a pixelated `<canvas>`. The mirror
runs **only while a browser is actually watching** — zero render-path cost
otherwise. Supports all scales, including smallsign (scale = 1).

## Performance posture (the design's organizing principle)

| State | Render-path cost |
|---|---|
| `[web]` absent | Zero. No tee, no new code on any path. |
| `[web]` present, unwatched | One boolean branch per SetPixel + one isinstance per `draw_text`/`swap`. Estimated well under 1% of the 50 ms tick budget; verified by an on-device micro-bench during hardware validation. |
| Watched | Extra byte stores per pixel, BDF re-raster for scale = 1 text, one ~100 KB tmpfs write per 200 ms (same cost class as the already-benchmarked status heartbeat). Typical content ≈ 1–2% of tick budget. |
| Watched, worst case | **Full-canvas gif sections**: the blit loop already pushes tens of thousands of SetPixels per tick; mirroring adds ~30–50% to that loop while watched. Named, bounded, temporary; degrades to slightly slower gif frames, never to a frozen panel. Measured during hardware validation and recorded. |

Every CPU-owning step lands on the machine with the most idle capacity:
display does a memcopy, sidecar serves file bytes, the browser does all
rendering (no PNG encoding anywhere, no Pillow on the hot path).

## Component 1: capture lifecycle (watched-flag)

Three actors, one tmpfs directory (the existing `ticker-status` volume), no
new processes:

- **Browser**: polls `GET /api/preview` at 5 fps while the Status tab is
  active AND the page is visible (`visibilitychange` + tab-switch stop it).
- **Sidecar**: on every preview fetch, touches `preview-requested` (empty
  marker file; `utime` only) and serves the latest frame. This is the
  sidecar's only write, ever — a deliberate, narrow exception to
  "pure reader," confined to one empty file whose only content is an mtime.
  status.json remains display-written only.
- **Display**: the existing heartbeat task checks the marker mtime once per
  second (one tmpfs `stat()`, off the render path). Fresh (< 10 s) →
  `tee.mirror = True`. Stale → `False` and the frame file is deleted, so the
  sidecar reports idle instead of serving a frozen stale frame. The 10 s grace
  absorbs browser refreshes without thrashing.

The tee is installed **once at startup** when `[web]` is present, as the
innermost layer of the canvas chain, and is never inserted or removed
dynamically — only the boolean flips. Engine canvas references stay valid for
the process lifetime; no mid-cycle wrapper surgery exists to race.

First capture after enable is deferred until a full `Clear()`-initiated tick
completes (the shadow misses draws from earlier in the enabling tick). One
engine tick of delay; invisible at human timescales.

## Component 2: frame file + capture write

- **Shadow**: flat `bytearray(width × height × 3)`, physical resolution, RGB.
  SetPixel mirrors as an index computation + three byte stores; `Fill`/`Clear`
  mirror as bulk slice assignment (C-speed). One shadow spans both hardware
  buffers: it holds "everything drawn since the last Clear," which after a
  full tick equals the displayed frame — the engine's redraw-every-tick
  discipline is what makes a single shadow correct.
- **Capture point**: inside `frame.swap()`, after overlay hooks paint (the
  busy-light dot belongs in the preview), beside the liveness counter. Gated
  on `mirror and (now - last_capture) >= 0.2`.
- **File**: `preview.bin` = 16-byte header (magic, version, width, height,
  seq) + raw RGB payload, written temp + `os.replace` (atomic, same pattern
  as status.json) to the tmpfs volume. ~100 KB at 5 fps.
- **Seq** advances per capture; a static panel stops advancing seq, letting
  the page skip repaints and doubling as a liveness signal for the mirror.

## Component 3: TeeCanvas mechanics

- Surface: exactly what widgets use — `SetPixel`, `Fill`, `Clear`, `width`,
  `height` — each forwarding to the hardware canvas and, when mirroring, to
  the shadow.
- The hardware handle is `tee._hw`, deliberately NOT `.real`: `unwrap_to_real`
  walks `.real`, so the tee is **terminal** to the unwrap machinery. Every
  existing physical-resolution paint site (hires fonts/emoji, dissolve
  scatter, borders) lands on the tee with zero call-site changes.
- Exactly two places reach past the tee, both of which already special-case
  canvas types today:
  1. **`frame.swap()`** — unwraps `tee._hw` for C `SwapOnVSync`, then rebinds
     `tee._hw` to the returned back buffer. Tee identity is stable across
     frames (the same invariant ScaledCanvas documents). Callers keep
     capturing swap's return (constraint #1) unchanged.
  2. **`text_render.draw_text()`** — the scale = 1 branch becomes: C
     `DrawText` on `canvas._hw`; if mirroring, rasterize the same glyphs into
     the shadow via the existing BDF machinery (`lit_pixels`, byte writes —
     not per-pixel method calls); return the C advance width.
- Wrapper order: smallsign → widgets receive the tee directly;
  scaled signs → `ScaledCanvas(TeeCanvas(hw))` built by `_maybe_wrap`,
  rebound via the existing `rebind_innermost` machinery.
- **Ownership**: `LedFrame` owns the single tee for the process lifetime.
  `get_clean_canvas()` rebinds `tee._hw` to the fresh hardware buffer and
  returns the tee (callers chain `ScaledCanvas` on top as today), exactly
  as `swap()` rebinds per frame — one tee object, many hardware buffers.
- **Spine invariant** (tripwired): the hardware forward happens first and
  unconditionally; mirroring is write-only divergence. A shadow bug can
  produce a wrong preview but structurally cannot produce a wrong panel.

### Fidelity caveat (scale = 1 only)

Preview text comes from the pure-Python BDF rasterizer; panel text from the C
library. They are stub-parity-tested but have never been bit-compared against
real C output, so a glyph edge may differ by a pixel in the preview. The panel
is untouched either way. (Pure-Python text at panel scale is already the
bigsign's normal operating mode at 4× the pixel count — viability is
hardware-proven, only exactness carries the caveat.) The page shows a one-line
muted caption on scale = 1 signs.

## Component 4: endpoint + page

- **`GET /api/preview`** (auth-gated): success → payload bytes,
  `application/octet-stream`, with `X-Preview-Width/-Height/-Seq` headers.
  Degraded states are JSON, never 500: file absent → `{"state": "idle"}`
  (the normal first answer — the fetch itself wakes the mirror; the page shows
  "waking the preview…" for ~a second); bad magic/version or size-vs-header
  mismatch → `{"state": "unsupported", ...}` (sidecar/display version skew,
  same posture as the schema envelope).
- **Page**: hero strip at the top of the Status tab — `<canvas>` at the
  physical panel aspect, `image-rendering: pixelated`, LED-bezel styling. JS
  unpacks raw RGB into `ImageData`. Seq-unchanged → no repaint. Pre-tee
  display processes (any build before this feature) never produce a frame: after a few seconds of
  idle-while-watching the page says the display process needs upgrading.

## Error handling

- Capture-write exceptions self-disable capture for the session (one
  WARNING), panel unaffected — the publisher's failure rule, inherited.
- Mirror-rasterization failures disable mirroring the same way; never
  propagate into a widget's draw.
- The tee's hardware-forward path introduces no new failure modes (same calls
  as today, one indirection deeper).
- Sidecar marker-touch failure logs once; preview degrades, other tabs
  unaffected. Display marker-stat failure → mirror stays off (fail-quiet
  toward zero cost).

## Testing

- **Spine tripwire**: inject a shadow that raises on write; every pixel must
  still reach the hardware canvas and `swap()` must complete.
- **Mirror correctness**: known scene through the tee on stub hardware;
  shadow bytes == stub `_pixels` exactly at scale > 1; scale = 1 text held to
  the same stub-parity standard render_demo uses.
- **Lifecycle**: marker fresh/stale transitions; frame file deleted on
  disable; first-capture-deferred-until-after-Clear; throttle (N swaps in
  200 ms → 1 write); capture failure self-disables without touching swap.
- **Engine contracts stay green**: the redraw-contract AST suite and all
  render-path tripwires must pass unchanged — the tee adds no draw loops.
- **Endpoint**: idle/ok/unsupported envelopes, auth, header echo, and a
  binary round-trip (real tee → file → fetch → pixel-compare).
- **Perf gates, not vibes**: on-device micro-bench (sibling of the tmpfs
  flush bench) measuring tee-off and mirror-on per-tick overhead on
  text-heavy and gif-full-canvas content during longboi hardware validation;
  results recorded in the PR.
- **Composition**: tee + render_demo's `RecordingMatrix` compose (one test),
  keeping the door open for preview-in-CI.

## Out of scope

- Preview-driven controls of any kind (still no write path to the display).
- History/recording (the file holds exactly one frame).
- Audio of any kind for the three people who will ask.
- WebSocket push — polling at 5 fps is sufficient and keeps the sidecar
  dependency-free; revisit only if a real need appears.

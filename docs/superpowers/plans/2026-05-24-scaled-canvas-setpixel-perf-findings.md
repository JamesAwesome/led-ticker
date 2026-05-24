# ScaledCanvas SetPixel Performance — Research Findings

**Date:** 2026-05-24  
**Branch:** scaled-canvas-perf  
**Status:** Research complete; Docker rebuild + hardware benchmark not yet done

## Problem

`ScaledCanvas.SetPixel` at scale=4 fires 16 Python→C Cython calls per logical pixel (a 4×4 block = 16 individual `SetPixel` calls). On the bigsign (64×16 logical), a fully-lit frame = **16,384 Python→C calls per frame**. Each call crosses the Cython dispatch boundary (GIL handling, argument parsing, C++ vtable call).

## Benchmark Results (dev machine stub)

| Path | Calls/Frame | Python dispatch / frame | % of 50ms budget |
|---|---|---|---|
| Original (16× SetPixel) | 16,384 | ~0.73 ms | 1.5% |
| SubFill prototype (1× per pixel) | 1,024 | ~0.08 ms | 0.2% |
| **Speedup** | **16× fewer calls** | **~9.5–9.8×** | — |

> Dev-machine benchmark uses a Python stub that counts calls. On real Pi 5 hardware, each Cython `SetPixel` call has GIL acquisition, arg parsing, and a C++ vtable dispatch — the actual speedup will be larger than the stub numbers show.

## C++ API Landscape

| API | C-side savings vs 16× SetPixel | Python call reduction | Viable? |
|---|---|---|---|
| `SubFill(x, y, w, h, r, g, b)` | **High** — single `MapColors` call + sequential designator advance (no per-pixel `get(x,y)` lookup) | 16→1 per logical pixel | **YES** |
| `SetPixels(x, y, w, h, Color*)` | **None** — loops `SetPixel` internally | 16→1 per logical pixel (Python overhead only) | Marginal |
| `Serialize/Deserialize` | N/A | N/A | **NO** — opaque format, config-tied, no Python binding, breaks animation |

### Why SubFill beats SetPixels on the C side

`SubFill` in `framebuffer.cc`:
1. Calls `MapColors(r, g, b)` **once** to convert RGB → PWM planes
2. Looks up the starting `PixelDesignator` once per row and **increments the pointer sequentially** across columns (cache-friendly, avoids the `shared_mapper_->get(x, y)` hash lookup per pixel)

`SetPixels` is a thin loop over `SetPixel` — each call does its own `MapColors` + `get(x,y)` lookup.

## Python Binding Gap

Neither `SubFill` nor `SetPixels` is declared in `cppinc.pxd` or wrapped in `core.pyx`.

### Minimal change to expose SubFill (~6 lines total across 2 files)

**`bindings/python/rgbmatrix/cppinc.pxd`** — add inside `cdef cppclass FrameCanvas(Canvas):`:
```cython
void SubFill(int, int, int, int, uint8_t, uint8_t, uint8_t) nogil
```

**`bindings/python/rgbmatrix/core.pyx`** — add method to `cdef class FrameCanvas(Canvas):`:
```cython
def SubFill(self, int x, int y, int width, int height,
            uint8_t red, uint8_t green, uint8_t blue):
    (<cppinc.FrameCanvas*>self._getCanvas()).SubFill(
        x, y, width, height, red, green, blue)
```

## Upstream Status

`hzeller/rpi-rgb-led-matrix` (upstream) has **no Python binding for SubFill or SetPixels**. Our fork is 5 commits behind upstream (all docs). Upstream has now officially merged kingdo9's Pi5 PR (#1886) — our fork could simplify by tracking `upstream/master` directly, with only 4 commits to reapply: CLAUDE.md, fork-notes header, Pillow shim, `pio_rp1.c` named-param fix.

## Prototype Result

- Added `SubFill` to `tests/stubs/rgbmatrix/__init__.py`
- Updated `ScaledCanvas.SetPixel` to single `self.real.SubFill(rx, ry, s, s, r, g, b)` call
- **1980/1980 tests pass** (2 pre-existing hardware skips unchanged)

## Fix Approach Ranking

| Approach | Effort | Expected speedup | Risk |
|---|---|---|---|
| **A: Expose SubFill + update ScaledCanvas** (recommended) | 6 lines Cython + Docker rebuild (~0.5 day) | ~9–15× Python-side; additional C-side savings from designator reuse | Low — minimal surface area |
| B: Expose SetPixels + numpy buffer in ScaledCanvas | ~3 days | ~9–15× Python-side; no C-side savings | Medium — requires frame buffer architecture |
| C: PIL-backed ScaledCanvas (render to PIL, call SetImage) | ~2 days | 1 Python call per frame | Medium — PIL alloc overhead; only works for solid-color blocks if custom format used |

## Recommendation

Ship **Approach A**. The Cython change is 6 lines in 2 files in our fork + a 3-line `ScaledCanvas.SetPixel` update in led-ticker. The Docker rebuild is the only non-trivial part. Hardware benchmark on Pi 5 should be done post-rebuild to confirm actual speedup (expected: > 9.8× because Cython GIL overhead dominates stub's pure-Python overhead).

## Bonus Finding: Fork Simplification Opportunity

Since upstream/master now contains Pi5 support, consider rebasing our 4 patches directly onto `upstream/master` instead of maintaining the divergent `main`. This keeps us current with any upstream fixes (RT kernel docs, future GPIO improvements) without manual cherry-picks. Low urgency but worth doing at the next Docker image rebuild milestone.

## Next Steps

1. `git checkout -b subfill-binding` on the rpi-rgb-led-matrix fork
2. Apply the 6-line Cython change (cppinc.pxd + core.pyx)
3. `make build-docker` to rebuild the image
4. Deploy to Pi 5, add a timing probe around `ScaledCanvas.SetPixel` calls, measure real-hardware speedup
5. Merge the rpi-rgb-led-matrix fork PR + the led-ticker `ScaledCanvas` change as a paired release

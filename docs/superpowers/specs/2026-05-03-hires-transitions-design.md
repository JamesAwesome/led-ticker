# Hi-res Transitions — Design

**Date:** 2026-05-03
**Status:** Approved, ready for implementation plan

## Goal

Add high-resolution variants of `nyancat` and `pokeball` transition families on the bigsign (Pi 5, 256×64 native) using bundled animated gif/webp sprites. Selection is automatic via canvas type — same TOML config (`transition = "nyancat"`) works on both signs; the bigsign auto-picks the hi-res branch.

## Why now

The bigsign has 256×64 native physical pixels but `ScaledCanvas` paints transition sprites at 16-row "logical" resolution and expands each pixel into a 4×4 block. The 16-row Pikachu in `pokeball` reads as readable but blocky. With real animated sprite assets staged on `~/Desktop` (transparent webp/gif of Nyan Cat and a running Pikachu), we can render at native physical resolution where the existing `:moon:` hi-res emoji has already proven the pattern works.

## Scope (decided in brainstorming)

**In scope:** hi-res variants of these 4 transition names:
- `nyancat`
- `nyancat_reverse`
- `pokeball`
- `pokeball_reverse`

`nyancat_alternating` and `pokeball_alternating` need no per-class change — they delegate to base/reverse and inherit dispatch automatically.

**Out of scope** (deferred — see end of doc):
- `sailor_moon`, `baseball`, `pacman` families (no hi-res source staged)
- Hi-res on the small sign (16-row panel can't host a 64-tall sprite)
- Per-transition fit/cadence/trajectory knobs
- Procedural rainbow trail or particle effects on the hi-res path

## Architecture

### Dispatch

No new transition class registrations. Existing classes (`NyanCat`, `NyanCatReverse`, `Pokeball`, `PokeballReverse`) get a single check at the top of `frame_at`:

```python
def frame_at(self, t, canvas, outgoing, incoming, **kwargs):
    if isinstance(canvas, ScaledCanvas) and self._registry_name in HIRES_REGISTRY:
        return self._frame_at_hires(t, canvas, outgoing, incoming, **kwargs)
    return self._frame_at_lowres(t, canvas, outgoing, incoming, **kwargs)
```

`_frame_at_lowres` is today's `frame_at` body, renamed verbatim. `_frame_at_hires` is new (Section: Per-frame rendering). `_registry_name` is a class-level string attr (e.g. `_registry_name = "nyancat"` on `NyanCat`, `"nyancat_reverse"` on `NyanCatReverse`) — set explicitly per class to avoid a fragile reverse lookup of the `@register_transition` decorator's registry.

The `:moon:` emoji's existing `HIRES_REGISTRY` is the precedent — same model, transition scope.

### Sprite registry and file layout

```
src/led_ticker/transitions/
  sprites/
    nyancat.webp           # 250×175, 6 frames (from ~/Desktop/nyancat-transparent.webp)
    pokeball.gif           # 220×160, 4 frames (from ~/Desktop/pikachu-run-transparent.gif)
  _hires_registry.py
  _hires_loader.py
```

Reverse variants reuse the same source file and flip horizontally at decode time — one file per family, not two. Sprites bundle inside the package via `importlib.resources` so `pip install` ships them.

```python
# _hires_registry.py
from dataclasses import dataclass
from pathlib import Path

SPRITES_DIR = Path(__file__).parent / "sprites"

@dataclass(frozen=True)
class HiresSpec:
    sprite_path: Path
    flip_horizontal: bool

HIRES_REGISTRY: dict[str, HiresSpec] = {
    "nyancat":          HiresSpec(SPRITES_DIR / "nyancat.webp",  flip_horizontal=False),
    "nyancat_reverse":  HiresSpec(SPRITES_DIR / "nyancat.webp",  flip_horizontal=True),
    "pokeball":         HiresSpec(SPRITES_DIR / "pokeball.gif",  flip_horizontal=False),
    "pokeball_reverse": HiresSpec(SPRITES_DIR / "pokeball.gif",  flip_horizontal=True),
}
```

Adding a new hi-res family later is one entry + one sprite file. No new module, no new class registration.

### Decoder and frame cache

```python
# _hires_loader.py
import functools
from dataclasses import dataclass

@dataclass
class HiresFrames:
    width: int                                                    # post-fit
    height: int                                                   # post-fit, ≤ panel_h
    durations_ms: list[int]                                       # per-frame, from gif/webp metadata
    non_black: list[list[tuple[int, int, int, int, int]]]         # per-frame skip-black pixels
    total_loop_ms: int                                            # sum(durations_ms)

@functools.cache
def load_hires(transition_name: str) -> HiresFrames | None:
    spec = HIRES_REGISTRY.get(transition_name)
    if spec is None:
        return None
    return _decode(spec)
```

`_decode` walks Pillow frames directly. `apply_fit` and `flatten_onto_black` from `widgets/_image_fit.py` produce panel-sized output (good for the GIF widget which fills the whole panel). The hi-res sprite path needs sprite-sized output (so we can position it horizontally during traversal), so the decoder uses Pillow primitives directly:

1. Open with Pillow, walk frames via `seek(i)`.
2. Per frame: convert to RGBA. If `spec.flip_horizontal`, mirror via `rgba.transpose(Image.FLIP_LEFT_RIGHT)`. Scale to fit panel height: `scale = panel_h / rgba.height`, `new_w = round(rgba.width * scale)`, resize via LANCZOS.
3. Flatten alpha onto a sprite-sized black image (`Image.new("RGB", (new_w, panel_h))` + `paste(scaled, (0,0), mask=scaled.split()[3])`), then `tobytes()`.
4. Run `scan_non_black` (the existing helper from `_image_fit.py`) over those bytes to build the `non_black` list per frame.
5. Read durations via `frame.info.get("duration", 50)`. Pillow exposes this on both gif and webp.

Result: a 88×64×6-frame nyancat ≈ 33k pixels per frame; only opaque non-black pixels are kept (~30-50% typically), so ~10-15k tuples per frame, 6 frames ≈ 80k tuples. Memory-cheap.

`@functools.cache` keeps the decoded frames forever — sprites are static and the decoder is pure.

### Per-frame rendering

```python
def _frame_at_hires(self, t, canvas, outgoing, incoming, **kwargs):
    sprite = load_hires(self._registry_name)        # cached
    real = unwrap_to_real(canvas)                   # bypass ScaledCanvas
    panel_w, panel_h = real.width, real.height

    # 1. Outgoing paints through the wrapper at logical coords
    outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))

    # 2. Sprite frame from elapsed wall-clock time (intrinsic timing)
    duration_ms = kwargs.get("duration_ms", 500)
    elapsed_ms = int(t * duration_ms)
    frame_idx = _frame_for_elapsed(elapsed_ms, sprite)

    # 3. Sprite x-position. Traversal direction follows flip_horizontal:
    #    forward (flip=False)  → enter from LEFT, exit RIGHT
    #    reverse (flip=True)   → enter from RIGHT, exit LEFT
    #    The sprite art is already mirrored via flip_horizontal at decode,
    #    so the cat/pikachu faces its travel direction in both cases.
    travel = panel_w + sprite.width
    spec = HIRES_REGISTRY[self._registry_name]
    if spec.flip_horizontal:
        sprite_x = panel_w - int(t * travel)
    else:
        sprite_x = -sprite.width + int(t * travel)
    sprite_y = (panel_h - sprite.height) // 2       # center vertically

    # 4. Skip-black paint to native pixels
    for x, y, r, g, b in sprite.non_black[frame_idx]:
        rx = sprite_x + x
        if 0 <= rx < panel_w:
            real.SetPixel(rx, sprite_y + y, r, g, b)

    # 5. Snap to incoming at t≥0.95
    if t >= 0.95:
        canvas.Clear()
        incoming.draw(canvas)
```

**Why outgoing paints through the wrapper but the sprite paints to `real`:** outgoing is a normal widget at logical 16-tall coords and benefits from the wrapper's block expansion. The sprite is already at native physical resolution; painting through the wrapper would 4×4-block-expand each sprite pixel and defeat the purpose.

**`_frame_for_elapsed`** mirrors `gif.py`'s existing per-frame picker — walks cumulative durations until `pos < cum`. Lives in `_hires_loader.py` so transition modules import it from the same place as the registry.

### `run_transition` wiring change

`run_transition` adds one kwarg to its `frame_at` call:

```python
transition.frame_at(
    t,
    active,
    outgoing,
    incoming,
    outgoing_scroll_pos=outgoing_scroll_pos,
    duration_ms=int(duration * 1000),    # NEW
)
```

All existing transition classes use `**kwargs` and ignore extras — non-breaking change.

## Coexistence with the lowres path

The lowres path is preserved untouched. Today's `frame_at` body in each modified class becomes `_frame_at_lowres`, called verbatim when:
- `canvas` is not a `ScaledCanvas` (small sign, `scale=1`) → always lowres
- `canvas` IS a `ScaledCanvas` but the transition has no `HIRES_REGISTRY` entry (sailor_moon, baseball, pacman) → always lowres
- Test environment (conftest `canvas` fixture is a `Mock`) → always lowres → existing tests in `test_nyancat.py` / `test_pokeball.py` continue to pass without modification

`nyancat_alternating` / `pokeball_alternating` need no changes. Their `frame_at` delegates to base/reverse, each delegated call hits dispatch independently and picks lowres or hires based on the canvas. So `nyancat_alternating` on the bigsign cycles through hires-nyancat → hires-nyancat-reverse without alternating itself knowing hires exists.

The hires path's bottom-level paint primitive is `unwrap_to_real(canvas).SetPixel(...)` — the same path the GIF widget already drives at 20fps without flicker. Performance is known-good.

## Testing strategy

**1. Registry + loader (unit):**
- `HIRES_REGISTRY` has exactly the 4 expected entries.
- `load_hires(name)` returns `None` for unregistered names; returns `HiresFrames` for registered.
- `load_hires` is cached: two calls return the same object.
- `flip_horizontal=True` mirrors x: a non-black pixel at `(3, 5)` in the base sprite appears at `(width-1-3, 5)` in the flipped variant.
- Test fixtures use Pillow to generate a tiny 8×8 transparent gif with 2 frames at test setup, written to `tmp_path` and registered via a monkeypatched `HIRES_REGISTRY`. **Production sprite files are not test inputs.**

**2. Dispatch (per-class):**
- `NyanCat.frame_at(t, canvas=Mock(), ...)` → lowres path (existing tests in `test_nyancat.py` continue passing unchanged).
- `NyanCat.frame_at(t, canvas=ScaledCanvas(real, scale=4), ...)` with registered hires sprite → hires path (assert via spy on `_frame_at_hires`).
- `NyanCat.frame_at(t, canvas=ScaledCanvas(real, scale=4), ...)` with name not in registry → defensive fallback to lowres.
- Same coverage for `Pokeball`.

**3. Hires rendering (integration):**
- With a synthetic 8×8 sprite registered, painting at `t=0.5` places sprite pixels at expected x range and is centered vertically.
- Frame index advances with `duration_ms`: at `duration_ms=200`, `t=0` → frame 0; `t=0.5` → frame 1 if first frame is 50ms; etc.
- Sprite pixels outside `[0, panel_w)` are clipped (no `SetPixel` calls there).
- At `t >= 0.95`, the canvas is cleared and `incoming.draw` is called (asserted via spy).

**4. Production sprite smoke test:**
- One test loads each production sprite (`load_hires("nyancat")`, `load_hires("pokeball")`) and asserts: ≥1 frame, fits within 256×64, has a non-empty `non_black` list. Catches breakage if a sprite goes missing or becomes corrupt.

**5. `run_transition` wiring:**
- `run_transition(duration=0.5, ...)` passes `duration_ms=500` to `frame_at`. One mock-based test confirms.

**Estimated:** ~25-30 new tests across `tests/test_hires_loader.py` (new), `tests/test_nyancat.py` (extended), `tests/test_pokeball.py` (extended), `tests/test_transitions.py` (run_transition wiring).

**Not testing:** real-hardware visual fidelity — rely on a manual bigsign smoke run with a config that exercises every transition.

## Out of scope / deferred

- **Hi-res sailor_moon / baseball / pacman.** No source staged. Adding later is one `HIRES_REGISTRY` entry + one sprite file + nothing else.
- **Hi-res on the small sign.** `default_scale=1` → no `ScaledCanvas` → dispatch picks lowres. Hi-res sprites are 64-tall on a 16-tall panel — physically impossible.
- **Sprite fit modes.** Always fits-by-height. No `fit="stretch"`/`"crop"`/`"pillarbox"` knob per transition.
- **Per-sprite cadence override.** Sprite's intrinsic durations win. Re-export the gif at the desired speed if you want it faster.
- **Vertical / diagonal sprite paths.** Hi-res inherits left↔right traversal from lowres.
- **Rainbow trail behind hi-res nyancat.** Lowres `nyancat` paints a procedural rainbow background; hi-res draws only the sprite. The user's `nyan-cat-transparent-rainbow.gif` (1750×800) has the rainbow baked in — if the trail is wanted on the bigsign later, swap the registered source file and the rainbow comes for free.
- **Animated background / particle effects.** No sparkles, motion blur, etc. on the hires path.
- **Compressed / optimized sprite formats.** Pillow handles gif and webp natively. No APNG, no AVIF.
- **Runtime user-supplied sprite swap.** Sprites bundle with the package. Users wanting custom animated transitions can use the GIF widget instead.

## Touch list (rough)

- `src/led_ticker/transitions/sprites/` — new directory with `nyancat.webp`, `pokeball.gif` (copied from `~/Desktop/nyancat-transparent.webp` and `~/Desktop/pikachu-run-transparent.gif`).
- `src/led_ticker/transitions/_hires_registry.py` — new (HIRES_REGISTRY, HiresSpec dataclass).
- `src/led_ticker/transitions/_hires_loader.py` — new (HiresFrames, load_hires, _decode, _frame_for_elapsed).
- `src/led_ticker/transitions/nyancat.py` — split current `frame_at` into `_frame_at_lowres`; add `_frame_at_hires` and dispatch in `NyanCat` and `NyanCatReverse`. Add `_registry_name` class attr.
- `src/led_ticker/transitions/pokeball.py` — same edits to `Pokeball` and `PokeballReverse`.
- `src/led_ticker/transitions/__init__.py` — pass `duration_ms` to `frame_at`.
- `pyproject.toml` — package data include for `transitions/sprites/*`.
- Tests: `tests/test_hires_loader.py` (new), extensions to `tests/test_nyancat.py`, `tests/test_pokeball.py`, `tests/test_transitions.py`.

Estimated 8-12 small commits + tests.

---

## Implementation deltas (post-ship, 2026-05-03)

The design above shipped, plus these scope expansions added during hardware iteration:

- **Baseball family** added (`baseball`, `baseball_reverse`, `baseball_alternating`). Procedural — no sprite asset; reuses the `:baseball:` hi-res emoji geometry rotated through `_BASEBALL_ROTATION_FRAMES=8` frames at 45° each (cached via `@functools.cache`). Render path is `render_hires_baseball_frame`, parallel to `render_hires_frame` but separate because it uses procedural rotation, not Pillow frame seek.
- **Trail field on `HiresSpec`** (`"none"` / `"black"` / `"rainbow"`) — original spec had no trail concept. Without a trail, sprite traversal leaves outgoing text visible in regions the sprite has passed. Trail saturates at `TRAIL_SATURATION_T=0.85` (panel fully covered), holds, then snaps to incoming at `SNAP_THRESHOLD=0.95`.
- **`show_pokeball` toggle** (parallel to existing `show_pikachu`) — TOML can hide either entity. Threaded through `TransitionConfig` and `app._build_widget`. Sprite-only mode (`show_pokeball=False`) extends the trail through the sprite's own front edge so transparent regions read as trail color, not outgoing text bleed-through.
- **Procedural pokeball rotation** — original spec described a single Pillow-decoded sprite. Hi-res Pokeball is now procedural (`_paint_procedural_pokeball`) at radius=panel_h//3, with rotation keyed on travel distance, paired with the Pillow-decoded Pikachu chase sprite. RTL rotates counter-clockwise.
- **Sprite bbox black-fill before sprite paint** — added so transparent (alpha=0) regions of the sprite read as black, matching the lowres look. Originally the trail color leaked through. Skipped when `trail == "black"` (already covered by trail) for ~5600 SetPixel calls saved per frame.
- **Resampling: NEAREST, not LANCZOS** (spec called for LANCZOS). NEAREST preserves crisp pixel-art edges; LANCZOS rings on hard color transitions and softens the silhouette.
- **Pacman lowres tweak** — blackout extended through Pac-Man's *front* edge (was: trailing edge). Letters now vanish at his mouth instead of after he passes. `pacman` was deferred from the hi-res scope (8-bit aesthetic IS the design).
- **Sprite renamed**: spec called for `pokeball.gif`; shipped as `pikachu-run-transparent.gif` (more descriptive — the asset is the running Pikachu, the procedural ball is separate).

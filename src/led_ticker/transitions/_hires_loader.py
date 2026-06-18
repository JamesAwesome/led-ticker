# src/led_ticker/transitions/_hires_loader.py
"""Decoder, cache, and per-frame painter for hi-res transitions.

The loader uses Pillow directly (not `widgets/_image_fit.apply_fit` /
`flatten_onto_black`) because those produce panel-sized output suitable
for the GIF widget. Hi-res transitions need sprite-sized output so the
sprite can be positioned horizontally during traversal.

`render_hires_frame` paints a single sprite that traverses horizontally
leaving a trail and snaps to incoming near t=1.0; it is consumed by
external sprite-trail transition plugins.
"""

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from led_ticker.scaled_canvas import unwrap_to_real
from led_ticker.widgets._image_fit import scan_non_black


@dataclass(frozen=True)
class HiresSpec:
    """Describes one hi-res sprite asset for a sprite-trail transition.

    `sprite_path` points at a gif/webp sprite file.
    `flip_horizontal=True` mirrors each frame at decode (used for
    ``*_reverse`` variants so the sprite faces its travel direction).
    `trail` selects the band painted behind the sprite to erase outgoing
    text: ``"none"`` paints nothing, ``"black"`` fills the band with
    black, ``"rainbow"`` fills it with 6 horizontal RGB stripes.

    This class is part of the public plugin API (``led_ticker.plugin``) so
    external transition plugins can supply their own sprites to
    ``render_hires_frame`` / ``load_hires``.
    """

    sprite_path: Path
    flip_horizontal: bool
    trail: str = "none"


# Trail saturates (sprite reaches far edge, trail fills the entire panel)
# at this t. Below SNAP_THRESHOLD so the panel holds a fully-covered
# rainbow / black field for a beat before the cut to incoming — matches
# the lowres nyancat / pokeball "fill, hold, cut" feel.
TRAIL_SATURATION_T: float = 0.85

# Snap to incoming this fraction of the way through. By this t the trail
# has fully filled the panel (TRAIL_SATURATION_T < SNAP_THRESHOLD).
SNAP_THRESHOLD: float = 0.95

# Local copy of the lowres nyancat rainbow palette so this loader stays
# self-contained -- crossing-importing from `nyancat.py` would create a
# back-edge from the shared loader to a specific transition.
_RAINBOW_TRAIL_COLORS: list[tuple[int, int, int]] = [
    (255, 0, 0),  # red
    (255, 153, 0),  # orange
    (255, 255, 0),  # yellow
    (51, 255, 0),  # green
    (0, 153, 255),  # blue
    (102, 51, 255),  # purple
]


def snap_reset(canvas: Any, incoming_bg_color: Any) -> None:
    """Reset a canvas to the section's background before drawing the incoming
    frame at the end of a transition.

    Use this in a custom transition's ``frame_at`` when ``t`` reaches
    ``SNAP_THRESHOLD`` and you're about to draw the incoming widget: it Fills the canvas
    with ``incoming_bg_color`` (so a bg-colored section doesn't flash "incoming
    on black" for one tick), or Clears to black when no bg color is given.
    ``incoming_bg_color`` may be ``None``, an ``(r, g, b)`` tuple, or a
    ``graphics.Color`` — the same shapes a section's ``bg_color`` takes.
    """
    from led_ticker.transitions import _normalize_bg

    bg = _normalize_bg(incoming_bg_color)
    if bg is not None:
        canvas.Fill(*bg)
    else:
        canvas.Clear()


@dataclass(frozen=True)
class HiresFrames:
    """Decoded sprite, ready to paint at native resolution.

    `flip_horizontal` and `trail` are denormalized from the originating
    `HiresSpec` so callers (`render_hires_frame`) can read them off the
    cached frames without re-reading the originating `HiresSpec`.
    Intentional duplication; if these fields ever drift between
    HiresSpec and HiresFrames, the renderer's behavior will diverge
    silently from the spec.
    """

    width: int
    height: int
    durations_ms: list[int]
    non_black: list[list[tuple[int, int, int, int, int]]]
    flip_horizontal: bool
    trail: str = "none"
    total_loop_ms: int = field(init=False)

    def __post_init__(self) -> None:
        # frozen=True blocks normal attr assignment; use object.__setattr__
        # to set the auto-computed field. Standard pattern for frozen
        # dataclasses with init=False derived fields.
        object.__setattr__(self, "total_loop_ms", sum(self.durations_ms))


def _frame_for_elapsed(elapsed_ms: int, durations: list[int]) -> int:
    """Pick the frame index for a given elapsed time, wrapping at total loop."""
    total = sum(durations)
    if total <= 0:
        return 0
    pos = elapsed_ms % total
    cum = 0
    for i, d in enumerate(durations):
        cum += d
        if pos < cum:
            return i
    return len(durations) - 1


def _decode(spec: HiresSpec, panel_h: int = 64) -> HiresFrames:
    """Decode all frames of `spec.sprite_path` to sprite-sized non-black lists.

    Scales each frame by height to `panel_h`; flips horizontally if
    `spec.flip_horizontal`; flattens alpha onto black; runs `scan_non_black`.
    """
    durations: list[int] = []
    non_black: list[list[tuple[int, int, int, int, int]]] = []
    out_width = 0
    out_height = 0

    with Image.open(spec.sprite_path) as src:
        n_frames = getattr(src, "n_frames", 1)
        for i in range(n_frames):
            src.seek(i)
            rgba = src.convert("RGBA")
            if spec.flip_horizontal:
                rgba = rgba.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

            scale = panel_h / rgba.height
            new_w = max(1, round(rgba.width * scale))
            new_h = panel_h
            # NEAREST preserves crisp pixel-art edges; LANCZOS would ring on
            # hard color transitions and soften the silhouette. Sprites in
            # the registry are designed for pixel-doubling, not smoothing.
            scaled = rgba.resize((new_w, new_h), Image.Resampling.NEAREST)

            black = Image.new("RGB", (new_w, new_h), (0, 0, 0))
            black.paste(scaled, (0, 0), mask=scaled.split()[3])
            pixels = black.tobytes()

            # For animated WebP, Pillow populates img.info["duration"] only after
            # convert() forces frame decode. Read after convert, not before.
            durations.append(int(src.info.get("duration", 50)))
            non_black.append(scan_non_black(pixels, new_w, new_h))
            out_width = new_w
            out_height = new_h

    return HiresFrames(
        width=out_width,
        height=out_height,
        durations_ms=durations,
        non_black=non_black,
        flip_horizontal=spec.flip_horizontal,
        trail=spec.trail,
    )


@functools.cache
def load_hires(spec: HiresSpec) -> HiresFrames:
    """Decode + cache a sprite from its spec. Cached on the frozen, hashable
    HiresSpec, so callers (plugins holding their own spec) share decode work
    for identical specs. Build a plugin's spec once (module scope), not
    per-frame — the cache retains one decode per distinct spec."""
    return _decode(spec)


def render_hires_frame(
    t: float,
    canvas: Any,
    outgoing: Any,
    incoming: Any,
    spec: HiresSpec,
    **kwargs: Any,
) -> Any:
    """Paint one frame of a hi-res sprite traversing the panel, leaving a trail.

    Generic sprite-trail infra: a single sprite (from `spec`) moves
    horizontally across a `ScaledCanvas`, a trail fills behind its leading
    edge to erase outgoing content, and the frame snaps to `incoming` near
    t=1.0. Used by external sprite-trail transition plugins (e.g.
    led-ticker-arcade's nyancat / pokeball). No entity-specific logic.
    """
    # CAUTION: this function trusts that `canvas` is a `ScaledCanvas` (the
    # transition's own dispatch guarantees this).
    # `unwrap_to_real(canvas)` walks any number of nested ScaledCanvas
    # wrappers. If a future caller wraps a ScaledCanvas in some OTHER kind
    # of wrapper, dispatch would still pick lowres but this code would
    # paint to the wrong canvas. Not a concern today; flag here for future
    # reference.
    sprite = load_hires(spec)
    real = unwrap_to_real(canvas)
    panel_w = real.width
    panel_h = real.height

    # 1. Outgoing paints through the wrapper at logical coords.
    outgoing.draw(canvas, cursor_pos=kwargs.get("outgoing_scroll_pos", 0))

    # 2. Pick sprite frame from elapsed wall-clock time (intrinsic timing).
    duration_ms = int(kwargs.get("duration_ms", 500))
    elapsed_ms = int(t * duration_ms)
    frame_idx = _frame_for_elapsed(elapsed_ms, sprite.durations_ms)

    # 3. x-position. flip_horizontal drives both art mirroring AND
    #    traversal direction -- the sprite faces its travel direction.
    #    effective_t scales position so the leading edge reaches the far
    #    edge by TRAIL_SATURATION_T (well before SNAP_THRESHOLD), giving
    #    the trail time to fully fill the panel and hold before the cut.
    #    leading_x is the FRONT edge of the sprite (where it's moving to),
    #    so the trail extends THROUGH the sprite's region; the sprite then
    #    paints on top of the trail, and transparent / alpha-zero regions
    #    of the sprite reveal trail color rather than outgoing text.
    effective_t = min(1.0, t / TRAIL_SATURATION_T)
    travel = panel_w + sprite.width
    if sprite.flip_horizontal:
        sprite_x = panel_w - int(effective_t * travel)
        leading_x = sprite_x  # left edge — front of RTL traversal
    else:
        sprite_x = -sprite.width + int(effective_t * travel)
        leading_x = sprite_x + sprite.width  # right edge — front of LTR
    sprite_y = (panel_h - sprite.height) // 2

    set_px = real.SetPixel

    # 4. Paint trail BEHIND the leading edge (erases outgoing text).
    if sprite.trail != "none":
        if sprite.flip_horizontal:
            trail_x_start = min(panel_w, max(0, leading_x))
            trail_x_end = panel_w
        else:
            trail_x_start = 0
            trail_x_end = min(panel_w, max(0, leading_x))

        if trail_x_end > trail_x_start:
            if sprite.trail == "black":
                for y in range(panel_h):
                    for x in range(trail_x_start, trail_x_end):
                        set_px(x, y, 0, 0, 0)
            elif sprite.trail == "rainbow":
                n_stripes = len(_RAINBOW_TRAIL_COLORS)
                for stripe_idx, (r, g, b) in enumerate(_RAINBOW_TRAIL_COLORS):
                    y_start = stripe_idx * panel_h // n_stripes
                    y_end = (
                        (stripe_idx + 1) * panel_h // n_stripes
                        if stripe_idx < n_stripes - 1
                        else panel_h
                    )
                    for y in range(y_start, y_end):
                        for x in range(trail_x_start, trail_x_end):
                            set_px(x, y, r, g, b)

    # 5. Paint sprite pixels to the native physical canvas (skip-black).
    #    Before painting, blacken the sprite's bounding box so transparent
    #    (alpha=0) regions read as black instead of revealing the trail
    #    color underneath. Skip the bbox black-fill when the trail is
    #    already black across the sprite's bbox (black-trail case) — saves
    #    ~5600 SetPixel calls per frame on the bigsign. Still needed for the
    #    rainbow trail (must convert to black under the sprite) and
    #    trail="none" (prevents text bleed).
    if sprite.trail != "black":
        bbox_x_start = max(0, sprite_x)
        bbox_x_end = min(panel_w, sprite_x + sprite.width)
        bbox_y_start = max(0, sprite_y)
        bbox_y_end = min(panel_h, sprite_y + sprite.height)
        for y in range(bbox_y_start, bbox_y_end):
            for x in range(bbox_x_start, bbox_x_end):
                set_px(x, y, 0, 0, 0)
    # Sprite paint. We only x-clip — y is invariantly in-bounds because
    # `_decode` forces `new_h = panel_h` and `sprite_y = (panel_h -
    # sprite.height) // 2 = 0`, so `sprite_y + y ∈ [0, panel_h)`. If a
    # future change decouples sprite.height from panel_h (e.g. a
    # `fit="letterbox"` mode), add a `0 <= ry < panel_h` guard.
    for x, y, r, g, b in sprite.non_black[frame_idx]:
        rx = sprite_x + x
        if 0 <= rx < panel_w:
            set_px(rx, sprite_y + y, r, g, b)

    # 6. At t>=0.95, snap to incoming so the panel doesn't end on
    #    "outgoing-with-sprite-just-exited". Use bg-aware reset so
    #    the last transition frame matches the new section's bg
    #    instead of flashing black for one tick.
    if t >= SNAP_THRESHOLD:
        snap_reset(canvas, kwargs.get("incoming_bg_color"))
        incoming.draw(canvas)

    return canvas

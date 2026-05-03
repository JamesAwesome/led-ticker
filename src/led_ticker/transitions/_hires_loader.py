# src/led_ticker/transitions/_hires_loader.py
"""Decoder, cache, and per-frame painter for hi-res transitions.

The loader uses Pillow directly (not `widgets/_image_fit.apply_fit` /
`flatten_onto_black`) because those produce panel-sized output suitable
for the GIF widget. Hi-res transitions need sprite-sized output so the
sprite can be positioned horizontally during traversal.

`render_hires_frame` is shared by `NyanCat`, `NyanCatReverse`, `Pokeball`,
and `PokeballReverse` -- they all paint a single sprite that traverses
horizontally and snap to incoming near t=1.0.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from led_ticker.scaled_canvas import unwrap_to_real
from led_ticker.transitions._hires_registry import HIRES_REGISTRY, HiresSpec
from led_ticker.widgets._image_fit import scan_non_black

# Snap to incoming this fraction of the way through; the sprite has
# traveled most of the way across by then. Keeps the panel from showing
# a frame of "outgoing only" right before t=1.0.
SNAP_THRESHOLD: float = 0.95


@dataclass
class HiresFrames:
    """Decoded sprite, ready to paint at native resolution."""

    width: int
    height: int
    durations_ms: list[int]
    non_black: list[list[tuple[int, int, int, int, int]]]
    total_loop_ms: int = field(init=False)

    def __post_init__(self) -> None:
        self.total_loop_ms = sum(self.durations_ms)


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
                rgba = rgba.transpose(Image.FLIP_LEFT_RIGHT)

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

            durations.append(int(src.info.get("duration", 50)))
            non_black.append(scan_non_black(pixels, new_w, new_h))
            out_width = new_w
            out_height = new_h

    return HiresFrames(
        width=out_width,
        height=out_height,
        durations_ms=durations,
        non_black=non_black,
    )


@functools.cache
def load_hires(transition_name: str) -> HiresFrames | None:
    """Decode + cache a registered sprite. Returns None for unregistered names."""
    spec = HIRES_REGISTRY.get(transition_name)
    if spec is None:
        return None
    return _decode(spec)


def render_hires_frame(
    t: float,
    canvas: Any,
    outgoing: Any,
    incoming: Any,
    registry_name: str,
    **kwargs: Any,
) -> Any:
    """Paint one frame of a hi-res sprite traversing horizontally.

    Used by `NyanCat`/`NyanCatReverse`/`Pokeball`/`PokeballReverse` when
    the canvas is a `ScaledCanvas` and the registry has an entry.
    """
    sprite = load_hires(registry_name)
    if sprite is None:
        return canvas
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
    #    traversal direction -- sprite faces its travel direction.
    travel = panel_w + sprite.width
    spec = HIRES_REGISTRY[registry_name]
    if spec.flip_horizontal:
        sprite_x = panel_w - int(t * travel)
    else:
        sprite_x = -sprite.width + int(t * travel)
    sprite_y = (panel_h - sprite.height) // 2

    # 4. Paint sprite pixels to native physical canvas (skip-black).
    set_px = real.SetPixel
    for x, y, r, g, b in sprite.non_black[frame_idx]:
        rx = sprite_x + x
        if 0 <= rx < panel_w:
            set_px(rx, sprite_y + y, r, g, b)

    # 5. At t>=0.95, snap to incoming so the panel doesn't end on
    #    "outgoing-with-sprite-just-exited".
    if t >= SNAP_THRESHOLD:
        canvas.Clear()
        incoming.draw(canvas)

    return canvas

"""GIF decoding helper — pure function, no side effects.

Reads an animated GIF, applies a fit mode, and returns a list of
(rgb_bytes, duration_ms) tuples ready to be SetImage-blitted to the
panel.

Fit/alpha primitives live in `_image_fit.py` and are shared with the
still-image decoder.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from led_ticker.widgets._image_fit import (
    VALID_FITS,
    VALID_GIF_ALIGNS,
    validate_choice,
)
from led_ticker.widgets._image_fit import (
    apply_fit as _apply_fit,
)

_log = logging.getLogger(__name__)

_MIN_FRAME_DURATION_MS = 50


def decode_gif(
    path: Path,
    panel_w: int,
    panel_h: int,
    fit: str,
    image_align: str = "center",
) -> list[tuple[bytes, int]]:
    """Decode an animated GIF and return per-frame RGB bytes + durations.

    See `_image_fit.apply_fit` for the `fit` and `image_align` semantics
    — identical here.

    Frame durations below 50 ms are clamped to 50 ms (some GIFs encode
    `duration=0` which would otherwise spin the playback loop). Logs
    once per gif on the first clamped frame.
    """
    validate_choice("fit", fit, VALID_FITS)
    validate_choice("image_align", image_align, VALID_GIF_ALIGNS)

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"GIF not found at {path}")

    frames: list[tuple[bytes, int]] = []
    clamped_first_frame: int | None = None
    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        for i in range(n):
            img.seek(i)
            # RGBA preserves the GIF's transparency index; `apply_fit`
            # composites onto black so transparent areas become (0,0,0)
            # — which the scroll-text path already treats as "skip".
            rgba = img.convert("RGBA")
            fitted = _apply_fit(rgba, panel_w, panel_h, fit, image_align)
            raw_duration = int(img.info.get("duration", 100))
            duration = max(_MIN_FRAME_DURATION_MS, raw_duration)
            if duration != raw_duration and clamped_first_frame is None:
                clamped_first_frame = i
                _log.info(
                    "decode_gif: %s frame %d duration %dms clamped to %dms "
                    "(further clamps suppressed)",
                    path,
                    i,
                    raw_duration,
                    _MIN_FRAME_DURATION_MS,
                )
            frames.append((fitted.tobytes(), duration))
    return frames

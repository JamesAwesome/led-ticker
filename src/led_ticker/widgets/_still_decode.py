"""Still-image decoding helper — pure function, no side effects.

Reads a single image (PNG / JPG / single-frame GIF / anything Pillow
opens), applies a fit mode, and returns the panel-sized RGB bytes ready
to be SetImage-blitted to the panel.

Fit + alpha behavior is shared with the gif decoder via `_image_fit.py`.
Transparent PNGs (alpha-channel) and palette-transparency PNGs both
composite onto black so the existing skip-black scroll path Just Works.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from led_ticker.widgets._image_fit import (
    _VALID_FITS,
    _VALID_GIF_ALIGNS,
    apply_fit,
    validate_choice,
)


def decode_still(
    path: Path,
    panel_w: int,
    panel_h: int,
    fit: str,
    gif_align: str = "center",
) -> bytes:
    """Decode a single image and return panel-sized RGB bytes.

    See `_image_fit.apply_fit` for the `fit` and `gif_align` semantics —
    identical to the gif widget's behaviour.

    Returns `bytes` of length `panel_w * panel_h * 3` (RGB triples). For
    a multi-frame source (e.g. an animated GIF) only the first frame
    is decoded — use the `gif` widget for animation.
    """
    validate_choice("fit", fit, _VALID_FITS)
    validate_choice("gif_align", gif_align, _VALID_GIF_ALIGNS)

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"image not found at {path}")

    with Image.open(path) as img:
        # `seek(0)` is a no-op for single-frame formats and pins us to
        # the first frame for animated sources.
        if getattr(img, "n_frames", 1) > 1:
            img.seek(0)
        rgba = img.convert("RGBA")
        fitted = apply_fit(rgba, panel_w, panel_h, fit, gif_align)
        return fitted.tobytes()

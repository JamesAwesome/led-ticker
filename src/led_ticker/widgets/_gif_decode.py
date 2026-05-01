"""GIF decoding helper — pure function, no side effects.

Reads an animated GIF, applies a fit mode, and returns a list of
(rgb_bytes, duration_ms) tuples ready to be SetPixel-blitted to the
panel.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_VALID_FITS: frozenset[str] = frozenset({"pillarbox", "letterbox", "stretch", "crop"})
_MIN_FRAME_DURATION_MS = 50


def decode_gif(
    path: Path,
    panel_w: int,
    panel_h: int,
    fit: str,
) -> list[tuple[bytes, int]]:
    """Decode an animated GIF and return per-frame RGB bytes + durations.

    `fit` controls how each frame is scaled to fit the panel's
    `panel_w × panel_h`:

    - ``pillarbox``: scale by height (or width, whichever is the more
      restrictive constraint), center the result on a black canvas.
      Most common for square / portrait sources on a wide panel.
    - ``letterbox``: scale by width, center vertically with black bars.
    - ``stretch``: resize directly, distorting aspect ratio.
    - ``crop``: scale to cover both axes, center-crop the excess.

    Frame durations below 50 ms are clamped to 50 ms (some GIFs encode
    `duration=0` which would otherwise spin the playback loop).
    """
    if fit not in _VALID_FITS:
        raise ValueError(f"unknown fit={fit!r}; expected one of {sorted(_VALID_FITS)}")

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"GIF not found at {path}")

    frames: list[tuple[bytes, int]] = []
    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        for i in range(n):
            img.seek(i)
            rgb = img.convert("RGB")
            fitted = _apply_fit(rgb, panel_w, panel_h, fit)
            duration = max(_MIN_FRAME_DURATION_MS, int(img.info.get("duration", 100)))
            frames.append((fitted.tobytes(), duration))
    return frames


def _apply_fit(src: Image.Image, panel_w: int, panel_h: int, fit: str) -> Image.Image:
    """Scale + place `src` onto a `panel_w × panel_h` black canvas."""
    sw, sh = src.size
    if fit == "stretch":
        return src.resize((panel_w, panel_h), Image.Resampling.LANCZOS)

    if fit == "crop":
        scale = max(panel_w / sw, panel_h / sh)
        new_w = max(panel_w, int(round(sw * scale)))
        new_h = max(panel_h, int(round(sh * scale)))
        scaled = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x0 = (new_w - panel_w) // 2
        y0 = (new_h - panel_h) // 2
        return scaled.crop((x0, y0, x0 + panel_w, y0 + panel_h))

    # pillarbox / letterbox both fit-by-axis with black bands.
    # `pillarbox` prefers height; `letterbox` prefers width.
    if fit == "pillarbox":
        scale = panel_h / sh
        if int(round(sw * scale)) > panel_w:
            scale = panel_w / sw  # fall back to width-fit if width would overflow
    else:  # letterbox
        scale = panel_w / sw
        if int(round(sh * scale)) > panel_h:
            scale = panel_h / sh

    new_w = max(1, int(round(sw * scale)))
    new_h = max(1, int(round(sh * scale)))
    scaled = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (panel_w, panel_h), color=(0, 0, 0))
    canvas.paste(scaled, ((panel_w - new_w) // 2, (panel_h - new_h) // 2))
    return canvas

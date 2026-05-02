"""GIF decoding helper — pure function, no side effects.

Reads an animated GIF, applies a fit mode, and returns a list of
(rgb_bytes, duration_ms) tuples ready to be SetPixel-blitted to the
panel.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_VALID_FITS: frozenset[str] = frozenset({"pillarbox", "letterbox", "stretch", "crop"})
_VALID_H_ALIGNS: frozenset[str] = frozenset({"left", "center", "right"})
_MIN_FRAME_DURATION_MS = 50


def validate_choice(name: str, value: str, allowed: frozenset[str]) -> None:
    """Raise ValueError if `value` is not in `allowed`. Shared by the gif
    widget and decode helper to keep error messages identical."""
    if value not in allowed:
        raise ValueError(f"unknown {name}={value!r}; expected one of {sorted(allowed)}")


def decode_gif(
    path: Path,
    panel_w: int,
    panel_h: int,
    fit: str,
    h_align: str = "center",
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

    `h_align` (left | center | right) anchors the scaled image
    horizontally when there's slack — only meaningful for ``pillarbox``
    where the scaled width is < panel width. ``stretch`` / ``crop`` /
    ``letterbox`` all fill the panel width so it has no effect.

    Frame durations below 50 ms are clamped to 50 ms (some GIFs encode
    `duration=0` which would otherwise spin the playback loop).
    """
    validate_choice("fit", fit, _VALID_FITS)
    validate_choice("h_align", h_align, _VALID_H_ALIGNS)

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"GIF not found at {path}")

    frames: list[tuple[bytes, int]] = []
    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        for i in range(n):
            img.seek(i)
            # RGBA preserves the GIF's transparency index; `_apply_fit`
            # composites onto black so transparent areas become (0,0,0)
            # — which the scroll-text path already treats as "skip".
            rgba = img.convert("RGBA")
            fitted = _apply_fit(rgba, panel_w, panel_h, fit, h_align)
            duration = max(_MIN_FRAME_DURATION_MS, int(img.info.get("duration", 100)))
            frames.append((fitted.tobytes(), duration))
    return frames


def _flatten_onto_black(
    rgba: Image.Image, panel_w: int, panel_h: int, x_off: int, y_off: int
) -> Image.Image:
    """Paste an RGBA image onto a black RGB canvas using its alpha as mask.

    Transparent areas (alpha=0) become pure black (0,0,0), which the
    scroll-text path treats as "skip" — letting underlying text show
    through. Semi-transparent edges get blended toward black, which on
    LEDs reads as a soft halo at the gif's silhouette.
    """
    out = Image.new("RGB", (panel_w, panel_h), color=(0, 0, 0))
    if rgba.mode == "RGBA":
        out.paste(rgba, (x_off, y_off), mask=rgba.split()[3])
    else:
        out.paste(rgba, (x_off, y_off))
    return out


def _apply_fit(
    src: Image.Image, panel_w: int, panel_h: int, fit: str, h_align: str = "center"
) -> Image.Image:
    """Scale + place `src` onto a `panel_w × panel_h` black canvas.

    `src` is expected in RGBA mode so transparency survives the resize.
    """
    sw, sh = src.size
    if fit == "stretch":
        scaled = src.resize((panel_w, panel_h), Image.Resampling.LANCZOS)
        return _flatten_onto_black(scaled, panel_w, panel_h, 0, 0)

    if fit == "crop":
        scale = max(panel_w / sw, panel_h / sh)
        new_w = max(panel_w, int(round(sw * scale)))
        new_h = max(panel_h, int(round(sh * scale)))
        scaled = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x0 = (new_w - panel_w) // 2
        y0 = (new_h - panel_h) // 2
        cropped = scaled.crop((x0, y0, x0 + panel_w, y0 + panel_h))
        return _flatten_onto_black(cropped, panel_w, panel_h, 0, 0)

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
    if h_align == "left":
        x_off = 0
    elif h_align == "right":
        x_off = max(0, panel_w - new_w)
    else:  # center
        x_off = (panel_w - new_w) // 2
    return _flatten_onto_black(scaled, panel_w, panel_h, x_off, (panel_h - new_h) // 2)

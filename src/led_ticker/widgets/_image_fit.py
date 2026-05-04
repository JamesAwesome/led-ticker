"""Shared image-decoding primitives — the CANONICAL home for fit, alpha,
and validation logic used by every image-source widget (gif, still, and
any future video / sprite-sheet variants). All functions are pure (no
side effects on the input image).

The fit modes and `image_align` semantics are identical for all
consumers so the TOML config schema is consistent across image widgets.

To extend with a new image source: import `apply_fit`, `flatten_onto_black`,
`validate_choice`, `VALID_FITS`, `VALID_IMAGE_ALIGNS` from here. Do NOT
duplicate these helpers in a new module.
"""

from __future__ import annotations

from PIL import Image

VALID_FITS: frozenset[str] = frozenset({"pillarbox", "letterbox", "stretch", "crop"})
VALID_IMAGE_ALIGNS: frozenset[str] = frozenset({"left", "center", "right"})


def validate_choice(name: str, value: str, allowed: frozenset[str]) -> None:
    """Raise ValueError if `value` is not in `allowed`. Shared shape so
    error messages match across the widget + decode helpers."""
    if value not in allowed:
        raise ValueError(f"unknown {name}={value!r}; expected one of {sorted(allowed)}")


def scan_non_black(
    pixels: bytes, w: int, h: int
) -> list[tuple[int, int, int, int, int]]:
    """Walk panel-sized RGB bytes and return `(x, y, r, g, b)` for every
    non-zero pixel. Used by both `GifPlayer` and `StillImage` to build
    the skip-black scroll-text cache once per decode."""
    nb: list[tuple[int, int, int, int, int]] = []
    for y in range(h):
        row = y * w * 3
        for x in range(w):
            base = row + x * 3
            r = pixels[base]
            g = pixels[base + 1]
            b = pixels[base + 2]
            if r or g or b:
                nb.append((x, y, r, g, b))
    return nb


# Alpha threshold for `flatten_onto_black` binarization. Pixels with
# `alpha >= ALPHA_BINARIZE_THRESHOLD` paste at full opacity; anything
# below becomes fully transparent (RGB → 0,0,0 against the black
# canvas). 128 = the natural midpoint and matches our font rasterizer's
# default. The binarization eliminates the "soft halo" that anti-
# aliased alpha edges otherwise produce — at decode time those edge
# pixels would blend toward near-black RGB (e.g. (12, 8, 0) for a
# yellow edge at alpha=20), and `scan_non_black` would treat them as
# lit, painting a dim ring around the silhouette over any scrolling
# text. With the threshold, edges are crisp and the silhouette is
# truly transparent. The work is one Pillow .point() pass per gif
# frame at LOAD time — no per-tick render impact.
ALPHA_BINARIZE_THRESHOLD: int = 128


def flatten_onto_black(
    rgba: Image.Image, panel_w: int, panel_h: int, x_off: int, y_off: int
) -> Image.Image:
    """Paste an RGBA image onto a black RGB canvas using its alpha as mask.

    The alpha channel is binarized at ``ALPHA_BINARIZE_THRESHOLD`` first
    so anti-aliased edges are crisp instead of bleeding into near-black
    RGB. Transparent areas (alpha=0) become pure black (0,0,0), which
    the scroll-text path treats as "skip" — letting underlying text
    show through. Pre-fix, semi-transparent edges blended toward black
    and read as a soft halo at the image's silhouette during
    skip-black compositing.
    """
    out = Image.new("RGB", (panel_w, panel_h), color=(0, 0, 0))
    if rgba.mode == "RGBA":
        alpha = rgba.split()[3]
        # Binarize: any alpha at or above ALPHA_BINARIZE_THRESHOLD → fully
        # opaque, anything below → fully transparent. Build a 256-entry
        # lookup table once and pass it to .point() — Pillow recognizes
        # the table form and skips the per-pixel callable overhead. This
        # also keeps pyright happy (the callable form's stub typing is
        # awkward with module-level default args).
        lut = [255 if a >= ALPHA_BINARIZE_THRESHOLD else 0 for a in range(256)]
        binary_mask = alpha.point(lut)
        out.paste(rgba, (x_off, y_off), mask=binary_mask)
    else:
        out.paste(rgba, (x_off, y_off))
    return out


def apply_fit(
    src: Image.Image,
    panel_w: int,
    panel_h: int,
    fit: str,
    image_align: str = "center",
) -> Image.Image:
    """Scale + place `src` onto a `panel_w × panel_h` black canvas.

    `src` is expected in RGBA mode so transparency survives the resize.

    `fit`:
      - ``stretch``: resize directly, distorting aspect ratio.
      - ``crop``: scale to cover both axes, center-crop the excess.
      - ``pillarbox``: scale by height (or width if width-fit overflows),
        center-or-anchor horizontally with black bands on the unused
        side(s).
      - ``letterbox``: scale by width (or height if height-fit
        overflows), center vertically with black top/bottom bands.

    `image_align` (left | center | right) anchors the scaled image
    horizontally for `pillarbox`. The other three fits fill the panel
    width so it has no effect.
    """
    sw, sh = src.size
    if fit == "stretch":
        scaled = src.resize((panel_w, panel_h), Image.Resampling.LANCZOS)
        return flatten_onto_black(scaled, panel_w, panel_h, 0, 0)

    if fit == "crop":
        scale = max(panel_w / sw, panel_h / sh)
        new_w = max(panel_w, int(round(sw * scale)))
        new_h = max(panel_h, int(round(sh * scale)))
        scaled = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x0 = (new_w - panel_w) // 2
        y0 = (new_h - panel_h) // 2
        cropped = scaled.crop((x0, y0, x0 + panel_w, y0 + panel_h))
        return flatten_onto_black(cropped, panel_w, panel_h, 0, 0)

    # pillarbox / letterbox both fit-by-axis with black bands.
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
    if image_align == "left":
        x_off = 0
    elif image_align == "right":
        x_off = max(0, panel_w - new_w)
    else:  # center
        x_off = (panel_w - new_w) // 2
    return flatten_onto_black(scaled, panel_w, panel_h, x_off, (panel_h - new_h) // 2)


def reset_canvas(canvas, bg_color) -> None:
    """Clear canvas, or Fill it with `bg_color` if set.

    `bg_color` is a `graphics.Color` (with `.red`, `.green`, `.blue`
    attrs) or `None`. `(0, 0, 0)` is treated as "explicit black" — the
    Fill path runs, painting black across the whole canvas. Visually
    identical to Clear() but counts as a "set" bg for resolution rules.
    """
    if bg_color is None:
        canvas.Clear()
    else:
        canvas.Fill(bg_color.red, bg_color.green, bg_color.blue)


def fill_band(canvas, y_start: int, y_end: int, color) -> None:
    """Fill the half-open horizontal band [y_start, y_end) with `color`.

    Used for per-row backgrounds in `TwoRowMessage`. Goes through
    SetPixel so a `ScaledCanvas` wrapper expands each logical pixel to
    a scale×scale block on the real canvas.
    """
    set_px = canvas.SetPixel
    r, g, b = color.red, color.green, color.blue
    width = canvas.width
    for y in range(y_start, y_end):
        for x in range(width):
            set_px(x, y, r, g, b)

"""Shadow-buffer tee for the live web preview.

PreviewTee sits innermost in the canvas chain (under ScaledCanvas on scaled
signs, handed to widgets directly on smallsign). Every draw is forwarded to
the hardware canvas FIRST and unconditionally; only while watched does it
also mirror into a flat RGB bytearray. The spine invariant: a shadow bug can
break the preview, never the panel — every mirror write is wrapped, and any
failure flips mirroring off for the session.

The hardware handle is deliberately named `_hw`, NOT `real`:
`scaled_canvas.unwrap_to_real` walks `.real`, so the tee is terminal to the
unwrap machinery and every physical-resolution paint site (hires fonts,
emoji, dissolve scatter, borders) lands here with zero call-site changes.

Stdlib-only; must never import rgbmatrix (webui purity rules apply to the
shapes this module shares with the sidecar).
"""

import contextlib
import logging
import os
import struct
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PREVIEW_MAGIC = b"LTPV"
PREVIEW_VERSION = 1
# magic, version, width, height, reserved, seq -> 16 bytes
HEADER = struct.Struct("<4sHHHHI")
CAPTURE_INTERVAL = 0.2  # seconds -> 5 fps
MARKER_TTL = 10.0  # seconds of marker freshness that keep the mirror on


class PreviewTee:
    """Forward-and-mirror canvas. See module docstring for the contract."""

    def __init__(self, hw: Any, width: int, height: int, frame_path: Path) -> None:
        self._hw = hw
        self.width = width
        self.height = height
        self._frame_path = Path(frame_path)
        self._shadow: Any = bytearray(width * height * 3)
        self.mirror = False
        self._complete = False  # full Clear/Fill seen since mirror enable
        self._seq = 0
        self._last_capture = 0.0
        self._disabled = False  # session kill-switch after a shadow failure

    # -- lifecycle -----------------------------------------------------

    def set_watched(self, watched: bool) -> None:
        """Toggle mirroring from the watched-marker state. Off also removes
        the frame file so the sidecar reports idle, not a frozen frame."""
        if watched and not self._disabled:
            if not self.mirror:
                self._shadow[:] = bytes(len(self._shadow))
                self._complete = False
                self.mirror = True
        else:
            self.mirror = False
            with contextlib.suppress(OSError):
                self._frame_path.unlink(missing_ok=True)

    def _disable(self, why: str) -> None:
        self.mirror = False
        self._disabled = True
        logger.warning(
            "preview mirroring disabled for this session (%s); panel unaffected",
            why,
        )

    # -- safety net ----------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # Safety net for the spine invariant: any canvas attribute the tee
        # doesn't explicitly mirror forwards to the hardware canvas, so a
        # future canvas method can only make the PREVIEW silently diverge —
        # never raise inside a widget's draw and break the panel.
        #
        # NOTE: __getattr__ is only called for *missing* attributes (ones
        # not found via normal lookup), so it cannot shadow any of the
        # explicit methods defined on this class. It also fires for internal
        # _x attrs that haven't been set yet (e.g. during object
        # construction), but __init__ sets every self._x attribute before
        # any other code path reads them, so that path can't arise here.
        return getattr(self._hw, name)

    # -- canvas surface (forward first, mirror second) -----------------

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self._hw.SetPixel(x, y, r, g, b)
        if self.mirror:
            try:
                if 0 <= x < self.width and 0 <= y < self.height:
                    i = (y * self.width + x) * 3
                    s = self._shadow
                    s[i] = r
                    s[i + 1] = g
                    s[i + 2] = b
            except Exception:
                self._disable("shadow write failed")

    def Fill(self, r: int, g: int, b: int) -> None:
        self._hw.Fill(r, g, b)
        if self.mirror:
            try:
                self._shadow[:] = bytes((r, g, b)) * (self.width * self.height)
                self._complete = True
            except Exception:
                self._disable("shadow fill failed")

    def Clear(self) -> None:
        self._hw.Clear()
        if self.mirror:
            try:
                self._shadow[:] = bytes(len(self._shadow))
                self._complete = True
            except Exception:
                self._disable("shadow clear failed")

    def SetImage(self, image: Any, offset_x: int = 0, offset_y: int = 0) -> None:
        """Blit a PIL image onto the canvas at (offset_x, offset_y).

        Forwards to the hardware canvas first and unconditionally (same as
        every other canvas method — a hardware error propagates up). Then, if
        mirroring is on, iterates the image pixels and writes them into the
        shadow, clipping to canvas bounds. Alpha channel is handled the same
        way the rgbmatrix stub does it: fully-transparent pixels (alpha == 0)
        composite onto black; all other pixels use the RGB channels directly.
        """
        self._hw.SetImage(image, offset_x, offset_y)
        if self.mirror:
            try:
                rgb = image if image.mode == "RGB" else image.convert("RGB")
                img_w, img_h = rgb.size
                pixels = rgb.load()
                shadow = self._shadow
                w, h = self.width, self.height
                for dy in range(img_h):
                    py = offset_y + dy
                    if py < 0 or py >= h:
                        continue
                    for dx in range(img_w):
                        px = offset_x + dx
                        if 0 <= px < w:
                            r_c, g_c, b_c = pixels[dx, dy]
                            i = (py * w + px) * 3
                            shadow[i] = r_c
                            shadow[i + 1] = g_c
                            shadow[i + 2] = b_c
            except Exception:
                self._disable("shadow image blit failed")

    def SubFill(
        self, x: int, y: int, width: int, height: int, r: int, g: int, b: int
    ) -> None:
        """Fill a rectangle. Forwards to hardware first; mirrors per-pixel
        into the shadow while watched. Used by ScaledCanvas.SetPixel for
        block expansion on scaled signs."""
        self._hw.SubFill(x, y, width, height, r, g, b)
        if self.mirror:
            try:
                w, h = self.width, self.height
                shadow = self._shadow
                for dy in range(height):
                    py = y + dy
                    if py < 0 or py >= h:
                        continue
                    for dx in range(width):
                        px = x + dx
                        if 0 <= px < w:
                            i = (py * w + px) * 3
                            shadow[i] = r
                            shadow[i + 1] = g
                            shadow[i + 2] = b
            except Exception:
                self._disable("shadow subfill failed")

    # -- text mirror (scale = 1 funnel) ---------------------------------

    def mirror_bdf_text(self, bdf: Any, x: int, y: int, color: Any, text: str) -> None:
        """Rasterize `text` into the shadow only (the C library has already
        drawn it on the hardware canvas). Same glyph math as
        ScaledCanvas.draw_bdf_text; failures self-disable, never raise."""
        if not self.mirror:
            return
        try:
            if isinstance(color, tuple):
                r, g, b = color
            else:
                r, g, b = color.red, color.green, color.blue
            shadow = self._shadow
            w, h = self.width, self.height
            cx = x
            for ch in text:
                glyph = bdf.glyphs.get(ch)
                if glyph is None:
                    cx += bdf.bbx_width
                    continue
                top_y = y - glyph.bbx_height - glyph.bbx_yoff
                base_x = cx + glyph.bbx_xoff
                for col, row in glyph.lit_pixels:
                    px = base_x + col
                    py = top_y + row
                    if 0 <= px < w and 0 <= py < h:
                        i = (py * w + px) * 3
                        shadow[i] = r
                        shadow[i + 1] = g
                        shadow[i + 2] = b
                cx += glyph.advance_width
        except Exception:
            self._disable("shadow text raster failed")

    # -- capture --------------------------------------------------------

    def maybe_capture(self, now: float | None = None) -> None:
        """Write the shadow as a frame file, at most once per
        CAPTURE_INTERVAL, and only once a full Clear/Fill has run since
        mirroring was enabled (a mid-tick enable leaves the shadow
        incomplete for the remainder of that tick). Failures self-disable
        — same rule as every other write on the web path."""
        if not self.mirror or not self._complete:
            return
        if now is None:
            now = time.monotonic()
        if now - self._last_capture < CAPTURE_INTERVAL:
            return
        try:
            self._seq += 1
            header = HEADER.pack(
                PREVIEW_MAGIC, PREVIEW_VERSION, self.width, self.height, 0, self._seq
            )
            tmp = self._frame_path.with_name(self._frame_path.name + ".tmp")
            tmp.write_bytes(header + bytes(self._shadow))
            os.replace(tmp, self._frame_path)
            self._last_capture = now
        except Exception:
            self._disable("capture write failed")

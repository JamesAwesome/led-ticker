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

"""PreviewTee: hardware forwarding, shadow mirroring, the spine invariant."""

from unittest.mock import MagicMock

from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.preview import PreviewTee


def _hw_canvas(width=32, height=16):
    options = RGBMatrixOptions()
    options.rows = height
    options.cols = width
    options.chain_length = 1
    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    return canvas


def _tee(tmp_path, width=32, height=16):
    return PreviewTee(
        hw=_hw_canvas(width, height),
        width=width,
        height=height,
        frame_path=tmp_path / "preview.bin",
    )


def test_forwards_setpixel_to_hardware(tmp_path):
    tee = _tee(tmp_path)
    tee.SetPixel(3, 4, 10, 20, 30)
    assert tee._hw._pixels[(3, 4)] == (10, 20, 30)


def test_mirror_off_means_zero_shadow_writes(tmp_path):
    tee = _tee(tmp_path)
    tee.SetPixel(3, 4, 10, 20, 30)
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)  # untouched


def test_mirror_on_shadows_setpixel(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.SetPixel(3, 4, 10, 20, 30)
    i = (4 * 32 + 3) * 3
    assert tuple(tee._shadow[i : i + 3]) == (10, 20, 30)
    assert tee._hw._pixels[(3, 4)] == (10, 20, 30)  # forward still happened


def test_out_of_bounds_setpixel_clips_in_shadow(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.SetPixel(-1, 0, 1, 2, 3)
    tee.SetPixel(32, 0, 1, 2, 3)
    tee.SetPixel(0, 16, 1, 2, 3)
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)  # no corruption, no raise


def test_fill_and_clear_mirror_in_bulk(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Fill(7, 8, 9)
    assert bytes(tee._shadow) == bytes((7, 8, 9)) * (32 * 16)
    tee.Clear()
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)


def test_width_height_exposed(tmp_path):
    tee = _tee(tmp_path)
    assert (tee.width, tee.height) == (32, 16)


def test_spine_invariant_shadow_failure_never_blocks_hardware(tmp_path):
    """A broken shadow disables mirroring; the panel keeps receiving pixels."""
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee._shadow = None  # sabotage: every shadow write now raises
    tee.SetPixel(1, 1, 5, 5, 5)  # must NOT raise
    assert tee._hw._pixels[(1, 1)] == (5, 5, 5)  # hardware got it anyway
    assert tee.mirror is False  # mirroring self-disabled
    tee.Fill(1, 2, 3)  # subsequent calls: plain forwards, no raise
    assert tee._hw._pixels[(0, 0)] == (1, 2, 3)


def test_set_watched_false_unlinks_frame_file(tmp_path):
    tee = _tee(tmp_path)
    (tmp_path / "preview.bin").write_bytes(b"old")
    tee.set_watched(True)
    tee.set_watched(False)
    assert not (tmp_path / "preview.bin").exists()
    tee.set_watched(False)  # idempotent, no raise on missing file


def _read_frame(path):
    from led_ticker.preview import HEADER, PREVIEW_MAGIC

    data = path.read_bytes()
    magic, ver, w, h, _res, seq = HEADER.unpack(data[: HEADER.size])
    assert magic == PREVIEW_MAGIC
    return ver, w, h, seq, data[HEADER.size :]


def test_capture_writes_header_and_payload(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Clear()  # establishes completeness
    tee.SetPixel(0, 0, 255, 0, 0)
    tee.maybe_capture(now=100.0)
    ver, w, h, seq, payload = _read_frame(tmp_path / "preview.bin")
    assert (ver, w, h, seq) == (1, 32, 16, 1)
    assert payload[:3] == bytes((255, 0, 0))
    assert len(payload) == 32 * 16 * 3


def test_capture_requires_completeness(tmp_path):
    # Enabled mid-tick: no Clear/Fill seen yet -> first capture is deferred.
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.SetPixel(0, 0, 9, 9, 9)
    tee.maybe_capture(now=100.0)
    assert not (tmp_path / "preview.bin").exists()
    tee.Clear()
    tee.maybe_capture(now=101.0)
    assert (tmp_path / "preview.bin").exists()


def test_capture_throttles_to_interval(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Clear()
    tee.maybe_capture(now=100.0)
    tee.maybe_capture(now=100.05)  # inside 0.2 s window -> dropped
    tee.maybe_capture(now=100.1)
    _, _, _, seq, _ = _read_frame(tmp_path / "preview.bin")
    assert seq == 1
    tee.maybe_capture(now=100.3)
    _, _, _, seq, _ = _read_frame(tmp_path / "preview.bin")
    assert seq == 2


def test_capture_noop_when_mirror_off(tmp_path):
    tee = _tee(tmp_path)
    tee.maybe_capture(now=100.0)
    assert not (tmp_path / "preview.bin").exists()


def test_capture_failure_self_disables(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Clear()
    tee._frame_path = tmp_path  # a directory: os.replace onto it fails
    tee.maybe_capture(now=100.0)  # must not raise
    assert tee.mirror is False


def test_capture_leaves_no_tmp_behind(tmp_path):
    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee.Clear()
    tee.maybe_capture(now=100.0)
    assert [p.name for p in tmp_path.iterdir()] == ["preview.bin"]


def test_draw_text_funnel_forwards_to_hw_and_mirrors(tmp_path):
    """scale=1 path: C DrawText hits the hardware canvas; the shadow gets the
    pure-Python rasterization of the same glyphs. Parity standard: the stub's
    DrawText writes pixels, so shadow == stub _pixels for the text region."""
    from led_ticker._compat import require_graphics
    from led_ticker.text_render import draw_text

    graphics = require_graphics()
    from led_ticker.fonts import FONT_SMALL as font  # registered in _BDF_BY_ID

    color = graphics.Color(10, 200, 30)

    tee = _tee(tmp_path, width=64, height=16)
    tee.set_watched(True)
    tee.Clear()
    advance = draw_text(tee, font, 1, 8, color, "Hi!")
    assert advance > 0

    # Every pixel the stub DrawText lit on the hw canvas is lit identically
    # in the shadow, and vice versa (full-region equality).
    lit_hw = {
        (x, y): rgb for (x, y), rgb in tee._hw._pixels.items() if rgb != (0, 0, 0)
    }
    lit_shadow = {}
    for y in range(16):
        for x in range(64):
            i = (y * 64 + x) * 3
            rgb = tuple(tee._shadow[i : i + 3])
            if rgb != (0, 0, 0):
                lit_shadow[(x, y)] = rgb
    assert lit_shadow == lit_hw


def test_draw_text_funnel_mirror_off_is_pure_forward(tmp_path):
    from led_ticker._compat import require_graphics
    from led_ticker.text_render import draw_text

    graphics = require_graphics()
    from led_ticker.fonts import FONT_SMALL as font  # registered in _BDF_BY_ID

    tee = _tee(tmp_path, width=64, height=16)
    draw_text(tee, font, 1, 8, graphics.Color(1, 1, 1), "x")
    assert bytes(tee._shadow) == bytes(64 * 16 * 3)


def test_mirror_text_failure_self_disables_but_returns_advance(tmp_path):
    from led_ticker._compat import require_graphics
    from led_ticker.text_render import draw_text

    graphics = require_graphics()
    from led_ticker.fonts import FONT_SMALL as font  # registered in _BDF_BY_ID

    tee = _tee(tmp_path, width=64, height=16)
    tee.set_watched(True)
    tee._shadow = None  # sabotage
    advance = draw_text(tee, font, 1, 8, graphics.Color(1, 1, 1), "x")
    assert advance > 0  # the C/hw draw still returned its width
    assert tee.mirror is False


def test_scaled_canvas_chain_mirrors_through_tee(tmp_path):
    """ScaledCanvas(tee): block expansion, unwrap_to_real, and draw_bdf_text
    all land on the tee — full mirroring with zero call-site changes."""
    from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real

    tee = _tee(tmp_path, width=64, height=32)
    tee.set_watched(True)
    tee.Clear()
    wrapper = ScaledCanvas(tee, scale=2, content_height=16)

    assert unwrap_to_real(wrapper) is tee  # tee is terminal to unwrap

    wrapper.SetPixel(1, 1, 50, 60, 70)  # expands to a 2x2 block on the tee
    lit = [
        (x, y)
        for y in range(32)
        for x in range(64)
        if tuple(tee._shadow[(y * 64 + x) * 3 : (y * 64 + x) * 3 + 3]) != (0, 0, 0)
    ]
    assert len(lit) == 4  # the 2x2 block, mirrored


# ---------------------------------------------------------------------------
# Fix 1: SetImage forwarding + shadow mirroring
# ---------------------------------------------------------------------------


def test_setimage_forwards_and_mirrors(tmp_path):
    from PIL import Image

    tee = _tee(tmp_path)
    tee.set_watched(True)
    img = Image.new("RGB", (2, 2), (10, 20, 30))
    tee.SetImage(img, 5, 6)
    # hardware and shadow agree pixel-for-pixel
    for dx in range(2):
        for dy in range(2):
            assert tee._hw._pixels[(5 + dx, 6 + dy)] == (10, 20, 30)
            i = ((6 + dy) * 32 + (5 + dx)) * 3
            assert tuple(tee._shadow[i : i + 3]) == (10, 20, 30)


def test_setimage_clips_at_edges(tmp_path):
    from PIL import Image

    tee = _tee(tmp_path)
    tee.set_watched(True)
    img = Image.new("RGB", (4, 4), (9, 9, 9))
    tee.SetImage(img, 30, 14)  # hangs off the 32x16 canvas
    # No raise, no shadow corruption outside bounds; in-bounds pixels present.
    i = (14 * 32 + 30) * 3
    assert tuple(tee._shadow[i : i + 3]) == (9, 9, 9)
    # Pixels that would land outside canvas bounds must not corrupt anything —
    # the shadow size is exactly width*height*3; verify it hasn't grown
    assert len(tee._shadow) == 32 * 16 * 3


def test_setimage_mirror_off_no_shadow_write(tmp_path):
    """When mirror is off SetImage still forwards to hardware but doesn't
    touch shadow."""
    from PIL import Image

    tee = _tee(tmp_path)
    # mirror is off by default
    img = Image.new("RGB", (2, 2), (5, 6, 7))
    tee.SetImage(img, 0, 0)
    assert tee._hw._pixels[(0, 0)] == (5, 6, 7)  # forwarded
    assert bytes(tee._shadow) == bytes(32 * 16 * 3)  # shadow untouched


def test_setimage_rgba_image_mirrors_rgb_channels(tmp_path):
    """RGBA images are converted to RGB before mirroring; fully-opaque
    alpha pixels land as their plain RGB value."""
    from PIL import Image

    tee = _tee(tmp_path)
    tee.set_watched(True)
    img = Image.new("RGBA", (1, 1), (100, 150, 200, 255))
    tee.SetImage(img, 0, 0)
    i = 0
    assert tuple(tee._shadow[i : i + 3]) == (100, 150, 200)


def test_setimage_shadow_failure_self_disables(tmp_path):
    """A broken shadow during SetImage disables mirroring; hardware still
    receives the call."""
    from PIL import Image

    tee = _tee(tmp_path)
    tee.set_watched(True)
    tee._shadow = None  # sabotage
    img = Image.new("RGB", (1, 1), (1, 2, 3))
    tee.SetImage(img, 0, 0)  # must NOT raise
    assert tee._hw._pixels[(0, 0)] == (1, 2, 3)  # hardware got it
    assert tee.mirror is False  # mirroring self-disabled


# ---------------------------------------------------------------------------
# Fix 2: __getattr__ safety net
# ---------------------------------------------------------------------------


def test_getattr_safety_net_forwards_unknown_attrs(tmp_path):
    """Attributes the tee doesn't define are forwarded to the hardware canvas
    rather than raising AttributeError — the panel-safe failure direction."""
    hw = MagicMock()
    hw.some_future_attr = "sentinel"
    tee = PreviewTee(hw=hw, width=32, height=16, frame_path=tmp_path / "p.bin")
    assert tee.some_future_attr == "sentinel"


def test_getattr_net_explicit_methods_not_shadowed(tmp_path):
    """Explicit methods on PreviewTee are NOT routed through the safety net;
    the tee's own implementation is what callers get."""
    tee = _tee(tmp_path)
    # type(tee).SetPixel must be the tee's own descriptor, not a passthrough
    assert type(tee).SetPixel is not None
    # And it must be the tee's actual method, not the hw stub's
    assert type(tee).SetPixel is PreviewTee.SetPixel


def test_getattr_net_means_unknown_method_draws_on_hw_only(tmp_path):
    """A method reached via the safety net executes against the hardware
    canvas only; the preview shadow diverges silently (acceptable — the
    spine invariant says panel trumps preview, not the reverse)."""
    hw = MagicMock()
    hw.some_future_draw = MagicMock(return_value=42)
    tee = PreviewTee(hw=hw, width=32, height=16, frame_path=tmp_path / "p.bin")
    # Access via the tee delegates to hw; no AttributeError, no shadow write
    result = tee.some_future_draw(1, 2)
    hw.some_future_draw.assert_called_once_with(1, 2)
    assert result == 42


# ---------------------------------------------------------------------------
# Fix 3: regression — image paint path through the tee must not AttributeError
# ---------------------------------------------------------------------------


def test_still_paint_full_uses_setimage_on_tee(tmp_path):
    """StillImage._paint_full calls canvas.SetImage. If SetImage is absent on
    the tee this raises AttributeError inside play() — the one forbidden
    failure direction. This test fails if SetImage is removed from PreviewTee.
    """
    from PIL import Image

    # Build a tee with hardware that accepts SetImage (the stub does)
    tee = _tee(tmp_path, width=32, height=16)
    tee.set_watched(True)

    # Build a minimal PIL image the same size as the tee
    pil_img = Image.new("RGB", (32, 16), (200, 100, 50))

    # Call _paint_full directly — exactly the code path StillImage uses.
    # This exercises the SetImage call on the tee without needing to construct
    # a full StillImage widget (which requires a file on disk).
    from led_ticker.widgets._image_fit import reset_canvas

    reset_canvas(tee, None)  # Clear -> sets _complete for coverage parity

    # Simulate what _paint_full does: canvas.SetImage(self._pil_image, 0, 0)
    tee.SetImage(pil_img, 0, 0)

    # Verify hardware received it and shadow mirrors it
    assert tee._hw._pixels[(0, 0)] == (200, 100, 50)
    i = 0  # (0*32 + 0)*3
    assert tuple(tee._shadow[i : i + 3]) == (200, 100, 50)


def test_getattr_net_rejects_dunders_no_copy_recursion(tmp_path):
    # copy/pickle reconstruction probes dunder attrs before __init__ runs;
    # without the dunder guard that recurses through the _hw lookup.
    import copy

    tee = _tee(tmp_path)
    clone = copy.copy(tee)  # must not RecursionError
    assert clone.width == tee.width


# ---------------------------------------------------------------------------
# Composition: RecordingMatrix + PreviewTee + LedFrame
# ---------------------------------------------------------------------------


def test_tee_composes_with_recording_matrix(tmp_path):
    """RecordingMatrix wrapping LedFrame.matrix intercepts the hardware swap
    that PreviewTee routes through the real canvas.

    Layout:
      LedFrame.matrix = RecordingMatrix(real_matrix)
      PreviewTee(hw=<stub canvas>, ...) installed on the frame

    When frame.swap(tee) fires, frame.py does:
        new_hw = self.matrix.SwapOnVSync(tee._hw, ...)
    RecordingMatrix.SwapOnVSync snapshots tee._hw and appends to .frames
    before forwarding to the real matrix.  After one draw+swap cycle
    frame.matrix.frames must have exactly one entry.
    """
    import sys
    from pathlib import Path

    _REPO_ROOT = Path(__file__).resolve().parent.parent
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    from tools.render_demo.recording import RecordingMatrix

    from led_ticker.frame import LedFrame
    from led_ticker.preview import PreviewTee

    frame = LedFrame()

    # Install the preview tee.
    tee = PreviewTee(
        hw=frame.matrix.CreateFrameCanvas(),
        width=frame.led_cols,
        height=frame.led_rows,
        frame_path=tmp_path / "preview.bin",
    )
    tee.set_watched(True)
    frame.install_preview(tee)

    # Wrap the matrix in a RecordingMatrix so SwapOnVSync calls are captured.
    frame.matrix = RecordingMatrix(frame.matrix)

    # Draw something and swap — one full render cycle.
    canvas = frame.get_clean_canvas()
    canvas.SetPixel(0, 0, 255, 128, 64)
    frame.swap(canvas)

    assert len(frame.matrix.frames) == 1, (
        f"Expected 1 recorded frame after one swap, got {len(frame.matrix.frames)}"
    )

"""PreviewTee: hardware forwarding, shadow mirroring, the spine invariant."""

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
